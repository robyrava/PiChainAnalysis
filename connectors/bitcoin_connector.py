import config
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

class BitcoinConnector:
    """
    Gestisce la connessione e le chiamate RPC a un nodo Bitcoin Core.
    """
    def __init__(self):
        """
        Inizializza la connessione al nodo Bitcoin utilizzando le credenziali
        definite nel file di configurazione.
        """
        try:
            self.rpc_connection = AuthServiceProxy(config.RPC_URL)
            # Testa la connessione per assicurarti che sia funzionante
            self.rpc_connection.getblockchaininfo()
            print("Connessione al nodo Bitcoin Core stabilita con successo.")
        except JSONRPCException as e:
            print(f"Errore di connessione RPC: {e.error['message']}")
            self.rpc_connection = None
        except Exception as e:
            print(f"Errore durante la connessione al nodo Bitcoin: {e}")
            print("Controlla che il nodo sia in esecuzione e che le credenziali nel file .env siano corrette.")
            self.rpc_connection = None

    def get_transaction(self, txid: str) -> dict:
        """
        Recupera le informazioni dettagliate di una transazione dato il suo hash (txid).

        Args:
            txid: L'hash della transazione da recuperare.

        Returns:
            Un dizionario con i dettagli della transazione se trovata, altrimenti None.
        """
        if not self.rpc_connection:
            print("Connessione al nodo non disponibile.")
            return None

        try:
            # Il parametro '1' (o True) corrisponde a verbose=True per ottenere l'output in formato JSON
            transaction_data = self.rpc_connection.getrawtransaction(txid, 1)
            return transaction_data
        except JSONRPCException as e:
            print(f"Errore durante il recupero della transazione '{txid}': {e.error['message']}")
            return None
        except Exception as e:
            print(f"Si è verificato un errore imprevisto: {e}")
            return None
        
    def get_block_height(self, block_hash: str) -> int:
            """Recupera l'altezza di un blocco dato il suo hash."""
            if not self.rpc_connection or not block_hash or block_hash == 'Mempool':
                return 0
            try:
                block_header = self.rpc_connection.getblockheader(block_hash)
                return block_header.get('height', 0)
            except JSONRPCException:
                # Questo può succedere per transazioni in mempool
                return 0
            except Exception as e:
                print(f"Errore imprevisto in get_block_height: {e}")
                return 0

        

      
