import config
from neo4j import GraphDatabase
from core import query

class Neo4jConnector:
    def __init__(self):
        try:
            self.driver = GraphDatabase.driver(config.NEO4J_URI, auth=config.NEO4J_AUTH)
            self.driver.verify_connectivity()
            print("Connessione a Neo4j stabilita con successo.")
        except Exception as e:
            print(f"Errore durante la connessione a Neo4j: {e}")
            self.driver = None

    def close(self):
        if self.driver:
            self.driver.close()
            print("Connessione a Neo4j chiusa.")

    def store_transaction_info(self, tx_info: dict, inputs: list, outputs: list):
        if not self.driver: return
        with self.driver.session() as session:
            try:
                print("Inizio memorizzazione su Neo4j:")
                session.execute_write(self._create_tx_node, tx_info)
                session.execute_write(self._create_input_utxos, inputs)
                session.execute_write(self._create_output_utxos, outputs)
                print("Memorizzazione completata.")
            except Exception as e:
                print(f"Errore durante la memorizzazione: {e}")

    @staticmethod
    def _create_tx_node(tx, tx_info: dict):
        tx.run(query.CREATE_TX_NODE, **tx_info)
        print(f"--> Creato nodo TX: {tx_info['TXID']}")

    @staticmethod
    def _create_input_utxos(tx, inputs: list):
        for utxo in inputs:
            utxo_id = f"{utxo['transaction_hash']}:{utxo['index']}"
            spending_hash = utxo['spending_transaction_hash']
            tx.run(query.UPDATE_SPENT_UTXO, utxo_id=utxo_id, spending_tx_hash=spending_hash)
            tx.run(query.CREATE_INPUT_RELATION, utxo_id=utxo_id, tx_hash=spending_hash)
            print(f"--> Aggiornato e collegato UTXO di input: {utxo_id}")

    @staticmethod
    def _create_output_utxos(tx, outputs: list):
        for utxo in outputs:
            utxo_id = f"{utxo['transaction_hash']}:{utxo['index']}"
            tx.run(query.CREATE_OUTPUT_UTXO_NODE,
                   utxo_id=utxo_id,
                   wallet_address=utxo['wallet_address'],
                   value=utxo['value'],
                   is_spent=utxo['is_spent'],
                   time=utxo['time'],
                   block_id=utxo['block_id'])
            tx.run(query.CREATE_OUTPUT_RELATION,
                   tx_hash=utxo['transaction_hash'],
                   utxo_id=utxo_id)
            print(f"--> Creato/collegato UTXO di output: {utxo_id}")