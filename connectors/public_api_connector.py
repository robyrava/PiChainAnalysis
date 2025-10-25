import requests
import time

class PublicApiConnector:
    """
    Gestisce le chiamate a un'API pubblica (mempool.space) come fallback
    per recuperare i dati della blockchain.
    """
    def __init__(self):
        self.base_url = "https://mempool.space/api"
        print("Connettore API Pubblica (mempool.space) inizializzato.")

    def get_transaction(self, txid: str) -> dict:
        """
        Recupera i dati di una transazione dall'API pubblica e li adatta
        al formato richiesto da PiChainAnalysis (formato RPC Bitcoin Core).
        """
        try:
            response = requests.get(f"{self.base_url}/tx/{txid}", timeout=20)
            response.raise_for_status()
            tx_data = response.json()

            # --- Traduzione del formato da Mempool a RPC-like ---
            status_data = tx_data.get("status", {})
            formatted_tx = {
                "txid": tx_data.get("txid"),
                "blockhash": status_data.get("block_hash"),
                "blockheight": status_data.get("block_height"),
                "time": status_data.get("block_time"),
                "vin": [],
                "vout": []
            }

            for vin in tx_data.get("vin", []):
                if vin.get("is_coinbase", False):
                    formatted_tx["vin"].append({"coinbase": True, "sequence": vin.get("sequence")})
                    continue
                formatted_tx["vin"].append({
                    "txid": vin.get("txid"),
                    "vout": vin.get("vout"),
                })

            for i, vout in enumerate(tx_data.get("vout", [])):
                scriptpubkey_address = vout.get("scriptpubkey_address")
                scriptpubkey_info = {
                    "hex": vout.get("scriptpubkey"),
                    "address": scriptpubkey_address,
                    "addresses": [scriptpubkey_address] if scriptpubkey_address else []
                }
                formatted_tx["vout"].append({
                    "value": float(vout.get("value", 0)) / 100_000_000,
                    "n": i,
                    "scriptPubKey": scriptpubkey_info
                })
            return formatted_tx

        except requests.exceptions.Timeout:
            print(f"Timeout durante la richiesta all'API pubblica per la transazione {txid}")
            return None
        except requests.exceptions.ConnectionError:
            print(f"Errore di connessione all'API pubblica per la transazione {txid}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Errore durante la richiesta all'API pubblica per la transazione {txid}: {e}")
            return None
        except Exception as e:
            print(f"Errore imprevisto durante il recupero da API pubblica per {txid}: {e}")
            return None

    def get_spending_tx(self, txid: str, vout_index: int) -> str:
        """
        Trova la transazione che spende un UTXO usando l'API pubblica.
        """
        try:
            # mempool.space ha un endpoint specifico per questo scopo
            response = requests.get(f"{self.base_url}/tx/{txid}/outspend/{vout_index}", timeout=20) # Aumentato timeout

            # Se l'output non è speso, l'API restituisce un 404, che è un caso normale
            if response.status_code == 404:
                # print(f"API: UTXO {txid[:10]}:{vout_index} non speso.")
                return None

            response.raise_for_status() # Solleva errore per altri status code (es. 5xx)
            spend_data = response.json()

            # Se l'output è speso, restituisce l'hash della transazione che lo spende
            if spend_data and spend_data.get("spent"):
                spending_txid = spend_data.get("txid")
                # print(f"API: Trovato spender {spending_txid[:10]}... per {txid[:10]}:{vout_index}")
                return spending_txid
            else:
                 # print(f"API: UTXO {txid[:10]}:{vout_index} marcato come non speso dalla risposta.")
                 return None # Non speso secondo l'API

        except requests.exceptions.Timeout:
            print(f"Timeout durante la richiesta all'API pubblica per lo spender di {txid}:{vout_index}")
            return None
        except requests.exceptions.ConnectionError:
            print(f"Errore di connessione all'API pubblica per lo spender di {txid}:{vout_index}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Errore durante la richiesta all'API pubblica per lo spender di {txid}:{vout_index}: {e}")
            return None
        except Exception as e:
            print(f"Errore imprevisto durante il recupero spender da API per {txid}:{vout_index}: {e}")
            return None

    def get_block_height(self, block_hash: str) -> int:
         """Ottiene l'altezza di un blocco."""
         if not block_hash: return 0
         try:
            response = requests.get(f"{self.base_url}/block/{block_hash}", timeout=10)
            response.raise_for_status()
            block_data = response.json()
            return block_data.get("height", 0)
         except Exception as e:
            print(f"Errore API pubblica (get_block_height): {e}")
            return 0