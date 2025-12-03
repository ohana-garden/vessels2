"""
A0 Framework - Dynamic Code Loader

Loads and executes code stored in FalkorDB instead of filesystem.
Enables A0 to be fully self-aware and self-modifying.

Architecture:
- All code (tools, extensions, helpers, instruments) stored in FalkorDB
- Code is loaded dynamically when needed
- A0 can write new code directly to the database
- Cached in memory for performance

Usage:
    from python.helpers.code_loader import CodeLoader

    loader = await CodeLoader.get()

    # Load and get a class from stored code
    ToolClass = await loader.load_class("python/tools/my_tool.py", "MyTool")

    # Execute stored code
    result = await loader.execute("instruments/my_script.py")

    # Store new code
    await loader.store("python/tools/new_tool.py", code_content, code_type="tool")
"""

import asyncio
import sys
import types
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Type, Callable
from enum import Enum
import importlib.util
import json

from python.helpers.graph_store import GraphStore, get_graph_store
from python.helpers.print_style import PrintStyle


class CodeType(str, Enum):
    """Types of executable code."""
    TOOL = "tool"
    EXTENSION = "extension"
    HELPER = "helper"
    API = "api"
    INSTRUMENT = "instrument"
    SCRIPT = "script"


@dataclass
class StoredCode:
    """Code stored in FalkorDB."""
    path: str
    content: str
    code_type: CodeType
    hash: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.hash:
            self.hash = hashlib.sha256(self.content.encode()).hexdigest()[:16]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.updated_at:
            self.updated_at = self.created_at

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "content": self.content,
            "code_type": self.code_type.value,
            "hash": self.hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StoredCode":
        return cls(
            path=data["path"],
            content=data["content"],
            code_type=CodeType(data.get("code_type", "script")),
            hash=data.get("hash", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class LoadedModule:
    """A module loaded from stored code."""
    path: str
    module: types.ModuleType
    hash: str
    loaded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CodeLoader:
    """
    Dynamic code loader that retrieves and executes code from FalkorDB.

    This replaces filesystem-based code loading, allowing A0 to:
    - Load tools, extensions, helpers from the database
    - Write and modify its own code
    - Be fully self-aware of its capabilities
    """

    _instance: Optional["CodeLoader"] = None
    _lock = asyncio.Lock()

    def __init__(self, graph_store: GraphStore):
        self.graph_store = graph_store
        self._module_cache: dict[str, LoadedModule] = {}
        self._code_cache: dict[str, StoredCode] = {}

    @classmethod
    async def get(cls) -> "CodeLoader":
        """Get or create CodeLoader singleton."""
        async with cls._lock:
            if cls._instance is None:
                graph_store = await get_graph_store()
                cls._instance = cls(graph_store)
            return cls._instance

    # =========================================================================
    # Code Storage
    # =========================================================================

    async def store(
        self,
        path: str,
        content: str,
        code_type: CodeType = CodeType.SCRIPT,
        metadata: Optional[dict] = None,
    ) -> StoredCode:
        """
        Store code in FalkorDB.

        Args:
            path: Virtual path (e.g., "python/tools/my_tool.py")
            content: The Python code content
            code_type: Type of code (tool, extension, etc.)
            metadata: Optional metadata (description, author, etc.)

        Returns:
            StoredCode object
        """
        # Normalize path
        path = path.replace("\\", "/").lstrip("/")

        # Check if exists to preserve created_at
        existing = await self.get_code(path)
        created_at = existing.created_at if existing else None

        stored = StoredCode(
            path=path,
            content=content,
            code_type=code_type,
            created_at=created_at or "",
            metadata=metadata or {},
        )

        # Store in graph
        await self._store_to_graph(stored)

        # Invalidate caches
        self._code_cache.pop(path, None)
        self._module_cache.pop(path, None)

        PrintStyle.standard(f"Stored code: {path} ({code_type.value})")
        return stored

    async def _store_to_graph(self, stored: StoredCode) -> None:
        """Store code in the graph database."""
        from graphiti_core.nodes import EpisodeType

        content_data = json.dumps(stored.to_dict())

        # Delete existing
        await self._delete_from_graph(stored.path)

        # Store as episode
        await self.graph_store.graphiti.add_episode(
            name=f"executable:{stored.path}",
            episode_body=content_data,
            source=EpisodeType.json,
            reference_time=datetime.now(timezone.utc),
            group_id=f"executable:{stored.code_type.value}",
        )

    async def _delete_from_graph(self, path: str) -> None:
        """Delete code from graph."""
        path = path.replace("\\", "/").lstrip("/")
        try:
            query = f"""
            MATCH (n:Episode) WHERE n.name = 'executable:{path}'
            DETACH DELETE n
            """
            await self.graph_store._driver.execute_query(query)
        except Exception:
            pass

    async def delete(self, path: str) -> bool:
        """Delete stored code."""
        path = path.replace("\\", "/").lstrip("/")
        await self._delete_from_graph(path)
        self._code_cache.pop(path, None)
        self._module_cache.pop(path, None)
        return True

    # =========================================================================
    # Code Retrieval
    # =========================================================================

    async def get_code(self, path: str) -> Optional[StoredCode]:
        """
        Get stored code by path.

        Args:
            path: Virtual path to the code

        Returns:
            StoredCode or None if not found
        """
        path = path.replace("\\", "/").lstrip("/")

        # Check cache
        if path in self._code_cache:
            return self._code_cache[path]

        # Query graph
        query = f"""
        MATCH (n:Episode) WHERE n.name = 'executable:{path}'
        RETURN n.content as content
        """
        result = await self.graph_store._driver.execute_query(query)

        if result and len(result) > 0:
            try:
                data = json.loads(result[0].get("content", "{}"))
                stored = StoredCode.from_dict(data)
                self._code_cache[path] = stored
                return stored
            except (json.JSONDecodeError, KeyError):
                pass

        return None

    async def list_code(self, code_type: Optional[CodeType] = None) -> list[str]:
        """List all stored code paths."""
        if code_type:
            query = f"""
            MATCH (n:Episode) WHERE n.name STARTS WITH 'executable:'
                AND n.group_id = 'executable:{code_type.value}'
            RETURN n.name as name
            """
        else:
            query = """
            MATCH (n:Episode) WHERE n.name STARTS WITH 'executable:'
            RETURN n.name as name
            """

        results = await self.graph_store._driver.execute_query(query)

        paths = []
        for row in results:
            name = row.get("name", "")
            if name.startswith("executable:"):
                paths.append(name[11:])  # Remove 'executable:' prefix

        return sorted(paths)

    async def search(self, query: str, code_type: Optional[CodeType] = None, limit: int = 10) -> list[dict]:
        """Search stored code by description/content."""
        group_id = f"executable:{code_type.value}" if code_type else None

        results = await self.graph_store.graphiti.search(
            query=query,
            num_results=limit,
            group_ids=[group_id] if group_id else None,
        )

        found = []
        for result in results:
            name = getattr(result, 'name', '') or ''
            if name.startswith("executable:"):
                path = name[11:]
                found.append({
                    "path": path,
                    "score": getattr(result, 'score', 1.0),
                })

        return found

    # =========================================================================
    # Code Loading & Execution
    # =========================================================================

    async def load_module(self, path: str, force_reload: bool = False) -> Optional[types.ModuleType]:
        """
        Load code as a Python module.

        Args:
            path: Virtual path to the code
            force_reload: Force reload even if cached

        Returns:
            Python module object or None if not found
        """
        path = path.replace("\\", "/").lstrip("/")

        # Check cache (unless force reload)
        if not force_reload and path in self._module_cache:
            cached = self._module_cache[path]
            # Verify hash hasn't changed
            stored = await self.get_code(path)
            if stored and stored.hash == cached.hash:
                return cached.module

        # Get code
        stored = await self.get_code(path)
        if not stored:
            return None

        # Create module
        module_name = path.replace("/", ".").replace(".py", "")
        module = types.ModuleType(module_name)
        module.__file__ = f"falkordb://{path}"
        module.__loader__ = None
        module.__package__ = ".".join(module_name.split(".")[:-1])

        # Execute code in module namespace
        try:
            exec(compile(stored.content, f"falkordb://{path}", "exec"), module.__dict__)
        except Exception as e:
            PrintStyle.error(f"Failed to load module {path}: {e}")
            return None

        # Cache it
        self._module_cache[path] = LoadedModule(
            path=path,
            module=module,
            hash=stored.hash,
        )

        return module

    async def load_class(self, path: str, class_name: str) -> Optional[Type]:
        """
        Load a specific class from stored code.

        Args:
            path: Virtual path to the code
            class_name: Name of the class to load

        Returns:
            The class or None if not found
        """
        module = await self.load_module(path)
        if not module:
            return None

        return getattr(module, class_name, None)

    async def load_function(self, path: str, func_name: str) -> Optional[Callable]:
        """
        Load a specific function from stored code.

        Args:
            path: Virtual path to the code
            func_name: Name of the function to load

        Returns:
            The function or None if not found
        """
        module = await self.load_module(path)
        if not module:
            return None

        return getattr(module, func_name, None)

    async def execute(
        self,
        path: str,
        globals_dict: Optional[dict] = None,
        locals_dict: Optional[dict] = None,
    ) -> Any:
        """
        Execute stored code and return result.

        Args:
            path: Virtual path to the code
            globals_dict: Global namespace for execution
            locals_dict: Local namespace for execution

        Returns:
            The result of execution (last expression or explicit return)
        """
        stored = await self.get_code(path)
        if not stored:
            raise FileNotFoundError(f"Code not found: {path}")

        # Prepare execution namespace
        exec_globals = globals_dict or {}
        exec_locals = locals_dict or {}

        # Add common imports
        exec_globals.setdefault("__builtins__", __builtins__)

        # Execute
        try:
            exec(compile(stored.content, f"falkordb://{path}", "exec"), exec_globals, exec_locals)
            # Return 'result' if defined
            return exec_locals.get("result", None)
        except Exception as e:
            PrintStyle.error(f"Execution failed for {path}: {e}")
            raise

    async def execute_function(
        self,
        path: str,
        func_name: str,
        *args,
        **kwargs,
    ) -> Any:
        """
        Load and execute a specific function.

        Args:
            path: Virtual path to the code
            func_name: Name of the function
            *args, **kwargs: Arguments to pass to the function

        Returns:
            Function return value
        """
        func = await self.load_function(path, func_name)
        if not func:
            raise AttributeError(f"Function {func_name} not found in {path}")

        # Handle async functions
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        return func(*args, **kwargs)

    # =========================================================================
    # Tool Loading (A0 Integration)
    # =========================================================================

    async def load_tool(self, tool_path: str) -> Optional[Type]:
        """
        Load a Tool class from stored code.

        Convenience method for loading A0 tools.
        """
        # Find the Tool subclass in the module
        module = await self.load_module(tool_path)
        if not module:
            return None

        # Import Tool base for isinstance check
        from python.helpers.tool import Tool

        # Find Tool subclass
        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, Tool) and obj is not Tool:
                return obj

        return None

    async def load_extension(self, ext_path: str) -> Optional[Type]:
        """
        Load an Extension class from stored code.

        Convenience method for loading A0 extensions.
        """
        module = await self.load_module(ext_path)
        if not module:
            return None

        from python.helpers.extension import Extension

        for name in dir(module):
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, Extension) and obj is not Extension:
                return obj

        return None

    async def get_all_tools(self) -> dict[str, Type]:
        """Load all stored tools."""
        tools = {}
        paths = await self.list_code(CodeType.TOOL)

        for path in paths:
            tool_cls = await self.load_tool(path)
            if tool_cls:
                tools[path] = tool_cls

        return tools

    async def get_all_extensions(self, extension_point: str) -> list[Type]:
        """Load all extensions for an extension point."""
        extensions = []
        paths = await self.list_code(CodeType.EXTENSION)

        for path in paths:
            if extension_point in path:
                ext_cls = await self.load_extension(path)
                if ext_cls:
                    extensions.append(ext_cls)

        # Sort by path (maintains _NN_ ordering)
        extensions.sort(key=lambda x: getattr(x, '__module__', ''))
        return extensions

