import socket
import ssl
import json
import config
import hashlib
from .bitcoin_connector import BitcoinConnector

def _calculate_scripthash(script_hex: str) -> str:
    """Calcola lo scripthash di Electrum partendo da uno script esadecimale."""
    script_bytes = bytes.fromhex(script_hex)
    sha256_hash = hashlib.sha256(script_bytes).digest()
    return sha256_hash[::-1].hex()


class ElectrsConnector:
    """
    Gestisce la connessione sicura al server Electrs usando socket standard,
    implementando le best practices del protocollo Electrum.
    """
    def __init__(self):
        self.host = config.ELECTRS_HOST
        self.port = int(config.ELECTRS_PORT)
        self.timeout = config.ELECTRS_TIMEOUT 
        self.request_id = 1
        print(f"Connettore Electrs configurato per {self.host}:{self.port}")

    def _get_next_id(self):
        """Genera un ID unico per ogni richiesta RPC."""
        current_id = self.request_id
        self.request_id += 1
        return current_id

    def _send_rpc_request(self, method: str, params: list, connection=None):
        """
        Invia una singola richiesta JSON-RPC. Se riceve una connessione,
        la utilizza, altrimenti ne crea una nuova.
        """
        if connection:
            # Uso una connessione esistente
            return self._send_request_on_connection(connection, method, params)
        else:
            # Creo una nuova connessione per questa singola richiesta
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

            try:
                with socket.create_connection((self.host, self.port), self.timeout) as sock:
                    with context.wrap_socket(sock, server_hostname=self.host) as ssock:
                        return self._send_request_on_connection(ssock, method, params)
            except Exception as e:
                print(f"Errore durante la richiesta a Electrs ({method}): {e}")
                return None

    def _send_request_on_connection(self, connection, method: str, params: list):
        """Invia una richiesta su una connessione esistente."""
        try:
            request = {
                "id": self._get_next_id(),
                "method": method,
                "params": params
            }
            connection.sendall(json.dumps(request).encode() + b'\n')

            # Leggo la risposta
            response_data = b""
            while True:
                part = connection.recv(1024)
                if not part:
                    break
                response_data += part
                if b'\n' in part:
                    break
            
            if not response_data:
                raise ConnectionError("Nessuna risposta ricevuta dal server Electrs.")

            response = json.loads(response_data.decode())
            
            if 'error' in response:
                raise Exception(f"Errore dal server Electrs: {response['error']}")
            
            return response.get('result')

        except Exception as e:
            print(f"Errore durante l'invio della richiesta: {e}")
            return None

    def _scripthash_query(self, scripthash: str):
        """
        Implementa il flusso di interrogazione di uno scripthash:
        1. Si iscrive per ricevere notifiche
        2. Recupera la cronologia completa
        3. Si disiscrive per liberare risorse
        """
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        try:
            with socket.create_connection((self.host, self.port), self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=self.host) as ssock:
                    
                    # 1. Mi iscrivo allo scripthash
                    #print(f"Sottoscrizione a scripthash: {scripthash[:16]}...")
                    subscribe_result = self._send_request_on_connection(
                        ssock, "blockchain.scripthash.subscribe", [scripthash]
                    )
                    
                    if subscribe_result is None:
                        print(f"Fallita sottoscrizione per scripthash {scripthash[:16]}...")
                        return None
                    
                    #print(f"Sottoscrizione confermata per scripthash {scripthash[:16]}...")
                    
                    # 2. Ottengo la cronologia 
                    #print(f"Recupero cronologia per scripthash sottoscritto...")
                    history = self._send_request_on_connection(
                        ssock, "blockchain.scripthash.get_history", [scripthash]
                    )
                    
                    # 3. Mi disiscrivo per liberare risorse sul server
                    #print(f"Rimozione sottoscrizione...")
                    self._send_request_on_connection(
                        ssock, "blockchain.scripthash.unsubscribe", [scripthash]
                    )
                    
                    return history

        except Exception as e:
            print(f"Errore durante la query scripthash: {e}")
            return None

    def get_spending_tx(self, btc_connector: BitcoinConnector, txid: str, vout_index: int):
        """
        Trova la transazione che spende un UTXO utilizzando il metodo
        raccomandato dal protocollo Electrum.
        """
        try:
            #print(f"Ricerca spending transaction per {txid[:10]}...:{vout_index}")
            
            # Ottengo la transazione originale per estrarre lo script
            raw_tx = btc_connector.get_transaction(txid)
            if not raw_tx or vout_index >= len(raw_tx['vout']):
                print(f"Transazione {txid[:10]}... non trovata o indice output non valido")
                return None

            # Calcolo lo scripthash dallo scriptPubKey
            script_pub_key_hex = raw_tx['vout'][vout_index]['scriptPubKey']['hex']
            scripthash = _calculate_scripthash(script_pub_key_hex)
            #print(f"Calcolato scripthash: {scripthash[:16]}...")

            # Ottengo la cronologia
            history = self._scripthash_query(scripthash)
            if not history:
                print(f"Impossibile ottenere cronologia per scripthash {scripthash[:16]}...")
                return None

            #print(f"Trovate {len(history)} transazioni nella cronologia")

            # Cerco nelle transazioni quella che spende il mio UTXO
            for i, tx_item in enumerate(history):
                if tx_item['tx_hash'] == txid:
                    #print(f"Trovata transazione originale nella cronologia (posizione {i+1}/{len(history)})")
                    continue

                print(f"Controllo transazione {i+1}/{len(history)}: {tx_item['tx_hash'][:10]}...")
                
                # Ottengo i dettagli della transazione sospetta
                spending_tx_raw = self._send_rpc_request(
                    "blockchain.transaction.get", 
                    [tx_item['tx_hash'], True]
                )
                
                if not spending_tx_raw:
                    print(f"Impossibile ottenere dettagli per {tx_item['tx_hash'][:10]}...")
                    continue

                # Controllo se questa transazione spende il mio UTXO
                for j, vin in enumerate(spending_tx_raw.get('vin', [])):
                    if vin.get('txid') == txid and vin.get('vout') == vout_index:
                        print(f"Trovato spender! TX: {tx_item['tx_hash'][:10]}..., input #{j}")
                        return tx_item['tx_hash']

            print(f"UTXO {txid[:10]}...:{vout_index} non è stato speso (UTXO non speso)")
            return None
            
        except Exception as e:
            print(f"Errore imprevisto in get_spending_tx: {e}")
            return None

    def batch_get_spending_txs(self, btc_connector: BitcoinConnector, utxo_list: list):
        """
        Gestisce in modo ottimizzato il controllo dello stato di spesa di multipli UTXO
        in una singola connessione, riducendo l'overhead di connessione.
        
        Args:
            utxo_list: Lista di tuple (txid, vout_index)
            
        Returns:
            Dict con chiave (txid, vout_index) e valore spending_txid o None
        """
        if not utxo_list:
            return {}
            
        #print(f"Avvio batch query per {len(utxo_list)} UTXO...")
        results = {}
        
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        try:
            with socket.create_connection((self.host, self.port), self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=self.host) as ssock:
                    
                    for i, (txid, vout_index) in enumerate(utxo_list):
                        print(f"Processando UTXO {i+1}/{len(utxo_list)}: {txid[:10]}...:{vout_index}")
                        
                        try:
                            # Ottengo la transazione e calcolo lo scripthash
                            raw_tx = btc_connector.get_transaction(txid)
                            if not raw_tx or vout_index >= len(raw_tx['vout']):
                                results[(txid, vout_index)] = None
                                continue

                            script_pub_key_hex = raw_tx['vout'][vout_index]['scriptPubKey']['hex']
                            scripthash = _calculate_scripthash(script_pub_key_hex)

                            # Mi iscrivo, ottengo la cronologia e mi disiscrivo
                            self._send_request_on_connection(
                                ssock, "blockchain.scripthash.subscribe", [scripthash]
                            )
                            
                            history = self._send_request_on_connection(
                                ssock, "blockchain.scripthash.get_history", [scripthash]
                            )
                            
                            self._send_request_on_connection(
                                ssock, "blockchain.scripthash.unsubscribe", [scripthash]
                            )

                            if not history:
                                results[(txid, vout_index)] = None
                                continue

                            # Cerco lo spender
                            spending_tx = None
                            for tx_item in history:
                                if tx_item['tx_hash'] == txid:
                                    continue

                                spending_tx_raw = self._send_request_on_connection(
                                    ssock, "blockchain.transaction.get", 
                                    [tx_item['tx_hash'], True]
                                )
                                
                                if spending_tx_raw:
                                    for vin in spending_tx_raw.get('vin', []):
                                        if vin.get('txid') == txid and vin.get('vout') == vout_index:
                                            spending_tx = tx_item['tx_hash']
                                            break
                                
                                if spending_tx:
                                    break

                            results[(txid, vout_index)] = spending_tx
                            status = "speso" if spending_tx else "non speso"
                            print(f"UTXO {txid[:10]}...:{vout_index} è {status}")
                            
                        except Exception as e:
                            print(f" Errore per UTXO {txid[:10]}...:{vout_index}: {e}")
                            results[(txid, vout_index)] = None

            print(f"Batch query completata: {len(results)} risultati")
            return results

        except Exception as e:
            print(f"Errore durante batch query: {e}")
            return {}