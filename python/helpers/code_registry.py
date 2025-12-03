"""
Code Registry - Graph-native code storage and execution for Vessels.

Code lives in the graph database. On first access, defaults are seeded.
No startup initialization required - lazy loading handles everything.

Usage:
    # Load code (auto-seeds from defaults if not in DB)
    module = await registry.load("moral_geometry")
    vector = module.MoralVector()
"""

import asyncio
import json
import types
import hashlib
from datetime import datetime, timezone
from typing import Any, Optional, Type, TypeVar
from dataclasses import dataclass, field

T = TypeVar('T')


# =============================================================================
# Embedded Code Defaults (seeded to DB on first access)
# =============================================================================

_DEFAULTS = {
    "moral_geometry": {
        "code_type": "module",
        "code": '''
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math

class MoralDimension(str, Enum):
    HARM_BENEFIT = "harm_benefit"
    INDIVIDUAL_COLLECTIVE = "individual_collective"
    SHORT_LONG_TERM = "short_long_term"
    AUTONOMY = "autonomy"
    JUSTICE = "justice"
    FIDELITY = "fidelity"
    TRUTH = "truth"
    COMPASSION = "compassion"
    COURAGE = "courage"
    PRUDENCE = "prudence"
    TEMPERANCE = "temperance"
    RECIPROCITY = "reciprocity"
    SANCTITY = "sanctity"
    AUTHORITY = "authority"
    LIBERTY = "liberty"

    @classmethod
    def all_dimensions(cls): return [d.value for d in cls]

@dataclass
class MoralVector:
    id: str = ""
    name: str = ""
    description: str = ""
    components: dict = field(default_factory=dict)
    source_type: str = "action"
    timestamp: str = ""
    magnitude: float = 0.0
    dominant_dimension: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.components:
            self.components = {d.value: 0.0 for d in MoralDimension}

    def set_dimension(self, dim, value):
        key = dim.value if hasattr(dim, "value") else dim
        self.components[key] = max(-1.0, min(1.0, float(value)))
        return self

    def get_dimension(self, dim):
        key = dim.value if hasattr(dim, "value") else dim
        return self.components.get(key, 0.0)

    def compute_magnitude(self):
        self.magnitude = math.sqrt(sum(v*v for v in self.components.values()))
        return self.magnitude

    def find_dominant(self):
        if self.components:
            self.dominant_dimension = max(self.components, key=lambda k: abs(self.components[k]))
        return self.dominant_dimension

    def to_dict(self):
        return {"id": self.id, "name": self.name, "components": self.components,
                "magnitude": self.magnitude, "dominant_dimension": self.dominant_dimension}

    @classmethod
    def from_dict(cls, d):
        return cls(id=d.get("id",""), name=d.get("name",""), components=d.get("components",{}))

@dataclass
class MoralDistance:
    euclidean: float = 0.0
    cosine_similarity: float = 0.0
    alignment_score: float = 0.0
    conflict_dimensions: list = field(default_factory=list)

def compute_distance(a, b):
    ca = a.components if hasattr(a, "components") else a.get("components", {})
    cb = b.components if hasattr(b, "components") else b.get("components", {})
    dims = set(ca) | set(cb)
    sum_sq = sum((ca.get(d,0) - cb.get(d,0))**2 for d in dims)
    dot = sum(ca.get(d,0) * cb.get(d,0) for d in dims)
    ma = math.sqrt(sum(v*v for v in ca.values()))
    mb = math.sqrt(sum(v*v for v in cb.values()))
    cos = dot/(ma*mb) if ma and mb else 0
    conflicts = [d for d in dims if ca.get(d,0) * cb.get(d,0) < -0.25]
    return MoralDistance(euclidean=math.sqrt(sum_sq), cosine_similarity=cos,
                         alignment_score=(cos+1)/2, conflict_dimensions=conflicts)
''',
    },
    "spectral": {
        "code_type": "agent_capability",
        "code": '''
import math

def eigenvalues(matrix, n=5, iters=100):
    """Power iteration eigenvalue decomposition (no numpy)."""
    size = len(matrix)
    if not size: return {"eigenvalues": [], "eigenvectors": []}
    A = [row[:] for row in matrix]
    vals, vecs = [], []
    for _ in range(min(n, size)):
        v = [1/math.sqrt(size)] * size
        ev = 0
        for _ in range(iters):
            Av = [sum(A[i][j]*v[j] for j in range(size)) for i in range(size)]
            ev = sum(v[i]*Av[i] for i in range(size))
            norm = math.sqrt(sum(x*x for x in Av))
            if norm < 1e-10: break
            v = [x/norm for x in Av]
        if abs(ev) < 1e-10: break
        vals.append(ev)
        vecs.append(v)
        for i in range(size):
            for j in range(size):
                A[i][j] -= ev * v[i] * v[j]
    return {"eigenvalues": vals, "eigenvectors": vecs}

def covariance(data):
    if not data or not data[0]: return []
    n, m = len(data), len(data[0])
    means = [sum(data[i][j] for i in range(n))/n for j in range(m)]
    return [[sum((data[k][i]-means[i])*(data[k][j]-means[j]) for k in range(n))/(n-1 if n>1 else 1)
             for j in range(m)] for i in range(m)]

def pca(data, components=2):
    cov = covariance(data)
    result = eigenvalues(cov, components)
    total = sum(result["eigenvalues"]) or 1
    return {"components": result["eigenvectors"][:components],
            "variance_explained": [e/total for e in result["eigenvalues"][:components]]}
''',
    },
}


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
    """Graph-native code registry. Auto-seeds defaults on first access."""

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
        """Load module from graph. Seeds from defaults if missing."""
        if name in self._cache:
            return self._cache[name]

        entry = await self._load_entry(name)

        # Auto-seed from defaults if not in DB
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
                try:
                    data = json.loads(content)
                    if data.get("type") == "code_registry":
                        entry = CodeEntry.from_dict(data["entry"])
                        self._entries[name] = entry
                        return entry
                except json.JSONDecodeError:
                    pass
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
