"""
Collective Memory System for Vessels A0 Framework

This module implements a comprehensive collective memory system that records
all inputs, outputs, and interactions across the entire agent ecosystem.

The collective memory serves as:
1. A shared knowledge base across all agents
2. An audit trail for all operations
3. A learning substrate for continuous improvement
4. A source of truth for ethical compliance
"""

import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Types of memories that can be stored in collective memory."""

    # Input/Output Types
    USER_INPUT = "user_input"
    AGENT_OUTPUT = "agent_output"
    TOOL_INPUT = "tool_input"
    TOOL_OUTPUT = "tool_output"
    A2A_MESSAGE = "a2a_message"
    MCP_REQUEST = "mcp_request"
    MCP_RESPONSE = "mcp_response"

    # Operational Types
    AGENT_THOUGHT = "agent_thought"
    DECISION = "decision"
    PLAN = "plan"
    TASK = "task"

    # Knowledge Types
    FACT = "fact"
    INSIGHT = "insight"
    LEARNING = "learning"
    CORRECTION = "correction"

    # Ethical Types
    ETHICAL_VALIDATION = "ethical_validation"
    ETHICAL_VIOLATION = "ethical_violation"
    ETHICAL_APPROVAL = "ethical_approval"

    # System Types
    ERROR = "error"
    WARNING = "warning"
    METRIC = "metric"
    EVENT = "event"


class MemoryScope(Enum):
    """Scope/visibility of a memory."""
    AGENT = "agent"  # Visible only to the owning agent
    PROJECT = "project"  # Visible to all agents in a project
    GLOBAL = "global"  # Visible to all agents in the system
    PRIVATE = "private"  # Encrypted, restricted access


class MemoryPriority(Enum):
    """Priority levels for memory retention."""
    EPHEMERAL = 0  # Can be pruned immediately
    LOW = 1  # Can be pruned after short period
    NORMAL = 2  # Standard retention
    HIGH = 3  # Important, longer retention
    CRITICAL = 4  # Must not be pruned
    PERMANENT = 5  # Never prune


@dataclass
class MemoryEntry:
    """A single entry in the collective memory."""

    # Core fields
    memory_id: str
    memory_type: MemoryType
    content: Any
    timestamp: datetime

    # Attribution
    agent_id: Optional[str] = None
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    user_id: Optional[str] = None

    # Classification
    scope: MemoryScope = MemoryScope.AGENT
    priority: MemoryPriority = MemoryPriority.NORMAL

    # Relationships
    parent_id: Optional[str] = None
    related_ids: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Computed fields
    embedding: Optional[List[float]] = None
    content_hash: Optional[str] = None

    def __post_init__(self):
        if not self.content_hash and self.content:
            content_str = json.dumps(self.content) if not isinstance(self.content, str) else self.content
            self.content_hash = hashlib.sha256(content_str.encode()).hexdigest()[:32]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "memory_type": self.memory_type.value,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "scope": self.scope.value,
            "priority": self.priority.value,
            "parent_id": self.parent_id,
            "related_ids": self.related_ids,
            "tags": self.tags,
            "metadata": self.metadata,
            "content_hash": self.content_hash
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryEntry':
        return cls(
            memory_id=data["memory_id"],
            memory_type=MemoryType(data["memory_type"]),
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            agent_id=data.get("agent_id"),
            project_id=data.get("project_id"),
            session_id=data.get("session_id"),
            user_id=data.get("user_id"),
            scope=MemoryScope(data.get("scope", "agent")),
            priority=MemoryPriority(data.get("priority", 2)),
            parent_id=data.get("parent_id"),
            related_ids=data.get("related_ids", []),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            content_hash=data.get("content_hash")
        )


@dataclass
class MemoryQuery:
    """Query parameters for searching collective memory."""

    # Type filters
    memory_types: Optional[List[MemoryType]] = None
    scopes: Optional[List[MemoryScope]] = None
    min_priority: Optional[MemoryPriority] = None

    # Attribution filters
    agent_ids: Optional[List[str]] = None
    project_ids: Optional[List[str]] = None
    session_ids: Optional[List[str]] = None
    user_ids: Optional[List[str]] = None

    # Content filters
    text_query: Optional[str] = None
    tags: Optional[List[str]] = None
    parent_id: Optional[str] = None

    # Time filters
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

    # Pagination
    limit: int = 100
    offset: int = 0

    # Ordering
    order_by: str = "timestamp"
    order_desc: bool = True

    # Search options
    semantic_search: bool = False
    similarity_threshold: float = 0.7


class MemoryBackend(ABC):
    """Abstract base class for memory storage backends."""

    @abstractmethod
    async def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry and return its ID."""
        pass

    @abstractmethod
    async def retrieve(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by ID."""
        pass

    @abstractmethod
    async def search(self, query: MemoryQuery) -> List[MemoryEntry]:
        """Search for memory entries matching query."""
        pass

    @abstractmethod
    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """Update a memory entry."""
        pass

    @abstractmethod
    async def delete(self, memory_id: str) -> bool:
        """Delete a memory entry."""
        pass

    @abstractmethod
    async def count(self, query: Optional[MemoryQuery] = None) -> int:
        """Count memory entries matching query."""
        pass


class GraphMemoryBackend(MemoryBackend):
    """Memory backend that uses the graph store (FalkorDB + Graphiti)."""

    def __init__(self):
        self._graph_store = None

    async def _get_graph_store(self):
        """Lazy initialization of graph store."""
        if self._graph_store is None:
            from python.helpers.graph_store import GraphStore
            self._graph_store = await GraphStore.get_instance()
        return self._graph_store

    async def store(self, entry: MemoryEntry) -> str:
        graph = await self._get_graph_store()

        # Create node in graph
        node_data = entry.to_dict()
        node_data["node_type"] = "COLLECTIVE_MEMORY"

        try:
            await graph.create_node(
                node_type="COLLECTIVE_MEMORY",
                node_id=entry.memory_id,
                properties=node_data
            )

            # Create relationships
            if entry.parent_id:
                await graph.create_relationship(
                    from_id=entry.memory_id,
                    to_id=entry.parent_id,
                    rel_type="CHILD_OF"
                )

            for related_id in entry.related_ids:
                await graph.create_relationship(
                    from_id=entry.memory_id,
                    to_id=related_id,
                    rel_type="RELATED_TO"
                )

            # Add embedding for semantic search if content is text
            if isinstance(entry.content, str) and len(entry.content) > 10:
                await graph.add_embedding(
                    node_id=entry.memory_id,
                    text=entry.content
                )

            return entry.memory_id

        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            raise

    async def retrieve(self, memory_id: str) -> Optional[MemoryEntry]:
        graph = await self._get_graph_store()

        try:
            node = await graph.get_node(
                node_type="COLLECTIVE_MEMORY",
                node_id=memory_id
            )
            if node:
                return MemoryEntry.from_dict(node)
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve memory: {e}")
            return None

    async def search(self, query: MemoryQuery) -> List[MemoryEntry]:
        graph = await self._get_graph_store()

        try:
            # Build Cypher query
            conditions = ["n.node_type = 'COLLECTIVE_MEMORY'"]
            params = {}

            if query.memory_types:
                conditions.append("n.memory_type IN $memory_types")
                params["memory_types"] = [mt.value for mt in query.memory_types]

            if query.scopes:
                conditions.append("n.scope IN $scopes")
                params["scopes"] = [s.value for s in query.scopes]

            if query.agent_ids:
                conditions.append("n.agent_id IN $agent_ids")
                params["agent_ids"] = query.agent_ids

            if query.project_ids:
                conditions.append("n.project_id IN $project_ids")
                params["project_ids"] = query.project_ids

            if query.tags:
                conditions.append("ANY(tag IN $tags WHERE tag IN n.tags)")
                params["tags"] = query.tags

            if query.start_time:
                conditions.append("n.timestamp >= $start_time")
                params["start_time"] = query.start_time.isoformat()

            if query.end_time:
                conditions.append("n.timestamp <= $end_time")
                params["end_time"] = query.end_time.isoformat()

            if query.parent_id:
                conditions.append("n.parent_id = $parent_id")
                params["parent_id"] = query.parent_id

            # If semantic search and text query, use vector similarity
            if query.semantic_search and query.text_query:
                results = await graph.semantic_search(
                    text=query.text_query,
                    node_type="COLLECTIVE_MEMORY",
                    limit=query.limit,
                    threshold=query.similarity_threshold
                )
                return [MemoryEntry.from_dict(r) for r in results]

            # Otherwise use standard query
            where_clause = " AND ".join(conditions)
            order_dir = "DESC" if query.order_desc else "ASC"

            cypher = f"""
            MATCH (n)
            WHERE {where_clause}
            RETURN n
            ORDER BY n.{query.order_by} {order_dir}
            SKIP $offset
            LIMIT $limit
            """
            params["offset"] = query.offset
            params["limit"] = query.limit

            results = await graph.execute_query(cypher, params)
            return [MemoryEntry.from_dict(r["n"]) for r in results]

        except Exception as e:
            logger.error(f"Failed to search memories: {e}")
            return []

    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        graph = await self._get_graph_store()

        try:
            await graph.update_node(
                node_type="COLLECTIVE_MEMORY",
                node_id=memory_id,
                properties=updates
            )
            return True
        except Exception as e:
            logger.error(f"Failed to update memory: {e}")
            return False

    async def delete(self, memory_id: str) -> bool:
        graph = await self._get_graph_store()

        try:
            await graph.delete_node(
                node_type="COLLECTIVE_MEMORY",
                node_id=memory_id
            )
            return True
        except Exception as e:
            logger.error(f"Failed to delete memory: {e}")
            return False

    async def count(self, query: Optional[MemoryQuery] = None) -> int:
        graph = await self._get_graph_store()

        try:
            conditions = ["n.node_type = 'COLLECTIVE_MEMORY'"]
            params = {}

            if query:
                if query.memory_types:
                    conditions.append("n.memory_type IN $memory_types")
                    params["memory_types"] = [mt.value for mt in query.memory_types]

            where_clause = " AND ".join(conditions)

            cypher = f"""
            MATCH (n)
            WHERE {where_clause}
            RETURN count(n) as cnt
            """

            results = await graph.execute_query(cypher, params)
            return results[0]["cnt"] if results else 0

        except Exception as e:
            logger.error(f"Failed to count memories: {e}")
            return 0


class InMemoryBackend(MemoryBackend):
    """In-memory backend for testing or ephemeral storage."""

    def __init__(self):
        self._storage: Dict[str, MemoryEntry] = {}

    async def store(self, entry: MemoryEntry) -> str:
        self._storage[entry.memory_id] = entry
        return entry.memory_id

    async def retrieve(self, memory_id: str) -> Optional[MemoryEntry]:
        return self._storage.get(memory_id)

    async def search(self, query: MemoryQuery) -> List[MemoryEntry]:
        results = list(self._storage.values())

        # Apply filters
        if query.memory_types:
            results = [m for m in results if m.memory_type in query.memory_types]

        if query.scopes:
            results = [m for m in results if m.scope in query.scopes]

        if query.agent_ids:
            results = [m for m in results if m.agent_id in query.agent_ids]

        if query.project_ids:
            results = [m for m in results if m.project_id in query.project_ids]

        if query.tags:
            results = [m for m in results if any(t in m.tags for t in query.tags)]

        if query.start_time:
            results = [m for m in results if m.timestamp >= query.start_time]

        if query.end_time:
            results = [m for m in results if m.timestamp <= query.end_time]

        if query.parent_id:
            results = [m for m in results if m.parent_id == query.parent_id]

        if query.text_query:
            query_lower = query.text_query.lower()
            results = [m for m in results if query_lower in str(m.content).lower()]

        # Sort
        reverse = query.order_desc
        results.sort(key=lambda m: getattr(m, query.order_by, m.timestamp), reverse=reverse)

        # Paginate
        return results[query.offset:query.offset + query.limit]

    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        if memory_id not in self._storage:
            return False

        entry = self._storage[memory_id]
        for key, value in updates.items():
            if hasattr(entry, key):
                setattr(entry, key, value)
        return True

    async def delete(self, memory_id: str) -> bool:
        if memory_id in self._storage:
            del self._storage[memory_id]
            return True
        return False

    async def count(self, query: Optional[MemoryQuery] = None) -> int:
        if query is None:
            return len(self._storage)
        results = await self.search(query)
        return len(results)


class CollectiveMemory:
    """
    Central collective memory system that provides a unified interface
    for storing and retrieving memories across the agent ecosystem.

    This is a singleton that manages memory storage, retrieval, and
    coordination across all agents and components.
    """

    _instance: Optional['CollectiveMemory'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._backend: Optional[MemoryBackend] = None
        self._hooks: Dict[str, List[Callable]] = {
            "before_store": [],
            "after_store": [],
            "before_retrieve": [],
            "after_retrieve": [],
        }
        self._ethics_engine = None
        self._current_context: Dict[str, Any] = {}
        self._initialized = False

    @classmethod
    async def get_instance(cls, backend_type: str = "graph") -> 'CollectiveMemory':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize(backend_type)
            return cls._instance

    async def _initialize(self, backend_type: str = "graph"):
        """Initialize the collective memory system."""
        if self._initialized:
            return

        # Initialize backend
        if backend_type == "graph":
            try:
                self._backend = GraphMemoryBackend()
            except Exception as e:
                logger.warning(f"Graph backend not available, using in-memory: {e}")
                self._backend = InMemoryBackend()
        else:
            self._backend = InMemoryBackend()

        # Initialize ethics engine integration
        try:
            from python.helpers.ethics import EthicsEngine
            self._ethics_engine = await EthicsEngine.get_instance()
            self._ethics_engine.set_memory_recorder(self._record_ethical_validation)
        except Exception as e:
            logger.warning(f"Ethics engine not available: {e}")

        self._initialized = True
        logger.info(f"CollectiveMemory initialized with {backend_type} backend")

    async def _record_ethical_validation(self, record: Dict[str, Any]):
        """Callback for ethics engine to record validations."""
        await self.store(
            memory_type=MemoryType.ETHICAL_VALIDATION,
            content=record,
            scope=MemoryScope.GLOBAL,
            priority=MemoryPriority.HIGH,
            tags=["ethics", "validation"]
        )

    def set_context(
        self,
        agent_id: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None
    ):
        """Set the current context for memory operations."""
        if agent_id:
            self._current_context["agent_id"] = agent_id
        if project_id:
            self._current_context["project_id"] = project_id
        if session_id:
            self._current_context["session_id"] = session_id
        if user_id:
            self._current_context["user_id"] = user_id

    def clear_context(self):
        """Clear the current context."""
        self._current_context = {}

    def add_hook(self, hook_name: str, callback: Callable):
        """Add a hook callback."""
        if hook_name in self._hooks:
            self._hooks[hook_name].append(callback)

    async def _run_hooks(self, hook_name: str, data: Any) -> Any:
        """Run hooks and allow modification of data."""
        for hook in self._hooks.get(hook_name, []):
            try:
                result = hook(data)
                if asyncio.iscoroutine(result):
                    result = await result
                if result is not None:
                    data = result
            except Exception as e:
                logger.error(f"Hook {hook_name} failed: {e}")
        return data

    def _generate_id(self, content: Any, timestamp: datetime) -> str:
        """Generate a unique memory ID."""
        content_str = json.dumps(content) if not isinstance(content, str) else content
        unique = f"{timestamp.isoformat()}:{content_str[:100]}"
        return hashlib.sha256(unique.encode()).hexdigest()[:24]

    async def store(
        self,
        memory_type: MemoryType,
        content: Any,
        scope: MemoryScope = MemoryScope.AGENT,
        priority: MemoryPriority = MemoryPriority.NORMAL,
        parent_id: Optional[str] = None,
        related_ids: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Store a memory entry in the collective memory.

        Args:
            memory_type: Type of memory
            content: The content to store
            scope: Visibility scope
            priority: Retention priority
            parent_id: Optional parent memory ID
            related_ids: Optional related memory IDs
            tags: Optional tags for categorization
            metadata: Optional additional metadata
            **kwargs: Override context values (agent_id, project_id, etc.)

        Returns:
            The ID of the stored memory
        """
        timestamp = datetime.now()
        memory_id = self._generate_id(content, timestamp)

        entry = MemoryEntry(
            memory_id=memory_id,
            memory_type=memory_type,
            content=content,
            timestamp=timestamp,
            agent_id=kwargs.get("agent_id", self._current_context.get("agent_id")),
            project_id=kwargs.get("project_id", self._current_context.get("project_id")),
            session_id=kwargs.get("session_id", self._current_context.get("session_id")),
            user_id=kwargs.get("user_id", self._current_context.get("user_id")),
            scope=scope,
            priority=priority,
            parent_id=parent_id,
            related_ids=related_ids or [],
            tags=tags or [],
            metadata=metadata or {}
        )

        # Run before hooks
        entry = await self._run_hooks("before_store", entry)

        # Validate with ethics if not an ethics record itself
        if memory_type not in (MemoryType.ETHICAL_VALIDATION, MemoryType.ETHICAL_VIOLATION) and self._ethics_engine:
            validation = await self._ethics_engine.validate(
                action_type="memory_store",
                data={"content": content, "memory_type": memory_type.value},
                context={"consent_verified": True}
            )
            if validation.is_blocked:
                raise ValueError(f"Memory storage blocked: {validation.explanation}")

        # Store
        await self._backend.store(entry)

        # Run after hooks
        await self._run_hooks("after_store", entry)

        logger.debug(f"Stored memory {memory_id} of type {memory_type.value}")
        return memory_id

    async def retrieve(self, memory_id: str) -> Optional[MemoryEntry]:
        """Retrieve a specific memory by ID."""
        await self._run_hooks("before_retrieve", memory_id)
        entry = await self._backend.retrieve(memory_id)
        await self._run_hooks("after_retrieve", entry)
        return entry

    async def search(self, query: MemoryQuery) -> List[MemoryEntry]:
        """Search for memories matching the query."""
        return await self._backend.search(query)

    async def update(self, memory_id: str, updates: Dict[str, Any]) -> bool:
        """Update a memory entry."""
        return await self._backend.update(memory_id, updates)

    async def delete(self, memory_id: str) -> bool:
        """Delete a memory entry."""
        return await self._backend.delete(memory_id)

    async def count(self, query: Optional[MemoryQuery] = None) -> int:
        """Count memories matching a query."""
        return await self._backend.count(query)

    # Convenience methods for recording specific types

    async def record_user_input(
        self,
        content: str,
        user_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """Record a user input."""
        return await self.store(
            memory_type=MemoryType.USER_INPUT,
            content=content,
            scope=MemoryScope.PROJECT,
            priority=MemoryPriority.NORMAL,
            user_id=user_id,
            tags=["input", "user"],
            **kwargs
        )

    async def record_agent_output(
        self,
        content: str,
        agent_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """Record an agent output."""
        return await self.store(
            memory_type=MemoryType.AGENT_OUTPUT,
            content=content,
            scope=MemoryScope.PROJECT,
            priority=MemoryPriority.NORMAL,
            agent_id=agent_id,
            tags=["output", "agent"],
            **kwargs
        )

    async def record_tool_execution(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        tool_output: Any,
        execution_time: float,
        success: bool,
        **kwargs
    ) -> Tuple[str, str]:
        """Record a tool execution (input and output)."""
        timestamp = datetime.now()

        input_id = await self.store(
            memory_type=MemoryType.TOOL_INPUT,
            content={
                "tool_name": tool_name,
                "args": tool_input
            },
            priority=MemoryPriority.NORMAL,
            tags=["tool", tool_name, "input"],
            metadata={"execution_start": timestamp.isoformat()},
            **kwargs
        )

        output_id = await self.store(
            memory_type=MemoryType.TOOL_OUTPUT,
            content={
                "tool_name": tool_name,
                "result": tool_output,
                "success": success,
                "execution_time_ms": execution_time
            },
            priority=MemoryPriority.NORMAL,
            parent_id=input_id,
            tags=["tool", tool_name, "output", "success" if success else "failure"],
            metadata={"execution_end": datetime.now().isoformat()},
            **kwargs
        )

        return input_id, output_id

    async def record_a2a_message(
        self,
        from_agent: str,
        to_agent: str,
        message: str,
        direction: str = "outgoing",
        **kwargs
    ) -> str:
        """Record an agent-to-agent message."""
        return await self.store(
            memory_type=MemoryType.A2A_MESSAGE,
            content={
                "from_agent": from_agent,
                "to_agent": to_agent,
                "message": message,
                "direction": direction
            },
            scope=MemoryScope.GLOBAL,
            priority=MemoryPriority.HIGH,
            tags=["a2a", direction, from_agent, to_agent],
            **kwargs
        )

    async def record_mcp_interaction(
        self,
        server_name: str,
        tool_name: str,
        request: Dict[str, Any],
        response: Any,
        success: bool,
        **kwargs
    ) -> Tuple[str, str]:
        """Record an MCP interaction."""
        request_id = await self.store(
            memory_type=MemoryType.MCP_REQUEST,
            content={
                "server": server_name,
                "tool": tool_name,
                "request": request
            },
            priority=MemoryPriority.NORMAL,
            tags=["mcp", server_name, tool_name, "request"],
            **kwargs
        )

        response_id = await self.store(
            memory_type=MemoryType.MCP_RESPONSE,
            content={
                "server": server_name,
                "tool": tool_name,
                "response": response,
                "success": success
            },
            priority=MemoryPriority.NORMAL,
            parent_id=request_id,
            tags=["mcp", server_name, tool_name, "response", "success" if success else "failure"],
            **kwargs
        )

        return request_id, response_id

    async def record_decision(
        self,
        decision: str,
        reasoning: str,
        options_considered: List[str],
        **kwargs
    ) -> str:
        """Record a decision made by an agent."""
        return await self.store(
            memory_type=MemoryType.DECISION,
            content={
                "decision": decision,
                "reasoning": reasoning,
                "options_considered": options_considered
            },
            scope=MemoryScope.PROJECT,
            priority=MemoryPriority.HIGH,
            tags=["decision"],
            **kwargs
        )

    async def record_learning(
        self,
        subject: str,
        insight: str,
        source: str,
        confidence: float = 1.0,
        **kwargs
    ) -> str:
        """Record a learning/insight."""
        return await self.store(
            memory_type=MemoryType.LEARNING,
            content={
                "subject": subject,
                "insight": insight,
                "source": source,
                "confidence": confidence
            },
            scope=MemoryScope.GLOBAL,
            priority=MemoryPriority.HIGH,
            tags=["learning", subject],
            **kwargs
        )

    async def record_error(
        self,
        error_type: str,
        message: str,
        context: Dict[str, Any],
        stack_trace: Optional[str] = None,
        **kwargs
    ) -> str:
        """Record an error."""
        return await self.store(
            memory_type=MemoryType.ERROR,
            content={
                "error_type": error_type,
                "message": message,
                "context": context,
                "stack_trace": stack_trace
            },
            scope=MemoryScope.PROJECT,
            priority=MemoryPriority.HIGH,
            tags=["error", error_type],
            **kwargs
        )

    async def get_recent_memories(
        self,
        limit: int = 50,
        memory_types: Optional[List[MemoryType]] = None
    ) -> List[MemoryEntry]:
        """Get recent memories."""
        query = MemoryQuery(
            memory_types=memory_types,
            limit=limit,
            order_by="timestamp",
            order_desc=True
        )
        return await self.search(query)

    async def get_agent_memories(
        self,
        agent_id: str,
        limit: int = 100
    ) -> List[MemoryEntry]:
        """Get memories for a specific agent."""
        query = MemoryQuery(
            agent_ids=[agent_id],
            limit=limit,
            order_by="timestamp",
            order_desc=True
        )
        return await self.search(query)

    async def get_project_memories(
        self,
        project_id: str,
        limit: int = 100
    ) -> List[MemoryEntry]:
        """Get memories for a specific project."""
        query = MemoryQuery(
            project_ids=[project_id],
            scopes=[MemoryScope.PROJECT, MemoryScope.GLOBAL],
            limit=limit,
            order_by="timestamp",
            order_desc=True
        )
        return await self.search(query)

    async def semantic_search(
        self,
        query_text: str,
        limit: int = 20,
        memory_types: Optional[List[MemoryType]] = None
    ) -> List[MemoryEntry]:
        """Perform semantic search on memories."""
        query = MemoryQuery(
            text_query=query_text,
            memory_types=memory_types,
            limit=limit,
            semantic_search=True
        )
        return await self.search(query)

    async def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about the collective memory."""
        total = await self.count()

        stats = {
            "total_memories": total,
            "by_type": {},
            "by_scope": {},
            "by_priority": {}
        }

        for mt in MemoryType:
            count = await self.count(MemoryQuery(memory_types=[mt]))
            if count > 0:
                stats["by_type"][mt.value] = count

        for scope in MemoryScope:
            count = await self.count(MemoryQuery(scopes=[scope]))
            if count > 0:
                stats["by_scope"][scope.value] = count

        return stats


# Convenience functions for direct use
async def get_collective_memory(backend_type: str = "graph") -> CollectiveMemory:
    """Get the collective memory instance."""
    return await CollectiveMemory.get_instance(backend_type)


async def record_input(content: str, **kwargs) -> str:
    """Record user input to collective memory."""
    memory = await get_collective_memory()
    return await memory.record_user_input(content, **kwargs)


async def record_output(content: str, **kwargs) -> str:
    """Record agent output to collective memory."""
    memory = await get_collective_memory()
    return await memory.record_agent_output(content, **kwargs)


async def record_tool(
    tool_name: str,
    tool_input: Dict[str, Any],
    tool_output: Any,
    execution_time: float,
    success: bool,
    **kwargs
) -> Tuple[str, str]:
    """Record tool execution to collective memory."""
    memory = await get_collective_memory()
    return await memory.record_tool_execution(
        tool_name, tool_input, tool_output, execution_time, success, **kwargs
    )
