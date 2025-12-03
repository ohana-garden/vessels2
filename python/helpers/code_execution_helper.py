"""
A0 Framework - Code Execution Helper

Manages shell sessions and code execution state.
Extracted from code_execution_tool.py to follow A0 helper patterns.

Usage:
    from python.helpers.code_execution_helper import CodeExecutionHelper

    helper = await CodeExecutionHelper.get(agent)
    output = await helper.execute_terminal("ls -la", session=0)
"""

import asyncio
import re
import shlex
import time
from dataclasses import dataclass, field
from typing import Optional, Any, TYPE_CHECKING

from python.helpers.agent_helper import AgentHelper
from python.helpers.shell_local import LocalInteractiveSession
from python.helpers.shell_ssh import SSHInteractiveSession
from python.helpers.print_style import PrintStyle
from python.helpers import files, rfc_exchange, projects, runtime
from python.helpers.messages import truncate_text as truncate_text_agent
from python.helpers.strings import truncate_text as truncate_text_string

if TYPE_CHECKING:
    from agent import Agent


# Default timeouts for different execution types
CODE_EXEC_TIMEOUTS: dict[str, int] = {
    "first_output_timeout": 30,
    "between_output_timeout": 15,
    "max_exec_timeout": 180,
    "dialog_timeout": 5,
}

OUTPUT_TIMEOUTS: dict[str, int] = {
    "first_output_timeout": 90,
    "between_output_timeout": 45,
    "max_exec_timeout": 300,
    "dialog_timeout": 5,
}


@dataclass
class ShellWrap:
    """Wrapper for a shell session."""
    id: int
    session: LocalInteractiveSession | SSHInteractiveSession
    running: bool = False


@dataclass
class CodeExecutionState:
    """State for code execution helper."""
    ssh_enabled: bool = False
    shells: dict[int, ShellWrap] = field(default_factory=dict)


class CodeExecutionHelper(AgentHelper):
    """
    A0 Helper for code execution via local/SSH shells.

    Manages multiple shell sessions, handles output collection,
    and provides timeout/dialog detection.
    """

    STATE_KEY = "_code_execution_state"

    # Shell prompt patterns for detecting completion
    PROMPT_PATTERNS = [
        re.compile(r"\\(venv\\).+[$#] ?$"),
        re.compile(r"root@[^:]+:[^#]+# ?$"),
        re.compile(r"[a-zA-Z0-9_.-]+@[^:]+:[^$#]+[$#] ?$"),
        re.compile(r"\(?.*\)?\s*PS\s+[^>]+> ?$"),
    ]

    # Dialog patterns for detecting interactive prompts
    DIALOG_PATTERNS = [
        re.compile(r"Y/N", re.IGNORECASE),
        re.compile(r"yes/no", re.IGNORECASE),
        re.compile(r":\s*$"),
        re.compile(r"\?\s*$"),
    ]

    def __init__(self, agent: "Agent"):
        super().__init__(agent)
        self._state: CodeExecutionState = CodeExecutionState(
            ssh_enabled=agent.config.code_exec_ssh_enabled
        )

    @classmethod
    async def get(cls, agent: "Agent") -> "CodeExecutionHelper":
        """Get or create code execution helper for agent."""
        existing = agent.get_data(cls.STATE_KEY)
        if existing is not None and isinstance(existing, cls):
            # Reset if SSH config changed
            if existing._state.ssh_enabled != agent.config.code_exec_ssh_enabled:
                await existing.cleanup()
                return await cls._create_new(agent)
            return existing
        return await cls._create_new(agent)

    @classmethod
    async def _create_new(cls, agent: "Agent") -> "CodeExecutionHelper":
        """Create new helper instance."""
        instance = cls(agent)
        agent.set_data(cls.STATE_KEY, instance)
        return instance

    @property
    def state(self) -> CodeExecutionState:
        """Get current state."""
        return self._state

    def get_cwd(self) -> Optional[str]:
        """Get current working directory for shells."""
        project_name = projects.get_context_project_name(self.agent.context)
        if not project_name:
            return None
        project_path = projects.get_project_folder(project_name)
        return files.normalize_a0_path(project_path)

    async def ensure_session(self, session: int) -> ShellWrap:
        """Ensure a shell session exists, creating if needed."""
        if session in self._state.shells:
            return self._state.shells[session]

        # Create new session
        if self.agent.config.code_exec_ssh_enabled:
            pswd = (
                self.agent.config.code_exec_ssh_pass
                if self.agent.config.code_exec_ssh_pass
                else await rfc_exchange.get_root_password()
            )
            shell = SSHInteractiveSession(
                self.agent.context.log,
                self.agent.config.code_exec_ssh_addr,
                self.agent.config.code_exec_ssh_port,
                self.agent.config.code_exec_ssh_user,
                pswd,
                cwd=self.get_cwd(),
            )
        else:
            shell = LocalInteractiveSession(cwd=self.get_cwd())

        shell_wrap = ShellWrap(id=session, session=shell, running=False)
        self._state.shells[session] = shell_wrap
        await shell.connect()
        return shell_wrap

    async def reset_session(self, session: int) -> None:
        """Reset a specific shell session."""
        if session in self._state.shells:
            await self._state.shells[session].session.close()
            del self._state.shells[session]

    async def reset_all_sessions(self) -> None:
        """Reset all shell sessions."""
        for session_id in list(self._state.shells.keys()):
            await self._state.shells[session_id].session.close()
        self._state.shells = {}

    async def cleanup(self) -> None:
        """Cleanup all resources."""
        await self.reset_all_sessions()

    def is_session_running(self, session: int) -> bool:
        """Check if a session is currently running a command."""
        if session not in self._state.shells:
            return False
        return self._state.shells[session].running

    def mark_session_running(self, session: int, running: bool = True) -> None:
        """Mark session as running or idle."""
        if session in self._state.shells:
            self._state.shells[session].running = running

    def get_session_type(self, session: int) -> str:
        """Get type of session (local/remote)."""
        if session not in self._state.shells:
            return "unknown"
        shell = self._state.shells[session].session
        if isinstance(shell, LocalInteractiveSession):
            return "local"
        elif isinstance(shell, SSHInteractiveSession):
            return "remote"
        return "unknown"

    async def send_command(self, session: int, command: str) -> None:
        """Send command to a session."""
        shell_wrap = await self.ensure_session(session)
        shell_wrap.running = True
        await shell_wrap.session.send_command(command)

    async def read_output(
        self,
        session: int,
        timeout: int = 1,
        reset_full_output: bool = False
    ) -> tuple[str, str]:
        """Read output from a session."""
        if session not in self._state.shells:
            return "", ""
        return await self._state.shells[session].session.read_output(
            timeout=timeout, reset_full_output=reset_full_output
        )

    def detect_prompt(self, output: str) -> bool:
        """Check if output ends with a shell prompt."""
        last_lines = output.splitlines()[-3:] if output else []
        for line in last_lines:
            for pat in self.PROMPT_PATTERNS:
                if pat.search(line.strip()):
                    return True
        return False

    def detect_dialog(self, output: str) -> bool:
        """Check if output ends with a dialog prompt."""
        last_lines = output.splitlines()[-2:] if output else []
        for line in last_lines:
            for pat in self.DIALOG_PATTERNS:
                if pat.search(line.strip()):
                    return True
        return False

    def format_command(self, command: str, max_length: int = 100) -> str:
        """Format command for display output."""
        short_cmd = command[:200]
        short_cmd = " ".join(short_cmd.split())
        return truncate_text_string(short_cmd, max_length)

    def fix_output(self, output: str) -> str:
        """Clean and truncate output."""
        output = re.sub(r"(?<!\\)\\x[0-9A-Fa-f]{2}", "", output)
        return truncate_text_agent(agent=self.agent, output=output, threshold=1000000)

    async def execute_python(
        self,
        code: str,
        session: int = 0,
        reset: bool = False
    ) -> tuple[str, str]:
        """Execute Python code and return (prefix, command)."""
        escaped_code = shlex.quote(code)
        command = f"ipython -c {escaped_code}"
        prefix = "python> " + self.format_command(code) + "\n\n"
        return prefix, command

    async def execute_nodejs(
        self,
        code: str,
        session: int = 0,
        reset: bool = False
    ) -> tuple[str, str]:
        """Execute Node.js code and return (prefix, command)."""
        escaped_code = shlex.quote(code)
        command = f"node /exe/node_eval.js {escaped_code}"
        prefix = "node> " + self.format_command(code) + "\n\n"
        return prefix, command

    async def execute_terminal(
        self,
        command: str,
        session: int = 0,
        reset: bool = False
    ) -> tuple[str, str]:
        """Execute terminal command and return (prefix, command)."""
        shell_type = "bash" if not runtime.is_windows() or self.agent.config.code_exec_ssh_enabled else "PS"
        prefix = f"{shell_type}> " + self.format_command(command) + "\n\n"
        return prefix, command

    async def collect_output(
        self,
        session: int,
        prefix: str = "",
        timeouts: Optional[dict] = None,
        log_callback: Optional[Any] = None,
        progress_callback: Optional[Any] = None
    ) -> tuple[str, Optional[str]]:
        """
        Collect output from a running command.

        Returns:
            (output, system_info) - system_info is None if completed normally
        """
        if timeouts is None:
            timeouts = CODE_EXEC_TIMEOUTS

        first_output_timeout = timeouts.get("first_output_timeout", 30)
        between_output_timeout = timeouts.get("between_output_timeout", 15)
        dialog_timeout = timeouts.get("dialog_timeout", 5)
        max_exec_timeout = timeouts.get("max_exec_timeout", 180)

        start_time = time.time()
        last_output_time = start_time
        truncated_output = ""
        got_output = False
        reset_full_output = True

        while True:
            await asyncio.sleep(0.1)
            full_output, partial_output = await self.read_output(
                session, timeout=1, reset_full_output=reset_full_output
            )
            reset_full_output = False

            await self.agent.handle_intervention()

            now = time.time()
            if partial_output:
                PrintStyle(font_color="#85C1E9").stream(partial_output)
                truncated_output = self.fix_output(full_output)

                if progress_callback:
                    progress_callback(truncated_output)
                if log_callback:
                    log_callback(prefix + truncated_output)

                last_output_time = now
                got_output = True

                # Check for shell prompt
                if self.detect_prompt(truncated_output):
                    PrintStyle.info("Detected shell prompt, returning output early.")
                    self.mark_session_running(session, False)
                    return truncated_output, None

            # Check max execution time
            if now - start_time > max_exec_timeout:
                sys_info = f"Command execution exceeded maximum time ({max_exec_timeout}s)"
                PrintStyle.warning(sys_info)
                return truncated_output, sys_info

            # Check timeouts
            if not got_output:
                if now - start_time > first_output_timeout:
                    sys_info = f"No output received within {first_output_timeout}s"
                    PrintStyle.warning(sys_info)
                    return "", sys_info
            else:
                if now - last_output_time > between_output_timeout:
                    sys_info = f"No additional output for {between_output_timeout}s"
                    PrintStyle.warning(sys_info)
                    return truncated_output, sys_info

                # Dialog detection
                if now - last_output_time > dialog_timeout:
                    if self.detect_dialog(truncated_output):
                        PrintStyle.info("Detected dialog prompt, returning output early.")
                        sys_info = f"Possible interactive prompt detected after {dialog_timeout}s"
                        return truncated_output, sys_info

    async def check_running_session(
        self,
        session: int
    ) -> tuple[Optional[str], bool]:
        """
        Check if session is running and get current output.

        Returns:
            (output, has_dialog) or (None, False) if not running
        """
        if not self.is_session_running(session):
            return None, False

        full_output, _ = await self.read_output(session, timeout=1, reset_full_output=True)
        truncated_output = self.fix_output(full_output)

        # Check for prompt (command finished)
        if self.detect_prompt(truncated_output):
            self.mark_session_running(session, False)
            return None, False

        has_dialog = self.detect_dialog(truncated_output)
        return truncated_output, has_dialog
