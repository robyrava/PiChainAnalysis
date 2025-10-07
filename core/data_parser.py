from datetime import datetime, timezone

class DataParser:
    @staticmethod
    def parse_transaction(raw_tx: dict, total_input_value: float, block_height: int) -> dict:
        is_coinbase = 'coinbase' in raw_tx['vin'][0]
        return {
            'TXID': raw_tx['txid'],
            'time': datetime.fromtimestamp(raw_tx['time'], tz=timezone.utc).isoformat(),
            'block_id': raw_tx.get('blockhash', 'Mempool'),
            'block_height': block_height,
            'coinbase': is_coinbase,
            'input_count': len(raw_tx['vin']),
            'output_count': len(raw_tx['vout']),
            'input_value': total_input_value,
            'output_value': sum(float(vout['value']) for vout in raw_tx['vout'])
        }

    @staticmethod
    def parse_outputs(raw_tx: dict) -> list:
        outputs = []
        for vout in raw_tx['vout']:
            script_pub_key = vout.get('scriptPubKey', {})
            addresses = script_pub_key.get('addresses', [script_pub_key.get('address')])
            recipient = addresses[0] if addresses and addresses[0] else "unknown"
            outputs.append({
                'transaction_hash': raw_tx['txid'],
                'index': vout['n'],
                'wallet_address': recipient,
                'value': float(vout['value']),
                'is_spent': False,
                'time': datetime.fromtimestamp(raw_tx.get('time', 0), tz=timezone.utc).isoformat(),
                'block_id': raw_tx.get('blockhash', 'Mempool')
            })
        return outputs

    @staticmethod
    def parse_input(source_vout: dict, spending_tx_hash: str) -> dict:
        script_pub_key = source_vout.get('scriptPubKey', {})
        addresses = script_pub_key.get('addresses', [script_pub_key.get('address')])
        recipient = addresses[0] if addresses and addresses[0] else "unknown"
        return {
            'transaction_hash': source_vout['txid_creator'],
            'index': source_vout['n'],
            'wallet_address': recipient,
            'value': float(source_vout['value']),
            'spending_transaction_hash': spending_tx_hash
        }