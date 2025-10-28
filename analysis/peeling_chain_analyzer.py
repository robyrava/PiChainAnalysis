import numpy as np
from typing import Tuple, Dict, Any, List, Optional

def safe_float_conversion(value, default=0.0):
    """Converte in modo sicuro un valore in float."""
    if value is None: return default
    try: return float(value)
    except (ValueError, TypeError): return default

def check_neo4j_transaction_coverage(neo4j_connector, tx_hash):
    """Verifica la completezza dei dati di una transazione in Neo4j."""
    try:
        exists_result = neo4j_connector.check_transaction_exists(tx_hash)
        exists = exists_result[0]['exists'] if exists_result else False
        if not exists:
            return {"exists": False, "complete": False, "message": "Transazione non trovata in Neo4j"}
        
        return {"exists": True, "complete": True, "message": "Transazione trovata"}
    except Exception as e:
        return {"exists": False, "complete": False, "message": f"Errore controllo Neo4j: {e}"}


class PeelingChainAnalyzer:
    """
    Analizza le peeling chain, affidandosi principalmente a Neo4j.
    """
    def __init__(self, btc_connector, electrs_connector, neo4j_connector):
        self.btc_connector = btc_connector
        self.electrs_connector = electrs_connector
        self.neo4j_connector = neo4j_connector

    def _get_transaction_from_neo4j(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Recupera dati completi da Neo4j e li formatta come RPC."""
        try:
            result = self.neo4j_connector.get_full_transaction_data(tx_hash)
            if not result or not result[0] or 't' not in result[0]: return None
            
            record = result[0]
            tx_data = record['t']
            inputs = record.get('inputs', [])
            outputs = record.get('outputs', [])
            
            formatted_tx = {
                'txid': tx_data['TXID'], 'time': tx_data.get('time'),
                'vin': [], 'vout': [],
                'input_value_total': safe_float_conversion(tx_data.get('input_value'))
            }
            
            valid_inputs = [inp for inp in inputs if inp and inp.get('utxo_id')]
            for inp in valid_inputs:
                utxo_parts = inp['utxo_id'].split(':')
                formatted_tx['vin'].append({
                    'txid': utxo_parts[0],
                    'vout': int(utxo_parts[1]) if len(utxo_parts) > 1 else 0,
                    'value': safe_float_conversion(inp.get('value')) 
                })
            
            valid_outputs = [out for out in outputs if out and out.get('utxo_id')]
            for i, out in enumerate(valid_outputs):
                 # Aggiungiamo 'n' basato sull'ordine in Neo4j se non presente
                 output_n = out.get('index', i) # Usa 'index' se c'è, altrimenti l'indice della lista
                 addr = out.get('address', 'unknown')
                 
                 formatted_tx['vout'].append({
                    'n': output_n,
                    'value': safe_float_conversion(out.get('value')),
                    'scriptPubKey': {'addresses': [addr] if addr else []},
                    'spending_tx_hash': out.get('spending_tx_hash')
                 })
                 
            # Ordina gli output per indice 'n' per consistenza
            formatted_tx['vout'] = sorted(formatted_tx['vout'], key=lambda x: x['n'])

            return formatted_tx
        except Exception as e:
            print(f"Errore recupero da Neo4j ({tx_hash}): {e}")
            return None

    def _find_next_transaction_neo4j(self, tx_hash: str, output_index: int) -> Optional[str]:
        """Trova la transazione spesa da Neo4j."""
        utxo_id = f"{tx_hash}:{output_index}"
        try:
            result = self.neo4j_connector.find_spending_transaction(utxo_id)
            return result[0]['spending_tx_hash'] if result and result[0].get('spending_tx_hash') else None
        except Exception as e:
            print(f"Errore ricerca spender Neo4j ({utxo_id}): {e}")
            return None

    def _get_total_input_value(self, raw_tx: Dict[str, Any]) -> float:
        """Calcola il valore totale degli input, priorità a Neo4j, fallback a Bitcoin Core."""
        # Se il valore è già stato calcolato da Neo4j
        if raw_tx.get('input_value_total', 0) > 0:
            return raw_tx['input_value_total']

        total_value = 0.0
        for vin in raw_tx.get('vin', []):
            # Se il valore è nell'input (recuperato da Neo4j _get_transaction_from_neo4j)
            if 'value' in vin and vin['value'] is not None:
                total_value += safe_float_conversion(vin['value'])
            else: # Fallback: recupera dal nodo Bitcoin
                source_tx_hash, source_tx_index = vin.get('txid'), vin.get('vout')
                if not source_tx_hash or source_tx_hash == "0" * 64: continue # Salta coinbase

                try:
                    # NOTA: Evitiamo chiamate RPC non necessarie se possibile
                    # Questo potrebbe essere chiamato solo se Neo4j non aveva il valore
                    print(f"Fallback: Recupero valore input da nodo Bitcoin per {source_tx_hash[:10]}...:{source_tx_index}")
                    source_tx_data = self.btc_connector.get_transaction(source_tx_hash)
                    if source_tx_data and source_tx_index < len(source_tx_data.get('vout', [])):
                        value = source_tx_data['vout'][source_tx_index]['value']
                        total_value += safe_float_conversion(value)
                except Exception as e:
                    print(f"Errore recupero input fallback ({source_tx_hash}:{source_tx_index}): {e}")
                    continue
        return total_value

    def _identify_peeling_outputs(self, raw_tx: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Identifica output 'peeled' (piccolo) e 'change' (grande)."""
        vouts = raw_tx.get('vout', [])
        # Rilassiamo il controllo a >= 2 output per gestire casi più generali
        if len(vouts) < 2:
             print(f"Warning: Transazione {raw_tx.get('txid','N/A')[:10]} ha meno di 2 output ({len(vouts)}).")
             # Potrebbe essere la fine o una tx non-peeling. Se c'è un solo output, consideralo 'change'?
             # Per ora, non lo consideriamo peeling standard.
             return None, None

        valid_vouts = []
        for vout in vouts:
            vout['value'] = safe_float_conversion(vout.get('value'))
            # Aggiungi un controllo per 'n' se necessario, o assumi l'ordine
            if 'n' not in vout: vout['n'] = vouts.index(vout) # Assegna indice se mancante
            valid_vouts.append(vout)

        # Ordina per valore
        sorted_vouts = sorted(valid_vouts, key=lambda x: x['value'])
        peeled_output = sorted_vouts[0] # Il più piccolo
        change_output = sorted_vouts[-1] # Il più grande

        # Controllo di sicurezza: non dovrebbero essere lo stesso output se ce ne sono >= 2
        if peeled_output['n'] == change_output['n'] and len(valid_vouts) >=2 :
             print(f"Warning: Peeled e Change sembrano essere lo stesso output per {raw_tx.get('txid','N/A')[:10]}. Controllare.")
             # Potrebbe succedere se tutti gli output hanno lo stesso valore?
             # Gestiamo restituendo il primo e l'ultimo per convenzione.

        return peeled_output, change_output

    def _calculate_metrics(self, chain_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcola metriche finali (semplificato per ora)."""
        if not chain_data: return {"chain_length": 0, "total_peeled_value": 0.0}

        peeled_values = [tx['peeled_value'] for tx in chain_data]
        return {
            "chain_length": len(chain_data),
            "total_peeled_value": sum(peeled_values),
            
        }

    def analyze(self, start_hash: str) -> Dict[str, Any]:
        """Esegue l'analisi completa, priorità a Neo4j."""
        print(f"\nAvvio analisi peeling chain per: {start_hash}")
        chain_data = []
        current_hash = start_hash
        max_steps_debug = 100 # Limite di sicurezza per evitare cicli infiniti

        while current_hash and len(chain_data) < max_steps_debug:
            print(f"Analizzo TX: {current_hash[:16]}...")
            try:
                # 1. Prova a recuperare da Neo4j
                raw_tx = self._get_transaction_from_neo4j(current_hash)

                # 2. Fallback: Se Neo4j fallisce o manca, prova Bitcoin Core
                if not raw_tx:
                    print(f" Neo4j non ha dati per {current_hash[:10]}... Fallback su Bitcoin Core.")
                    raw_tx = self.btc_connector.get_transaction(current_hash) # Usa il connettore esistente

                # 3. Se ancora non abbiamo dati, interrompi
                if not raw_tx:
                    print(f" Impossibile recuperare dati per {current_hash}. Fine catena.")
                    break

                # 4. Identifica output peeled e change
                peeled_output, change_output = self._identify_peeling_outputs(raw_tx)
                if not peeled_output or not change_output:
                    print(f" Transazione {current_hash[:10]}... non sembra peeling standard. Fine catena.")
                    break # Non è una transazione peeling standard (o errore)

                # 5. Calcola valori
                total_input = self._get_total_input_value(raw_tx)
                peeled_value = peeled_output['value']
                change_value = change_output['value']
                peeled_percentage = (peeled_value / total_input) * 100 if total_input > 0 else 0

                chain_data.append({
                    "tx_hash": current_hash,
                    "input_value": total_input,
                    "peeled_value": peeled_value,
                    "change_value": change_value,
                    "peeled_percentage": peeled_percentage
                })

                # 6. Trova la prossima transazione
                next_tx = None
                change_output_index = change_output['n']

                # 6a. Prova Neo4j
                next_tx = self._find_next_transaction_neo4j(current_hash, change_output_index)
                
                # 6b. Fallback: Se Neo4j non trova, prova Electrs
                if not next_tx:
                    print(f" Neo4j non ha lo spender per {current_hash[:10]}...:{change_output_index}. Fallback su Electrs...")
                    # NOTA: Assumiamo che electrs_connector esista e sia configurato
                    next_tx = self.electrs_connector.get_spending_tx(
                        self.btc_connector, current_hash, change_output_index
                    )
                
                if next_tx:
                     print(f" Prossima TX trovata: {next_tx[:16]}...")
                     current_hash = next_tx
                else:
                     print(f" Nessuna transazione successiva trovata per {current_hash[:10]}...:{change_output_index}. Fine catena.")
                     current_hash = None # Fine della catena

            except Exception as e:
                print(f"Errore durante l'analisi di {current_hash}: {e}")
                import traceback
                traceback.print_exc() # Stampa traceback per debug
                break # Interrompi in caso di errore grave

        if len(chain_data) >= max_steps_debug:
             print(f"Warning: Raggiunto limite massimo di {max_steps_debug} passi. Interruzione.")

        final_metrics = self._calculate_metrics(chain_data)
        final_metrics["chain"] = chain_data # Aggiunge la catena raccolta ai risultati
        
        print(f"Analisi completata. Lunghezza catena: {len(chain_data)}")
        return final_metrics