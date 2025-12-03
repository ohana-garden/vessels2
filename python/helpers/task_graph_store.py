"""
Vessels Task Graph Store - Graph-based Task Storage

This module provides graph-native task storage for the A0 framework,
replacing JSON file storage with FalkorDB + Graphiti.

Key features:
- Store tasks as graph nodes with semantic indexing
- Link tasks to code snippets for execution
- Track task dependencies via graph relationships
- Hybrid search for task discovery
- Temporal tracking of task history
"""

import asyncio
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, List, Union, Dict
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from python.helpers.graph_store import (
    GraphStore,
    VesselNodeType,
    get_graph_store,
)
from python.helpers.code_store import (
    CodeStore,
    CodeSnippet,
    CodeRelationType,
    get_code_store,
)
from python.helpers.print_style import PrintStyle
from python.helpers import guids


# =============================================================================
# Enums
# =============================================================================

class GraphTaskState(str, Enum):
    """State of a graph task."""
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GraphTaskType(str, Enum):
    """Type of task execution."""
    IMMEDIATE = "immediate"   # Execute now
    SCHEDULED = "scheduled"   # Execute on cron schedule
    PLANNED = "planned"       # Execute at specific times
    TRIGGERED = "triggered"   # Execute on event


class TaskRelationType(str, Enum):
    """Types of relationships between tasks."""
    DEPENDS_ON = "DEPENDS_ON"     # Task depends on another
    BLOCKED_BY = "BLOCKED_BY"     # Task blocked by another
    SUBTASK_OF = "SUBTASK_OF"     # Task is subtask of parent
    FOLLOWS = "FOLLOWS"           # Task follows another in sequence
    PRODUCES = "PRODUCES"         # Task produces output for another


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class GraphTask:
    """
    A task stored in the graph with code and dependency links.

    Unlike the file-based BaseTask, GraphTask:
    - Links to reusable code snippets via graph edges
    - Has explicit task dependencies as graph relationships
    - Supports semantic search for task discovery
    - Tracks temporal execution history
    """
    id: str
    name: str
    description: str  # Semantic description for search
    state: GraphTaskState = GraphTaskState.PENDING
    task_type: GraphTaskType = GraphTaskType.IMMEDIATE

    # Execution content
    system_prompt: str = ""
    prompt: str = ""
    attachments: List[str] = field(default_factory=list)

    # Graph relationships (stored as edges, cached as IDs)
    code_refs: List[str] = field(default_factory=list)  # CodeSnippet IDs to execute
    depends_on: List[str] = field(default_factory=list)  # Other task IDs
    subtask_of: Optional[str] = None  # Parent task ID

    # Scheduling
    schedule: Optional[Dict[str, str]] = None  # Cron schedule if scheduled type
    planned_times: List[str] = field(default_factory=list)  # ISO times if planned type
    next_run: Optional[str] = None

    # Execution context
    context_id: Optional[str] = None
    agent_profile: str = "vessels"  # developer, researcher, hacker, etc.
    project_name: Optional[str] = None
    project_color: Optional[str] = None

    # Results
    last_run: Optional[str] = None
    last_result: Optional[str] = None
    run_count: int = 0
    success_count: int = 0

    # Timestamps
    created_at: str = ""
    updated_at: str = ""

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not self.id:
            self.id = guids.generate_id(10)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "state": self.state.value if isinstance(self.state, GraphTaskState) else self.state,
            "task_type": self.task_type.value if isinstance(self.task_type, GraphTaskType) else self.task_type,
            "system_prompt": self.system_prompt,
            "prompt": self.prompt,
            "attachments": self.attachments,
            "code_refs": self.code_refs,
            "depends_on": self.depends_on,
            "subtask_of": self.subtask_of,
            "schedule": self.schedule,
            "planned_times": self.planned_times,
            "next_run": self.next_run,
            "context_id": self.context_id,
            "agent_profile": self.agent_profile,
            "project_name": self.project_name,
            "project_color": self.project_color,
            "last_run": self.last_run,
            "last_result": self.last_result,
            "run_count": self.run_count,
            "success_count": self.success_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GraphTask":
        state = data.get("state", "pending")
        if isinstance(state, str):
            state = GraphTaskState(state) if state in [e.value for e in GraphTaskState] else GraphTaskState.PENDING

        task_type = data.get("task_type", "immediate")
        if isinstance(task_type, str):
            task_type = GraphTaskType(task_type) if task_type in [e.value for e in GraphTaskType] else GraphTaskType.IMMEDIATE

        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            state=state,
            task_type=task_type,
            system_prompt=data.get("system_prompt", ""),
            prompt=data.get("prompt", ""),
            attachments=data.get("attachments", []),
            code_refs=data.get("code_refs", []),
            depends_on=data.get("depends_on", []),
            subtask_of=data.get("subtask_of"),
            schedule=data.get("schedule"),
            planned_times=data.get("planned_times", []),
            next_run=data.get("next_run"),
            context_id=data.get("context_id"),
            agent_profile=data.get("agent_profile", "vessels"),
            project_name=data.get("project_name"),
            project_color=data.get("project_color"),
            last_run=data.get("last_run"),
            last_result=data.get("last_result"),
            run_count=data.get("run_count", 0),
            success_count=data.get("success_count", 0),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=data.get("metadata", {}),
            tags=data.get("tags", []),
        )

    def to_searchable_text(self) -> str:
        """Generate text for semantic indexing."""
        parts = [
            f"Task: {self.name}",
            f"Description: {self.description}",
            f"Type: {self.task_type.value if isinstance(self.task_type, GraphTaskType) else self.task_type}",
            f"Tags: {', '.join(self.tags)}" if self.tags else "",
            f"Prompt: {self.prompt[:300]}..." if len(self.prompt) > 300 else f"Prompt: {self.prompt}",
        ]
        return "\n".join(p for p in parts if p)

    @property
    def is_ready(self) -> bool:
        """Check if task is ready to run (no pending dependencies)."""
        return len(self.depends_on) == 0 and self.state == GraphTaskState.PENDING

    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.run_count == 0:
            return 0.0
        return self.success_count / self.run_count


@dataclass
class TaskExecutionContext:
    """Context for task execution with assembled code."""
    task: GraphTask
    code_snippets: List[CodeSnippet]
    assembled_code: str
    input_data: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Task Graph Store Implementation
# =============================================================================

class TaskGraphStore:
    """
    Graph-based storage for tasks with code and dependency linking.

    Uses FalkorDB + Graphiti for:
    - Semantic search of tasks
    - Task-code relationships
    - Task dependency graphs
    - Temporal execution history
    """

    _instance: Optional["TaskGraphStore"] = None
    _lock = asyncio.Lock()

    def __init__(self, graph_store: GraphStore, code_store: CodeStore):
        self.graph_store = graph_store
        self.code_store = code_store
        self._initialized = False

    @classmethod
    async def get_instance(cls) -> "TaskGraphStore":
        """Get or create the singleton task graph store instance."""
        async with cls._lock:
            if cls._instance is None:
                graph_store = await get_graph_store()
                code_store = await get_code_store()
                cls._instance = cls(graph_store, code_store)
                await cls._instance.initialize()
            return cls._instance

    async def initialize(self) -> None:
        """Initialize task graph store indices."""
        if self._initialized:
            return

        PrintStyle.standard("Initializing Task Graph Store...")
        self._initialized = True

    # =========================================================================
    # Task CRUD Operations
    # =========================================================================

    async def save_task(self, task: GraphTask) -> str:
        """
        Save a task to the graph.

        Creates a graph node with semantic indexing and establishes
        relationships to code snippets and dependent tasks.
        """
        task.updated_at = datetime.now(timezone.utc).isoformat()

        if not task.id:
            task.id = guids.generate_id(10)

        # Store as graph episode with semantic content
        episode_content = json.dumps({
            "type": VesselNodeType.TASK.value,
            "data": task.to_dict(),
            "searchable": task.to_searchable_text(),
        })

        try:
            ref_time = datetime.fromisoformat(task.created_at.replace('Z', '+00:00'))

            await self.graph_store.graphiti.add_episode(
                name=f"task_{task.id}",
                episode_body=episode_content,
                source_description=f"Task: {task.name}",
                reference_time=ref_time,
                group_id=f"task:{task.task_type.value if isinstance(task.task_type, GraphTaskType) else task.task_type}",
            )

            # Create code relationships
            for code_id in task.code_refs:
                await self.code_store.link_code_to_task(
                    code_id, task.id, CodeRelationType.EXECUTES
                )

            # Create dependency relationships
            for dep_id in task.depends_on:
                await self._create_task_relationship(
                    task.id, dep_id, TaskRelationType.DEPENDS_ON
                )

            # Create subtask relationship
            if task.subtask_of:
                await self._create_task_relationship(
                    task.id, task.subtask_of, TaskRelationType.SUBTASK_OF
                )

            PrintStyle.standard(f"Saved task: {task.name} ({task.id})")

        except Exception as e:
            PrintStyle.error(f"Failed to save task: {e}")
            raise

        return task.id

    async def get_task(self, task_id: str) -> Optional[GraphTask]:
        """Get a task by ID."""
        try:
            query = f"""
            MATCH (n:Episode) WHERE n.name = 'task_{task_id}'
            RETURN n.content as content
            """
            result = await self.graph_store._driver.execute_query(query)

            if result and len(result) > 0:
                content = json.loads(result[0].get("content", "{}"))
                if content.get("type") == VesselNodeType.TASK.value:
                    return GraphTask.from_dict(content.get("data", {}))
        except Exception as e:
            PrintStyle.error(f"Failed to get task {task_id}: {e}")

        return None

    async def update_task(self, task: GraphTask) -> bool:
        """Update an existing task."""
        if not task.id:
            return False

        # Delete old and save new
        await self.delete_task(task.id)
        await self.save_task(task)
        return True

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task and its relationships."""
        try:
            query = f"""
            MATCH (n:Episode) WHERE n.name = 'task_{task_id}'
            DETACH DELETE n
            """
            await self.graph_store._driver.execute_query(query)
            return True
        except Exception as e:
            PrintStyle.error(f"Failed to delete task {task_id}: {e}")
            return False

    async def _create_task_relationship(
        self,
        from_task_id: str,
        to_task_id: str,
        relation: TaskRelationType,
    ) -> bool:
        """Create a relationship between two tasks."""
        try:
            query = f"""
            MATCH (from:Episode) WHERE from.name = 'task_{from_task_id}'
            MATCH (to:Episode) WHERE to.name = 'task_{to_task_id}'
            MERGE (from)-[:{relation.value}]->(to)
            """
            await self.graph_store._driver.execute_query(query)
            return True
        except Exception as e:
            PrintStyle.error(f"Failed to create task relationship: {e}")
            return False

    # =========================================================================
    # Task Search Operations
    # =========================================================================

    async def search_tasks(
        self,
        query: str,
        task_type: Optional[GraphTaskType] = None,
        state: Optional[GraphTaskState] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[GraphTask]:
        """
        Search for tasks using hybrid retrieval.

        Combines semantic search with filters.
        """
        group_ids = [f"task:{task_type.value}"] if task_type else None

        try:
            results = await self.graph_store.graphiti.search(
                query=query,
                num_results=limit * 2,  # Over-fetch for filtering
                group_ids=group_ids,
            )

            tasks = []
            for result in results:
                try:
                    content = json.loads(str(result.fact) if hasattr(result, 'fact') else "{}")
                    if content.get("type") == VesselNodeType.TASK.value:
                        task = GraphTask.from_dict(content.get("data", {}))

                        # Apply state filter
                        if state and task.state != state:
                            continue

                        # Apply tag filter
                        if tags and not any(t in task.tags for t in tags):
                            continue

                        tasks.append(task)

                        if len(tasks) >= limit:
                            break
                except Exception:
                    continue

            return tasks

        except Exception as e:
            PrintStyle.error(f"Task search failed: {e}")
            return []

    async def list_tasks(
        self,
        task_type: Optional[GraphTaskType] = None,
        state: Optional[GraphTaskState] = None,
        limit: int = 50,
    ) -> List[GraphTask]:
        """List tasks with optional filtering."""
        try:
            if task_type:
                query = f"""
                MATCH (n:Episode) WHERE n.name STARTS WITH 'task_'
                AND n.group_id = 'task:{task_type.value}'
                RETURN n.content as content
                ORDER BY n.reference_time DESC
                LIMIT {limit}
                """
            else:
                query = f"""
                MATCH (n:Episode) WHERE n.name STARTS WITH 'task_'
                RETURN n.content as content
                ORDER BY n.reference_time DESC
                LIMIT {limit}
                """

            results = await self.graph_store._driver.execute_query(query)

            tasks = []
            for row in results:
                try:
                    content = json.loads(row.get("content", "{}"))
                    if content.get("type") == VesselNodeType.TASK.value:
                        task = GraphTask.from_dict(content.get("data", {}))

                        # Apply state filter
                        if state and task.state != state:
                            continue

                        tasks.append(task)
                except Exception:
                    continue

            return tasks

        except Exception as e:
            PrintStyle.error(f"Failed to list tasks: {e}")
            return []

    async def get_ready_tasks(self) -> List[GraphTask]:
        """Get all tasks that are ready to run."""
        tasks = await self.list_tasks(state=GraphTaskState.PENDING)
        return [t for t in tasks if t.is_ready]

    async def get_task_dependencies(self, task_id: str) -> List[GraphTask]:
        """Get all tasks that a task depends on."""
        try:
            query = f"""
            MATCH (task:Episode)-[:DEPENDS_ON]->(dep:Episode)
            WHERE task.name = 'task_{task_id}'
            RETURN dep.content as content
            """
            results = await self.graph_store._driver.execute_query(query)

            tasks = []
            for row in results:
                try:
                    content = json.loads(row.get("content", "{}"))
                    if content.get("type") == VesselNodeType.TASK.value:
                        tasks.append(GraphTask.from_dict(content.get("data", {})))
                except Exception:
                    continue

            return tasks

        except Exception as e:
            PrintStyle.error(f"Failed to get task dependencies: {e}")
            return []

    async def get_subtasks(self, parent_task_id: str) -> List[GraphTask]:
        """Get all subtasks of a parent task."""
        try:
            query = f"""
            MATCH (sub:Episode)-[:SUBTASK_OF]->(parent:Episode)
            WHERE parent.name = 'task_{parent_task_id}'
            RETURN sub.content as content
            """
            results = await self.graph_store._driver.execute_query(query)

            tasks = []
            for row in results:
                try:
                    content = json.loads(row.get("content", "{}"))
                    if content.get("type") == VesselNodeType.TASK.value:
                        tasks.append(GraphTask.from_dict(content.get("data", {})))
                except Exception:
                    continue

            return tasks

        except Exception as e:
            PrintStyle.error(f"Failed to get subtasks: {e}")
            return []

    # =========================================================================
    # Task Execution Operations
    # =========================================================================

    async def prepare_execution(self, task_id: str) -> Optional[TaskExecutionContext]:
        """
        Prepare a task for execution by assembling code and context.

        Returns a TaskExecutionContext with all code snippets assembled.
        """
        task = await self.get_task(task_id)
        if not task:
            return None

        # Get linked code snippets
        code_snippets = []
        for code_id in task.code_refs:
            snippet = await self.code_store.get_code(code_id)
            if snippet:
                code_snippets.append(snippet)

        # Assemble code in dependency order
        assembled_code = self._assemble_code(code_snippets)

        return TaskExecutionContext(
            task=task,
            code_snippets=code_snippets,
            assembled_code=assembled_code,
        )

    def _assemble_code(self, snippets: List[CodeSnippet]) -> str:
        """Assemble code snippets into a single executable block."""
        if not snippets:
            return ""

        # Group by language
        by_language: Dict[str, List[CodeSnippet]] = {}
        for snippet in snippets:
            lang = snippet.language.value if isinstance(snippet.language, Enum) else snippet.language
            if lang not in by_language:
                by_language[lang] = []
            by_language[lang].append(snippet)

        # Assemble each language group
        parts = []
        for lang, lang_snippets in by_language.items():
            parts.append(f"# === {lang.upper()} CODE ===")
            for snippet in lang_snippets:
                parts.append(f"# {snippet.name}: {snippet.description}")
                parts.append(snippet.code)
                parts.append("")

        return "\n".join(parts)

    async def mark_running(self, task_id: str) -> bool:
        """Mark a task as running."""
        task = await self.get_task(task_id)
        if not task:
            return False

        task.state = GraphTaskState.RUNNING
        task.last_run = datetime.now(timezone.utc).isoformat()
        return await self.update_task(task)

    async def mark_completed(
        self,
        task_id: str,
        result: str,
        success: bool = True,
    ) -> bool:
        """Mark a task as completed with result."""
        task = await self.get_task(task_id)
        if not task:
            return False

        task.state = GraphTaskState.COMPLETED if success else GraphTaskState.FAILED
        task.last_result = result
        task.run_count += 1
        if success:
            task.success_count += 1

        # Update code usage stats
        for code_id in task.code_refs:
            await self.code_store.record_usage(code_id, success)

        return await self.update_task(task)


# =============================================================================
# Module-level helpers
# =============================================================================

async def get_task_graph_store() -> TaskGraphStore:
    """Get the task graph store singleton instance."""
    return await TaskGraphStore.get_instance()
