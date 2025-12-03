"""
Code Registry - Graph-native code storage and execution for Vessels.

This module provides a system for storing Python code in the graph database
and loading/executing it dynamically at runtime. This enables the A0 paradigm:
"no files, code in DB, agents instead of imports."

Usage:
    # Register code in the graph
    await registry.register("moral_geometry", code_string, code_type="module")

    # Load and use code from graph
    module = await registry.load("moral_geometry")
    vector = module.MoralVector()

    # Or get a specific class
    MoralVector = await registry.get_class("moral_geometry", "MoralVector")
"""

import asyncio
import json
import types
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional, Type, TypeVar
from dataclasses import dataclass, field

T = TypeVar('T')


@dataclass
class CodeEntry:
    """A code entry in the registry."""
    name: str
    code: str
    code_type: str  # module, tool, extension, agent_capability
    version: str = ""
    dependencies: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
        if not self.version:
            # Generate version from code hash
            self.version = hashlib.sha256(self.code.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "code": self.code,
            "code_type": self.code_type,
            "version": self.version,
            "dependencies": self.dependencies,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CodeEntry":
        return cls(
            name=data.get("name", ""),
            code=data.get("code", ""),
            code_type=data.get("code_type", "module"),
            version=data.get("version", ""),
            dependencies=data.get("dependencies", []),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


class CodeRegistry:
    """
    Graph-native code registry for dynamic code loading.

    Stores Python code in the graph database and provides
    mechanisms to load and execute it at runtime.
    """

    _instance: Optional["CodeRegistry"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._cache: dict[str, types.ModuleType] = {}
        self._entries: dict[str, CodeEntry] = {}
        self._store = None

    @classmethod
    async def get_instance(cls) -> "CodeRegistry":
        """Get or create the singleton registry instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    async def _get_store(self):
        """Get the graph store instance."""
        if self._store is None:
            from python.helpers.graph_store import get_graph_store
            self._store = await get_graph_store()
        return self._store

    # =========================================================================
    # Registration (storing code in graph)
    # =========================================================================

    async def register(
        self,
        name: str,
        code: str,
        code_type: str = "module",
        dependencies: list[str] = None,
        metadata: dict = None,
    ) -> str:
        """
        Register code in the graph database.

        Args:
            name: Unique name for this code module
            code: Python source code as string
            code_type: Type of code (module, tool, extension, agent_capability)
            dependencies: List of other registry entries this depends on
            metadata: Additional metadata

        Returns:
            Version hash of the registered code
        """
        entry = CodeEntry(
            name=name,
            code=code,
            code_type=code_type,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )

        store = await self._get_store()

        content = json.dumps({
            "type": "code_registry",
            "entry": entry.to_dict(),
        })

        await store.save_content(
            f"code/{code_type}/{name}",
            content,
            content_type="code"
        )

        # Update local cache entry
        self._entries[name] = entry

        # Invalidate module cache if exists
        if name in self._cache:
            del self._cache[name]

        return entry.version

    async def register_tool(
        self,
        name: str,
        code: str,
        description: str = "",
        methods: list[str] = None,
    ) -> str:
        """Register a tool class in the graph."""
        return await self.register(
            name=name,
            code=code,
            code_type="tool",
            metadata={
                "description": description,
                "methods": methods or [],
            }
        )

    async def register_extension(
        self,
        name: str,
        code: str,
        extension_point: str,
        priority: int = 50,
    ) -> str:
        """Register an extension in the graph."""
        return await self.register(
            name=name,
            code=code,
            code_type="extension",
            metadata={
                "extension_point": extension_point,
                "priority": priority,
            }
        )

    async def register_agent_capability(
        self,
        name: str,
        code: str,
        capability_type: str,
        description: str = "",
    ) -> str:
        """
        Register an agent capability (replaces imports).

        Instead of `import numpy`, an agent provides the capability.
        """
        return await self.register(
            name=name,
            code=code,
            code_type="agent_capability",
            metadata={
                "capability_type": capability_type,
                "description": description,
            }
        )

    # =========================================================================
    # Loading (retrieving and executing code from graph)
    # =========================================================================

    async def load(self, name: str) -> Optional[types.ModuleType]:
        """
        Load a code module from the graph.

        Returns a Python module object with the code executed.
        """
        # Check cache first
        if name in self._cache:
            return self._cache[name]

        # Load entry from graph
        entry = await self._load_entry(name)
        if entry is None:
            return None

        # Load dependencies first
        for dep in entry.dependencies:
            await self.load(dep)

        # Compile and execute code
        module = self._compile_module(name, entry.code)

        # Cache the module
        self._cache[name] = module

        return module

    async def _load_entry(self, name: str) -> Optional[CodeEntry]:
        """Load a code entry from the graph."""
        if name in self._entries:
            return self._entries[name]

        store = await self._get_store()

        # Try different code types
        for code_type in ["module", "tool", "extension", "agent_capability"]:
            content = await store.get_content(f"code/{code_type}/{name}")
            if content:
                try:
                    data = json.loads(content)
                    if data.get("type") == "code_registry":
                        entry = CodeEntry.from_dict(data["entry"])
                        self._entries[name] = entry
                        return entry
                except json.JSONDecodeError:
                    pass

        return None

    def _compile_module(self, name: str, code: str) -> types.ModuleType:
        """Compile code string into a module object."""
        # Create a new module
        module = types.ModuleType(name)
        module.__dict__["__name__"] = name
        module.__dict__["__file__"] = f"<graph:{name}>"

        # Provide common imports in module namespace
        module.__dict__["__builtins__"] = __builtins__

        # Add access to other registry modules
        module.__dict__["__registry__"] = self

        # Compile and execute code in module namespace
        try:
            compiled = compile(code, f"<graph:{name}>", "exec")
            exec(compiled, module.__dict__)
        except Exception as e:
            from python.helpers.print_style import PrintStyle
            PrintStyle.error(f"Failed to compile code '{name}': {e}")
            raise

        return module

    async def get_class(
        self,
        module_name: str,
        class_name: str,
        base_class: Type[T] = None,
    ) -> Optional[Type[T]]:
        """
        Get a specific class from a registered module.

        Args:
            module_name: Name of the registered module
            class_name: Name of the class to retrieve
            base_class: Optional base class for type checking

        Returns:
            The class if found, None otherwise
        """
        module = await self.load(module_name)
        if module is None:
            return None

        cls = getattr(module, class_name, None)

        if cls is None:
            return None

        if base_class and not issubclass(cls, base_class):
            return None

        return cls

    async def get_function(
        self,
        module_name: str,
        function_name: str,
    ) -> Optional[callable]:
        """Get a specific function from a registered module."""
        module = await self.load(module_name)
        if module is None:
            return None

        func = getattr(module, function_name, None)

        if func is None or not callable(func):
            return None

        return func

    # =========================================================================
    # Listing and Discovery
    # =========================================================================

    async def list_registered(
        self,
        code_type: Optional[str] = None,
    ) -> list[str]:
        """List all registered code entries."""
        store = await self._get_store()
        paths = await store.list_content(content_type="code")

        names = []
        for path in paths:
            if path.startswith("code/"):
                parts = path.split("/")
                if len(parts) >= 3:
                    entry_type = parts[1]
                    entry_name = parts[2]
                    if code_type is None or entry_type == code_type:
                        names.append(entry_name)

        return names

    async def list_tools(self) -> list[dict]:
        """List all registered tools with metadata."""
        store = await self._get_store()
        paths = await store.list_content(content_type="code")

        tools = []
        for path in paths:
            if path.startswith("code/tool/"):
                name = path.split("/")[-1]
                entry = await self._load_entry(name)
                if entry:
                    tools.append({
                        "name": name,
                        "description": entry.metadata.get("description", ""),
                        "methods": entry.metadata.get("methods", []),
                        "version": entry.version,
                    })

        return tools

    async def list_extensions(self, extension_point: str = None) -> list[dict]:
        """List all registered extensions."""
        store = await self._get_store()
        paths = await store.list_content(content_type="code")

        extensions = []
        for path in paths:
            if path.startswith("code/extension/"):
                name = path.split("/")[-1]
                entry = await self._load_entry(name)
                if entry:
                    ep = entry.metadata.get("extension_point", "")
                    if extension_point is None or ep == extension_point:
                        extensions.append({
                            "name": name,
                            "extension_point": ep,
                            "priority": entry.metadata.get("priority", 50),
                            "version": entry.version,
                        })

        # Sort by priority
        extensions.sort(key=lambda x: x["priority"])

        return extensions

    async def list_capabilities(self) -> list[dict]:
        """List all registered agent capabilities."""
        store = await self._get_store()
        paths = await store.list_content(content_type="code")

        capabilities = []
        for path in paths:
            if path.startswith("code/agent_capability/"):
                name = path.split("/")[-1]
                entry = await self._load_entry(name)
                if entry:
                    capabilities.append({
                        "name": name,
                        "capability_type": entry.metadata.get("capability_type", ""),
                        "description": entry.metadata.get("description", ""),
                        "version": entry.version,
                    })

        return capabilities

    # =========================================================================
    # Deletion
    # =========================================================================

    async def unregister(self, name: str) -> bool:
        """Remove code from the registry."""
        store = await self._get_store()

        # Try to delete from all code types
        deleted = False
        for code_type in ["module", "tool", "extension", "agent_capability"]:
            if await store.delete_content(f"code/{code_type}/{name}"):
                deleted = True
                break

        # Clear from caches
        if name in self._cache:
            del self._cache[name]
        if name in self._entries:
            del self._entries[name]

        return deleted

    def clear_cache(self):
        """Clear the module cache."""
        self._cache.clear()


# =============================================================================
# Convenience Functions
# =============================================================================

async def get_registry() -> CodeRegistry:
    """Get the code registry singleton."""
    return await CodeRegistry.get_instance()


async def register_code(
    name: str,
    code: str,
    code_type: str = "module",
    **kwargs
) -> str:
    """Register code in the graph database."""
    registry = await get_registry()
    return await registry.register(name, code, code_type, **kwargs)


async def load_code(name: str) -> Optional[types.ModuleType]:
    """Load code from the graph database."""
    registry = await get_registry()
    return await registry.load(name)


async def get_class_from_graph(
    module_name: str,
    class_name: str,
) -> Optional[type]:
    """Get a class from graph-stored code."""
    registry = await get_registry()
    return await registry.get_class(module_name, class_name)
