"""
Vessels Code Store - Graph-based Code Snippet Storage

This module provides agentic code storage and execution tracking using
FalkorDB + Graphiti as the backend. Code snippets are stored as graph
nodes with semantic search capabilities for intelligent code reuse.

Key features:
- Store reusable code snippets with semantic descriptions
- Track execution history and results
- Link code to tasks via graph relationships
- Hybrid search (semantic + keyword + graph) for code discovery
"""

import asyncio
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, List
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from python.helpers.graph_store import (
    GraphStore,
    VesselNodeType,
    get_graph_store,
)
from python.helpers.print_style import PrintStyle
from python.helpers import guids


# =============================================================================
# Enums
# =============================================================================

class CodeLanguage(str, Enum):
    """Supported code languages for execution."""
    PYTHON = "python"
    NODEJS = "nodejs"
    TERMINAL = "terminal"
    SHELL = "shell"  # alias for terminal


class ExecutionStatus(str, Enum):
    """Status of a code execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"


class CodeRelationType(str, Enum):
    """Types of relationships between code nodes."""
    IMPORTS = "IMPORTS"       # Code imports another code snippet
    EXTENDS = "EXTENDS"       # Code extends/builds on another
    PRODUCES = "PRODUCES"     # Task produces this code
    EXECUTES = "EXECUTES"     # Task executes this code
    DERIVED_FROM = "DERIVED_FROM"  # Code was derived from execution result


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class CodeSnippet:
    """
    A reusable code snippet stored in the graph.

    Code snippets can be discovered through semantic search and
    linked to tasks for execution. They form part of the agent's
    "procedural memory" - knowledge about how to do things.
    """
    id: str
    name: str
    language: CodeLanguage
    code: str
    description: str  # Semantic description for search
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # IDs of other snippets
    parameters: dict = field(default_factory=dict)  # Expected input parameters
    created_at: str = ""
    updated_at: str = ""
    last_used: str = ""
    use_count: int = 0
    success_rate: float = 0.0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language.value if isinstance(self.language, CodeLanguage) else self.language,
            "code": self.code,
            "description": self.description,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "parameters": self.parameters,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_used": self.last_used,
            "use_count": self.use_count,
            "success_rate": self.success_rate,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CodeSnippet":
        language = data.get("language", "python")
        if isinstance(language, str):
            language = CodeLanguage(language) if language in [e.value for e in CodeLanguage] else CodeLanguage.PYTHON
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            language=language,
            code=data.get("code", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            dependencies=data.get("dependencies", []),
            parameters=data.get("parameters", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            last_used=data.get("last_used", ""),
            use_count=data.get("use_count", 0),
            success_rate=data.get("success_rate", 0.0),
            metadata=data.get("metadata", {}),
        )

    def to_searchable_text(self) -> str:
        """Generate text for semantic indexing."""
        parts = [
            f"Code: {self.name}",
            f"Language: {self.language.value if isinstance(self.language, CodeLanguage) else self.language}",
            f"Description: {self.description}",
            f"Tags: {', '.join(self.tags)}" if self.tags else "",
            f"Code:\n{self.code[:500]}..." if len(self.code) > 500 else f"Code:\n{self.code}",
        ]
        return "\n".join(p for p in parts if p)


@dataclass
class ExecutionRecord:
    """
    Record of a code execution with results.

    Tracks the history of code executions for learning and optimization.
    """
    id: str
    code_id: str  # Reference to CodeSnippet
    task_id: Optional[str] = None  # Reference to GraphTask
    context_id: Optional[str] = None  # Agent context
    status: ExecutionStatus = ExecutionStatus.PENDING
    input_data: dict = field(default_factory=dict)
    output: str = ""
    error: str = ""
    started_at: str = ""
    completed_at: str = ""
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "code_id": self.code_id,
            "task_id": self.task_id,
            "context_id": self.context_id,
            "status": self.status.value if isinstance(self.status, ExecutionStatus) else self.status,
            "input_data": self.input_data,
            "output": self.output,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionRecord":
        status = data.get("status", "pending")
        if isinstance(status, str):
            status = ExecutionStatus(status) if status in [e.value for e in ExecutionStatus] else ExecutionStatus.PENDING
        return cls(
            id=data.get("id", ""),
            code_id=data.get("code_id", ""),
            task_id=data.get("task_id"),
            context_id=data.get("context_id"),
            status=status,
            input_data=data.get("input_data", {}),
            output=data.get("output", ""),
            error=data.get("error", ""),
            started_at=data.get("started_at", ""),
            completed_at=data.get("completed_at", ""),
            duration_ms=data.get("duration_ms", 0),
            metadata=data.get("metadata", {}),
        )

    def complete(self, output: str = "", error: str = "", status: Optional[ExecutionStatus] = None):
        """Mark execution as complete with results."""
        self.completed_at = datetime.now(timezone.utc).isoformat()
        self.output = output
        self.error = error

        if status:
            self.status = status
        elif error:
            self.status = ExecutionStatus.FAILURE
        else:
            self.status = ExecutionStatus.SUCCESS

        # Calculate duration
        try:
            start = datetime.fromisoformat(self.started_at.replace('Z', '+00:00'))
            end = datetime.fromisoformat(self.completed_at.replace('Z', '+00:00'))
            self.duration_ms = int((end - start).total_seconds() * 1000)
        except Exception:
            pass


# =============================================================================
# Code Store Implementation
# =============================================================================

class CodeStore:
    """
    Graph-based storage for code snippets and execution history.

    Uses FalkorDB + Graphiti for:
    - Semantic search of code snippets
    - Temporal tracking of executions
    - Graph relationships between code, tasks, and agents
    """

    _instance: Optional["CodeStore"] = None
    _lock = asyncio.Lock()

    def __init__(self, graph_store: GraphStore):
        self.graph_store = graph_store
        self._initialized = False

    @classmethod
    async def get_instance(cls) -> "CodeStore":
        """Get or create the singleton code store instance."""
        async with cls._lock:
            if cls._instance is None:
                graph_store = await get_graph_store()
                cls._instance = cls(graph_store)
                await cls._instance.initialize()
            return cls._instance

    async def initialize(self) -> None:
        """Initialize code store indices."""
        if self._initialized:
            return

        PrintStyle.standard("Initializing Code Store...")
        self._initialized = True

    # =========================================================================
    # Code Snippet Operations
    # =========================================================================

    async def save_code(self, snippet: CodeSnippet) -> str:
        """
        Save a code snippet to the graph.

        Creates a graph node with semantic indexing for search.
        """
        snippet.updated_at = datetime.now(timezone.utc).isoformat()

        if not snippet.id:
            snippet.id = guids.generate_id(10)

        # Store as graph episode with semantic content
        episode_content = json.dumps({
            "type": VesselNodeType.CODE.value,
            "data": snippet.to_dict(),
            "searchable": snippet.to_searchable_text(),
        })

        try:
            await self.graph_store.graphiti.add_episode(
                name=f"code_{snippet.id}",
                episode_body=episode_content,
                source_description=f"Code snippet: {snippet.name} ({snippet.language.value})",
                reference_time=datetime.fromisoformat(snippet.created_at.replace('Z', '+00:00')),
                group_id=f"code:{snippet.language.value}",
            )
            PrintStyle.standard(f"Saved code snippet: {snippet.name} ({snippet.id})")
        except Exception as e:
            PrintStyle.error(f"Failed to save code snippet: {e}")
            raise

        return snippet.id

    async def get_code(self, code_id: str) -> Optional[CodeSnippet]:
        """Get a code snippet by ID."""
        try:
            query = f"""
            MATCH (n:Episode) WHERE n.name = 'code_{code_id}'
            RETURN n.content as content
            """
            result = await self.graph_store._driver.execute_query(query)

            if result and len(result) > 0:
                content = json.loads(result[0].get("content", "{}"))
                if content.get("type") == VesselNodeType.CODE.value:
                    return CodeSnippet.from_dict(content.get("data", {}))
        except Exception as e:
            PrintStyle.error(f"Failed to get code snippet {code_id}: {e}")

        return None

    async def update_code(self, snippet: CodeSnippet) -> bool:
        """Update an existing code snippet."""
        if not snippet.id:
            return False

        # Delete old and save new (Graphiti handles this atomically)
        await self.delete_code(snippet.id)
        await self.save_code(snippet)
        return True

    async def delete_code(self, code_id: str) -> bool:
        """Delete a code snippet."""
        try:
            query = f"""
            MATCH (n:Episode) WHERE n.name = 'code_{code_id}'
            DETACH DELETE n
            """
            await self.graph_store._driver.execute_query(query)
            return True
        except Exception as e:
            PrintStyle.error(f"Failed to delete code snippet {code_id}: {e}")
            return False

    async def search_code(
        self,
        query: str,
        language: Optional[CodeLanguage] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[CodeSnippet]:
        """
        Search for code snippets using hybrid retrieval.

        Combines semantic search with keyword and tag filtering.
        """
        group_ids = [f"code:{language.value}"] if language else None

        try:
            results = await self.graph_store.graphiti.search(
                query=query,
                num_results=limit * 2,  # Over-fetch for post-filtering
                group_ids=group_ids,
            )

            snippets = []
            for result in results:
                try:
                    # Parse the stored content
                    content = json.loads(str(result.fact) if hasattr(result, 'fact') else "{}")
                    if content.get("type") == VesselNodeType.CODE.value:
                        snippet = CodeSnippet.from_dict(content.get("data", {}))

                        # Apply tag filter
                        if tags:
                            if not any(t in snippet.tags for t in tags):
                                continue

                        snippets.append(snippet)

                        if len(snippets) >= limit:
                            break
                except Exception as e:
                    PrintStyle.error(f"Failed to parse code result: {e}")
                    continue

            return snippets

        except Exception as e:
            PrintStyle.error(f"Code search failed: {e}")
            return []

    async def list_code(
        self,
        language: Optional[CodeLanguage] = None,
        limit: int = 50,
    ) -> List[CodeSnippet]:
        """List all code snippets, optionally filtered by language."""
        try:
            if language:
                query = f"""
                MATCH (n:Episode) WHERE n.name STARTS WITH 'code_'
                AND n.group_id = 'code:{language.value}'
                RETURN n.content as content
                ORDER BY n.reference_time DESC
                LIMIT {limit}
                """
            else:
                query = f"""
                MATCH (n:Episode) WHERE n.name STARTS WITH 'code_'
                RETURN n.content as content
                ORDER BY n.reference_time DESC
                LIMIT {limit}
                """

            results = await self.graph_store._driver.execute_query(query)

            snippets = []
            for row in results:
                try:
                    content = json.loads(row.get("content", "{}"))
                    if content.get("type") == VesselNodeType.CODE.value:
                        snippets.append(CodeSnippet.from_dict(content.get("data", {})))
                except Exception as e:
                    PrintStyle.error(f"Failed to parse code: {e}")

            return snippets

        except Exception as e:
            PrintStyle.error(f"Failed to list code: {e}")
            return []

    async def record_usage(self, code_id: str, success: bool = True) -> None:
        """Record that a code snippet was used."""
        snippet = await self.get_code(code_id)
        if snippet:
            snippet.use_count += 1
            snippet.last_used = datetime.now(timezone.utc).isoformat()

            # Update success rate
            if snippet.use_count > 0:
                total_successes = snippet.success_rate * (snippet.use_count - 1)
                if success:
                    total_successes += 1
                snippet.success_rate = total_successes / snippet.use_count

            await self.update_code(snippet)

    # =========================================================================
    # Execution Record Operations
    # =========================================================================

    async def save_execution(self, record: ExecutionRecord) -> str:
        """Save an execution record to the graph."""
        if not record.id:
            record.id = guids.generate_id(10)

        episode_content = json.dumps({
            "type": VesselNodeType.EXECUTION.value,
            "data": record.to_dict(),
        })

        try:
            ref_time = datetime.fromisoformat(record.started_at.replace('Z', '+00:00'))

            await self.graph_store.graphiti.add_episode(
                name=f"execution_{record.id}",
                episode_body=episode_content,
                source_description=f"Code execution: {record.code_id}",
                reference_time=ref_time,
                group_id=f"execution:{record.code_id}",
            )
        except Exception as e:
            PrintStyle.error(f"Failed to save execution record: {e}")
            raise

        return record.id

    async def get_execution(self, execution_id: str) -> Optional[ExecutionRecord]:
        """Get an execution record by ID."""
        try:
            query = f"""
            MATCH (n:Episode) WHERE n.name = 'execution_{execution_id}'
            RETURN n.content as content
            """
            result = await self.graph_store._driver.execute_query(query)

            if result and len(result) > 0:
                content = json.loads(result[0].get("content", "{}"))
                if content.get("type") == VesselNodeType.EXECUTION.value:
                    return ExecutionRecord.from_dict(content.get("data", {}))
        except Exception as e:
            PrintStyle.error(f"Failed to get execution {execution_id}: {e}")

        return None

    async def get_execution_history(
        self,
        code_id: str,
        limit: int = 20,
    ) -> List[ExecutionRecord]:
        """Get execution history for a code snippet."""
        try:
            query = f"""
            MATCH (n:Episode) WHERE n.group_id = 'execution:{code_id}'
            RETURN n.content as content
            ORDER BY n.reference_time DESC
            LIMIT {limit}
            """
            results = await self.graph_store._driver.execute_query(query)

            records = []
            for row in results:
                try:
                    content = json.loads(row.get("content", "{}"))
                    if content.get("type") == VesselNodeType.EXECUTION.value:
                        records.append(ExecutionRecord.from_dict(content.get("data", {})))
                except Exception:
                    continue

            return records

        except Exception as e:
            PrintStyle.error(f"Failed to get execution history: {e}")
            return []

    # =========================================================================
    # Code-Task Linking Operations
    # =========================================================================

    async def link_code_to_task(
        self,
        code_id: str,
        task_id: str,
        relation: CodeRelationType = CodeRelationType.EXECUTES,
    ) -> bool:
        """Create a relationship between code and a task."""
        try:
            query = f"""
            MATCH (code:Episode) WHERE code.name = 'code_{code_id}'
            MATCH (task:Episode) WHERE task.name = 'task_{task_id}'
            MERGE (task)-[:{relation.value}]->(code)
            """
            await self.graph_store._driver.execute_query(query)
            return True
        except Exception as e:
            PrintStyle.error(f"Failed to link code to task: {e}")
            return False

    async def get_task_code(self, task_id: str) -> List[CodeSnippet]:
        """Get all code snippets linked to a task."""
        try:
            query = f"""
            MATCH (task:Episode)-[r]->(code:Episode)
            WHERE task.name = 'task_{task_id}'
            AND code.name STARTS WITH 'code_'
            RETURN code.content as content, type(r) as relation
            """
            results = await self.graph_store._driver.execute_query(query)

            snippets = []
            for row in results:
                try:
                    content = json.loads(row.get("content", "{}"))
                    if content.get("type") == VesselNodeType.CODE.value:
                        snippets.append(CodeSnippet.from_dict(content.get("data", {})))
                except Exception:
                    continue

            return snippets

        except Exception as e:
            PrintStyle.error(f"Failed to get task code: {e}")
            return []


# =============================================================================
# Module-level helpers
# =============================================================================

async def get_code_store() -> CodeStore:
    """Get the code store singleton instance."""
    return await CodeStore.get_instance()
