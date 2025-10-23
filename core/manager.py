from connectors.bitcoin_connector import BitcoinConnector
from connectors.neo4j_connector import Neo4jConnector
from connectors.electrs_connector import ElectrsConnector
from connectors.public_api_connector import PublicApiConnector # Importato
from core.data_parser import DataParser
from typing import Tuple

class Manager:
    def __init__(self):
        self.btc_connector = BitcoinConnector()
        self.neo4j_connector = Neo4jConnector()
        self.electrs_connector = ElectrsConnector()
        self.public_api_connector = PublicApiConnector() 
        self.parser = DataParser()
        self.using_public_api = False # Flag per tracciare la modalità corrente

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

    def store_transaction_by_hash(self, tx_hash: str) -> dict:
        """
        Flusso completo per recuperare, parsare e archiviare una transazione,
        con fallback all'API pubblica.
        """
        print(f"\n--- Inizio processamento transazione: {tx_hash} ---")
        raw_tx = None
        
        # 1. Prova il nodo locale
        if not self.using_public_api:
            raw_tx = self.btc_connector.get_transaction(tx_hash)
            if not raw_tx:
                # Chiedi permesso per il fallback
                if self._ask_user_fallback_permission():
                    self.using_public_api = True
                    print("Passaggio temporaneo all'API pubblica...")
                else:
                    print(f"--- Processamento interrotto per {tx_hash}: nodo locale non disponibile e fallback rifiutato. ---")
                    return None # Interrompi se l'utente rifiuta

        # 2. Se il nodo locale ha fallito (e l'utente ha accettato) o se eravamo GIA' in modalità API
        if self.using_public_api and raw_tx is None:
             print(f"Tentativo di recupero tramite API pubblica per {tx_hash}...")
             raw_tx = self.public_api_connector.get_transaction(tx_hash)
             if not raw_tx:
                 print(f"--- Processamento fallito: transazione {tx_hash} non trovata neanche su API pubblica. ---")
                 # Considera se tornare automaticamente al nodo locale qui o gestire diversamente
                 # self.using_public_api = False # Potrebbe essere un'opzione
                 return None

        # --- Da qui in poi, assumiamo di avere raw_tx (o da locale o da API) ---

        # Ottieni altezza blocco in base alla modalità
        block_hash = raw_tx.get('blockhash')
        block_height = 0
        if self.using_public_api:
            # Se siamo in modalità API, chiediamo l'altezza all'API
             if block_hash: # Chiedi solo se c'è un block hash
                 block_height = self.public_api_connector.get_block_height(block_hash)
             elif raw_tx.get('blockheight'): # Usa l'altezza se già presente nella risposta API
                 block_height = raw_tx.get('blockheight')
        else:
            # Altrimenti chiedi al nodo locale
            if block_hash:
                 block_height = self.btc_connector.get_block_height(block_hash)
                 
        # Gestione input coinbase (leggermente diversa tra RPC e API mempool)
        is_coinbase = False
        if raw_tx.get('vin') and isinstance(raw_tx['vin'][0], dict):
             if 'coinbase' in raw_tx['vin'][0] or raw_tx['vin'][0].get("is_coinbase") == True:
                 is_coinbase = True

        if is_coinbase:
            print("Transazione Coinbase rilevata. Non ci sono input standard da processare.")
            inputs_data = []
            total_input_value = 0.0
        else:
            # _process_inputs dovrà anche gestire il fallback
            success, inputs_data, total_input_value = self._process_inputs(raw_tx)
            if not success:
                # Messaggio di errore aggiornato per riflettere entrambe le fonti
                print(f"--- Processamento interrotto per {tx_hash}: impossibile recuperare tutti gli input (né da nodo locale né da API pubblica).")
                return None

        outputs_data = self.parser.parse_outputs(raw_tx)
        # Passiamo is_coinbase calcolato qui
        tx_info = self.parser.parse_transaction(raw_tx, total_input_value, block_height)
        # Sovrascriviamo il valore coinbase nel dizionario tx_info se necessario
        tx_info['coinbase'] = is_coinbase 

        self.neo4j_connector.store_transaction_info(tx_info, inputs_data, outputs_data)
        mode_used = "API Pubblica" if self.using_public_api else "Nodo Locale"
        print(f"--- Fine processamento transazione: {tx_hash} (utilizzando {mode_used}) ---")
        return raw_tx

    def _process_inputs(self, raw_tx: dict) -> Tuple[bool, list, float]:
        """Metodo ausiliario aggiornato per gestire il fallback anche nel recupero degli input."""
        parsed_inputs = []
        total_value = 0.0
        
        print(f"Recupero dei {len(raw_tx.get('vin', []))} input della transazione...")
        
        vin_list = raw_tx.get('vin', [])
        if not vin_list: return True, [], 0.0 # Nessun input (o errore formato)
        
        for vin in vin_list:
             # Salta se è un input coinbase formattato dal parser API o RPC
             if 'coinbase' in vin or vin.get("is_coinbase") == True:
                 continue
                 
             source_tx_hash, source_tx_index = vin.get('txid'), vin.get('vout')

             # Controlli di validità di base
             if not source_tx_hash or source_tx_index is None:
                 print(f"Attenzione: dati input mancanti o non validi: {vin}")
                 continue # Salta questo input problematico

             source_tx_data = None
             # Prova prima la fonte dati corrente (locale o API)
             if self.using_public_api:
                 source_tx_data = self.public_api_connector.get_transaction(source_tx_hash)
             else:
                 source_tx_data = self.btc_connector.get_transaction(source_tx_hash)

             # Se fallisce, tenta il fallback (se non eravamo già in API)
             if not source_tx_data and not self.using_public_api:
                 print(f"Input {source_tx_hash[:10]}... non trovato su nodo locale. Tentativo con API pubblica...")
                 if self._ask_user_fallback_permission(): # Chiedi permesso ANCHE qui
                      self.using_public_api = True # Passa alla modalità API per il resto
                      source_tx_data = self.public_api_connector.get_transaction(source_tx_hash)
                 else:
                     print(f"Recupero input {source_tx_hash[:10]}... fallito: fallback rifiutato.")
                     return False, [], 0.0 # Interrompi se l'utente rifiuta qui
            
             # Se ancora non abbiamo i dati dopo eventuale fallback
             if not source_tx_data:
                 print(f"Attenzione: impossibile recuperare la transazione di origine {source_tx_hash} (né da nodo locale né da API).")
                 return False, [], 0.0 # Fallimento critico
            
             # Verifica che l'indice vout sia valido
             if source_tx_index >= len(source_tx_data.get('vout',[])):
                  print(f"Attenzione: indice vout {source_tx_index} non valido per la transazione di origine {source_tx_hash}")
                  return False, [], 0.0 # Fallimento critico
                  
             source_vout = source_tx_data['vout'][source_tx_index]
             source_vout['txid_creator'] = source_tx_hash # Aggiungi l'hash per il parser
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
        # Aggiungi un messaggio sullo stato finale (se si è usata l'API)
        if self.using_public_api:
             print("Sessione terminata utilizzando (almeno parzialmente) l'API pubblica.")
        else:
             print("Sessione terminata utilizzando solo il nodo locale.")
        print("Tutte le connessioni sono state chiuse. Arrivederci!")