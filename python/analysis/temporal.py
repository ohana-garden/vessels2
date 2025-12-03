"""
Temporal Analysis Patterns for Evolving Graphs

This module provides methods for analyzing how graph structure changes
over time, including:
- Temporal adjacency with decay weighting
- Perturbation-based eigenvalue updates
- Sliding window spectrum analysis
- Temporal motif detection
"""

from typing import List, Tuple, Dict, Optional, Union, Callable
from dataclasses import dataclass
import numpy as np
from scipy.sparse import csr_matrix, coo_matrix, issparse
from scipy.sparse.linalg import eigsh


@dataclass
class TemporalEdge:
    """An edge with temporal information."""
    source: int
    target: int
    timestamp: float
    weight: float = 1.0
    metadata: Optional[Dict] = None


def temporal_adjacency(
    edges: List[Tuple[int, int, float, float]],
    current_time: float,
    half_life: float,
    n_nodes: Optional[int] = None,
    threshold: float = 1e-6,
    symmetric: bool = True,
) -> csr_matrix:
    """
    Build adjacency matrix with exponential decay on older edges.

    Recent edges have higher weight, older edges decay exponentially.
    This reflects the intuition that recent relationships are more
    relevant for current graph structure.

    Args:
        edges: List of (source, target, timestamp, weight) tuples.
        current_time: Reference time for decay computation.
        half_life: Decay half-life (same units as timestamps).
                  After half_life time units, edge weight is halved.
        n_nodes: Number of nodes (inferred from edges if not provided).
        threshold: Minimum weight threshold; edges below this are dropped
                  for sparsity.
        symmetric: If True, create symmetric adjacency (undirected graph).

    Returns:
        weighted_adj: Sparse adjacency matrix with temporal weighting.

    Example:
        >>> edges = [(0, 1, 100.0, 1.0), (1, 2, 90.0, 1.0), (0, 2, 50.0, 1.0)]
        >>> adj = temporal_adjacency(edges, current_time=100.0, half_life=25.0)
        >>> # Edge (0,1) at t=100: weight=1.0 (no decay)
        >>> # Edge (1,2) at t=90: weight~0.76 (10 time units old)
        >>> # Edge (0,2) at t=50: weight=0.25 (50 time units = 2 half-lives)
    """
    if not edges:
        n = n_nodes or 0
        return csr_matrix((n, n))

    decay_factor = np.log(2) / half_life

    # Compute decayed weights
    rows, cols, weights = [], [], []

    for src, tgt, ts, w in edges:
        age = current_time - ts
        if age < 0:
            # Future edges (shouldn't happen, but handle gracefully)
            age = 0

        decayed_weight = w * np.exp(-decay_factor * age)

        if decayed_weight >= threshold:
            rows.append(src)
            cols.append(tgt)
            weights.append(decayed_weight)

            if symmetric and src != tgt:
                rows.append(tgt)
                cols.append(src)
                weights.append(decayed_weight)

    # Determine matrix size
    if n_nodes is not None:
        n = n_nodes
    elif rows:
        n = max(max(rows), max(cols)) + 1
    else:
        n = 0

    # Build sparse matrix
    adj = coo_matrix(
        (weights, (rows, cols)),
        shape=(n, n),
    ).tocsr()

    return adj


def perturb_eigenvalues(
    eigenvectors: np.ndarray,
    eigenvalues: np.ndarray,
    delta_L: Union[np.ndarray, csr_matrix],
) -> np.ndarray:
    """
    First-order approximation of eigenvalue change after Laplacian modification.

    Uses perturbation theory to approximate new eigenvalues without
    full recomputation. Efficient for small graph updates (edge additions/removals).

    Args:
        eigenvectors: Current eigenvectors, shape (n_nodes, k).
        eigenvalues: Current eigenvalues, shape (k,).
        delta_L: Change in Laplacian (typically rank-2 for single edge change).

    Returns:
        new_eigenvalues: Approximate eigenvalues after perturbation.

    Notes:
        - Accuracy degrades for large perturbations
        - Best for single edge additions/removals
        - Does not update eigenvectors (would require second-order terms)
    """
    if issparse(delta_L):
        delta_L = delta_L.toarray()

    # First-order perturbation: delta_lambda_i = v_i^T @ delta_L @ v_i
    delta_eigs = np.array([
        v.T @ delta_L @ v for v in eigenvectors.T
    ])

    return eigenvalues + delta_eigs


def compute_laplacian_delta_for_edge(
    n_nodes: int,
    edge: Tuple[int, int],
    weight_change: float,
    normalized: bool = True,
    current_degrees: Optional[np.ndarray] = None,
) -> csr_matrix:
    """
    Compute the change in Laplacian for a single edge modification.

    Args:
        n_nodes: Number of nodes in the graph.
        edge: (source, target) node indices.
        weight_change: Positive for edge addition, negative for removal.
        normalized: If True, compute change for normalized Laplacian.
        current_degrees: Current degree sequence (required for normalized).

    Returns:
        delta_L: Sparse matrix representing change in Laplacian.

    Notes:
        For unnormalized Laplacian, edge (i,j) change affects:
        - L[i,i] and L[j,j] by +weight_change (degree increase)
        - L[i,j] and L[j,i] by -weight_change (adjacency)
    """
    i, j = edge
    rows, cols, data = [], [], []

    if not normalized:
        # Unnormalized: simple update
        # Diagonal entries increase by weight change
        rows.extend([i, j])
        cols.extend([i, j])
        data.extend([weight_change, weight_change])

        # Off-diagonal entries decrease by weight change
        rows.extend([i, j])
        cols.extend([j, i])
        data.extend([-weight_change, -weight_change])
    else:
        # Normalized Laplacian update is more complex
        # Requires current degrees for accurate computation
        if current_degrees is None:
            raise ValueError(
                "current_degrees required for normalized Laplacian delta"
            )

        # This is approximate - full computation requires eigenvalue update
        d_i, d_j = current_degrees[i], current_degrees[j]

        if d_i > 0 and d_j > 0:
            # Approximate change based on degree normalization
            factor = weight_change / np.sqrt(d_i * d_j)
            rows.extend([i, j])
            cols.extend([j, i])
            data.extend([-factor, -factor])

    delta_L = coo_matrix(
        (data, (rows, cols)),
        shape=(n_nodes, n_nodes),
    ).tocsr()

    return delta_L


def sliding_window_spectrum(
    edges: List[Tuple[int, int, float, float]],
    window_size: float,
    step_size: float,
    start_time: float,
    end_time: float,
    k: int = 10,
    n_nodes: Optional[int] = None,
) -> List[Dict]:
    """
    Compute spectral properties over sliding time windows.

    Generates a time series of spectral snapshots for trend analysis.

    Args:
        edges: List of (source, target, timestamp, weight) tuples.
        window_size: Duration of each window (in timestamp units).
        step_size: Step between consecutive windows.
        start_time: Beginning of analysis period.
        end_time: End of analysis period.
        k: Number of eigenvalues to compute per window.
        n_nodes: Number of nodes (inferred if not provided).

    Returns:
        snapshots: List of dicts containing:
            - window_start: Start time of window
            - window_end: End time of window
            - n_edges: Number of active edges
            - eigenvalues: Array of k smallest eigenvalues
            - fiedler_value: Second smallest eigenvalue (connectivity)
            - spectral_gap: Gap between first two eigenvalues

    Example:
        >>> snapshots = sliding_window_spectrum(
        ...     edges, window_size=3600, step_size=1800,  # 1hr window, 30min step
        ...     start_time=0, end_time=86400, k=10
        ... )
    """
    from python.analysis.spectral import compute_laplacian, safe_spectral_decomposition

    # Determine node count
    if n_nodes is None and edges:
        n_nodes = max(max(e[0], e[1]) for e in edges) + 1
    elif n_nodes is None:
        n_nodes = 0

    snapshots = []
    t = start_time

    while t + window_size <= end_time:
        window_start = t
        window_end = t + window_size

        # Filter edges in window
        window_edges = [
            (s, tgt, ts, w) for s, tgt, ts, w in edges
            if window_start <= ts < window_end
        ]

        if window_edges:
            # Build adjacency for this window (no decay within window)
            adj = temporal_adjacency(
                window_edges,
                current_time=window_end,
                half_life=window_size * 10,  # Minimal decay within window
                n_nodes=n_nodes,
            )

            # Compute Laplacian and spectral properties
            L = compute_laplacian(adj, normalized=True)
            eigenvalues, _ = safe_spectral_decomposition(L, k)

            # Extract metrics
            fiedler_value = eigenvalues[0] if len(eigenvalues) > 0 else 0.0
            spectral_gap = (
                eigenvalues[1] - eigenvalues[0]
                if len(eigenvalues) > 1
                else 0.0
            )
        else:
            eigenvalues = np.array([])
            fiedler_value = 0.0
            spectral_gap = 0.0

        snapshots.append({
            'window_start': window_start,
            'window_end': window_end,
            'n_edges': len(window_edges),
            'eigenvalues': eigenvalues,
            'fiedler_value': fiedler_value,
            'spectral_gap': spectral_gap,
        })

        t += step_size

    return snapshots


def trajectory_similarity(
    traj1: np.ndarray,
    traj2: np.ndarray,
    method: str = "correlation",
) -> float:
    """
    Compute similarity between two spectral trajectories.

    Used for motif detection and pattern matching.

    Args:
        traj1: First trajectory, shape (timesteps1, n_features).
        traj2: Second trajectory, shape (timesteps2, n_features).
        method: Similarity method:
               - "correlation": Pearson correlation (requires same length)
               - "dtw": Dynamic time warping (different lengths OK)
               - "cosine": Cosine similarity of flattened trajectories

    Returns:
        similarity: Value in [0, 1] where 1 is identical.
    """
    if method == "correlation":
        if traj1.shape != traj2.shape:
            raise ValueError(
                "Trajectories must have same shape for correlation"
            )
        # Flatten and compute correlation
        flat1, flat2 = traj1.flatten(), traj2.flatten()
        corr = np.corrcoef(flat1, flat2)[0, 1]
        return (corr + 1) / 2  # Map [-1, 1] to [0, 1]

    elif method == "cosine":
        flat1, flat2 = traj1.flatten(), traj2.flatten()
        # Pad shorter to match length
        max_len = max(len(flat1), len(flat2))
        flat1 = np.pad(flat1, (0, max_len - len(flat1)))
        flat2 = np.pad(flat2, (0, max_len - len(flat2)))

        norm1, norm2 = np.linalg.norm(flat1), np.linalg.norm(flat2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return (np.dot(flat1, flat2) / (norm1 * norm2) + 1) / 2

    elif method == "dtw":
        # Simple DTW implementation
        n, m = len(traj1), len(traj2)

        # Cost matrix
        D = np.full((n + 1, m + 1), np.inf)
        D[0, 0] = 0

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                cost = np.linalg.norm(traj1[i - 1] - traj2[j - 1])
                D[i, j] = cost + min(
                    D[i - 1, j],      # insertion
                    D[i, j - 1],      # deletion
                    D[i - 1, j - 1],  # match
                )

        # Normalize by path length
        dtw_distance = D[n, m] / (n + m)

        # Convert distance to similarity
        return np.exp(-dtw_distance)

    else:
        raise ValueError(f"Unknown method: {method}")


def detect_formation_motif(
    spectral_trajectory: List[np.ndarray],
    motif_templates: Dict[str, np.ndarray],
    threshold: float = 0.5,
    method: str = "dtw",
) -> List[Tuple[str, float]]:
    """
    Detect if current spectral trajectory matches known motifs.

    Motifs are patterns that precede significant graph events
    (e.g., community formation, relationship emergence).

    Args:
        spectral_trajectory: List of spectral embeddings over recent timesteps.
                            Each element is shape (n_nodes, k).
        motif_templates: Dict mapping motif names to trajectory patterns.
        threshold: Minimum similarity to consider a match.
        method: Similarity method (see trajectory_similarity).

    Returns:
        matches: List of (motif_name, confidence) tuples, sorted by confidence.

    Example motifs:
        - "convergence": Nodes moving closer in spectral space
        - "splitting": Single cluster dividing into two
        - "merger": Two clusters merging
    """
    if not spectral_trajectory:
        return []

    # Stack trajectory for comparison
    current_traj = np.stack(spectral_trajectory)

    matches = []
    for name, template in motif_templates.items():
        try:
            similarity = trajectory_similarity(current_traj, template, method)
            if similarity >= threshold:
                matches.append((name, float(similarity)))
        except Exception:
            # Skip incompatible comparisons
            continue

    return sorted(matches, key=lambda x: -x[1])


def spectral_change_points(
    snapshots: List[Dict],
    eigenvalue_key: str = 'eigenvalues',
    sensitivity: float = 2.0,
) -> List[int]:
    """
    Detect change points in spectral time series.

    Identifies timesteps where graph structure changes significantly.

    Args:
        snapshots: Output from sliding_window_spectrum.
        eigenvalue_key: Key in snapshot dict containing eigenvalues.
        sensitivity: Number of standard deviations for change detection.

    Returns:
        change_points: List of snapshot indices where changes detected.
    """
    if len(snapshots) < 3:
        return []

    from scipy.stats import wasserstein_distance

    # Compute pairwise spectral distances
    distances = []
    for i in range(1, len(snapshots)):
        prev_eigs = snapshots[i - 1][eigenvalue_key]
        curr_eigs = snapshots[i][eigenvalue_key]

        if len(prev_eigs) > 0 and len(curr_eigs) > 0:
            # Pad to same length
            max_len = max(len(prev_eigs), len(curr_eigs))
            prev_padded = np.pad(prev_eigs, (0, max_len - len(prev_eigs)))
            curr_padded = np.pad(curr_eigs, (0, max_len - len(curr_eigs)))

            dist = wasserstein_distance(prev_padded, curr_padded)
        else:
            dist = 0.0

        distances.append(dist)

    # Detect outliers (change points)
    distances = np.array(distances)
    mean_dist = np.mean(distances)
    std_dist = np.std(distances)

    change_points = []
    for i, d in enumerate(distances):
        if d > mean_dist + sensitivity * std_dist:
            change_points.append(i + 1)  # Index in original snapshots

    return change_points


def exponential_moving_spectrum(
    edges: List[Tuple[int, int, float, float]],
    query_times: List[float],
    alpha: float = 0.1,
    k: int = 10,
    n_nodes: Optional[int] = None,
) -> List[Dict]:
    """
    Compute spectral properties with exponential moving average weighting.

    Unlike sliding windows, EMA gives continuous decay based on recency.

    Args:
        edges: List of (source, target, timestamp, weight) tuples.
        query_times: Times at which to compute spectrum.
        alpha: EMA smoothing factor (higher = more recent focus).
        k: Number of eigenvalues to compute.
        n_nodes: Number of nodes.

    Returns:
        spectra: List of spectral analysis results at each query time.
    """
    from python.analysis.spectral import compute_laplacian, safe_spectral_decomposition

    if n_nodes is None and edges:
        n_nodes = max(max(e[0], e[1]) for e in edges) + 1
    elif n_nodes is None:
        n_nodes = 0

    # Sort edges by time
    sorted_edges = sorted(edges, key=lambda e: e[2])

    results = []
    for query_time in query_times:
        # Compute EMA weights for edges up to query_time
        weighted_edges = []
        for src, tgt, ts, w in sorted_edges:
            if ts > query_time:
                break

            # EMA decay
            age = query_time - ts
            ema_weight = w * (1 - alpha) ** age

            if ema_weight > 1e-8:
                weighted_edges.append((src, tgt, ts, ema_weight))

        if weighted_edges:
            # Build graph from weighted edges
            rows = [e[0] for e in weighted_edges] + [e[1] for e in weighted_edges]
            cols = [e[1] for e in weighted_edges] + [e[0] for e in weighted_edges]
            weights = [e[3] for e in weighted_edges] * 2

            adj = csr_matrix(
                (weights, (rows, cols)),
                shape=(n_nodes, n_nodes),
            )

            L = compute_laplacian(adj, normalized=True)
            eigenvalues, eigenvectors = safe_spectral_decomposition(L, k)
        else:
            eigenvalues = np.array([])
            eigenvectors = np.zeros((n_nodes, 0))

        results.append({
            'time': query_time,
            'eigenvalues': eigenvalues,
            'eigenvectors': eigenvectors,
            'n_edges': len(weighted_edges),
        })

    return results
