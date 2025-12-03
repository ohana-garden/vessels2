"""Financial Tool - TigerBeetle operations for Vessels.

Thin wrapper around ledger_store for agent tool access.
"""

from python.helpers.tool import Tool, Response
from python.helpers.ledger_store import (
    get_ledger_store, ledger_available, AccountType,
    LEDGER_DEFAULT, LEDGER_USD, LEDGER_EUR, LEDGER_GBP
)


class Financial(Tool):
    """Double-entry bookkeeping operations via TigerBeetle."""

    async def execute(self, operation: str = "", **kwargs) -> Response:
        if not ledger_available():
            return Response(message="TigerBeetle not available", break_loop=False)

        store = await get_ledger_store()
        if not store.available:
            return Response(message="TigerBeetle connection failed", break_loop=False)

        try:
            if operation == "create_account":
                return await self._create_account(store, **kwargs)
            elif operation == "transfer":
                return await self._transfer(store, **kwargs)
            elif operation == "pending_transfer":
                return await self._pending_transfer(store, **kwargs)
            elif operation == "post_transfer":
                return await self._post_transfer(store, **kwargs)
            elif operation == "void_transfer":
                return await self._void_transfer(store, **kwargs)
            elif operation == "get_balance":
                return await self._get_balance(store, **kwargs)
            elif operation == "get_account":
                return await self._get_account(store, **kwargs)
            elif operation == "list_accounts":
                return await self._list_accounts(store, **kwargs)
            elif operation == "setup_chart":
                return await self._setup_chart(store, **kwargs)
            else:
                return Response(
                    message=f"Unknown operation: {operation}.\n\n"
                    "Available operations:\n"
                    "- create_account: Create named account\n"
                    "- transfer: Immediate transfer between accounts\n"
                    "- pending_transfer: Two-phase commit transfer\n"
                    "- post_transfer: Commit pending transfer\n"
                    "- void_transfer: Cancel pending transfer\n"
                    "- get_balance: Get account balance\n"
                    "- get_account: Get full account details\n"
                    "- list_accounts: List all named accounts\n"
                    "- setup_chart: Create chart of accounts",
                    break_loop=False
                )
        except Exception as e:
            return Response(message=f"Financial error: {e}", break_loop=False)

    async def _create_account(self, store, name: str = "", account_type: str = "asset",
                              ledger: int = LEDGER_DEFAULT, code: int = None,
                              description: str = "", no_overdraft: bool = False, **kwargs) -> Response:
        if not name:
            return Response(message="Account name required", break_loop=False)

        type_map = {
            "asset": AccountType.ASSET,
            "liability": AccountType.LIABILITY,
            "equity": AccountType.EQUITY,
            "revenue": AccountType.REVENUE,
            "expense": AccountType.EXPENSE,
        }
        acc_type = type_map.get(account_type.lower(), AccountType.ASSET)

        account_id = await store.create_account(
            name=name,
            account_type=acc_type,
            ledger=ledger,
            code=code,
            description=description,
            no_overdraft=no_overdraft
        )

        return Response(
            message=f"Account created.\n  Name: {name}\n  ID: {account_id}\n  Type: {account_type}\n  Ledger: {ledger}",
            break_loop=False
        )

    async def _transfer(self, store, from_account: str = "", to_account: str = "",
                        amount: int = 0, ledger: int = LEDGER_DEFAULT, code: int = 0, **kwargs) -> Response:
        if not from_account or not to_account:
            return Response(message="from_account and to_account required", break_loop=False)
        if amount <= 0:
            return Response(message="amount must be positive", break_loop=False)

        result = await store.transfer(from_account, to_account, amount, ledger, code)

        if result.success:
            return Response(message=result.message, break_loop=False)
        return Response(message=f"Transfer failed: {result.message}", break_loop=False)

    async def _pending_transfer(self, store, from_account: str = "", to_account: str = "",
                                amount: int = 0, timeout: int = 0, ledger: int = LEDGER_DEFAULT,
                                code: int = 0, **kwargs) -> Response:
        if not from_account or not to_account:
            return Response(message="from_account and to_account required", break_loop=False)
        if amount <= 0:
            return Response(message="amount must be positive", break_loop=False)

        result = await store.transfer_pending(from_account, to_account, amount, timeout, ledger, code)

        if result.success:
            return Response(
                message=f"Pending transfer created.\n  ID: {result.id}\n  Use post_transfer or void_transfer to complete.",
                break_loop=False
            )
        return Response(message=f"Pending transfer failed: {result.message}", break_loop=False)

    async def _post_transfer(self, store, pending_id: int = 0, **kwargs) -> Response:
        if not pending_id:
            return Response(message="pending_id required", break_loop=False)

        result = await store.post_transfer(pending_id)
        return Response(message=result.message, break_loop=False)

    async def _void_transfer(self, store, pending_id: int = 0, **kwargs) -> Response:
        if not pending_id:
            return Response(message="pending_id required", break_loop=False)

        result = await store.void_transfer(pending_id)
        return Response(message=result.message, break_loop=False)

    async def _get_balance(self, store, account: str = "", **kwargs) -> Response:
        if not account:
            return Response(message="account name or ID required", break_loop=False)

        try:
            balance = await store.get_balance(account)
            return Response(message=f"Balance for {account}: {balance}", break_loop=False)
        except ValueError as e:
            return Response(message=str(e), break_loop=False)

    async def _get_account(self, store, account: str = "", **kwargs) -> Response:
        if not account:
            return Response(message="account name or ID required", break_loop=False)

        info = await store.get_account(account)
        if not info:
            return Response(message=f"Account not found: {account}", break_loop=False)

        return Response(
            message=f"Account: {info.name}\n"
                    f"  ID: {info.id}\n"
                    f"  Type: {info.account_type.name}\n"
                    f"  Ledger: {info.ledger}\n"
                    f"  Code: {info.code}\n"
                    f"  Description: {info.description}\n"
                    f"  Credits Posted: {info.credits_posted}\n"
                    f"  Debits Posted: {info.debits_posted}\n"
                    f"  Balance: {info.balance}\n"
                    f"  Pending: +{info.credits_pending} -{info.debits_pending}",
            break_loop=False
        )

    async def _list_accounts(self, store, **kwargs) -> Response:
        accounts = await store.list_accounts()
        if not accounts:
            return Response(message="No named accounts found", break_loop=False)

        lines = ["Named Accounts:"]
        for acc in accounts:
            lines.append(f"  {acc.name}: {acc.balance} ({acc.account_type.name})")

        return Response(message="\n".join(lines), break_loop=False)

    async def _setup_chart(self, store, accounts: dict = None, **kwargs) -> Response:
        """Setup chart of accounts from dict."""
        if not accounts:
            # Default basic chart
            accounts = {
                "cash": {"type": "asset", "description": "Cash and bank accounts"},
                "accounts_receivable": {"type": "asset", "description": "Money owed to us"},
                "accounts_payable": {"type": "liability", "description": "Money we owe"},
                "equity": {"type": "equity", "description": "Owner's equity"},
                "revenue": {"type": "revenue", "description": "Income"},
                "expenses": {"type": "expense", "description": "Operating expenses"},
            }

        created = await store.setup_chart_of_accounts(accounts)

        lines = ["Chart of accounts created:"]
        for name, account_id in created.items():
            lines.append(f"  {name}: {account_id}")

        return Response(message="\n".join(lines), break_loop=False)
