"""
Vessels Vector DB - Graph-based Implementation

This module provides a vector database interface using FalkorDB + Graphiti
instead of FAISS. The API remains compatible with the original vector_db.py.
"""

from typing import Any, List, Optional
import uuid
import asyncio

from python.helpers.graph_store import (
    GraphStore,
    MemoryArea,
    get_graph_store,
)
from python.helpers.print_style import PrintStyle
from agent import Agent


class VectorDB:
    """
    Graph-based vector database for Vessels.

    This replaces the FAISS-based VectorDB with FalkorDB + Graphiti,
    providing temporal knowledge graph capabilities while maintaining
    API compatibility.
    """

    _graph_store: Optional[GraphStore] = None

    @classmethod
    async def _ensure_graph_store(cls) -> GraphStore:
        """Ensure graph store is initialized."""
        if cls._graph_store is None:
            cls._graph_store = await get_graph_store()
        return cls._graph_store

    def __init__(self, agent: Agent, cache: bool = True):
        """
        Initialize VectorDB for an agent.

        Args:
            agent: The agent to create VectorDB for
            cache: Whether to cache embeddings (ignored in graph implementation)
        """
        self.agent = agent
        self.cache = cache
        self._graph_store_instance: Optional[GraphStore] = None
        self._group_id = f"vectordb_{id(self)}"

    async def _get_graph_store(self) -> GraphStore:
        """Get the graph store instance."""
        if self._graph_store_instance is None:
            self._graph_store_instance = await VectorDB._ensure_graph_store()
        return self._graph_store_instance

    async def search_by_similarity_threshold(
        self,
        query: str,
        limit: int,
        threshold: float,
        filter: str = "",
    ) -> list["_CompatDocument"]:
        """
        Search by semantic similarity with threshold.

        Args:
            query: Search query text
            limit: Maximum results to return
            threshold: Minimum similarity threshold (0-1)
            filter: Optional filter expression

        Returns:
            List of matching documents
        """
        graph_store = await self._get_graph_store()

        results = await graph_store.search_memories(
            query=query,
            limit=limit,
            threshold=threshold,
            memory_subdir=self._group_id,
        )

        # Apply filter if provided
        if filter:
            comparator = get_comparator(filter)
            results = [r for r in results if comparator(r.get("metadata", {}))]

        return [_dict_to_document(r) for r in results]

    async def search_by_metadata(
        self,
        filter: str,
        limit: int = 0,
    ) -> list["_CompatDocument"]:
        """
        Search by metadata filter.

        Args:
            filter: Filter expression
            limit: Maximum results (0 = unlimited)

        Returns:
            List of matching documents
        """
        graph_store = await self._get_graph_store()

        # Search with a generic query and filter by metadata
        results = await graph_store.search_memories(
            query="*",
            limit=limit if limit > 0 else 1000,
            threshold=0.0,
            memory_subdir=self._group_id,
        )

        # Apply filter
        comparator = get_comparator(filter)
        filtered = []
        for r in results:
            if comparator(r.get("metadata", {})):
                filtered.append(_dict_to_document(r))
                if limit > 0 and len(filtered) >= limit:
                    break

        return filtered

    async def insert_documents(self, docs: list[Any]) -> list[str]:
        """
        Insert documents into the vector database.

        Args:
            docs: List of Document-like objects

        Returns:
            List of generated document IDs
        """
        graph_store = await self._get_graph_store()
        ids = []

        for doc in docs:
            doc_id = str(uuid.uuid4())
            content = getattr(doc, 'page_content', str(doc))
            metadata = getattr(doc, 'metadata', {})
            metadata['id'] = doc_id

            await graph_store.save_memory(
                content=content,
                area=MemoryArea.MAIN,
                metadata=metadata,
                memory_subdir=self._group_id,
            )
            ids.append(doc_id)

        return ids

    async def delete_documents_by_ids(self, ids: list[str]) -> list[Any]:
        """
        Delete documents by their IDs.

        Args:
            ids: List of document IDs to delete

        Returns:
            List of deleted documents (empty in graph implementation)
        """
        graph_store = await self._get_graph_store()
        await graph_store.delete_memories(ids, self._group_id)
        return []


# =============================================================================
# Compatibility Layer
# =============================================================================

class _CompatDocument:
    """Compatibility wrapper for Document-like objects."""

    def __init__(self, page_content: str, metadata: dict):
        self.page_content = page_content
        self.metadata = metadata


def _dict_to_document(data: dict) -> _CompatDocument:
    """Convert dictionary to Document-like object."""
    content = data.get("content", "")
    metadata = {
        "id": data.get("id", ""),
        "score": data.get("score", 1.0),
        **data.get("metadata", {}),
    }
    return _CompatDocument(content, metadata)


def format_docs_plain(docs: list[Any]) -> list[str]:
    """Format documents as plain text strings."""
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


def cosine_normalizer(val: float) -> float:
    """Normalize cosine similarity score to 0-1 range."""
    res = (1 + val) / 2
    res = max(0, min(1, res))
    return res


def get_comparator(condition: str):
    """
    Create a comparator function from a filter expression.

    Args:
        condition: Filter expression (e.g., "area == 'main'")

    Returns:
        Function that evaluates the condition against metadata
    """
    from simpleeval import simple_eval

    def comparator(data: dict[str, Any]) -> bool:
        try:
            result = simple_eval(condition, {}, data)
            return bool(result)
        except Exception:
            return False

    return comparator
