from connectors.bitcoin_connector import BitcoinConnector
from connectors.neo4j_connector import Neo4jConnector
from core.data_parser import DataParser
from typing import Tuple

class Manager:
    def __init__(self):
        self.btc_connector = BitcoinConnector()
        self.neo4j_connector = Neo4jConnector()
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

    def shutdown(self):
        print("\n--- Chiusura delle connessioni... ---")
        self.neo4j_connector.close()
        print("Tutte le connessioni sono state chiuse. Arrivederci!")