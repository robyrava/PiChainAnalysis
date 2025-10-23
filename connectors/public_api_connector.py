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
                "blockheight": status_data.get("block_height"), # Aggiunto per potenziale uso futuro
                "time": status_data.get("block_time"),
                "vin": [],
                "vout": []
            }

            # Traduci input
            for vin in tx_data.get("vin", []):
                 # Gestione input coinbase (diverso formato su mempool)
                if vin.get("is_coinbase", False):
                     formatted_tx["vin"].append({"coinbase": True, "sequence": vin.get("sequence")})
                     continue
                
                # Input normali
                formatted_tx["vin"].append({
                    "txid": vin.get("txid"),
                    "vout": vin.get("vout"),
                    
                })

            # Traduci output
            for i, vout in enumerate(tx_data.get("vout", [])):
                 # Assicurati che scriptPubKey esista
                scriptpubkey_address = vout.get("scriptpubkey_address")
                scriptpubkey_info = {
                    "hex": vout.get("scriptpubkey"), # Manca 'hex' diretto, usiamo scriptpubkey
                    "address": scriptpubkey_address,
                     # Simula 'addresses' come fa RPC
                    "addresses": [scriptpubkey_address] if scriptpubkey_address else []
                }
                
                formatted_tx["vout"].append({
                    # Converti da satoshi a BTC
                    "value": float(vout.get("value", 0)) / 100_000_000,
                    "n": i, # L'API mempool non sembra fornire 'n', usiamo l'indice
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
            # Gestisce errori HTTP (4xx, 5xx) e altri errori di richiesta
            print(f"Errore durante la richiesta all'API pubblica per la transazione {txid}: {e}")
            return None
        except Exception as e:
            # Cattura altri errori imprevisti (es. parsing JSON fallito)
            print(f"Errore imprevisto durante il recupero da API pubblica per {txid}: {e}")
            return None

    # Aggiungeremo get_block_height e get_spending_tx nei commit successivi
    def get_block_height(self, block_hash: str) -> int:
         """Ottiene l'altezza di un blocco (placeholder)."""
         # Implementazione base per ora
         try:
            response = requests.get(f"{self.base_url}/block/{block_hash}", timeout=10)
            response.raise_for_status()
            block_data = response.json()
            return block_data.get("height", 0)
         except Exception as e:
            print(f"Errore API pubblica (get_block_height): {e}")
            return 0