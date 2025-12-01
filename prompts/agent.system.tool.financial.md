## Financial management tool:
double-entry bookkeeping with TigerBeetle + Graphiti
accounts transfers balances two-phase commits
all amounts in smallest unit (cents)

### create_account
create new financial account
- ledger: group related accounts (required)
- code: category identifier (required)
- account_type: asset|liability|equity|revenue|expense
- no_overdraft: prevent negative balance
~~~json
{
    "thoughts": [
        "Creating a new asset account for the user wallet"
    ],
    "headline": "Creating user wallet account",
    "tool_name": "financial",
    "tool_args": {
        "operation": "create_account",
        "name": "User Wallet",
        "ledger": 1,
        "code": 100,
        "account_type": "asset",
        "owner": "user_123",
        "description": "Main user wallet",
        "no_overdraft": true
    }
}
~~~

### transfer
move funds between accounts (immediate)
~~~json
{
    "thoughts": [
        "Transferring 1000 cents from wallet to merchant"
    ],
    "headline": "Processing payment transfer",
    "tool_name": "financial",
    "tool_args": {
        "operation": "transfer",
        "debit_account": 12345,
        "credit_account": 67890,
        "amount": 1000,
        "ledger": 1,
        "code": 1,
        "reason": "Payment for order #123"
    }
}
~~~

### pending_transfer
two-phase transfer (hold funds)
~~~json
{
    "thoughts": [
        "Creating pending transfer for authorization"
    ],
    "headline": "Holding funds for authorization",
    "tool_name": "financial",
    "tool_args": {
        "operation": "pending_transfer",
        "debit_account": 12345,
        "credit_account": 67890,
        "amount": 5000,
        "ledger": 1,
        "timeout": 3600,
        "reason": "Pre-authorization for hotel"
    }
}
~~~

### post_transfer
complete a pending transfer
~~~json
{
    "thoughts": [
        "Posting the pending authorization"
    ],
    "headline": "Completing pending transfer",
    "tool_name": "financial",
    "tool_args": {
        "operation": "post_transfer",
        "pending_id": 98765432
    }
}
~~~

### void_transfer
cancel a pending transfer
~~~json
{
    "thoughts": [
        "Voiding the hold on funds"
    ],
    "headline": "Voiding pending transfer",
    "tool_name": "financial",
    "tool_args": {
        "operation": "void_transfer",
        "pending_id": 98765432
    }
}
~~~

### get_balance
check account balance
~~~json
{
    "thoughts": [
        "Checking the current balance"
    ],
    "headline": "Getting account balance",
    "tool_name": "financial",
    "tool_args": {
        "operation": "get_balance",
        "account_id": 12345
    }
}
~~~

### get_account
get account with context and balance
~~~json
{
    "thoughts": [
        "Getting full account details"
    ],
    "headline": "Retrieving account information",
    "tool_name": "financial",
    "tool_args": {
        "operation": "get_account",
        "account_id": 12345
    }
}
~~~

### search_transfers
search transfers by reason or context
~~~json
{
    "thoughts": [
        "Finding all hotel-related transfers"
    ],
    "headline": "Searching transfers",
    "tool_name": "financial",
    "tool_args": {
        "operation": "search_transfers",
        "query": "hotel authorization",
        "limit": 10
    }
}
~~~

### get_history
get transfer history for account
~~~json
{
    "thoughts": [
        "Getting transaction history"
    ],
    "headline": "Retrieving transfer history",
    "tool_name": "financial",
    "tool_args": {
        "operation": "get_history",
        "account_id": 12345,
        "limit": 50
    }
}
~~~

### find_accounts
find accounts by owner entity
~~~json
{
    "thoughts": [
        "Finding all accounts for this user"
    ],
    "headline": "Finding user accounts",
    "tool_name": "financial",
    "tool_args": {
        "operation": "find_accounts",
        "owner": "user_123"
    }
}
~~~
