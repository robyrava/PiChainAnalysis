# --- Query di Creazione ---

CREATE_TX_NODE = """
MERGE (t:Transaction {TXID: $TXID})
SET t.time = $time, t.block_id = $block_id, t.block_height = $block_height,
    t.coinbase = $coinbase, t.input_count = $input_count,
    t.output_count = $output_count, t.input_value = $input_value,
    t.output_value = $output_value
"""

UPDATE_SPENT_UTXO = """
MERGE (u:UTXO {TXID: $utxo_id})
SET u.is_spent = true, u.spending_transaction_hash = $spending_tx_hash
"""

CREATE_INPUT_RELATION = """
MATCH (u:UTXO {TXID: $utxo_id})
MATCH (t:Transaction {TXID: $tx_hash})
MERGE (u)-[:INPUT]->(t)
"""

CREATE_OUTPUT_UTXO_NODE = """
MERGE (u:UTXO {TXID: $utxo_id})
SET u.wallet_address = $wallet_address, u.value = $value, u.is_spent = $is_spent,
    u.time = $time, u.block_id = $block_id
"""

CREATE_OUTPUT_RELATION = """
MATCH (t:Transaction {TXID: $tx_hash})
MATCH (u:UTXO {TXID: $utxo_id})
MERGE (t)-[:OUTPUT]->(u)
"""

# --- Query di Cancellazione ---

DELETE_TRANSACTION = """
MATCH (t:Transaction {TXID: $hash})
DETACH DELETE t
"""

DELETE_UTXO = """
MATCH (u:UTXO {TXID: $utxo_id})
DETACH DELETE u
"""

DELETE_TRANSACTION_AND_UTXOS = """
MATCH (t:Transaction {TXID: $hash})
OPTIONAL MATCH (u:UTXO)-[:INPUT]->(t)
OPTIONAL MATCH (t)-[:OUTPUT]->(o:UTXO)
DETACH DELETE t, u, o
"""