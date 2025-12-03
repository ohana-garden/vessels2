"""
A0 Tool - Browser Agent

Thin wrapper around BrowserHelper for browser automation tasks.
Following A0 pattern: minimal Tool class, logic in helper.
"""

import asyncio
import time
from python.helpers.tool import Tool, Response
from python.helpers.browser_helper import BrowserHelper
from python.helpers.secrets import get_secrets_manager
from python.helpers.dirty_json import DirtyJson
from python.helpers import strings
from python.helpers.print_style import PrintStyle


class BrowserAgent(Tool):
    """Browser automation tool using browser-use library."""

    async def execute(self, message="", reset="", **kwargs) -> Response:
        self.guid = self.agent.context.generate_id()
        reset = str(reset).lower().strip() == "true"

        # Get helper (creates or resets as needed)
        self.helper = await BrowserHelper.get(self.agent, reset=reset)

        # Mask secrets in message
        message = get_secrets_manager(self.agent.context).mask_values(
            message, placeholder="<secret>{key}</secret>"
        )

        # Start browser task
        task = self.helper.start_task(message)
        if not task:
            return Response(message="Failed to start browser task", break_loop=False)

        # Wait for task completion with progress updates
        result = await self._wait_for_task(task)
        return result

    async def _wait_for_task(self, task) -> Response:
        """Wait for browser task and handle progress updates."""
        timeout_seconds = BrowserHelper.TASK_TIMEOUT
        start_time = time.time()
        fail_counter = 0

        while not task.is_ready():
            if time.time() - start_time > timeout_seconds:
                PrintStyle().warning(
                    self._mask(f"Browser agent task timeout after {timeout_seconds} seconds")
                )
                break

            await self.agent.handle_intervention()
            await asyncio.sleep(1)

            try:
                if task.is_ready():
                    break

                try:
                    update = await asyncio.wait_for(self._get_update(), timeout=10)
                    fail_counter = 0
                except asyncio.TimeoutError:
                    fail_counter += 1
                    PrintStyle().warning(
                        self._mask(f"browser_agent.get_update timed out ({fail_counter}/3)")
                    )
                    if fail_counter >= 3:
                        PrintStyle().warning(
                            self._mask("3 consecutive timeouts, breaking loop")
                        )
                        break
                    continue

                self._update_progress_from(update)

            except Exception as e:
                PrintStyle().error(self._mask(f"Error getting update: {str(e)}"))

        return await self._collect_result(task)

    async def _get_update(self) -> dict:
        """Get progress update from browser task."""
        result = {}

        if not self.helper.is_task_ready():
            async def _inner():
                result["log"] = self.helper.get_activity_log()
                screenshot = await self.helper.capture_screenshot(self.guid)
                if screenshot:
                    result["screenshot"] = screenshot

            if self.helper.state.task and not self.helper.state.task.is_ready():
                await self.helper.state.task.execute_inside(_inner)

        return result

    def _update_progress_from(self, update: dict) -> None:
        """Update progress display from update dict."""
        log = update.get("log", self.helper.get_activity_log())
        progress_text = "\n".join(log)
        self.update_progress(progress_text)

        screenshot = update.get("screenshot")
        if screenshot:
            self.log.update(screenshot=screenshot)

    async def _collect_result(self, task) -> Response:
        """Collect final result from browser task."""
        if not task.is_ready():
            PrintStyle().warning(self._mask("Task timed out, killing"))
            await self.helper.kill_task()
            return Response(
                message=self._mask("Browser agent task timed out, no output provided."),
                break_loop=False,
            )

        # Final progress update
        if self.helper.state.use_agent:
            log_final = self.helper.get_activity_log()
            self.update_progress("\n".join(log_final))

        # Get result
        try:
            result = await task.result()
        except Exception as e:
            PrintStyle().error(self._mask(f"Error getting result: {str(e)}"))
            answer_text = self._mask(f"Browser agent task failed: {str(e)}")
            self.log.update(answer=answer_text)
            return Response(message=answer_text, break_loop=False)

        # Parse result
        answer_text = self._parse_result(result)
        answer_text = self._mask(answer_text)
        self.log.update(answer=answer_text)

        # Add screenshot path if available
        if self.log.kvps and "screenshot" in self.log.kvps and self.log.kvps["screenshot"]:
            path = self.log.kvps["screenshot"].split("//", 1)[-1].split("&", 1)[0]
            answer_text += f"\n\nScreenshot: {path}"

        return Response(message=answer_text, break_loop=False)

    def _parse_result(self, result) -> str:
        """Parse browser task result into text."""
        if result and result.is_done():
            answer = result.final_result()
            try:
                if answer and isinstance(answer, str) and answer.strip():
                    answer_data = DirtyJson.parse_string(answer)
                    return strings.dict_to_text(answer_data)
                return str(answer) if answer else "Task completed successfully"
            except Exception as e:
                return str(answer) if answer else f"Task completed with parse error: {str(e)}"
        else:
            urls = result.urls() if result else []
            current_url = urls[-1] if urls else "unknown"
            return (
                f"Task reached step limit without completion. Last page: {current_url}. "
                f"The browser agent may need clearer instructions on when to finish."
            )

    def get_log_object(self):
        return self.agent.context.log.log(
            type="browser",
            heading=f"icon://captive_portal {self.agent.agent_name}: Calling Browser Agent",
            content="",
            kvps=self.args,
        )

    def update_progress(self, text: str) -> None:
        """Update progress display."""
        text = self._mask(text)
        short = text.split("\n")[-1]
        if len(short) > 50:
            short = short[:50] + "..."
        progress = f"Browser: {short}"

        self.log.update(progress=text)
        self.agent.context.log.set_progress(progress)

    def _mask(self, text: str) -> str:
        """Mask sensitive values in text."""
        try:
            return get_secrets_manager(self.agent.context).mask_values(text or "")
        except Exception:
            return text or ""
