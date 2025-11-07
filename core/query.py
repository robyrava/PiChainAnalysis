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

# --- Query per Analisi Peeling Chain ---

GET_TRANSACTION_DETAILS = """
MATCH (t:Transaction {TXID: $tx_hash})
RETURN t.TXID as txid, t.time as time, t.block_id as block_id, 
       t.block_height as block_height, t.coinbase as coinbase,
       t.input_count as input_count, t.output_count as output_count,
       t.input_value as input_value, t.output_value as output_value
"""

GET_TRANSACTION_OUTPUTS = """
MATCH (t:Transaction {TXID: $tx_hash})-[:OUTPUT]->(u:UTXO)
RETURN u.TXID as utxo_id, u.wallet_address as address, u.value as value,
       u.is_spent as is_spent, u.spending_transaction_hash as spending_tx_hash,
       u.time as time, u.block_id as block_id
ORDER BY u.TXID
"""

GET_TRANSACTION_INPUTS = """
MATCH (u:UTXO)-[:INPUT]->(t:Transaction {TXID: $tx_hash})
RETURN u.TXID as utxo_id, u.wallet_address as address, u.value as value,
       u.is_spent as is_spent, u.time as time, u.block_id as block_id,
       u.days_held as days_held, u.coin_days as coin_days, 
       u.creation_time as creation_time
ORDER BY u.TXID
"""

FIND_SPENDING_TRANSACTION = """
MATCH (u:UTXO {TXID: $utxo_id})
WHERE u.is_spent = true AND u.spending_transaction_hash IS NOT NULL
RETURN u.spending_transaction_hash as spending_tx_hash
"""

GET_FULL_TRANSACTION_DATA = """
MATCH (t:Transaction {TXID: $tx_hash})
OPTIONAL MATCH (input_utxo:UTXO)-[:INPUT]->(t)
OPTIONAL MATCH (t)-[:OUTPUT]->(output_utxo:UTXO)
RETURN t,
       collect(DISTINCT {
           utxo_id: input_utxo.TXID,
           address: input_utxo.wallet_address,
           value: input_utxo.value,
           days_held: input_utxo.days_held,
           coin_days: input_utxo.coin_days,
           creation_time: input_utxo.creation_time
       }) as inputs,
       collect(DISTINCT {
           utxo_id: output_utxo.TXID,
           address: output_utxo.wallet_address,
           value: output_utxo.value,
           is_spent: output_utxo.is_spent,
           spending_tx_hash: output_utxo.spending_transaction_hash
       }) as outputs
"""

CHECK_TRANSACTION_EXISTS = """
MATCH (t:Transaction {TXID: $tx_hash})
RETURN count(t) > 0 as exists
"""

# --- Query per Fan-In Analysis ---

UPDATE_INPUT_UTXO_WITH_METRICS = """
MATCH (u:UTXO {TXID: $utxo_id})
SET u.value = $value,
    u.days_held = $days_held,
    u.coin_days = $coin_days,
    u.creation_time = $creation_time
"""