"""
A0 Framework - Tool Base Class

Base class for all A0 tools with guardian integration for output sanitization.
All tools inherit from this class and implement the execute() method.

Usage:
    class MyTool(Tool):
        async def execute(self, **kwargs) -> Response:
            result = "..."
            return Response(message=result, break_loop=False)
"""

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any

from agent import Agent, LoopData
from python.helpers.print_style import PrintStyle
from python.helpers.strings import sanitize_string
from python.helpers.guardians import guard_tool


@dataclass
class Response:
    """Standard response from tool execution."""
    message: str
    break_loop: bool
    additional: dict[str, Any] | None = None

    def with_guarded_message(self, source: str = "tool") -> "Response":
        """Return a new Response with the message sanitized by guardians."""
        guarded = guard_tool(self.message, source=source)
        return Response(
            message=guarded,
            break_loop=self.break_loop,
            additional=self.additional
        )


class Tool:

    def __init__(self, agent: Agent, name: str, method: str | None, args: dict[str,str], message: str, loop_data: LoopData | None, **kwargs) -> None:
        self.agent = agent
        self.name = name
        self.method = method
        self.args = args
        self.loop_data = loop_data
        self.message = message
        self.progress: str = ""

    @abstractmethod
    async def execute(self,**kwargs) -> Response:
        pass

    def set_progress(self, content: str | None):
        self.progress = content or ""

    def add_progress(self, content: str | None):
        if not content:
            return
        self.progress += content

    @classmethod
    def use_guardians(cls) -> bool:
        """Override to disable guardian sanitization for specific tools."""
        return True

    async def before_execution(self, **kwargs):
        PrintStyle(font_color="#1B4F72", padding=True, background_color="white", bold=True).print(f"{self.agent.agent_name}: Using tool '{self.name}'")
        self.log = self.get_log_object()
        if self.args and isinstance(self.args, dict):
            for key, value in self.args.items():
                PrintStyle(font_color="#85C1E9", bold=True).stream(self.nice_key(key)+": ")
                PrintStyle(font_color="#85C1E9", padding=isinstance(value,str) and "\n" in value).stream(value)
                PrintStyle().print()

    async def after_execution(self, response: Response, **kwargs):
        # Apply guardian sanitization to tool output
        if self.use_guardians():
            response = response.with_guarded_message(source=f"tool.{self.name}")

        text = sanitize_string(response.message.strip())
        self.agent.hist_add_tool_result(self.name, text, **(response.additional or {}))
        PrintStyle(font_color="#1B4F72", background_color="white", padding=True, bold=True).print(f"{self.agent.agent_name}: Response from tool '{self.name}'")
        PrintStyle(font_color="#85C1E9").print(text)
        self.log.update(content=text)

    def get_log_object(self):
        if self.method:
            heading = f"icon://construction {self.agent.agent_name}: Using tool '{self.name}:{self.method}'"
        else:
            heading = f"icon://construction {self.agent.agent_name}: Using tool '{self.name}'"
        return self.agent.context.log.log(type="tool", heading=heading, content="", kvps=self.args)

    def nice_key(self, key:str):
        words = key.split('_')
        words = [words[0].capitalize()] + [word.lower() for word in words[1:]]
        result = ' '.join(words)
        return result
