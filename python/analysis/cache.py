"""
Performance Utilities and Caching for Spectral Analysis

This module provides:
- Spectral decomposition caching with intelligent invalidation
- Perturbation-based approximation for incremental updates
- Memory-efficient operations for large graphs
- Nyström approximation for very large graphs
"""

from typing import Tuple, Optional, Union, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import numpy as np
from scipy.sparse import csr_matrix, issparse
from scipy.sparse.linalg import eigsh

from python.analysis.temporal import perturb_eigenvalues


@dataclass
class SpectralCacheEntry:
    """Cached spectral decomposition with metadata."""
    eigenvalues: np.ndarray
    eigenvectors: np.ndarray
    laplacian_hash: int
    timestamp: datetime = field(default_factory=datetime.now)
    n_nodes: int = 0
    n_edges: int = 0


class SpectralCache:
    """
    Cache spectral decompositions with intelligent invalidation.

    Maintains cached eigenvalues/eigenvectors and uses perturbation
    theory for small graph updates to avoid full recomputation.
    """

    def __init__(
        self,
        recompute_threshold: float = 0.05,
        max_cache_entries: int = 10,
        perturbation_max_change: float = 0.01,
    ):
        """
        Args:
            recompute_threshold: Fraction of Laplacian change that triggers
                               full recomputation (vs perturbation approx).
            max_cache_entries: Maximum number of cached decompositions.
            perturbation_max_change: Maximum relative change for perturbation
                                    to be considered accurate.
        """
        self.recompute_threshold = recompute_threshold
        self.max_cache_entries = max_cache_entries
        self.perturbation_max_change = perturbation_max_change

        self._cache: Dict[str, SpectralCacheEntry] = {}
        self._access_order: list = []

    def _laplacian_hash(self, L: csr_matrix) -> int:
        """Compute hash of Laplacian for cache lookup."""
        # Use shape and data hash
        if issparse(L):
            data_hash = hash(L.data.tobytes()) if L.nnz > 0 else 0
            return hash((L.shape, L.nnz, data_hash))
        else:
            return hash(L.tobytes())

    def _compute_change_magnitude(
        self,
        current_L: csr_matrix,
        cached_L_hash: int,
        delta_L: Optional[csr_matrix] = None,
    ) -> float:
        """Estimate magnitude of Laplacian change."""
        if delta_L is None:
            # Can't compute exact change without stored Laplacian
            return float('inf')

        if issparse(delta_L):
            delta_norm = np.abs(delta_L.data).sum() if delta_L.nnz > 0 else 0
        else:
            delta_norm = np.abs(delta_L).sum()

        if issparse(current_L):
            current_norm = np.abs(current_L.data).sum() if current_L.nnz > 0 else 1
        else:
            current_norm = np.abs(current_L).sum()

        return delta_norm / (current_norm + 1e-10)

    def get_or_compute(
        self,
        current_laplacian: Union[np.ndarray, csr_matrix],
        k: int,
        cache_key: str = "default",
        delta_L: Optional[csr_matrix] = None,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get cached spectral decomposition or compute new one.

        Uses perturbation approximation for small changes, full
        recomputation for large changes.

        Args:
            current_laplacian: Current graph Laplacian.
            k: Number of eigenvalues/eigenvectors to return.
            cache_key: Key for caching (e.g., graph identifier).
            delta_L: Change in Laplacian since last computation (optional).
                    If provided, enables perturbation approximation.

        Returns:
            eigenvalues: Shape (k,).
            eigenvectors: Shape (n, k).
        """
        if not issparse(current_laplacian):
            current_laplacian = csr_matrix(current_laplacian)

        current_hash = self._laplacian_hash(current_laplacian)

        if cache_key in self._cache:
            cached = self._cache[cache_key]

            # Check if cache is still valid
            if cached.laplacian_hash == current_hash:
                # Exact match - return cached
                self._update_access_order(cache_key)
                return cached.eigenvalues[:k], cached.eigenvectors[:, :k]

            # Check if we can use perturbation approximation
            if delta_L is not None:
                change_magnitude = self._compute_change_magnitude(
                    current_laplacian, cached.laplacian_hash, delta_L
                )

                if change_magnitude < self.recompute_threshold:
                    # Use perturbation approximation for eigenvalues
                    approx_eigs = perturb_eigenvalues(
                        cached.eigenvectors,
                        cached.eigenvalues,
                        delta_L,
                    )

                    # Check if approximation is reasonable
                    relative_change = np.abs(
                        approx_eigs - cached.eigenvalues
                    ) / (np.abs(cached.eigenvalues) + 1e-10)

                    if np.max(relative_change) < self.perturbation_max_change:
                        self._update_access_order(cache_key)
                        return approx_eigs[:k], cached.eigenvectors[:, :k]

        # Full recomputation needed
        return self._compute_and_cache(current_laplacian, k, cache_key)

    def _compute_and_cache(
        self,
        L: csr_matrix,
        k: int,
        cache_key: str,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Compute spectral decomposition and cache results."""
        from python.analysis.spectral import safe_spectral_decomposition

        eigenvalues, eigenvectors = safe_spectral_decomposition(L, k)

        # Create cache entry
        entry = SpectralCacheEntry(
            eigenvalues=eigenvalues,
            eigenvectors=eigenvectors,
            laplacian_hash=self._laplacian_hash(L),
            timestamp=datetime.now(),
            n_nodes=L.shape[0],
            n_edges=L.nnz // 2 if issparse(L) else 0,
        )

        # Cache with LRU eviction
        self._cache[cache_key] = entry
        self._update_access_order(cache_key)
        self._evict_if_needed()

        return eigenvalues, eigenvectors

    def _update_access_order(self, key: str):
        """Update LRU access order."""
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)

    def _evict_if_needed(self):
        """Evict least recently used entries if over limit."""
        while len(self._cache) > self.max_cache_entries:
            if self._access_order:
                oldest_key = self._access_order.pop(0)
                self._cache.pop(oldest_key, None)

    def invalidate(self, cache_key: str = "default"):
        """Explicitly invalidate a cache entry."""
        self._cache.pop(cache_key, None)
        if cache_key in self._access_order:
            self._access_order.remove(cache_key)

    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()
        self._access_order.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "num_entries": len(self._cache),
            "max_entries": self.max_cache_entries,
            "cache_keys": list(self._cache.keys()),
            "total_nodes_cached": sum(e.n_nodes for e in self._cache.values()),
        }


def nystrom_approximation(
    adj_matrix: Union[np.ndarray, csr_matrix],
    k: int,
    n_samples: Optional[int] = None,
    random_state: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Nyström approximation for spectral decomposition of large graphs.

    More efficient than exact eigendecomposition for graphs with
    > 100k nodes, at the cost of some approximation error.

    Args:
        adj_matrix: Adjacency matrix (sparse preferred).
        k: Number of eigenvectors/eigenvalues to approximate.
        n_samples: Number of landmark nodes to sample.
                  Defaults to min(2*k, sqrt(n_nodes)).
        random_state: Random seed for reproducibility.

    Returns:
        eigenvalues: Approximate k smallest eigenvalues.
        eigenvectors: Approximate eigenvectors shape (n_nodes, k).

    Notes:
        - Quality depends on n_samples; more samples = better approximation
        - Works best for graphs with smooth eigenvector structure
        - For very sparse graphs, may not improve over exact methods
    """
    from python.analysis.spectral import compute_laplacian

    if not issparse(adj_matrix):
        adj_matrix = csr_matrix(adj_matrix)

    n = adj_matrix.shape[0]

    # Set number of samples
    if n_samples is None:
        n_samples = min(2 * k, int(np.sqrt(n)), n)
    n_samples = min(n_samples, n)

    if n_samples >= n:
        # Fall back to exact computation for small graphs
        L = compute_laplacian(adj_matrix, normalized=True)
        return eigsh(L, k=k, which='SM')

    # Random sampling
    rng = np.random.RandomState(random_state)
    sample_indices = rng.choice(n, n_samples, replace=False)
    sample_indices = np.sort(sample_indices)

    # Compute full Laplacian
    L = compute_laplacian(adj_matrix, normalized=True)

    # Extract submatrices
    # L_ss = L[sample_indices][:, sample_indices]  # Landmark-landmark
    # L_ns = L[:, sample_indices]  # All-landmark

    L_ss = L[sample_indices][:, sample_indices].toarray()
    L_ns = L[:, sample_indices].toarray()

    # Eigendecomposition of landmark submatrix
    try:
        eigs_ss, vecs_ss = np.linalg.eigh(L_ss)
    except np.linalg.LinAlgError:
        # Regularize if not positive definite
        L_ss += 1e-6 * np.eye(n_samples)
        eigs_ss, vecs_ss = np.linalg.eigh(L_ss)

    # Sort by eigenvalue
    idx = np.argsort(eigs_ss)
    eigs_ss = eigs_ss[idx]
    vecs_ss = vecs_ss[:, idx]

    # Nyström extension
    # Approximate eigenvectors for all nodes
    # v_approx = L_ns @ vecs_ss @ diag(1/eigs_ss)

    # Handle zero eigenvalues
    eigs_ss_safe = np.where(np.abs(eigs_ss) > 1e-10, eigs_ss, 1e-10)
    eigs_inv_sqrt = 1.0 / np.sqrt(eigs_ss_safe)

    # Extend to full graph
    eigenvectors_approx = L_ns @ (vecs_ss * eigs_inv_sqrt)

    # Normalize columns
    col_norms = np.linalg.norm(eigenvectors_approx, axis=0, keepdims=True)
    col_norms[col_norms == 0] = 1
    eigenvectors_approx = eigenvectors_approx / col_norms

    # Return k smallest (skip first if connected)
    return eigs_ss[1:k + 1], eigenvectors_approx[:, 1:k + 1]


def randomized_svd_laplacian(
    adj_matrix: Union[np.ndarray, csr_matrix],
    k: int,
    n_oversamples: int = 10,
    random_state: Optional[int] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Randomized SVD for approximate spectral decomposition.

    Alternative to Nyström for large graphs. May be more stable
    for ill-conditioned matrices.

    Args:
        adj_matrix: Adjacency matrix.
        k: Number of components.
        n_oversamples: Extra samples for accuracy.
        random_state: Random seed.

    Returns:
        eigenvalues: Approximate eigenvalues.
        eigenvectors: Approximate eigenvectors.
    """
    from sklearn.utils.extmath import randomized_svd
    from python.analysis.spectral import compute_laplacian

    if not issparse(adj_matrix):
        adj_matrix = csr_matrix(adj_matrix)

    L = compute_laplacian(adj_matrix, normalized=True)

    # For symmetric PSD matrix, SVD singular values = eigenvalues
    U, s, _ = randomized_svd(
        L,
        n_components=k + 1,
        n_oversamples=n_oversamples,
        random_state=random_state,
    )

    # Skip first (zero) eigenvalue
    return s[1:], U[:, 1:]


class IncrementalSpectralTracker:
    """
    Track spectral properties incrementally as edges are added/removed.

    Maintains approximate spectral decomposition through edge-by-edge
    updates using perturbation theory.
    """

    def __init__(
        self,
        n_nodes: int,
        k: int = 10,
        recompute_every: int = 100,
    ):
        """
        Args:
            n_nodes: Number of nodes in graph.
            k: Number of eigenvalues to track.
            recompute_every: Force full recomputation after this many updates.
        """
        self.n_nodes = n_nodes
        self.k = k
        self.recompute_every = recompute_every

        # Initialize with empty graph
        self.adj_data: Dict[Tuple[int, int], float] = {}
        self.eigenvalues: Optional[np.ndarray] = None
        self.eigenvectors: Optional[np.ndarray] = None
        self.degrees: np.ndarray = np.zeros(n_nodes)

        self._updates_since_recompute = 0

    def _build_laplacian(self) -> csr_matrix:
        """Build Laplacian from current adjacency data."""
        from python.analysis.spectral import compute_laplacian

        if not self.adj_data:
            return csr_matrix((self.n_nodes, self.n_nodes))

        rows, cols, data = [], [], []
        for (i, j), w in self.adj_data.items():
            rows.extend([i, j])
            cols.extend([j, i])
            data.extend([w, w])

        adj = csr_matrix(
            (data, (rows, cols)),
            shape=(self.n_nodes, self.n_nodes),
        )

        return compute_laplacian(adj, normalized=True)

    def add_edge(self, i: int, j: int, weight: float = 1.0):
        """Add or update an edge."""
        edge_key = (min(i, j), max(i, j))
        old_weight = self.adj_data.get(edge_key, 0)

        self.adj_data[edge_key] = weight
        self.degrees[i] += weight - old_weight
        self.degrees[j] += weight - old_weight

        self._updates_since_recompute += 1
        self._maybe_recompute()

    def remove_edge(self, i: int, j: int):
        """Remove an edge."""
        edge_key = (min(i, j), max(i, j))
        if edge_key in self.adj_data:
            old_weight = self.adj_data.pop(edge_key)
            self.degrees[i] -= old_weight
            self.degrees[j] -= old_weight

            self._updates_since_recompute += 1
            self._maybe_recompute()

    def _maybe_recompute(self):
        """Recompute if needed."""
        if self._updates_since_recompute >= self.recompute_every:
            self.recompute()

    def recompute(self):
        """Force full recomputation of spectral properties."""
        from python.analysis.spectral import safe_spectral_decomposition

        L = self._build_laplacian()

        if L.nnz == 0:
            self.eigenvalues = np.zeros(self.k)
            self.eigenvectors = np.zeros((self.n_nodes, self.k))
        else:
            self.eigenvalues, self.eigenvectors = safe_spectral_decomposition(
                L, self.k
            )

        self._updates_since_recompute = 0

    def get_spectrum(self) -> Tuple[np.ndarray, np.ndarray]:
        """Get current spectral decomposition."""
        if self.eigenvalues is None:
            self.recompute()

        return self.eigenvalues, self.eigenvectors

    def get_fiedler_value(self) -> float:
        """Get current Fiedler value (connectivity measure)."""
        eigs, _ = self.get_spectrum()
        return float(eigs[0]) if len(eigs) > 0 else 0.0

    def get_spectral_gap(self) -> float:
        """Get current spectral gap."""
        eigs, _ = self.get_spectrum()
        if len(eigs) > 1:
            return float(eigs[1] - eigs[0])
        return 0.0
