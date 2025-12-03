"""
Task Scheduler - Graph-Native Implementation (A0 Framework)

This module provides graph-native task scheduling using FalkorDB + Graphiti
as the sole storage backend. No JSON file fallback.

Tasks, code snippets, and execution history all live in the graph.
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from python.helpers.task_graph_store import (
    TaskGraphStore,
    GraphTask,
    GraphTaskState,
    GraphTaskType,
    get_task_graph_store,
)
from python.helpers.code_store import (
    CodeStore,
    CodeSnippet,
    CodeLanguage,
    ExecutionRecord,
    ExecutionStatus,
    get_code_store,
)
from python.helpers.print_style import PrintStyle


class GraphScheduler:
    """
    Graph-native task scheduler using FalkorDB + Graphiti.

    All tasks are stored as graph nodes. No JSON file storage.
    Fails explicitly if graph store is not available.
    """

    _instance: Optional["GraphScheduler"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._task_store: Optional[TaskGraphStore] = None
        self._code_store: Optional[CodeStore] = None
        self._initialized = False

    @classmethod
    async def get_instance(cls) -> "GraphScheduler":
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance.initialize()
            return cls._instance

    async def initialize(self) -> None:
        """Initialize graph stores. Fails if unavailable."""
        if self._initialized:
            return

        self._task_store = await get_task_graph_store()
        self._code_store = await get_code_store()
        self._initialized = True
        PrintStyle.standard("Graph scheduler initialized")

    def _require_initialized(self):
        """Ensure scheduler is initialized."""
        if not self._initialized:
            raise RuntimeError("Graph scheduler not initialized. Call initialize() first.")

    @property
    def task_store(self) -> TaskGraphStore:
        self._require_initialized()
        return self._task_store  # type: ignore

    @property
    def code_store(self) -> CodeStore:
        self._require_initialized()
        return self._code_store  # type: ignore

    # =========================================================================
    # Task Operations
    # =========================================================================

    async def create_task(
        self,
        name: str,
        prompt: str,
        description: str = "",
        system_prompt: str = "",
        task_type: GraphTaskType = GraphTaskType.IMMEDIATE,
        attachments: Optional[List[str]] = None,
        code_refs: Optional[List[str]] = None,
        depends_on: Optional[List[str]] = None,
        schedule: Optional[Dict[str, str]] = None,
        planned_times: Optional[List[str]] = None,
        context_id: Optional[str] = None,
        agent_profile: str = "vessels",
        project_name: Optional[str] = None,
        project_color: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """Create a new task in the graph."""
        task = GraphTask(
            id="",  # Will be generated
            name=name,
            description=description or f"Task: {name}",
            state=GraphTaskState.PENDING,
            task_type=task_type,
            system_prompt=system_prompt,
            prompt=prompt,
            attachments=attachments or [],
            code_refs=code_refs or [],
            depends_on=depends_on or [],
            schedule=schedule,
            planned_times=planned_times or [],
            context_id=context_id,
            agent_profile=agent_profile,
            project_name=project_name,
            project_color=project_color,
            tags=tags or [],
        )

        return await self.task_store.save_task(task)

    async def get_task(self, task_id: str) -> Optional[GraphTask]:
        """Get a task by ID."""
        return await self.task_store.get_task(task_id)

    async def update_task(self, task: GraphTask) -> bool:
        """Update a task."""
        return await self.task_store.update_task(task)

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        return await self.task_store.delete_task(task_id)

    async def list_tasks(
        self,
        task_type: Optional[GraphTaskType] = None,
        state: Optional[GraphTaskState] = None,
        limit: int = 50,
    ) -> List[GraphTask]:
        """List tasks with optional filtering."""
        return await self.task_store.list_tasks(task_type=task_type, state=state, limit=limit)

    async def search_tasks(
        self,
        query: str,
        task_type: Optional[GraphTaskType] = None,
        state: Optional[GraphTaskState] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[GraphTask]:
        """Search tasks using semantic search."""
        return await self.task_store.search_tasks(
            query=query,
            task_type=task_type,
            state=state,
            tags=tags,
            limit=limit,
        )

    async def get_ready_tasks(self) -> List[GraphTask]:
        """Get tasks ready to execute."""
        return await self.task_store.get_ready_tasks()

    async def get_task_dependencies(self, task_id: str) -> List[GraphTask]:
        """Get tasks that a task depends on."""
        return await self.task_store.get_task_dependencies(task_id)

    async def get_subtasks(self, parent_task_id: str) -> List[GraphTask]:
        """Get subtasks of a parent task."""
        return await self.task_store.get_subtasks(parent_task_id)

    # =========================================================================
    # Task Execution
    # =========================================================================

    async def run_task(self, task_id: str) -> Optional[GraphTask]:
        """Mark task as running and return it for execution."""
        task = await self.get_task(task_id)
        if not task:
            raise ValueError(f"Task not found: {task_id}")

        if task.state == GraphTaskState.RUNNING:
            raise ValueError(f"Task already running: {task_id}")

        if task.state == GraphTaskState.CANCELLED:
            raise ValueError(f"Task is cancelled: {task_id}")

        await self.task_store.mark_running(task_id)
        return await self.get_task(task_id)

    async def complete_task(
        self,
        task_id: str,
        result: str,
        success: bool = True,
    ) -> bool:
        """Mark task as completed with result."""
        return await self.task_store.mark_completed(task_id, result, success)

    async def prepare_execution(self, task_id: str):
        """Prepare task for execution with assembled code."""
        return await self.task_store.prepare_execution(task_id)

    # =========================================================================
    # Code Snippet Operations
    # =========================================================================

    async def save_code_snippet(
        self,
        name: str,
        language: str,
        code: str,
        description: str,
        tags: Optional[List[str]] = None,
    ) -> Optional[str]:
        """Save a code snippet."""
        try:
            lang = CodeLanguage(language) if language in [e.value for e in CodeLanguage] else CodeLanguage.PYTHON

            snippet = CodeSnippet(
                id="",
                name=name,
                language=lang,
                code=code,
                description=description,
                tags=tags or [],
            )

            return await self.code_store.save_code(snippet)

        except Exception as e:
            PrintStyle.error(f"Failed to save code snippet: {e}")
            return None

    async def get_code_snippet(self, code_id: str) -> Optional[CodeSnippet]:
        """Get a code snippet by ID."""
        return await self.code_store.get_code(code_id)

    async def search_code(
        self,
        query: str,
        language: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[CodeSnippet]:
        """Search for code snippets."""
        lang = None
        if language:
            try:
                lang = CodeLanguage(language)
            except ValueError:
                pass

        return await self.code_store.search_code(
            query=query,
            language=lang,
            tags=tags,
            limit=limit,
        )

    async def list_code(
        self,
        language: Optional[str] = None,
        limit: int = 50,
    ) -> List[CodeSnippet]:
        """List code snippets."""
        lang = None
        if language:
            try:
                lang = CodeLanguage(language)
            except ValueError:
                pass

        return await self.code_store.list_code(language=lang, limit=limit)

    async def link_code_to_task(self, task_id: str, code_id: str) -> bool:
        """Link a code snippet to a task."""
        task = await self.get_task(task_id)
        if not task:
            return False

        if code_id not in task.code_refs:
            task.code_refs.append(code_id)
            return await self.update_task(task)

        return True

    async def get_task_with_code(self, task_id: str) -> Dict[str, Any]:
        """Get a task with all its linked code snippets."""
        task = await self.get_task(task_id)
        if not task:
            return {}

        code_snippets = []
        for code_id in task.code_refs:
            snippet = await self.get_code_snippet(code_id)
            if snippet:
                code_snippets.append(snippet.to_dict())

        return {
            "task": task.to_dict(),
            "code_snippets": code_snippets,
        }

    # =========================================================================
    # Execution Tracking
    # =========================================================================

    async def record_execution(
        self,
        code_id: str,
        output: str,
        success: bool = True,
        task_id: Optional[str] = None,
        context_id: Optional[str] = None,
    ) -> Optional[str]:
        """Record a code execution."""
        record = ExecutionRecord(
            id="",
            code_id=code_id,
            task_id=task_id,
            context_id=context_id,
            status=ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILURE,
            output=output,
        )
        record.complete(output=output)

        return await self.code_store.save_execution(record)

    async def get_execution_history(
        self,
        code_id: str,
        limit: int = 20,
    ) -> List[ExecutionRecord]:
        """Get execution history for a code snippet."""
        return await self.code_store.get_execution_history(code_id, limit=limit)


# =============================================================================
# Module-level helper
# =============================================================================

async def get_graph_scheduler() -> GraphScheduler:
    """Get the graph scheduler singleton."""
    return await GraphScheduler.get_instance()
