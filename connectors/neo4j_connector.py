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
        """
        Per ogni input, trova l'UTXO esistente, lo aggiorna a 'speso'
        e aggiunge il spending_hash, poi crea la relazione :INPUT.
        """
        for utxo in inputs:
            utxo_id = f"{utxo['transaction_hash']}:{utxo['index']}"
            spending_hash = utxo['spending_transaction_hash']
            
            # Esegue la query per aggiornare l'UTXO esistente, passando TUTTI i parametri
            tx.run(query.UPDATE_SPENT_UTXO, utxo_id=utxo_id, spending_tx_hash=spending_hash)
            
            # Crea la relazione di input verso la nuova transazione
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
                   # Passiamo i nuovi parametri alla query
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

    # --- METODI DI LETTURA PER ANALISI ---
    def run_read_query(self, cypher_query: str, parameters: dict = None):
        """
        Esegue una query di lettura e restituisce i risultati.
        
        Args:
            cypher_query: La query Cypher da eseguire
            parameters: Parametri per la query
            
        Returns:
            Lista di record/risultati
        """
        if not self.driver:
            return []
        
        try:
            with self.driver.session() as session:
                result = session.run(cypher_query, parameters or {})
                return [record.data() for record in result]
        except Exception as e:
            print(f"Errore durante l'esecuzione della query di lettura: {e}")
            return []

    def get_transaction_details(self, tx_hash: str):
        """Recupera i dettagli di una transazione."""
        return self.run_read_query(query.GET_TRANSACTION_DETAILS, {"tx_hash": tx_hash})

    def get_transaction_outputs(self, tx_hash: str):
        """Recupera tutti gli output di una transazione."""
        return self.run_read_query(query.GET_TRANSACTION_OUTPUTS, {"tx_hash": tx_hash})

    def get_transaction_inputs(self, tx_hash: str):
        """Recupera tutti gli input di una transazione."""
        return self.run_read_query(query.GET_TRANSACTION_INPUTS, {"tx_hash": tx_hash})

    def find_spending_transaction(self, utxo_id: str):
        """Trova la transazione che spende un UTXO specifico."""
        return self.run_read_query(query.FIND_SPENDING_TRANSACTION, {"utxo_id": utxo_id})

    def get_full_transaction_data(self, tx_hash: str):
        """Recupera tutti i dati di una transazione (input, output, dettagli)."""
        return self.run_read_query(query.GET_FULL_TRANSACTION_DATA, {"tx_hash": tx_hash})

    def check_transaction_exists(self, tx_hash: str):
        """Verifica se una transazione esiste nel database."""
        return self.run_read_query(query.CHECK_TRANSACTION_EXISTS, {"tx_hash": tx_hash})