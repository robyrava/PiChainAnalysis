import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import time

class FanOutAnalyzer:
    """
    Classe per l'analisi delle transazioni Fan-Out.
    Calcola metriche relative alla distribuzione di fondi da pochi input a molti output.
    Tipico di: servizi di payout, faucet, exchange withdrawals, distribuzione batch.
    """
    
    def __init__(self, btc_connector, neo4j_connector, public_api_connector=None):
        """
        Inizializza l'analizzatore Fan-Out.
        
        Args:
            btc_connector: Connettore per il nodo Bitcoin
            neo4j_connector: Connettore per Neo4j
            public_api_connector: Connettore per API pubblica (opzionale, fallback)
        """
        self.btc_connector = btc_connector
        self.neo4j_connector = neo4j_connector
        self.public_api_connector = public_api_connector
        self._last_api_call = 0  # Registro il timestamp dell'ultima chiamata API
        self._api_call_delay = 0.5  # Imposto il ritardo minimo tra chiamate (secondi)
    
    def analyze(self, tx_hash: str) -> Dict[str, Any]:
        """
        Esegue l'analisi completa di una transazione Fan-Out.
        
        Args:
            tx_hash: Hash della transazione da analizzare
            
        Returns:
            Dizionario con i risultati dell'analisi
        """
        print(f"Avvio analisi Fan-Out per transazione: {tx_hash}")
        
        # Recupero i dati della transazione
        tx_data = self._get_transaction_data(tx_hash)
        if not tx_data:
            print(f"Impossibile recuperare dati per la transazione {tx_hash}")
            return {}
        
        # Calcolo le metriche
        metrics = self._calculate_fan_out_metrics(tx_data)
        
        # Aggiungo i dati grezzi per i grafici
        metrics['tx_data'] = tx_data
        
        return metrics
    
    def _get_transaction_data(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """
        Recupera i dati della transazione da Neo4j, con fallback al nodo Bitcoin.
        """
        # Provo prima con Neo4j
        tx_neo4j = self._get_transaction_from_neo4j(tx_hash)
        
        if tx_neo4j and self._is_transaction_complete(tx_neo4j):
            print("Dati recuperati da Neo4j")
            return tx_neo4j
        
        # Eseguo il fallback al nodo Bitcoin
        print("Recupero dati dal nodo Bitcoin...")
        tx_bitcoin = self._get_transaction_from_bitcoin(tx_hash)
        
        return tx_bitcoin
    
    def _get_transaction_from_neo4j(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Recupera la transazione da Neo4j."""
        try:
            result = self.neo4j_connector.get_full_transaction_data(tx_hash)
            if not result or not result[0]:
                return None
            
            record = result[0]
            tx_data = record.get('t')
            inputs = record.get('inputs', [])
            outputs = record.get('outputs', [])
            
            if not tx_data:
                return None
            
            # Formatto i dati
            formatted_tx = {
                'txid': tx_data['TXID'],
                'time': tx_data.get('time'),
                'block_height': tx_data.get('block_height', 0),
                'inputs': [],
                'outputs': []
            }
            
            # Processo gli input
            for inp in inputs:
                if inp and inp.get('utxo_id'):
                    utxo_parts = inp['utxo_id'].split(':')
                    if len(utxo_parts) >= 2:
                        value = inp.get('value', 0)
                        source_txid = utxo_parts[0]
                        vout_index = int(utxo_parts[1])
                        
                        # Controlla se abbiamo il timestamp di creazione salvato in Neo4j
                        creation_time_str = inp.get('creation_time')
                        
                        # Gestisce il caso in cui value sia None
                        if value is None or value == 0:
                            print(f"Recupero valore per input {source_txid[:16]}...:{vout_index}...")
                            value = self._get_utxo_value_from_bitcoin(source_txid, vout_index)
                            if value is None or value == 0:
                                print(f"  -> Valore non recuperabile per {source_txid[:16]}...:{vout_index}")
                                value = 0
                        
                        # Recupera il timestamp di creazione se non è già salvato
                        if not creation_time_str:
                            creation_time = self._get_utxo_creation_time(source_txid)
                            creation_time_str = creation_time.isoformat() if creation_time else None
                        
                        formatted_tx['inputs'].append({
                            'utxo_id': inp['utxo_id'],
                            'value': float(value),
                            'address': inp.get('address', 'unknown'),
                            'creation_time': creation_time_str
                        })
            
            # Processo gli output
            for out in outputs:
                if out and out.get('utxo_id'):
                    formatted_tx['outputs'].append({
                        'utxo_id': out['utxo_id'],
                        'value': float(out.get('value', 0)),
                        'address': out.get('address', 'unknown'),
                        'is_spent': out.get('is_spent', False),
                        'spending_tx_hash': out.get('spending_tx_hash')
                    })
            
            return formatted_tx
            
        except Exception as e:
            print(f"Errore nel recupero da Neo4j: {e}")
            return None
    
    def _get_transaction_from_bitcoin(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Recupera la transazione dal nodo Bitcoin."""
        try:
            raw_tx = self.btc_connector.get_transaction(tx_hash)
            if not raw_tx:
                return None
            
            # Formatto i dati
            formatted_tx = {
                'txid': raw_tx['txid'],
                'time': raw_tx.get('time'),
                'block_height': raw_tx.get('height', 0),
                'inputs': [],
                'outputs': []
            }
            
            # Processo gli input
            for vin in raw_tx.get('vin', []):
                if 'coinbase' in vin:
                    continue
                
                # Recupero la transazione di origine per ottenere il valore
                prev_tx_hash = vin.get('txid')
                prev_vout = vin.get('vout')
                
                if prev_tx_hash:
                    prev_tx = self.btc_connector.get_transaction(prev_tx_hash)
                    if prev_tx and prev_vout < len(prev_tx.get('vout', [])):
                        prev_output = prev_tx['vout'][prev_vout]
                        addresses = prev_output.get('scriptPubKey', {}).get('addresses', ['unknown'])
                        
                        formatted_tx['inputs'].append({
                            'utxo_id': f"{prev_tx_hash}:{prev_vout}",
                            'value': float(prev_output.get('value', 0)),
                            'address': addresses[0] if addresses else 'unknown',
                            'creation_time': prev_tx.get('time')
                        })
            
            # Processo gli output
            for vout in raw_tx.get('vout', []):
                addresses = vout.get('scriptPubKey', {}).get('addresses', ['unknown'])
                
                formatted_tx['outputs'].append({
                    'utxo_id': f"{raw_tx['txid']}:{vout['n']}",
                    'value': float(vout.get('value', 0)),
                    'address': addresses[0] if addresses else 'unknown',
                    'is_spent': False  # Non possiamo saperlo facilmente dal nodo
                })
            
            return formatted_tx
            
        except Exception as e:
            print(f"Errore nel recupero dal nodo Bitcoin: {e}")
            return None
    
    def _is_transaction_complete(self, tx_data: Dict[str, Any]) -> bool:
        """Verifica se la transazione ha dati completi."""
        if not tx_data:
            return False
        
        inputs = tx_data.get('inputs', [])
        outputs = tx_data.get('outputs', [])
        
        return len(inputs) > 0 and len(outputs) > 0
    
    def _get_utxo_value_from_bitcoin(self, tx_hash: str, vout_index: int) -> Optional[float]:
        """
        Recupera il valore di un UTXO specifico dal nodo Bitcoin.
        Usato come fallback quando Neo4j non ha il valore.
        """
        try:
            prev_tx = self.btc_connector.get_transaction(tx_hash)
            if prev_tx and vout_index < len(prev_tx.get('vout', [])):
                return float(prev_tx['vout'][vout_index].get('value', 0))
        except Exception as e:
            print(f"Errore nel recupero valore UTXO: {e}")
        return None
    
    def _get_utxo_creation_time(self, tx_hash: str) -> Optional[datetime]:
        """
        Recupera il timestamp di creazione di un UTXO (quando è stato generato come output).
        Necessario per l'analisi temporale e il grafico distribuzione oraria.
        """
        try:
            tx = self.btc_connector.get_transaction(tx_hash)
            if tx and 'time' in tx:
                return datetime.fromtimestamp(tx['time'], tz=timezone.utc)
        except Exception as e:
            print(f"Errore nel recupero creation time: {e}")
        return None
    
    def _calculate_fan_out_metrics(self, tx_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calcola tutte le metriche per l'analisi Fan-Out.
        """
        inputs = tx_data.get('inputs', [])
        outputs = tx_data.get('outputs', [])
        
        if not inputs or not outputs:
            return {
                'error': 'Dati insufficienti per l\'analisi',
                'input_count': 0,
                'output_count': 0
            }
        
        # Metriche di base
        input_count = len(inputs)
        output_count = len(outputs)
        total_input_value = sum(inp.get('value', 0) for inp in inputs)
        total_output_value = sum(out.get('value', 0) for out in outputs)
        operation_cost = total_input_value - total_output_value
        
        # Analisi della distribuzione degli output
        output_values = [out.get('value', 0) for out in outputs]
        avg_output_value = np.mean(output_values) if output_values else 0
        std_output_value = np.std(output_values) if len(output_values) > 1 else 0
        min_output_value = min(output_values) if output_values else 0
        max_output_value = max(output_values) if output_values else 0
        
        # Coefficiente di variazione (misura l'uniformità della distribuzione)
        cv = (std_output_value / avg_output_value * 100) if avg_output_value > 0 else 0
        
        # Analisi della distribuzione (quanti output sono simili?)
        distribution_uniformity = self._analyze_distribution_uniformity(output_values)
        
        # Categorizzazione degli output
        output_categories = self._categorize_outputs(outputs, avg_output_value)
        
        # Analisi temporale (se disponibile)
        time_analysis = self._analyze_output_spending_time(outputs)
        
        # Ratio di distribuzione
        fan_out_ratio = output_count / input_count if input_count > 0 else 0
        
        metrics = {
            # Metriche di base
            'input_count': input_count,
            'output_count': output_count,
            'fan_out_ratio': fan_out_ratio,
            'total_input_value': total_input_value,
            'total_output_value': total_output_value,
            'operation_cost': operation_cost,
            
            # Analisi distribuzione output
            'avg_output_value': avg_output_value,
            'std_output_value': std_output_value,
            'min_output_value': min_output_value,
            'max_output_value': max_output_value,
            'coefficient_of_variation': cv,
            'distribution_uniformity': distribution_uniformity,
            
            # Categorizzazione
            'output_categories': output_categories,
            
            # Analisi temporale
            'time_analysis': time_analysis,
            
            # Interpretazione
            'interpretation': self._interpret_fan_out(fan_out_ratio, cv, distribution_uniformity)
        }
        
        return metrics
    
    def _analyze_distribution_uniformity(self, values: List[float]) -> Dict[str, Any]:
        """
        Analizza l'uniformità della distribuzione degli output.
        """
        if len(values) < 2:
            return {'uniformity_score': 0, 'description': 'Dati insufficienti'}
        
        # Calcolo il coefficiente di Gini (0 = perfettamente uniforme, 1 = massima disuguaglianza)
        sorted_values = sorted(values)
        n = len(sorted_values)
        cumsum = np.cumsum(sorted_values)
        gini = (2 * sum((i + 1) * v for i, v in enumerate(sorted_values))) / (n * sum(sorted_values)) - (n + 1) / n
        
        # Score di uniformità (inverso del Gini, normalizzato 0-100)
        uniformity_score = (1 - gini) * 100
        
        # Classificazione
        if uniformity_score > 80:
            description = "Alta uniformità - distribuzione molto simile"
        elif uniformity_score > 60:
            description = "Media uniformità - distribuzione moderatamente simile"
        elif uniformity_score > 40:
            description = "Bassa uniformità - distribuzione variabile"
        else:
            description = "Minima uniformità - distribuzione molto disuguale"
        
        return {
            'gini_coefficient': gini,
            'uniformity_score': uniformity_score,
            'description': description
        }
    
    def _categorize_outputs(self, outputs: List[Dict[str, Any]], avg_value: float) -> Dict[str, Any]:
        """
        Categorizza gli output in base al valore rispetto alla media.
        """
        if not outputs or avg_value == 0:
            return {}
        
        small = []  # < 50% della media
        medium = []  # 50-150% della media
        large = []  # > 150% della media
        
        for out in outputs:
            value = out.get('value', 0)
            ratio = (value / avg_value) if avg_value > 0 else 0
            
            if ratio < 0.5:
                small.append(out)
            elif ratio <= 1.5:
                medium.append(out)
            else:
                large.append(out)
        
        return {
            'small_outputs': {
                'count': len(small),
                'total_value': sum(o.get('value', 0) for o in small),
                'percentage': (len(small) / len(outputs) * 100) if outputs else 0
            },
            'medium_outputs': {
                'count': len(medium),
                'total_value': sum(o.get('value', 0) for o in medium),
                'percentage': (len(medium) / len(outputs) * 100) if outputs else 0
            },
            'large_outputs': {
                'count': len(large),
                'total_value': sum(o.get('value', 0) for o in large),
                'percentage': (len(large) / len(outputs) * 100) if outputs else 0
            }
        }
    
    def _analyze_output_spending_time(self, outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analizza quando gli output sono stati spesi (se disponibile).
        """
        spent_count = sum(1 for out in outputs if out.get('is_spent', False))
        unspent_count = len(outputs) - spent_count
        
        return {
            'spent_outputs': spent_count,
            'unspent_outputs': unspent_count,
            'spent_percentage': (spent_count / len(outputs) * 100) if outputs else 0
        }
    
    def _interpret_fan_out(self, ratio: float, cv: float, uniformity: Dict[str, Any]) -> str:
        """
        Fornisce un'interpretazione del tipo di Fan-Out basata sulle metriche.
        """
        interpretations = []
        
        # Analisi del ratio
        if ratio > 50:
            interpretations.append("ALTO fan-out - possibile servizio di distribuzione di massa (faucet, airdrop)")
        elif ratio > 10:
            interpretations.append("MEDIO fan-out - possibile servizio di payout o exchange withdrawal batch")
        else:
            interpretations.append("BASSO fan-out - distribuzione limitata o transazione normale")
        
        # Analisi dell'uniformità
        uniformity_score = uniformity.get('uniformity_score', 0)
        if uniformity_score > 80:
            interpretations.append("Distribuzione UNIFORME - output di valore simile (tipico di faucet o distribuzione programmata)")
        elif uniformity_score > 50:
            interpretations.append("Distribuzione MISTA - combinazione di output grandi e piccoli")
        else:
            interpretations.append("Distribuzione DISUGUALE - output molto variabili (tipico di payout personalizzati)")
        
        # Analisi del coefficiente di variazione
        if cv < 20:
            interpretations.append("Variabilità BASSA - valori molto consistenti")
        elif cv < 50:
            interpretations.append("Variabilità MEDIA - valori moderatamente diversi")
        else:
            interpretations.append("Variabilità ALTA - valori molto diversificati")
        
        return " | ".join(interpretations)
