"""
Moral Geometry - A geometric framework for ethical reasoning in Vessels.

This module provides a multi-dimensional moral space where actions, decisions,
and agent behaviors are represented as vectors. Spectral analysis decomposes
moral positions into fundamental harmonics for deeper understanding.

Key Concepts:
- Moral Dimensions: Axes representing ethical values (harm/benefit, autonomy, justice, etc.)
- Moral Vectors: Positions in moral space representing stances or actions
- Moral Distance: Geometric distance between moral positions
- Spectral Decomposition: Eigenvalue analysis of moral stance matrices
- Moral Resonance: Alignment/dissonance detection between positions

Storage: All moral data is graph-native (FalkorDB + Graphiti)
Computation: Agent-delegated (no numpy/scipy imports - agents provide math)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import json
import math


# =============================================================================
# Moral Dimensions - The axes of moral space
# =============================================================================

class MoralDimension(str, Enum):
    """Fundamental dimensions of moral space."""

    # Consequentialist dimensions
    HARM_BENEFIT = "harm_benefit"          # -1 (harm) to +1 (benefit)
    INDIVIDUAL_COLLECTIVE = "individual_collective"  # Individual vs collective good
    SHORT_LONG_TERM = "short_long_term"    # Immediate vs long-term consequences

    # Deontological dimensions
    AUTONOMY = "autonomy"                  # Respect for agency
    JUSTICE = "justice"                    # Fairness and equity
    FIDELITY = "fidelity"                  # Keeping promises, loyalty
    TRUTH = "truth"                        # Honesty and transparency

    # Virtue dimensions
    COMPASSION = "compassion"              # Care and empathy
    COURAGE = "courage"                    # Moral bravery
    PRUDENCE = "prudence"                  # Practical wisdom
    TEMPERANCE = "temperance"              # Moderation and self-control

    # Relational dimensions
    RECIPROCITY = "reciprocity"            # Mutual exchange
    SANCTITY = "sanctity"                  # Purity, sacred values
    AUTHORITY = "authority"                # Legitimate hierarchy
    LIBERTY = "liberty"                    # Freedom from constraint

    @classmethod
    def all_dimensions(cls) -> list[str]:
        return [d.value for d in cls]

    @classmethod
    def dimension_count(cls) -> int:
        return len(cls)


# =============================================================================
# Moral Vector - A position in moral space
# =============================================================================

@dataclass
class MoralVector:
    """
    A vector in moral space representing a moral position.

    Each component is a value from -1.0 to +1.0 representing
    the position along that moral dimension.
    """

    id: str = ""
    name: str = ""
    description: str = ""

    # Core dimensional values
    components: dict[str, float] = field(default_factory=dict)

    # Metadata
    source_type: str = "action"  # action, decision, stance, agent, policy
    source_id: str = ""
    timestamp: str = ""

    # Computed properties (filled by spectral analysis)
    magnitude: float = 0.0
    dominant_dimension: str = ""
    spectral_signature: list[float] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if not self.components:
            # Initialize all dimensions to neutral (0.0)
            self.components = {d.value: 0.0 for d in MoralDimension}

    def set_dimension(self, dimension: MoralDimension | str, value: float) -> "MoralVector":
        """Set a dimension value (clamped to [-1, 1])."""
        dim_key = dimension.value if isinstance(dimension, MoralDimension) else dimension
        self.components[dim_key] = max(-1.0, min(1.0, value))
        return self

    def get_dimension(self, dimension: MoralDimension | str) -> float:
        """Get a dimension value."""
        dim_key = dimension.value if isinstance(dimension, MoralDimension) else dimension
        return self.components.get(dim_key, 0.0)

    def compute_magnitude(self) -> float:
        """Compute the magnitude (L2 norm) of the moral vector."""
        sum_sq = sum(v * v for v in self.components.values())
        self.magnitude = math.sqrt(sum_sq)
        return self.magnitude

    def find_dominant(self) -> str:
        """Find the dominant (highest absolute value) dimension."""
        if not self.components:
            return ""
        max_dim = max(self.components.items(), key=lambda x: abs(x[1]))
        self.dominant_dimension = max_dim[0]
        return self.dominant_dimension

    def to_list(self) -> list[float]:
        """Convert to ordered list (for spectral operations)."""
        return [self.components.get(d.value, 0.0) for d in MoralDimension]

    @classmethod
    def from_list(cls, values: list[float], **kwargs) -> "MoralVector":
        """Create from ordered list of values."""
        components = {}
        dims = list(MoralDimension)
        for i, v in enumerate(values[:len(dims)]):
            components[dims[i].value] = v
        return cls(components=components, **kwargs)

    def to_dict(self) -> dict:
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
    def from_dict(cls, data: dict) -> "MoralVector":
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


# =============================================================================
# Moral Distance - Measuring ethical difference
# =============================================================================

@dataclass
class MoralDistance:
    """Result of computing distance between moral vectors."""

    vector_a_id: str
    vector_b_id: str

    # Distance metrics
    euclidean: float = 0.0
    cosine_similarity: float = 0.0
    manhattan: float = 0.0

    # Dimensional breakdown
    dimension_deltas: dict[str, float] = field(default_factory=dict)
    max_divergence_dimension: str = ""

    # Interpretation
    alignment_score: float = 0.0  # 0 = opposed, 0.5 = orthogonal, 1 = aligned
    conflict_dimensions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
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


# =============================================================================
# Spectral Decomposition - Eigenvalue analysis of moral positions
# =============================================================================

@dataclass
class SpectralDecomposition:
    """
    Result of spectral analysis on moral vectors.

    Decomposes moral positions into principal components (eigenvalues/eigenvectors)
    to reveal fundamental moral modes and their relative strengths.
    """

    source_vectors: list[str]  # IDs of source vectors

    # Eigenvalue decomposition
    eigenvalues: list[float] = field(default_factory=list)
    eigenvectors: list[list[float]] = field(default_factory=list)

    # Principal components
    principal_components: int = 0
    variance_explained: list[float] = field(default_factory=list)
    cumulative_variance: list[float] = field(default_factory=list)

    # Moral harmonics (named principal components)
    harmonics: list[dict] = field(default_factory=list)  # [{name, strength, dimensions}]

    # Resonance analysis
    resonance_score: float = 0.0  # How well vectors resonate (0-1)
    dissonance_dimensions: list[str] = field(default_factory=list)

    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
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
    def from_dict(cls, data: dict) -> "SpectralDecomposition":
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


# =============================================================================
# Moral Trajectory - Path through moral space over time
# =============================================================================

@dataclass
class MoralTrajectory:
    """A path through moral space, tracking moral evolution over time."""

    id: str = ""
    name: str = ""
    entity_type: str = "agent"  # agent, action_sequence, policy
    entity_id: str = ""

    # Sequence of moral positions
    waypoints: list[MoralVector] = field(default_factory=list)

    # Trajectory analysis
    total_distance: float = 0.0
    net_displacement: float = 0.0
    drift_direction: dict[str, float] = field(default_factory=dict)  # Per-dimension drift

    # Stability analysis
    stability_score: float = 0.0  # How stable the moral position is
    oscillation_frequency: float = 0.0  # How often position changes direction

    def add_waypoint(self, vector: MoralVector) -> None:
        """Add a new waypoint to the trajectory."""
        self.waypoints.append(vector)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "waypoints": [w.to_dict() for w in self.waypoints],
            "total_distance": self.total_distance,
            "net_displacement": self.net_displacement,
            "drift_direction": self.drift_direction,
            "stability_score": self.stability_score,
            "oscillation_frequency": self.oscillation_frequency,
        }


# =============================================================================
# Moral Geometry Engine - Core computation (agent-delegated)
# =============================================================================

class MoralGeometryEngine:
    """
    Core engine for moral geometry calculations.

    IMPORTANT: This engine uses agent delegation for complex math.
    Instead of importing numpy/scipy, it delegates to a spectral agent
    that provides these capabilities. This is the A0 pattern:
    no imports, agents instead.
    """

    def __init__(self, agent: Any = None):
        """
        Initialize the moral geometry engine.

        Args:
            agent: The parent agent (used for delegation)
        """
        self.agent = agent
        self._spectral_agent = None

    # =========================================================================
    # Basic Geometry (no external dependencies)
    # =========================================================================

    def compute_distance(self, a: MoralVector, b: MoralVector) -> MoralDistance:
        """Compute the moral distance between two vectors."""
        result = MoralDistance(
            vector_a_id=a.id,
            vector_b_id=b.id,
        )

        # Compute dimension deltas
        sum_sq = 0.0
        sum_abs = 0.0
        dot_product = 0.0
        mag_a_sq = 0.0
        mag_b_sq = 0.0
        max_delta = 0.0
        max_delta_dim = ""
        conflicts = []

        for dim in MoralDimension:
            val_a = a.get_dimension(dim)
            val_b = b.get_dimension(dim)
            delta = val_b - val_a

            result.dimension_deltas[dim.value] = delta
            sum_sq += delta * delta
            sum_abs += abs(delta)
            dot_product += val_a * val_b
            mag_a_sq += val_a * val_a
            mag_b_sq += val_b * val_b

            if abs(delta) > max_delta:
                max_delta = abs(delta)
                max_delta_dim = dim.value

            # Conflict: opposite signs with significant magnitude
            if val_a * val_b < -0.25:  # Opposite directions
                conflicts.append(dim.value)

        # Euclidean distance
        result.euclidean = math.sqrt(sum_sq)

        # Manhattan distance
        result.manhattan = sum_abs

        # Cosine similarity
        mag_a = math.sqrt(mag_a_sq)
        mag_b = math.sqrt(mag_b_sq)
        if mag_a > 0 and mag_b > 0:
            result.cosine_similarity = dot_product / (mag_a * mag_b)
        else:
            result.cosine_similarity = 0.0

        # Alignment score (normalized cosine similarity to 0-1)
        result.alignment_score = (result.cosine_similarity + 1) / 2

        result.max_divergence_dimension = max_delta_dim
        result.conflict_dimensions = conflicts

        return result

    def compute_centroid(self, vectors: list[MoralVector]) -> MoralVector:
        """Compute the centroid (average) of multiple moral vectors."""
        if not vectors:
            return MoralVector()

        centroid = MoralVector(name="centroid", source_type="computed")
        n = len(vectors)

        for dim in MoralDimension:
            total = sum(v.get_dimension(dim) for v in vectors)
            centroid.set_dimension(dim, total / n)

        centroid.compute_magnitude()
        centroid.find_dominant()

        return centroid

    def normalize(self, vector: MoralVector) -> MoralVector:
        """Normalize a vector to unit length."""
        mag = vector.compute_magnitude()
        if mag == 0:
            return vector

        normalized = MoralVector(
            id=vector.id,
            name=vector.name,
            description=vector.description,
            source_type=vector.source_type,
            source_id=vector.source_id,
        )

        for dim in MoralDimension:
            normalized.set_dimension(dim, vector.get_dimension(dim) / mag)

        normalized.magnitude = 1.0
        normalized.find_dominant()

        return normalized

    # =========================================================================
    # Spectral Analysis (agent-delegated for complex math)
    # =========================================================================

    async def spectral_decompose(
        self,
        vectors: list[MoralVector],
        num_components: int = 5
    ) -> SpectralDecomposition:
        """
        Perform spectral decomposition on a set of moral vectors.

        This delegates to the spectral agent for eigenvalue computation
        (A0 pattern: agents instead of imports).
        """
        result = SpectralDecomposition(
            source_vectors=[v.id for v in vectors],
            principal_components=num_components,
        )

        if len(vectors) < 2:
            return result

        # Build covariance matrix (done locally - simple math)
        n_dims = MoralDimension.dimension_count()
        matrix = self._build_covariance_matrix(vectors)

        # Delegate eigenvalue computation to agent
        eigen_result = await self._delegate_eigenvalue_computation(matrix)

        if eigen_result:
            result.eigenvalues = eigen_result.get("eigenvalues", [])
            result.eigenvectors = eigen_result.get("eigenvectors", [])

            # Compute variance explained
            total_variance = sum(abs(e) for e in result.eigenvalues)
            if total_variance > 0:
                result.variance_explained = [
                    abs(e) / total_variance for e in result.eigenvalues[:num_components]
                ]
                cumulative = 0.0
                for v in result.variance_explained:
                    cumulative += v
                    result.cumulative_variance.append(cumulative)

            # Name the harmonics (principal moral modes)
            result.harmonics = self._name_harmonics(
                result.eigenvalues[:num_components],
                result.eigenvectors[:num_components]
            )

            # Compute resonance
            result.resonance_score = self._compute_resonance(vectors, result)
            result.dissonance_dimensions = self._find_dissonance(vectors, result)

        return result

    def _build_covariance_matrix(self, vectors: list[MoralVector]) -> list[list[float]]:
        """Build the covariance matrix from moral vectors."""
        n = len(vectors)
        dims = list(MoralDimension)
        d = len(dims)

        # Compute means
        means = {}
        for dim in dims:
            means[dim.value] = sum(v.get_dimension(dim) for v in vectors) / n

        # Build covariance matrix
        matrix = [[0.0] * d for _ in range(d)]

        for i, dim_i in enumerate(dims):
            for j, dim_j in enumerate(dims):
                cov = 0.0
                for v in vectors:
                    cov += (v.get_dimension(dim_i) - means[dim_i.value]) * \
                           (v.get_dimension(dim_j) - means[dim_j.value])
                matrix[i][j] = cov / (n - 1) if n > 1 else 0.0

        return matrix

    async def _delegate_eigenvalue_computation(
        self,
        matrix: list[list[float]]
    ) -> Optional[dict]:
        """
        Delegate eigenvalue computation to a subordinate agent.

        This is the A0 pattern: instead of importing numpy/scipy,
        we ask an agent to perform the computation.
        """
        if not self.agent:
            # Fallback: use power iteration for largest eigenvalue
            return self._power_iteration_eigenvalues(matrix, num_iterations=100)

        # Delegate to spectral computation agent
        try:
            from agent import Agent, UserMessage

            # Check for existing spectral agent
            spectral_agent = self.agent.get_data("spectral_agent")

            if spectral_agent is None:
                # Create subordinate agent for spectral computation
                from initialize import initialize_agent
                config = initialize_agent()
                config.profile = "vessels"  # Use vessels profile

                spectral_agent = Agent(
                    self.agent.number + 1,
                    config,
                    self.agent.context
                )
                spectral_agent.set_data(Agent.DATA_NAME_SUPERIOR, self.agent)
                self.agent.set_data("spectral_agent", spectral_agent)

            # Request eigenvalue computation
            request = {
                "task": "eigenvalue_decomposition",
                "matrix": matrix,
                "num_eigenvalues": min(5, len(matrix)),
            }

            message = f"""Compute eigenvalue decomposition for this covariance matrix.
Return JSON with 'eigenvalues' (list of floats, descending order) and
'eigenvectors' (list of lists, corresponding to eigenvalues).

Matrix: {json.dumps(matrix)}

Use power iteration or QR algorithm. Return only the JSON result."""

            spectral_agent.hist_add_user_message(UserMessage(message=message, attachments=[]))
            result_text = await spectral_agent.monologue()

            # Parse result
            # Find JSON in response
            start = result_text.find('{')
            end = result_text.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(result_text[start:end])

        except Exception as e:
            # Fallback to local computation
            pass

        return self._power_iteration_eigenvalues(matrix, num_iterations=100)

    def _power_iteration_eigenvalues(
        self,
        matrix: list[list[float]],
        num_iterations: int = 100
    ) -> dict:
        """
        Compute eigenvalues using power iteration (no external deps).

        This is the fallback when agent delegation is not available.
        """
        n = len(matrix)
        if n == 0:
            return {"eigenvalues": [], "eigenvectors": []}

        eigenvalues = []
        eigenvectors = []

        # Make a copy of matrix for deflation
        A = [row[:] for row in matrix]

        for _ in range(min(5, n)):  # Get top 5 eigenvalues
            # Initialize random vector
            v = [1.0 / math.sqrt(n)] * n

            eigenvalue = 0.0

            for _ in range(num_iterations):
                # Matrix-vector multiply
                Av = [sum(A[i][j] * v[j] for j in range(n)) for i in range(n)]

                # Compute eigenvalue (Rayleigh quotient)
                eigenvalue = sum(v[i] * Av[i] for i in range(n))

                # Normalize
                norm = math.sqrt(sum(x * x for x in Av))
                if norm < 1e-10:
                    break
                v = [x / norm for x in Av]

            if abs(eigenvalue) < 1e-10:
                break

            eigenvalues.append(eigenvalue)
            eigenvectors.append(v)

            # Deflate matrix
            for i in range(n):
                for j in range(n):
                    A[i][j] -= eigenvalue * v[i] * v[j]

        return {"eigenvalues": eigenvalues, "eigenvectors": eigenvectors}

    def _name_harmonics(
        self,
        eigenvalues: list[float],
        eigenvectors: list[list[float]]
    ) -> list[dict]:
        """Name the principal moral harmonics based on dominant dimensions."""
        dims = list(MoralDimension)
        harmonics = []

        harmonic_names = [
            "Primary Moral Mode",
            "Secondary Moral Mode",
            "Tertiary Moral Mode",
            "Quaternary Moral Mode",
            "Quinary Moral Mode",
        ]

        for i, (eigenvalue, eigenvector) in enumerate(zip(eigenvalues, eigenvectors)):
            if i >= len(harmonic_names):
                break

            # Find dominant dimensions in this eigenvector
            dim_weights = []
            for j, weight in enumerate(eigenvector):
                if j < len(dims):
                    dim_weights.append((dims[j].value, abs(weight), weight))

            # Sort by absolute weight
            dim_weights.sort(key=lambda x: x[1], reverse=True)

            # Top 3 dimensions define the harmonic
            top_dims = dim_weights[:3]

            harmonics.append({
                "name": harmonic_names[i],
                "strength": abs(eigenvalue),
                "dimensions": [
                    {"dimension": d[0], "weight": d[2]}
                    for d in top_dims
                ],
                "description": self._describe_harmonic(top_dims),
            })

        return harmonics

    def _describe_harmonic(self, dim_weights: list[tuple]) -> str:
        """Generate a human-readable description of a moral harmonic."""
        if not dim_weights:
            return "Undefined moral mode"

        primary = dim_weights[0]
        direction = "high" if primary[2] > 0 else "low"

        descriptions = {
            "harm_benefit": f"{direction} focus on outcomes/consequences",
            "autonomy": f"{direction} respect for individual agency",
            "justice": f"{direction} emphasis on fairness",
            "compassion": f"{direction} expression of care/empathy",
            "truth": f"{direction} commitment to honesty",
            "liberty": f"{direction} value of freedom",
            "reciprocity": f"{direction} mutual exchange emphasis",
            "prudence": f"{direction} practical wisdom applied",
        }

        return descriptions.get(
            primary[0],
            f"{direction} {primary[0].replace('_', ' ')} emphasis"
        )

    def _compute_resonance(
        self,
        vectors: list[MoralVector],
        decomposition: SpectralDecomposition
    ) -> float:
        """
        Compute resonance score: how well the vectors align in moral space.

        High resonance = vectors point in similar directions
        Low resonance = vectors are scattered/opposed
        """
        if len(vectors) < 2:
            return 1.0

        # Use the ratio of first eigenvalue to total
        if decomposition.variance_explained:
            return decomposition.variance_explained[0]

        # Fallback: average pairwise alignment
        total_alignment = 0.0
        count = 0
        for i, v1 in enumerate(vectors):
            for v2 in vectors[i+1:]:
                dist = self.compute_distance(v1, v2)
                total_alignment += dist.alignment_score
                count += 1

        return total_alignment / count if count > 0 else 0.5

    def _find_dissonance(
        self,
        vectors: list[MoralVector],
        decomposition: SpectralDecomposition
    ) -> list[str]:
        """Find dimensions where there is significant moral dissonance."""
        dims = list(MoralDimension)
        dissonant = []

        for dim in dims:
            values = [v.get_dimension(dim) for v in vectors]
            if not values:
                continue

            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)

            # High variance indicates dissonance
            if variance > 0.25:  # Threshold for significant variance
                dissonant.append(dim.value)

        return dissonant


# =============================================================================
# Graph Storage Integration
# =============================================================================

class MoralGeometryStore:
    """
    Graph-native storage for moral geometry data.

    Uses the Vessels GraphStore to persist moral vectors, trajectories,
    and spectral analyses as graph nodes/edges.
    """

    def __init__(self, graph_store: Any = None):
        """
        Initialize with a GraphStore instance.

        Args:
            graph_store: The GraphStore instance (from graph_store.py)
        """
        self._store = graph_store

    async def get_store(self):
        """Get or create the graph store."""
        if self._store is None:
            from python.helpers.graph_store import get_graph_store
            self._store = await get_graph_store()
        return self._store

    async def save_moral_vector(self, vector: MoralVector) -> str:
        """Save a moral vector to the graph."""
        from python.helpers import guids

        if not vector.id:
            vector.id = guids.generate_id(10)

        store = await self.get_store()

        content = json.dumps({
            "type": "moral_vector",
            "data": vector.to_dict(),
        })

        await store.save_content(
            f"moral/vectors/{vector.id}",
            content,
            content_type="moral_geometry"
        )

        return vector.id

    async def load_moral_vector(self, vector_id: str) -> Optional[MoralVector]:
        """Load a moral vector from the graph."""
        store = await self.get_store()
        content = await store.get_content(f"moral/vectors/{vector_id}")

        if content:
            data = json.loads(content)
            if data.get("type") == "moral_vector":
                return MoralVector.from_dict(data["data"])

        return None

    async def save_spectral_decomposition(
        self,
        decomposition: SpectralDecomposition,
        name: str = ""
    ) -> str:
        """Save a spectral decomposition to the graph."""
        from python.helpers import guids

        decomp_id = guids.generate_id(10)

        store = await self.get_store()

        content = json.dumps({
            "type": "spectral_decomposition",
            "name": name,
            "data": decomposition.to_dict(),
        })

        await store.save_content(
            f"moral/spectral/{decomp_id}",
            content,
            content_type="moral_geometry"
        )

        return decomp_id

    async def save_trajectory(self, trajectory: MoralTrajectory) -> str:
        """Save a moral trajectory to the graph."""
        from python.helpers import guids

        if not trajectory.id:
            trajectory.id = guids.generate_id(10)

        store = await self.get_store()

        content = json.dumps({
            "type": "moral_trajectory",
            "data": trajectory.to_dict(),
        })

        await store.save_content(
            f"moral/trajectories/{trajectory.id}",
            content,
            content_type="moral_geometry"
        )

        return trajectory.id

    async def search_moral_vectors(
        self,
        query: str,
        limit: int = 10
    ) -> list[MoralVector]:
        """Search for moral vectors using semantic search."""
        store = await self.get_store()

        results = await store.search_knowledge(
            query=f"moral vector {query}",
            limit=limit,
        )

        vectors = []
        for result in results:
            content = result.get("content", "")
            try:
                data = json.loads(content)
                if data.get("type") == "moral_vector":
                    vectors.append(MoralVector.from_dict(data["data"]))
            except:
                pass

        return vectors
