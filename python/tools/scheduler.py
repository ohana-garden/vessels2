import asyncio
from datetime import datetime
import json
import random
import re
from python.helpers.tool import Tool, Response
from python.helpers.task_scheduler import (
    TaskScheduler, ScheduledTask, AdHocTask, PlannedTask,
    serialize_task, TaskState, TaskSchedule, TaskPlan, parse_datetime, serialize_datetime
)
from agent import AgentContext
from python.helpers import persist_chat
from python.helpers.projects import get_context_project_name, load_basic_project_data
from python.helpers.print_style import PrintStyle

# Graph-based code storage (A0 framework)
try:
    from python.helpers.code_store import (
        CodeStore,
        CodeSnippet,
        CodeLanguage,
        get_code_store,
    )
    from python.helpers.task_scheduler_graph import (
        GraphEnabledScheduler,
        get_graph_scheduler,
    )
    GRAPH_SCHEDULER_AVAILABLE = True
except ImportError:
    GRAPH_SCHEDULER_AVAILABLE = False

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
        elif self.method == "create_scheduled_task":
            return await self.create_scheduled_task(**kwargs)
        elif self.method == "create_adhoc_task":
            return await self.create_adhoc_task(**kwargs)
        elif self.method == "create_planned_task":
            return await self.create_planned_task(**kwargs)
        elif self.method == "wait_for_task":
            return await self.wait_for_task(**kwargs)
        # Code snippet operations (A0 framework)
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
            return await self.search_tasks_semantic(**kwargs)
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

    async def list_tasks(self, **kwargs) -> Response:
        state_filter: list[str] | None = kwargs.get("state", None)
        type_filter: list[str] | None = kwargs.get("type", None)
        next_run_within_filter: int | None = kwargs.get("next_run_within", None)
        next_run_after_filter: int | None = kwargs.get("next_run_after", None)

        tasks: list[ScheduledTask | AdHocTask | PlannedTask] = TaskScheduler.get().get_tasks()
        filtered_tasks = []
        for task in tasks:
            if state_filter and task.state not in state_filter:
                continue
            if type_filter and task.type not in type_filter:
                continue
            if next_run_within_filter and task.get_next_run_minutes() is not None and task.get_next_run_minutes() > next_run_within_filter:  # type: ignore
                continue
            if next_run_after_filter and task.get_next_run_minutes() is not None and task.get_next_run_minutes() < next_run_after_filter:  # type: ignore
                continue
            filtered_tasks.append(serialize_task(task))

        return Response(message=json.dumps(filtered_tasks, indent=4), break_loop=False)

    async def find_task_by_name(self, **kwargs) -> Response:
        name: str = kwargs.get("name", "")
        if not name:
            return Response(message="Task name is required", break_loop=False)
        tasks: list[ScheduledTask | AdHocTask | PlannedTask] = TaskScheduler.get().find_task_by_name(name)
        if not tasks:
            return Response(message=f"Task not found: {name}", break_loop=False)
        return Response(message=json.dumps([serialize_task(task) for task in tasks], indent=4), break_loop=False)

    async def show_task(self, **kwargs) -> Response:
        task_uuid: str = kwargs.get("uuid", "")
        if not task_uuid:
            return Response(message="Task UUID is required", break_loop=False)
        task: ScheduledTask | AdHocTask | PlannedTask | None = TaskScheduler.get().get_task_by_uuid(task_uuid)
        if not task:
            return Response(message=f"Task not found: {task_uuid}", break_loop=False)
        return Response(message=json.dumps(serialize_task(task), indent=4), break_loop=False)

    async def run_task(self, **kwargs) -> Response:
        task_uuid: str = kwargs.get("uuid", "")
        if not task_uuid:
            return Response(message="Task UUID is required", break_loop=False)
        task_context: str | None = kwargs.get("context", None)
        task: ScheduledTask | AdHocTask | PlannedTask | None = TaskScheduler.get().get_task_by_uuid(task_uuid)
        if not task:
            return Response(message=f"Task not found: {task_uuid}", break_loop=False)
        await TaskScheduler.get().run_task_by_uuid(task_uuid, task_context)
        if task.context_id == self.agent.context.id:
            break_loop = True  # break loop if task is running in the same context, otherwise it would start two conversations in one window
        else:
            break_loop = False
        return Response(message=f"Task started: {task_uuid}", break_loop=break_loop)

    async def delete_task(self, **kwargs) -> Response:
        task_uuid: str = kwargs.get("uuid", "")
        if not task_uuid:
            return Response(message="Task UUID is required", break_loop=False)

        task: ScheduledTask | AdHocTask | PlannedTask | None = TaskScheduler.get().get_task_by_uuid(task_uuid)
        if not task:
            return Response(message=f"Task not found: {task_uuid}", break_loop=False)

        context = None
        if task.context_id:
            context = AgentContext.get(task.context_id)

        if task.state == TaskState.RUNNING:
            if context:
                context.reset()
            await TaskScheduler.get().update_task(task_uuid, state=TaskState.IDLE)
            await TaskScheduler.get().save()

        if context and context.id == task.uuid:
            AgentContext.remove(context.id)
            persist_chat.remove_chat(context.id)

        await TaskScheduler.get().remove_task_by_uuid(task_uuid)
        if TaskScheduler.get().get_task_by_uuid(task_uuid) is None:
            return Response(message=f"Task deleted: {task_uuid}", break_loop=False)
        else:
            return Response(message=f"Task failed to delete: {task_uuid}", break_loop=False)

    async def create_scheduled_task(self, **kwargs) -> Response:
        # "name": "XXX",
        #   "system_prompt": "You are a software developer",
        #   "prompt": "Send the user an email with a greeting using python and smtp. The user's address is: xxx@yyy.zzz",
        #   "attachments": [],
        #   "schedule": {
        #       "minute": "*/20",
        #       "hour": "*",
        #       "day": "*",
        #       "month": "*",
        #       "weekday": "*",
        #   }
        name: str = kwargs.get("name", "")
        system_prompt: str = kwargs.get("system_prompt", "")
        prompt: str = kwargs.get("prompt", "")
        attachments: list[str] = kwargs.get("attachments", [])
        schedule: dict[str, str] = kwargs.get("schedule", {})
        dedicated_context: bool = kwargs.get("dedicated_context", False)

        task_schedule = TaskSchedule(
            minute=schedule.get("minute", "*"),
            hour=schedule.get("hour", "*"),
            day=schedule.get("day", "*"),
            month=schedule.get("month", "*"),
            weekday=schedule.get("weekday", "*"),
        )

        # Validate cron expression, agent might hallucinate
        cron_regex = "^((((\d+,)+\d+|(\d+(\/|-|#)\d+)|\d+L?|\*(\/\d+)?|L(-\d+)?|\?|[A-Z]{3}(-[A-Z]{3})?) ?){5,7})$"
        if not re.match(cron_regex, task_schedule.to_crontab()):
            return Response(message="Invalid cron expression: " + task_schedule.to_crontab(), break_loop=False)

        project_slug, project_color = self._resolve_project_metadata()

        task = ScheduledTask.create(
            name=name,
            system_prompt=system_prompt,
            prompt=prompt,
            attachments=attachments,
            schedule=task_schedule,
            context_id=None if dedicated_context else self.agent.context.id,
            project_name=project_slug,
            project_color=project_color,
        )
        await TaskScheduler.get().add_task(task)
        return Response(message=f"Scheduled task '{name}' created: {task.uuid}", break_loop=False)

    async def create_adhoc_task(self, **kwargs) -> Response:
        name: str = kwargs.get("name", "")
        system_prompt: str = kwargs.get("system_prompt", "")
        prompt: str = kwargs.get("prompt", "")
        attachments: list[str] = kwargs.get("attachments", [])
        token: str = str(random.randint(1000000000000000000, 9999999999999999999))
        dedicated_context: bool = kwargs.get("dedicated_context", False)

        project_slug, project_color = self._resolve_project_metadata()

        task = AdHocTask.create(
            name=name,
            system_prompt=system_prompt,
            prompt=prompt,
            attachments=attachments,
            token=token,
            context_id=None if dedicated_context else self.agent.context.id,
            project_name=project_slug,
            project_color=project_color,
        )
        await TaskScheduler.get().add_task(task)
        return Response(message=f"Adhoc task '{name}' created: {task.uuid}", break_loop=False)

    async def create_planned_task(self, **kwargs) -> Response:
        name: str = kwargs.get("name", "")
        system_prompt: str = kwargs.get("system_prompt", "")
        prompt: str = kwargs.get("prompt", "")
        attachments: list[str] = kwargs.get("attachments", [])
        plan: list[str] = kwargs.get("plan", [])
        dedicated_context: bool = kwargs.get("dedicated_context", False)

        # Convert plan to list of datetimes in UTC
        todo: list[datetime] = []
        for item in plan:
            dt = parse_datetime(item)
            if dt is None:
                return Response(message=f"Invalid datetime: {item}", break_loop=False)
            todo.append(dt)

        # Create task plan with todo list
        task_plan = TaskPlan.create(
            todo=todo,
            in_progress=None,
            done=[]
        )

        project_slug, project_color = self._resolve_project_metadata()

        # Create planned task with task plan
        task = PlannedTask.create(
            name=name,
            system_prompt=system_prompt,
            prompt=prompt,
            attachments=attachments,
            plan=task_plan,
            context_id=None if dedicated_context else self.agent.context.id,
            project_name=project_slug,
            project_color=project_color
        )
        await TaskScheduler.get().add_task(task)
        return Response(message=f"Planned task '{name}' created: {task.uuid}", break_loop=False)

    async def wait_for_task(self, **kwargs) -> Response:
        task_uuid: str = kwargs.get("uuid", "")
        if not task_uuid:
            return Response(message="Task UUID is required", break_loop=False)

        scheduler = TaskScheduler.get()
        task: ScheduledTask | AdHocTask | PlannedTask | None = scheduler.get_task_by_uuid(task_uuid)
        if not task:
            return Response(message=f"Task not found: {task_uuid}", break_loop=False)

        if task.context_id == self.agent.context.id:
            return Response(message="You can only wait for tasks running in their own dedicated context.", break_loop=False)

        done = False
        elapsed = 0
        while not done:
            await scheduler.reload()
            task = scheduler.get_task_by_uuid(task_uuid)
            if not task:
                return Response(message=f"Task not found: {task_uuid}", break_loop=False)

            if task.state == TaskState.RUNNING:
                await asyncio.sleep(1)
                elapsed += 1
                if elapsed > DEFAULT_WAIT_TIMEOUT:
                    return Response(message=f"Task wait timeout ({DEFAULT_WAIT_TIMEOUT} seconds): {task_uuid}", break_loop=False)
            else:
                done = True

        return Response(
            message=f"*Task*: {task_uuid}\n*State*: {task.state}\n*Last run*: {serialize_datetime(task.last_run)}\n*Result*:\n{task.last_result}",
            break_loop=False
        )

    # =========================================================================
    # Code Snippet Operations (A0 Framework)
    # =========================================================================

    async def save_code(self, **kwargs) -> Response:
        """Save a reusable code snippet to the graph store."""
        if not GRAPH_SCHEDULER_AVAILABLE:
            return Response(message="Graph scheduler not available. Code snippets require graph store.", break_loop=False)

        name: str = kwargs.get("name", "")
        language: str = kwargs.get("language", "python")
        code: str = kwargs.get("code", "")
        description: str = kwargs.get("description", "")
        tags: list[str] = kwargs.get("tags", [])

        if not name or not code:
            return Response(message="Code snippet requires 'name' and 'code' parameters", break_loop=False)

        try:
            graph_scheduler = await get_graph_scheduler()
            code_id = await graph_scheduler.save_code_snippet(
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
        if not GRAPH_SCHEDULER_AVAILABLE:
            return Response(message="Graph scheduler not available", break_loop=False)

        code_id: str = kwargs.get("code_id", "")
        if not code_id:
            return Response(message="Code ID is required", break_loop=False)

        try:
            graph_scheduler = await get_graph_scheduler()
            snippet = await graph_scheduler.get_code_snippet(code_id)

            if snippet:
                return Response(message=json.dumps(snippet.to_dict(), indent=4), break_loop=False)
            else:
                return Response(message=f"Code snippet not found: {code_id}", break_loop=False)

        except Exception as e:
            return Response(message=f"Error getting code snippet: {e}", break_loop=False)

    async def search_code(self, **kwargs) -> Response:
        """Search for code snippets using semantic search."""
        if not GRAPH_SCHEDULER_AVAILABLE:
            return Response(message="Graph scheduler not available", break_loop=False)

        query: str = kwargs.get("query", "")
        language: str | None = kwargs.get("language", None)
        limit: int = kwargs.get("limit", 10)

        if not query:
            return Response(message="Search query is required", break_loop=False)

        try:
            graph_scheduler = await get_graph_scheduler()
            snippets = await graph_scheduler.search_code(
                query=query,
                language=language,
                limit=limit,
            )

            results = [s.to_dict() for s in snippets]
            return Response(message=json.dumps(results, indent=4), break_loop=False)

        except Exception as e:
            return Response(message=f"Error searching code: {e}", break_loop=False)

    async def list_code(self, **kwargs) -> Response:
        """List all code snippets."""
        if not GRAPH_SCHEDULER_AVAILABLE:
            return Response(message="Graph scheduler not available", break_loop=False)

        language: str | None = kwargs.get("language", None)
        limit: int = kwargs.get("limit", 50)

        try:
            code_store = await get_code_store()

            lang = None
            if language:
                try:
                    lang = CodeLanguage(language)
                except ValueError:
                    pass

            snippets = await code_store.list_code(language=lang, limit=limit)
            results = [s.to_dict() for s in snippets]
            return Response(message=json.dumps(results, indent=4), break_loop=False)

        except Exception as e:
            return Response(message=f"Error listing code: {e}", break_loop=False)

    async def link_code_to_task(self, **kwargs) -> Response:
        """Link a code snippet to a task for execution."""
        if not GRAPH_SCHEDULER_AVAILABLE:
            return Response(message="Graph scheduler not available", break_loop=False)

        task_uuid: str = kwargs.get("task_uuid", "")
        code_id: str = kwargs.get("code_id", "")

        if not task_uuid or not code_id:
            return Response(message="Both task_uuid and code_id are required", break_loop=False)

        try:
            graph_scheduler = await get_graph_scheduler()
            success = await graph_scheduler.link_code_to_task(task_uuid, code_id)

            if success:
                return Response(message=f"Code {code_id} linked to task {task_uuid}", break_loop=False)
            else:
                return Response(message="Failed to link code to task", break_loop=False)

        except Exception as e:
            return Response(message=f"Error linking code to task: {e}", break_loop=False)

    async def search_tasks_semantic(self, **kwargs) -> Response:
        """Search for tasks using semantic search (graph-based)."""
        if not GRAPH_SCHEDULER_AVAILABLE:
            return Response(message="Graph scheduler not available. Use list_tasks for basic filtering.", break_loop=False)

        query: str = kwargs.get("query", "")
        limit: int = kwargs.get("limit", 10)

        if not query:
            return Response(message="Search query is required", break_loop=False)

        try:
            graph_scheduler = await get_graph_scheduler()
            tasks = await graph_scheduler.search_tasks(query=query, limit=limit)

            results = [t.to_dict() for t in tasks]
            return Response(message=json.dumps(results, indent=4), break_loop=False)

        except Exception as e:
            return Response(message=f"Error searching tasks: {e}", break_loop=False)

    async def get_task_with_code(self, **kwargs) -> Response:
        """Get a task with all its linked code snippets."""
        if not GRAPH_SCHEDULER_AVAILABLE:
            return Response(message="Graph scheduler not available", break_loop=False)

        task_uuid: str = kwargs.get("task_uuid", "")
        if not task_uuid:
            return Response(message="Task UUID is required", break_loop=False)

        try:
            graph_scheduler = await get_graph_scheduler()
            result = await graph_scheduler.get_tasks_with_code(task_uuid)

            if result:
                return Response(message=json.dumps(result, indent=4), break_loop=False)
            else:
                return Response(message=f"Task not found: {task_uuid}", break_loop=False)

        except Exception as e:
            return Response(message=f"Error getting task with code: {e}", break_loop=False)
