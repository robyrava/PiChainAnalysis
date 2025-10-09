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

    # --- METODI DI SCRITTURA ---
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

    # --- METODI DI CANCELLAZIONE ---
    def delete_transaction(self, tx_hash: str):
        if not self.driver: return
        with self.driver.session() as session:
            try:
                session.execute_write(self._delete_transaction_node, tx_hash)
                print(f"Transazione '{tx_hash}' eliminata con successo.")
            except Exception as e:
                print(f"Errore durante l'eliminazione della transazione: {e}")

    @staticmethod
    def _delete_transaction_node(tx, tx_hash: str):
        tx.run(query.DELETE_TRANSACTION, hash=tx_hash)

    def delete_utxo(self, utxo_id: str):
        if not self.driver: return
        with self.driver.session() as session:
            try:
                session.execute_write(self._delete_utxo_node, utxo_id)
                print(f"UTXO '{utxo_id}' eliminato con successo.")
            except Exception as e:
                print(f"Errore durante l'eliminazione dell'UTXO: {e}")

    @staticmethod
    def _delete_utxo_node(tx, utxo_id: str):
        tx.run(query.DELETE_UTXO, utxo_id=utxo_id)

    def delete_transaction_and_related_utxos(self, tx_hash: str):
        if not self.driver: return
        with self.driver.session() as session:
            try:
                session.execute_write(self._delete_full_transaction, tx_hash)
                print(f"Transazione '{tx_hash}' e UTXO associati eliminati con successo.")
            except Exception as e:
                print(f"Errore durante l'eliminazione completa della transazione: {e}")

    @staticmethod
    def _delete_full_transaction(tx, tx_hash: str):
        tx.run(query.DELETE_TRANSACTION_AND_UTXOS, hash=tx_hash)