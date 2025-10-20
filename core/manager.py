from connectors.bitcoin_connector import BitcoinConnector
from connectors.neo4j_connector import Neo4jConnector
from connectors.electrs_connector import ElectrsConnector # Importato
from core.data_parser import DataParser
from typing import Tuple

class Manager:
    def __init__(self):
        self.btc_connector = BitcoinConnector()
        self.neo4j_connector = Neo4jConnector()
        self.electrs_connector = ElectrsConnector() 
        self.parser = DataParser()

    def store_transaction_by_hash(self, tx_hash: str) -> dict:
        print(f"\n--- Inizio processamento transazione: {tx_hash} ---")
        raw_tx = self.btc_connector.get_transaction(tx_hash)
        if not raw_tx:
            print(f"--- Processamento fallito: transazione {tx_hash} non trovata. ---")
            return None

        block_hash = raw_tx.get('blockhash')
        block_height = self.btc_connector.get_block_height(block_hash)

        if 'coinbase' in raw_tx['vin'][0]:
            print("Transazione Coinbase rilevata. Non ci sono input da processare.")
            inputs_data = []
            total_input_value = 0.0
        else:
            success, inputs_data, total_input_value = self._process_inputs(raw_tx)
            if not success:
                print(f"--- Processamento interrotto per {tx_hash}: impossibile recuperare tutti gli input.")
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

            if max_steps and step == max_steps:
                print(f"\n--- Raggiunto limite massimo di {max_steps} passi. Tracciamento concluso. ---")
                break

            next_hash = None
            highest_value = -1.0
            unspent_output = None

            # Trova l'output con il valore più alto
            for i, vout in enumerate(raw_tx.get('vout', [])):
                current_value = float(vout['value'])
                if current_value > highest_value:
                    highest_value = current_value
                    
                    # Cerca la transazione che spende questo output
                    print(f"Tentativo di trovare lo spender per {current_hash[:10]}...:{i} tramite Electrs...")
                    spending_tx = self.electrs_connector.get_spending_tx(
                        self.btc_connector, current_hash, i
                    )
                    
                    if spending_tx:
                        next_hash = spending_tx
                        unspent_output = None # Resetta se troviamo uno spender
                    else:
                        # Se non c'è uno spender, questo è un potenziale UTXO finale
                        unspent_output = (current_hash, i, current_value)
                        next_hash = None

            current_hash = next_hash

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
                    print("Nessun percorso da seguire o tutti gli output sono stati spesi.")


    def _process_inputs(self, raw_tx: dict) -> Tuple[bool, list, float]:
        parsed_inputs = []
        total_value = 0.0
        
        print(f"Recupero dei {len(raw_tx['vin'])} input della transazione...")
        for vin in raw_tx['vin']:
            source_tx_hash, source_tx_index = vin['txid'], vin['vout']
            source_tx_data = self.btc_connector.get_transaction(source_tx_hash)
            
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
        print("Tutte le connessioni sono state chiuse. Arrivederci!")