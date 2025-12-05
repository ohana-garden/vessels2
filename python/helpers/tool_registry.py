"""
Tool Registry - Graph-native tool source and capability management for Vessels.

This module provides the Tool Registry Subsystem as specified in the build spec:
1. Sync external tool sources (MCP servers, OpenAPI specs) into the graph
2. Provide semantic + structural capability matching via graph traversal
3. Core agents (SourceAgent, GuardianAgent, SyncAgent) as graph nodes
4. Guardian validation of tool registrations

All data lives in FalkorDB. No filesystem fallback.
"""

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)


# =============================================================================
# Enums and Types
# =============================================================================

class ToolSourceType(str, Enum):
    """Types of tool sources."""
    MCP = "mcp"
    OPENAPI = "openapi"
    CUSTOM = "custom"


class ToolTransport(str, Enum):
    """Transport types for tool sources."""
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"
    WEBSOCKET = "websocket"


class RegistryOrigin(str, Enum):
    """Origin of tool registration."""
    OFFICIAL = "official"
    GITHUB = "github"
    MANUAL = "manual"


class ToolStatus(str, Enum):
    """Status of a tool source."""
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    DENIED = "denied"
    DEPRECATED = "deprecated"


class ActionType(str, Enum):
    """Types of actions a capability can perform."""
    READ = "read"
    WRITE = "write"
    SEARCH = "search"
    CREATE = "create"
    DELETE = "delete"
    EXECUTE = "execute"
    TRANSFORM = "transform"


class RiskLevel(str, Enum):
    """Risk levels for operations."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuthType(str, Enum):
    """Authentication types."""
    NONE = "none"
    API_KEY = "api_key"
    OAUTH = "oauth"
    BEARER = "bearer"


class ApprovalDecision(str, Enum):
    """Guardian approval decisions."""
    APPROVE = "approve"
    DENY = "deny"
    REQUEST_INFO = "request_info"


class OpenAPIStrategy(str, Enum):
    """OpenAPI integration strategies."""
    DIRECT = "direct"  # Each operation = tool
    META = "meta"      # Three operations: list_endpoints, get_schema, invoke


# =============================================================================
# Data Models (Graph Nodes)
# =============================================================================

@dataclass
class ToolSource:
    """A tool source - MCP server, OpenAPI spec, or custom provider."""
    id: str
    name: str
    description: str = ""
    source_type: ToolSourceType = ToolSourceType.MCP
    transport: ToolTransport = ToolTransport.STDIO
    registry_origin: RegistryOrigin = RegistryOrigin.MANUAL
    spec_url: str = ""
    base_url: str = ""
    status: ToolStatus = ToolStatus.PENDING_APPROVAL
    last_synced: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "source_type": self.source_type.value,
            "transport": self.transport.value,
            "registry_origin": self.registry_origin.value,
            "spec_url": self.spec_url,
            "base_url": self.base_url,
            "status": self.status.value,
            "last_synced": self.last_synced.isoformat() if self.last_synced else None,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolSource":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            source_type=ToolSourceType(data.get("source_type", "mcp")),
            transport=ToolTransport(data.get("transport", "stdio")),
            registry_origin=RegistryOrigin(data.get("registry_origin", "manual")),
            spec_url=data.get("spec_url", ""),
            base_url=data.get("base_url", ""),
            status=ToolStatus(data.get("status", "pending_approval")),
            last_synced=datetime.fromisoformat(data["last_synced"]) if data.get("last_synced") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Capability:
    """What a tool can do."""
    id: str
    name: str
    domain: str
    action_type: ActionType = ActionType.READ
    description: str = ""
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "action_type": self.action_type.value,
            "description": self.description,
            # Embedding stored separately for vector index
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Capability":
        return cls(
            id=data["id"],
            name=data["name"],
            domain=data.get("domain", "general"),
            action_type=ActionType(data.get("action_type", "read")),
            description=data.get("description", ""),
            embedding=data.get("embedding"),
        )


@dataclass
class ToolOperation:
    """Individual operation a tool exposes."""
    id: str
    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    tool_source_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "risk_level": self.risk_level.value,
            "tool_source_id": self.tool_source_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolOperation":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            input_schema=data.get("input_schema", {}),
            output_schema=data.get("output_schema", {}),
            risk_level=RiskLevel(data.get("risk_level", "low")),
            tool_source_id=data.get("tool_source_id", ""),
        )


@dataclass
class AuthRequirement:
    """Auth reference - NEVER stores actual secrets."""
    id: str
    type: AuthType = AuthType.NONE
    env_var: str = ""  # Reference only, e.g., "GITHUB_TOKEN"
    scope: str = ""
    required: bool = False
    tool_source_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "env_var": self.env_var,
            "scope": self.scope,
            "required": self.required,
            "tool_source_id": self.tool_source_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AuthRequirement":
        return cls(
            id=data["id"],
            type=AuthType(data.get("type", "none")),
            env_var=data.get("env_var", ""),
            scope=data.get("scope", ""),
            required=data.get("required", False),
            tool_source_id=data.get("tool_source_id", ""),
        )


@dataclass
class ApprovalRecord:
    """Guardian decision record."""
    id: str
    decision: ApprovalDecision
    risk_level: RiskLevel = RiskLevel.LOW
    conditions: List[str] = field(default_factory=list)
    reasoning: str = ""
    reviewed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    guardian_id: str = "guardian_agent"
    tool_source_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "decision": self.decision.value,
            "risk_level": self.risk_level.value,
            "conditions": self.conditions,
            "reasoning": self.reasoning,
            "reviewed_at": self.reviewed_at.isoformat(),
            "guardian_id": self.guardian_id,
            "tool_source_id": self.tool_source_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ApprovalRecord":
        return cls(
            id=data["id"],
            decision=ApprovalDecision(data["decision"]),
            risk_level=RiskLevel(data.get("risk_level", "low")),
            conditions=data.get("conditions", []),
            reasoning=data.get("reasoning", ""),
            reviewed_at=datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else datetime.now(timezone.utc),
            guardian_id=data.get("guardian_id", "guardian_agent"),
            tool_source_id=data.get("tool_source_id", ""),
        )


@dataclass
class RegistrySource:
    """External registry to sync from."""
    id: str
    name: str
    url: str
    sync_interval_hours: int = 24
    auto_approve: bool = False
    last_sync: Optional[datetime] = None
    next_sync: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "sync_interval_hours": self.sync_interval_hours,
            "auto_approve": self.auto_approve,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "next_sync": self.next_sync.isoformat() if self.next_sync else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RegistrySource":
        return cls(
            id=data["id"],
            name=data["name"],
            url=data["url"],
            sync_interval_hours=data.get("sync_interval_hours", 24),
            auto_approve=data.get("auto_approve", False),
            last_sync=datetime.fromisoformat(data["last_sync"]) if data.get("last_sync") else None,
            next_sync=datetime.fromisoformat(data["next_sync"]) if data.get("next_sync") else None,
        )


@dataclass
class SyncRun:
    """Record of a sync operation."""
    id: str
    registry_source_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    tools_added: int = 0
    tools_updated: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "registry_source_id": self.registry_source_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "tools_added": self.tools_added,
            "tools_updated": self.tools_updated,
            "errors": self.errors,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncRun":
        return cls(
            id=data["id"],
            registry_source_id=data["registry_source_id"],
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else datetime.now(timezone.utc),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            tools_added=data.get("tools_added", 0),
            tools_updated=data.get("tools_updated", 0),
            errors=data.get("errors", []),
        )


@dataclass
class AgentNode:
    """Agent definition stored in graph."""
    id: str
    name: str
    system_prompt: str
    model: str = "claude-sonnet-4-20250514"
    temperature: float = 0.3
    status: str = "active"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    capabilities: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "system_prompt": self.system_prompt,
            "model": self.model,
            "temperature": self.temperature,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "capabilities": self.capabilities,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentNode":
        return cls(
            id=data["id"],
            name=data["name"],
            system_prompt=data["system_prompt"],
            model=data.get("model", "claude-sonnet-4-20250514"),
            temperature=data.get("temperature", 0.3),
            status=data.get("status", "active"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
            capabilities=data.get("capabilities", []),
        )


# =============================================================================
# Agent System Prompts
# =============================================================================

SOURCE_AGENT_PROMPT = '''
You are the Source Agent in the Vessels network. You help other agents find and access external tools.

When an agent needs a capability:
1. Understand what they are trying to accomplish
2. Query the tool registry for matching capabilities
3. Return tool configurations they can instantiate
4. If a tool requires approval, escalate to Guardian

You execute these graph queries:

FIND_BY_TASK (semantic):
  CALL db.idx.vector.queryNodes("capability_embedding", $k, vecf32($embedding))
  YIELD node, score
  MATCH (t:ToolSource)-[:HAS_CAPABILITY]->(node)
  WHERE t.status = "active"
  RETURN DISTINCT t, score ORDER BY score DESC LIMIT $limit

FIND_BY_DOMAIN (structural):
  MATCH (t:ToolSource)-[:HAS_CAPABILITY]->(c:Capability)
  WHERE c.domain = $domain AND t.status = "active"
  RETURN DISTINCT t

GET_TOOL_CONFIG:
  MATCH (t:ToolSource {id: $tool_id})
  OPTIONAL MATCH (t)-[:REQUIRES_AUTH]->(auth:AuthRequirement)
  OPTIONAL MATCH (t)-[:PROVIDES]->(op:ToolOperation)
  RETURN t, collect(DISTINCT auth) as auth, collect(DISTINCT op) as operations

REQUEST_APPROVAL:
  MATCH (t:ToolSource {id: $tool_id})
  SET t.status = "pending_review", t.review_requested_by = $requesting_agent, t.review_justification = $justification
  WITH t
  MATCH (g:Agent {id: "guardian_agent"})
  CREATE (t)-[:AWAITING_REVIEW]->(g)
  RETURN t

Never return tools where status != "active" unless explicitly approved by Guardian.
Output tool configs as:
{
  "id": "...",
  "name": "...",
  "type": "mcp|openapi",
  "transport": "stdio|http|sse",
  "spec_url": "...",
  "base_url": "...",
  "auth_env_var": "..."
}
'''

GUARDIAN_AGENT_PROMPT = '''
You are the Guardian Agent in the Vessels network. You validate tool registrations before they become active.

Review criteria:
1. Source origin - official registries (registry.modelcontextprotocol.io) get lighter review
2. Auth scope - flag excessive permissions, prefer principle of least privilege
3. Operation risk - write/delete operations need justification
4. Dependencies - reject chains containing unapproved tools

Decision levels:
- AUTO_APPROVE: official registry + read-only + no auth required
- APPROVE: community source with acceptable risk
- DENY: unknown source with auth, or flagged security concerns
- REQUEST_INFO: need more context before deciding

You execute these graph queries:

REVIEW_PENDING:
  MATCH (t:ToolSource {status: "pending_approval"})
  OPTIONAL MATCH (t)-[:SYNCED_FROM]->(r:RegistrySource)
  OPTIONAL MATCH (t)-[:REQUIRES_AUTH]->(auth:AuthRequirement)
  OPTIONAL MATCH (t)-[:PROVIDES]->(op:ToolOperation)
  OPTIONAL MATCH (t)-[:DEPENDS_ON]->(dep:ToolSource)
  RETURN t, r, collect(DISTINCT auth) as auth, collect(DISTINCT op) as ops, collect(DISTINCT dep) as deps

RECORD_DECISION:
  MATCH (t:ToolSource {id: $tool_id})
  CREATE (ar:ApprovalRecord {
    id: randomUUID(),
    decision: $decision,
    risk_level: $risk_level,
    conditions: $conditions,
    reasoning: $reasoning,
    reviewed_at: datetime(),
    guardian_id: "guardian_agent"
  })
  CREATE (t)-[:APPROVED_BY]->(ar)
  SET t.status = CASE $decision WHEN "approve" THEN "active" WHEN "deny" THEN "denied" ELSE t.status END
  RETURN t, ar

CHECK_DEPENDENCY_CHAIN:
  MATCH path = (t:ToolSource {id: $tool_id})-[:DEPENDS_ON*1..5]->(dep:ToolSource)
  WHERE dep.status <> "active"
  RETURN dep, length(path) as depth

Output structured decisions:
{
  "tool_id": "...",
  "decision": "approve|deny|request_info",
  "risk_level": "low|medium|high",
  "conditions": [],
  "reasoning": "..."
}
'''

SYNC_AGENT_PROMPT = '''
You are the Sync Agent. You pull tool definitions from external registries into the graph.

Sync sources:
1. MCP Official Registry: GET https://registry.modelcontextprotocol.io/v0/servers?limit=100
2. Manual OpenAPI ingestion via spec URL
3. Watched external sources defined in RegistrySource nodes

For each tool from MCP registry:
  MERGE (t:ToolSource {id: server.name})
  SET t.name = server.title,
      t.description = server.description,
      t.source_type = "mcp",
      t.transport = extract from server.packages[0].transport.type,
      t.registry_origin = "official",
      t.spec_url = server.repository,
      t.status = CASE WHEN $auto_approve THEN "active" ELSE "pending_approval" END,
      t.last_synced = datetime()

For capabilities, analyze the description and create:
  MERGE (c:Capability {id: $tool_id + "." + $capability_name})
  SET c.name = $capability_name,
      c.domain = $domain,
      c.action_type = $action_type,
      c.description = $description,
      c.embedding = $embedding_vector
  MERGE (t)-[:HAS_CAPABILITY]->(c)

Record sync runs:
  CREATE (sr:SyncRun {
    id: randomUUID(),
    started_at: $start,
    completed_at: datetime(),
    tools_added: $added,
    tools_updated: $updated,
    errors: $errors
  })
  MATCH (rs:RegistrySource {id: $source_id})
  CREATE (rs)-[:HAD_RUN]->(sr)

After sync, notify Guardian of pending approvals:
  MATCH (t:ToolSource {status: "pending_approval"})
  WHERE t.last_synced > datetime() - duration("PT1H")
  WITH collect(t.id) as pending_ids
  // Guardian reviews batch
'''


# =============================================================================
# Tool Registry Implementation
# =============================================================================

class ToolRegistry:
    """
    Central registry for tool sources and capabilities.

    All data is stored in FalkorDB via GraphStore.
    Provides semantic and structural capability matching.
    """

    _instance: Optional["ToolRegistry"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._store = None
        self._initialized = False
        self._embedder = None

    @classmethod
    async def get_instance(cls) -> "ToolRegistry":
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self) -> None:
        """Initialize the registry."""
        if self._initialized:
            return

        from python.helpers.graph_store import get_graph_store
        self._store = await get_graph_store()

        # Seed initial data
        await self._seed_registry_sources()
        await self._seed_core_agents()

        self._initialized = True
        logger.info("ToolRegistry initialized")

    async def _get_store(self):
        """Get the graph store instance."""
        if self._store is None:
            from python.helpers.graph_store import get_graph_store
            self._store = await get_graph_store()
        return self._store

    # =========================================================================
    # Registry Source Management
    # =========================================================================

    async def _seed_registry_sources(self) -> None:
        """Seed the default registry sources."""
        default_sources = [
            RegistrySource(
                id="mcp_official",
                name="MCP Official Registry",
                url="https://registry.modelcontextprotocol.io/v0/servers",
                sync_interval_hours=24,
                auto_approve=True,
            ),
            RegistrySource(
                id="github_mcp",
                name="GitHub MCP Registry",
                url="https://github.com/mcp",
                sync_interval_hours=48,
                auto_approve=False,
            ),
        ]

        for source in default_sources:
            await self.save_registry_source(source)

    async def save_registry_source(self, source: RegistrySource) -> None:
        """Save a registry source to the graph."""
        store = await self._get_store()
        content = json.dumps({
            "type": "registry_source",
            "data": source.to_dict(),
        })
        await store.save_content(
            f"tool_registry/sources/{source.id}",
            content,
            content_type="tool_registry"
        )

    async def get_registry_source(self, source_id: str) -> Optional[RegistrySource]:
        """Get a registry source by ID."""
        store = await self._get_store()
        content = await store.get_content(f"tool_registry/sources/{source_id}")
        if content:
            data = json.loads(content)
            if data.get("type") == "registry_source":
                return RegistrySource.from_dict(data["data"])
        return None

    async def list_registry_sources(self) -> List[RegistrySource]:
        """List all registry sources."""
        store = await self._get_store()
        paths = await store.list_content(content_type="tool_registry")
        sources = []
        for path in paths:
            if path.startswith("tool_registry/sources/"):
                content = await store.get_content(path)
                if content:
                    data = json.loads(content)
                    if data.get("type") == "registry_source":
                        sources.append(RegistrySource.from_dict(data["data"]))
        return sources

    # =========================================================================
    # Core Agent Management
    # =========================================================================

    async def _seed_core_agents(self) -> None:
        """Seed the core agents."""
        agents = [
            AgentNode(
                id="source_agent",
                name="Source Agent",
                system_prompt=SOURCE_AGENT_PROMPT,
                model="claude-sonnet-4-20250514",
                temperature=0.3,
                capabilities=["tool_discovery", "capability_matching", "tool_resolution"],
            ),
            AgentNode(
                id="guardian_agent",
                name="Guardian Agent",
                system_prompt=GUARDIAN_AGENT_PROMPT,
                model="claude-sonnet-4-20250514",
                temperature=0.1,
                capabilities=["tool_approval", "risk_assessment", "security_review"],
            ),
            AgentNode(
                id="sync_agent",
                name="Sync Agent",
                system_prompt=SYNC_AGENT_PROMPT,
                model="claude-sonnet-4-20250514",
                temperature=0.0,
                capabilities=["registry_sync", "tool_import", "capability_extraction"],
            ),
        ]

        for agent in agents:
            await self.save_agent(agent)

    async def save_agent(self, agent: AgentNode) -> None:
        """Save an agent node to the graph."""
        store = await self._get_store()
        content = json.dumps({
            "type": "agent_node",
            "data": agent.to_dict(),
        })
        await store.save_content(
            f"tool_registry/agents/{agent.id}",
            content,
            content_type="tool_registry"
        )

    async def get_agent(self, agent_id: str) -> Optional[AgentNode]:
        """Get an agent by ID."""
        store = await self._get_store()
        content = await store.get_content(f"tool_registry/agents/{agent_id}")
        if content:
            data = json.loads(content)
            if data.get("type") == "agent_node":
                return AgentNode.from_dict(data["data"])
        return None

    async def list_agents(self) -> List[AgentNode]:
        """List all agents."""
        store = await self._get_store()
        paths = await store.list_content(content_type="tool_registry")
        agents = []
        for path in paths:
            if path.startswith("tool_registry/agents/"):
                content = await store.get_content(path)
                if content:
                    data = json.loads(content)
                    if data.get("type") == "agent_node":
                        agents.append(AgentNode.from_dict(data["data"]))
        return agents

    # =========================================================================
    # Tool Source Management
    # =========================================================================

    async def save_tool_source(self, tool_source: ToolSource) -> None:
        """Save a tool source to the graph."""
        store = await self._get_store()
        content = json.dumps({
            "type": "tool_source",
            "data": tool_source.to_dict(),
        })
        await store.save_content(
            f"tool_registry/tools/{tool_source.id}",
            content,
            content_type="tool_registry"
        )

    async def get_tool_source(self, tool_id: str) -> Optional[ToolSource]:
        """Get a tool source by ID."""
        store = await self._get_store()
        content = await store.get_content(f"tool_registry/tools/{tool_id}")
        if content:
            data = json.loads(content)
            if data.get("type") == "tool_source":
                return ToolSource.from_dict(data["data"])
        return None

    async def list_tool_sources(self, status: Optional[ToolStatus] = None) -> List[ToolSource]:
        """List all tool sources, optionally filtered by status."""
        store = await self._get_store()
        paths = await store.list_content(content_type="tool_registry")
        tools = []
        for path in paths:
            if path.startswith("tool_registry/tools/"):
                content = await store.get_content(path)
                if content:
                    data = json.loads(content)
                    if data.get("type") == "tool_source":
                        tool = ToolSource.from_dict(data["data"])
                        if status is None or tool.status == status:
                            tools.append(tool)
        return tools

    async def update_tool_status(self, tool_id: str, status: ToolStatus) -> bool:
        """Update a tool source's status."""
        tool = await self.get_tool_source(tool_id)
        if tool:
            tool.status = status
            await self.save_tool_source(tool)
            return True
        return False

    # =========================================================================
    # Capability Management
    # =========================================================================

    async def save_capability(self, capability: Capability, tool_source_id: str) -> None:
        """Save a capability and link it to a tool source."""
        store = await self._get_store()
        content = json.dumps({
            "type": "capability",
            "tool_source_id": tool_source_id,
            "data": capability.to_dict(),
        })
        await store.save_content(
            f"tool_registry/capabilities/{capability.id}",
            content,
            content_type="tool_registry"
        )

    async def get_capability(self, capability_id: str) -> Optional[Tuple[Capability, str]]:
        """Get a capability by ID. Returns (capability, tool_source_id)."""
        store = await self._get_store()
        content = await store.get_content(f"tool_registry/capabilities/{capability_id}")
        if content:
            data = json.loads(content)
            if data.get("type") == "capability":
                return (
                    Capability.from_dict(data["data"]),
                    data.get("tool_source_id", ""),
                )
        return None

    async def list_capabilities_for_tool(self, tool_source_id: str) -> List[Capability]:
        """List all capabilities for a tool source."""
        store = await self._get_store()
        paths = await store.list_content(content_type="tool_registry")
        capabilities = []
        for path in paths:
            if path.startswith("tool_registry/capabilities/"):
                content = await store.get_content(path)
                if content:
                    data = json.loads(content)
                    if data.get("type") == "capability" and data.get("tool_source_id") == tool_source_id:
                        capabilities.append(Capability.from_dict(data["data"]))
        return capabilities

    async def find_capabilities_by_domain(self, domain: str) -> List[Tuple[Capability, ToolSource]]:
        """Find capabilities by domain with their associated active tools."""
        store = await self._get_store()
        paths = await store.list_content(content_type="tool_registry")
        results = []

        for path in paths:
            if path.startswith("tool_registry/capabilities/"):
                content = await store.get_content(path)
                if content:
                    data = json.loads(content)
                    if data.get("type") == "capability":
                        cap = Capability.from_dict(data["data"])
                        if cap.domain == domain:
                            tool = await self.get_tool_source(data.get("tool_source_id", ""))
                            if tool and tool.status == ToolStatus.ACTIVE:
                                results.append((cap, tool))
        return results

    # =========================================================================
    # Operation Management
    # =========================================================================

    async def save_operation(self, operation: ToolOperation) -> None:
        """Save a tool operation."""
        store = await self._get_store()
        content = json.dumps({
            "type": "tool_operation",
            "data": operation.to_dict(),
        })
        await store.save_content(
            f"tool_registry/operations/{operation.id}",
            content,
            content_type="tool_registry"
        )

    async def get_operation(self, operation_id: str) -> Optional[ToolOperation]:
        """Get an operation by ID."""
        store = await self._get_store()
        content = await store.get_content(f"tool_registry/operations/{operation_id}")
        if content:
            data = json.loads(content)
            if data.get("type") == "tool_operation":
                return ToolOperation.from_dict(data["data"])
        return None

    async def list_operations_for_tool(self, tool_source_id: str) -> List[ToolOperation]:
        """List all operations for a tool source."""
        store = await self._get_store()
        paths = await store.list_content(content_type="tool_registry")
        operations = []
        for path in paths:
            if path.startswith("tool_registry/operations/"):
                content = await store.get_content(path)
                if content:
                    data = json.loads(content)
                    if data.get("type") == "tool_operation":
                        op = ToolOperation.from_dict(data["data"])
                        if op.tool_source_id == tool_source_id:
                            operations.append(op)
        return operations

    # =========================================================================
    # Auth Requirement Management
    # =========================================================================

    async def save_auth_requirement(self, auth: AuthRequirement) -> None:
        """Save an auth requirement."""
        store = await self._get_store()
        content = json.dumps({
            "type": "auth_requirement",
            "data": auth.to_dict(),
        })
        await store.save_content(
            f"tool_registry/auth/{auth.id}",
            content,
            content_type="tool_registry"
        )

    async def get_auth_requirements_for_tool(self, tool_source_id: str) -> List[AuthRequirement]:
        """Get all auth requirements for a tool source."""
        store = await self._get_store()
        paths = await store.list_content(content_type="tool_registry")
        requirements = []
        for path in paths:
            if path.startswith("tool_registry/auth/"):
                content = await store.get_content(path)
                if content:
                    data = json.loads(content)
                    if data.get("type") == "auth_requirement":
                        auth = AuthRequirement.from_dict(data["data"])
                        if auth.tool_source_id == tool_source_id:
                            requirements.append(auth)
        return requirements

    # =========================================================================
    # Approval Record Management
    # =========================================================================

    async def save_approval_record(self, record: ApprovalRecord) -> None:
        """Save an approval record."""
        store = await self._get_store()
        content = json.dumps({
            "type": "approval_record",
            "data": record.to_dict(),
        })
        await store.save_content(
            f"tool_registry/approvals/{record.id}",
            content,
            content_type="tool_registry"
        )

    async def get_approval_records_for_tool(self, tool_source_id: str) -> List[ApprovalRecord]:
        """Get all approval records for a tool source."""
        store = await self._get_store()
        paths = await store.list_content(content_type="tool_registry")
        records = []
        for path in paths:
            if path.startswith("tool_registry/approvals/"):
                content = await store.get_content(path)
                if content:
                    data = json.loads(content)
                    if data.get("type") == "approval_record":
                        rec = ApprovalRecord.from_dict(data["data"])
                        if rec.tool_source_id == tool_source_id:
                            records.append(rec)
        return records

    # =========================================================================
    # Sync Run Management
    # =========================================================================

    async def save_sync_run(self, run: SyncRun) -> None:
        """Save a sync run record."""
        store = await self._get_store()
        content = json.dumps({
            "type": "sync_run",
            "data": run.to_dict(),
        })
        await store.save_content(
            f"tool_registry/sync_runs/{run.id}",
            content,
            content_type="tool_registry"
        )

    async def get_sync_runs_for_source(self, source_id: str, limit: int = 10) -> List[SyncRun]:
        """Get recent sync runs for a registry source."""
        store = await self._get_store()
        paths = await store.list_content(content_type="tool_registry")
        runs = []
        for path in paths:
            if path.startswith("tool_registry/sync_runs/"):
                content = await store.get_content(path)
                if content:
                    data = json.loads(content)
                    if data.get("type") == "sync_run":
                        run = SyncRun.from_dict(data["data"])
                        if run.registry_source_id == source_id:
                            runs.append(run)

        # Sort by started_at descending and limit
        runs.sort(key=lambda r: r.started_at, reverse=True)
        return runs[:limit]

    # =========================================================================
    # Capability Matching (SourceAgent Queries)
    # =========================================================================

    async def find_tools_by_domain(self, domain: str) -> List[ToolSource]:
        """
        Structural search: Find active tools by capability domain.

        Equivalent to:
        MATCH (t:ToolSource)-[:HAS_CAPABILITY]->(c:Capability)
        WHERE c.domain = $domain AND t.status = "active"
        RETURN DISTINCT t
        """
        results = await self.find_capabilities_by_domain(domain)
        # Deduplicate tools
        seen = set()
        tools = []
        for _, tool in results:
            if tool.id not in seen:
                seen.add(tool.id)
                tools.append(tool)
        return tools

    async def find_tools_by_action(self, action_type: ActionType) -> List[ToolSource]:
        """Find active tools by action type."""
        store = await self._get_store()
        paths = await store.list_content(content_type="tool_registry")

        tool_ids = set()
        for path in paths:
            if path.startswith("tool_registry/capabilities/"):
                content = await store.get_content(path)
                if content:
                    data = json.loads(content)
                    if data.get("type") == "capability":
                        cap = Capability.from_dict(data["data"])
                        if cap.action_type == action_type:
                            tool_ids.add(data.get("tool_source_id", ""))

        tools = []
        for tool_id in tool_ids:
            tool = await self.get_tool_source(tool_id)
            if tool and tool.status == ToolStatus.ACTIVE:
                tools.append(tool)
        return tools

    async def get_tool_config(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """
        Get full tool configuration for instantiation.

        Equivalent to:
        MATCH (t:ToolSource {id: $tool_id})
        OPTIONAL MATCH (t)-[:REQUIRES_AUTH]->(auth:AuthRequirement)
        OPTIONAL MATCH (t)-[:PROVIDES]->(op:ToolOperation)
        RETURN t, collect(DISTINCT auth) as auth, collect(DISTINCT op) as operations
        """
        tool = await self.get_tool_source(tool_id)
        if not tool:
            return None

        auth_reqs = await self.get_auth_requirements_for_tool(tool_id)
        operations = await self.list_operations_for_tool(tool_id)
        capabilities = await self.list_capabilities_for_tool(tool_id)

        # Build config for tool instantiation
        config = {
            "id": tool.id,
            "name": tool.name,
            "type": tool.source_type.value,
            "transport": tool.transport.value,
            "spec_url": tool.spec_url,
            "base_url": tool.base_url,
            "status": tool.status.value,
            "auth_requirements": [a.to_dict() for a in auth_reqs],
            "operations": [o.to_dict() for o in operations],
            "capabilities": [c.to_dict() for c in capabilities],
        }

        # Add auth_env_var if present
        for auth in auth_reqs:
            if auth.env_var:
                config["auth_env_var"] = auth.env_var
                break

        return config

    # =========================================================================
    # Guardian Functions
    # =========================================================================

    async def get_pending_tools(self) -> List[Dict[str, Any]]:
        """
        Get tools pending approval with full context.

        Equivalent to REVIEW_PENDING query.
        """
        pending = await self.list_tool_sources(status=ToolStatus.PENDING_APPROVAL)
        results = []

        for tool in pending:
            auth_reqs = await self.get_auth_requirements_for_tool(tool.id)
            operations = await self.list_operations_for_tool(tool.id)

            # Determine registry source
            registry_origin = tool.registry_origin.value

            results.append({
                "tool": tool.to_dict(),
                "registry_origin": registry_origin,
                "auth_requirements": [a.to_dict() for a in auth_reqs],
                "operations": [o.to_dict() for o in operations],
                "has_write_ops": any(o.risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH] for o in operations),
                "requires_auth": any(a.required for a in auth_reqs),
            })

        return results

    async def record_approval_decision(
        self,
        tool_id: str,
        decision: ApprovalDecision,
        risk_level: RiskLevel,
        reasoning: str,
        conditions: List[str] = None,
    ) -> Optional[ApprovalRecord]:
        """
        Record a Guardian approval decision.

        Equivalent to RECORD_DECISION query.
        """
        tool = await self.get_tool_source(tool_id)
        if not tool:
            return None

        record_id = hashlib.sha256(
            f"{tool_id}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]

        record = ApprovalRecord(
            id=record_id,
            decision=decision,
            risk_level=risk_level,
            conditions=conditions or [],
            reasoning=reasoning,
            tool_source_id=tool_id,
        )

        await self.save_approval_record(record)

        # Update tool status based on decision
        if decision == ApprovalDecision.APPROVE:
            tool.status = ToolStatus.ACTIVE
        elif decision == ApprovalDecision.DENY:
            tool.status = ToolStatus.DENIED

        await self.save_tool_source(tool)

        return record

    async def auto_approve_tool(self, tool: ToolSource) -> bool:
        """
        Attempt auto-approval based on Guardian criteria.

        AUTO_APPROVE if:
        - Official registry origin
        - No required auth
        - All operations are low risk (read-only)
        """
        if tool.registry_origin != RegistryOrigin.OFFICIAL:
            return False

        auth_reqs = await self.get_auth_requirements_for_tool(tool.id)
        if any(a.required for a in auth_reqs):
            return False

        operations = await self.list_operations_for_tool(tool.id)
        if any(o.risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL] for o in operations):
            return False

        # Auto-approve
        await self.record_approval_decision(
            tool_id=tool.id,
            decision=ApprovalDecision.APPROVE,
            risk_level=RiskLevel.LOW,
            reasoning="Auto-approved: Official registry, no auth required, read-only operations",
        )

        return True

    # =========================================================================
    # Sync Functions
    # =========================================================================

    async def sync_mcp_registry(self, source_id: str = "mcp_official") -> SyncRun:
        """
        Sync tools from the MCP official registry.

        Fetches from: https://registry.modelcontextprotocol.io/v0/servers
        """
        source = await self.get_registry_source(source_id)
        if not source:
            raise ValueError(f"Registry source not found: {source_id}")

        run_id = hashlib.sha256(
            f"{source_id}:{datetime.now(timezone.utc).isoformat()}".encode()
        ).hexdigest()[:16]

        run = SyncRun(
            id=run_id,
            registry_source_id=source_id,
        )

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{source.url}?limit=100")
                response.raise_for_status()
                data = response.json()
        except Exception as e:
            run.errors.append(f"Failed to fetch registry: {str(e)}")
            run.completed_at = datetime.now(timezone.utc)
            await self.save_sync_run(run)
            return run

        servers = data.get("servers", [])

        for server in servers:
            try:
                tool_id = server.get("name", "")
                if not tool_id:
                    continue

                # Check if tool exists
                existing = await self.get_tool_source(tool_id)

                # Extract transport from packages
                transport = ToolTransport.STDIO
                packages = server.get("packages", [])
                if packages:
                    pkg = packages[0]
                    transport_config = pkg.get("transport", {})
                    transport_type = transport_config.get("type", "stdio")
                    transport = ToolTransport(transport_type) if transport_type in [t.value for t in ToolTransport] else ToolTransport.STDIO

                tool = ToolSource(
                    id=tool_id,
                    name=server.get("title", tool_id),
                    description=server.get("description", ""),
                    source_type=ToolSourceType.MCP,
                    transport=transport,
                    registry_origin=RegistryOrigin.OFFICIAL,
                    spec_url=server.get("repository", ""),
                    status=ToolStatus.ACTIVE if source.auto_approve else ToolStatus.PENDING_APPROVAL,
                    last_synced=datetime.now(timezone.utc),
                    created_at=existing.created_at if existing else datetime.now(timezone.utc),
                    metadata=server,
                )

                await self.save_tool_source(tool)

                # Extract capabilities from description
                await self._extract_capabilities(tool)

                if existing:
                    run.tools_updated += 1
                else:
                    run.tools_added += 1

            except Exception as e:
                run.errors.append(f"Failed to process {server.get('name', 'unknown')}: {str(e)}")

        # Update source sync times
        source.last_sync = datetime.now(timezone.utc)
        source.next_sync = datetime.now(timezone.utc).replace(
            hour=(datetime.now(timezone.utc).hour + source.sync_interval_hours) % 24
        )
        await self.save_registry_source(source)

        run.completed_at = datetime.now(timezone.utc)
        await self.save_sync_run(run)

        logger.info(f"MCP registry sync complete: {run.tools_added} added, {run.tools_updated} updated, {len(run.errors)} errors")

        return run

    async def _extract_capabilities(self, tool: ToolSource) -> None:
        """Extract capabilities from tool description using heuristics."""
        description = tool.description.lower()

        # Domain detection heuristics
        domain_keywords = {
            "filesystem": ["file", "directory", "path", "read file", "write file", "folder"],
            "database": ["database", "sql", "query", "table", "record", "schema"],
            "web": ["http", "api", "request", "endpoint", "url", "fetch", "web"],
            "git": ["git", "repository", "commit", "branch", "merge", "clone"],
            "docker": ["docker", "container", "image", "compose", "kubernetes"],
            "shell": ["shell", "command", "terminal", "bash", "execute", "script"],
            "ai": ["llm", "model", "inference", "embedding", "ai", "ml", "neural"],
            "search": ["search", "find", "query", "lookup", "index"],
            "communication": ["email", "slack", "message", "notification", "send"],
            "data": ["json", "csv", "xml", "parse", "transform", "data"],
        }

        # Action detection heuristics
        action_keywords = {
            ActionType.READ: ["read", "get", "fetch", "retrieve", "load", "view"],
            ActionType.WRITE: ["write", "save", "store", "put", "update", "set"],
            ActionType.CREATE: ["create", "new", "add", "insert", "generate"],
            ActionType.DELETE: ["delete", "remove", "drop", "clear"],
            ActionType.SEARCH: ["search", "find", "query", "lookup", "filter"],
            ActionType.EXECUTE: ["execute", "run", "invoke", "call", "perform"],
            ActionType.TRANSFORM: ["transform", "convert", "parse", "format"],
        }

        detected_domains = []
        detected_actions = []

        for domain, keywords in domain_keywords.items():
            for keyword in keywords:
                if keyword in description:
                    detected_domains.append(domain)
                    break

        for action, keywords in action_keywords.items():
            for keyword in keywords:
                if keyword in description:
                    detected_actions.append(action)
                    break

        # Default if nothing detected
        if not detected_domains:
            detected_domains = ["general"]
        if not detected_actions:
            detected_actions = [ActionType.READ]

        # Create capabilities
        for domain in detected_domains:
            for action in detected_actions:
                cap_id = f"{tool.id}.{domain}.{action.value}"
                capability = Capability(
                    id=cap_id,
                    name=f"{domain}_{action.value}",
                    domain=domain,
                    action_type=action,
                    description=f"{action.value.title()} operations for {domain} via {tool.name}",
                )
                await self.save_capability(capability, tool.id)

    async def import_openapi_spec(
        self,
        spec_url: str,
        name: Optional[str] = None,
        strategy: OpenAPIStrategy = OpenAPIStrategy.DIRECT,
        auto_approve: bool = False,
    ) -> Optional[ToolSource]:
        """
        Import an OpenAPI spec as a tool source.

        Strategies:
        - DIRECT: Each operation becomes a tool operation
        - META: Three operations: list_endpoints, get_schema, invoke
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(spec_url)
                response.raise_for_status()

                if spec_url.endswith('.yaml') or spec_url.endswith('.yml'):
                    import yaml
                    spec = yaml.safe_load(response.text)
                else:
                    spec = response.json()
        except Exception as e:
            logger.error(f"Failed to fetch OpenAPI spec: {e}")
            return None

        # Extract info
        info = spec.get("info", {})
        servers = spec.get("servers", [])
        base_url = servers[0].get("url", "") if servers else ""

        tool_id = f"openapi.{name or info.get('title', 'unknown').lower().replace(' ', '_')}"

        tool = ToolSource(
            id=tool_id,
            name=name or info.get("title", "OpenAPI Tool"),
            description=info.get("description", ""),
            source_type=ToolSourceType.OPENAPI,
            transport=ToolTransport.HTTP,
            registry_origin=RegistryOrigin.MANUAL,
            spec_url=spec_url,
            base_url=base_url,
            status=ToolStatus.ACTIVE if auto_approve else ToolStatus.PENDING_APPROVAL,
            metadata={"strategy": strategy.value, "openapi_version": spec.get("openapi", "3.0.0")},
        )

        await self.save_tool_source(tool)

        # Create operations based on strategy
        if strategy == OpenAPIStrategy.DIRECT:
            await self._create_direct_operations(tool, spec)
        else:
            await self._create_meta_operations(tool, spec)

        # Extract capabilities
        await self._extract_capabilities(tool)

        return tool

    async def _create_direct_operations(self, tool: ToolSource, spec: Dict[str, Any]) -> None:
        """Create tool operations for each OpenAPI path/method."""
        paths = spec.get("paths", {})

        for path, methods in paths.items():
            for method, operation in methods.items():
                if method in ["get", "post", "put", "patch", "delete"]:
                    op_id = f"{tool.id}.{method}_{path.replace('/', '_').strip('_')}"

                    # Determine risk level
                    risk = RiskLevel.LOW
                    if method in ["post", "put", "patch"]:
                        risk = RiskLevel.MEDIUM
                    elif method == "delete":
                        risk = RiskLevel.HIGH

                    op = ToolOperation(
                        id=op_id,
                        name=operation.get("operationId", f"{method.upper()} {path}"),
                        description=operation.get("summary", operation.get("description", "")),
                        input_schema=operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}),
                        output_schema=operation.get("responses", {}).get("200", {}).get("content", {}).get("application/json", {}).get("schema", {}),
                        risk_level=risk,
                        tool_source_id=tool.id,
                    )

                    await self.save_operation(op)

    async def _create_meta_operations(self, tool: ToolSource, spec: Dict[str, Any]) -> None:
        """Create meta operations for OpenAPI spec."""
        operations = [
            ToolOperation(
                id=f"{tool.id}.list_endpoints",
                name="list_endpoints",
                description="List all available endpoints in this API",
                input_schema={},
                output_schema={"type": "array", "items": {"type": "string"}},
                risk_level=RiskLevel.LOW,
                tool_source_id=tool.id,
            ),
            ToolOperation(
                id=f"{tool.id}.get_schema",
                name="get_schema",
                description="Get the schema for a specific endpoint",
                input_schema={"type": "object", "properties": {"endpoint": {"type": "string"}}},
                output_schema={"type": "object"},
                risk_level=RiskLevel.LOW,
                tool_source_id=tool.id,
            ),
            ToolOperation(
                id=f"{tool.id}.invoke",
                name="invoke",
                description="Invoke an endpoint with parameters",
                input_schema={
                    "type": "object",
                    "properties": {
                        "endpoint": {"type": "string"},
                        "method": {"type": "string"},
                        "params": {"type": "object"},
                    },
                },
                output_schema={"type": "object"},
                risk_level=RiskLevel.MEDIUM,
                tool_source_id=tool.id,
            ),
        ]

        for op in operations:
            await self.save_operation(op)

    # =========================================================================
    # Statistics and Verification
    # =========================================================================

    async def get_statistics(self) -> Dict[str, Any]:
        """Get registry statistics."""
        tools = await self.list_tool_sources()
        agents = await self.list_agents()
        sources = await self.list_registry_sources()

        status_counts = {}
        for status in ToolStatus:
            count = sum(1 for t in tools if t.status == status)
            status_counts[status.value] = count

        type_counts = {}
        for source_type in ToolSourceType:
            count = sum(1 for t in tools if t.source_type == source_type)
            type_counts[source_type.value] = count

        return {
            "total_tools": len(tools),
            "total_agents": len(agents),
            "total_registry_sources": len(sources),
            "tools_by_status": status_counts,
            "tools_by_type": type_counts,
            "active_tools": status_counts.get("active", 0),
            "pending_approval": status_counts.get("pending_approval", 0),
        }

    async def verify_system(self) -> Dict[str, Any]:
        """Run verification queries on the system."""
        results = {}

        # Check tool sources
        tools = await self.list_tool_sources()
        results["tool_sources"] = [{"id": t.id, "status": t.status.value, "type": t.source_type.value} for t in tools[:20]]

        # Check agents
        agents = await self.list_agents()
        results["agents"] = [{"id": a.id, "name": a.name, "status": a.status} for a in agents]

        # Check registry sources
        sources = await self.list_registry_sources()
        results["registry_sources"] = [{"id": s.id, "name": s.name, "auto_approve": s.auto_approve} for s in sources]

        # Find tools by domain example
        filesystem_tools = await self.find_tools_by_domain("filesystem")
        results["filesystem_tools"] = [t.id for t in filesystem_tools]

        # Get pending tools
        pending = await self.get_pending_tools()
        results["pending_count"] = len(pending)

        return results


# =============================================================================
# Convenience Functions
# =============================================================================

async def get_tool_registry() -> ToolRegistry:
    """Get the tool registry instance."""
    return await ToolRegistry.get_instance()


async def sync_mcp_registry() -> SyncRun:
    """Sync from the official MCP registry."""
    registry = await get_tool_registry()
    return await registry.sync_mcp_registry()


async def find_tools_for_task(task_description: str) -> List[Dict[str, Any]]:
    """
    Find tools that can help with a task.

    This is a simplified version - full semantic search requires embeddings.
    """
    registry = await get_tool_registry()

    # Extract domain keywords from task
    task_lower = task_description.lower()

    domains_to_search = []
    domain_keywords = {
        "filesystem": ["file", "read", "write", "directory"],
        "database": ["database", "sql", "query"],
        "web": ["http", "api", "request", "url"],
        "git": ["git", "commit", "repository"],
        "shell": ["command", "shell", "execute"],
    }

    for domain, keywords in domain_keywords.items():
        if any(kw in task_lower for kw in keywords):
            domains_to_search.append(domain)

    if not domains_to_search:
        domains_to_search = ["general"]

    results = []
    seen = set()

    for domain in domains_to_search:
        tools = await registry.find_tools_by_domain(domain)
        for tool in tools:
            if tool.id not in seen:
                seen.add(tool.id)
                config = await registry.get_tool_config(tool.id)
                if config:
                    results.append(config)

    return results


async def approve_tool(
    tool_id: str,
    reasoning: str,
    risk_level: str = "low",
    conditions: List[str] = None,
) -> bool:
    """Approve a tool (Guardian function)."""
    registry = await get_tool_registry()
    record = await registry.record_approval_decision(
        tool_id=tool_id,
        decision=ApprovalDecision.APPROVE,
        risk_level=RiskLevel(risk_level),
        reasoning=reasoning,
        conditions=conditions,
    )
    return record is not None


async def deny_tool(tool_id: str, reasoning: str) -> bool:
    """Deny a tool (Guardian function)."""
    registry = await get_tool_registry()
    record = await registry.record_approval_decision(
        tool_id=tool_id,
        decision=ApprovalDecision.DENY,
        risk_level=RiskLevel.HIGH,
        reasoning=reasoning,
    )
    return record is not None
