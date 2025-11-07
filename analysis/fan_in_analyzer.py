import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import time

class FanInAnalyzer:
    """
    Classe per l'analisi delle transazioni Fan-In.
    Calcola metriche relative al consolidamento di fondi e identifica pattern tipici di mixer/tumbler.
    """
    
    def __init__(self, btc_connector, neo4j_connector, public_api_connector=None):
        """
        Inizializza l'analizzatore Fan-In.
        
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
        Esegue l'analisi completa di una transazione Fan-In.
        
        Args:
            tx_hash: Hash della transazione da analizzare
            
        Returns:
            Dizionario con i risultati dell'analisi
        """
        print(f"Avvio analisi Fan-In per transazione: {tx_hash}")
        
        # Recupero i dati della transazione
        tx_data = self._get_transaction_data(tx_hash)
        if not tx_data:
            print(f"Impossibile recuperare dati per la transazione {tx_hash}")
            return {}
        
        # Calcolo le metriche
        metrics = self._calculate_fan_in_metrics(tx_data)
        
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
            
            # Formatta i dati
            formatted = {
                'txid': tx_data.get('TXID'),
                'time': tx_data.get('time'),
                'block_height': tx_data.get('block_height', 0),
                'inputs': [],
                'outputs': []
            }
            
            # Processa gli input
            for inp in inputs:
                if inp and inp.get('utxo_id'):
                    utxo_parts = inp['utxo_id'].split(':')
                    if len(utxo_parts) >= 2:
                        value = inp.get('value', 0)
                        source_txid = utxo_parts[0]
                        vout_index = int(utxo_parts[1])
                        
                        # Controlla se abbiamo già i dati salvati in Neo4j
                        creation_time_str = inp.get('creation_time')
                        days_held = inp.get('days_held')
                        coin_days = inp.get('coin_days')
                        
                        # Gestisce il caso in cui value sia None - recupera con fallback
                        if value is None or value == 0:
                            print(f"Recupero valore per input {source_txid[:16]}...:{vout_index}...")
                            value = self._get_utxo_value_from_bitcoin(source_txid, vout_index)
                            if value is None or value == 0:
                                print(f"  -> Valore non recuperabile per {source_txid[:16]}...:{vout_index}")
                                value = 0
                        
                        # Recupera il timestamp di creazione solo se non è già salvato
                        if not creation_time_str:
                            creation_time = self._get_utxo_creation_time(source_txid)
                            creation_time_str = creation_time.isoformat() if creation_time else None
                        
                        formatted['inputs'].append({
                            'txid': source_txid,
                            'vout': vout_index,
                            'value': float(value),
                            'address': inp.get('address'),
                            'creation_time': creation_time_str,
                            'days_held': days_held,
                            'coin_days': coin_days
                        })
            
            # Processo gli output (di solito hanno sempre il valore corretto)
            for out in outputs:
                if out and out.get('utxo_id'):
                    value = out.get('value', 0)
                    
                    # Gestisco il caso in cui value sia None (evento raro per gli output)
                    if value is None or value == 0:
                        utxo_parts = out.get('utxo_id', ':').split(':')
                        if len(utxo_parts) >= 2:
                            print(f"Recupero valore per output {utxo_parts[0][:16]}...:{utxo_parts[1]} dal nodo Bitcoin...")
                            value = self._get_utxo_value_from_bitcoin(utxo_parts[0], int(utxo_parts[1]))
                            if value is None:
                                value = 0
                    
                    formatted['outputs'].append({
                        'value': float(value),
                        'address': out.get('address'),
                        'is_spent': out.get('is_spent', False)
                    })
            
            return formatted
            
        except Exception as e:
            print(f"Errore nel recupero da Neo4j: {e}")
            return None
    
    def _get_transaction_from_bitcoin(self, tx_hash: str) -> Optional[Dict[str, Any]]:
        """Recupera la transazione dal nodo Bitcoin."""
        try:
            raw_tx = self.btc_connector.get_transaction(tx_hash)
            if not raw_tx:
                return None
            
            formatted = {
                'txid': raw_tx['txid'],
                'time': raw_tx.get('time'),
                'block_height': 0,
                'inputs': [],
                'outputs': []
            }
            
            # Recupero la block height se disponibile
            if raw_tx.get('blockhash'):
                formatted['block_height'] = self.btc_connector.get_block_height(raw_tx['blockhash'])
            
            # Processo gli input
            for vin in raw_tx.get('vin', []):
                if 'coinbase' in vin:
                    continue
                
                source_tx = self.btc_connector.get_transaction(vin['txid'])
                if source_tx:
                    vout = source_tx['vout'][vin['vout']]
                    addresses = vout.get('scriptPubKey', {}).get('addresses', [])
                    address = addresses[0] if addresses else None
                    
                    formatted['inputs'].append({
                        'txid': vin['txid'],
                        'vout': vin['vout'],
                        'value': float(vout['value']),
                        'address': address
                    })
            
            # Processo gli output
            for vout in raw_tx.get('vout', []):
                addresses = vout.get('scriptPubKey', {}).get('addresses', [])
                address = addresses[0] if addresses else None
                
                formatted['outputs'].append({
                    'value': float(vout['value']),
                    'address': address,
                    'is_spent': False
                })
            
            return formatted
            
        except Exception as e:
            print(f"Errore nel recupero dal nodo Bitcoin: {e}")
            return None
    
    def _is_transaction_complete(self, tx_data: Dict[str, Any]) -> bool:
        """Verifica se i dati della transazione sono completi."""
        if not tx_data:
            return False
        
        inputs = tx_data.get('inputs', [])
        outputs = tx_data.get('outputs', [])
        
        # Verifico che ci siano input e output
        if not inputs or not outputs:
            return False
        
        # Verifico che gli input abbiano i valori
        for inp in inputs:
            if 'value' not in inp or inp['value'] is None:
                return False
        
        return True
    
    def _calculate_fan_in_metrics(self, tx_data: Dict[str, Any]) -> Dict[str, Any]:
        """Calcola tutte le metriche per l'analisi Fan-In."""
        inputs = tx_data.get('inputs', [])
        outputs = tx_data.get('outputs', [])
        
        # Calcolo il valore totale in ingresso
        total_input_value = sum(inp['value'] for inp in inputs)
        
        # Calcolo il valore totale in uscita
        total_output_value = sum(out['value'] for out in outputs)
        
        # Calcolo il costo dell'operazione (commissione)
        operation_cost = total_input_value - total_output_value
        
        print(f"\nRiepilogo calcoli:")
        print(f"  Total input value: {total_input_value:.8f} BTC ({len(inputs)} inputs)")
        print(f"  Total output value: {total_output_value:.8f} BTC ({len(outputs)} outputs)")
        print(f"  Operation cost (fee): {operation_cost:.8f} BTC\n")
        
        # Calcolo i Coin Days Destroyed
        coin_days_destroyed = self._calculate_coin_days_destroyed(inputs, tx_data)
        
        # Salvo i valori calcolati in Neo4j per future analisi
        self._save_input_metrics_to_neo4j(inputs)
        
        # Analizzo la distribuzione dell'età degli input
        age_distribution = self._analyze_input_age_distribution(inputs, tx_data)
        
        # Analizzo la distribuzione oraria degli input
        hourly_distribution = self._analyze_input_hourly_distribution(inputs)
        
        # Identifico l'output probabile pagamento e quello di resto
        payment_output, change_output = self._identify_payment_and_change(outputs)
        
        metrics = {
            'total_input_value': total_input_value,
            'total_output_value': total_output_value,
            'operation_cost': operation_cost,
            'coin_days_destroyed': coin_days_destroyed,
            'input_count': len(inputs),
            'output_count': len(outputs),
            'payment_output': payment_output,
            'change_output': change_output,
            'age_distribution': age_distribution,
            'hourly_distribution': hourly_distribution,
            'avg_coin_days_per_input': coin_days_destroyed / len(inputs) if inputs else 0
        }
        
        return metrics
    
    def _calculate_coin_days_destroyed(self, inputs: List[Dict], tx_data: Dict) -> float:
        """
        Calcola i Coin Days Destroyed per gli input.
        
        Coin Days Destroyed = Valore Input * Giorni dall'ultima spesa
        """
        if not tx_data.get('time'):
            return 0.0
        
        tx_time = self._parse_timestamp(tx_data['time'])
        total_coin_days = 0.0
        
        for inp in inputs:
            input_value = inp['value']
            
            # Recupero il tempo di creazione dell'UTXO
            utxo_creation_time = self._get_utxo_creation_time(inp['txid'])
            
            if utxo_creation_time:
                days_held = (tx_time - utxo_creation_time).days
                coin_days = input_value * days_held
                total_coin_days += coin_days
                
                # Aggiungo l'età al singolo input per l'analisi
                inp['days_held'] = days_held
                inp['coin_days'] = coin_days
            else:
                inp['days_held'] = 0
                inp['coin_days'] = 0
        
        return total_coin_days
    
    def _save_input_metrics_to_neo4j(self, inputs: List[Dict]) -> None:
        """
        Salva i valori calcolati degli input nel database Neo4j.
        Questo evita di dover ricalcolare i valori nelle analisi successive.
        
        Args:
            inputs: Lista degli input con i campi value, days_held, coin_days, creation_time
        """
        try:
            from core import query
            
            saved_count = 0
            for inp in inputs:
                # Costruisco l'ID dell'UTXO nel formato source_txid:vout
                utxo_id = f"{inp['txid']}:{inp['vout']}"
                
                # Preparo i parametri da salvare
                params = {
                    'utxo_id': utxo_id,
                    'value': inp.get('value', 0),
                    'days_held': inp.get('days_held'),
                    'coin_days': inp.get('coin_days'),
                    'creation_time': inp.get('creation_time')
                }
                
                # Eseguo l'update solo se dispongo almeno del valore
                if params['value'] is not None and params['value'] > 0:
                    with self.neo4j_connector.driver.session() as session:
                        session.run(query.UPDATE_INPUT_UTXO_WITH_METRICS, **params)
                        saved_count += 1
            
            if saved_count > 0:
                print(f"✓ Salvati {saved_count} valori di input in Neo4j per future analisi")
                
        except Exception as e:
            print(f"Warning: Impossibile salvare i valori in Neo4j: {e}")
            # Non blocco l'analisi se il salvataggio fallisce
    
    def _get_utxo_creation_time(self, source_txid: str) -> Optional[datetime]:
        """Recupera il timestamp di creazione di un UTXO con fallback all'API pubblica."""
        try:
            # Provo prima con Neo4j
            outputs = self.neo4j_connector.get_transaction_outputs(source_txid)
            if outputs and outputs[0].get('time'):
                return self._parse_timestamp(outputs[0]['time'])
            
            # Eseguo il fallback al nodo Bitcoin
            source_tx = self.btc_connector.get_transaction(source_txid)
            if source_tx and source_tx.get('time'):
                return datetime.fromtimestamp(source_tx['time'], tz=timezone.utc)
            
        except Exception:
            pass  # Ignoro l'errore e provo con l'API pubblica
        
        # Eseguo il fallback all'API pubblica
        if self.public_api_connector:
            try:
                # Rispetto il rate limiting
                elapsed = time.time() - self._last_api_call
                if elapsed < self._api_call_delay:
                    time.sleep(self._api_call_delay - elapsed)
                
                self._last_api_call = time.time()
                
                source_tx = self.public_api_connector.get_transaction(source_txid)
                if source_tx and source_tx.get('time'):
                    return datetime.fromtimestamp(source_tx['time'], tz=timezone.utc)
            except Exception as e:
                print(f"Errore nel recupero tempo creazione da API pubblica {source_txid}: {e}")
        
        return None
    
    def _get_utxo_value_from_bitcoin(self, source_txid: str, vout_index: int) -> Optional[float]:
        """
        Recupera il valore di un UTXO dal nodo Bitcoin con fallback all'API pubblica.
        
        Args:
            source_txid: Hash della transazione che ha creato l'UTXO
            vout_index: Indice dell'output
            
        Returns:
            Valore in BTC o None se non trovato
        """
        # Provo prima con il nodo Bitcoin
        try:
            source_tx = self.btc_connector.get_transaction(source_txid)
            if source_tx:
                vout_list = source_tx.get('vout', [])
                if vout_index < len(vout_list):
                    vout = vout_list[vout_index]
                    value = vout.get('value', 0)
                    if value is not None and value > 0:
                        return float(value)
        except Exception as e:
            pass  # Ignoro l'errore e provo con l'API pubblica
        
        # Eseguo il fallback all'API pubblica
        if self.public_api_connector:
            try:
                # Rispetto il rate limiting per evitare di sovraccaricare l'API
                elapsed = time.time() - self._last_api_call
                if elapsed < self._api_call_delay:
                    time.sleep(self._api_call_delay - elapsed)
                
                self._last_api_call = time.time()
                print(f"  -> Recupero da API pubblica...")
                
                source_tx = self.public_api_connector.get_transaction(source_txid)
                if source_tx:
                    vout_list = source_tx.get('vout', [])
                    if vout_index < len(vout_list):
                        vout = vout_list[vout_index]
                        value = vout.get('value', 0)
                        if value is not None:
                            return float(value)
            except Exception as e:
                print(f"  -> Errore nel recupero da API pubblica: {e}")
        
        return None
    
    def _parse_timestamp(self, timestamp) -> datetime:
        """Converte un timestamp in datetime."""
        if isinstance(timestamp, str):
            return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        elif isinstance(timestamp, int):
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        elif isinstance(timestamp, datetime):
            return timestamp
        return datetime.now(timezone.utc)
    
    def _analyze_input_age_distribution(self, inputs: List[Dict], tx_data: Dict) -> Dict[str, int]:
        """
        Analizza la distribuzione dell'età degli input.
        
        Returns:
            Dizionario con le fasce di età e il conteggio degli input
        """
        age_bins = {
            '0-30 giorni': 0,
            '30-90 giorni': 0,
            '90-365 giorni': 0,
            '>1 anno': 0
        }
        
        for inp in inputs:
            days = inp.get('days_held', 0)
            
            if days <= 30:
                age_bins['0-30 giorni'] += 1
            elif days <= 90:
                age_bins['30-90 giorni'] += 1
            elif days <= 365:
                age_bins['90-365 giorni'] += 1
            else:
                age_bins['>1 anno'] += 1
        
        return age_bins
    
    def _analyze_input_hourly_distribution(self, inputs: List[Dict]) -> Dict[int, int]:
        """
        Analizza la distribuzione oraria degli input.
        
        Args:
            inputs: Lista degli input con campo 'creation_time'
            
        Returns:
            Dizionario con l'ora (0-23) e il conteggio degli input
        """
        hourly_bins = {hour: 0 for hour in range(24)}
        
        for inp in inputs:
            creation_time = inp.get('creation_time')
            if creation_time:
                try:
                    # Analizzo la stringa in formato ISO
                    dt = self._parse_timestamp(creation_time)
                    hour = dt.hour
                    hourly_bins[hour] += 1
                except Exception as e:
                    print(f"Errore nel parsing del timestamp per input: {e}")
        
        return hourly_bins
    
    def _identify_payment_and_change(self, outputs: List[Dict]) -> tuple:
        """
        Identifica quale output è probabilmente il pagamento e quale il resto.
        
        Euristica: L'output con valore minore è probabilmente il pagamento,
        l'output con valore maggiore è probabilmente il resto.
        """
        if len(outputs) < 2:
            return (outputs[0] if outputs else None, None)
        
        sorted_outputs = sorted(outputs, key=lambda x: x['value'])
        
        # Considero l'output più piccolo come probabile pagamento
        payment = sorted_outputs[0]
        # Considero l'output più grande come probabile resto
        change = sorted_outputs[-1]
        
        return payment, change