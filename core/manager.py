from connectors.bitcoin_connector import BitcoinConnector
from connectors.neo4j_connector import Neo4jConnector
from connectors.electrs_connector import ElectrsConnector
from connectors.public_api_connector import PublicApiConnector
from core.data_parser import DataParser
from typing import Tuple

class Manager:
    def __init__(self):
        self.btc_connector = BitcoinConnector()
        self.neo4j_connector = Neo4jConnector()
        self.electrs_connector = ElectrsConnector()
        self.public_api_connector = PublicApiConnector()
        self.parser = DataParser()
        self.using_public_api = False
        self.public_api_steps = 0 # Contatore per ritornare al nodo locale

    def start_peeling_chain_analysis(self, start_hash: str) -> Dict[str, Any]:
        """
        Inizializza e avvia l'analisi di una peeling chain.
        """
        print("\n--- Avvio del Modulo di Analisi Peeling Chain ---")
        analyzer = PeelingChainAnalyzer(
            btc_connector=self.btc_connector,
            electrs_connector=self.electrs_connector, # Passa il connettore Electrs
            neo4j_connector=self.neo4j_connector
        )
        # Avvia l'analisi e restituisce i risultati
        analysis_results = analyzer.analyze(start_hash)
        print("--- Analisi Peeling Chain Completata ---")
        return analysis_results

    def _ask_user_fallback_permission(self) -> bool:
        """
        Chiede all'utente se vuole passare all'API pubblica quando il nodo locale fallisce.
        """
        source = "Electrs" if not self.btc_connector.rpc_connection else "Bitcoin Core" # Indica quale nodo ha fallito
        print(f"\nATTENZIONE: Il nodo locale ({source}) non risponde o ha fallito!")
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
            # Testa la connessione al nodo Bitcoin Core
            if self.btc_connector.rpc_connection:
                try:
                    # Prova una chiamata semplice per verificare che funzioni
                    self.btc_connector.rpc_connection.getblockchaininfo()
                    print("Nodo Bitcoin Core locale di nuovo disponibile! Ritorno alla modalità locale.")
                    self.using_public_api = False
                    self.public_api_steps = 0 # Resetta il contatore
                    return True # Successo nel tornare a locale
                except Exception as e:
                    print(f"Nodo Bitcoin Core locale ancora non pienamente operativo ({e}). Continuo con API pubblica.")
                    # Reset il contatore per riprovare tra altri 5 passi
                    self.public_api_steps = 0
                    return False # Fallito, resta su API
            else:
                print("Nodo Bitcoin Core locale ancora non disponibile. Continuo con API pubblica.")
                # Reset il contatore per riprovare tra altri 5 passi
                self.public_api_steps = 0
                return False # Fallito, resta su API
        return False # Non è il momento di provare o non eravamo in API

    def store_transaction_by_hash(self, tx_hash: str) -> dict:
        """
        Flusso completo per recuperare, parsare e archiviare una transazione,
        con fallback all'API pubblica e tentativi di ritorno a locale.
        """
        print(f"\n--- Inizio processamento transazione: {tx_hash} ---")
        raw_tx = None
        
        # Prova a ritornare al nodo locale PRIMA di iniziare
        self._try_return_to_local_node()

        # 1. Prova il nodo locale (se non siamo già forzati su API)
        if not self.using_public_api:
            raw_tx = self.btc_connector.get_transaction(tx_hash)
            if not raw_tx:
                if self._ask_user_fallback_permission():
                    self.using_public_api = True
                    print("Passaggio temporaneo all'API pubblica...")
                    # Non resettare subito public_api_steps qui, fallo solo quando usi l'API
                else:
                    print(f"--- Processamento interrotto per {tx_hash}: nodo locale non disponibile e fallback rifiutato. ---")
                    return None

        # 2. Se serve l'API pubblica
        if self.using_public_api and raw_tx is None:
             print(f"Tentativo di recupero tramite API pubblica per {tx_hash}...")
             raw_tx = self.public_api_connector.get_transaction(tx_hash)
             if not raw_tx:
                 print(f"--- Processamento fallito: transazione {tx_hash} non trovata neanche su API pubblica. ---")
                 return None
             self.public_api_steps += 1 # Incrementa solo se l'API è stata USATA con successo

        # --- Da qui in poi, raw_tx dovrebbe esistere ---

        block_hash = raw_tx.get('blockhash')
        block_height = 0
        if self.using_public_api:
             if block_hash:
                 block_height = self.public_api_connector.get_block_height(block_hash)
             elif raw_tx.get('blockheight'):
                 block_height = raw_tx.get('blockheight')
        else:
            if block_hash:
                 block_height = self.btc_connector.get_block_height(block_hash)

        is_coinbase = False
        if raw_tx.get('vin') and isinstance(raw_tx['vin'][0], dict):
             if 'coinbase' in raw_tx['vin'][0] or raw_tx['vin'][0].get("is_coinbase") == True:
                 is_coinbase = True

        if is_coinbase:
            print("Transazione Coinbase rilevata.")
            inputs_data = []
            total_input_value = 0.0
        else:
            # Passiamo lo stato API a _process_inputs implicitamente tramite self.using_public_api
            success, inputs_data, total_input_value = self._process_inputs(raw_tx)
            if not success:
                print(f"--- Processamento interrotto per {tx_hash}: impossibile recuperare tutti gli input.")
                return None

        outputs_data = self.parser.parse_outputs(raw_tx)
        tx_info = self.parser.parse_transaction(raw_tx, total_input_value, block_height)
        tx_info['coinbase'] = is_coinbase

        self.neo4j_connector.store_transaction_info(tx_info, inputs_data, outputs_data)
        mode_used = "API Pubblica" if self.using_public_api else "Nodo Locale"
        api_step_info = f" (Passo API: {self.public_api_steps})" if self.using_public_api else ""
        print(f"--- Fine processamento transazione: {tx_hash} (utilizzando {mode_used}{api_step_info}) ---")
        return raw_tx

    def trace_transaction_path(self, start_hash: str, max_steps: int = None):
        """
        Analizza una transazione e segue il flusso di denaro, con fallback API
        per Electrs e tentativi di ritorno a locale.
        """
        print("\n--- Avvio Tracciamento Automatico del Percorso ---")
        current_hash = start_hash
        step = 1

        while current_hash and (max_steps is None or step <= max_steps):
            
            # Tenta ritorno a locale all'inizio di ogni passo del tracciamento
            self._try_return_to_local_node()
            
            mode_str = "API pubblica" if self.using_public_api else "nodo locale"
            api_step_info = f" (Passo API: {self.public_api_steps})" if self.using_public_api else ""
            print(f"\n--- Passo {step}: Analisi di {current_hash} (usando {mode_str}{api_step_info}) ---")
            
            # store_transaction_by_hash gestisce già il fallback per il recupero TX
            raw_tx = self.store_transaction_by_hash(current_hash)

            if not raw_tx:
                print("Tracciamento interrotto: la transazione non può essere processata.")
                break

            if max_steps and step == max_steps:
                print(f"\n--- Raggiunto limite massimo di {max_steps} passi. Tracciamento concluso. ---")
                break

            next_hash = None
            highest_value = -1.0
            unspent_output = None
            spending_tx = None # Per memorizzare il risultato della ricerca spender

            # Trova l'output con il valore più alto e cerca chi lo spende
            for i, vout in enumerate(raw_tx.get('vout', [])):
                current_value = float(vout['value'])
                if current_value > highest_value:
                    highest_value = current_value
                    
                    # Cerca la transazione che spende questo output
                    spending_tx = None # Resetta per questo output
                    if self.using_public_api:
                        # Se siamo GIA' in modalità API, usala direttamente
                        print(f"Ricerca spender per {current_hash[:10]}...:{i} tramite API pubblica...")
                        spending_tx = self.public_api_connector.get_spending_tx(current_hash, i)
                        # Incrementa contatore API se la chiamata ha successo (anche se non trova spender)
                        if spending_tx is not None: # Verifica se la chiamata è andata a buon fine
                             self.public_api_steps += 1
                    else:
                        # Altrimenti, prova prima Electrs locale
                        print(f"Tentativo di trovare lo spender per {current_hash[:10]}...:{i} tramite Electrs locale...")
                        spending_tx = self.electrs_connector.get_spending_tx(self.btc_connector, current_hash, i)
                        
                        # Se Electrs fallisce E NON siamo già in modalità API
                        if spending_tx is None and not self.using_public_api:
                             # Eseguiamo il controllo in modo più robusto: get_spending_tx potrebbe tornare None
                             # anche se la connessione funziona ma l'UTXO non è speso. Dobbiamo distinguere.
                             # Per ora, assumiamo che None significhi fallimento O non speso.
                             # Se vogliamo essere più precisi, ElectrsConnector dovrebbe sollevare eccezioni specifiche.
                             
                             print(f"Electrs non ha trovato lo spender (o non è disponibile).")
                             if self._ask_user_fallback_permission():
                                 self.using_public_api = True # Passa a modalità API
                                 print(f"Tentativo con API pubblica per {current_hash[:10]}...:{i}...")
                                 spending_tx = self.public_api_connector.get_spending_tx(current_hash, i)
                                 # Incrementa contatore se chiamata API ha successo
                                 if spending_tx is not None:
                                      self.public_api_steps += 1
                             else:
                                 print("Tracciamento interrotto: Electrs non disponibile e fallback rifiutato.")
                                 return # Interrompe tutto il tracciamento

                    # Aggiorna next_hash e unspent_output in base al risultato
                    if spending_tx:
                        next_hash = spending_tx
                        unspent_output = None
                    else:
                        # Se NESSUNA fonte ha trovato uno spender per questo output (il più alto finora)
                        unspent_output = (current_hash, i, current_value)
                        next_hash = None # Assicura che non si vada avanti se l'output maggiore non è speso

            current_hash = next_hash # Aggiorna l'hash per il prossimo ciclo

            if current_hash:
                print(f"Flusso principale prosegue nella transazione: {current_hash}")
                step += 1
            else:
                print("\n--- Tracciamento Concluso ---")
                if unspent_output:
                    txid, vout_index, value = unspent_output
                    print(f"Raggiunto UTXO non speso con valore più alto:")
                    print(f"  TXID: {txid}:{vout_index}")
                    print(f"  Valore: {value} BTC")
                else:
                    # Questo caso potrebbe verificarsi se l'ultimo TX analizzato non aveva output
                    # o se c'è stato un errore imprevisto.
                    print("Nessun percorso valido da seguire trovato o l'ultimo output non era spendibile.")
                break # Esce dal ciclo while


    def _process_inputs(self, raw_tx: dict) -> Tuple[bool, list, float]:
        """Metodo ausiliario aggiornato per gestire il fallback e incrementare il contatore API."""
        parsed_inputs = []
        total_value = 0.0
        
        vin_list = raw_tx.get('vin', [])
        if not vin_list: return True, [], 0.0
        
        print(f"Recupero dei {len(vin_list)} input della transazione...")

        for vin in vin_list:
             if 'coinbase' in vin or vin.get("is_coinbase") == True:
                 continue
                 
             source_tx_hash, source_tx_index = vin.get('txid'), vin.get('vout')
             if not source_tx_hash or source_tx_index is None:
                 print(f"Attenzione: dati input mancanti o non validi: {vin}")
                 continue

             source_tx_data = None
             used_api_for_this_input = False # Flag locale

             # 1. Prova la fonte dati corrente
             if self.using_public_api:
                 source_tx_data = self.public_api_connector.get_transaction(source_tx_hash)
                 used_api_for_this_input = True # Abbiamo provato l'API
             else:
                 source_tx_data = self.btc_connector.get_transaction(source_tx_hash)

             # 2. Se fallisce e non eravamo già in API, tenta il fallback
             if not source_tx_data and not self.using_public_api:
                 print(f"Input {source_tx_hash[:10]}... non trovato su nodo locale. Tentativo con API pubblica...")
                 if self._ask_user_fallback_permission():
                      self.using_public_api = True
                      source_tx_data = self.public_api_connector.get_transaction(source_tx_hash)
                      used_api_for_this_input = True # Abbiamo usato l'API
                 else:
                     print(f"Recupero input {source_tx_hash[:10]}... fallito: fallback rifiutato.")
                     return False, [], 0.0

             # 3. Se ancora non abbiamo i dati
             if not source_tx_data:
                 print(f"Attenzione: impossibile recuperare transazione origine {source_tx_hash}.")
                 return False, [], 0.0
                 
             # 4. Incrementa contatore API se abbiamo usato l'API per QUESTO input
             if used_api_for_this_input:
                  self.public_api_steps += 1

             # Verifica indice vout
             if source_tx_index >= len(source_tx_data.get('vout',[])):
                  print(f"Attenzione: indice vout {source_tx_index} non valido per TX origine {source_tx_hash}")
                  return False, [], 0.0
                  
             source_vout = source_tx_data['vout'][source_tx_index]
             source_vout['txid_creator'] = source_tx_hash
             parsed_input = self.parser.parse_input(source_vout, raw_tx['txid'])
             parsed_inputs.append(parsed_input)
             total_value += float(parsed_input['value'])
        
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
            # Messaggio più specifico
            print(f"Sessione terminata. L'API pubblica è stata utilizzata per {self.public_api_steps} operazioni.")
        else:
            print("Sessione terminata utilizzando esclusivamente il nodo locale.")
        print("Tutte le connessioni sono state chiuse. Arrivederci!")