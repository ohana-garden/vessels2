"""
A0 Tool - Code Execution

Thin wrapper around CodeExecutionHelper for executing code.
Following A0 pattern: minimal Tool class, logic in helper.
"""

from python.helpers.tool import Tool, Response
from python.helpers.code_execution_helper import (
    CodeExecutionHelper,
    CODE_EXEC_TIMEOUTS,
    OUTPUT_TIMEOUTS,
)
from python.helpers.print_style import PrintStyle


class CodeExecution(Tool):
    """Code execution tool for Python, Node.js, and terminal commands."""

    async def execute(self, **kwargs) -> Response:
        await self.agent.handle_intervention()

        runtime = self.args.get("runtime", "").lower().strip()
        session = int(self.args.get("session", 0))
        self.allow_running = bool(self.args.get("allow_running", False))

        # Get helper
        self.helper = await CodeExecutionHelper.get(self.agent)

        if runtime == "python":
            response = await self._execute_python(session)
        elif runtime == "nodejs":
            response = await self._execute_nodejs(session)
        elif runtime == "terminal":
            response = await self._execute_terminal(session)
        elif runtime == "output":
            response = await self._get_output(session, OUTPUT_TIMEOUTS)
        elif runtime == "reset":
            response = await self._reset(session)
        else:
            response = self.agent.read_prompt("fw.code.runtime_wrong.md", runtime=runtime)

        if not response:
            response = self.agent.read_prompt(
                "fw.code.info.md",
                info=self.agent.read_prompt("fw.code.no_output.md")
            )
        return Response(message=response, break_loop=False)

    async def _execute_python(self, session: int) -> str:
        """Execute Python code."""
        prefix, command = await self.helper.execute_python(
            code=self.args["code"], session=session
        )
        return await self._run_session(session, command, prefix)

    async def _execute_nodejs(self, session: int) -> str:
        """Execute Node.js code."""
        prefix, command = await self.helper.execute_nodejs(
            code=self.args["code"], session=session
        )
        return await self._run_session(session, command, prefix)

    async def _execute_terminal(self, session: int) -> str:
        """Execute terminal command."""
        prefix, command = await self.helper.execute_terminal(
            command=self.args["code"], session=session
        )
        return await self._run_session(session, command, prefix)

    async def _run_session(
        self,
        session: int,
        command: str,
        prefix: str,
        timeouts: dict | None = None
    ) -> str:
        """Run command in session and collect output."""
        await self.agent.handle_intervention()

        # Check for running session
        if not self.allow_running:
            running_response = await self._handle_running_session(session, prefix)
            if running_response:
                return running_response

        # Try with retry on connection loss
        for attempt in range(2):
            try:
                await self.helper.send_command(session, command)

                session_type = self.helper.get_session_type(session)
                PrintStyle(
                    background_color="white", font_color="#1B4F72", bold=True
                ).print(f"{self.agent.agent_name} code execution output ({session_type})")

                return await self._collect_output(session, prefix, timeouts or CODE_EXEC_TIMEOUTS)

            except Exception as e:
                if attempt == 0:
                    PrintStyle.error(str(e))
                    await self.helper.reset_session(session)
                    continue
                raise

        return ""

    async def _collect_output(
        self,
        session: int,
        prefix: str,
        timeouts: dict
    ) -> str:
        """Collect output with progress updates."""
        if prefix:
            self.log.update(content=prefix)

        def log_callback(content: str):
            heading = self._get_heading_from_output(content.replace(prefix, ""), 0)
            self.log.update(content=content, heading=heading)

        def progress_callback(content: str):
            self.set_progress(content)

        output, sys_info = await self.helper.collect_output(
            session=session,
            prefix=prefix,
            timeouts=timeouts,
            log_callback=log_callback,
            progress_callback=progress_callback
        )

        if sys_info:
            response = self.agent.read_prompt("fw.code.info.md", info=sys_info)
            if output:
                response = output + "\n\n" + response
            return response

        return output if output else ""

    async def _get_output(self, session: int, timeouts: dict) -> str:
        """Get output from running session."""
        return await self._collect_output(session, "", timeouts)

    async def _reset(self, session: int, reason: str | None = None) -> str:
        """Reset a terminal session."""
        if reason:
            PrintStyle(font_color="#FFA500", bold=True).print(
                f"Resetting terminal session {session}... Reason: {reason}"
            )
        else:
            PrintStyle(font_color="#FFA500", bold=True).print(
                f"Resetting terminal session {session}..."
            )

        await self.helper.reset_session(session)
        response = self.agent.read_prompt(
            "fw.code.info.md",
            info=self.agent.read_prompt("fw.code.reset.md")
        )
        self.log.update(content=response)
        return response

    async def _handle_running_session(self, session: int, prefix: str) -> str | None:
        """Handle case where session is already running."""
        output, has_dialog = await self.helper.check_running_session(session)
        if output is None:
            return None

        heading = self._get_heading_from_output(output, 0)
        self.set_progress(output)

        if has_dialog:
            sys_info = self.agent.read_prompt("fw.code.pause_dialog.md", timeout=1)
        else:
            sys_info = self.agent.read_prompt("fw.code.running.md", session=session)

        response = self.agent.read_prompt("fw.code.info.md", info=sys_info)
        if output:
            response = output + "\n\n" + response

        PrintStyle(font_color="#FFA500", bold=True).print(response)
        self.log.update(content=prefix + response, heading=heading)
        return response

    def get_log_object(self):
        return self.agent.context.log.log(
            type="code_exe",
            heading=self._get_heading(),
            content="",
            kvps=self.args,
        )

    def _get_heading(self, text: str = "") -> str:
        """Get heading for log display."""
        if not text:
            runtime = self.args.get('runtime', 'unknown')
            text = f"{self.name} - {runtime}"
        session = self.args.get("session", None)
        session_text = f"[{session}] " if session or session == 0 else ""
        return f"icon://terminal {session_text}{text}"

    def _get_heading_from_output(self, output: str, skip_lines: int = 0, done: bool = False) -> str:
        """Get heading from output last line."""
        done_icon = " icon://done_all" if done else ""

        if not output:
            return self._get_heading() + done_icon

        lines = output.splitlines()
        for i in range(len(lines) - skip_lines - 1, -1, -1):
            line = lines[i].strip()
            if line:
                return self._get_heading(line) + done_icon

        return self._get_heading() + done_icon

    async def after_execution(self, response, **kwargs):
        self.agent.hist_add_tool_result(self.name, response.message, **(response.additional or {}))
