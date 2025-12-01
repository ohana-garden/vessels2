# Problem
Manage financial transactions with double-entry bookkeeping using TigerBeetle

# Solution
TigerBeetle is a high-performance financial transactions database. Use the Python wrapper for all operations.

## Prerequisites
Ensure TigerBeetle server is running (default: localhost:3000).

## Usage

### 1. Create Accounts
```python
python3 /vessels/instruments/default/tigerbeetle/tigerbeetle.py create_account \
    --id <account_id> \
    --ledger <ledger_id> \
    --code <account_code>
```

### 2. Create Transfer
```python
python3 /vessels/instruments/default/tigerbeetle/tigerbeetle.py transfer \
    --debit-account <debit_id> \
    --credit-account <credit_id> \
    --amount <amount> \
    --ledger <ledger_id> \
    --code <transfer_code>
```

### 3. Lookup Account Balance
```python
python3 /vessels/instruments/default/tigerbeetle/tigerbeetle.py lookup_account --id <account_id>
```

### 4. Two-Phase Transfer (Pending)
```python
python3 /vessels/instruments/default/tigerbeetle/tigerbeetle.py pending_transfer \
    --id <transfer_id> \
    --debit-account <debit_id> \
    --credit-account <credit_id> \
    --amount <amount> \
    --ledger <ledger_id>
```

### 5. Post Pending Transfer
```python
python3 /vessels/instruments/default/tigerbeetle/tigerbeetle.py post_transfer --id <transfer_id>
```

### 6. Void Pending Transfer
```python
python3 /vessels/instruments/default/tigerbeetle/tigerbeetle.py void_transfer --id <transfer_id>
```

## Account Flags
- `linked`: Link multiple accounts atomically
- `debits_must_not_exceed_credits`: Prevent overdrafts
- `credits_must_not_exceed_debits`: For liability accounts

## Transfer Flags
- `linked`: Link multiple transfers atomically
- `pending`: Create two-phase pending transfer
- `post_pending_transfer`: Post a pending transfer
- `void_pending_transfer`: Void a pending transfer

## Notes
- All amounts are in the smallest unit (e.g., cents)
- Account IDs and Transfer IDs are 128-bit UUIDs
- Ledger IDs group related accounts
- Code is a user-defined category identifier
