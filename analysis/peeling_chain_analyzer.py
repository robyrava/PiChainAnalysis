# analysis/peeling_chain_analyzer.py
import numpy as np
from typing import Tuple, Dict, Any, List, Optional


def safe_float_conversion(value, default=0.0):
    """
    Converte in modo sicuro un valore in float.
    
    Args:
        value: Valore da convertire
        default: Valore di default se la conversione fallisce
        
    Returns:
        float: Valore convertito o default
    """
    if value is None:
        return default
    
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def check_neo4j_transaction_coverage(neo4j_connector, tx_hash):
    """
    Verifica la completezza dei dati di una transazione in Neo4j.
    
    Args:
        neo4j_connector: Connettore Neo4j
        tx_hash: Hash della transazione da verificare
        
    Returns:
        dict: Report della copertura dati
    """
    try:
        # Verifico l'esistenza della transazione
        exists_result = neo4j_connector.check_transaction_exists(tx_hash)
        exists = exists_result[0]['exists'] if exists_result else False
        
        if not exists:
            return {"exists": False, "complete": False, "message": "Transazione non trovata in Neo4j"}
        
        # Verifico la completezza di input e output
        outputs_result = neo4j_connector.get_transaction_outputs(tx_hash)
        inputs_result = neo4j_connector.get_transaction_inputs(tx_hash)
        
        output_count = len(outputs_result) if outputs_result else 0
        input_count = len(inputs_result) if inputs_result else 0
        
        # Analizzo le possibili transazioni spender
        spending_info = []
        if outputs_result:
            for output in outputs_result:
                spending_info.append({
                    "utxo_id": output['utxo_id'],
                    "value": output['value'],
                    "is_spent": output['is_spent'],
                    "spending_tx_hash": output['spending_tx_hash']
                })
        
        return {
            "exists": True,
            "complete": output_count > 0 and input_count >= 0,
            "output_count": output_count,
            "input_count": input_count,
            "spending_info": spending_info,
            "message": f"Transazione completa: {input_count} input, {output_count} output"
        }
        
    except Exception as e:
        return {"exists": False, "complete": False, "message": f"Errore: {e}"}

class PeelingChainAnalyzer:
    """
    Questa classe è responsabile dell'analisi delle peeling chain.
    Utilizza principalmente Neo4j come fonte dati e si connette al nodo Bitcoin
    solo quando servono informazioni aggiuntive non presenti nel database.
    """
    def __init__(self, btc_connector, electrs_connector, neo4j_connector):
        """
        Inizializza l'analizzatore con i connettori necessari.

        Args:
            btc_connector: Un'istanza di BitcoinConnector per dati aggiuntivi.
            electrs_connector: Un'istanza di ElectrsConnector (mantenuto per compatibilità).
            neo4j_connector: Un'istanza di Neo4jConnector per i dati principali.
        """
        self.btc_connector = btc_connector
        self.electrs_connector = electrs_connector
        self.neo4j_connector = neo4j_connector

    def _get_transaction_from_neo4j(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Recupera i dati completi di una transazione da Neo4j."""
        try:
            # Provo prima con la query completa
            result = self.neo4j_connector.get_full_transaction_data(tx_hash)
            if not result:
                return None
            
            record = result[0]
            
            # Controllo se ho il formato atteso
            if 't' not in record:
                print(f"Formato dati inaspettato da Neo4j per {tx_hash}")
                return None
                
            tx_data = record['t']
            inputs = record.get('inputs', [])
            outputs = record.get('outputs', [])
            
            # Converto nel formato compatibile con Bitcoin RPC
            formatted_tx = {
                'txid': tx_data['TXID'],
                'time': tx_data.get('time'),
                'vin': [],
                'vout': []
            }
            
            # Formatto gli input filtrando quelli vuoti
            valid_inputs = [inp for inp in inputs if inp and inp.get('utxo_id')]
            for i, inp in enumerate(valid_inputs):
                utxo_parts = inp['utxo_id'].split(':')
                formatted_tx['vin'].append({
                    'txid': utxo_parts[0] if len(utxo_parts) > 0 else inp['utxo_id'],
                    'vout': int(utxo_parts[1]) if len(utxo_parts) > 1 else 0,
                    'value': safe_float_conversion(inp.get('value'))
                })
            
            # Formatto gli output filtrando quelli vuoti
            valid_outputs = [out for out in outputs if out and out.get('utxo_id')]
            for i, out in enumerate(valid_outputs):
                formatted_tx['vout'].append({
                    'n': i,
                    'value': safe_float_conversion(out.get('value')),
                    'scriptPubKey': {'addresses': [out.get('address')] if out.get('address') else []},
                    'spending_tx_hash': out.get('spending_tx_hash')
                })
            
            return formatted_tx
            
        except Exception as e:
            print(f"Errore nel recupero da Neo4j per {tx_hash}: {e}")
            return None

    def _find_next_transaction_neo4j(self, tx_hash: str, output_index: int) -> Optional[str]:
        """Trova la transazione che spende un output specifico usando Neo4j."""
        utxo_id = f"{tx_hash}:{output_index}"
        try:
            result = self.neo4j_connector.find_spending_transaction(utxo_id)
            if result and result[0]['spending_tx_hash']:
                return result[0]['spending_tx_hash']
            return None
        except Exception as e:
            print(f"Errore nella ricerca spending transaction per {utxo_id}: {e}")
            return None

    def _get_total_input_value(self, raw_tx: Dict[str, Any]) -> float:
        """Calcola il valore totale degli input di una transazione usando principalmente Neo4j."""
        total_value = 0.0
        
        # Se trovo il valore già presente nella transazione (da Neo4j) lo riuso
        if 'input_value_total' in raw_tx:
            return safe_float_conversion(raw_tx['input_value_total'])
        
        for vin in raw_tx.get('vin', []):
            if 'value' in vin:
                # In questo caso il valore è già presente (da Neo4j)
                total_value += safe_float_conversion(vin['value'])
            else:
                # Come fallback recupero dal nodo Bitcoin solo se necessario
                source_tx_hash = vin.get('txid')
                source_tx_index = vin.get('vout')
                
                # Salto gli input coinbase
                if not source_tx_hash or source_tx_hash == "0" * 64:
                    continue

                try:
                    print(f"🔄 Recupero valore input da nodo Bitcoin per {source_tx_hash}:{source_tx_index}")
                    source_tx_data = self.btc_connector.get_transaction(source_tx_hash)
                    if source_tx_data and source_tx_index < len(source_tx_data.get('vout', [])):
                        value = source_tx_data['vout'][source_tx_index]['value']
                        total_value += safe_float_conversion(value)
                except Exception as e:
                    print(f"Errore nel recupero input da {source_tx_hash}:{source_tx_index} - {e}")
                    continue
                
        return total_value

    def _identify_peeling_outputs(self, raw_tx: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        Identifica l'output 'pelato' (più piccolo) e quello 'resto' (più grande).
        Assume una transazione standard di peeling con due output.
        """
        vouts = raw_tx.get('vout', [])
        if len(vouts) != 2:
            return None, None
            
        # Converto i valori in float usando la conversione sicura
        for vout in vouts:
            if 'value' in vout:
                vout['value'] = safe_float_conversion(vout['value'])
            
        sorted_vouts = sorted(vouts, key=lambda x: x['value'])
        peeled_output = sorted_vouts[0]
        change_output = sorted_vouts[1]
        
        return peeled_output, change_output

    def _analyze_peeling_patterns(self, chain_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analizza i pattern nella peeling chain per identificare comportamenti anomali."""
        if not chain_data:
            return {}
        
        percentages = [tx['peeled_percentage'] for tx in chain_data]
        
        # Mantengo solo il rilevamento delle anomalie
        return {
            "anomaly_detection": self._detect_anomalies(percentages)
        }

    def _detect_anomalies(self, percentages: List[float]) -> Dict[str, Any]:
        """Rileva anomalie nei pattern di peeling usando l'IQR method."""
        if len(percentages) < 4:
            return {"anomalies": [], "anomaly_count": 0}
        
        q1 = np.percentile(percentages, 25)
        q3 = np.percentile(percentages, 75)
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr
        
        anomalies = [i for i, p in enumerate(percentages) if p < lower_bound or p > upper_bound]
        
        return {
            "anomalies": anomalies,
            "anomaly_count": len(anomalies),
            "lower_bound": lower_bound,
            "upper_bound": upper_bound
        }

    def _calculate_metrics(self, chain_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calcola le metriche finali basandosi sui dati raccolti della catena."""
        if not chain_data:
            return {
                "chain_length": 0, 
                "total_peeled_value": 0.0,
                "average_peeled_percentage": 0.0, 
                "advanced_analytics": {}
            }

        peeled_percentages = [tx['peeled_percentage'] for tx in chain_data if tx['input_value'] > 0]
        peeled_values = [tx['peeled_value'] for tx in chain_data]
        
        # Calcolo le metriche di base
        base_metrics = {
            "chain_length": len(chain_data),
            "total_peeled_value": sum(peeled_values),
            "average_peeled_percentage": np.mean(peeled_percentages) if peeled_percentages else 0.0,
            "min_peeled_percentage": min(peeled_percentages) if peeled_percentages else 0.0,
            "max_peeled_percentage": max(peeled_percentages) if peeled_percentages else 0.0,
        }
        
        # Eseguo l'analisi avanzata
        advanced_analytics = self._analyze_peeling_patterns(chain_data)
        base_metrics["advanced_analytics"] = advanced_analytics
        
        # Aggiorno con statistiche aggiuntive sui valori
        if peeled_values:
            base_metrics.update({
                "total_value_processed": sum(tx['input_value'] for tx in chain_data),
                "average_transaction_size": np.mean([tx['input_value'] for tx in chain_data]),
                "largest_peel": max(peeled_values),
                "smallest_peel": min(peeled_values)
            })
        
        return base_metrics

    def analyze(self, start_hash: str) -> Dict[str, Any]:
        """
        Esegue l'analisi completa di una peeling chain a partire da un hash.
        Utilizza principalmente Neo4j come fonte dati.
        """
        print(f"Avvio analisi peeling chain per: {start_hash}")
        chain_data = []
        current_hash = start_hash

        while current_hash:
            try:
                # Verifico la copertura in Neo4j
                coverage = check_neo4j_transaction_coverage(self.neo4j_connector, current_hash)
                
                # Provo prima con Neo4j
                raw_tx = self._get_transaction_from_neo4j(current_hash)
                
                if not raw_tx:
                    print(f"Transazione {current_hash} non trovata in Neo4j")
                    # In fallback provo con il nodo Bitcoin
                    print(f"Tentativo di recupero dal nodo Bitcoin...")
                    raw_tx = self.btc_connector.get_transaction(current_hash)
                    
                if not raw_tx:
                    break

                peeled_output, change_output = self._identify_peeling_outputs(raw_tx)
                if not peeled_output:
                    print(f"La transazione {current_hash} non è una peeling classica. Fine della catena.")
                    break

                total_input = self._get_total_input_value(raw_tx)
                if total_input > 0:
                    peeled_value = safe_float_conversion(peeled_output['value'])
                    peeled_percentage = (peeled_value / total_input) * 100
                else:
                    print(f"Valore di input nullo per la transazione {current_hash}.")
                    peeled_value = safe_float_conversion(peeled_output['value'])
                    peeled_percentage = 0.0

                # Estraggo il timestamp della transazione se disponibile
                tx_time = raw_tx.get('time')
                
                chain_data.append({
                    "tx_hash": current_hash,
                    "input_value": total_input,
                    "peeled_value": peeled_value,
                    "change_value": safe_float_conversion(change_output['value']),
                    "peeled_percentage": peeled_percentage,
                    "time": tx_time  # Aggiungo il timestamp per analisi temporali
                })

                # Cerco la prossima transazione usando prima Neo4j
                next_tx = None
                change_output_index = change_output.get('n', 1)  # Di solito considero l'output di change all'indice 1
                
                # Metodo 1: cerco in Neo4j
                next_tx = self._find_next_transaction_neo4j(current_hash, change_output_index)
                
                if not next_tx:
                    # Metodo 2: passo al fallback con Electrs
                    print(f"Neo4j non ha trovato la prossima transazione, provo con Electrs...")
                    next_tx = self.electrs_connector.get_spending_tx(
                        self.btc_connector, current_hash, change_output_index
                    )
                
                if next_tx:
                    current_hash = next_tx
                else:
                    current_hash = None
                    
            except Exception as e:
                break
        
        final_metrics = self._calculate_metrics(chain_data)
        final_metrics["chain"] = chain_data
        
        return final_metrics