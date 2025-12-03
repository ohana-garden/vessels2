"""
A0 Framework - Browser Helper

Manages browser session state and browser-use agent integration.
Extracted from browser_agent.py tool to follow A0 helper patterns.

Usage:
    from python.helpers.browser_helper import BrowserHelper

    helper = await BrowserHelper.get(agent)
    task = helper.start_task("Navigate to example.com")
    result = await task.result()
"""

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any, TYPE_CHECKING
from pydantic import BaseModel

from python.helpers.agent_helper import AgentHelper
from python.helpers.browser_use import browser_use
from python.helpers import files, defer, persist_chat
from python.helpers.print_style import PrintStyle
from python.helpers.playwright import ensure_playwright_binary
from python.helpers.secrets import get_secrets_manager

if TYPE_CHECKING:
    from agent import Agent


@dataclass
class BrowserState:
    """State for browser helper."""
    browser_session: Optional[browser_use.BrowserSession] = None
    task: Optional[defer.DeferredTask] = None
    use_agent: Optional[browser_use.Agent] = None
    secrets_dict: Optional[dict[str, str]] = None
    iter_no: int = 0


class DoneResult(BaseModel):
    """Result model for browser task completion."""
    title: str
    response: str
    page_summary: str


class BrowserHelper(AgentHelper):
    """
    A0 Helper for browser automation via browser-use.

    Manages browser session lifecycle, task execution, and screenshot capture.
    """

    STATE_KEY = "_browser_helper_state"
    TASK_TIMEOUT = 300  # 5 minute timeout

    def __init__(self, agent: "Agent"):
        super().__init__(agent)
        self._state: BrowserState = BrowserState()

    @classmethod
    async def get(cls, agent: "Agent", reset: bool = False) -> "BrowserHelper":
        """Get or create browser helper for agent."""
        existing = agent.get_data(cls.STATE_KEY)
        if existing is not None and isinstance(existing, cls):
            if reset:
                await existing.kill_task()
            return existing

        instance = cls(agent)
        agent.set_data(cls.STATE_KEY, instance)
        return instance

    @property
    def state(self) -> BrowserState:
        """Get current browser state."""
        return self._state

    def get_user_data_dir(self) -> str:
        """Get browser profile directory for this agent context."""
        return str(
            Path.home()
            / ".config"
            / "browseruse"
            / "profiles"
            / f"agent_{self.agent.context.id}"
        )

    async def initialize_session(self) -> None:
        """Initialize browser session if not already active."""
        if self._state.browser_session:
            return

        pw_binary = ensure_playwright_binary()

        self._state.browser_session = browser_use.BrowserSession(
            browser_profile=browser_use.BrowserProfile(
                headless=True,
                disable_security=True,
                chromium_sandbox=False,
                accept_downloads=True,
                downloads_path=files.get_abs_path("tmp/downloads"),
                allowed_domains=["*", "http://*", "https://*"],
                executable_path=pw_binary,
                keep_alive=True,
                minimum_wait_page_load_time=1.0,
                wait_for_network_idle_page_load_time=2.0,
                maximum_wait_page_load_time=10.0,
                window_size={"width": 1024, "height": 2048},
                screen={"width": 1024, "height": 2048},
                viewport={"width": 1024, "height": 2048},
                no_viewport=False,
                args=["--headless=new"],
                user_data_dir=self.get_user_data_dir(),
                extra_http_headers=self.agent.config.browser_http_headers or {},
            )
        )

        if self._state.browser_session:
            await self._state.browser_session.start()

        # Patch viewport size
        await self._force_viewport_size()

        # Add init script
        await self._add_init_script()

    async def _force_viewport_size(self) -> None:
        """Force correct viewport size after browser startup."""
        if not self._state.browser_session:
            return
        try:
            page = await self._state.browser_session.get_current_page()
            if page:
                await page.set_viewport_size({"width": 1024, "height": 2048})
        except Exception as e:
            PrintStyle().warning(f"Could not force set viewport size: {e}")

    async def _add_init_script(self) -> None:
        """Add initialization script to browser context."""
        if not self._state.browser_session or not self._state.browser_session.browser_context:
            return
        js_override = files.get_abs_path("lib/browser/init_override.js")
        await self._state.browser_session.browser_context.add_init_script(path=js_override)

    def start_task(self, task_message: str) -> Optional[defer.DeferredTask]:
        """Start a new browser task."""
        if self._state.task and self._state.task.is_alive():
            self.kill_task_sync()

        self._state.task = defer.DeferredTask(
            thread_name="BrowserAgent" + self.agent.context.id
        )
        if self.agent.context.task:
            self.agent.context.task.add_child_task(self._state.task, terminate_thread=True)

        if self._state.task:
            self._state.task.start_task(self._run_task, task_message)

        return self._state.task

    def kill_task_sync(self) -> None:
        """Synchronously kill current task."""
        if self._state.task:
            self._state.task.kill(terminate_thread=True)
            self._state.task = None

        if self._state.browser_session:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._state.browser_session.close())
                loop.close()
            except Exception as e:
                PrintStyle().error(f"Error closing browser session: {e}")
            finally:
                self._state.browser_session = None

        self._state.use_agent = None
        self._state.iter_no = 0

    async def kill_task(self) -> None:
        """Kill current browser task and cleanup resources."""
        if self._state.task:
            self._state.task.kill(terminate_thread=True)
            self._state.task = None

        if self._state.browser_session:
            try:
                await self._state.browser_session.close()
            except Exception as e:
                PrintStyle().error(f"Error closing browser session: {e}")
            finally:
                self._state.browser_session = None

        self._state.use_agent = None
        self._state.iter_no = 0

    async def cleanup(self) -> None:
        """Cleanup browser resources."""
        await self.kill_task()
        files.delete_dir(self.get_user_data_dir())

    async def _run_task(self, task: str) -> Any:
        """Execute browser task."""
        await self.initialize_session()

        controller = browser_use.Controller(output_model=DoneResult)

        @controller.registry.action("Complete task", param_model=DoneResult)
        async def complete_task(params: DoneResult):
            return browser_use.ActionResult(
                is_done=True, success=True, extracted_content=params.model_dump_json()
            )

        model = self.agent.get_browser_model()

        try:
            secrets_manager = get_secrets_manager(self.agent.context)
            secrets_dict = secrets_manager.load_secrets()

            self._state.use_agent = browser_use.Agent(
                task=task,
                browser_session=self._state.browser_session,
                llm=model,
                use_vision=self.agent.config.browser_model.vision,
                extend_system_message=self.agent.read_prompt(
                    "prompts/browser_agent.system.md"
                ),
                controller=controller,
                enable_memory=False,
                llm_timeout=3000,
                sensitive_data=secrets_dict or {},
            )
        except Exception as e:
            raise Exception(
                f"Browser agent initialization failed. This might be due to model compatibility issues. Error: {e}"
            ) from e

        from python.extensions.message_loop_start._10_iteration_no import get_iter_no
        self._state.iter_no = get_iter_no(self.agent)

        async def hook(agent: browser_use.Agent):
            from agent import InterventionException
            await self.agent.wait_if_paused()
            if self._state.iter_no != get_iter_no(self.agent):
                raise InterventionException("Task cancelled")

        result = None
        if self._state.use_agent:
            result = await self._state.use_agent.run(
                max_steps=50, on_step_start=hook, on_step_end=hook
            )
        return result

    async def get_page(self) -> Any:
        """Get current browser page."""
        if self._state.use_agent and self._state.browser_session:
            try:
                if self._state.use_agent.browser_session:
                    return await self._state.use_agent.browser_session.get_current_page()
            except Exception:
                return None
        return None

    async def get_selector_map(self) -> dict:
        """Get selector map for current page state."""
        if self._state.use_agent and self._state.use_agent.browser_session:
            await self._state.use_agent.browser_session.get_state_summary(
                cache_clickable_elements_hashes=True
            )
            return await self._state.use_agent.browser_session.get_selector_map()
        return {}

    async def capture_screenshot(self, guid: str) -> Optional[str]:
        """Capture screenshot of current page."""
        page = await self.get_page()
        if not page:
            return None

        try:
            path = files.get_abs_path(
                persist_chat.get_chat_folder_path(self.agent.context.id),
                "browser",
                "screenshots",
                f"{guid}.png",
            )
            files.make_dirs(path)
            await page.screenshot(path=path, full_page=False, timeout=3000)
            return f"img://{path}&t={str(time.time())}"
        except Exception:
            return None

    def get_activity_log(self) -> list[str]:
        """Get short activity log from browser-use agent."""
        result = ["🚦 Starting task"]
        if not self._state.use_agent:
            return result

        action_results = self._state.use_agent.history.action_results() or []
        for item in action_results:
            if item.is_done:
                if item.success:
                    result.append("✅ Done")
                else:
                    result.append(
                        f"❌ Error: {item.error or item.extracted_content or 'Unknown error'}"
                    )
            else:
                text = item.extracted_content
                if text:
                    first_line = text.split("\n", 1)[0][:200]
                    result.append(first_line)

        return result

    def is_task_ready(self) -> bool:
        """Check if current task is ready/complete."""
        return self._state.task is None or self._state.task.is_ready()

    def is_task_alive(self) -> bool:
        """Check if current task is still running."""
        return self._state.task is not None and self._state.task.is_alive()
