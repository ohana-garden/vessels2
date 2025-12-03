"""
Task Scheduler Graph Integration

This module bridges the existing TaskScheduler with the new graph-based
storage system, providing:
- Conversion between file-based tasks and graph tasks
- Graph storage as primary backend with JSON fallback
- Code snippet integration for task execution
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, List, Union, Dict, Any

from python.helpers.task_scheduler import (
    TaskScheduler,
    SchedulerTaskList,
    BaseTask,
    ScheduledTask,
    AdHocTask,
    PlannedTask,
    TaskState,
    TaskType,
    TaskSchedule,
    TaskPlan,
)
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


# =============================================================================
# State Mapping
# =============================================================================

def task_state_to_graph_state(state: TaskState) -> GraphTaskState:
    """Convert file-based TaskState to GraphTaskState."""
    mapping = {
        TaskState.IDLE: GraphTaskState.PENDING,
        TaskState.RUNNING: GraphTaskState.RUNNING,
        TaskState.DISABLED: GraphTaskState.CANCELLED,
        TaskState.ERROR: GraphTaskState.FAILED,
    }
    return mapping.get(state, GraphTaskState.PENDING)


def graph_state_to_task_state(state: GraphTaskState) -> TaskState:
    """Convert GraphTaskState to file-based TaskState."""
    mapping = {
        GraphTaskState.PENDING: TaskState.IDLE,
        GraphTaskState.SCHEDULED: TaskState.IDLE,
        GraphTaskState.RUNNING: TaskState.RUNNING,
        GraphTaskState.COMPLETED: TaskState.IDLE,
        GraphTaskState.FAILED: TaskState.ERROR,
        GraphTaskState.CANCELLED: TaskState.DISABLED,
    }
    return mapping.get(state, TaskState.IDLE)


def task_type_to_graph_type(task: Union[ScheduledTask, AdHocTask, PlannedTask]) -> GraphTaskType:
    """Convert file-based task type to GraphTaskType."""
    if isinstance(task, ScheduledTask):
        return GraphTaskType.SCHEDULED
    elif isinstance(task, AdHocTask):
        return GraphTaskType.IMMEDIATE
    elif isinstance(task, PlannedTask):
        return GraphTaskType.PLANNED
    return GraphTaskType.IMMEDIATE


# =============================================================================
# Task Conversion
# =============================================================================

def base_task_to_graph_task(task: Union[ScheduledTask, AdHocTask, PlannedTask]) -> GraphTask:
    """Convert a file-based task to a GraphTask."""
    # Build schedule dict for scheduled tasks
    schedule_dict = None
    if isinstance(task, ScheduledTask):
        schedule_dict = {
            "minute": task.schedule.minute,
            "hour": task.schedule.hour,
            "day": task.schedule.day,
            "month": task.schedule.month,
            "weekday": task.schedule.weekday,
            "timezone": task.schedule.timezone,
        }

    # Build planned times for planned tasks
    planned_times = []
    if isinstance(task, PlannedTask):
        planned_times = [dt.isoformat() for dt in task.plan.todo]

    return GraphTask(
        id=task.uuid,
        name=task.name,
        description=f"Task: {task.name}",  # Can be enhanced
        state=task_state_to_graph_state(task.state),
        task_type=task_type_to_graph_type(task),
        system_prompt=task.system_prompt,
        prompt=task.prompt,
        attachments=task.attachments,
        schedule=schedule_dict,
        planned_times=planned_times,
        next_run=task.get_next_run().isoformat() if task.get_next_run() else None,
        context_id=task.context_id,
        project_name=task.project_name,
        project_color=task.project_color,
        last_run=task.last_run.isoformat() if task.last_run else None,
        last_result=task.last_result,
        created_at=task.created_at.isoformat() if task.created_at else "",
        updated_at=task.updated_at.isoformat() if task.updated_at else "",
    )


def graph_task_to_base_task(graph_task: GraphTask) -> Union[ScheduledTask, AdHocTask, PlannedTask]:
    """Convert a GraphTask back to a file-based task."""
    common_args = {
        "uuid": graph_task.id,
        "name": graph_task.name,
        "state": graph_state_to_task_state(graph_task.state),
        "system_prompt": graph_task.system_prompt,
        "prompt": graph_task.prompt,
        "attachments": graph_task.attachments,
        "context_id": graph_task.context_id,
        "project_name": graph_task.project_name,
        "project_color": graph_task.project_color,
    }

    if graph_task.last_run:
        try:
            common_args["last_run"] = datetime.fromisoformat(graph_task.last_run.replace('Z', '+00:00'))
        except Exception:
            pass

    common_args["last_result"] = graph_task.last_result

    if graph_task.task_type == GraphTaskType.SCHEDULED and graph_task.schedule:
        schedule = TaskSchedule(
            minute=graph_task.schedule.get("minute", "*"),
            hour=graph_task.schedule.get("hour", "*"),
            day=graph_task.schedule.get("day", "*"),
            month=graph_task.schedule.get("month", "*"),
            weekday=graph_task.schedule.get("weekday", "*"),
            timezone=graph_task.schedule.get("timezone", "UTC"),
        )
        return ScheduledTask(schedule=schedule, **common_args)

    elif graph_task.task_type == GraphTaskType.PLANNED:
        todo_times = []
        for time_str in graph_task.planned_times:
            try:
                todo_times.append(datetime.fromisoformat(time_str.replace('Z', '+00:00')))
            except Exception:
                pass
        plan = TaskPlan.create(todo=todo_times)
        return PlannedTask(plan=plan, **common_args)

    else:
        # AdHocTask (immediate)
        return AdHocTask(token=str(hash(graph_task.id))[-19:], **common_args)


# =============================================================================
# Graph-Enabled Scheduler
# =============================================================================

class GraphEnabledScheduler:
    """
    Extended TaskScheduler that uses graph storage as primary backend.

    Provides:
    - Graph-based task persistence
    - Code snippet integration
    - Hybrid search for tasks
    - Backward compatibility with file-based storage
    """

    _instance: Optional["GraphEnabledScheduler"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._scheduler = TaskScheduler.get()
        self._graph_store: Optional[TaskGraphStore] = None
        self._code_store: Optional[CodeStore] = None
        self._initialized = False
        self._use_graph = True  # Feature flag

    @classmethod
    async def get_instance(cls) -> "GraphEnabledScheduler":
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance.initialize()
            return cls._instance

    async def initialize(self) -> None:
        """Initialize graph stores."""
        if self._initialized:
            return

        try:
            self._graph_store = await get_task_graph_store()
            self._code_store = await get_code_store()
            self._initialized = True
            PrintStyle.standard("Graph-enabled scheduler initialized")
        except Exception as e:
            PrintStyle.error(f"Failed to initialize graph stores: {e}")
            self._use_graph = False

    @property
    def scheduler(self) -> TaskScheduler:
        """Get the underlying TaskScheduler."""
        return self._scheduler

    @property
    def graph_store(self) -> Optional[TaskGraphStore]:
        """Get the task graph store."""
        return self._graph_store

    @property
    def code_store(self) -> Optional[CodeStore]:
        """Get the code store."""
        return self._code_store

    # =========================================================================
    # Task Operations with Graph Sync
    # =========================================================================

    async def add_task(
        self,
        task: Union[ScheduledTask, AdHocTask, PlannedTask],
        code_snippets: Optional[List[str]] = None,
    ) -> str:
        """
        Add a task and sync to graph store.

        Args:
            task: The task to add
            code_snippets: Optional list of code snippet IDs to link

        Returns:
            The task UUID
        """
        # Add to file-based scheduler
        await self._scheduler.add_task(task)

        # Sync to graph store
        if self._use_graph and self._graph_store:
            try:
                graph_task = base_task_to_graph_task(task)

                # Link code snippets if provided
                if code_snippets:
                    graph_task.code_refs = code_snippets

                await self._graph_store.save_task(graph_task)
            except Exception as e:
                PrintStyle.error(f"Failed to sync task to graph: {e}")

        return task.uuid

    async def remove_task(self, task_uuid: str) -> bool:
        """Remove a task from both stores."""
        await self._scheduler.remove_task_by_uuid(task_uuid)

        if self._use_graph and self._graph_store:
            try:
                await self._graph_store.delete_task(task_uuid)
            except Exception as e:
                PrintStyle.error(f"Failed to remove task from graph: {e}")

        return True

    async def update_task(
        self,
        task_uuid: str,
        code_snippets: Optional[List[str]] = None,
        **update_params
    ) -> Optional[Union[ScheduledTask, AdHocTask, PlannedTask]]:
        """Update a task in both stores."""
        updated_task = await self._scheduler.update_task(task_uuid, **update_params)

        if self._use_graph and self._graph_store and updated_task:
            try:
                graph_task = base_task_to_graph_task(updated_task)
                if code_snippets:
                    graph_task.code_refs = code_snippets
                await self._graph_store.update_task(graph_task)
            except Exception as e:
                PrintStyle.error(f"Failed to sync task update to graph: {e}")

        return updated_task

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
        """Save a code snippet to the graph."""
        if not self._code_store:
            PrintStyle.error("Code store not initialized")
            return None

        try:
            lang = CodeLanguage(language) if language in [e.value for e in CodeLanguage] else CodeLanguage.PYTHON

            snippet = CodeSnippet(
                id="",  # Will be generated
                name=name,
                language=lang,
                code=code,
                description=description,
                tags=tags or [],
            )

            return await self._code_store.save_code(snippet)

        except Exception as e:
            PrintStyle.error(f"Failed to save code snippet: {e}")
            return None

    async def search_code(
        self,
        query: str,
        language: Optional[str] = None,
        limit: int = 10,
    ) -> List[CodeSnippet]:
        """Search for code snippets."""
        if not self._code_store:
            return []

        try:
            lang = None
            if language:
                lang = CodeLanguage(language) if language in [e.value for e in CodeLanguage] else None

            return await self._code_store.search_code(query, language=lang, limit=limit)

        except Exception as e:
            PrintStyle.error(f"Code search failed: {e}")
            return []

    async def get_code_snippet(self, code_id: str) -> Optional[CodeSnippet]:
        """Get a code snippet by ID."""
        if not self._code_store:
            return None
        return await self._code_store.get_code(code_id)

    async def link_code_to_task(self, task_uuid: str, code_id: str) -> bool:
        """Link a code snippet to a task."""
        if not self._graph_store or not self._code_store:
            return False

        try:
            # Get task and add code ref
            task = await self._graph_store.get_task(task_uuid)
            if task and code_id not in task.code_refs:
                task.code_refs.append(code_id)
                await self._graph_store.update_task(task)
            return True
        except Exception as e:
            PrintStyle.error(f"Failed to link code to task: {e}")
            return False

    # =========================================================================
    # Task Search Operations
    # =========================================================================

    async def search_tasks(
        self,
        query: str,
        limit: int = 10,
    ) -> List[GraphTask]:
        """Search for tasks using semantic search."""
        if not self._graph_store:
            return []

        try:
            return await self._graph_store.search_tasks(query, limit=limit)
        except Exception as e:
            PrintStyle.error(f"Task search failed: {e}")
            return []

    async def get_tasks_with_code(self, task_uuid: str) -> Dict[str, Any]:
        """Get a task with its linked code snippets."""
        if not self._graph_store or not self._code_store:
            return {}

        try:
            task = await self._graph_store.get_task(task_uuid)
            if not task:
                return {}

            code_snippets = []
            for code_id in task.code_refs:
                snippet = await self._code_store.get_code(code_id)
                if snippet:
                    code_snippets.append(snippet.to_dict())

            return {
                "task": task.to_dict(),
                "code_snippets": code_snippets,
            }
        except Exception as e:
            PrintStyle.error(f"Failed to get task with code: {e}")
            return {}

    # =========================================================================
    # Execution Tracking
    # =========================================================================

    async def record_execution(
        self,
        task_uuid: str,
        code_id: str,
        output: str,
        success: bool = True,
        context_id: Optional[str] = None,
    ) -> Optional[str]:
        """Record a code execution for a task."""
        if not self._code_store:
            return None

        try:
            record = ExecutionRecord(
                id="",  # Will be generated
                code_id=code_id,
                task_id=task_uuid,
                context_id=context_id,
                status=ExecutionStatus.SUCCESS if success else ExecutionStatus.FAILURE,
                output=output,
            )
            record.complete(output=output)

            return await self._code_store.save_execution(record)

        except Exception as e:
            PrintStyle.error(f"Failed to record execution: {e}")
            return None

    # =========================================================================
    # Migration Helpers
    # =========================================================================

    async def migrate_to_graph(self) -> Dict[str, int]:
        """Migrate all file-based tasks to graph store."""
        if not self._graph_store:
            return {"error": -1, "migrated": 0}

        stats = {"migrated": 0, "failed": 0}

        for task in self._scheduler.get_tasks():
            try:
                graph_task = base_task_to_graph_task(task)
                await self._graph_store.save_task(graph_task)
                stats["migrated"] += 1
            except Exception as e:
                PrintStyle.error(f"Failed to migrate task {task.uuid}: {e}")
                stats["failed"] += 1

        return stats


# =============================================================================
# Module-level helpers
# =============================================================================

async def get_graph_scheduler() -> GraphEnabledScheduler:
    """Get the graph-enabled scheduler singleton."""
    return await GraphEnabledScheduler.get_instance()
