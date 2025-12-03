"""
A0 Framework - Agentic Tool & Instrument Loader

Discovers and executes tools/instruments from FalkorDB semantically.
No hard-coded imports - A0 finds what it needs through the graph.

Architecture:
- Tools/instruments stored in FalkorDB with semantic descriptions
- A0 searches by intent: "I need to execute shell commands"
- Code is loaded dynamically and executed
- A0 can create new tools/instruments as needed

Usage:
    from python.helpers.agentic_loader import AgenticLoader

    loader = await AgenticLoader.get()

    # Find and execute a tool by intent
    result = await loader.execute_tool("execute shell command", command="ls -la")

    # Find and run an instrument
    result = await loader.run_instrument("parse JSON data", data=json_string)
"""

import asyncio
from typing import Any, Optional, Type, Callable
from dataclasses import dataclass

from python.helpers.code_loader import CodeLoader, CodeType
from python.helpers.print_style import PrintStyle


@dataclass
class ToolMatch:
    """A tool found via semantic search."""
    path: str
    score: float
    tool_class: Optional[Type] = None


@dataclass
class InstrumentMatch:
    """An instrument found via semantic search."""
    path: str
    score: float
    execute: Optional[Callable] = None


class AgenticLoader:
    """
    Agentic loader for tools and instruments.

    Instead of hard-coded imports, A0 describes what it needs
    and this loader finds, loads, and executes the right code.
    """

    _instance: Optional["AgenticLoader"] = None
    _lock = asyncio.Lock()

    def __init__(self, code_loader: CodeLoader):
        self.code_loader = code_loader
        self._tool_cache: dict[str, Type] = {}
        self._instrument_cache: dict[str, Callable] = {}

    @classmethod
    async def get(cls) -> "AgenticLoader":
        """Get or create AgenticLoader singleton."""
        async with cls._lock:
            if cls._instance is None:
                code_loader = await CodeLoader.get()
                cls._instance = cls(code_loader)
            return cls._instance

    # =========================================================================
    # Tool Discovery & Execution
    # =========================================================================

    async def find_tool(self, intent: str, threshold: float = 0.5) -> Optional[ToolMatch]:
        """
        Find a tool by intent/description.

        Args:
            intent: What the tool should do (e.g., "execute shell commands")
            threshold: Minimum similarity score

        Returns:
            ToolMatch or None if not found
        """
        results = await self.code_loader.search(intent, code_type=CodeType.TOOL, limit=1)

        if not results:
            return None

        match = results[0]
        if match.get("score", 0) < threshold:
            return None

        path = match["path"]

        # Load the tool class
        tool_class = await self.code_loader.load_tool(path)
        if not tool_class:
            return None

        return ToolMatch(
            path=path,
            score=match.get("score", 1.0),
            tool_class=tool_class,
        )

    async def find_tools(self, intent: str, limit: int = 5) -> list[ToolMatch]:
        """Find multiple tools matching an intent."""
        results = await self.code_loader.search(intent, code_type=CodeType.TOOL, limit=limit)

        matches = []
        for r in results:
            path = r["path"]
            tool_class = await self.code_loader.load_tool(path)
            if tool_class:
                matches.append(ToolMatch(
                    path=path,
                    score=r.get("score", 1.0),
                    tool_class=tool_class,
                ))

        return matches

    async def get_tool_class(self, intent: str) -> Optional[Type]:
        """
        Get a tool class by intent. Returns cached if available.

        This is the primary method for agentic tool discovery.
        """
        # Check cache first
        if intent in self._tool_cache:
            return self._tool_cache[intent]

        match = await self.find_tool(intent)
        if match and match.tool_class:
            self._tool_cache[intent] = match.tool_class
            return match.tool_class

        return None

    async def execute_tool(
        self,
        intent: str,
        agent: Any,
        **kwargs,
    ) -> Any:
        """
        Find and execute a tool by intent.

        Args:
            intent: What the tool should do
            agent: The agent context
            **kwargs: Arguments to pass to the tool

        Returns:
            Tool execution result
        """
        tool_class = await self.get_tool_class(intent)
        if not tool_class:
            raise ValueError(f"No tool found for intent: {intent}")

        # Instantiate and execute
        tool = tool_class(
            agent=agent,
            name=tool_class.__name__,
            method=None,
            args=kwargs,
            message="",
            loop_data=None,
        )

        await tool.before_execution()
        response = await tool.execute(**kwargs)
        await tool.after_execution(response)

        return response

    # =========================================================================
    # Instrument Discovery & Execution
    # =========================================================================

    async def find_instrument(self, intent: str, threshold: float = 0.5) -> Optional[InstrumentMatch]:
        """
        Find an instrument by intent/description.

        Args:
            intent: What the instrument should do
            threshold: Minimum similarity score

        Returns:
            InstrumentMatch or None if not found
        """
        results = await self.code_loader.search(intent, code_type=CodeType.INSTRUMENT, limit=1)

        if not results:
            return None

        match = results[0]
        if match.get("score", 0) < threshold:
            return None

        path = match["path"]

        # Load the instrument module
        module = await self.code_loader.load_module(path)
        if not module:
            return None

        # Find the main entry point (run, execute, main, or module-level code)
        execute_fn = None
        for name in ["run", "execute", "main", "__call__"]:
            if hasattr(module, name):
                execute_fn = getattr(module, name)
                break

        return InstrumentMatch(
            path=path,
            score=match.get("score", 1.0),
            execute=execute_fn,
        )

    async def run_instrument(
        self,
        intent: str,
        *args,
        **kwargs,
    ) -> Any:
        """
        Find and run an instrument by intent.

        Args:
            intent: What the instrument should do
            *args, **kwargs: Arguments to pass

        Returns:
            Instrument execution result
        """
        match = await self.find_instrument(intent)
        if not match:
            raise ValueError(f"No instrument found for intent: {intent}")

        if match.execute:
            # Call the entry point function
            if asyncio.iscoroutinefunction(match.execute):
                return await match.execute(*args, **kwargs)
            return match.execute(*args, **kwargs)
        else:
            # Execute the whole module (for scripts)
            return await self.code_loader.execute(match.path, locals_dict={"args": args, "kwargs": kwargs})

    async def execute_instrument(
        self,
        path: str,
        *args,
        **kwargs,
    ) -> Any:
        """
        Execute an instrument by path (when path is known).

        Args:
            path: Path to the instrument in FalkorDB
            *args, **kwargs: Arguments to pass

        Returns:
            Execution result
        """
        module = await self.code_loader.load_module(path)
        if not module:
            raise FileNotFoundError(f"Instrument not found: {path}")

        # Find entry point
        for name in ["run", "execute", "main"]:
            if hasattr(module, name):
                fn = getattr(module, name)
                if asyncio.iscoroutinefunction(fn):
                    return await fn(*args, **kwargs)
                return fn(*args, **kwargs)

        # No entry point, execute as script
        return await self.code_loader.execute(path, locals_dict={"args": args, "kwargs": kwargs})

    # =========================================================================
    # Extension Discovery
    # =========================================================================

    async def get_extensions(self, extension_point: str) -> list[Type]:
        """
        Get all extensions for an extension point.

        Args:
            extension_point: The extension point name (e.g., "monologue_start")

        Returns:
            List of extension classes, sorted by execution order
        """
        return await self.code_loader.get_all_extensions(extension_point)

    # =========================================================================
    # Helper Discovery
    # =========================================================================

    async def find_helper(self, intent: str) -> Optional[Any]:
        """
        Find a helper module by intent.

        Args:
            intent: What the helper should do

        Returns:
            The loaded module or None
        """
        results = await self.code_loader.search(intent, code_type=CodeType.HELPER, limit=1)

        if not results:
            return None

        path = results[0]["path"]
        return await self.code_loader.load_module(path)

    async def get_helper_class(self, intent: str, class_name: str) -> Optional[Type]:
        """
        Find a helper and get a specific class from it.

        Args:
            intent: What the helper should do
            class_name: Name of the class to get

        Returns:
            The class or None
        """
        module = await self.find_helper(intent)
        if module:
            return getattr(module, class_name, None)
        return None

    # =========================================================================
    # Code Creation (A0 writes new code)
    # =========================================================================

    async def create_tool(
        self,
        name: str,
        description: str,
        code: str,
    ) -> str:
        """
        Create a new tool in FalkorDB.

        Args:
            name: Tool name
            description: What the tool does
            code: Python code for the tool

        Returns:
            Path where the tool was stored
        """
        path = f"python/tools/{name.lower()}.py"

        await self.code_loader.store(
            path=path,
            content=code,
            code_type=CodeType.TOOL,
            metadata={"description": description, "name": name},
        )

        # Clear cache
        self._tool_cache.clear()

        return path

    async def create_instrument(
        self,
        name: str,
        description: str,
        code: str,
    ) -> str:
        """
        Create a new instrument in FalkorDB.

        Args:
            name: Instrument name
            description: What the instrument does
            code: Python code for the instrument

        Returns:
            Path where the instrument was stored
        """
        path = f"instruments/{name.lower()}.py"

        await self.code_loader.store(
            path=path,
            content=code,
            code_type=CodeType.INSTRUMENT,
            metadata={"description": description, "name": name},
        )

        # Clear cache
        self._instrument_cache.clear()

        return path

    # =========================================================================
    # Listing
    # =========================================================================

    async def list_tools(self) -> list[str]:
        """List all available tools."""
        return await self.code_loader.list_code(CodeType.TOOL)

    async def list_instruments(self) -> list[str]:
        """List all available instruments."""
        return await self.code_loader.list_code(CodeType.INSTRUMENT)

    async def list_extensions(self) -> list[str]:
        """List all available extensions."""
        return await self.code_loader.list_code(CodeType.EXTENSION)

    async def list_helpers(self) -> list[str]:
        """List all available helpers."""
        return await self.code_loader.list_code(CodeType.HELPER)
