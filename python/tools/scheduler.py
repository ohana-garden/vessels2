"""
Scheduler Tool - Graph-Native Task and Code Management (A0 Framework)

All tasks and code snippets are stored in FalkorDB + Graphiti.
No JSON file fallback.
"""

import asyncio
import json
from datetime import datetime
from python.helpers.tool import Tool, Response
from python.helpers.print_style import PrintStyle
from python.helpers.projects import get_context_project_name, load_basic_project_data

from python.helpers.task_scheduler_graph import (
    GraphScheduler,
    get_graph_scheduler,
)
from python.helpers.task_graph_store import (
    GraphTask,
    GraphTaskState,
    GraphTaskType,
)
from python.helpers.code_store import (
    CodeSnippet,
    CodeLanguage,
    get_code_store,
)

DEFAULT_WAIT_TIMEOUT = 300


class SchedulerTool(Tool):

    async def execute(self, **kwargs):
        # Task operations
        if self.method == "list_tasks":
            return await self.list_tasks(**kwargs)
        elif self.method == "find_task_by_name":
            return await self.find_task_by_name(**kwargs)
        elif self.method == "show_task":
            return await self.show_task(**kwargs)
        elif self.method == "run_task":
            return await self.run_task(**kwargs)
        elif self.method == "delete_task":
            return await self.delete_task(**kwargs)
        elif self.method == "create_task":
            return await self.create_task(**kwargs)
        elif self.method == "create_scheduled_task":
            return await self.create_scheduled_task(**kwargs)
        elif self.method == "create_adhoc_task":
            return await self.create_adhoc_task(**kwargs)
        elif self.method == "create_planned_task":
            return await self.create_planned_task(**kwargs)
        elif self.method == "wait_for_task":
            return await self.wait_for_task(**kwargs)
        elif self.method == "complete_task":
            return await self.complete_task(**kwargs)
        # Code snippet operations
        elif self.method == "save_code":
            return await self.save_code(**kwargs)
        elif self.method == "get_code":
            return await self.get_code(**kwargs)
        elif self.method == "search_code":
            return await self.search_code(**kwargs)
        elif self.method == "list_code":
            return await self.list_code(**kwargs)
        elif self.method == "link_code_to_task":
            return await self.link_code_to_task(**kwargs)
        elif self.method == "search_tasks":
            return await self.search_tasks(**kwargs)
        elif self.method == "get_task_with_code":
            return await self.get_task_with_code(**kwargs)
        else:
            return Response(message=f"Unknown method '{self.name}:{self.method}'", break_loop=False)

    def _resolve_project_metadata(self) -> tuple[str | None, str | None]:
        context = self.agent.context
        if not context:
            return (None, None)
        project_slug = get_context_project_name(context)
        if not project_slug:
            return (None, None)
        try:
            metadata = load_basic_project_data(project_slug)
            color = metadata.get("color") or None
        except Exception:
            color = None
        return project_slug, color

    # =========================================================================
    # Task Operations
    # =========================================================================

    async def list_tasks(self, **kwargs) -> Response:
        """List all tasks with optional filtering."""
        state_filter: str | None = kwargs.get("state", None)
        type_filter: str | None = kwargs.get("type", None)
        limit: int = kwargs.get("limit", 50)

        try:
            scheduler = await get_graph_scheduler()

            task_type = None
            if type_filter:
                try:
                    task_type = GraphTaskType(type_filter)
                except ValueError:
                    pass

            state = None
            if state_filter:
                try:
                    state = GraphTaskState(state_filter)
                except ValueError:
                    pass

            tasks = await scheduler.list_tasks(task_type=task_type, state=state, limit=limit)
            results = [t.to_dict() for t in tasks]
            return Response(message=json.dumps(results, indent=4), break_loop=False)

        except Exception as e:
            return Response(message=f"Error listing tasks: {e}", break_loop=False)

    async def find_task_by_name(self, **kwargs) -> Response:
        """Find tasks by name using semantic search."""
        name: str = kwargs.get("name", "")
        if not name:
            return Response(message="Task name is required", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            tasks = await scheduler.search_tasks(query=name, limit=10)

            if not tasks:
                return Response(message=f"No tasks found matching: {name}", break_loop=False)

            results = [t.to_dict() for t in tasks]
            return Response(message=json.dumps(results, indent=4), break_loop=False)

        except Exception as e:
            return Response(message=f"Error finding task: {e}", break_loop=False)

    async def show_task(self, **kwargs) -> Response:
        """Show task details by ID."""
        task_id: str = kwargs.get("uuid", "") or kwargs.get("task_id", "")
        if not task_id:
            return Response(message="Task ID is required", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            task = await scheduler.get_task(task_id)

            if not task:
                return Response(message=f"Task not found: {task_id}", break_loop=False)

            return Response(message=json.dumps(task.to_dict(), indent=4), break_loop=False)

        except Exception as e:
            return Response(message=f"Error showing task: {e}", break_loop=False)

    async def run_task(self, **kwargs) -> Response:
        """Run a task."""
        task_id: str = kwargs.get("uuid", "") or kwargs.get("task_id", "")
        if not task_id:
            return Response(message="Task ID is required", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            task = await scheduler.run_task(task_id)

            if task:
                return Response(message=f"Task started: {task_id}", break_loop=False)
            else:
                return Response(message=f"Failed to start task: {task_id}", break_loop=False)

        except ValueError as e:
            return Response(message=str(e), break_loop=False)
        except Exception as e:
            return Response(message=f"Error running task: {e}", break_loop=False)

    async def delete_task(self, **kwargs) -> Response:
        """Delete a task."""
        task_id: str = kwargs.get("uuid", "") or kwargs.get("task_id", "")
        if not task_id:
            return Response(message="Task ID is required", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            success = await scheduler.delete_task(task_id)

            if success:
                return Response(message=f"Task deleted: {task_id}", break_loop=False)
            else:
                return Response(message=f"Failed to delete task: {task_id}", break_loop=False)

        except Exception as e:
            return Response(message=f"Error deleting task: {e}", break_loop=False)

    async def create_task(self, **kwargs) -> Response:
        """Create a new task (generic)."""
        name: str = kwargs.get("name", "")
        prompt: str = kwargs.get("prompt", "")
        description: str = kwargs.get("description", "")
        system_prompt: str = kwargs.get("system_prompt", "")
        task_type: str = kwargs.get("task_type", "immediate")
        attachments: list[str] = kwargs.get("attachments", [])
        code_refs: list[str] = kwargs.get("code_refs", [])
        depends_on: list[str] = kwargs.get("depends_on", [])
        tags: list[str] = kwargs.get("tags", [])

        if not name or not prompt:
            return Response(message="Task requires 'name' and 'prompt'", break_loop=False)

        try:
            tt = GraphTaskType(task_type) if task_type in [e.value for e in GraphTaskType] else GraphTaskType.IMMEDIATE
        except ValueError:
            tt = GraphTaskType.IMMEDIATE

        project_slug, project_color = self._resolve_project_metadata()

        try:
            scheduler = await get_graph_scheduler()
            task_id = await scheduler.create_task(
                name=name,
                prompt=prompt,
                description=description,
                system_prompt=system_prompt,
                task_type=tt,
                attachments=attachments,
                code_refs=code_refs,
                depends_on=depends_on,
                context_id=self.agent.context.id if self.agent.context else None,
                project_name=project_slug,
                project_color=project_color,
                tags=tags,
            )

            return Response(message=f"Task '{name}' created: {task_id}", break_loop=False)

        except Exception as e:
            return Response(message=f"Error creating task: {e}", break_loop=False)

    async def create_scheduled_task(self, **kwargs) -> Response:
        """Create a scheduled (cron-based) task."""
        name: str = kwargs.get("name", "")
        prompt: str = kwargs.get("prompt", "")
        system_prompt: str = kwargs.get("system_prompt", "")
        attachments: list[str] = kwargs.get("attachments", [])
        schedule: dict[str, str] = kwargs.get("schedule", {})

        if not name or not prompt:
            return Response(message="Task requires 'name' and 'prompt'", break_loop=False)

        if not schedule:
            return Response(message="Scheduled task requires 'schedule'", break_loop=False)

        project_slug, project_color = self._resolve_project_metadata()

        try:
            scheduler = await get_graph_scheduler()
            task_id = await scheduler.create_task(
                name=name,
                prompt=prompt,
                system_prompt=system_prompt,
                task_type=GraphTaskType.SCHEDULED,
                attachments=attachments,
                schedule=schedule,
                context_id=self.agent.context.id if self.agent.context else None,
                project_name=project_slug,
                project_color=project_color,
            )

            return Response(message=f"Scheduled task '{name}' created: {task_id}", break_loop=False)

        except Exception as e:
            return Response(message=f"Error creating scheduled task: {e}", break_loop=False)

    async def create_adhoc_task(self, **kwargs) -> Response:
        """Create an immediate (ad-hoc) task."""
        name: str = kwargs.get("name", "")
        prompt: str = kwargs.get("prompt", "")
        system_prompt: str = kwargs.get("system_prompt", "")
        attachments: list[str] = kwargs.get("attachments", [])

        if not name or not prompt:
            return Response(message="Task requires 'name' and 'prompt'", break_loop=False)

        project_slug, project_color = self._resolve_project_metadata()

        try:
            scheduler = await get_graph_scheduler()
            task_id = await scheduler.create_task(
                name=name,
                prompt=prompt,
                system_prompt=system_prompt,
                task_type=GraphTaskType.IMMEDIATE,
                attachments=attachments,
                context_id=self.agent.context.id if self.agent.context else None,
                project_name=project_slug,
                project_color=project_color,
            )

            return Response(message=f"Task '{name}' created: {task_id}", break_loop=False)

        except Exception as e:
            return Response(message=f"Error creating task: {e}", break_loop=False)

    async def create_planned_task(self, **kwargs) -> Response:
        """Create a planned task with specific execution times."""
        name: str = kwargs.get("name", "")
        prompt: str = kwargs.get("prompt", "")
        system_prompt: str = kwargs.get("system_prompt", "")
        attachments: list[str] = kwargs.get("attachments", [])
        plan: list[str] = kwargs.get("plan", [])

        if not name or not prompt:
            return Response(message="Task requires 'name' and 'prompt'", break_loop=False)

        if not plan:
            return Response(message="Planned task requires 'plan' (list of ISO datetime strings)", break_loop=False)

        project_slug, project_color = self._resolve_project_metadata()

        try:
            scheduler = await get_graph_scheduler()
            task_id = await scheduler.create_task(
                name=name,
                prompt=prompt,
                system_prompt=system_prompt,
                task_type=GraphTaskType.PLANNED,
                attachments=attachments,
                planned_times=plan,
                context_id=self.agent.context.id if self.agent.context else None,
                project_name=project_slug,
                project_color=project_color,
            )

            return Response(message=f"Planned task '{name}' created: {task_id}", break_loop=False)

        except Exception as e:
            return Response(message=f"Error creating planned task: {e}", break_loop=False)

    async def wait_for_task(self, **kwargs) -> Response:
        """Wait for a task to complete."""
        task_id: str = kwargs.get("uuid", "") or kwargs.get("task_id", "")
        if not task_id:
            return Response(message="Task ID is required", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            task = await scheduler.get_task(task_id)

            if not task:
                return Response(message=f"Task not found: {task_id}", break_loop=False)

            elapsed = 0
            while task and task.state == GraphTaskState.RUNNING:
                await asyncio.sleep(1)
                elapsed += 1
                if elapsed > DEFAULT_WAIT_TIMEOUT:
                    return Response(message=f"Task wait timeout ({DEFAULT_WAIT_TIMEOUT}s): {task_id}", break_loop=False)
                task = await scheduler.get_task(task_id)

            if not task:
                return Response(message=f"Task not found: {task_id}", break_loop=False)

            return Response(
                message=f"*Task*: {task_id}\n*State*: {task.state.value}\n*Last run*: {task.last_run}\n*Result*:\n{task.last_result}",
                break_loop=False
            )

        except Exception as e:
            return Response(message=f"Error waiting for task: {e}", break_loop=False)

    async def complete_task(self, **kwargs) -> Response:
        """Mark a task as completed."""
        task_id: str = kwargs.get("uuid", "") or kwargs.get("task_id", "")
        result: str = kwargs.get("result", "")
        success: bool = kwargs.get("success", True)

        if not task_id:
            return Response(message="Task ID is required", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            done = await scheduler.complete_task(task_id, result, success)

            if done:
                return Response(message=f"Task completed: {task_id}", break_loop=False)
            else:
                return Response(message=f"Failed to complete task: {task_id}", break_loop=False)

        except Exception as e:
            return Response(message=f"Error completing task: {e}", break_loop=False)

    # =========================================================================
    # Code Snippet Operations
    # =========================================================================

    async def save_code(self, **kwargs) -> Response:
        """Save a reusable code snippet."""
        name: str = kwargs.get("name", "")
        language: str = kwargs.get("language", "python")
        code: str = kwargs.get("code", "")
        description: str = kwargs.get("description", "")
        tags: list[str] = kwargs.get("tags", [])

        if not name or not code:
            return Response(message="Code snippet requires 'name' and 'code'", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            code_id = await scheduler.save_code_snippet(
                name=name,
                language=language,
                code=code,
                description=description,
                tags=tags,
            )

            if code_id:
                return Response(message=f"Code snippet '{name}' saved: {code_id}", break_loop=False)
            else:
                return Response(message="Failed to save code snippet", break_loop=False)

        except Exception as e:
            return Response(message=f"Error saving code snippet: {e}", break_loop=False)

    async def get_code(self, **kwargs) -> Response:
        """Get a code snippet by ID."""
        code_id: str = kwargs.get("code_id", "")
        if not code_id:
            return Response(message="Code ID is required", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            snippet = await scheduler.get_code_snippet(code_id)

            if snippet:
                return Response(message=json.dumps(snippet.to_dict(), indent=4), break_loop=False)
            else:
                return Response(message=f"Code snippet not found: {code_id}", break_loop=False)

        except Exception as e:
            return Response(message=f"Error getting code snippet: {e}", break_loop=False)

    async def search_code(self, **kwargs) -> Response:
        """Search for code snippets."""
        query: str = kwargs.get("query", "")
        language: str | None = kwargs.get("language", None)
        limit: int = kwargs.get("limit", 10)

        if not query:
            return Response(message="Search query is required", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            snippets = await scheduler.search_code(
                query=query,
                language=language,
                limit=limit,
            )

            results = [s.to_dict() for s in snippets]
            return Response(message=json.dumps(results, indent=4), break_loop=False)

        except Exception as e:
            return Response(message=f"Error searching code: {e}", break_loop=False)

    async def list_code(self, **kwargs) -> Response:
        """List code snippets."""
        language: str | None = kwargs.get("language", None)
        limit: int = kwargs.get("limit", 50)

        try:
            scheduler = await get_graph_scheduler()
            snippets = await scheduler.list_code(language=language, limit=limit)

            results = [s.to_dict() for s in snippets]
            return Response(message=json.dumps(results, indent=4), break_loop=False)

        except Exception as e:
            return Response(message=f"Error listing code: {e}", break_loop=False)

    async def link_code_to_task(self, **kwargs) -> Response:
        """Link a code snippet to a task."""
        task_id: str = kwargs.get("task_uuid", "") or kwargs.get("task_id", "")
        code_id: str = kwargs.get("code_id", "")

        if not task_id or not code_id:
            return Response(message="Both task_id and code_id are required", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            success = await scheduler.link_code_to_task(task_id, code_id)

            if success:
                return Response(message=f"Code {code_id} linked to task {task_id}", break_loop=False)
            else:
                return Response(message="Failed to link code to task", break_loop=False)

        except Exception as e:
            return Response(message=f"Error linking code to task: {e}", break_loop=False)

    async def search_tasks(self, **kwargs) -> Response:
        """Search for tasks using semantic search."""
        query: str = kwargs.get("query", "")
        limit: int = kwargs.get("limit", 10)

        if not query:
            return Response(message="Search query is required", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            tasks = await scheduler.search_tasks(query=query, limit=limit)

            results = [t.to_dict() for t in tasks]
            return Response(message=json.dumps(results, indent=4), break_loop=False)

        except Exception as e:
            return Response(message=f"Error searching tasks: {e}", break_loop=False)

    async def get_task_with_code(self, **kwargs) -> Response:
        """Get a task with all its linked code snippets."""
        task_id: str = kwargs.get("task_uuid", "") or kwargs.get("task_id", "")
        if not task_id:
            return Response(message="Task ID is required", break_loop=False)

        try:
            scheduler = await get_graph_scheduler()
            result = await scheduler.get_task_with_code(task_id)

            if result:
                return Response(message=json.dumps(result, indent=4), break_loop=False)
            else:
                return Response(message=f"Task not found: {task_id}", break_loop=False)

        except Exception as e:
            return Response(message=f"Error getting task with code: {e}", break_loop=False)
