"""
Code Registry - Graph-native code storage and execution for Vessels.

Code lives in the graph database. No filesystem fallback.
FalkorDB required - Vessels won't run without it.

All embedded defaults are in embedded_defaults.py for fast Docker startup.
"""

import asyncio
import json
import types
import hashlib
from typing import Optional, Type, TypeVar
from dataclasses import dataclass, field

# Import all defaults from centralized module
from python.helpers.embedded_defaults import get_all_defaults

T = TypeVar('T')


# =============================================================================
# Embedded Defaults (imported from embedded_defaults.py)
# =============================================================================

_DEFAULTS = get_all_defaults()


@dataclass
class CodeEntry:
    name: str
    code: str
    code_type: str = "module"
    version: str = ""
    dependencies: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.version:
            self.version = hashlib.sha256(self.code.encode()).hexdigest()[:12]

    def to_dict(self) -> dict:
        return {"name": self.name, "code": self.code, "code_type": self.code_type,
                "version": self.version, "dependencies": self.dependencies, "metadata": self.metadata}

    @classmethod
    def from_dict(cls, data: dict) -> "CodeEntry":
        return cls(name=data.get("name", ""), code=data.get("code", ""),
                   code_type=data.get("code_type", "module"), version=data.get("version", ""),
                   dependencies=data.get("dependencies", []), metadata=data.get("metadata", {}))


class CodeRegistry:
    """Graph-native code registry. DB required."""

    _instance: Optional["CodeRegistry"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._cache: dict[str, types.ModuleType] = {}
        self._entries: dict[str, CodeEntry] = {}
        self._store = None

    @classmethod
    async def get_instance(cls) -> "CodeRegistry":
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    async def _get_store(self):
        if self._store is None:
            from python.helpers.graph_store import get_graph_store
            self._store = await get_graph_store()
        return self._store

    async def register(self, name: str, code: str, code_type: str = "module",
                       dependencies: list[str] = None, metadata: dict = None) -> str:
        entry = CodeEntry(name=name, code=code, code_type=code_type,
                          dependencies=dependencies or [], metadata=metadata or {})
        store = await self._get_store()
        content = json.dumps({"type": "code_registry", "entry": entry.to_dict()})
        await store.save_content(f"code/{code_type}/{name}", content, content_type="code")
        self._entries[name] = entry
        self._cache.pop(name, None)
        return entry.version

    async def load(self, name: str) -> Optional[types.ModuleType]:
        """Load module from graph DB."""
        if name in self._cache:
            return self._cache[name]

        entry = await self._load_entry(name)

        # Seed from defaults if not in DB
        if entry is None and name in _DEFAULTS:
            default = _DEFAULTS[name]
            await self.register(name, default["code"], default.get("code_type", "module"))
            entry = await self._load_entry(name)

        if entry is None:
            return None

        for dep in entry.dependencies:
            await self.load(dep)

        module = self._compile(name, entry.code)
        self._cache[name] = module
        return module

    async def _load_entry(self, name: str) -> Optional[CodeEntry]:
        if name in self._entries:
            return self._entries[name]

        store = await self._get_store()
        for code_type in ["module", "tool", "extension", "agent_capability"]:
            content = await store.get_content(f"code/{code_type}/{name}")
            if content:
                data = json.loads(content)
                if data.get("type") == "code_registry":
                    entry = CodeEntry.from_dict(data["entry"])
                    self._entries[name] = entry
                    return entry
        return None

    def _compile(self, name: str, code: str) -> types.ModuleType:
        module = types.ModuleType(name)
        module.__dict__["__name__"] = name
        module.__dict__["__builtins__"] = __builtins__
        module.__dict__["__registry__"] = self
        compiled = compile(code, f"<db:{name}>", "exec")
        exec(compiled, module.__dict__)
        return module

    async def get_class(self, module_name: str, class_name: str) -> Optional[type]:
        module = await self.load(module_name)
        return getattr(module, class_name, None) if module else None

    async def list_registered(self, code_type: str = None) -> list[str]:
        store = await self._get_store()
        paths = await store.list_content(content_type="code")
        names = []
        for path in paths:
            if path.startswith("code/"):
                parts = path.split("/")
                if len(parts) >= 3:
                    if code_type is None or parts[1] == code_type:
                        names.append(parts[2])
        return names

    async def unregister(self, name: str) -> bool:
        store = await self._get_store()
        for code_type in ["module", "tool", "extension", "agent_capability"]:
            if await store.delete_content(f"code/{code_type}/{name}"):
                self._cache.pop(name, None)
                self._entries.pop(name, None)
                return True
        return False


async def get_registry() -> CodeRegistry:
    return await CodeRegistry.get_instance()

async def load_code(name: str) -> Optional[types.ModuleType]:
    registry = await get_registry()
    return await registry.load(name)
