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


class MemoryArea(str, Enum):
    """Memory storage areas (compatible with legacy Memory.Area)."""
    MAIN = "main"
    FRAGMENTS = "fragments"
    SOLUTIONS = "solutions"
    INSTRUMENTS = "instruments"


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
