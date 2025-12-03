"""
Core Spectral Analysis for Temporal Semantic Graphs

This module provides fundamental spectral graph analysis capabilities:
- Graph Laplacian computation (normalized and unnormalized)
- Spectral embedding via eigendecomposition
- Spectral divergence for measuring structural change
- Robust decomposition with fallbacks for large/sparse graphs
"""

from typing import Tuple, Optional, Union
import numpy as np
from scipy.sparse import csr_matrix, issparse, diags, eye as sparse_eye
from scipy.sparse.linalg import eigsh, ArpackNoConvergence
from scipy.stats import wasserstein_distance


def compute_laplacian(
    adj_matrix: Union[np.ndarray, csr_matrix],
    normalized: bool = True,
) -> csr_matrix:
    """
    Compute the graph Laplacian from an adjacency matrix.

    The Laplacian matrix encodes the graph structure and is fundamental
    for spectral analysis. Its eigenvalues reveal connectivity properties
    and community structure.

    Args:
        adj_matrix: Adjacency matrix (scipy sparse or numpy array).
                   Should be symmetric for undirected graphs.
        normalized: If True, compute symmetric normalized Laplacian:
                   L_sym = I - D^{-1/2} A D^{-1/2}
                   If False, compute unnormalized Laplacian:
                   L = D - A

    Returns:
        L: Graph Laplacian as sparse CSR matrix.

    Notes:
        - Normalized Laplacian eigenvalues are bounded in [0, 2]
        - Unnormalized Laplacian eigenvalues depend on node degrees
        - Both have zero eigenvalue with multiplicity = number of components
    """
    if not issparse(adj_matrix):
        adj_matrix = csr_matrix(adj_matrix)

    n = adj_matrix.shape[0]

    # Compute degree vector
    degrees = np.array(adj_matrix.sum(axis=1)).flatten()

    if normalized:
        # L_sym = I - D^{-1/2} A D^{-1/2}
        # Handle zero-degree nodes to avoid division by zero
        d_inv_sqrt = np.zeros_like(degrees, dtype=np.float64)
        nonzero_mask = degrees > 0
        d_inv_sqrt[nonzero_mask] = np.power(degrees[nonzero_mask], -0.5)

        D_inv_sqrt = diags(d_inv_sqrt)
        L = sparse_eye(n, format='csr') - D_inv_sqrt @ adj_matrix @ D_inv_sqrt
    else:
        # L = D - A
        D = diags(degrees)
        L = D - adj_matrix

    return csr_matrix(L)


def spectral_embedding(
    laplacian: Union[np.ndarray, csr_matrix],
    k: int = 10,
    skip_first: bool = True,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Embed graph nodes into k-dimensional spectral space.

    Uses the smallest eigenvalues of the Laplacian (Laplacian Eigenmaps).
    These capture the coarse/global structure of the graph.

    Args:
        laplacian: Graph Laplacian (sparse or dense).
        k: Embedding dimension (number of eigenvectors to use).
        skip_first: If True, skip the first (zero) eigenvalue.
                   Set to False for disconnected graphs where you want
                   to analyze component structure.

    Returns:
        eigenvalues: Shape (k,) - sorted eigenvalues
        eigenvectors: Shape (n_nodes, k) - corresponding eigenvectors

    Raises:
        ValueError: If k is too large for the graph size.

    Notes:
        - For connected graphs, first eigenvalue is 0 (constant eigenvector)
        - Second smallest eigenvalue (Fiedler value) indicates connectivity
        - Eigenvector corresponding to Fiedler value (Fiedler vector) reveals
          optimal graph bisection
    """
    if not issparse(laplacian):
        laplacian = csr_matrix(laplacian)

    n = laplacian.shape[0]
    num_to_compute = k + 1 if skip_first else k

    if num_to_compute > n - 1:
        raise ValueError(
            f"Cannot compute {num_to_compute} eigenvalues for graph "
            f"with {n} nodes. Maximum is {n - 1}."
        )

    # Compute smallest eigenvalues
    eigenvalues, eigenvectors = eigsh(
        laplacian,
        k=num_to_compute,
        which='SM',  # Smallest magnitude
        return_eigenvectors=True,
    )

    # Sort by eigenvalue (eigsh doesn't guarantee order)
    idx = np.argsort(eigenvalues)
    eigenvalues = eigenvalues[idx]
    eigenvectors = eigenvectors[:, idx]

    if skip_first:
        # Skip the trivial zero eigenvalue for connected graphs
        return eigenvalues[1:k + 1], eigenvectors[:, 1:k + 1]
    else:
        return eigenvalues[:k], eigenvectors[:, :k]


def spectral_divergence(
    L1: Union[np.ndarray, csr_matrix],
    L2: Union[np.ndarray, csr_matrix],
    k: int = 20,
    method: str = "wasserstein",
) -> float:
    """
    Measure structural change between two graph states.

    Compares the spectral properties (eigenvalue distribution) of two
    Laplacians to quantify how much the graph structure has changed.

    Args:
        L1: Laplacian at time t (first graph state).
        L2: Laplacian at time t+1 (second graph state).
        k: Number of eigenvalues to compare.
        method: Distance metric to use:
               - "wasserstein": Earth Mover's Distance (default)
               - "l2": Euclidean distance between sorted eigenvalues
               - "max": Maximum eigenvalue difference

    Returns:
        distance: Scalar measuring structural divergence.
                 Higher values indicate more structural change.

    Notes:
        - Wasserstein distance is most robust to eigenvalue crossings
        - L2 is sensitive to individual eigenvalue changes
        - Max is useful for detecting large structural events
    """
    if not issparse(L1):
        L1 = csr_matrix(L1)
    if not issparse(L2):
        L2 = csr_matrix(L2)

    # Handle different graph sizes
    n1, n2 = L1.shape[0], L2.shape[0]
    k_actual = min(k, n1 - 1, n2 - 1)

    if k_actual < 2:
        return 0.0  # Can't meaningfully compare very small graphs

    # Compute eigenvalues for both graphs
    eigs1, _ = eigsh(L1, k=k_actual, which='SM')
    eigs2, _ = eigsh(L2, k=k_actual, which='SM')

    # Sort eigenvalues
    eigs1 = np.sort(eigs1)
    eigs2 = np.sort(eigs2)

    if method == "wasserstein":
        return wasserstein_distance(eigs1, eigs2)
    elif method == "l2":
        return float(np.linalg.norm(eigs1 - eigs2))
    elif method == "max":
        return float(np.max(np.abs(eigs1 - eigs2)))
    else:
        raise ValueError(f"Unknown method: {method}. Use 'wasserstein', 'l2', or 'max'.")


def safe_spectral_decomposition(
    L: Union[np.ndarray, csr_matrix],
    k: int,
    max_iter: int = 1000,
    tol: float = 1e-6,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Robust spectral decomposition with fallbacks.

    Handles convergence issues that can occur with large sparse graphs
    or ill-conditioned Laplacians.

    Args:
        L: Laplacian matrix (sparse or dense).
        k: Number of eigenvalues/eigenvectors to compute.
        max_iter: Maximum ARPACK iterations.
        tol: Convergence tolerance.

    Returns:
        eigenvalues: Shape (k,) or fewer if partial convergence.
        eigenvectors: Shape (n, k) or (n, fewer).

    Notes:
        - Returns partial results if ARPACK doesn't fully converge
        - For very large graphs (>100k nodes), consider Nyström approximation
    """
    if not issparse(L):
        L = csr_matrix(L)

    n = L.shape[0]
    k_actual = min(k, n - 1)

    if k_actual < 1:
        return np.array([]), np.array([]).reshape(n, 0)

    try:
        eigenvalues, eigenvectors = eigsh(
            L,
            k=k_actual,
            which='SM',
            maxiter=max_iter,
            tol=tol,
        )

        # Sort by eigenvalue
        idx = np.argsort(eigenvalues)
        return eigenvalues[idx], eigenvectors[:, idx]

    except ArpackNoConvergence as e:
        # Return partial results
        eigenvalues = e.eigenvalues if e.eigenvalues is not None else np.array([])
        eigenvectors = e.eigenvectors if e.eigenvectors is not None else np.array([]).reshape(n, 0)

        if len(eigenvalues) > 0:
            idx = np.argsort(eigenvalues)
            return eigenvalues[idx], eigenvectors[:, idx]

        return eigenvalues, eigenvectors


def compute_fiedler(
    laplacian: Union[np.ndarray, csr_matrix],
) -> Tuple[float, np.ndarray]:
    """
    Compute the Fiedler value and vector.

    The Fiedler value (second smallest eigenvalue) is a key measure of
    graph connectivity. The Fiedler vector provides an optimal bisection.

    Args:
        laplacian: Graph Laplacian.

    Returns:
        fiedler_value: Second smallest eigenvalue. Higher = more connected.
        fiedler_vector: Corresponding eigenvector for graph bisection.

    Notes:
        - Fiedler value = 0 iff graph is disconnected
        - Sign of Fiedler vector entries indicates bisection membership
    """
    eigenvalues, eigenvectors = spectral_embedding(laplacian, k=1, skip_first=True)
    return float(eigenvalues[0]), eigenvectors[:, 0]


def spectral_clustering_labels(
    laplacian: Union[np.ndarray, csr_matrix],
    n_clusters: int,
) -> np.ndarray:
    """
    Assign nodes to clusters using spectral clustering.

    Uses k-means on the spectral embedding to find clusters.

    Args:
        laplacian: Graph Laplacian.
        n_clusters: Number of clusters to find.

    Returns:
        labels: Array of cluster assignments for each node.
    """
    from sklearn.cluster import KMeans

    # Get spectral embedding
    _, eigenvectors = spectral_embedding(laplacian, k=n_clusters)

    # Normalize rows for better clustering
    row_norms = np.linalg.norm(eigenvectors, axis=1, keepdims=True)
    row_norms[row_norms == 0] = 1  # Avoid division by zero
    normalized = eigenvectors / row_norms

    # Cluster using k-means
    kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = kmeans.fit_predict(normalized)

    return labels


def connected_components_from_spectrum(
    laplacian: Union[np.ndarray, csr_matrix],
    zero_threshold: float = 1e-8,
) -> int:
    """
    Count connected components using spectral properties.

    The number of connected components equals the multiplicity of the
    zero eigenvalue.

    Args:
        laplacian: Graph Laplacian.
        zero_threshold: Eigenvalues below this are considered zero.

    Returns:
        n_components: Number of connected components.
    """
    n = laplacian.shape[0]
    k = min(10, n - 1)  # Check first few eigenvalues

    if k < 1:
        return 1 if n == 1 else 0

    eigenvalues, _ = safe_spectral_decomposition(laplacian, k)

    # Count near-zero eigenvalues
    n_components = np.sum(np.abs(eigenvalues) < zero_threshold)

    return max(1, int(n_components))


def spectral_gap(
    laplacian: Union[np.ndarray, csr_matrix],
) -> float:
    """
    Compute the spectral gap (difference between first two non-zero eigenvalues).

    A larger spectral gap indicates clearer community structure.

    Args:
        laplacian: Graph Laplacian.

    Returns:
        gap: Difference between second and first non-zero eigenvalues.
    """
    eigenvalues, _ = spectral_embedding(laplacian, k=2, skip_first=True)

    if len(eigenvalues) < 2:
        return 0.0

    return float(eigenvalues[1] - eigenvalues[0])
