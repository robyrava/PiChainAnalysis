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
        al formato richiesto da PiChainAnalysis
        """
        try:
            # Eseguo la richiesta GET all'endpoint della transazione
            response = requests.get(f"{self.base_url}/tx/{txid}", timeout=30)
            response.raise_for_status()  # Sollevo un errore per status code 4xx/5xx
            
            # Debug: stampo informazioni sulla risposta
            #print(f"Status code: {response.status_code}")
            #print(f"Content-Type: {response.headers.get('content-type', 'N/A')}")
            
            # Verifico che la risposta sia JSON valido
            try:
                tx_data = response.json()
            except ValueError as json_error:
                print(f"Errore nel parsing JSON della risposta: {json_error}")
                print(f"Contenuto della risposta (primi 200 caratteri): {response.text[:200]}")
                return None

            # Verifico che i campi necessari siano presenti
            if not isinstance(tx_data, dict):
                print(f"Errore: La risposta non è un dizionario: {type(tx_data)}")
                return None
            
            if "txid" not in tx_data:
                print(f"Errore: Campo 'txid' mancante nella risposta")
                print(f"Campi disponibili: {list(tx_data.keys())}")
                return None

            # --- Traduco il formato ---
            # L'API di mempool ha un formato diverso, lo converto per mantenerlo compatibile.
            status_data = tx_data.get("status", {})
            if not isinstance(status_data, dict):
                status_data = {}
            
            formatted_tx = {
                "txid": tx_data.get("txid", ""),
                "blockhash": status_data.get("block_hash"),
                "blockheight": status_data.get("block_height"),  # Aggiungo l'altezza blocco per ottimizzazione
                "time": status_data.get("block_time"),
                "vin": [],
                "vout": []
            }

            # Gestisco in modo sicuro gli input
            vin_data = tx_data.get("vin", [])
            if not isinstance(vin_data, list):
                print(f"Warning: Campo 'vin' non è una lista: {type(vin_data)}")
                vin_data = []
                
            for i, vin in enumerate(vin_data):
                if not isinstance(vin, dict):
                    print(f"Warning: Input {i} non è un dizionario: {type(vin)}")
                    continue
                    
                # Controllo che i campi necessari esistano e siano validi
                input_txid = vin.get("txid")
                input_vout = vin.get("vout")
                
                if input_txid is None:
                    print(f"Warning: Input {i} ha txid None, probabilmente è un coinbase input")
                    # Per i coinbase input, uso valori di default
                    formatted_tx["vin"].append({
                        "txid": "0" * 64,  # Imposto hash nullo per coinbase
                        "vout": 0xffffffff,  # Uso il valore speciale per coinbase
                    })
                    continue
                
                if input_vout is None:
                    print(f"Warning: Input {i} ha vout None, saltato")
                    continue
                    
                # Verifico che vout sia un numero
                try:
                    vout_num = int(input_vout)
                except (ValueError, TypeError):
                    print(f"Warning: Input {i} ha vout non numerico: {input_vout}")
                    continue
                
                formatted_tx["vin"].append({
                    "txid": str(input_txid),
                    "vout": vout_num,
                })

            # Gestisco in modo sicuro gli output
            vout_data = tx_data.get("vout", [])
            if not isinstance(vout_data, list):
                print(f"Warning: Campo 'vout' non è una lista: {type(vout_data)}")
                vout_data = []
                
            for i, vout in enumerate(vout_data):
                if not isinstance(vout, dict):
                    print(f"Warning: Output {i} non è un dizionario: {type(vout)}")
                    continue
                
                try:
                    # Controllo che i campi necessari esistano
                    value = vout.get("value")
                    if value is None:
                        print(f"Warning: Output {i} ha valore None, saltato")
                        continue
                        
                    # Verifico che value sia numerico
                    try:
                        value_num = float(value)
                    except (ValueError, TypeError):
                        print(f"Warning: Output {i} ha valore non numerico: {value}")
                        continue
                    
                    # Gestisco in modo sicuro l'indice n
                    n_value = vout.get("n")
                    if n_value is None:
                        n_value = i  # Uso l'indice come fallback
                    else:
                        try:
                            n_value = int(n_value)
                        except (ValueError, TypeError):
                            print(f"Warning: Output {i} ha indice 'n' non numerico: {n_value}, uso {i}")
                            n_value = i
                    
                    # Gestisco in modo sicuro i dati dello script
                    scriptpubkey = vout.get("scriptpubkey", "")
                    scriptpubkey_address = vout.get("scriptpubkey_address")
                    
                    scriptpubkey_info = {
                        "hex": str(scriptpubkey) if scriptpubkey is not None else "",
                        "address": str(scriptpubkey_address) if scriptpubkey_address is not None else None,
                        "addresses": [str(scriptpubkey_address)] if scriptpubkey_address is not None else []
                    }
                    
                    formatted_tx["vout"].append({
                        "value": value_num / 100_000_000,  # Converto da satoshi a BTC
                        "n": n_value,
                        "scriptPubKey": scriptpubkey_info
                    })
                except Exception as output_error:
                    print(f"Errore nel processare output {i}: {output_error}")
                    continue
            
            print(f"Transazione formattata con successo: {len(formatted_tx['vin'])} input, {len(formatted_tx['vout'])} output")
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
        except KeyError as e:
            print(f"Campo mancante nella risposta API per la transazione {txid}: {e}")
            print(f"Struttura ricevuta: {list(tx_data.keys()) if 'tx_data' in locals() else 'N/A'}")
            return None
        except Exception as e:
            print(f"Errore imprevisto durante il parsing della risposta API per {txid}: {type(e).__name__}: {e}")
            if 'tx_data' in locals():
                print(f"Dati ricevuti (primi 500 caratteri): {str(tx_data)[:500]}")
            return None

    def get_spending_tx(self, txid: str, vout_index: int) -> str:
        """
        Trova la transazione che spende un UTXO usando l'API pubblica.
        """
        try:
            # Uso l'endpoint specifico di mempool.space per questo scopo
            response = requests.get(f"{self.base_url}/tx/{txid}/outspend/{vout_index}", timeout=30)
            
            # Se l'output non risulta speso, l'API restituisce un 404, che considero un caso normale
            if response.status_code == 404:
                return None 

            response.raise_for_status()
            
            # Verifico che la risposta sia JSON valido
            try:
                spend_data = response.json()
            except ValueError as json_error:
                print(f"Errore nel parsing JSON della risposta per outspend: {json_error}")
                print(f"Contenuto della risposta: {response.text[:200]}")
                return None
            
            # Verifico che i dati siano nel formato atteso
            if not isinstance(spend_data, dict):
                print(f"Errore: La risposta non è un dizionario: {type(spend_data)}")
                return None
            
            # Se l'output risulta speso, restituisco l'hash della transazione che lo spende
            if spend_data and spend_data.get("spent"):
                return spend_data.get("txid")
            
            return None

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
            print(f"Errore imprevisto durante il parsing della risposta outspend per {txid}:{vout_index}: {type(e).__name__}: {e}")
            return None

    def get_block_height(self, block_hash: str) -> int:
        """
        Ottiene l'altezza di un blocco dall'API pubblica usando il suo hash.
        """
        try:
            response = requests.get(f"{self.base_url}/block/{block_hash}", timeout=30)
            response.raise_for_status()
            
            try:
                block_data = response.json()
            except ValueError as json_error:
                print(f"Errore nel parsing JSON della risposta per block: {json_error}")
                return 0
            
            if not isinstance(block_data, dict):
                print(f"Errore: La risposta non è un dizionario: {type(block_data)}")
                return 0
            
            height = block_data.get("height", 0)
            if isinstance(height, int):
                return height
            else:
                print(f"Errore: Altezza blocco non è un intero: {type(height)}")
                return 0

        except requests.exceptions.Timeout:
            print(f"Timeout durante la richiesta all'API pubblica per il blocco {block_hash}")
            return 0
        except requests.exceptions.ConnectionError:
            print(f"Errore di connessione all'API pubblica per il blocco {block_hash}")
            return 0
        except requests.exceptions.RequestException as e:
            print(f"Errore durante la richiesta all'API pubblica per il blocco {block_hash}: {e}")
            return 0
        except Exception as e:
            print(f"Errore imprevisto durante il parsing della risposta block per {block_hash}: {type(e).__name__}: {e}")
            return 0