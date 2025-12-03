"""
Vessels Graph Store - FalkorDB + Graphiti Integration

This module provides a unified graph-based storage layer for Vessels,
replacing all file-based and FAISS vector storage with a temporal
knowledge graph powered by FalkorDB and Graphiti.

Storage domains:
- Memories: Agent memories with semantic search and temporal tracking
- Chats: Conversation persistence as graph episodes
- Knowledge: Document ingestion as graph nodes
- Settings: Configuration stored as graph properties
- History: Conversation history as connected episodes
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, TypeVar, Generic
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

from pydantic import BaseModel, Field

# Graphiti imports
try:
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EpisodeType, EntityNode, EpisodicNode
    from graphiti_core.edges import EntityEdge, EpisodicEdge
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client import LLMClient
    from graphiti_core.embedder import EmbedderClient
    GRAPHITI_AVAILABLE = True
except ImportError:
    GRAPHITI_AVAILABLE = False
    Graphiti = None
    FalkorDriver = None

from python.helpers.print_style import PrintStyle
from python.helpers.guardians import guard_memory


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class GraphStoreConfig:
    """Configuration for the graph store connection."""
    host: str = "localhost"
    port: int = 6379
    username: str = ""
    password: str = ""
    database: str = "vessels"

    # LLM configuration for Graphiti
    llm_provider: str = "openai"  # or "anthropic"
    llm_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    @classmethod
    def from_env(cls) -> "GraphStoreConfig":
        """Load configuration from environment variables."""
        return cls(
            host=os.getenv("FALKORDB_HOST", "localhost"),
            port=int(os.getenv("FALKORDB_PORT", "6379")),
            username=os.getenv("FALKORDB_USERNAME", ""),
            password=os.getenv("FALKORDB_PASSWORD", ""),
            database=os.getenv("FALKORDB_DATABASE", "vessels"),
            llm_provider=os.getenv("GRAPHITI_LLM_PROVIDER", "openai"),
            llm_model=os.getenv("GRAPHITI_LLM_MODEL", "gpt-4o-mini"),
            embedding_model=os.getenv("GRAPHITI_EMBEDDING_MODEL", "text-embedding-3-small"),
        )


# =============================================================================
# Node Types for Vessels
# =============================================================================

class VesselNodeType(str, Enum):
    """Types of nodes in the Vessels knowledge graph."""
    MEMORY = "memory"
    CHAT = "chat"
    MESSAGE = "message"
    AGENT = "agent"
    KNOWLEDGE = "knowledge"
    SETTING = "setting"
    PROJECT = "project"
    TASK = "task"
    CODE = "code"           # Reusable code snippets for agentic execution
    EXECUTION = "execution" # Execution history and results
    # Moral Geometry types
    MORAL_VECTOR = "moral_vector"
    MORAL_TRAJECTORY = "moral_trajectory"
    SPECTRAL_DECOMPOSITION = "spectral_decomposition"
    MORAL_DISTANCE = "moral_distance"
    # Kala types - Contribution Visibility
    KALA_EVENT = "kala_event"
    KALA_PARTICIPATION = "kala_participation"
    KALA_PATTERN = "kala_pattern"
    KALA_ATTRACTOR = "kala_attractor"
    # Persona & Voice types - Agent Identity
    PERSONA = "persona"
    VOICE_PROFILE = "voice_profile"
    VOICE_SESSION = "voice_session"
    EMOTIONAL_STATE = "emotional_state"
    HUME_CONFIG = "hume_config"
    # Entity Ontology types - Universal Entities
    ENTITY = "entity"                       # Universal entity persona
    ELICITATION_SESSION = "elicitation_session"  # Persona discovery session
    SPOKESPERSON = "spokesperson"           # Who speaks for non-self-voiced entities
    SENSOR_SOURCE = "sensor_source"         # Data streams representing entities
    STORY = "story"                         # Defining narratives
    BOUNDARY = "boundary"                   # Entity limits and edges
    CYCLE = "cycle"                         # Rhythms and patterns


class MemoryArea(str, Enum):
    """Memory storage areas (compatible with legacy Memory.Area)."""
    MAIN = "main"
    FRAGMENTS = "fragments"
    SOLUTIONS = "solutions"
    INSTRUMENTS = "instruments"


class MoralGeometryArea(str, Enum):
    """Storage areas for moral geometry data."""
    VECTORS = "vectors"
    TRAJECTORIES = "trajectories"
    DECOMPOSITIONS = "decompositions"
    DISTANCES = "distances"


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class MemoryDocument:
    """A memory document stored in the graph."""
    id: str
    content: str
    area: MemoryArea = MemoryArea.MAIN
    timestamp: str = ""
    metadata: dict = field(default_factory=dict)
    embedding: list[float] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "area": self.area.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryDocument":
        return cls(
            id=data["id"],
            content=data["content"],
            area=MemoryArea(data.get("area", "main")),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ChatDocument:
    """A chat/conversation stored in the graph."""
    id: str
    name: str
    created_at: datetime
    last_message: datetime
    context_type: str = "user"
    agents: list[dict] = field(default_factory=list)
    log: dict = field(default_factory=dict)
    data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "last_message": self.last_message.isoformat(),
            "context_type": self.context_type,
            "agents": self.agents,
            "log": self.log,
            "data": self.data,
            "output_data": self.output_data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ChatDocument":
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_message=datetime.fromisoformat(data["last_message"]),
            context_type=data.get("context_type", "user"),
            agents=data.get("agents", []),
            log=data.get("log", {}),
            data=data.get("data", {}),
            output_data=data.get("output_data", {}),
        )


@dataclass
class SettingDocument:
    """A setting stored in the graph."""
    key: str
    value: Any
    category: str = "general"
    updated_at: str = ""

    def __post_init__(self):
        if not self.updated_at:
            self.updated_at = datetime.now(timezone.utc).isoformat()


# =============================================================================
# Graph Store Implementation
# =============================================================================

class GraphStore:
    """
    Unified graph-based storage for Vessels using FalkorDB + Graphiti.

    This replaces:
    - FAISS vector database (memory.py, vector_db.py)
    - File-based chat persistence (persist_chat.py)
    - File-based settings (settings.py)
    - File-based knowledge import (knowledge_import.py)
    """

    _instance: Optional["GraphStore"] = None
    _lock = asyncio.Lock()

    def __init__(self, config: Optional[GraphStoreConfig] = None):
        self.config = config or GraphStoreConfig.from_env()
        self._graphiti: Optional[Graphiti] = None
        self._driver: Optional[FalkorDriver] = None
        self._initialized = False
        self._embedder = None
        self._llm_client = None

    @classmethod
    async def get_instance(cls, config: Optional[GraphStoreConfig] = None) -> "GraphStore":
        """Get or create the singleton graph store instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls(config)
                await cls._instance.initialize()
            return cls._instance

    @classmethod
    def get_instance_sync(cls, config: Optional[GraphStoreConfig] = None) -> "GraphStore":
        """Synchronous version of get_instance for initialization."""
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    async def initialize(self) -> None:
        """Initialize the graph store connection and indices."""
        if self._initialized:
            return

        if not GRAPHITI_AVAILABLE:
            raise ImportError(
                "Graphiti is not installed. Install with: "
                "pip install graphiti-core[falkordb]"
            )

        PrintStyle.standard("Initializing Vessels Graph Store (FalkorDB + Graphiti)...")

        try:
            # Create FalkorDB driver
            self._driver = FalkorDriver(
                host=self.config.host,
                port=self.config.port,
                username=self.config.username if self.config.username else None,
                password=self.config.password if self.config.password else None,
                database=self.config.database,
            )

            # Initialize Graphiti with the driver
            self._graphiti = Graphiti(graph_driver=self._driver)

            # Build indices and constraints
            await self._graphiti.build_indices_and_constraints()

            self._initialized = True
            PrintStyle.standard("Graph Store initialized successfully")

        except Exception as e:
            PrintStyle.error(f"Failed to initialize Graph Store: {e}")
            raise

    async def close(self) -> None:
        """Close the graph store connection."""
        if self._graphiti:
            await self._graphiti.close()
        self._initialized = False
        GraphStore._instance = None

    @property
    def graphiti(self) -> Graphiti:
        """Get the Graphiti instance."""
        if not self._graphiti:
            raise RuntimeError("Graph Store not initialized. Call initialize() first.")
        return self._graphiti

    # =========================================================================
    # Memory Operations (replaces memory.py / FAISS)
    # =========================================================================

    async def save_memory(
        self,
        content: str,
        area: MemoryArea = MemoryArea.MAIN,
        metadata: Optional[dict] = None,
        memory_subdir: str = "default",
    ) -> str:
        """
        Save a memory to the graph.

        Replaces: Memory.insert_text()
        """
        from python.helpers import guids

        memory_id = guids.generate_id(10)
        timestamp = datetime.now(timezone.utc)

        # Create episode for the memory
        episode_content = f"[Memory:{area.value}] {content}"
        if metadata:
            episode_content += f"\nMetadata: {json.dumps(metadata)}"

        await self._graphiti.add_episode(
            name=f"memory_{memory_id}",
            episode_body=episode_content,
            source=EpisodeType.text,
            reference_time=timestamp,
            group_id=f"{memory_subdir}:{area.value}",
        )

        return memory_id

    async def search_memories(
        self,
        query: str,
        limit: int = 10,
        threshold: float = 0.7,
        area: Optional[MemoryArea] = None,
        memory_subdir: str = "default",
    ) -> list[dict]:
        """
        Search memories using hybrid retrieval.

        Replaces: Memory.search_similarity_threshold()
        """
        group_id = f"{memory_subdir}:{area.value}" if area else memory_subdir

        # Use Graphiti's hybrid search
        results = await self._graphiti.search(
            query=query,
            num_results=limit,
            group_ids=[group_id] if area else None,
        )

        # Convert to legacy format
        memories = []
        for result in results:
            content = result.fact if hasattr(result, 'fact') else str(result)
            # Guard memory content - stored data may contain injection patterns
            content = guard_memory(content, source="graph_store:memories")
            memories.append({
                "id": result.uuid,
                "content": content,
                "score": getattr(result, 'score', 1.0),
                "metadata": {
                    "area": area.value if area else "main",
                    "timestamp": getattr(result, 'created_at', datetime.now()).isoformat(),
                },
            })

        return memories

    async def delete_memories(
        self,
        ids: list[str],
        memory_subdir: str = "default",
    ) -> int:
        """
        Delete memories by IDs.

        Replaces: Memory.delete_documents_by_ids()
        """
        deleted = 0
        for memory_id in ids:
            try:
                # Query to find and delete the memory node
                query = f"""
                MATCH (n) WHERE n.name = 'memory_{memory_id}'
                DETACH DELETE n
                """
                await self._driver.execute_query(query)
                deleted += 1
            except Exception as e:
                PrintStyle.error(f"Failed to delete memory {memory_id}: {e}")

        return deleted

    async def get_memory_by_id(
        self,
        memory_id: str,
        memory_subdir: str = "default",
    ) -> Optional[dict]:
        """Get a specific memory by ID."""
        query = f"""
        MATCH (n) WHERE n.name = 'memory_{memory_id}'
        RETURN n
        """
        result = await self._driver.execute_query(query)

        if result and len(result) > 0:
            node = result[0]
            return {
                "id": memory_id,
                "content": node.get("content", ""),
                "metadata": node.get("metadata", {}),
            }
        return None

    # =========================================================================
    # Chat Operations (replaces persist_chat.py)
    # =========================================================================

    async def save_chat(self, chat: ChatDocument) -> None:
        """
        Save a chat/conversation to the graph.

        Replaces: save_tmp_chat()
        """
        # Store chat as an episode with full serialization
        chat_content = json.dumps(chat.to_dict())

        await self._graphiti.add_episode(
            name=f"chat_{chat.id}",
            episode_body=chat_content,
            source=EpisodeType.json,
            reference_time=chat.last_message,
            group_id="chats",
        )

    async def load_chat(self, chat_id: str) -> Optional[ChatDocument]:
        """
        Load a chat from the graph.

        Replaces: load_tmp_chats() for single chat
        """
        query = f"""
        MATCH (n:Episode) WHERE n.name = 'chat_{chat_id}'
        RETURN n.content as content
        """
        result = await self._driver.execute_query(query)

        if result and len(result) > 0:
            content = result[0].get("content", "{}")
            data = json.loads(content)
            return ChatDocument.from_dict(data)
        return None

    async def load_all_chats(self) -> list[ChatDocument]:
        """
        Load all chats from the graph.

        Replaces: load_tmp_chats()
        """
        query = """
        MATCH (n:Episode) WHERE n.name STARTS WITH 'chat_'
        RETURN n.content as content, n.name as name
        ORDER BY n.reference_time DESC
        """
        results = await self._driver.execute_query(query)

        chats = []
        for row in results:
            try:
                content = row.get("content", "{}")
                data = json.loads(content)
                chats.append(ChatDocument.from_dict(data))
            except Exception as e:
                PrintStyle.error(f"Failed to load chat: {e}")

        return chats

    async def delete_chat(self, chat_id: str) -> bool:
        """
        Delete a chat from the graph.

        Replaces: remove_chat()
        """
        query = f"""
        MATCH (n:Episode) WHERE n.name = 'chat_{chat_id}'
        DETACH DELETE n
        """
        try:
            await self._driver.execute_query(query)
            return True
        except Exception as e:
            PrintStyle.error(f"Failed to delete chat {chat_id}: {e}")
            return False

    # =========================================================================
    # Settings Operations (replaces settings.py file storage)
    # =========================================================================

    async def save_setting(self, key: str, value: Any, category: str = "general") -> None:
        """Save a setting to the graph."""
        setting_content = json.dumps({
            "key": key,
            "value": value,
            "category": category,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        # Upsert pattern - delete old and insert new
        await self.delete_setting(key)

        await self._graphiti.add_episode(
            name=f"setting_{key}",
            episode_body=setting_content,
            source=EpisodeType.json,
            reference_time=datetime.now(timezone.utc),
            group_id="settings",
        )

    async def load_setting(self, key: str) -> Optional[Any]:
        """Load a setting from the graph."""
        query = f"""
        MATCH (n:Episode) WHERE n.name = 'setting_{key}'
        RETURN n.content as content
        """
        result = await self._driver.execute_query(query)

        if result and len(result) > 0:
            content = result[0].get("content", "{}")
            data = json.loads(content)
            return data.get("value")
        return None

    async def load_all_settings(self) -> dict[str, Any]:
        """Load all settings from the graph."""
        query = """
        MATCH (n:Episode) WHERE n.name STARTS WITH 'setting_'
        RETURN n.content as content
        """
        results = await self._driver.execute_query(query)

        settings = {}
        for row in results:
            try:
                content = row.get("content", "{}")
                data = json.loads(content)
                settings[data["key"]] = data["value"]
            except Exception as e:
                PrintStyle.error(f"Failed to load setting: {e}")

        return settings

    async def delete_setting(self, key: str) -> bool:
        """Delete a setting from the graph."""
        query = f"""
        MATCH (n:Episode) WHERE n.name = 'setting_{key}'
        DETACH DELETE n
        """
        try:
            await self._driver.execute_query(query)
            return True
        except Exception:
            return False

    # =========================================================================
    # Secrets Operations (replaces secrets.py file storage)
    # =========================================================================

    async def save_secrets(self, content: str) -> None:
        """Save secrets content (raw .env format) to the graph."""
        secrets_data = json.dumps({
            "content": content,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        # Upsert - delete old and insert new
        await self.delete_secrets()

        await self._graphiti.add_episode(
            name="secrets_store",
            episode_body=secrets_data,
            source=EpisodeType.json,
            reference_time=datetime.now(timezone.utc),
            group_id="secrets",
        )

    async def load_secrets(self) -> Optional[str]:
        """Load secrets content from the graph. Returns raw .env format string."""
        query = """
        MATCH (n:Episode) WHERE n.name = 'secrets_store'
        RETURN n.content as content
        """
        result = await self._driver.execute_query(query)

        if result and len(result) > 0:
            try:
                data = json.loads(result[0].get("content", "{}"))
                return data.get("content")
            except Exception:
                pass
        return None

    async def delete_secrets(self) -> bool:
        """Delete secrets from the graph."""
        query = """
        MATCH (n:Episode) WHERE n.name = 'secrets_store'
        DETACH DELETE n
        """
        try:
            await self._driver.execute_query(query)
            return True
        except Exception:
            return False

    # =========================================================================
    # Knowledge Operations (replaces knowledge_import.py)
    # =========================================================================

    async def import_knowledge(
        self,
        content: str,
        source_file: str,
        area: MemoryArea = MemoryArea.MAIN,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Import knowledge document into the graph.

        Replaces: knowledge_import.load_knowledge()
        """
        from python.helpers import guids

        knowledge_id = guids.generate_id(10)

        full_metadata = {
            "source_file": source_file,
            "area": area.value,
            "knowledge_source": True,
            "import_timestamp": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }

        episode_content = f"[Knowledge:{source_file}]\n{content}\nMetadata: {json.dumps(full_metadata)}"

        await self._graphiti.add_episode(
            name=f"knowledge_{knowledge_id}",
            episode_body=episode_content,
            source=EpisodeType.text,
            reference_time=datetime.now(timezone.utc),
            group_id=f"knowledge:{area.value}",
        )

        return knowledge_id

    async def search_knowledge(
        self,
        query: str,
        limit: int = 10,
        area: Optional[MemoryArea] = None,
    ) -> list[dict]:
        """Search knowledge base using hybrid retrieval."""
        group_id = f"knowledge:{area.value}" if area else None

        results = await self._graphiti.search(
            query=query,
            num_results=limit,
            group_ids=[group_id] if group_id else None,
        )

        knowledge_items = []
        for result in results:
            content = result.fact if hasattr(result, 'fact') else str(result)
            # Guard knowledge content - stored data may contain injection patterns
            content = guard_memory(content, source="graph_store:knowledge")
            knowledge_items.append({
                "id": result.uuid,
                "content": content,
                "score": getattr(result, 'score', 1.0),
            })

        return knowledge_items

    # =========================================================================
    # Content Store Operations (replaces file-based .md storage)
    # =========================================================================

    async def save_content(self, path: str, content: str, content_type: str = "prompt") -> None:
        """
        Save file content to the graph, keyed by relative path.

        Args:
            path: Relative path (e.g., 'prompts/agent.system.main.md')
            content: Raw file content
            content_type: Type of content (prompt, doc, instrument, knowledge)
        """
        # Normalize path
        path = path.replace("\\", "/").lstrip("/")

        content_data = json.dumps({
            "path": path,
            "content": content,
            "content_type": content_type,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        # Upsert - delete old and insert new
        await self.delete_content(path)

        await self._graphiti.add_episode(
            name=f"content:{path}",
            episode_body=content_data,
            source=EpisodeType.json,
            reference_time=datetime.now(timezone.utc),
            group_id=f"content:{content_type}",
        )

    async def get_content(self, path: str) -> Optional[str]:
        """
        Get file content from the graph by path.

        Returns: Raw file content or None if not found
        """
        path = path.replace("\\", "/").lstrip("/")

        query = f"""
        MATCH (n:Episode) WHERE n.name = 'content:{path}'
        RETURN n.content as content
        """
        result = await self._driver.execute_query(query)

        if result and len(result) > 0:
            try:
                data = json.loads(result[0].get("content", "{}"))
                return data.get("content")
            except json.JSONDecodeError:
                return None
        return None

    async def content_exists(self, path: str) -> bool:
        """Check if content exists for the given path."""
        path = path.replace("\\", "/").lstrip("/")

        query = f"""
        MATCH (n:Episode) WHERE n.name = 'content:{path}'
        RETURN count(n) as count
        """
        result = await self._driver.execute_query(query)

        if result and len(result) > 0:
            return result[0].get("count", 0) > 0
        return False

    async def delete_content(self, path: str) -> bool:
        """Delete content by path."""
        path = path.replace("\\", "/").lstrip("/")

        query = f"""
        MATCH (n:Episode) WHERE n.name = 'content:{path}'
        DETACH DELETE n
        """
        try:
            await self._driver.execute_query(query)
            return True
        except Exception:
            return False

    async def list_content(self, content_type: Optional[str] = None) -> list[str]:
        """List all content paths, optionally filtered by type."""
        if content_type:
            query = f"""
            MATCH (n:Episode) WHERE n.name STARTS WITH 'content:' AND n.group_id = 'content:{content_type}'
            RETURN n.name as name
            """
        else:
            query = """
            MATCH (n:Episode) WHERE n.name STARTS WITH 'content:'
            RETURN n.name as name
            """

        results = await self._driver.execute_query(query)

        paths = []
        for row in results:
            name = row.get("name", "")
            if name.startswith("content:"):
                paths.append(name[8:])  # Remove 'content:' prefix

        return paths

    async def get_all_content(self, content_type: Optional[str] = None) -> dict[str, str]:
        """Get all content as a dict of path -> content."""
        if content_type:
            query = f"""
            MATCH (n:Episode) WHERE n.name STARTS WITH 'content:' AND n.group_id = 'content:{content_type}'
            RETURN n.name as name, n.content as content
            """
        else:
            query = """
            MATCH (n:Episode) WHERE n.name STARTS WITH 'content:'
            RETURN n.name as name, n.content as content
            """

        results = await self._driver.execute_query(query)

        content_map = {}
        for row in results:
            name = row.get("name", "")
            if name.startswith("content:"):
                path = name[8:]
                try:
                    data = json.loads(row.get("content", "{}"))
                    content_map[path] = data.get("content", "")
                except json.JSONDecodeError:
                    pass

        return content_map

    # =========================================================================
    # Moral Geometry Operations
    # =========================================================================

    async def save_moral_vector(
        self,
        vector_id: str,
        vector_data: dict,
        agent_id: str = "default",
    ) -> str:
        """
        Save a moral vector to the graph.

        Args:
            vector_id: Unique identifier for the vector
            vector_data: Dict containing moral vector data
            agent_id: Agent that created/owns this vector

        Returns: The vector ID
        """
        content = json.dumps({
            "type": VesselNodeType.MORAL_VECTOR.value,
            "agent_id": agent_id,
            "data": vector_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"moral/vectors/{vector_id}",
            content,
            content_type="moral_geometry"
        )

        return vector_id

    async def load_moral_vector(self, vector_id: str) -> Optional[dict]:
        """Load a moral vector from the graph."""
        content = await self.get_content(f"moral/vectors/{vector_id}")

        if content:
            try:
                data = json.loads(content)
                if data.get("type") == VesselNodeType.MORAL_VECTOR.value:
                    return data.get("data")
            except json.JSONDecodeError:
                pass

        return None

    async def save_moral_trajectory(
        self,
        trajectory_id: str,
        trajectory_data: dict,
        entity_id: str = "default",
    ) -> str:
        """
        Save a moral trajectory to the graph.

        Args:
            trajectory_id: Unique identifier for the trajectory
            trajectory_data: Dict containing trajectory data with waypoints
            entity_id: Entity (agent, action sequence) being tracked

        Returns: The trajectory ID
        """
        content = json.dumps({
            "type": VesselNodeType.MORAL_TRAJECTORY.value,
            "entity_id": entity_id,
            "data": trajectory_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"moral/trajectories/{trajectory_id}",
            content,
            content_type="moral_geometry"
        )

        return trajectory_id

    async def load_moral_trajectory(self, trajectory_id: str) -> Optional[dict]:
        """Load a moral trajectory from the graph."""
        content = await self.get_content(f"moral/trajectories/{trajectory_id}")

        if content:
            try:
                data = json.loads(content)
                if data.get("type") == VesselNodeType.MORAL_TRAJECTORY.value:
                    return data.get("data")
            except json.JSONDecodeError:
                pass

        return None

    async def save_spectral_decomposition(
        self,
        decomposition_id: str,
        decomposition_data: dict,
        source_vectors: list[str] = None,
    ) -> str:
        """
        Save a spectral decomposition to the graph.

        Args:
            decomposition_id: Unique identifier
            decomposition_data: Dict containing eigenvalues, eigenvectors, harmonics
            source_vectors: IDs of vectors used in decomposition

        Returns: The decomposition ID
        """
        content = json.dumps({
            "type": VesselNodeType.SPECTRAL_DECOMPOSITION.value,
            "source_vectors": source_vectors or [],
            "data": decomposition_data,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"moral/spectral/{decomposition_id}",
            content,
            content_type="moral_geometry"
        )

        return decomposition_id

    async def load_spectral_decomposition(self, decomposition_id: str) -> Optional[dict]:
        """Load a spectral decomposition from the graph."""
        content = await self.get_content(f"moral/spectral/{decomposition_id}")

        if content:
            try:
                data = json.loads(content)
                if data.get("type") == VesselNodeType.SPECTRAL_DECOMPOSITION.value:
                    return data.get("data")
            except json.JSONDecodeError:
                pass

        return None

    async def search_moral_vectors(
        self,
        query: str,
        limit: int = 10,
        agent_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Search for moral vectors using semantic search.

        Args:
            query: Search query
            limit: Maximum results
            agent_id: Filter by agent (optional)

        Returns: List of matching moral vectors
        """
        results = await self.search_knowledge(
            query=f"moral vector {query}",
            limit=limit,
        )

        vectors = []
        for result in results:
            content = result.get("content", "")
            try:
                data = json.loads(content)
                if data.get("type") == VesselNodeType.MORAL_VECTOR.value:
                    if agent_id is None or data.get("agent_id") == agent_id:
                        vectors.append(data.get("data"))
            except (json.JSONDecodeError, TypeError):
                pass

        return vectors

    async def get_moral_trajectory_waypoints(
        self,
        entity_id: str,
        limit: int = 100,
    ) -> list[dict]:
        """
        Get all waypoints for an entity's moral trajectory.

        Args:
            entity_id: The entity being tracked
            limit: Maximum waypoints to return

        Returns: List of moral vector waypoints
        """
        # Search for trajectory
        content = await self.get_content(f"moral/trajectories/{entity_id}")

        if content:
            try:
                data = json.loads(content)
                trajectory = data.get("data", {})
                waypoints = trajectory.get("waypoints", [])
                return waypoints[:limit]
            except json.JSONDecodeError:
                pass

        return []

    async def list_moral_geometry(
        self,
        geometry_type: Optional[str] = None,
    ) -> list[str]:
        """
        List all moral geometry content.

        Args:
            geometry_type: Filter by type (vectors, trajectories, spectral)

        Returns: List of content paths
        """
        paths = await self.list_content(content_type="moral_geometry")

        if geometry_type:
            paths = [p for p in paths if f"moral/{geometry_type}" in p]

        return paths

    # =========================================================================
    # Kala Operations - Contribution Visibility System
    # =========================================================================

    async def save_kala_event(
        self,
        event_id: str,
        event_data: dict,
        vessel_id: str = "default",
    ) -> str:
        """
        Save a Kala event to the graph.

        Args:
            event_id: Unique identifier for the event
            event_data: Dict containing event data (participants, multipliers, etc.)
            vessel_id: Which vessel/community this belongs to

        Returns: The event ID
        """
        content = json.dumps({
            "type": VesselNodeType.KALA_EVENT.value,
            "vessel_id": vessel_id,
            "data": event_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"kala/events/{vessel_id}/{event_id}",
            content,
            content_type="kala"
        )

        return event_id

    async def load_kala_event(self, event_id: str, vessel_id: str = "default") -> Optional[dict]:
        """Load a Kala event from the graph."""
        content = await self.get_content(f"kala/events/{vessel_id}/{event_id}")

        if content:
            try:
                data = json.loads(content)
                if data.get("type") == VesselNodeType.KALA_EVENT.value:
                    return data.get("data")
            except json.JSONDecodeError:
                pass

        return None

    async def list_kala_events(
        self,
        vessel_id: str = "default",
        limit: int = 100,
    ) -> list[dict]:
        """List all Kala events for a vessel."""
        paths = await self.list_content(content_type="kala")

        events = []
        prefix = f"kala/events/{vessel_id}/"

        for path in paths:
            if path.startswith(prefix):
                content = await self.get_content(path)
                if content:
                    try:
                        data = json.loads(content)
                        if data.get("type") == VesselNodeType.KALA_EVENT.value:
                            events.append(data.get("data"))
                    except json.JSONDecodeError:
                        pass

            if len(events) >= limit:
                break

        return events

    async def get_participant_history(
        self,
        participant_id: str,
        vessel_id: str = "default",
    ) -> dict:
        """
        Get a participant's own history (HumanView).
        Returns only their own data - no rankings or comparisons.
        """
        events = await self.list_kala_events(vessel_id)

        participant_events = []
        total_kala = 0.0
        total_hours = 0.0

        for event in events:
            participants = event.get("participants", [])
            for p in participants:
                if p.get("participant_id") == participant_id:
                    participant_events.append({
                        "event_id": event.get("id"),
                        "event_name": event.get("name"),
                        "timestamp": p.get("timestamp"),
                        "hours": p.get("hours", 0),
                        "kala_received": p.get("kala_received", 0),
                    })
                    total_kala += p.get("kala_received", 0)
                    total_hours += p.get("hours", 0)

        # Aggregate community stats (anonymized)
        all_participants = set()
        community_total_kala = 0.0
        for event in events:
            community_total_kala += event.get("total_kala", 0)
            for p in event.get("participants", []):
                all_participants.add(p.get("participant_id"))

        return {
            "participant_id": participant_id,
            "total_kala": total_kala,
            "event_count": len(participant_events),
            "total_hours": total_hours,
            "events": participant_events,
            # Anonymized community stats
            "community_total_kala": community_total_kala,
            "community_event_count": len(events),
            "community_active_participants": len(all_participants),
        }

    async def get_agent_view(
        self,
        vessel_id: str = "default",
    ) -> dict:
        """
        Get the full agent view (AgentView) for coordination.
        Contains pattern data that enables burnout/withdrawal detection.
        NOT exposed to humans.
        """
        events = await self.list_kala_events(vessel_id)

        # Build participation frequency
        from collections import defaultdict
        participation_frequency = defaultdict(int)
        participant_hours = defaultdict(float)
        participant_kala = defaultdict(float)
        all_participations = defaultdict(list)

        for event in events:
            for p in event.get("participants", []):
                pid = p.get("participant_id")
                participation_frequency[pid] += 1
                participant_hours[pid] += p.get("hours", 0)
                participant_kala[pid] += p.get("kala_received", 0)
                all_participations[pid].append(p)

        # Detect burnout risks (high recent hours)
        burnout_risks = []
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        for pid, participations in all_participations.items():
            recent_hours = sum(
                p.get("hours", 0) for p in participations
                if datetime.fromisoformat(p.get("timestamp", now.isoformat())) > week_ago
            )
            if recent_hours > 20:  # threshold
                burnout_risks.append({
                    "participant_id": pid,
                    "hours_this_week": recent_hours,
                    "message": "High contribution - may need support"
                })

        # Detect withdrawal (sudden drops)
        withdrawal_signals = []
        two_weeks = now - timedelta(days=14)
        six_weeks = now - timedelta(days=42)

        for pid, participations in all_participations.items():
            recent = [p for p in participations
                      if datetime.fromisoformat(p.get("timestamp", now.isoformat())) > two_weeks]
            baseline = [p for p in participations
                        if two_weeks >= datetime.fromisoformat(p.get("timestamp", now.isoformat())) > six_weeks]

            if len(baseline) >= 2 and len(recent) == 0:
                withdrawal_signals.append({
                    "participant_id": pid,
                    "baseline_events": len(baseline),
                    "recent_events": 0,
                    "message": "Sudden withdrawal detected"
                })

        # Build care network (co-participation)
        co_participation = defaultdict(int)
        for event in events:
            pids = [p.get("participant_id") for p in event.get("participants", [])]
            for i, p1 in enumerate(pids):
                for p2 in pids[i+1:]:
                    key = tuple(sorted([p1, p2]))
                    co_participation[key] += 1

        care_edges = [(k[0], k[1], v) for k, v in co_participation.items()]

        # Find isolated participants
        connected = set()
        for k in co_participation.keys():
            connected.add(k[0])
            connected.add(k[1])
        isolated = [pid for pid in participation_frequency.keys() if pid not in connected]

        return {
            "vessel_id": vessel_id,
            "participation_frequency": dict(participation_frequency),
            "participant_hours": dict(participant_hours),
            "participant_kala": dict(participant_kala),
            "burnout_risks": burnout_risks,
            "withdrawal_signals": withdrawal_signals,
            "care_network": {
                "edges": care_edges,
                "isolated": isolated,
            },
            "total_events": len(events),
            "total_participants": len(participation_frequency),
        }

    async def save_kala_attractor_metrics(
        self,
        vessel_id: str,
        metrics: dict,
    ) -> None:
        """Save attractor dynamics metrics for a vessel."""
        content = json.dumps({
            "type": VesselNodeType.KALA_ATTRACTOR.value,
            "vessel_id": vessel_id,
            "metrics": metrics,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"kala/attractors/{vessel_id}",
            content,
            content_type="kala"
        )

    async def load_kala_attractor_metrics(self, vessel_id: str) -> Optional[dict]:
        """Load attractor metrics for a vessel."""
        content = await self.get_content(f"kala/attractors/{vessel_id}")

        if content:
            try:
                data = json.loads(content)
                return data.get("metrics")
            except json.JSONDecodeError:
                pass

        return None

    # =========================================================================
    # Persona & Voice Operations - Agent Identity System
    # =========================================================================

    async def save_persona(
        self,
        persona_id: str,
        persona_data: dict,
        vessel_id: str = "default",
    ) -> str:
        """
        Save an agent persona to the graph.

        Args:
            persona_id: Unique identifier for the persona
            persona_data: Dict containing persona data (voice, traits, etc.)
            vessel_id: Which vessel this persona belongs to

        Returns: The persona ID
        """
        content = json.dumps({
            "type": VesselNodeType.PERSONA.value,
            "vessel_id": vessel_id,
            "data": persona_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"personas/{vessel_id}/{persona_id}",
            content,
            content_type="persona"
        )

        return persona_id

    async def load_persona(self, persona_id: str, vessel_id: str = "default") -> Optional[dict]:
        """Load a persona from the graph."""
        content = await self.get_content(f"personas/{vessel_id}/{persona_id}")

        if content:
            try:
                data = json.loads(content)
                if data.get("type") == VesselNodeType.PERSONA.value:
                    return data.get("data")
            except json.JSONDecodeError:
                pass

        return None

    async def list_personas(
        self,
        vessel_id: str = "default",
        include_proxies: bool = True,
    ) -> list[dict]:
        """List all personas for a vessel."""
        paths = await self.list_content(content_type="persona")

        personas = []
        prefix = f"personas/{vessel_id}/"

        for path in paths:
            if path.startswith(prefix):
                content = await self.get_content(path)
                if content:
                    try:
                        data = json.loads(content)
                        if data.get("type") == VesselNodeType.PERSONA.value:
                            persona = data.get("data", {})
                            if include_proxies or not persona.get("is_human_proxy"):
                                personas.append(persona)
                    except json.JSONDecodeError:
                        pass

        return personas

    async def find_human_proxies(
        self,
        human_id: str,
        vessel_id: str = "default",
    ) -> list[dict]:
        """Find all proxy personas for a specific human."""
        all_personas = await self.list_personas(vessel_id, include_proxies=True)
        return [p for p in all_personas if p.get("human_id") == human_id]

    async def save_voice_session(
        self,
        session_id: str,
        session_data: dict,
        vessel_id: str = "default",
    ) -> str:
        """
        Save a voice session to the graph.

        Args:
            session_id: Unique identifier for the session
            session_data: Dict containing session data
            vessel_id: Which vessel this session belongs to

        Returns: The session ID
        """
        content = json.dumps({
            "type": VesselNodeType.VOICE_SESSION.value,
            "vessel_id": vessel_id,
            "data": session_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"voice_sessions/{vessel_id}/{session_id}",
            content,
            content_type="voice_session"
        )

        return session_id

    async def load_voice_session(self, session_id: str, vessel_id: str = "default") -> Optional[dict]:
        """Load a voice session from the graph."""
        content = await self.get_content(f"voice_sessions/{vessel_id}/{session_id}")

        if content:
            try:
                data = json.loads(content)
                if data.get("type") == VesselNodeType.VOICE_SESSION.value:
                    return data.get("data")
            except json.JSONDecodeError:
                pass

        return None

    async def list_voice_sessions(
        self,
        vessel_id: str = "default",
        persona_id: str = None,
        active_only: bool = False,
    ) -> list[dict]:
        """List voice sessions, optionally filtered by persona or active status."""
        paths = await self.list_content(content_type="voice_session")

        sessions = []
        prefix = f"voice_sessions/{vessel_id}/"

        for path in paths:
            if path.startswith(prefix):
                content = await self.get_content(path)
                if content:
                    try:
                        data = json.loads(content)
                        if data.get("type") == VesselNodeType.VOICE_SESSION.value:
                            session = data.get("data", {})
                            # Apply filters
                            if persona_id and session.get("persona_id") != persona_id:
                                continue
                            if active_only and not session.get("is_active"):
                                continue
                            sessions.append(session)
                    except json.JSONDecodeError:
                        pass

        return sessions

    async def save_hume_config(
        self,
        config_id: str,
        config_data: dict,
        vessel_id: str = "default",
    ) -> str:
        """Save a Hume EVI configuration."""
        content = json.dumps({
            "type": VesselNodeType.HUME_CONFIG.value,
            "vessel_id": vessel_id,
            "data": config_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"hume_configs/{vessel_id}/{config_id}",
            content,
            content_type="hume_config"
        )

        return config_id

    async def load_hume_config(self, config_id: str, vessel_id: str = "default") -> Optional[dict]:
        """Load a Hume EVI configuration."""
        content = await self.get_content(f"hume_configs/{vessel_id}/{config_id}")

        if content:
            try:
                data = json.loads(content)
                if data.get("type") == VesselNodeType.HUME_CONFIG.value:
                    return data.get("data")
            except json.JSONDecodeError:
                pass

        return None

    async def get_persona_emotional_history(
        self,
        persona_id: str,
        vessel_id: str = "default",
        limit: int = 100,
    ) -> list[dict]:
        """
        Get emotional history from voice sessions for a persona.
        Returns emotional trajectories aggregated across sessions.
        """
        sessions = await self.list_voice_sessions(
            vessel_id=vessel_id,
            persona_id=persona_id
        )

        all_emotions = []
        for session in sessions:
            trajectory = session.get("emotional_trajectory", [])
            for emotion in trajectory:
                emotion["session_id"] = session.get("id")
                all_emotions.append(emotion)

        # Sort by timestamp and limit
        all_emotions.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
        return all_emotions[:limit]

    async def get_vessel_emotional_state(
        self,
        vessel_id: str = "default",
    ) -> dict:
        """
        Get aggregate emotional state across all active sessions in a vessel.
        Useful for understanding community emotional climate.
        """
        sessions = await self.list_voice_sessions(
            vessel_id=vessel_id,
            active_only=True
        )

        if not sessions:
            return {"active_sessions": 0, "emotions": {}}

        from collections import Counter
        emotion_counts = Counter()
        valence_sum = 0
        arousal_sum = 0
        count = 0

        for session in sessions:
            current = session.get("current_emotion", {})
            if current.get("dominant_emotion"):
                emotion_counts[current["dominant_emotion"]] += 1
            valence_sum += current.get("valence", 0)
            arousal_sum += current.get("arousal", 0)
            count += 1

        return {
            "active_sessions": len(sessions),
            "dominant_emotions": emotion_counts.most_common(5),
            "average_valence": valence_sum / count if count else 0,
            "average_arousal": arousal_sum / count if count else 0,
        }

    # =========================================================================
    # Entity Ontology Operations - Universal Entity System
    # =========================================================================

    async def save_entity(
        self,
        entity_id: str,
        entity_data: dict,
        vessel_id: str = "default",
    ) -> str:
        """
        Save a universal entity persona to the graph.

        This is the primary method for storing any entity type:
        humans, agents, plants, machines, systems, biomes, etc.

        Args:
            entity_id: Unique identifier for the entity
            entity_data: Dict containing full EntityPersona data
            vessel_id: Which vessel this entity belongs to

        Returns: The entity ID
        """
        content = json.dumps({
            "type": VesselNodeType.ENTITY.value,
            "vessel_id": vessel_id,
            "entity_type": entity_data.get("entity_type", "agent"),
            "data": entity_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"entities/{vessel_id}/{entity_id}",
            content,
            content_type="entity"
        )

        return entity_id

    async def load_entity(self, entity_id: str, vessel_id: str = "default") -> Optional[dict]:
        """Load an entity persona from the graph."""
        content = await self.get_content(f"entities/{vessel_id}/{entity_id}")

        if content:
            try:
                data = json.loads(content)
                if data.get("type") == VesselNodeType.ENTITY.value:
                    return data.get("data")
            except json.JSONDecodeError:
                pass

        return None

    async def list_entities(
        self,
        vessel_id: str = "default",
        entity_type: Optional[str] = None,
        voice_source: Optional[str] = None,
        include_proxies: bool = True,
    ) -> list[dict]:
        """
        List all entities for a vessel, optionally filtered.

        Args:
            vessel_id: Which vessel
            entity_type: Filter by type (human, agent, plant, machine, etc.)
            voice_source: Filter by voice source (self, proxy, sensor, collective)
            include_proxies: Whether to include proxy entities

        Returns: List of entity data dicts
        """
        paths = await self.list_content(content_type="entity")

        entities = []
        prefix = f"entities/{vessel_id}/"

        for path in paths:
            if path.startswith(prefix):
                content = await self.get_content(path)
                if content:
                    try:
                        data = json.loads(content)
                        if data.get("type") == VesselNodeType.ENTITY.value:
                            entity = data.get("data", {})

                            # Apply filters
                            if entity_type and entity.get("entity_type") != entity_type:
                                continue
                            if voice_source and entity.get("voice_source") != voice_source:
                                continue
                            if not include_proxies and entity.get("is_proxy"):
                                continue

                            entities.append(entity)
                    except json.JSONDecodeError:
                        pass

        return entities

    async def search_entities_by_type(
        self,
        vessel_id: str = "default",
        entity_types: Optional[list[str]] = None,
    ) -> dict[str, list[dict]]:
        """
        Get entities grouped by type.

        Returns: Dict mapping entity_type -> list of entities
        """
        all_entities = await self.list_entities(vessel_id)

        grouped = {}
        for entity in all_entities:
            etype = entity.get("entity_type", "unknown")
            if entity_types and etype not in entity_types:
                continue
            if etype not in grouped:
                grouped[etype] = []
            grouped[etype].append(entity)

        return grouped

    async def find_entities_needing_spokespersons(
        self,
        vessel_id: str = "default",
    ) -> list[dict]:
        """Find entities that need spokespersons but don't have any."""
        entities = await self.list_entities(vessel_id)

        needing = []
        for entity in entities:
            voice_source = entity.get("voice_source", "self")
            if voice_source in ["proxy", "collective"]:
                spokespersons = entity.get("spokespersons", [])
                if not spokespersons:
                    needing.append(entity)

        return needing

    async def find_entities_with_incomplete_elicitation(
        self,
        vessel_id: str = "default",
    ) -> list[dict]:
        """Find entities that haven't completed persona elicitation."""
        entities = await self.list_entities(vessel_id)
        return [e for e in entities if not e.get("elicitation_complete", False)]

    # =========================================================================
    # Elicitation Session Operations
    # =========================================================================

    async def save_elicitation_session(
        self,
        session_id: str,
        session_data: dict,
        vessel_id: str = "default",
    ) -> str:
        """
        Save an elicitation session to the graph.

        Args:
            session_id: Unique identifier for the session
            session_data: Dict containing ElicitationSession data
            vessel_id: Which vessel

        Returns: The session ID
        """
        content = json.dumps({
            "type": VesselNodeType.ELICITATION_SESSION.value,
            "vessel_id": vessel_id,
            "entity_id": session_data.get("entity_id"),
            "data": session_data,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"elicitation/{vessel_id}/{session_id}",
            content,
            content_type="elicitation_session"
        )

        return session_id

    async def load_elicitation_session(
        self,
        session_id: str,
        vessel_id: str = "default",
    ) -> Optional[dict]:
        """Load an elicitation session from the graph."""
        content = await self.get_content(f"elicitation/{vessel_id}/{session_id}")

        if content:
            try:
                data = json.loads(content)
                if data.get("type") == VesselNodeType.ELICITATION_SESSION.value:
                    return data.get("data")
            except json.JSONDecodeError:
                pass

        return None

    async def list_elicitation_sessions(
        self,
        vessel_id: str = "default",
        entity_id: Optional[str] = None,
        active_only: bool = False,
    ) -> list[dict]:
        """
        List elicitation sessions, optionally filtered.

        Args:
            vessel_id: Which vessel
            entity_id: Filter by entity being elicited
            active_only: Only return active sessions

        Returns: List of session data dicts
        """
        paths = await self.list_content(content_type="elicitation_session")

        sessions = []
        prefix = f"elicitation/{vessel_id}/"

        for path in paths:
            if path.startswith(prefix):
                content = await self.get_content(path)
                if content:
                    try:
                        data = json.loads(content)
                        if data.get("type") == VesselNodeType.ELICITATION_SESSION.value:
                            session = data.get("data", {})

                            # Apply filters
                            if entity_id and session.get("entity_id") != entity_id:
                                continue
                            if active_only and not session.get("is_active"):
                                continue

                            sessions.append(session)
                    except json.JSONDecodeError:
                        pass

        return sessions

    async def get_active_elicitation_for_entity(
        self,
        entity_id: str,
        vessel_id: str = "default",
    ) -> Optional[dict]:
        """Get the active elicitation session for an entity, if any."""
        sessions = await self.list_elicitation_sessions(
            vessel_id=vessel_id,
            entity_id=entity_id,
            active_only=True
        )
        return sessions[0] if sessions else None

    # =========================================================================
    # Spokesperson Operations
    # =========================================================================

    async def save_spokesperson(
        self,
        spokesperson_id: str,
        spokesperson_data: dict,
        vessel_id: str = "default",
    ) -> str:
        """
        Save a spokesperson to the graph.

        Args:
            spokesperson_id: Unique identifier
            spokesperson_data: Dict containing Spokesperson data
            vessel_id: Which vessel

        Returns: The spokesperson ID
        """
        content = json.dumps({
            "type": VesselNodeType.SPOKESPERSON.value,
            "vessel_id": vessel_id,
            "entity_id": spokesperson_data.get("entity_id"),
            "data": spokesperson_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"spokespersons/{vessel_id}/{spokesperson_id}",
            content,
            content_type="spokesperson"
        )

        return spokesperson_id

    async def load_spokespersons_for_entity(
        self,
        entity_id: str,
        vessel_id: str = "default",
        active_only: bool = True,
    ) -> list[dict]:
        """
        Load all spokespersons for an entity.

        Args:
            entity_id: Which entity
            vessel_id: Which vessel
            active_only: Only return active spokespersons

        Returns: List of spokesperson data dicts
        """
        paths = await self.list_content(content_type="spokesperson")

        spokespersons = []
        prefix = f"spokespersons/{vessel_id}/"

        for path in paths:
            if path.startswith(prefix):
                content = await self.get_content(path)
                if content:
                    try:
                        data = json.loads(content)
                        if data.get("type") == VesselNodeType.SPOKESPERSON.value:
                            spokesperson = data.get("data", {})
                            if spokesperson.get("entity_id") == entity_id:
                                if not active_only or spokesperson.get("active", True):
                                    spokespersons.append(spokesperson)
                    except json.JSONDecodeError:
                        pass

        return spokespersons

    # =========================================================================
    # Sensor Source Operations
    # =========================================================================

    async def save_sensor_source(
        self,
        sensor_id: str,
        sensor_data: dict,
        vessel_id: str = "default",
    ) -> str:
        """
        Save a sensor source to the graph.

        Args:
            sensor_id: Unique identifier
            sensor_data: Dict containing SensorSource data
            vessel_id: Which vessel

        Returns: The sensor ID
        """
        content = json.dumps({
            "type": VesselNodeType.SENSOR_SOURCE.value,
            "vessel_id": vessel_id,
            "entity_id": sensor_data.get("entity_id"),
            "data": sensor_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"sensors/{vessel_id}/{sensor_id}",
            content,
            content_type="sensor_source"
        )

        return sensor_id

    async def load_sensors_for_entity(
        self,
        entity_id: str,
        vessel_id: str = "default",
    ) -> list[dict]:
        """Load all sensor sources for an entity."""
        paths = await self.list_content(content_type="sensor_source")

        sensors = []
        prefix = f"sensors/{vessel_id}/"

        for path in paths:
            if path.startswith(prefix):
                content = await self.get_content(path)
                if content:
                    try:
                        data = json.loads(content)
                        if data.get("type") == VesselNodeType.SENSOR_SOURCE.value:
                            sensor = data.get("data", {})
                            if sensor.get("entity_id") == entity_id:
                                sensors.append(sensor)
                    except json.JSONDecodeError:
                        pass

        return sensors

    # =========================================================================
    # Story Operations
    # =========================================================================

    async def save_story(
        self,
        story_id: str,
        story_data: dict,
        entity_id: str,
        vessel_id: str = "default",
    ) -> str:
        """
        Save a defining story to the graph.

        Args:
            story_id: Unique identifier
            story_data: Dict containing Story data
            entity_id: Which entity this story belongs to
            vessel_id: Which vessel

        Returns: The story ID
        """
        content = json.dumps({
            "type": VesselNodeType.STORY.value,
            "vessel_id": vessel_id,
            "entity_id": entity_id,
            "data": story_data,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        await self.save_content(
            f"stories/{vessel_id}/{entity_id}/{story_id}",
            content,
            content_type="story"
        )

        return story_id

    async def load_stories_for_entity(
        self,
        entity_id: str,
        vessel_id: str = "default",
        limit: int = 100,
    ) -> list[dict]:
        """Load all stories for an entity."""
        paths = await self.list_content(content_type="story")

        stories = []
        prefix = f"stories/{vessel_id}/{entity_id}/"

        for path in paths:
            if path.startswith(prefix):
                content = await self.get_content(path)
                if content:
                    try:
                        data = json.loads(content)
                        if data.get("type") == VesselNodeType.STORY.value:
                            stories.append(data.get("data", {}))
                    except json.JSONDecodeError:
                        pass

            if len(stories) >= limit:
                break

        return stories

    # =========================================================================
    # Vessel-wide Entity Analytics
    # =========================================================================

    async def get_vessel_entity_summary(
        self,
        vessel_id: str = "default",
    ) -> dict:
        """
        Get a summary of all entities in a vessel.

        Returns: Summary with counts by type, voice source, completion status
        """
        entities = await self.list_entities(vessel_id)

        from collections import Counter

        type_counts = Counter()
        voice_counts = Counter()
        scale_counts = Counter()
        complete_count = 0
        incomplete_count = 0

        for entity in entities:
            type_counts[entity.get("entity_type", "unknown")] += 1
            voice_counts[entity.get("voice_source", "unknown")] += 1
            scale_counts[entity.get("temporal_scale", "unknown")] += 1

            if entity.get("elicitation_complete"):
                complete_count += 1
            else:
                incomplete_count += 1

        return {
            "vessel_id": vessel_id,
            "total_entities": len(entities),
            "by_type": dict(type_counts),
            "by_voice_source": dict(voice_counts),
            "by_temporal_scale": dict(scale_counts),
            "elicitation_complete": complete_count,
            "elicitation_incomplete": incomplete_count,
        }

    async def get_entity_relationship_graph(
        self,
        vessel_id: str = "default",
    ) -> dict:
        """
        Build a graph of entity relationships.

        Returns: Nodes and edges representing entity connections
        """
        entities = await self.list_entities(vessel_id)

        nodes = []
        edges = []

        for entity in entities:
            entity_id = entity.get("id", "")
            nodes.append({
                "id": entity_id,
                "name": entity.get("name", ""),
                "type": entity.get("entity_type", "unknown"),
                "voice_source": entity.get("voice_source", "unknown"),
            })

            # Dependency edges
            for dep in entity.get("dependencies", []):
                # Check if dependency is another entity
                dep_entity = next(
                    (e for e in entities if e.get("name", "").lower() == dep.lower()),
                    None
                )
                if dep_entity:
                    edges.append({
                        "from": entity_id,
                        "to": dep_entity.get("id"),
                        "type": "depends_on",
                    })

            # Proxy relationships
            if entity.get("proxy_for"):
                edges.append({
                    "from": entity_id,
                    "to": entity.get("proxy_for"),
                    "type": "proxy_for",
                })

            # Spokesperson relationships
            for sp in entity.get("spokespersons", []):
                sp_id = sp.get("id", "")
                if sp_id:
                    edges.append({
                        "from": sp_id,
                        "to": entity_id,
                        "type": "speaks_for",
                    })

        return {
            "nodes": nodes,
            "edges": edges,
        }

    async def find_related_entities(
        self,
        entity_id: str,
        vessel_id: str = "default",
    ) -> dict:
        """
        Find all entities related to a given entity.

        Returns: Dict with related entities by relationship type
        """
        entities = await self.list_entities(vessel_id)
        entity = await self.load_entity(entity_id, vessel_id)

        if not entity:
            return {"entity_id": entity_id, "not_found": True}

        related = {
            "depends_on": [],
            "depended_on_by": [],
            "speaks_for": [],
            "spoken_for_by": [],
            "proxies": [],
            "proxy_of": [],
            "same_type": [],
        }

        entity_name = entity.get("name", "").lower()
        entity_type = entity.get("entity_type")

        for other in entities:
            if other.get("id") == entity_id:
                continue

            other_name = other.get("name", "").lower()

            # Check dependencies
            if entity_name in [d.lower() for d in other.get("dependencies", [])]:
                related["depended_on_by"].append(other)
            if other_name in [d.lower() for d in entity.get("dependencies", [])]:
                related["depends_on"].append(other)

            # Check proxy relationships
            if other.get("proxy_for") == entity_id:
                related["proxies"].append(other)
            if entity.get("proxy_for") == other.get("id"):
                related["proxy_of"].append(other)

            # Check spokesperson relationships
            for sp in entity.get("spokespersons", []):
                if sp.get("name", "").lower() == other_name:
                    related["spoken_for_by"].append(other)
            for sp in other.get("spokespersons", []):
                if sp.get("name", "").lower() == entity_name:
                    related["speaks_for"].append(other)

            # Same type
            if other.get("entity_type") == entity_type:
                related["same_type"].append(other)

        return {
            "entity_id": entity_id,
            "entity_name": entity.get("name"),
            "related": related,
        }

    # =========================================================================
    # Utility Methods
    # =========================================================================

    async def health_check(self) -> bool:
        """Check if the graph store is healthy."""
        try:
            query = "RETURN 1 as health"
            result = await self._driver.execute_query(query)
            return result is not None
        except Exception:
            return False

    async def get_stats(self) -> dict:
        """Get statistics about the graph store."""
        try:
            query = """
            MATCH (n)
            RETURN labels(n) as label, count(*) as count
            """
            results = await self._driver.execute_query(query)

            stats = {"nodes": {}, "total": 0}
            for row in results:
                label = row.get("label", ["unknown"])[0]
                count = row.get("count", 0)
                stats["nodes"][label] = count
                stats["total"] += count

            return stats
        except Exception as e:
            return {"error": str(e)}


# =============================================================================
# Convenience Functions (API compatibility layer)
# =============================================================================

async def get_graph_store(config: Optional[GraphStoreConfig] = None) -> GraphStore:
    """Get the graph store singleton instance."""
    return await GraphStore.get_instance(config)


def get_graph_store_sync(config: Optional[GraphStoreConfig] = None) -> GraphStore:
    """Get the graph store singleton instance (sync version)."""
    return GraphStore.get_instance_sync(config)


# =============================================================================
# Migration Helpers
# =============================================================================

class MigrationHelper:
    """Helpers for migrating from file-based storage to graph storage."""

    @staticmethod
    async def migrate_faiss_to_graph(
        faiss_memory_dir: str,
        graph_store: GraphStore,
        memory_subdir: str = "default",
    ) -> int:
        """
        Migrate memories from FAISS to graph store.

        Returns: Number of memories migrated
        """
        # This would load from FAISS and insert into graph
        # Implementation depends on having access to old FAISS data
        raise NotImplementedError("Migration from FAISS requires old data access")

    @staticmethod
    async def migrate_chats_to_graph(
        chats_dir: str,
        graph_store: GraphStore,
    ) -> int:
        """
        Migrate chats from file storage to graph.

        Returns: Number of chats migrated
        """
        import os
        from python.helpers import files

        migrated = 0
        chat_folders = files.list_files(chats_dir, "*")

        for folder in chat_folders:
            chat_file = os.path.join(chats_dir, folder, "chat.json")
            if os.path.exists(chat_file):
                try:
                    with open(chat_file, 'r') as f:
                        data = json.load(f)

                    chat = ChatDocument.from_dict(data)
                    await graph_store.save_chat(chat)
                    migrated += 1
                except Exception as e:
                    PrintStyle.error(f"Failed to migrate chat {folder}: {e}")

        return migrated

    @staticmethod
    async def migrate_md_files_to_graph(
        graph_store: GraphStore,
        base_dir: Optional[str] = None,
    ) -> int:
        """
        Migrate all .md files from filesystem to graph store.

        Returns: Number of files migrated
        """
        import os
        import glob as glob_module

        if base_dir is None:
            # Get the base directory of the application
            base_dir = os.path.dirname(os.path.abspath(os.path.join(__file__, "../../")))

        migrated = 0

        # Define content type mappings based on directory
        type_mappings = {
            "prompts/": "prompt",
            "agents/": "prompt",
            "docs/": "doc",
            "instruments/": "instrument",
            "knowledge/": "knowledge",
        }

        # Find all .md files
        pattern = os.path.join(base_dir, "**/*.md")
        md_files = glob_module.glob(pattern, recursive=True)

        for file_path in md_files:
            try:
                # Get relative path
                rel_path = os.path.relpath(file_path, base_dir)
                rel_path = rel_path.replace("\\", "/")

                # Skip certain directories
                if rel_path.startswith(("work_dir/", "tmp/", ".git/", "node_modules/")):
                    continue

                # Determine content type
                content_type = "other"
                for prefix, ctype in type_mappings.items():
                    if rel_path.startswith(prefix):
                        content_type = ctype
                        break

                # Read file content
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                # Save to graph
                await graph_store.save_content(rel_path, content, content_type)
                migrated += 1
                PrintStyle.standard(f"Migrated: {rel_path}")

            except Exception as e:
                PrintStyle.error(f"Failed to migrate {file_path}: {e}")

        PrintStyle.standard(f"Migration complete: {migrated} files migrated")
        return migrated
