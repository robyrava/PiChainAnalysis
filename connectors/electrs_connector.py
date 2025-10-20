# connectors/electrs_connector.py
import socket
import ssl
import json
import config
import hashlib
from .bitcoin_connector import BitcoinConnector

def _calculate_scripthash(script_hex: str) -> str:
    """Calcola lo scripthash di Electrum da uno script esadecimale."""
    script_bytes = bytes.fromhex(script_hex)
    sha256_hash = hashlib.sha256(script_bytes).digest()
    return sha256_hash[::-1].hex()

class ElectrsConnector:
    """
    Gestisce la connessione sicura al server Electrs.
    """
    def __init__(self):
        self.host = config.ELECTRS_HOST
        self.port = config.ELECTRS_PORT
        self.timeout = config.ELECTRS_TIMEOUT
        self.request_id = 1
        print(f"Connettore Electrs configurato per {self.host}:{self.port}")

    def _get_next_id(self):
        current_id = self.request_id
        self.request_id += 1
        return current_id

    def _send_rpc_request(self, method: str, params: list):
        """
        Invia una singola richiesta JSON-RPC creando una nuova connessione.
        """
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        try:
            with socket.create_connection((self.host, self.port), self.timeout) as sock:
                with context.wrap_socket(sock, server_hostname=self.host) as ssock:
                    request = {
                        "id": self._get_next_id(),
                        "method": method,
                        "params": params
                    }
                    ssock.sendall(json.dumps(request).encode() + b'\n')

                    response_data = b""
                    while True:
                        part = ssock.recv(1024)
                        if not part or b'\n' in part:
                            response_data += part
                            break
                        response_data += part
                    
                    if not response_data:
                        raise ConnectionError("Nessuna risposta ricevuta da Electrs.")

                    response = json.loads(response_data.decode())
                    if 'error' in response:
                        raise Exception(f"Errore Electrs: {response['error']}")
                    return response.get('result')

        except Exception as e:
            print(f"Errore durante la richiesta a Electrs ({method}): {e}")
            return None

    def get_spending_tx(self, btc_connector: BitcoinConnector, txid: str, vout_index: int):
        """
        Trova la transazione che spende un UTXO.
        """
        try:
            # 1. Ottenimento della transazione originale per estrarre lo script
            raw_tx = btc_connector.get_transaction(txid)
            if not raw_tx or vout_index >= len(raw_tx['vout']):
                print(f"Transazione {txid[:10]}... non trovata o indice output non valido")
                return None

            # 2. Calcolo dello scripthash
            script_pub_key_hex = raw_tx['vout'][vout_index]['scriptPubKey']['hex']
            scripthash = _calculate_scripthash(script_pub_key_hex)

            # 3. Ottenimento della cronologia dello scripthash
            history = self._send_rpc_request("blockchain.scripthash.get_history", [scripthash])
            if not history:
                print(f"Impossibile ottenere cronologia per scripthash {scripthash[:16]}...")
                return None

            # 4. Cerca la transazione che spende il nostro UTXO
            for tx_item in history:
                if tx_item['tx_hash'] == txid:
                    continue # Salta la transazione di creazione

                # Ottenimento dei dettagli della transazione "sospetta"
                spending_tx_raw = self._send_rpc_request("blockchain.transaction.get", [tx_item['tx_hash'], True])
                
                if not spending_tx_raw:
                    continue

                # Controllo se uno degli input di questa transazione corrisponde al nostro UTXO
                for vin in spending_tx_raw.get('vin', []):
                    if vin.get('txid') == txid and vin.get('vout') == vout_index:
                        print(f"Trovato spender! TX: {tx_item['tx_hash']}")
                        return tx_item['tx_hash']

            print(f"UTXO {txid[:10]}...:{vout_index} non è stato speso.")
            return None
            
        except Exception as e:
            print(f"Errore imprevisto in get_spending_tx: {e}")
            return None