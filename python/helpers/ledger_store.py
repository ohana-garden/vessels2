"""
Ledger Store - TigerBeetle integration for Vessels.

Provides ACID-compliant double-entry bookkeeping with:
- Named accounts (stored in FalkorDB for human-readable references)
- Multi-currency/multi-ledger support
- Two-phase commit transfers
- Balance queries and account lookups

Usage:
    from python.helpers.ledger_store import get_ledger_store, LedgerStore

    store = await get_ledger_store()

    # Create named account
    account_id = await store.create_account("operating_cash", ledger=1)

    # Transfer between accounts
    await store.transfer("operating_cash", "payroll", amount=50000)

    # Check balance
    balance = await store.get_balance("operating_cash")
"""

import os
import uuid
import asyncio
import threading
from typing import Optional, Any
from dataclasses import dataclass
from enum import IntFlag, auto

try:
    import tigerbeetle
    TB_AVAILABLE = True
except ImportError:
    TB_AVAILABLE = False
    tigerbeetle = None


# =============================================================================
# Configuration
# =============================================================================

TIGERBEETLE_HOST = os.environ.get("TIGERBEETLE_HOST", "127.0.0.1")
TIGERBEETLE_PORT = int(os.environ.get("TIGERBEETLE_PORT", "3000"))
TIGERBEETLE_CLUSTER_ID = int(os.environ.get("TIGERBEETLE_CLUSTER_ID", "0"))

# Default ledgers
LEDGER_DEFAULT = 1
LEDGER_USD = 840      # ISO 4217 currency code
LEDGER_EUR = 978
LEDGER_GBP = 826

# Account codes (customize as needed)
CODE_ASSET = 1000
CODE_LIABILITY = 2000
CODE_EQUITY = 3000
CODE_REVENUE = 4000
CODE_EXPENSE = 5000


# =============================================================================
# Data Types
# =============================================================================

class AccountType(IntFlag):
    """Account types for double-entry bookkeeping."""
    ASSET = auto()           # Debit increases, credit decreases
    LIABILITY = auto()       # Credit increases, debit decreases
    EQUITY = auto()          # Credit increases, debit decreases
    REVENUE = auto()         # Credit increases
    EXPENSE = auto()         # Debit increases


@dataclass
class AccountInfo:
    """Human-readable account information."""
    id: int
    name: str
    account_type: AccountType
    ledger: int
    code: int
    description: str = ""

    # Balance fields (populated on lookup)
    credits_posted: int = 0
    debits_posted: int = 0
    credits_pending: int = 0
    debits_pending: int = 0

    @property
    def balance(self) -> int:
        """Net balance (credits - debits for liability/equity/revenue, debits - credits for asset/expense)."""
        if self.account_type in (AccountType.ASSET, AccountType.EXPENSE):
            return self.debits_posted - self.credits_posted
        return self.credits_posted - self.debits_posted

    @property
    def pending_balance(self) -> int:
        """Pending amount not yet posted."""
        if self.account_type in (AccountType.ASSET, AccountType.EXPENSE):
            return self.debits_pending - self.credits_pending
        return self.credits_pending - self.debits_pending


@dataclass
class TransferResult:
    """Result of a transfer operation."""
    id: int
    success: bool
    message: str
    debit_account: str
    credit_account: str
    amount: int
    pending: bool = False


# =============================================================================
# Ledger Store
# =============================================================================

class LedgerStore:
    """
    TigerBeetle ledger with named account support.

    Account names are stored in FalkorDB, IDs in TigerBeetle.
    """

    _instance: Optional["LedgerStore"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._client: Optional[Any] = None
        self._account_registry: dict[str, int] = {}  # name -> id
        self._account_info: dict[int, AccountInfo] = {}  # id -> info
        self._initialized = False

    @classmethod
    async def get_instance(cls) -> "LedgerStore":
        """Get or create singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            if not cls._instance._initialized:
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize TigerBeetle client and load account registry."""
        if not TB_AVAILABLE:
            self._initialized = True
            return

        try:
            address = f"{TIGERBEETLE_HOST}:{TIGERBEETLE_PORT}"
            self._client = tigerbeetle.Client(TIGERBEETLE_CLUSTER_ID, [address])

            # Load account registry from FalkorDB
            await self._load_account_registry()

            self._initialized = True
        except Exception as e:
            # Log but don't fail - allows graceful degradation
            import logging
            logging.getLogger("ledger_store").warning(f"TigerBeetle init failed: {e}")
            self._initialized = True

    async def _load_account_registry(self):
        """Load named accounts from FalkorDB."""
        try:
            from python.helpers.graph_store import get_graph_store
            store = await get_graph_store()

            # Query account registry from graph
            registry = await store.get_setting("ledger_accounts", "ledger")
            if registry:
                for name, info in registry.items():
                    self._account_registry[name] = info["id"]
                    self._account_info[info["id"]] = AccountInfo(
                        id=info["id"],
                        name=name,
                        account_type=AccountType(info.get("type", AccountType.ASSET)),
                        ledger=info.get("ledger", LEDGER_DEFAULT),
                        code=info.get("code", CODE_ASSET),
                        description=info.get("description", "")
                    )
        except Exception:
            pass  # FalkorDB not available, start with empty registry

    async def _save_account_registry(self):
        """Save account registry to FalkorDB."""
        try:
            from python.helpers.graph_store import get_graph_store
            store = await get_graph_store()

            registry = {}
            for name, account_id in self._account_registry.items():
                info = self._account_info.get(account_id)
                if info:
                    registry[name] = {
                        "id": account_id,
                        "type": int(info.account_type),
                        "ledger": info.ledger,
                        "code": info.code,
                        "description": info.description
                    }

            await store.save_setting("ledger_accounts", registry, "ledger")
        except Exception:
            pass  # FalkorDB not available

    @property
    def available(self) -> bool:
        """Check if TigerBeetle is available."""
        return TB_AVAILABLE and self._client is not None

    def _resolve_account(self, name_or_id: str | int) -> int:
        """Resolve account name to ID."""
        if isinstance(name_or_id, int):
            return name_or_id
        if name_or_id in self._account_registry:
            return self._account_registry[name_or_id]
        # Try parsing as int
        try:
            return int(name_or_id)
        except ValueError:
            raise ValueError(f"Unknown account: {name_or_id}")

    # =========================================================================
    # Account Operations
    # =========================================================================

    async def create_account(
        self,
        name: str,
        account_type: AccountType = AccountType.ASSET,
        ledger: int = LEDGER_DEFAULT,
        code: Optional[int] = None,
        description: str = "",
        no_overdraft: bool = False
    ) -> int:
        """
        Create a named account.

        Args:
            name: Human-readable account name (must be unique)
            account_type: ASSET, LIABILITY, EQUITY, REVENUE, or EXPENSE
            ledger: Ledger ID (use for multi-currency)
            code: Account code (auto-assigned based on type if not provided)
            description: Optional description
            no_overdraft: Prevent negative balances

        Returns:
            Account ID
        """
        if not self.available:
            raise RuntimeError("TigerBeetle not available")

        if name in self._account_registry:
            raise ValueError(f"Account '{name}' already exists")

        # Auto-assign code based on type
        if code is None:
            if account_type == AccountType.ASSET:
                code = CODE_ASSET
            elif account_type == AccountType.LIABILITY:
                code = CODE_LIABILITY
            elif account_type == AccountType.EQUITY:
                code = CODE_EQUITY
            elif account_type == AccountType.REVENUE:
                code = CODE_REVENUE
            elif account_type == AccountType.EXPENSE:
                code = CODE_EXPENSE
            else:
                code = 0

        # Build flags
        flags = 0
        if no_overdraft:
            if account_type in (AccountType.ASSET, AccountType.EXPENSE):
                flags |= tigerbeetle.AccountFlags.DEBITS_MUST_NOT_EXCEED_CREDITS
            else:
                flags |= tigerbeetle.AccountFlags.CREDITS_MUST_NOT_EXCEED_DEBITS

        # Create in TigerBeetle
        account_id = uuid.uuid4().int & ((1 << 128) - 1)  # 128-bit ID

        account = tigerbeetle.Account(
            id=account_id,
            debits_pending=0,
            debits_posted=0,
            credits_pending=0,
            credits_posted=0,
            user_data_128=0,
            user_data_64=0,
            user_data_32=0,
            ledger=ledger,
            code=code,
            flags=flags,
            timestamp=0,
        )

        errors = self._client.create_accounts([account])
        if errors:
            raise RuntimeError(f"Failed to create account: {errors[0].result}")

        # Register name
        self._account_registry[name] = account_id
        self._account_info[account_id] = AccountInfo(
            id=account_id,
            name=name,
            account_type=account_type,
            ledger=ledger,
            code=code,
            description=description
        )

        # Persist to FalkorDB
        await self._save_account_registry()

        return account_id

    async def get_account(self, name_or_id: str | int) -> Optional[AccountInfo]:
        """Get account info with current balances."""
        if not self.available:
            return None

        account_id = self._resolve_account(name_or_id)

        # Lookup in TigerBeetle
        accounts = self._client.lookup_accounts([account_id])
        if not accounts:
            return None

        tb_account = accounts[0]

        # Get or create AccountInfo
        if account_id in self._account_info:
            info = self._account_info[account_id]
        else:
            # Unknown account (created directly in TigerBeetle)
            info = AccountInfo(
                id=account_id,
                name=str(account_id),
                account_type=AccountType.ASSET,
                ledger=tb_account.ledger,
                code=tb_account.code
            )

        # Update balances
        info.credits_posted = tb_account.credits_posted
        info.debits_posted = tb_account.debits_posted
        info.credits_pending = tb_account.credits_pending
        info.debits_pending = tb_account.debits_pending

        return info

    async def get_balance(self, name_or_id: str | int) -> int:
        """Get account balance."""
        info = await self.get_account(name_or_id)
        if info is None:
            raise ValueError(f"Account not found: {name_or_id}")
        return info.balance

    async def list_accounts(self) -> list[AccountInfo]:
        """List all named accounts with balances."""
        accounts = []
        for name in self._account_registry:
            info = await self.get_account(name)
            if info:
                accounts.append(info)
        return accounts

    # =========================================================================
    # Transfer Operations
    # =========================================================================

    async def transfer(
        self,
        from_account: str | int,
        to_account: str | int,
        amount: int,
        ledger: int = LEDGER_DEFAULT,
        code: int = 0,
        memo: str = ""
    ) -> TransferResult:
        """
        Transfer amount between accounts (immediate).

        Args:
            from_account: Debit account (source)
            to_account: Credit account (destination)
            amount: Amount in smallest currency unit (cents, etc.)
            ledger: Must match account ledgers
            code: Transfer code for categorization
            memo: Optional memo (stored in user_data)

        Returns:
            TransferResult
        """
        if not self.available:
            return TransferResult(
                id=0, success=False, message="TigerBeetle not available",
                debit_account=str(from_account), credit_account=str(to_account),
                amount=amount
            )

        debit_id = self._resolve_account(from_account)
        credit_id = self._resolve_account(to_account)
        transfer_id = uuid.uuid4().int & ((1 << 128) - 1)

        xfer = tigerbeetle.Transfer(
            id=transfer_id,
            debit_account_id=debit_id,
            credit_account_id=credit_id,
            amount=amount,
            pending_id=0,
            user_data_128=0,
            user_data_64=0,
            user_data_32=0,
            timeout=0,
            ledger=ledger,
            code=code,
            flags=0,
            timestamp=0,
        )

        errors = self._client.create_transfers([xfer])
        if errors:
            return TransferResult(
                id=transfer_id, success=False,
                message=f"Transfer failed: {errors[0].result}",
                debit_account=str(from_account), credit_account=str(to_account),
                amount=amount
            )

        return TransferResult(
            id=transfer_id, success=True,
            message=f"Transfer complete: {from_account} -> {to_account}: {amount}",
            debit_account=str(from_account), credit_account=str(to_account),
            amount=amount
        )

    async def transfer_pending(
        self,
        from_account: str | int,
        to_account: str | int,
        amount: int,
        timeout: int = 0,
        ledger: int = LEDGER_DEFAULT,
        code: int = 0
    ) -> TransferResult:
        """
        Create pending transfer (two-phase commit).

        Must be completed with post_transfer() or cancelled with void_transfer().

        Args:
            timeout: Auto-void after N seconds (0 = no timeout)
        """
        if not self.available:
            return TransferResult(
                id=0, success=False, message="TigerBeetle not available",
                debit_account=str(from_account), credit_account=str(to_account),
                amount=amount, pending=True
            )

        debit_id = self._resolve_account(from_account)
        credit_id = self._resolve_account(to_account)
        transfer_id = uuid.uuid4().int & ((1 << 128) - 1)

        xfer = tigerbeetle.Transfer(
            id=transfer_id,
            debit_account_id=debit_id,
            credit_account_id=credit_id,
            amount=amount,
            pending_id=0,
            user_data_128=0,
            user_data_64=0,
            user_data_32=0,
            timeout=timeout,
            ledger=ledger,
            code=code,
            flags=tigerbeetle.TransferFlags.PENDING,
            timestamp=0,
        )

        errors = self._client.create_transfers([xfer])
        if errors:
            return TransferResult(
                id=transfer_id, success=False,
                message=f"Pending transfer failed: {errors[0].result}",
                debit_account=str(from_account), credit_account=str(to_account),
                amount=amount, pending=True
            )

        return TransferResult(
            id=transfer_id, success=True,
            message=f"Pending transfer created: {transfer_id}",
            debit_account=str(from_account), credit_account=str(to_account),
            amount=amount, pending=True
        )

    async def post_transfer(self, pending_id: int) -> TransferResult:
        """Post (commit) a pending transfer."""
        if not self.available:
            return TransferResult(
                id=0, success=False, message="TigerBeetle not available",
                debit_account="", credit_account="", amount=0
            )

        post_id = uuid.uuid4().int & ((1 << 128) - 1)

        xfer = tigerbeetle.Transfer(
            id=post_id,
            debit_account_id=0,
            credit_account_id=0,
            amount=0,
            pending_id=pending_id,
            user_data_128=0,
            user_data_64=0,
            user_data_32=0,
            timeout=0,
            ledger=0,
            code=0,
            flags=tigerbeetle.TransferFlags.POST_PENDING_TRANSFER,
            timestamp=0,
        )

        errors = self._client.create_transfers([xfer])
        if errors:
            return TransferResult(
                id=post_id, success=False,
                message=f"Post failed: {errors[0].result}",
                debit_account="", credit_account="", amount=0
            )

        return TransferResult(
            id=post_id, success=True,
            message=f"Transfer {pending_id} posted",
            debit_account="", credit_account="", amount=0
        )

    async def void_transfer(self, pending_id: int) -> TransferResult:
        """Void (cancel) a pending transfer."""
        if not self.available:
            return TransferResult(
                id=0, success=False, message="TigerBeetle not available",
                debit_account="", credit_account="", amount=0
            )

        void_id = uuid.uuid4().int & ((1 << 128) - 1)

        xfer = tigerbeetle.Transfer(
            id=void_id,
            debit_account_id=0,
            credit_account_id=0,
            amount=0,
            pending_id=pending_id,
            user_data_128=0,
            user_data_64=0,
            user_data_32=0,
            timeout=0,
            ledger=0,
            code=0,
            flags=tigerbeetle.TransferFlags.VOID_PENDING_TRANSFER,
            timestamp=0,
        )

        errors = self._client.create_transfers([xfer])
        if errors:
            return TransferResult(
                id=void_id, success=False,
                message=f"Void failed: {errors[0].result}",
                debit_account="", credit_account="", amount=0
            )

        return TransferResult(
            id=void_id, success=True,
            message=f"Transfer {pending_id} voided",
            debit_account="", credit_account="", amount=0
        )

    # =========================================================================
    # Batch Operations
    # =========================================================================

    async def transfer_batch(
        self,
        transfers: list[tuple[str | int, str | int, int]]
    ) -> list[TransferResult]:
        """
        Execute multiple transfers atomically.

        Args:
            transfers: List of (from_account, to_account, amount) tuples

        Returns:
            List of TransferResults (all succeed or all fail)
        """
        if not self.available:
            return [TransferResult(
                id=0, success=False, message="TigerBeetle not available",
                debit_account=str(t[0]), credit_account=str(t[1]), amount=t[2]
            ) for t in transfers]

        tb_transfers = []
        results = []

        for from_acc, to_acc, amount in transfers:
            transfer_id = uuid.uuid4().int & ((1 << 128) - 1)
            debit_id = self._resolve_account(from_acc)
            credit_id = self._resolve_account(to_acc)

            tb_transfers.append(tigerbeetle.Transfer(
                id=transfer_id,
                debit_account_id=debit_id,
                credit_account_id=credit_id,
                amount=amount,
                pending_id=0,
                user_data_128=0,
                user_data_64=0,
                user_data_32=0,
                timeout=0,
                ledger=LEDGER_DEFAULT,
                code=0,
                flags=0,
                timestamp=0,
            ))

            results.append(TransferResult(
                id=transfer_id, success=True,
                message="OK",
                debit_account=str(from_acc), credit_account=str(to_acc),
                amount=amount
            ))

        errors = self._client.create_transfers(tb_transfers)
        if errors:
            # Mark failed transfers
            error_indices = {e.index for e in errors}
            for i, err in enumerate(errors):
                results[err.index].success = False
                results[err.index].message = f"Failed: {err.result}"

        return results

    # =========================================================================
    # Chart of Accounts Helpers
    # =========================================================================

    async def setup_chart_of_accounts(self, accounts: dict[str, dict]) -> dict[str, int]:
        """
        Create multiple accounts from a chart definition.

        Args:
            accounts: Dict of name -> {type, ledger, code, description}

        Example:
            await store.setup_chart_of_accounts({
                "cash": {"type": "asset"},
                "accounts_receivable": {"type": "asset"},
                "accounts_payable": {"type": "liability"},
                "revenue": {"type": "revenue"},
                "expenses": {"type": "expense"},
            })
        """
        type_map = {
            "asset": AccountType.ASSET,
            "liability": AccountType.LIABILITY,
            "equity": AccountType.EQUITY,
            "revenue": AccountType.REVENUE,
            "expense": AccountType.EXPENSE,
        }

        created = {}
        for name, config in accounts.items():
            if name in self._account_registry:
                created[name] = self._account_registry[name]
                continue

            acc_type = type_map.get(config.get("type", "asset"), AccountType.ASSET)
            account_id = await self.create_account(
                name=name,
                account_type=acc_type,
                ledger=config.get("ledger", LEDGER_DEFAULT),
                code=config.get("code"),
                description=config.get("description", "")
            )
            created[name] = account_id

        return created


# =============================================================================
# Module-level accessor
# =============================================================================

_store: Optional[LedgerStore] = None


async def get_ledger_store() -> LedgerStore:
    """Get the singleton LedgerStore instance."""
    global _store
    if _store is None:
        _store = await LedgerStore.get_instance()
    return _store


def ledger_available() -> bool:
    """Check if TigerBeetle is available (sync check)."""
    return TB_AVAILABLE
