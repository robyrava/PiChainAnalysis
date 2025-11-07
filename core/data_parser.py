# core/data_parser.py

from datetime import datetime, timezone

class DataParser:
    """
    Classe responsabile della trasformazione dei dati grezzi ricevuti dal
    nodo Bitcoin (via RPC) nel formato strutturato richiesto dal Neo4jConnector.
    """

    @staticmethod
    def parse_transaction(raw_tx: dict, total_input_value: float, block_height: int) -> dict:
        """
        Estrae e formatta le informazioni principali di una transazione.

        Args:
            raw_tx: Il dizionario JSON grezzo della transazione da getrawtransaction.
            total_input_value: Il valore totale degli input, calcolato separatamente.

        Returns:
            Un dizionario formattato con le informazioni della transazione.
        """
        # Controllo se è una transazione coinbase (non ha input standard)
        is_coinbase = 'coinbase' in raw_tx['vin'][0]

        return {
            'TXID': raw_tx['txid'],
            # Converte il timestamp unix in una stringa ISO 8601 leggibile
            'time': datetime.fromtimestamp(raw_tx['time'], tz=timezone.utc).isoformat(),
            'block_id': raw_tx.get('blockhash', 'Mempool'), # Se non è in un blocco, è in mempool
            'block_height': block_height,
            'coinbase': is_coinbase,
            'input_count': len(raw_tx['vin']),
            'output_count': len(raw_tx['vout']),
            'input_value': total_input_value,
            'output_value': sum(float(vout['value']) for vout in raw_tx['vout'])
        }

    @staticmethod
    def parse_outputs(raw_tx: dict) -> list:
        """
        Estrae e formatta tutti gli output (UTXO creati) di una transazione.

        Returns:
            Una lista di dizionari, ognuno rappresentante un UTXO di output.
        """
        outputs = []
        for vout in raw_tx['vout']:
            # Estrae il primo indirizzo disponibile, gestendo vari tipi di script
            recipient = "unknown"
            script_pub_key = vout.get('scriptPubKey', {})
            # Cerca prima 'addresses' (una lista), poi 'address' (una stringa), altrimenti 'unknown'
            addresses = script_pub_key.get('addresses', [script_pub_key.get('address')])
            recipient = addresses[0] if addresses[0] else "unknown"

            outputs.append({
                'transaction_hash': raw_tx['txid'],
                'index': vout['n'],
                'wallet_address': recipient,
                'value': float(vout['value']),
                'is_spent': False, # Di default un output non è speso. Lo stato cambierà quando diventerà un input.
                'time': datetime.fromtimestamp(raw_tx.get('time', 0), tz=timezone.utc).isoformat(),
                'block_id': raw_tx.get('blockhash', 'Mempool')
            })
        return outputs

    @staticmethod
    def parse_input(source_vout: dict, spending_tx_hash: str) -> dict:
        """
        Formatta un singolo input usando l'output della transazione di origine.

        Args:
            source_vout: Il vout specifico dalla transazione di origine che viene speso.
            spending_tx_hash: L'hash della transazione che sta spendendo questo UTXO.

        Returns:
            Un dizionario formattato per l'UTXO di input.
        """
        if source_vout is None:
            return {
                'transaction_hash': 'coinbase',
                'index': 0,
                'wallet_address': 'coinbase',
                'value': 0.0,
                'spending_transaction_hash': spending_tx_hash
            }
        
        # Estraggo l'indirizzo del destinatario originale
        script_pub_key = source_vout.get('scriptPubKey', {})
        addresses = script_pub_key.get('addresses', [script_pub_key.get('address')])
        recipient = addresses[0] if addresses[0] else "unknown"

        return {
            # L'hash e l'indice si riferiscono alla transazione che ha creato l'UTXO
            'transaction_hash': source_vout['txid_creator'], # Aggiungeremo questo campo nel manager
            'index': source_vout['n'],
            'wallet_address': recipient,
            'value': float(source_vout['value']),
            'spending_transaction_hash': spending_tx_hash
        }