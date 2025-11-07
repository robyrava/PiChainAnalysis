from connectors.bitcoin_connector import BitcoinConnector
from connectors.neo4j_connector import Neo4jConnector
from connectors.electrs_connector import ElectrsConnector
from connectors.public_api_connector import PublicApiConnector
from core.data_parser import DataParser
from typing import Tuple, Dict, Any
from analysis.peeling_chain_analyzer import PeelingChainAnalyzer

class Manager:
    """
    Orchestra le operazioni dell'applicazione, coordinando i connettori
    e il parser dei dati.
    """
    def __init__(self):
        """Inizializza tutti i componenti necessari."""
        self.btc_connector = BitcoinConnector()
        self.neo4j_connector = Neo4jConnector()
        self.electrs_connector = ElectrsConnector()
        self.public_api_connector = PublicApiConnector()
        self.parser = DataParser()
        self.using_public_api = False
        self.public_api_steps = 0 # Tengo il contatore per ritornare al nodo locale dopo 5 passi

    def start_peeling_chain_analysis(self, start_hash: str) -> Dict[str, Any]:
        """
        Inizializza e avvia l'analisi di una peeling chain.

        Questo metodo agisce come un ponte verso il modulo di analisi,
        fornendogli i connettori necessari per operare.

        Args:
            start_hash: L'hash della transazione da cui iniziare l'analisi.

        Returns:
            Un dizionario con i risultati completi dell'analisi.
        """
        print("\n--- Avvio del Modulo di Analisi Peeling Chain ---")
        
        analyzer = PeelingChainAnalyzer(
            btc_connector=self.btc_connector,
            electrs_connector=self.electrs_connector,
            neo4j_connector=self.neo4j_connector
        )
        
        analysis_results = analyzer.analyze(start_hash)
        
        return analysis_results
    
    def _ask_user_fallback_permission(self) -> bool:
        """
        Chiede all'utente se vuole passare all'API pubblica quando il nodo locale fallisce.
        """
        print("\nATTENZIONE: Il nodo Bitcoin locale non risponde!")
        print("Opzioni disponibili:")
        print("  1. Passa all'API pubblica (mempool.space) per continuare")
        print("  2. Interrompi l'operazione e mantieni solo il nodo locale")
        
        while True:
            try:
                choice = input("Scegli un'opzione (1 o 2): ").strip()
                if choice == "1":
                    print("Passaggio all'API pubblica confermato dall'utente.")
                    return True
                elif choice == "2":
                    print("Operazione interrotta per mantenere il nodo locale.")
                    return False
                else:
                    print("Scelta non valida. Inserisci 1 o 2.")
            except KeyboardInterrupt:
                print("\nOperazione interrotta dall'utente.")
                return False

    def _try_return_to_local_node(self):
        """
        Dopo 5 passi con l'API pubblica, prova a ritornare al nodo locale.
        """
        if self.using_public_api and self.public_api_steps >= 5:
            print("\nTentativo di ritorno al nodo locale dopo 5 passi con API pubblica...")
            
            # Testo la connessione al nodo locale
            test_result = self.btc_connector.rpc_connection
            if test_result:
                try:
                    # Provo una chiamata semplice per verificare che funzioni
                    self.btc_connector.rpc_connection.getblockchaininfo()
                    print("Nodo locale di nuovo disponibile! Ritorno al nodo locale.")
                    self.using_public_api = False
                    self.public_api_steps = 0
                    return True
                except:
                    print("Nodo locale ancora non disponibile. Continuo con API pubblica.")
                    # Resetto il contatore per riprovare tra altri 5 passi
                    self.public_api_steps = 0
                    return False
            else:
                print("Nodo locale ancora non disponibile. Continuo con API pubblica.")
                # Resetto il contatore per riprovare tra altri 5 passi
                self.public_api_steps = 0
                return False

    def store_transaction_by_hash(self, tx_hash: str) -> dict:
        """
        Flusso completo per recuperare, parsare e archiviare una transazione.
        """
        print(f"\n--- Inizio processamento transazione: {tx_hash} ---")
        
        # Provo a ritornare al nodo locale se ho fatto 5 passi con API pubblica
        self._try_return_to_local_node()
        
        # Se non sto già usando l'API pubblica, provo il nodo locale
        if not self.using_public_api:
            raw_tx = self.btc_connector.get_transaction(tx_hash)
            if not raw_tx:
                # Chiedo all'utente se vuole passare all'API pubblica
                if self._ask_user_fallback_permission():
                    self.using_public_api = True
                    self.public_api_steps = 0
                else:
                    print(f"--- Processamento interrotto per {tx_hash}: nodo locale non disponibile e utente ha rifiutato API pubblica. ---")
                    return None
        
        # Se sto usando l'API pubblica o il nodo locale ha fallito e l'utente ha accettato
        if self.using_public_api:
            raw_tx = self.public_api_connector.get_transaction(tx_hash)
            if not raw_tx:
                print(f"--- Processamento fallito: transazione {tx_hash} non trovata neanche su API pubblica. ---")
                return None
            # Incremento il contatore dei passi con API pubblica
            self.public_api_steps += 1

        # Ottengo l'altezza del blocco
        block_hash = raw_tx.get('blockhash')
        if self.using_public_api:
            # Con l'API pubblica, provo a utilizzare l'altezza del blocco se disponibile
            block_height = raw_tx.get('blockheight', 0)
            if block_height == 0 and block_hash:
                # Come fallback, chiedo l'altezza all'API pubblica se ho l'hash del blocco
                block_height = self.public_api_connector.get_block_height(block_hash)
        else:
            block_height = self.btc_connector.get_block_height(block_hash)

        if 'coinbase' in raw_tx['vin'][0]:
            print("Transazione Coinbase rilevata. Non ci sono input da processare.")
            inputs_data = []
            total_input_value = 0.0
        else:
            success, inputs_data, total_input_value = self._process_inputs(raw_tx)
            if not success:
                print(f"--- Processamento interrotto per {tx_hash}: impossibile recuperare tutti gli input. "
                      "Possibili cause:\n"
                      "  1. Il tuo nodo Bitcoin è in modalità 'pruned'.\n"
                      "  2. L'indice delle transazioni non è attivo o è corrotto (prova a riavviare con -reindex).")
                return None

        outputs_data = self.parser.parse_outputs(raw_tx)
        tx_info = self.parser.parse_transaction(raw_tx, total_input_value, block_height)

        self.neo4j_connector.store_transaction_info(tx_info, inputs_data, outputs_data)
        print(f"--- Fine processamento transazione: {tx_hash} ---")
        return raw_tx

    def trace_transaction_path(self, start_hash: str, max_steps: int = None):
        """
        Analizza una transazione e segue il flusso di denaro per un numero massimo
        di passi o fino a raggiungere un UTXO non speso.
        """
        print("\n--- Avvio Tracciamento Automatico del Percorso ---")
        current_hash = start_hash
        step = 1

        while current_hash and (max_steps is None or step <= max_steps):
            print(f"\n--- Passo {step}: Analisi di {current_hash} ---")
            raw_tx = self.store_transaction_by_hash(current_hash)

            if not raw_tx:
                print("Tracciamento interrotto: la transazione non può essere processata.")
                break

            # Se raggiungo il numero massimo di passi, mi fermo qui
            if max_steps and step == max_steps:
                print(f"\n--- Raggiunto limite massimo di {max_steps} passi. Tracciamento concluso. ---")
                break

            next_hash = None
            highest_value = -1.0
            unspent_output = None

            for i, vout in enumerate(raw_tx.get('vout', [])):
                current_value = float(vout['value'])
                if current_value > highest_value:
                    highest_value = current_value
                    
                    # Provo a ritornare al nodo locale se ho fatto 5 passi con API pubblica
                    self._try_return_to_local_node()
                    
                    # Uso la strategia appropriata in base alla modalità corrente
                    if self.using_public_api:
                        print(f"Ricerca dello spender per {current_hash[:10]}...:{i} tramite API pubblica...")
                        spending_tx = self.public_api_connector.get_spending_tx(current_hash, i)
                    else:
                        print(f"Tentativo di trovare lo spender per {current_hash[:10]}...:{i} tramite nodo locale (electrs)...")
                        spending_tx = self.electrs_connector.get_spending_tx(self.btc_connector, current_hash, i)
                        
                        if not spending_tx:
                            # Chiedo all'utente se vuole passare all'API pubblica
                            if self._ask_user_fallback_permission():
                                self.using_public_api = True
                                self.public_api_steps = 0
                                spending_tx = self.public_api_connector.get_spending_tx(current_hash, i)
                            else:
                                print("Tracciamento interrotto: electrs non disponibile e utente ha rifiutato API pubblica.")
                                return

                    if spending_tx:
                        next_hash = spending_tx
                        unspent_output = None 
                    else:
                        unspent_output = (current_hash, i, current_value)
                        next_hash = None

            current_hash = next_hash

            if current_hash:
                mode_str = "API pubblica" if self.using_public_api else "nodo locale"
                steps_info = f" (passo {self.public_api_steps}/5 con API)" if self.using_public_api else ""
                print(f"Flusso principale prosegue nella transazione: {current_hash} (usando {mode_str}{steps_info})")
                step += 1
            else:
                print("\n--- Tracciamento Concluso ---")
                if unspent_output:
                    txid, vout_index, value = unspent_output
                    print(f"Raggiunto UTXO non speso con valore più alto:")
                    print(f"  TXID: {txid}:{vout_index}")
                    print(f"  Valore: {value} BTC")
                else:
                    print("Nessun percorso da seguire o tutti gli output sono stati spesi.")

    def _process_inputs(self, raw_tx: dict) -> Tuple[bool, list, float]:
        """Metodo ausiliario che recupera gli input uno per uno."""

        parsed_inputs = []
        total_value = 0.0
        
        print(f"Recupero dei {len(raw_tx['vin'])} input della transazione...")
        for vin in raw_tx['vin']:
            source_tx_hash, source_tx_index = vin['txid'], vin['vout']

            # Uso la strategia appropriata in base alla modalità corrente
            if self.using_public_api:
                source_tx_data = self.public_api_connector.get_transaction(source_tx_hash)
            else:
                source_tx_data = self.btc_connector.get_transaction(source_tx_hash)
                if not source_tx_data:
                    # Chiedo all'utente se vuole passare all'API pubblica
                    if self._ask_user_fallback_permission():
                        self.using_public_api = True
                        self.public_api_steps = 0
                        source_tx_data = self.public_api_connector.get_transaction(source_tx_hash)
                    else:
                        print(f"Input {source_tx_hash[:10]}... non trovato su nodo locale e utente ha rifiutato API pubblica.")
                        return False, [], 0.0
            
            if source_tx_data:
                source_vout = source_tx_data['vout'][source_tx_index]
                source_vout['txid_creator'] = source_tx_hash 
                parsed_input = self.parser.parse_input(source_vout, raw_tx['txid'])
                parsed_inputs.append(parsed_input)
                total_value += float(parsed_input['value'])
            else:
                print(f"Attenzione: impossibile recuperare la transazione di origine {source_tx_hash}")
                return False, [], 0.0
        
        return True, parsed_inputs, total_value

    def delete_transaction(self, tx_hash: str):
        print(f"\n--- Richiesta eliminazione transazione: {tx_hash} ---")
        self.neo4j_connector.delete_transaction(tx_hash)

    def delete_utxo(self, utxo_id: str):
        print(f"\n--- Richiesta eliminazione UTXO: {utxo_id} ---")
        self.neo4j_connector.delete_utxo(utxo_id)
        
    def delete_transaction_and_utxos(self, tx_hash: str):
        print(f"\n--- Richiesta eliminazione completa: {tx_hash} ---")
        self.neo4j_connector.delete_transaction_and_related_utxos(tx_hash)

    def shutdown(self):
        print("\n--- Chiusura delle connessioni... ---")
        self.neo4j_connector.close()
        if self.using_public_api:
            print(f"Sessione terminata utilizzando l'API pubblica ({self.public_api_steps} passi effettuati).")
        else:
            print("Sessione terminata utilizzando il nodo locale.")
        print("Tutte le connessioni sono state chiuse. Arrivederci!")