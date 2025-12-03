"""
Prompt Registry - Graph-native prompt/content storage for Vessels.

Prompts and content live in the graph database. No filesystem fallback.
FalkorDB required - Vessels won't run without it.

Embedded defaults in embedded_defaults.py for fast Docker startup.
"""

import asyncio
import json
from typing import Optional
from dataclasses import dataclass, field

# Import prompt defaults from centralized module
from python.helpers.embedded_defaults import get_prompt_defaults

# =============================================================================
# Embedded Prompt Defaults
# =============================================================================

_PROMPT_DEFAULTS = get_prompt_defaults()


@dataclass
class PromptEntry:
    """A prompt/content entry stored in the database."""
    name: str
    content: str
    content_type: str = "prompt"
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "content": self.content,
            "content_type": self.content_type,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PromptEntry":
        return cls(
            name=data.get("name", ""),
            content=data.get("content", ""),
            content_type=data.get("content_type", "prompt"),
            metadata=data.get("metadata", {})
        )


class PromptRegistry:
    """Graph-native prompt registry. DB required."""

    _instance: Optional["PromptRegistry"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._cache: dict[str, str] = {}
        self._entries: dict[str, PromptEntry] = {}
        self._store = None

    @classmethod
    async def get_instance(cls) -> "PromptRegistry":
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    async def _get_store(self):
        if self._store is None:
            from python.helpers.graph_store import get_graph_store
            self._store = await get_graph_store()
        return self._store

    async def register(self, name: str, content: str, content_type: str = "prompt",
                       metadata: dict = None) -> None:
        """Register a prompt in the database."""
        entry = PromptEntry(
            name=name,
            content=content,
            content_type=content_type,
            metadata=metadata or {}
        )
        store = await self._get_store()
        db_content = json.dumps({"type": "prompt_registry", "entry": entry.to_dict()})
        await store.save_content(f"prompts/{name}", db_content, content_type="prompt")
        self._entries[name] = entry
        self._cache[name] = content

    async def load(self, name: str) -> Optional[str]:
        """Load prompt content from graph DB."""
        # Check cache first
        if name in self._cache:
            return self._cache[name]

        # Try loading from DB
        entry = await self._load_entry(name)

        # Seed from defaults if not in DB
        if entry is None and name in _PROMPT_DEFAULTS:
            default_content = _PROMPT_DEFAULTS[name]
            await self.register(name, default_content)
            entry = await self._load_entry(name)

        if entry is None:
            return None

        self._cache[name] = entry.content
        return entry.content

    async def _load_entry(self, name: str) -> Optional[PromptEntry]:
        """Load entry from database."""
        if name in self._entries:
            return self._entries[name]

        store = await self._get_store()
        content = await store.get_content(f"prompts/{name}")
        if content:
            try:
                data = json.loads(content)
                if data.get("type") == "prompt_registry":
                    entry = PromptEntry.from_dict(data["entry"])
                    self._entries[name] = entry
                    return entry
            except json.JSONDecodeError:
                # Raw content without registry wrapper
                entry = PromptEntry(name=name, content=content)
                self._entries[name] = entry
                return entry
        return None

    async def list_prompts(self) -> list[str]:
        """List all registered prompts."""
        store = await self._get_store()
        paths = await store.list_content(content_type="prompt")
        names = []
        for path in paths:
            if path.startswith("prompts/"):
                names.append(path[8:])  # Remove "prompts/" prefix
        return names

    async def delete(self, name: str) -> bool:
        """Delete a prompt from the database."""
        store = await self._get_store()
        if await store.delete_content(f"prompts/{name}"):
            self._cache.pop(name, None)
            self._entries.pop(name, None)
            return True
        return False

    def get_from_cache(self, name: str) -> Optional[str]:
        """Get prompt from cache only (synchronous, no DB access)."""
        return self._cache.get(name)

    async def preload_defaults(self) -> None:
        """Preload all default prompts to cache and DB."""
        for name, content in _PROMPT_DEFAULTS.items():
            if name not in self._cache:
                await self.register(name, content)


# =============================================================================
# Convenience Functions
# =============================================================================

async def get_prompt_registry() -> PromptRegistry:
    """Get the singleton prompt registry instance."""
    return await PromptRegistry.get_instance()


async def load_prompt(name: str) -> Optional[str]:
    """Load a prompt by name."""
    registry = await get_prompt_registry()
    return await registry.load(name)


async def register_prompt(name: str, content: str) -> None:
    """Register a new prompt."""
    registry = await get_prompt_registry()
    await registry.register(name, content)


# =============================================================================
# Synchronous Access (for backward compatibility)
# =============================================================================

_sync_cache: dict[str, str] = {}


def get_prompt_sync(name: str) -> Optional[str]:
    """
    Get prompt synchronously. Returns from cache or embedded defaults.
    Does NOT access database - use async load_prompt for DB access.
    """
    if name in _sync_cache:
        return _sync_cache[name]
    if name in _PROMPT_DEFAULTS:
        _sync_cache[name] = _PROMPT_DEFAULTS[name]
        return _sync_cache[name]
    return None


def _run_async(coro):
    """Run async function synchronously."""
    try:
        loop = asyncio.get_running_loop()
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)
