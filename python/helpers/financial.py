"""
Vessels Financial Helper - TigerBeetle + Graphiti Integration

This module provides a unified financial layer that combines:
- TigerBeetle: Source of truth for account balances and transfers
- Graphiti: Context layer for account metadata, relationships, and audit trails

Architecture:
┌─────────────────────────────────────────────────────────────┐
│                    FinancialStore                           │
├─────────────────────────────────────────────────────────────┤
│  Graphiti (Context)          │  TigerBeetle (Ledger)       │
│  • Account metadata          │  • Account balances         │
│  • Entity relationships      │  • Transfers                │
│  • Transfer audit context    │  • Two-phase commits        │
│  • Temporal history          │  • ACID guarantees          │
└─────────────────────────────────────────────────────────────┘
"""

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from python.helpers.print_style import PrintStyle
from python.helpers.graph_store import GraphStore, get_graph_store

# TigerBeetle imports
try:
    import tigerbeetle
    TIGERBEETLE_AVAILABLE = True
except ImportError:
    TIGERBEETLE_AVAILABLE = False
    tigerbeetle = None


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class FinancialConfig:
    """Configuration for financial store connections."""
    # TigerBeetle settings
    tb_host: str = "127.0.0.1"
    tb_port: int = 3000
    tb_cluster_id: int = 0

    @classmethod
    def from_env(cls) -> "FinancialConfig":
        return cls(
            tb_host=os.getenv("TIGERBEETLE_HOST", "127.0.0.1"),
            tb_port=int(os.getenv("TIGERBEETLE_PORT", "3000")),
            tb_cluster_id=int(os.getenv("TIGERBEETLE_CLUSTER_ID", "0")),
        )


# =============================================================================
# Data Models
# =============================================================================

class AccountType(str, Enum):
    """Standard account types for double-entry bookkeeping."""
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


@dataclass
class AccountEntity:
    """Account with both TigerBeetle ID and Graphiti metadata."""
    tigerbeetle_id: int
    name: str
    account_type: AccountType
    ledger: int
    code: int
    owner_entity: Optional[str] = None  # Graphiti entity ID
    description: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "tigerbeetle_id": self.tigerbeetle_id,
            "name": self.name,
            "account_type": self.account_type.value,
            "ledger": self.ledger,
            "code": self.code,
            "owner_entity": self.owner_entity,
            "description": self.description,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AccountEntity":
        return cls(
            tigerbeetle_id=data["tigerbeetle_id"],
            name=data["name"],
            account_type=AccountType(data["account_type"]),
            ledger=data["ledger"],
            code=data["code"],
            owner_entity=data.get("owner_entity"),
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
        )


@dataclass
class TransferContext:
    """Transfer with TigerBeetle execution and Graphiti context."""
    tigerbeetle_id: int
    debit_account_id: int
    credit_account_id: int
    amount: int
    ledger: int
    code: int
    reason: str = ""
    initiated_by: Optional[str] = None  # Agent or user entity
    related_entities: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    status: str = "completed"  # completed, pending, voided

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "tigerbeetle_id": self.tigerbeetle_id,
            "debit_account_id": self.debit_account_id,
            "credit_account_id": self.credit_account_id,
            "amount": self.amount,
            "ledger": self.ledger,
            "code": self.code,
            "reason": self.reason,
            "initiated_by": self.initiated_by,
            "related_entities": self.related_entities,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "status": self.status,
        }


# =============================================================================
# Financial Store Implementation
# =============================================================================

class FinancialStore:
    """
    Unified financial store combining TigerBeetle and Graphiti.

    TigerBeetle handles the actual financial transactions with ACID guarantees.
    Graphiti stores the context, relationships, and audit trail.
    """

    _instance: Optional["FinancialStore"] = None
    _lock = asyncio.Lock()

    def __init__(self, config: Optional[FinancialConfig] = None):
        self.config = config or FinancialConfig.from_env()
        self._tb_client: Optional[tigerbeetle.Client] = None
        self._graph_store: Optional[GraphStore] = None
        self._initialized = False

    @classmethod
    async def get_instance(cls, config: Optional[FinancialConfig] = None) -> "FinancialStore":
        """Get or create the singleton financial store instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config)
                await cls._instance.initialize()
            return cls._instance

    async def initialize(self) -> None:
        """Initialize connections to TigerBeetle and Graphiti."""
        if self._initialized:
            return

        PrintStyle.standard("Initializing Financial Store (TigerBeetle + Graphiti)...")

        # Initialize Graphiti connection
        self._graph_store = await get_graph_store()

        # Initialize TigerBeetle connection
        if TIGERBEETLE_AVAILABLE:
            try:
                self._tb_client = tigerbeetle.Client(
                    self.config.tb_cluster_id,
                    [f"{self.config.tb_host}:{self.config.tb_port}"]
                )
                PrintStyle.standard("TigerBeetle connected")
            except Exception as e:
                PrintStyle.error(f"TigerBeetle connection failed: {e}")
                self._tb_client = None
        else:
            PrintStyle.hint("TigerBeetle not installed - running in context-only mode")

        self._initialized = True

    def _generate_id(self) -> int:
        """Generate a 128-bit ID for TigerBeetle."""
        return uuid.uuid4().int

    # =========================================================================
    # Account Operations
    # =========================================================================

    async def create_account(
        self,
        name: str,
        ledger: int,
        code: int,
        account_type: AccountType = AccountType.ASSET,
        owner_entity: Optional[str] = None,
        description: str = "",
        no_overdraft: bool = False,
        metadata: Optional[dict] = None,
    ) -> AccountEntity:
        """
        Create an account in both TigerBeetle and Graphiti.

        Returns AccountEntity with both TigerBeetle ID and Graphiti context.
        """
        account_id = self._generate_id()

        # Create in TigerBeetle (source of truth for balance)
        if self._tb_client:
            flags = 0
            if no_overdraft:
                flags |= tigerbeetle.AccountFlags.DEBITS_MUST_NOT_EXCEED_CREDITS
            if account_type == AccountType.LIABILITY:
                flags |= tigerbeetle.AccountFlags.CREDITS_MUST_NOT_EXCEED_DEBITS

            tb_account = tigerbeetle.Account(
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

            errors = self._tb_client.create_accounts([tb_account])
            if errors:
                raise RuntimeError(f"TigerBeetle account creation failed: {errors[0].result}")

        # Create entity in Graphiti (context layer)
        account_entity = AccountEntity(
            tigerbeetle_id=account_id,
            name=name,
            account_type=account_type,
            ledger=ledger,
            code=code,
            owner_entity=owner_entity,
            description=description,
            metadata=metadata or {},
        )

        # Store in Graphiti as an episode
        from graphiti_core.nodes import EpisodeType
        await self._graph_store.graphiti.add_episode(
            name=f"account_{account_id}",
            episode_body=json.dumps(account_entity.to_dict()),
            source=EpisodeType.json,
            reference_time=datetime.now(timezone.utc),
            group_id="financial:accounts",
        )

        PrintStyle.standard(f"Account created: {name} (ID: {account_id})")
        return account_entity

    async def get_account(self, account_id: int) -> Optional[dict]:
        """
        Get account with both balance (TigerBeetle) and context (Graphiti).
        """
        result = {"id": account_id}

        # Get balance from TigerBeetle
        if self._tb_client:
            accounts = self._tb_client.lookup_accounts([account_id])
            if accounts:
                tb_acc = accounts[0]
                result["balance"] = {
                    "debits_pending": tb_acc.debits_pending,
                    "debits_posted": tb_acc.debits_posted,
                    "credits_pending": tb_acc.credits_pending,
                    "credits_posted": tb_acc.credits_posted,
                    "available": tb_acc.credits_posted - tb_acc.debits_posted,
                }

        # Get context from Graphiti
        query = f"""
        MATCH (n:Episode) WHERE n.name = 'account_{account_id}'
        RETURN n.content as content
        """
        graph_result = await self._graph_store._driver.execute_query(query)

        if graph_result and len(graph_result) > 0:
            content = graph_result[0].get("content", "{}")
            context = json.loads(content)
            result["context"] = context

        return result if len(result) > 1 else None

    async def find_accounts_by_owner(self, owner_entity: str) -> list[dict]:
        """Find all accounts owned by an entity."""
        query = """
        MATCH (n:Episode) WHERE n.name STARTS WITH 'account_'
        RETURN n.content as content
        """
        results = await self._graph_store._driver.execute_query(query)

        accounts = []
        for row in results:
            content = json.loads(row.get("content", "{}"))
            if content.get("owner_entity") == owner_entity:
                account_id = content.get("tigerbeetle_id")
                full_account = await self.get_account(account_id)
                if full_account:
                    accounts.append(full_account)

        return accounts

    # =========================================================================
    # Transfer Operations
    # =========================================================================

    async def transfer(
        self,
        debit_account_id: int,
        credit_account_id: int,
        amount: int,
        ledger: int,
        code: int,
        reason: str = "",
        initiated_by: Optional[str] = None,
        related_entities: Optional[list[str]] = None,
        metadata: Optional[dict] = None,
    ) -> TransferContext:
        """
        Execute a transfer in TigerBeetle and record context in Graphiti.
        """
        transfer_id = self._generate_id()

        # Execute in TigerBeetle
        if self._tb_client:
            tb_transfer = tigerbeetle.Transfer(
                id=transfer_id,
                debit_account_id=debit_account_id,
                credit_account_id=credit_account_id,
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

            errors = self._tb_client.create_transfers([tb_transfer])
            if errors:
                raise RuntimeError(f"TigerBeetle transfer failed: {errors[0].result}")

        # Record context in Graphiti
        transfer_context = TransferContext(
            tigerbeetle_id=transfer_id,
            debit_account_id=debit_account_id,
            credit_account_id=credit_account_id,
            amount=amount,
            ledger=ledger,
            code=code,
            reason=reason,
            initiated_by=initiated_by,
            related_entities=related_entities or [],
            metadata=metadata or {},
            status="completed",
        )

        from graphiti_core.nodes import EpisodeType
        await self._graph_store.graphiti.add_episode(
            name=f"transfer_{transfer_id}",
            episode_body=json.dumps(transfer_context.to_dict()),
            source=EpisodeType.json,
            reference_time=datetime.now(timezone.utc),
            group_id="financial:transfers",
        )

        PrintStyle.standard(f"Transfer completed: {amount} from {debit_account_id} to {credit_account_id}")
        return transfer_context

    async def pending_transfer(
        self,
        debit_account_id: int,
        credit_account_id: int,
        amount: int,
        ledger: int,
        code: int = 0,
        timeout: int = 0,
        reason: str = "",
        initiated_by: Optional[str] = None,
    ) -> TransferContext:
        """Create a two-phase pending transfer."""
        transfer_id = self._generate_id()

        if self._tb_client:
            tb_transfer = tigerbeetle.Transfer(
                id=transfer_id,
                debit_account_id=debit_account_id,
                credit_account_id=credit_account_id,
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

            errors = self._tb_client.create_transfers([tb_transfer])
            if errors:
                raise RuntimeError(f"Pending transfer failed: {errors[0].result}")

        transfer_context = TransferContext(
            tigerbeetle_id=transfer_id,
            debit_account_id=debit_account_id,
            credit_account_id=credit_account_id,
            amount=amount,
            ledger=ledger,
            code=code,
            reason=reason,
            initiated_by=initiated_by,
            status="pending",
        )

        from graphiti_core.nodes import EpisodeType
        await self._graph_store.graphiti.add_episode(
            name=f"transfer_{transfer_id}",
            episode_body=json.dumps(transfer_context.to_dict()),
            source=EpisodeType.json,
            reference_time=datetime.now(timezone.utc),
            group_id="financial:transfers",
        )

        return transfer_context

    async def post_pending_transfer(self, pending_id: int) -> bool:
        """Post a pending transfer to complete it."""
        if self._tb_client:
            post_id = self._generate_id()
            tb_transfer = tigerbeetle.Transfer(
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

            errors = self._tb_client.create_transfers([tb_transfer])
            if errors:
                raise RuntimeError(f"Post pending failed: {errors[0].result}")

        # Update status in Graphiti
        await self._update_transfer_status(pending_id, "completed")
        return True

    async def void_pending_transfer(self, pending_id: int) -> bool:
        """Void a pending transfer."""
        if self._tb_client:
            void_id = self._generate_id()
            tb_transfer = tigerbeetle.Transfer(
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

            errors = self._tb_client.create_transfers([tb_transfer])
            if errors:
                raise RuntimeError(f"Void pending failed: {errors[0].result}")

        await self._update_transfer_status(pending_id, "voided")
        return True

    async def _update_transfer_status(self, transfer_id: int, status: str) -> None:
        """Update transfer status in Graphiti."""
        query = f"""
        MATCH (n:Episode) WHERE n.name = 'transfer_{transfer_id}'
        RETURN n.content as content
        """
        result = await self._graph_store._driver.execute_query(query)

        if result and len(result) > 0:
            content = json.loads(result[0].get("content", "{}"))
            content["status"] = status

            # Delete old and create new (upsert)
            delete_query = f"""
            MATCH (n:Episode) WHERE n.name = 'transfer_{transfer_id}'
            DETACH DELETE n
            """
            await self._graph_store._driver.execute_query(delete_query)

            from graphiti_core.nodes import EpisodeType
            await self._graph_store.graphiti.add_episode(
                name=f"transfer_{transfer_id}",
                episode_body=json.dumps(content),
                source=EpisodeType.json,
                reference_time=datetime.now(timezone.utc),
                group_id="financial:transfers",
            )

    # =========================================================================
    # Query Operations
    # =========================================================================

    async def search_transfers(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict]:
        """Search transfers by reason, entities, or metadata using Graphiti."""
        results = await self._graph_store.graphiti.search(
            query=query,
            num_results=limit,
            group_ids=["financial:transfers"],
        )

        transfers = []
        for result in results:
            content = result.fact if hasattr(result, 'fact') else str(result)
            try:
                transfers.append(json.loads(content))
            except json.JSONDecodeError:
                transfers.append({"content": content})

        return transfers

    async def get_transfer_history(
        self,
        account_id: int,
        limit: int = 50,
    ) -> list[dict]:
        """Get transfer history for an account with full context."""
        query = f"""
        MATCH (n:Episode) WHERE n.name STARTS WITH 'transfer_'
        RETURN n.content as content
        ORDER BY n.reference_time DESC
        LIMIT {limit}
        """
        results = await self._graph_store._driver.execute_query(query)

        history = []
        for row in results:
            content = json.loads(row.get("content", "{}"))
            if (content.get("debit_account_id") == account_id or
                content.get("credit_account_id") == account_id):
                history.append(content)

        return history

    async def get_balance(self, account_id: int) -> Optional[dict]:
        """Get current balance from TigerBeetle."""
        if not self._tb_client:
            return None

        accounts = self._tb_client.lookup_accounts([account_id])
        if not accounts:
            return None

        acc = accounts[0]
        return {
            "account_id": account_id,
            "debits_pending": acc.debits_pending,
            "debits_posted": acc.debits_posted,
            "credits_pending": acc.credits_pending,
            "credits_posted": acc.credits_posted,
            "available": acc.credits_posted - acc.debits_posted,
        }


# =============================================================================
# Convenience Functions
# =============================================================================

async def get_financial_store(config: Optional[FinancialConfig] = None) -> FinancialStore:
    """Get the financial store singleton instance."""
    return await FinancialStore.get_instance(config)
