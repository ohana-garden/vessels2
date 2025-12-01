"""
Financial Tool - TigerBeetle + Graphiti Operations for Vessels

Provides double-entry bookkeeping operations with full context tracking.
"""

from python.helpers.tool import Tool, Response
from python.helpers.financial import (
    get_financial_store,
    AccountType,
)


class Financial(Tool):
    """Financial operations tool for account and transfer management."""

    async def execute(
        self,
        operation: str = "",
        # Account operations
        name: str = "",
        ledger: int = 1,
        code: int = 0,
        account_type: str = "asset",
        owner: str = "",
        description: str = "",
        no_overdraft: bool = False,
        # Transfer operations
        debit_account: int = 0,
        credit_account: int = 0,
        amount: int = 0,
        reason: str = "",
        # Query operations
        account_id: int = 0,
        transfer_id: int = 0,
        query: str = "",
        limit: int = 10,
        # Two-phase operations
        timeout: int = 0,
        pending_id: int = 0,
        **kwargs
    ):
        store = await get_financial_store()

        try:
            if operation == "create_account":
                account = await store.create_account(
                    name=name,
                    ledger=ledger,
                    code=code,
                    account_type=AccountType(account_type),
                    owner_entity=owner if owner else None,
                    description=description,
                    no_overdraft=no_overdraft,
                )
                return Response(
                    message=f"Account created: {name}\nID: {account.tigerbeetle_id}\nLedger: {ledger}, Code: {code}",
                    break_loop=False
                )

            elif operation == "transfer":
                transfer = await store.transfer(
                    debit_account_id=debit_account,
                    credit_account_id=credit_account,
                    amount=amount,
                    ledger=ledger,
                    code=code,
                    reason=reason,
                    initiated_by=self.agent.agent_name,
                )
                return Response(
                    message=f"Transfer completed\nID: {transfer.tigerbeetle_id}\nAmount: {amount}\nFrom: {debit_account} -> To: {credit_account}",
                    break_loop=False
                )

            elif operation == "pending_transfer":
                transfer = await store.pending_transfer(
                    debit_account_id=debit_account,
                    credit_account_id=credit_account,
                    amount=amount,
                    ledger=ledger,
                    code=code,
                    timeout=timeout,
                    reason=reason,
                    initiated_by=self.agent.agent_name,
                )
                return Response(
                    message=f"Pending transfer created\nID: {transfer.tigerbeetle_id}\nUse post_transfer or void_transfer to complete",
                    break_loop=False
                )

            elif operation == "post_transfer":
                await store.post_pending_transfer(pending_id)
                return Response(
                    message=f"Transfer {pending_id} posted successfully",
                    break_loop=False
                )

            elif operation == "void_transfer":
                await store.void_pending_transfer(pending_id)
                return Response(
                    message=f"Transfer {pending_id} voided successfully",
                    break_loop=False
                )

            elif operation == "get_balance":
                balance = await store.get_balance(account_id)
                if balance:
                    return Response(
                        message=(
                            f"Account {account_id} Balance:\n"
                            f"  Available: {balance['available']}\n"
                            f"  Credits Posted: {balance['credits_posted']}\n"
                            f"  Debits Posted: {balance['debits_posted']}\n"
                            f"  Credits Pending: {balance['credits_pending']}\n"
                            f"  Debits Pending: {balance['debits_pending']}"
                        ),
                        break_loop=False
                    )
                return Response(message=f"Account {account_id} not found", break_loop=False)

            elif operation == "get_account":
                account = await store.get_account(account_id)
                if account:
                    import json
                    return Response(
                        message=f"Account {account_id}:\n{json.dumps(account, indent=2)}",
                        break_loop=False
                    )
                return Response(message=f"Account {account_id} not found", break_loop=False)

            elif operation == "search_transfers":
                transfers = await store.search_transfers(query=query, limit=limit)
                if transfers:
                    import json
                    return Response(
                        message=f"Found {len(transfers)} transfers:\n{json.dumps(transfers, indent=2)}",
                        break_loop=False
                    )
                return Response(message="No transfers found", break_loop=False)

            elif operation == "get_history":
                history = await store.get_transfer_history(account_id=account_id, limit=limit)
                if history:
                    import json
                    return Response(
                        message=f"Transfer history for {account_id}:\n{json.dumps(history, indent=2)}",
                        break_loop=False
                    )
                return Response(message=f"No transfer history for {account_id}", break_loop=False)

            elif operation == "find_accounts":
                accounts = await store.find_accounts_by_owner(owner)
                if accounts:
                    import json
                    return Response(
                        message=f"Accounts for {owner}:\n{json.dumps(accounts, indent=2)}",
                        break_loop=False
                    )
                return Response(message=f"No accounts found for {owner}", break_loop=False)

            else:
                return Response(
                    message=f"Unknown operation: {operation}. Valid: create_account, transfer, pending_transfer, post_transfer, void_transfer, get_balance, get_account, search_transfers, get_history, find_accounts",
                    break_loop=False
                )

        except Exception as e:
            return Response(message=f"Financial operation failed: {str(e)}", break_loop=False)
