"""Financial Tool - TigerBeetle operations for Vessels."""

import os
import uuid
from python.helpers.tool import Tool, Response

try:
    import tigerbeetle
    TB_AVAILABLE = True
except ImportError:
    TB_AVAILABLE = False
    tigerbeetle = None


def _get_client():
    """Get TigerBeetle client."""
    if not TB_AVAILABLE:
        return None
    host = os.environ.get("TIGERBEETLE_HOST", "127.0.0.1")
    port = int(os.environ.get("TIGERBEETLE_PORT", "3000"))
    cluster_id = int(os.environ.get("TIGERBEETLE_CLUSTER_ID", "0"))
    return tigerbeetle.Client(cluster_id, [f"{host}:{port}"])


class Financial(Tool):
    """Double-entry bookkeeping operations."""

    async def execute(self, operation: str = "", **kwargs) -> Response:
        client = _get_client()
        if not client:
            return Response(message="TigerBeetle not available", break_loop=False)

        try:
            if operation == "create_account":
                return self._create_account(client, **kwargs)
            elif operation == "transfer":
                return self._transfer(client, **kwargs)
            elif operation == "pending_transfer":
                return self._pending_transfer(client, **kwargs)
            elif operation == "post_transfer":
                return self._post_transfer(client, **kwargs)
            elif operation == "void_transfer":
                return self._void_transfer(client, **kwargs)
            elif operation == "get_balance":
                return self._get_balance(client, **kwargs)
            elif operation == "get_account":
                return self._get_account(client, **kwargs)
            else:
                return Response(
                    message=f"Unknown operation: {operation}. Use: create_account, transfer, pending_transfer, post_transfer, void_transfer, get_balance, get_account",
                    break_loop=False
                )
        except Exception as e:
            return Response(message=f"Financial error: {e}", break_loop=False)

    def _create_account(self, client, ledger: int = 1, code: int = 0,
                        account_type: str = "asset", no_overdraft: bool = False, **kwargs) -> Response:
        account_id = uuid.uuid4().int
        flags = 0
        if no_overdraft:
            flags |= tigerbeetle.AccountFlags.DEBITS_MUST_NOT_EXCEED_CREDITS
        if account_type == "liability":
            flags |= tigerbeetle.AccountFlags.CREDITS_MUST_NOT_EXCEED_DEBITS

        account = tigerbeetle.Account(
            id=account_id, debits_pending=0, debits_posted=0,
            credits_pending=0, credits_posted=0, user_data_128=0,
            user_data_64=0, user_data_32=0, ledger=ledger, code=code,
            flags=flags, timestamp=0,
        )
        errors = client.create_accounts([account])
        if errors:
            return Response(message=f"Create failed: {errors[0].result}", break_loop=False)
        return Response(message=f"Account created. ID: {account_id}", break_loop=False)

    def _transfer(self, client, debit_account: int = 0, credit_account: int = 0,
                  amount: int = 0, ledger: int = 1, code: int = 0, **kwargs) -> Response:
        transfer_id = uuid.uuid4().int
        xfer = tigerbeetle.Transfer(
            id=transfer_id, debit_account_id=debit_account,
            credit_account_id=credit_account, amount=amount,
            pending_id=0, user_data_128=0, user_data_64=0, user_data_32=0,
            timeout=0, ledger=ledger, code=code, flags=0, timestamp=0,
        )
        errors = client.create_transfers([xfer])
        if errors:
            return Response(message=f"Transfer failed: {errors[0].result}", break_loop=False)
        return Response(
            message=f"Transfer complete. ID: {transfer_id}\n{debit_account} -> {credit_account}: {amount}",
            break_loop=False
        )

    def _pending_transfer(self, client, debit_account: int = 0, credit_account: int = 0,
                          amount: int = 0, ledger: int = 1, code: int = 0,
                          timeout: int = 0, **kwargs) -> Response:
        transfer_id = uuid.uuid4().int
        xfer = tigerbeetle.Transfer(
            id=transfer_id, debit_account_id=debit_account,
            credit_account_id=credit_account, amount=amount,
            pending_id=0, user_data_128=0, user_data_64=0, user_data_32=0,
            timeout=timeout, ledger=ledger, code=code,
            flags=tigerbeetle.TransferFlags.PENDING, timestamp=0,
        )
        errors = client.create_transfers([xfer])
        if errors:
            return Response(message=f"Pending transfer failed: {errors[0].result}", break_loop=False)
        return Response(
            message=f"Pending transfer created. ID: {transfer_id}\nUse post_transfer or void_transfer to complete.",
            break_loop=False
        )

    def _post_transfer(self, client, pending_id: int = 0, **kwargs) -> Response:
        post_id = uuid.uuid4().int
        xfer = tigerbeetle.Transfer(
            id=post_id, debit_account_id=0, credit_account_id=0, amount=0,
            pending_id=pending_id, user_data_128=0, user_data_64=0, user_data_32=0,
            timeout=0, ledger=0, code=0,
            flags=tigerbeetle.TransferFlags.POST_PENDING_TRANSFER, timestamp=0,
        )
        errors = client.create_transfers([xfer])
        if errors:
            return Response(message=f"Post failed: {errors[0].result}", break_loop=False)
        return Response(message=f"Transfer {pending_id} posted.", break_loop=False)

    def _void_transfer(self, client, pending_id: int = 0, **kwargs) -> Response:
        void_id = uuid.uuid4().int
        xfer = tigerbeetle.Transfer(
            id=void_id, debit_account_id=0, credit_account_id=0, amount=0,
            pending_id=pending_id, user_data_128=0, user_data_64=0, user_data_32=0,
            timeout=0, ledger=0, code=0,
            flags=tigerbeetle.TransferFlags.VOID_PENDING_TRANSFER, timestamp=0,
        )
        errors = client.create_transfers([xfer])
        if errors:
            return Response(message=f"Void failed: {errors[0].result}", break_loop=False)
        return Response(message=f"Transfer {pending_id} voided.", break_loop=False)

    def _get_balance(self, client, account_id: int = 0, **kwargs) -> Response:
        accounts = client.lookup_accounts([account_id])
        if not accounts:
            return Response(message=f"Account {account_id} not found", break_loop=False)
        acc = accounts[0]
        return Response(
            message=f"Account {account_id}:\n  Credits: {acc.credits_posted}\n  Debits: {acc.debits_posted}\n  Balance: {acc.credits_posted - acc.debits_posted}\n  Pending: +{acc.credits_pending} -{acc.debits_pending}",
            break_loop=False
        )

    def _get_account(self, client, account_id: int = 0, **kwargs) -> Response:
        accounts = client.lookup_accounts([account_id])
        if not accounts:
            return Response(message=f"Account {account_id} not found", break_loop=False)
        acc = accounts[0]
        return Response(
            message=f"Account {account_id}:\n  Ledger: {acc.ledger}\n  Code: {acc.code}\n  Credits Posted: {acc.credits_posted}\n  Debits Posted: {acc.debits_posted}\n  Credits Pending: {acc.credits_pending}\n  Debits Pending: {acc.debits_pending}\n  Balance: {acc.credits_posted - acc.debits_posted}",
            break_loop=False
        )
