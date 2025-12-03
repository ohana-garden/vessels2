"""
Graphiti Integration for Spectral Analysis

This module provides the bridge between Vessels' GraphStore/Graphiti
backend and the spectral analysis functionality. It handles:
- Extracting graph structure from Graphiti episodes
- Building adjacency matrices from entity relationships
- Fetching semantic embeddings for nodes
- Combined spectral + semantic analysis
"""

from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
import asyncio
import numpy as np
from scipy.sparse import csr_matrix, coo_matrix

from python.analysis.spectral import (
    compute_laplacian,
    spectral_embedding,
    spectral_divergence,
    compute_fiedler,
    spectral_gap,
)
from python.analysis.temporal import (
    temporal_adjacency,
    sliding_window_spectrum,
)
from python.analysis.fusion import (
    hybrid_embedding,
    link_prediction_score,
    recommend_edges,
)
from python.analysis.cache import SpectralCache


@dataclass
class GraphSnapshot:
    """A snapshot of graph structure at a point in time."""
    nodes: List[str]  # Node identifiers
    node_index: Dict[str, int]  # ID -> index mapping
    edges: List[Tuple[int, int, float, float]]  # (src, tgt, timestamp, weight)
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SpectralAnalysisResult:
    """Results from spectral analysis of a graph snapshot."""
    eigenvalues: np.ndarray
    eigenvectors: np.ndarray
    fiedler_value: float
    spectral_gap: float
    n_components: int
    hybrid_embeddings: Optional[np.ndarray] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            'eigenvalues': self.eigenvalues.tolist(),
            'fiedler_value': self.fiedler_value,
            'spectral_gap': self.spectral_gap,
            'n_components': self.n_components,
            'timestamp': self.timestamp.isoformat(),
        }


class GraphitiSpectralAnalyzer:
    """
    Spectral analysis integration for Graphiti-based knowledge graphs.

    Provides methods to:
    - Extract graph structure from Graphiti
    - Compute spectral properties
    - Analyze temporal evolution
    - Combine semantic and structural embeddings
    """

    def __init__(
        self,
        graph_store=None,
        k: int = 20,
        half_life: float = 3600.0,
        cache_enabled: bool = True,
    ):
        """
        Args:
            graph_store: GraphStore instance (or None for lazy initialization).
            k: Default number of spectral components.
            half_life: Temporal decay half-life in seconds.
            cache_enabled: Whether to cache spectral decompositions.
        """
        self._graph_store = graph_store
        self.k = k
        self.half_life = half_life

        if cache_enabled:
            self.cache = SpectralCache(
                recompute_threshold=0.05,
                max_cache_entries=10,
            )
        else:
            self.cache = None

    async def _get_graph_store(self):
        """Lazy initialization of graph store."""
        if self._graph_store is None:
            from python.helpers.graph_store import get_graph_store
            self._graph_store = await get_graph_store()
        return self._graph_store

    async def get_graph_snapshot(
        self,
        group_id: Optional[str] = None,
        time_window: Optional[Tuple[datetime, datetime]] = None,
    ) -> GraphSnapshot:
        """
        Extract current graph structure from Graphiti.

        Args:
            group_id: Filter to specific group (e.g., memory area).
            time_window: Optional (start, end) datetime filter.

        Returns:
            GraphSnapshot with nodes and edges.
        """
        graph_store = await self._get_graph_store()

        # Query for entity nodes
        query = """
        MATCH (n:Entity)
        """
        if group_id:
            query += f" WHERE n.group_id = '{group_id}'"
        query += " RETURN n.uuid as id, n.name as name, n.created_at as created_at"

        results = await graph_store._driver.execute_query(query)

        nodes = []
        node_index = {}
        for idx, row in enumerate(results or []):
            node_id = row.get('id', row.get('name', f'node_{idx}'))
            nodes.append(node_id)
            node_index[node_id] = idx

        # Query for edges (relationships between entities)
        edge_query = """
        MATCH (a:Entity)-[r]->(b:Entity)
        """
        if group_id:
            edge_query += f" WHERE a.group_id = '{group_id}' AND b.group_id = '{group_id}'"
        edge_query += """
        RETURN a.uuid as source, b.uuid as target,
               r.created_at as timestamp, r.weight as weight
        """

        edge_results = await graph_store._driver.execute_query(edge_query)

        edges = []
        now = datetime.now()
        for row in edge_results or []:
            src_id = row.get('source')
            tgt_id = row.get('target')

            if src_id in node_index and tgt_id in node_index:
                src_idx = node_index[src_id]
                tgt_idx = node_index[tgt_id]

                # Parse timestamp
                ts_raw = row.get('timestamp')
                if isinstance(ts_raw, datetime):
                    ts = ts_raw.timestamp()
                elif isinstance(ts_raw, str):
                    try:
                        ts = datetime.fromisoformat(ts_raw).timestamp()
                    except (ValueError, TypeError):
                        ts = now.timestamp()
                else:
                    ts = now.timestamp()

                weight = float(row.get('weight', 1.0))

                # Apply time window filter
                if time_window:
                    start_ts = time_window[0].timestamp()
                    end_ts = time_window[1].timestamp()
                    if not (start_ts <= ts <= end_ts):
                        continue

                edges.append((src_idx, tgt_idx, ts, weight))

        return GraphSnapshot(
            nodes=nodes,
            node_index=node_index,
            edges=edges,
            timestamp=now,
            metadata={'group_id': group_id},
        )

    async def get_node_embeddings(
        self,
        nodes: List[str],
    ) -> np.ndarray:
        """
        Fetch semantic embeddings for nodes from Graphiti.

        Args:
            nodes: List of node identifiers.

        Returns:
            embeddings: Shape (n_nodes, embedding_dim).
        """
        graph_store = await self._get_graph_store()

        # Query for embeddings
        # Note: Graphiti stores embeddings on nodes
        query = """
        MATCH (n:Entity)
        WHERE n.uuid IN $node_ids
        RETURN n.uuid as id, n.name_embedding as embedding
        """

        # Execute query (this is a simplified version - actual implementation
        # depends on how Graphiti stores embeddings)
        embeddings = {}

        try:
            results = await graph_store._driver.execute_query(
                query,
                {'node_ids': nodes},
            )

            for row in results or []:
                node_id = row.get('id')
                emb = row.get('embedding')
                if emb is not None:
                    embeddings[node_id] = np.array(emb)

        except Exception:
            # Fallback: return zero embeddings
            pass

        # Build output matrix
        if embeddings:
            emb_dim = len(next(iter(embeddings.values())))
        else:
            emb_dim = 384  # Default embedding dimension

        output = np.zeros((len(nodes), emb_dim))
        for idx, node_id in enumerate(nodes):
            if node_id in embeddings:
                output[idx] = embeddings[node_id]

        return output

    async def analyze_current_state(
        self,
        group_id: Optional[str] = None,
        include_hybrid: bool = True,
        alpha: float = 0.5,
    ) -> SpectralAnalysisResult:
        """
        Perform full spectral analysis of current graph state.

        Args:
            group_id: Optional group filter.
            include_hybrid: Whether to compute hybrid embeddings.
            alpha: Weight for structural vs semantic in hybrid embedding.

        Returns:
            SpectralAnalysisResult with all computed properties.
        """
        import time

        # Get graph snapshot
        snapshot = await self.get_graph_snapshot(group_id=group_id)

        if not snapshot.nodes:
            # Empty graph
            return SpectralAnalysisResult(
                eigenvalues=np.array([]),
                eigenvectors=np.array([]).reshape(0, 0),
                fiedler_value=0.0,
                spectral_gap=0.0,
                n_components=0,
                timestamp=snapshot.timestamp,
            )

        n_nodes = len(snapshot.nodes)
        current_time = time.time()

        # Build temporally-weighted adjacency matrix
        adj = temporal_adjacency(
            edges=snapshot.edges,
            current_time=current_time,
            half_life=self.half_life,
            n_nodes=n_nodes,
        )

        # Compute Laplacian
        L = compute_laplacian(adj, normalized=True)

        # Get spectral embedding (with caching)
        k_actual = min(self.k, n_nodes - 1)
        if k_actual < 1:
            eigenvalues = np.array([])
            eigenvectors = np.zeros((n_nodes, 0))
        elif self.cache:
            eigenvalues, eigenvectors = self.cache.get_or_compute(
                L, k_actual, cache_key=f"graph_{group_id or 'default'}"
            )
        else:
            eigenvalues, eigenvectors = spectral_embedding(L, k_actual)

        # Compute derived properties
        fiedler_val = float(eigenvalues[0]) if len(eigenvalues) > 0 else 0.0
        spec_gap = (
            float(eigenvalues[1] - eigenvalues[0])
            if len(eigenvalues) > 1
            else 0.0
        )

        # Count components (zero eigenvalues)
        n_components = np.sum(np.abs(eigenvalues) < 1e-8) + 1

        # Hybrid embeddings
        hybrid_emb = None
        if include_hybrid and len(eigenvalues) > 0:
            semantic_vecs = await self.get_node_embeddings(snapshot.nodes)
            hybrid_emb = hybrid_embedding(
                semantic_vectors=semantic_vecs,
                spectral_coords=eigenvectors,
                alpha=alpha,
            )

        return SpectralAnalysisResult(
            eigenvalues=eigenvalues,
            eigenvectors=eigenvectors,
            fiedler_value=fiedler_val,
            spectral_gap=spec_gap,
            n_components=n_components,
            hybrid_embeddings=hybrid_emb,
            timestamp=snapshot.timestamp,
        )

    async def analyze_temporal_evolution(
        self,
        group_id: Optional[str] = None,
        window_size: float = 3600.0,
        step_size: float = 1800.0,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Analyze how spectral properties evolve over time.

        Args:
            group_id: Optional group filter.
            window_size: Window duration in seconds.
            step_size: Step between windows in seconds.
            start_time: Analysis start (Unix timestamp).
            end_time: Analysis end (Unix timestamp).

        Returns:
            List of spectral snapshots over time.
        """
        import time

        # Get graph snapshot with all edges
        snapshot = await self.get_graph_snapshot(group_id=group_id)

        if not snapshot.edges:
            return []

        n_nodes = len(snapshot.nodes)

        # Determine time range
        edge_times = [e[2] for e in snapshot.edges]
        if start_time is None:
            start_time = min(edge_times)
        if end_time is None:
            end_time = time.time()

        # Compute sliding window spectrum
        snapshots = sliding_window_spectrum(
            edges=snapshot.edges,
            window_size=window_size,
            step_size=step_size,
            start_time=start_time,
            end_time=end_time,
            k=self.k,
            n_nodes=n_nodes,
        )

        return snapshots

    async def compute_divergence(
        self,
        time1: datetime,
        time2: datetime,
        group_id: Optional[str] = None,
    ) -> float:
        """
        Compute spectral divergence between two time points.

        Measures how much the graph structure has changed.

        Args:
            time1: First time point.
            time2: Second time point.
            group_id: Optional group filter.

        Returns:
            Divergence measure (higher = more change).
        """
        snapshot = await self.get_graph_snapshot(group_id=group_id)

        if not snapshot.edges:
            return 0.0

        n_nodes = len(snapshot.nodes)

        # Build adjacency at time1
        adj1 = temporal_adjacency(
            edges=[e for e in snapshot.edges if e[2] <= time1.timestamp()],
            current_time=time1.timestamp(),
            half_life=self.half_life,
            n_nodes=n_nodes,
        )

        # Build adjacency at time2
        adj2 = temporal_adjacency(
            edges=[e for e in snapshot.edges if e[2] <= time2.timestamp()],
            current_time=time2.timestamp(),
            half_life=self.half_life,
            n_nodes=n_nodes,
        )

        L1 = compute_laplacian(adj1, normalized=True)
        L2 = compute_laplacian(adj2, normalized=True)

        return spectral_divergence(L1, L2, k=self.k)

    async def predict_links(
        self,
        candidate_pairs: Optional[List[Tuple[str, str]]] = None,
        group_id: Optional[str] = None,
        top_k: int = 10,
        alpha: float = 0.5,
    ) -> List[Tuple[str, str, float]]:
        """
        Predict likely new edges using spectral + semantic features.

        Args:
            candidate_pairs: Specific pairs to evaluate (or None for all non-edges).
            group_id: Optional group filter.
            top_k: Number of top predictions to return.
            alpha: Weight for structural vs semantic.

        Returns:
            List of (node1, node2, score) predictions.
        """
        import time

        snapshot = await self.get_graph_snapshot(group_id=group_id)

        if len(snapshot.nodes) < 2:
            return []

        n_nodes = len(snapshot.nodes)
        current_time = time.time()

        # Build adjacency
        adj = temporal_adjacency(
            edges=snapshot.edges,
            current_time=current_time,
            half_life=self.half_life,
            n_nodes=n_nodes,
        )

        # Get spectral embedding
        L = compute_laplacian(adj, normalized=True)
        k_actual = min(self.k, n_nodes - 1)

        if k_actual < 1:
            return []

        eigenvalues, eigenvectors = spectral_embedding(L, k_actual)

        # Get semantic embeddings
        semantic_vecs = await self.get_node_embeddings(snapshot.nodes)

        # Determine candidate pairs
        if candidate_pairs is None:
            # All non-existing edges
            existing = set(
                (min(e[0], e[1]), max(e[0], e[1]))
                for e in snapshot.edges
            )
            index_pairs = [
                (i, j)
                for i in range(n_nodes)
                for j in range(i + 1, n_nodes)
                if (i, j) not in existing
            ]
        else:
            # Map node IDs to indices
            index_pairs = []
            for n1, n2 in candidate_pairs:
                if n1 in snapshot.node_index and n2 in snapshot.node_index:
                    i, j = snapshot.node_index[n1], snapshot.node_index[n2]
                    index_pairs.append((min(i, j), max(i, j)))

        if not index_pairs:
            return []

        # Get recommendations
        recommendations = recommend_edges(
            candidate_pairs=index_pairs,
            spectral_coords=eigenvectors,
            eigenvalues=eigenvalues,
            semantic_vectors=semantic_vecs,
            alpha=alpha,
            top_k=top_k,
        )

        # Map back to node IDs
        id_recommendations = []
        for i, j, score in recommendations:
            id_recommendations.append((
                snapshot.nodes[i],
                snapshot.nodes[j],
                score,
            ))

        return id_recommendations

    async def find_similar_nodes(
        self,
        node_id: str,
        group_id: Optional[str] = None,
        top_k: int = 10,
        use_hybrid: bool = True,
        alpha: float = 0.5,
    ) -> List[Tuple[str, float]]:
        """
        Find nodes most similar to a given node.

        Uses spectral coordinates (and optionally semantic embeddings)
        to find structurally similar nodes.

        Args:
            node_id: ID of query node.
            group_id: Optional group filter.
            top_k: Number of similar nodes to return.
            use_hybrid: Whether to use hybrid (semantic + spectral) similarity.
            alpha: Weight for structural vs semantic.

        Returns:
            List of (node_id, similarity) pairs.
        """
        result = await self.analyze_current_state(
            group_id=group_id,
            include_hybrid=use_hybrid,
            alpha=alpha,
        )

        snapshot = await self.get_graph_snapshot(group_id=group_id)

        if node_id not in snapshot.node_index:
            return []

        query_idx = snapshot.node_index[node_id]
        n_nodes = len(snapshot.nodes)

        if use_hybrid and result.hybrid_embeddings is not None:
            embeddings = result.hybrid_embeddings
        else:
            embeddings = result.eigenvectors

        if embeddings.shape[0] == 0 or embeddings.shape[1] == 0:
            return []

        query_vec = embeddings[query_idx]
        query_norm = np.linalg.norm(query_vec)

        if query_norm == 0:
            return []

        # Compute similarities
        similarities = []
        for i in range(n_nodes):
            if i == query_idx:
                continue

            vec_i = embeddings[i]
            norm_i = np.linalg.norm(vec_i)

            if norm_i > 0:
                sim = np.dot(query_vec, vec_i) / (query_norm * norm_i)
                similarities.append((snapshot.nodes[i], float(sim)))

        # Sort by similarity descending
        similarities.sort(key=lambda x: -x[1])

        return similarities[:top_k]

    async def get_community_structure(
        self,
        group_id: Optional[str] = None,
        n_communities: int = 5,
    ) -> Dict[str, int]:
        """
        Detect community structure using spectral clustering.

        Args:
            group_id: Optional group filter.
            n_communities: Number of communities to detect.

        Returns:
            Dict mapping node_id -> community_index.
        """
        from python.analysis.spectral import spectral_clustering_labels
        import time

        snapshot = await self.get_graph_snapshot(group_id=group_id)

        if len(snapshot.nodes) < n_communities:
            # Each node is its own community
            return {node: i for i, node in enumerate(snapshot.nodes)}

        n_nodes = len(snapshot.nodes)
        current_time = time.time()

        # Build adjacency
        adj = temporal_adjacency(
            edges=snapshot.edges,
            current_time=current_time,
            half_life=self.half_life,
            n_nodes=n_nodes,
        )

        L = compute_laplacian(adj, normalized=True)

        try:
            labels = spectral_clustering_labels(L, n_communities)
        except Exception:
            # Fallback to trivial clustering
            labels = np.zeros(n_nodes, dtype=int)

        return {
            snapshot.nodes[i]: int(labels[i])
            for i in range(n_nodes)
        }


# =============================================================================
# Convenience Functions
# =============================================================================

async def analyze_graph(
    group_id: Optional[str] = None,
    k: int = 20,
    include_hybrid: bool = True,
) -> SpectralAnalysisResult:
    """
    Quick spectral analysis of current graph state.

    Args:
        group_id: Optional group filter.
        k: Number of spectral components.
        include_hybrid: Whether to include hybrid embeddings.

    Returns:
        SpectralAnalysisResult with analysis.
    """
    analyzer = GraphitiSpectralAnalyzer(k=k)
    return await analyzer.analyze_current_state(
        group_id=group_id,
        include_hybrid=include_hybrid,
    )


async def get_graph_metrics(
    group_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Get summary metrics for the knowledge graph.

    Returns connectivity measures, community counts, etc.
    """
    analyzer = GraphitiSpectralAnalyzer(k=10)
    result = await analyzer.analyze_current_state(
        group_id=group_id,
        include_hybrid=False,
    )

    snapshot = await analyzer.get_graph_snapshot(group_id=group_id)

    return {
        'n_nodes': len(snapshot.nodes),
        'n_edges': len(snapshot.edges),
        'fiedler_value': result.fiedler_value,
        'spectral_gap': result.spectral_gap,
        'n_components': result.n_components,
        'is_connected': result.n_components == 1,
        'timestamp': result.timestamp.isoformat(),
    }
