"""
Vessels Memory System - Graph-based Implementation

This module provides the memory system for Vessels agents using
FalkorDB + Graphiti as the backend instead of FAISS.

The API remains compatible with the original memory.py for
seamless integration with existing agent code.

A0 Framework: Includes guardian integration for sanitizing retrieved memories.
"""

from datetime import datetime
from typing import Any, List, Optional
from enum import Enum
import asyncio

from python.helpers import guids
from python.helpers.print_style import PrintStyle
from python.helpers import files
from python.helpers.log import LogItem
from python.helpers.graph_store import (
    GraphStore,
    MemoryArea as GraphMemoryArea,
    MemoryDocument,
    get_graph_store,
)
from python.helpers.guardians import guard_memory
from agent import Agent, AgentContext
import models
import logging


# Raise the log level so WARNING messages aren't shown
logging.getLogger("langchain_core.vectorstores.base").setLevel(logging.ERROR)


class Memory:
    """
    Graph-based memory system for Vessels agents.

    This replaces the FAISS-based implementation with FalkorDB + Graphiti,
    providing temporal knowledge graph capabilities while maintaining
    API compatibility with the original Memory class.
    """

    class Area(Enum):
        """Memory storage areas."""
        MAIN = "main"
        FRAGMENTS = "fragments"
        SOLUTIONS = "solutions"
        INSTRUMENTS = "instruments"

    # Cache of initialized memory instances per subdir
    _instances: dict[str, "Memory"] = {}
    _graph_store: Optional[GraphStore] = None
    _init_lock = asyncio.Lock()

    @staticmethod
    async def _ensure_graph_store() -> GraphStore:
        """Ensure the graph store is initialized."""
        async with Memory._init_lock:
            if Memory._graph_store is None:
                Memory._graph_store = await get_graph_store()
            return Memory._graph_store

    @staticmethod
    async def get(agent: Agent) -> "Memory":
        """
        Get or create a Memory instance for an agent.

        Args:
            agent: The agent to get memory for

        Returns:
            Memory instance for the agent
        """
        memory_subdir = get_agent_memory_subdir(agent)

        if memory_subdir not in Memory._instances:
            log_item = agent.context.log.log(
                type="util",
                heading=f"Initializing Graph Memory in '/{memory_subdir}'",
            )

            graph_store = await Memory._ensure_graph_store()
            memory = Memory(graph_store, memory_subdir)

            # Preload knowledge if configured
            knowledge_subdirs = get_knowledge_subdirs_by_memory_subdir(
                memory_subdir, agent.config.knowledge_subdirs or []
            )
            if knowledge_subdirs:
                await memory.preload_knowledge(log_item, knowledge_subdirs, memory_subdir)

            Memory._instances[memory_subdir] = memory
            if log_item:
                log_item.update(heading=f"Graph Memory initialized for '/{memory_subdir}'")

        return Memory._instances[memory_subdir]

    @staticmethod
    async def get_by_subdir(
        memory_subdir: str,
        log_item: Optional[LogItem] = None,
        preload_knowledge: bool = True,
    ) -> "Memory":
        """Get memory by subdirectory name."""
        if memory_subdir not in Memory._instances:
            graph_store = await Memory._ensure_graph_store()
            memory = Memory(graph_store, memory_subdir)

            if preload_knowledge:
                import initialize
                agent_config = initialize.initialize_agent()
                knowledge_subdirs = get_knowledge_subdirs_by_memory_subdir(
                    memory_subdir, agent_config.knowledge_subdirs or []
                )
                if knowledge_subdirs:
                    await memory.preload_knowledge(log_item, knowledge_subdirs, memory_subdir)

            Memory._instances[memory_subdir] = memory

        return Memory._instances[memory_subdir]

    @staticmethod
    async def reload(agent: Agent) -> "Memory":
        """Reload memory for an agent."""
        memory_subdir = get_agent_memory_subdir(agent)
        if memory_subdir in Memory._instances:
            del Memory._instances[memory_subdir]
        return await Memory.get(agent)

    def __init__(self, graph_store: GraphStore, memory_subdir: str):
        """
        Initialize a Memory instance.

        Args:
            graph_store: The graph store instance
            memory_subdir: The memory subdirectory name
        """
        self.graph_store = graph_store
        self.memory_subdir = memory_subdir

    async def preload_knowledge(
        self,
        log_item: Optional[LogItem],
        kn_dirs: list[str],
        memory_subdir: str,
    ) -> None:
        """
        Preload knowledge documents into the graph.

        This imports documents from knowledge directories as episodes.
        """
        if log_item:
            log_item.update(heading="Preloading knowledge into graph...")

        from python.helpers import knowledge_import

        for kn_dir in kn_dirs:
            # Import root knowledge to MAIN
            await self._import_knowledge_dir(
                log_item,
                abs_knowledge_dir(kn_dir),
                Memory.Area.MAIN,
                recursive=False,
            )

            # Import subdirectories to their respective areas
            for area in Memory.Area:
                await self._import_knowledge_dir(
                    log_item,
                    abs_knowledge_dir(kn_dir, area.value),
                    area,
                    recursive=True,
                )

        # Import instruments descriptions
        await self._import_knowledge_dir(
            log_item,
            files.get_abs_path("instruments"),
            Memory.Area.INSTRUMENTS,
            recursive=True,
            pattern="**/*.md",
        )

    async def _import_knowledge_dir(
        self,
        log_item: Optional[LogItem],
        directory: str,
        area: "Memory.Area",
        recursive: bool = True,
        pattern: str = "*",
    ) -> None:
        """Import knowledge from a directory into the graph."""
        import os
        import glob

        if not os.path.exists(directory):
            return

        # Find files matching pattern
        if recursive:
            file_pattern = os.path.join(directory, "**", pattern)
        else:
            file_pattern = os.path.join(directory, pattern)

        for file_path in glob.glob(file_pattern, recursive=recursive):
            if os.path.isfile(file_path):
                try:
                    # Read file content
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Import into graph
                    graph_area = GraphMemoryArea(area.value)
                    await self.graph_store.import_knowledge(
                        content=content,
                        source_file=file_path,
                        area=graph_area,
                        metadata={"memory_subdir": self.memory_subdir},
                    )

                    if log_item:
                        log_item.stream(progress=f"\nImported: {os.path.basename(file_path)}")

                except Exception as e:
                    PrintStyle.error(f"Failed to import {file_path}: {e}")

    async def search_similarity_threshold(
        self,
        query: str,
        limit: int,
        threshold: float,
        filter: str = "",
        apply_guardians: bool = True,
    ) -> list[Any]:
        """
        Search memories by semantic similarity.

        Args:
            query: The search query
            limit: Maximum number of results
            threshold: Minimum similarity threshold (0-1)
            filter: Optional filter expression
            apply_guardians: Whether to sanitize results through guardians

        Returns:
            List of matching documents with metadata
        """
        # Parse filter to extract area if specified
        area = None
        if filter and "area" in filter:
            for memory_area in Memory.Area:
                if memory_area.value in filter:
                    area = GraphMemoryArea(memory_area.value)
                    break

        results = await self.graph_store.search_memories(
            query=query,
            limit=limit,
            threshold=threshold,
            area=area,
            memory_subdir=self.memory_subdir,
        )

        # Sanitize results through guardians
        if apply_guardians:
            results = [guard_memory(r, source=f"memory.{self.memory_subdir}") for r in results]

        # Convert to Document-like objects for compatibility
        return [_dict_to_document(r) for r in results]

    async def delete_documents_by_query(
        self,
        query: str,
        threshold: float,
        filter: str = "",
    ) -> list[Any]:
        """Delete documents matching a similarity query."""
        # First search for matching documents
        docs = await self.search_similarity_threshold(
            query=query,
            limit=100,
            threshold=threshold,
            filter=filter,
        )

        if docs:
            ids = [doc.metadata["id"] for doc in docs]
            await self.delete_documents_by_ids(ids)

        return docs

    async def delete_documents_by_ids(self, ids: list[str]) -> list[Any]:
        """Delete documents by their IDs."""
        await self.graph_store.delete_memories(ids, self.memory_subdir)
        return []

    async def insert_text(self, text: str, metadata: dict = {}) -> str:
        """
        Insert a text memory into the graph.

        Args:
            text: The memory content
            metadata: Additional metadata

        Returns:
            The generated memory ID
        """
        area = GraphMemoryArea(metadata.get("area", Memory.Area.MAIN.value))

        memory_id = await self.graph_store.save_memory(
            content=text,
            area=area,
            metadata=metadata,
            memory_subdir=self.memory_subdir,
        )

        return memory_id

    async def insert_documents(self, docs: list[Any]) -> list[str]:
        """
        Insert multiple documents into the graph.

        Args:
            docs: List of Document-like objects with page_content and metadata

        Returns:
            List of generated IDs
        """
        ids = []
        for doc in docs:
            content = getattr(doc, 'page_content', str(doc))
            metadata = getattr(doc, 'metadata', {})

            area = GraphMemoryArea(metadata.get("area", Memory.Area.MAIN.value))

            memory_id = await self.graph_store.save_memory(
                content=content,
                area=area,
                metadata=metadata,
                memory_subdir=self.memory_subdir,
            )
            ids.append(memory_id)

        return ids

    async def update_documents(self, docs: list[Any]) -> list[str]:
        """Update existing documents (delete + insert)."""
        ids = [doc.metadata["id"] for doc in docs]
        await self.delete_documents_by_ids(ids)
        return await self.insert_documents(docs)

    def get_document_by_id(self, doc_id: str) -> Optional[Any]:
        """Get a document by ID (sync wrapper)."""
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(
            self.graph_store.get_memory_by_id(doc_id, self.memory_subdir)
        )
        if result:
            return _dict_to_document(result)
        return None

    @staticmethod
    def format_docs_plain(docs: list[Any]) -> list[str]:
        """Format documents as plain text."""
        result = []
        for doc in docs:
            text = ""
            metadata = getattr(doc, 'metadata', {})
            for k, v in metadata.items():
                text += f"{k}: {v}\n"
            content = getattr(doc, 'page_content', str(doc))
            text += f"Content: {content}"
            result.append(text)
        return result

    @staticmethod
    def get_timestamp() -> str:
        """Get current timestamp string."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# =============================================================================
# Document Compatibility Layer
# =============================================================================

class _CompatDocument:
    """Compatibility wrapper for Document-like objects."""

    def __init__(self, page_content: str, metadata: dict):
        self.page_content = page_content
        self.metadata = metadata


def _dict_to_document(data: dict) -> _CompatDocument:
    """Convert a dictionary to a Document-like object."""
    content = data.get("content", "")
    metadata = {
        "id": data.get("id", ""),
        "area": data.get("area", data.get("metadata", {}).get("area", "main")),
        "timestamp": data.get("timestamp", data.get("metadata", {}).get("timestamp", "")),
        "score": data.get("score", 1.0),
        **data.get("metadata", {}),
    }
    return _CompatDocument(content, metadata)


# =============================================================================
# Helper Functions
# =============================================================================

def get_custom_knowledge_subdir_abs(agent: Agent) -> str:
    """Get absolute path to custom knowledge subdirectory."""
    for dir in agent.config.knowledge_subdirs:
        if dir != "default":
            return files.get_abs_path("knowledge", dir)
    raise Exception("No custom knowledge subdir set")


def reload():
    """Clear memory cache to force reload."""
    Memory._instances = {}


def abs_db_dir(memory_subdir: str) -> str:
    """Get absolute database directory path (for compatibility)."""
    if memory_subdir.startswith("projects/"):
        from python.helpers.projects import get_project_meta_folder
        return files.get_abs_path(get_project_meta_folder(memory_subdir[9:]), "memory")
    return files.get_abs_path("memory", memory_subdir)


def abs_knowledge_dir(knowledge_subdir: str, *sub_dirs: str) -> str:
    """Get absolute knowledge directory path."""
    if knowledge_subdir.startswith("projects/"):
        from python.helpers.projects import get_project_meta_folder
        return files.get_abs_path(
            get_project_meta_folder(knowledge_subdir[9:]), "knowledge", *sub_dirs
        )
    return files.get_abs_path("knowledge", knowledge_subdir, *sub_dirs)


def get_memory_subdir_abs(agent: Agent) -> str:
    """Get absolute memory subdirectory path."""
    subdir = get_agent_memory_subdir(agent)
    return abs_db_dir(subdir)


def get_agent_memory_subdir(agent: Agent) -> str:
    """Get memory subdirectory for an agent."""
    return get_context_memory_subdir(agent.context)


def get_context_memory_subdir(context: AgentContext) -> str:
    """Get memory subdirectory for a context."""
    from python.helpers.projects import (
        get_context_memory_subdir as get_project_memory_subdir,
    )

    memory_subdir = get_project_memory_subdir(context)
    if memory_subdir:
        return memory_subdir

    return context.config.memory_subdir or "default"


def get_existing_memory_subdirs() -> list[str]:
    """Get list of existing memory subdirectories."""
    try:
        from python.helpers.projects import (
            get_project_meta_folder,
            get_projects_parent_folder,
        )

        subdirs = files.get_subdirectories("memory", exclude="embeddings")

        project_subdirs = files.get_subdirectories(get_projects_parent_folder())
        for project_subdir in project_subdirs:
            # Check for graph-based memory or legacy FAISS
            subdirs.append(f"projects/{project_subdir}")

        if "default" not in subdirs:
            subdirs.insert(0, "default")

        return subdirs
    except Exception as e:
        PrintStyle.error(f"Failed to get memory subdirectories: {str(e)}")
        return ["default"]


def get_knowledge_subdirs_by_memory_subdir(
    memory_subdir: str,
    default: list[str],
) -> list[str]:
    """Get knowledge subdirectories for a memory subdir."""
    if memory_subdir.startswith("projects/"):
        from python.helpers.projects import get_project_meta_folder
        default.append(get_project_meta_folder(memory_subdir[9:], "knowledge"))
    return default
