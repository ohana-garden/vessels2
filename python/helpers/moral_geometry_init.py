"""
Moral Geometry Initialization - Registers code in graph database.

This module registers the moral geometry and spectral analysis code
into the graph database. The code is stored as strings and loaded
dynamically at runtime via the CodeRegistry.

Call initialize_moral_geometry() during application startup.
"""

import asyncio
from typing import Optional


# =============================================================================
# Moral Geometry Code (stored in graph, not as file)
# =============================================================================

MORAL_GEOMETRY_CODE = '''
"""
Moral Geometry - A geometric framework for ethical reasoning.

This code is stored in the graph database and loaded dynamically.
All data is graph-native (FalkorDB + Graphiti).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import math


class MoralDimension(str, Enum):
    """Fundamental dimensions of moral space."""
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
    def all_dimensions(cls):
        return [d.value for d in cls]

    @classmethod
    def dimension_count(cls):
        return len(cls)


@dataclass
class MoralVector:
    """A vector in moral space representing a moral position."""
    id: str = ""
    name: str = ""
    description: str = ""
    components: dict = field(default_factory=dict)
    source_type: str = "action"
    source_id: str = ""
    timestamp: str = ""
    magnitude: float = 0.0
    dominant_dimension: str = ""
    spectral_signature: list = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.components:
            self.components = {d.value: 0.0 for d in MoralDimension}

    def set_dimension(self, dimension, value):
        dim_key = dimension.value if isinstance(dimension, MoralDimension) else dimension
        self.components[dim_key] = max(-1.0, min(1.0, float(value)))
        return self

    def get_dimension(self, dimension):
        dim_key = dimension.value if isinstance(dimension, MoralDimension) else dimension
        return self.components.get(dim_key, 0.0)

    def compute_magnitude(self):
        self.magnitude = math.sqrt(sum(v * v for v in self.components.values()))
        return self.magnitude

    def find_dominant(self):
        if self.components:
            max_dim = max(self.components.items(), key=lambda x: abs(x[1]))
            self.dominant_dimension = max_dim[0]
        return self.dominant_dimension

    def to_list(self):
        return [self.components.get(d.value, 0.0) for d in MoralDimension]

    @classmethod
    def from_list(cls, values, **kwargs):
        components = {}
        dims = list(MoralDimension)
        for i, v in enumerate(values[:len(dims)]):
            components[dims[i].value] = v
        return cls(components=components, **kwargs)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "components": self.components,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "timestamp": self.timestamp,
            "magnitude": self.magnitude,
            "dominant_dimension": self.dominant_dimension,
            "spectral_signature": self.spectral_signature,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            description=data.get("description", ""),
            components=data.get("components", {}),
            source_type=data.get("source_type", "action"),
            source_id=data.get("source_id", ""),
            timestamp=data.get("timestamp", ""),
            magnitude=data.get("magnitude", 0.0),
            dominant_dimension=data.get("dominant_dimension", ""),
            spectral_signature=data.get("spectral_signature", []),
        )


@dataclass
class MoralDistance:
    """Distance between moral vectors."""
    vector_a_id: str
    vector_b_id: str
    euclidean: float = 0.0
    cosine_similarity: float = 0.0
    manhattan: float = 0.0
    dimension_deltas: dict = field(default_factory=dict)
    max_divergence_dimension: str = ""
    alignment_score: float = 0.0
    conflict_dimensions: list = field(default_factory=list)

    def to_dict(self):
        return {
            "vector_a_id": self.vector_a_id,
            "vector_b_id": self.vector_b_id,
            "euclidean": self.euclidean,
            "cosine_similarity": self.cosine_similarity,
            "manhattan": self.manhattan,
            "dimension_deltas": self.dimension_deltas,
            "max_divergence_dimension": self.max_divergence_dimension,
            "alignment_score": self.alignment_score,
            "conflict_dimensions": self.conflict_dimensions,
        }


@dataclass
class SpectralDecomposition:
    """Spectral analysis of moral vectors."""
    source_vectors: list = field(default_factory=list)
    eigenvalues: list = field(default_factory=list)
    eigenvectors: list = field(default_factory=list)
    principal_components: int = 0
    variance_explained: list = field(default_factory=list)
    cumulative_variance: list = field(default_factory=list)
    harmonics: list = field(default_factory=list)
    resonance_score: float = 0.0
    dissonance_dimensions: list = field(default_factory=list)
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return {
            "source_vectors": self.source_vectors,
            "eigenvalues": self.eigenvalues,
            "eigenvectors": self.eigenvectors,
            "principal_components": self.principal_components,
            "variance_explained": self.variance_explained,
            "cumulative_variance": self.cumulative_variance,
            "harmonics": self.harmonics,
            "resonance_score": self.resonance_score,
            "dissonance_dimensions": self.dissonance_dimensions,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            source_vectors=data.get("source_vectors", []),
            eigenvalues=data.get("eigenvalues", []),
            eigenvectors=data.get("eigenvectors", []),
            principal_components=data.get("principal_components", 0),
            variance_explained=data.get("variance_explained", []),
            cumulative_variance=data.get("cumulative_variance", []),
            harmonics=data.get("harmonics", []),
            resonance_score=data.get("resonance_score", 0.0),
            dissonance_dimensions=data.get("dissonance_dimensions", []),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class MoralTrajectory:
    """Track moral evolution over time."""
    id: str = ""
    name: str = ""
    entity_type: str = "agent"
    entity_id: str = ""
    waypoints: list = field(default_factory=list)
    total_distance: float = 0.0
    net_displacement: float = 0.0
    drift_direction: dict = field(default_factory=dict)
    stability_score: float = 0.0
    oscillation_frequency: float = 0.0

    def add_waypoint(self, vector):
        self.waypoints.append(vector)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "waypoints": [w.to_dict() if hasattr(w, 'to_dict') else w for w in self.waypoints],
            "total_distance": self.total_distance,
            "net_displacement": self.net_displacement,
            "drift_direction": self.drift_direction,
            "stability_score": self.stability_score,
            "oscillation_frequency": self.oscillation_frequency,
        }
'''


# =============================================================================
# Spectral Agent Code (agent-based computation, replaces numpy/scipy)
# =============================================================================

SPECTRAL_AGENT_CODE = '''
"""
Spectral Agent - Agent-based spectral analysis.

Provides eigenvalue/eigenvector computation through agent delegation.
Replaces numpy/scipy imports with agent capabilities.
"""

from dataclasses import dataclass
import json
import math


@dataclass
class SpectralRequest:
    """Request for spectral computation."""
    operation: str
    data: list
    params: dict

    def to_prompt(self):
        prompts = {
            "eigenvalues": self._eigenvalue_prompt,
            "covariance": self._covariance_prompt,
        }
        generator = prompts.get(self.operation, self._generic_prompt)
        return generator()

    def _eigenvalue_prompt(self):
        return f"""Compute eigenvalue decomposition.
Matrix: {json.dumps(self.data)}
Return JSON: {{"eigenvalues": [...], "eigenvectors": [[...], ...]}}"""

    def _covariance_prompt(self):
        return f"""Compute covariance matrix.
Data: {json.dumps(self.data)}
Return JSON: {{"covariance": [[...]]}}"""

    def _generic_prompt(self):
        return f"""Perform: {self.operation}
Data: {json.dumps(self.data)}
Params: {json.dumps(self.params)}"""


def power_iteration_eigenvalues(matrix, num_eigenvalues=5, iterations=100):
    """Compute eigenvalues using power iteration (no numpy)."""
    n = len(matrix)
    if n == 0:
        return {"eigenvalues": [], "eigenvectors": []}

    eigenvalues = []
    eigenvectors = []
    A = [row[:] for row in matrix]

    for _ in range(min(num_eigenvalues, n)):
        v = [1.0 / math.sqrt(n)] * n
        eigenvalue = 0.0

        for _ in range(iterations):
            Av = [sum(A[i][j] * v[j] for j in range(n)) for i in range(n)]
            eigenvalue = sum(v[i] * Av[i] for i in range(n))
            norm = math.sqrt(sum(x * x for x in Av))
            if norm < 1e-10:
                break
            v = [x / norm for x in Av]

        if abs(eigenvalue) < 1e-10:
            break

        eigenvalues.append(eigenvalue)
        eigenvectors.append(v)

        for i in range(n):
            for j in range(n):
                A[i][j] -= eigenvalue * v[i] * v[j]

    return {"eigenvalues": eigenvalues, "eigenvectors": eigenvectors}


def compute_covariance(data):
    """Compute covariance matrix."""
    if not data or not data[0]:
        return {"covariance": []}

    n_samples = len(data)
    n_features = len(data[0])

    means = [sum(data[i][j] for i in range(n_samples)) / n_samples for j in range(n_features)]

    cov = [[0.0] * n_features for _ in range(n_features)]
    for i in range(n_features):
        for j in range(n_features):
            c = sum((data[k][i] - means[i]) * (data[k][j] - means[j]) for k in range(n_samples))
            cov[i][j] = c / (n_samples - 1) if n_samples > 1 else 0.0

    return {"covariance": cov}


def compute_pca(data, n_components=2):
    """Simple PCA via covariance eigendecomposition."""
    cov_result = compute_covariance(data)
    cov = cov_result["covariance"]

    eigen_result = power_iteration_eigenvalues(cov, n_components, 100)
    eigenvalues = eigen_result["eigenvalues"]
    eigenvectors = eigen_result["eigenvectors"]

    total_var = sum(eigenvalues) if eigenvalues else 1.0

    n_samples = len(data)
    n_features = len(data[0]) if data else 0

    means = [sum(data[i][j] for i in range(n_samples)) / n_samples for j in range(n_features)]
    centered = [[data[i][j] - means[j] for j in range(n_features)] for i in range(n_samples)]

    transformed = []
    for sample in centered:
        projected = []
        for component in eigenvectors[:n_components]:
            proj = sum(sample[i] * component[i] for i in range(min(len(sample), len(component))))
            projected.append(proj)
        transformed.append(projected)

    return {
        "components": eigenvectors[:n_components],
        "explained_variance": [ev / total_var for ev in eigenvalues[:n_components]] if total_var > 0 else [],
        "transformed": transformed,
    }
'''


# =============================================================================
# Moral Geometry Engine Code
# =============================================================================

MORAL_ENGINE_CODE = '''
"""
Moral Geometry Engine - Core computation.

Uses agent delegation for complex math (A0 pattern).
"""

import math


class MoralGeometryEngine:
    """Engine for moral geometry calculations."""

    def __init__(self, agent=None):
        self.agent = agent

    def compute_distance(self, a, b):
        """Compute moral distance between two vectors."""
        # Import from registry (loaded at runtime)
        registry = __registry__

        result = {
            "vector_a_id": a.id if hasattr(a, 'id') else "",
            "vector_b_id": b.id if hasattr(b, 'id') else "",
            "euclidean": 0.0,
            "cosine_similarity": 0.0,
            "manhattan": 0.0,
            "dimension_deltas": {},
            "max_divergence_dimension": "",
            "alignment_score": 0.0,
            "conflict_dimensions": [],
        }

        sum_sq = 0.0
        sum_abs = 0.0
        dot_product = 0.0
        mag_a_sq = 0.0
        mag_b_sq = 0.0
        max_delta = 0.0
        max_delta_dim = ""
        conflicts = []

        components_a = a.components if hasattr(a, 'components') else a.get('components', {})
        components_b = b.components if hasattr(b, 'components') else b.get('components', {})

        all_dims = set(components_a.keys()) | set(components_b.keys())

        for dim in all_dims:
            val_a = components_a.get(dim, 0.0)
            val_b = components_b.get(dim, 0.0)
            delta = val_b - val_a

            result["dimension_deltas"][dim] = delta
            sum_sq += delta * delta
            sum_abs += abs(delta)
            dot_product += val_a * val_b
            mag_a_sq += val_a * val_a
            mag_b_sq += val_b * val_b

            if abs(delta) > max_delta:
                max_delta = abs(delta)
                max_delta_dim = dim

            if val_a * val_b < -0.25:
                conflicts.append(dim)

        result["euclidean"] = math.sqrt(sum_sq)
        result["manhattan"] = sum_abs

        mag_a = math.sqrt(mag_a_sq)
        mag_b = math.sqrt(mag_b_sq)
        if mag_a > 0 and mag_b > 0:
            result["cosine_similarity"] = dot_product / (mag_a * mag_b)

        result["alignment_score"] = (result["cosine_similarity"] + 1) / 2
        result["max_divergence_dimension"] = max_delta_dim
        result["conflict_dimensions"] = conflicts

        return result

    def compute_centroid(self, vectors):
        """Compute centroid of moral vectors."""
        if not vectors:
            return {}

        n = len(vectors)
        centroid = {}

        # Get all dimensions
        all_dims = set()
        for v in vectors:
            components = v.components if hasattr(v, 'components') else v.get('components', {})
            all_dims.update(components.keys())

        for dim in all_dims:
            total = 0.0
            for v in vectors:
                components = v.components if hasattr(v, 'components') else v.get('components', {})
                total += components.get(dim, 0.0)
            centroid[dim] = total / n

        return centroid

    async def spectral_decompose(self, vectors, num_components=5):
        """Perform spectral decomposition on moral vectors."""
        # Load spectral code from registry
        spectral = await __registry__.load("spectral_agent")

        if len(vectors) < 2:
            return {
                "source_vectors": [v.id if hasattr(v, 'id') else "" for v in vectors],
                "eigenvalues": [],
                "eigenvectors": [],
                "principal_components": num_components,
                "variance_explained": [],
                "harmonics": [],
                "resonance_score": 1.0 if vectors else 0.0,
            }

        # Build data matrix
        data = []
        for v in vectors:
            components = v.components if hasattr(v, 'components') else v.get('components', {})
            row = list(components.values())
            data.append(row)

        # Compute PCA
        pca_result = spectral.compute_pca(data, num_components)

        return {
            "source_vectors": [v.id if hasattr(v, 'id') else "" for v in vectors],
            "eigenvalues": pca_result.get("explained_variance", []),
            "eigenvectors": pca_result.get("components", []),
            "principal_components": num_components,
            "variance_explained": pca_result.get("explained_variance", []),
            "harmonics": [],
            "resonance_score": pca_result.get("explained_variance", [0])[0] if pca_result.get("explained_variance") else 0.5,
        }
'''


# =============================================================================
# Tool Code (loaded from graph, provides agent interface)
# =============================================================================

MORAL_TOOL_CODE = '''
"""
Moral Geometry Tool - Agent tool for moral space operations.

This code is stored in the graph and loaded dynamically.
"""

import json


class MoralGeometryTool:
    """Tool for moral geometry operations."""

    def __init__(self, agent):
        self.agent = agent

    async def execute(self, method="evaluate", **kwargs):
        handlers = {
            "create_vector": self._create_vector,
            "evaluate": self._evaluate,
            "distance": self._distance,
            "list_dimensions": self._list_dimensions,
        }

        handler = handlers.get(method)
        if not handler:
            return {"error": f"Unknown method: {method}"}

        return await handler(**kwargs)

    async def _create_vector(self, **kwargs):
        # Load moral geometry from registry
        mg = await __registry__.load("moral_geometry")

        name = kwargs.get("name", "")
        dimensions = kwargs.get("dimensions", {})

        vector = mg.MoralVector(name=name, source_type="action")
        for dim, value in dimensions.items():
            vector.set_dimension(dim, float(value))

        vector.compute_magnitude()
        vector.find_dominant()

        return {
            "status": "created",
            "vector": vector.to_dict(),
        }

    async def _evaluate(self, **kwargs):
        mg = await __registry__.load("moral_geometry")

        action = kwargs.get("action", "")

        vector = mg.MoralVector(
            name=f"eval_{action[:30]}",
            description=action,
            source_type="action",
        )

        # Simple keyword-based evaluation
        action_lower = action.lower()

        harm_words = ["harm", "hurt", "damage", "destroy"]
        benefit_words = ["help", "heal", "save", "protect"]

        harm_count = sum(1 for w in harm_words if w in action_lower)
        benefit_count = sum(1 for w in benefit_words if w in action_lower)

        if harm_count + benefit_count > 0:
            vector.set_dimension("harm_benefit", (benefit_count - harm_count) / (harm_count + benefit_count))

        vector.compute_magnitude()
        vector.find_dominant()

        return {
            "action": action,
            "vector": vector.to_dict(),
        }

    async def _distance(self, **kwargs):
        mg = await __registry__.load("moral_geometry")
        engine_mod = await __registry__.load("moral_engine")

        vec_a_data = kwargs.get("vector_a", {})
        vec_b_data = kwargs.get("vector_b", {})

        vector_a = mg.MoralVector.from_dict(vec_a_data) if isinstance(vec_a_data, dict) else vec_a_data
        vector_b = mg.MoralVector.from_dict(vec_b_data) if isinstance(vec_b_data, dict) else vec_b_data

        engine = engine_mod.MoralGeometryEngine(self.agent)
        distance = engine.compute_distance(vector_a, vector_b)

        return distance

    async def _list_dimensions(self, **kwargs):
        mg = await __registry__.load("moral_geometry")
        return {"dimensions": mg.MoralDimension.all_dimensions()}
'''


SPECTRAL_TOOL_CODE = '''
"""
Spectral Analysis Tool - Agent tool for spectral operations.

Provides eigenvalue, PCA, and related operations without numpy.
"""

import json


class SpectralAnalyzeTool:
    """Tool for spectral analysis."""

    def __init__(self, agent):
        self.agent = agent

    async def execute(self, method="eigenvalues", **kwargs):
        handlers = {
            "eigenvalues": self._eigenvalues,
            "pca": self._pca,
            "covariance": self._covariance,
        }

        handler = handlers.get(method)
        if not handler:
            return {"error": f"Unknown method: {method}"}

        return await handler(**kwargs)

    async def _eigenvalues(self, **kwargs):
        spectral = await __registry__.load("spectral_agent")

        matrix = kwargs.get("matrix", [])
        num_eigenvalues = kwargs.get("num_eigenvalues", 5)

        result = spectral.power_iteration_eigenvalues(matrix, num_eigenvalues)
        return result

    async def _pca(self, **kwargs):
        spectral = await __registry__.load("spectral_agent")

        data = kwargs.get("data", [])
        n_components = kwargs.get("n_components", 2)

        result = spectral.compute_pca(data, n_components)
        return result

    async def _covariance(self, **kwargs):
        spectral = await __registry__.load("spectral_agent")

        data = kwargs.get("data", [])
        result = spectral.compute_covariance(data)
        return result
'''


# =============================================================================
# Initialization Function
# =============================================================================

async def initialize_moral_geometry():
    """
    Initialize moral geometry by registering code in the graph database.

    Call this during application startup.
    """
    from python.helpers.code_registry import get_registry
    from python.helpers.print_style import PrintStyle

    PrintStyle.standard("Initializing Moral Geometry (code in DB)...")

    registry = await get_registry()

    # Register core modules
    await registry.register(
        name="moral_geometry",
        code=MORAL_GEOMETRY_CODE,
        code_type="module",
        metadata={"description": "Core moral geometry classes"}
    )

    await registry.register(
        name="spectral_agent",
        code=SPECTRAL_AGENT_CODE,
        code_type="agent_capability",
        metadata={
            "capability_type": "spectral_analysis",
            "description": "Eigenvalue/PCA computation (replaces numpy)"
        }
    )

    await registry.register(
        name="moral_engine",
        code=MORAL_ENGINE_CODE,
        code_type="module",
        dependencies=["moral_geometry", "spectral_agent"],
        metadata={"description": "Moral geometry computation engine"}
    )

    # Register tools
    await registry.register_tool(
        name="moral_geometry_tool",
        code=MORAL_TOOL_CODE,
        description="Tool for moral space operations",
        methods=["create_vector", "evaluate", "distance", "list_dimensions"]
    )

    await registry.register_tool(
        name="spectral_analyze_tool",
        code=SPECTRAL_TOOL_CODE,
        description="Tool for spectral analysis",
        methods=["eigenvalues", "pca", "covariance"]
    )

    PrintStyle.standard("Moral Geometry initialized in graph database")

    return True


# Synchronous wrapper for initialization
def initialize_moral_geometry_sync():
    """Synchronous wrapper for initialize_moral_geometry."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(initialize_moral_geometry())
