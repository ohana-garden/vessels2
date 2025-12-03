"""
Unit Tests for Spectral Analysis Module

Tests cover:
- Graph Laplacian computation
- Spectral embedding
- Temporal adjacency with decay
- Hybrid embeddings
- Spectral caching
- Link prediction features
"""

import pytest
import numpy as np
from scipy.sparse import csr_matrix
from numpy.testing import assert_array_almost_equal, assert_allclose


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def simple_graph():
    """A simple 4-node path graph: 0-1-2-3"""
    adj = np.array([
        [0, 1, 0, 0],
        [1, 0, 1, 0],
        [0, 1, 0, 1],
        [0, 0, 1, 0],
    ], dtype=float)
    return csr_matrix(adj)


@pytest.fixture
def disconnected_graph():
    """Two disconnected components: 0-1 and 2-3"""
    adj = np.array([
        [0, 1, 0, 0],
        [1, 0, 0, 0],
        [0, 0, 0, 1],
        [0, 0, 1, 0],
    ], dtype=float)
    return csr_matrix(adj)


@pytest.fixture
def complete_graph():
    """Complete graph on 4 nodes (K4)"""
    adj = np.ones((4, 4)) - np.eye(4)
    return csr_matrix(adj)


@pytest.fixture
def temporal_edges():
    """Edges with timestamps for temporal testing"""
    # (source, target, timestamp, weight)
    return [
        (0, 1, 100.0, 1.0),
        (1, 2, 90.0, 1.0),
        (2, 3, 80.0, 1.0),
        (0, 3, 50.0, 1.0),  # Older edge
    ]


@pytest.fixture
def semantic_vectors():
    """Synthetic semantic embeddings for 4 nodes"""
    np.random.seed(42)
    return np.random.randn(4, 10)


# =============================================================================
# Tests for spectral.py
# =============================================================================

class TestComputeLaplacian:
    """Tests for compute_laplacian function"""

    def test_unnormalized_laplacian(self, simple_graph):
        from python.analysis.spectral import compute_laplacian

        L = compute_laplacian(simple_graph, normalized=False)

        # L = D - A for unnormalized
        # Degrees: [1, 2, 2, 1]
        expected_diagonal = [1, 2, 2, 1]
        actual_diagonal = L.diagonal()

        assert_array_almost_equal(actual_diagonal, expected_diagonal)

    def test_normalized_laplacian(self, simple_graph):
        from python.analysis.spectral import compute_laplacian

        L = compute_laplacian(simple_graph, normalized=True)

        # Normalized Laplacian eigenvalues are in [0, 2]
        eigenvalues = np.linalg.eigvalsh(L.toarray())
        assert np.all(eigenvalues >= -1e-10)
        assert np.all(eigenvalues <= 2 + 1e-10)

    def test_laplacian_sparse_output(self, simple_graph):
        from python.analysis.spectral import compute_laplacian
        from scipy.sparse import issparse

        L = compute_laplacian(simple_graph, normalized=True)
        assert issparse(L)

    def test_laplacian_dense_input(self):
        from python.analysis.spectral import compute_laplacian

        adj_dense = np.array([[0, 1], [1, 0]], dtype=float)
        L = compute_laplacian(adj_dense, normalized=True)

        assert L.shape == (2, 2)


class TestSpectralEmbedding:
    """Tests for spectral_embedding function"""

    def test_embedding_dimension(self, simple_graph):
        from python.analysis.spectral import compute_laplacian, spectral_embedding

        L = compute_laplacian(simple_graph, normalized=True)
        eigenvalues, eigenvectors = spectral_embedding(L, k=2)

        assert eigenvalues.shape == (2,)
        assert eigenvectors.shape == (4, 2)

    def test_eigenvalues_sorted(self, simple_graph):
        from python.analysis.spectral import compute_laplacian, spectral_embedding

        L = compute_laplacian(simple_graph, normalized=True)
        eigenvalues, _ = spectral_embedding(L, k=3)

        # Should be sorted ascending
        assert np.all(eigenvalues[:-1] <= eigenvalues[1:])

    def test_connected_graph_nonzero_eigenvalue(self, simple_graph):
        from python.analysis.spectral import compute_laplacian, spectral_embedding

        L = compute_laplacian(simple_graph, normalized=True)
        eigenvalues, _ = spectral_embedding(L, k=1, skip_first=True)

        # First non-trivial eigenvalue should be positive
        assert eigenvalues[0] > 0

    def test_skip_first_option(self, simple_graph):
        from python.analysis.spectral import compute_laplacian, spectral_embedding

        L = compute_laplacian(simple_graph, normalized=True)

        eigs_skip, _ = spectral_embedding(L, k=2, skip_first=True)
        eigs_no_skip, _ = spectral_embedding(L, k=2, skip_first=False)

        # With skip_first=False, first eigenvalue should be ~0
        assert abs(eigs_no_skip[0]) < 1e-6


class TestSpectralDivergence:
    """Tests for spectral_divergence function"""

    def test_same_graph_zero_divergence(self, simple_graph):
        from python.analysis.spectral import compute_laplacian, spectral_divergence

        L = compute_laplacian(simple_graph, normalized=True)
        divergence = spectral_divergence(L, L, k=3)

        assert divergence < 1e-6

    def test_different_graphs_positive_divergence(self, simple_graph, complete_graph):
        from python.analysis.spectral import compute_laplacian, spectral_divergence

        L1 = compute_laplacian(simple_graph, normalized=True)
        L2 = compute_laplacian(complete_graph, normalized=True)

        divergence = spectral_divergence(L1, L2, k=3)

        assert divergence > 0

    def test_different_methods(self, simple_graph, complete_graph):
        from python.analysis.spectral import compute_laplacian, spectral_divergence

        L1 = compute_laplacian(simple_graph, normalized=True)
        L2 = compute_laplacian(complete_graph, normalized=True)

        div_wasserstein = spectral_divergence(L1, L2, k=3, method="wasserstein")
        div_l2 = spectral_divergence(L1, L2, k=3, method="l2")
        div_max = spectral_divergence(L1, L2, k=3, method="max")

        # All should be positive
        assert div_wasserstein > 0
        assert div_l2 > 0
        assert div_max > 0


class TestConnectedComponents:
    """Tests for connected_components_from_spectrum"""

    def test_connected_graph_one_component(self, simple_graph):
        from python.analysis.spectral import (
            compute_laplacian,
            connected_components_from_spectrum,
        )

        L = compute_laplacian(simple_graph, normalized=True)
        n_components = connected_components_from_spectrum(L)

        assert n_components == 1

    def test_disconnected_graph_two_components(self, disconnected_graph):
        from python.analysis.spectral import (
            compute_laplacian,
            connected_components_from_spectrum,
        )

        L = compute_laplacian(disconnected_graph, normalized=True)
        n_components = connected_components_from_spectrum(L)

        assert n_components == 2


class TestFiedlerValue:
    """Tests for compute_fiedler function"""

    def test_fiedler_value_positive(self, simple_graph):
        from python.analysis.spectral import compute_laplacian, compute_fiedler

        L = compute_laplacian(simple_graph, normalized=True)
        fiedler_val, fiedler_vec = compute_fiedler(L)

        assert fiedler_val > 0
        assert len(fiedler_vec) == 4

    def test_complete_graph_high_fiedler(self, complete_graph):
        from python.analysis.spectral import compute_laplacian, compute_fiedler

        # Complete graphs have high connectivity
        L = compute_laplacian(complete_graph, normalized=True)
        fiedler_val, _ = compute_fiedler(L)

        # K4 normalized Fiedler should be high
        assert fiedler_val > 0.5


# =============================================================================
# Tests for temporal.py
# =============================================================================

class TestTemporalAdjacency:
    """Tests for temporal_adjacency function"""

    def test_recent_edges_higher_weight(self, temporal_edges):
        from python.analysis.temporal import temporal_adjacency

        adj = temporal_adjacency(
            edges=temporal_edges,
            current_time=100.0,
            half_life=25.0,
            n_nodes=4,
        )

        # Edge (0,1) at t=100 should have full weight
        assert adj[0, 1] == pytest.approx(1.0, abs=0.01)

        # Edge (0,3) at t=50 is 2 half-lives old, should have ~0.25 weight
        assert adj[0, 3] == pytest.approx(0.25, abs=0.05)

    def test_symmetric_adjacency(self, temporal_edges):
        from python.analysis.temporal import temporal_adjacency

        adj = temporal_adjacency(
            edges=temporal_edges,
            current_time=100.0,
            half_life=25.0,
            n_nodes=4,
            symmetric=True,
        )

        # Check symmetry
        diff = adj - adj.T
        assert np.abs(diff).max() < 1e-10

    def test_threshold_removes_old_edges(self, temporal_edges):
        from python.analysis.temporal import temporal_adjacency

        # Very short half-life should eliminate old edges
        adj = temporal_adjacency(
            edges=temporal_edges,
            current_time=100.0,
            half_life=1.0,  # Very short
            n_nodes=4,
            threshold=0.01,
        )

        # Edge at t=50 should be gone (50 half-lives old)
        assert adj[0, 3] == 0


class TestPerturbEigenvalues:
    """Tests for perturb_eigenvalues function"""

    def test_small_perturbation_accuracy(self, simple_graph):
        from python.analysis.spectral import compute_laplacian, spectral_embedding
        from python.analysis.temporal import (
            perturb_eigenvalues,
            compute_laplacian_delta_for_edge,
        )

        L = compute_laplacian(simple_graph, normalized=False)
        eigenvalues, eigenvectors = spectral_embedding(L, k=2, skip_first=True)

        # Small perturbation: modify edge weight slightly
        delta_L = compute_laplacian_delta_for_edge(
            n_nodes=4,
            edge=(0, 1),
            weight_change=0.1,
            normalized=False,
        )

        approx_eigs = perturb_eigenvalues(eigenvectors, eigenvalues, delta_L)

        # Approximation should be close to original for small change
        assert_allclose(approx_eigs, eigenvalues, rtol=0.5)


class TestSlidingWindowSpectrum:
    """Tests for sliding_window_spectrum function"""

    def test_window_generation(self, temporal_edges):
        from python.analysis.temporal import sliding_window_spectrum

        snapshots = sliding_window_spectrum(
            edges=temporal_edges,
            window_size=20.0,
            step_size=10.0,
            start_time=50.0,
            end_time=100.0,
            k=3,
            n_nodes=4,
        )

        # Should have multiple snapshots
        assert len(snapshots) >= 3

        # Each snapshot should have required keys
        for snap in snapshots:
            assert 'window_start' in snap
            assert 'window_end' in snap
            assert 'eigenvalues' in snap
            assert 'fiedler_value' in snap


class TestTrajectorySimilarity:
    """Tests for trajectory_similarity function"""

    def test_identical_trajectories(self):
        from python.analysis.temporal import trajectory_similarity

        traj = np.random.randn(10, 5)
        sim = trajectory_similarity(traj, traj, method="correlation")

        assert sim == pytest.approx(1.0, abs=0.01)

    def test_dtw_different_lengths(self):
        from python.analysis.temporal import trajectory_similarity

        traj1 = np.random.randn(10, 5)
        traj2 = np.random.randn(15, 5)  # Different length

        sim = trajectory_similarity(traj1, traj2, method="dtw")

        # Should return valid similarity
        assert 0 <= sim <= 1


# =============================================================================
# Tests for fusion.py
# =============================================================================

class TestHybridEmbedding:
    """Tests for hybrid_embedding function"""

    def test_output_shape(self, semantic_vectors):
        from python.analysis.fusion import hybrid_embedding

        spectral_coords = np.random.randn(4, 3)
        hybrid = hybrid_embedding(semantic_vectors, spectral_coords, alpha=0.5)

        expected_dim = semantic_vectors.shape[1] + spectral_coords.shape[1]
        assert hybrid.shape == (4, expected_dim)

    def test_pure_semantic(self, semantic_vectors):
        from python.analysis.fusion import hybrid_embedding

        spectral_coords = np.random.randn(4, 3)
        hybrid = hybrid_embedding(semantic_vectors, spectral_coords, alpha=0.0)

        # Last spectral_dim columns should be zero
        spectral_part = hybrid[:, semantic_vectors.shape[1]:]
        assert np.allclose(spectral_part, 0)

    def test_pure_structural(self, semantic_vectors):
        from python.analysis.fusion import hybrid_embedding

        spectral_coords = np.random.randn(4, 3)
        hybrid = hybrid_embedding(semantic_vectors, spectral_coords, alpha=1.0)

        # First semantic_dim columns should be zero
        semantic_part = hybrid[:, :semantic_vectors.shape[1]]
        assert np.allclose(semantic_part, 0)


class TestEdgeSpectralFeatures:
    """Tests for edge_spectral_features function"""

    def test_feature_dimension(self, simple_graph):
        from python.analysis.spectral import compute_laplacian, spectral_embedding
        from python.analysis.fusion import edge_spectral_features

        L = compute_laplacian(simple_graph, normalized=True)
        eigenvalues, eigenvectors = spectral_embedding(L, k=2)

        features = edge_spectral_features(0, 1, eigenvectors, eigenvalues)

        # Should have 2 (distance, cosine) + k (alignment)
        expected_dim = 2 + len(eigenvalues)
        assert len(features) == expected_dim

    def test_self_edge_zero_distance(self, simple_graph):
        from python.analysis.spectral import compute_laplacian, spectral_embedding
        from python.analysis.fusion import edge_spectral_features

        L = compute_laplacian(simple_graph, normalized=True)
        eigenvalues, eigenvectors = spectral_embedding(L, k=2)

        features = edge_spectral_features(0, 0, eigenvectors, eigenvalues)

        # Distance to self should be zero
        assert features[0] == pytest.approx(0.0, abs=1e-6)

        # Cosine similarity with self should be 1
        assert features[1] == pytest.approx(1.0, abs=1e-6)


class TestLinkPrediction:
    """Tests for link prediction functions"""

    def test_prediction_score_range(self, simple_graph, semantic_vectors):
        from python.analysis.spectral import compute_laplacian, spectral_embedding
        from python.analysis.fusion import link_prediction_score

        L = compute_laplacian(simple_graph, normalized=True)
        eigenvalues, eigenvectors = spectral_embedding(L, k=2)

        score = link_prediction_score(
            0, 2, eigenvectors, eigenvalues, semantic_vectors
        )

        # Score should be in [0, 1]
        assert 0 <= score <= 1

    def test_recommend_edges(self, simple_graph, semantic_vectors):
        from python.analysis.spectral import compute_laplacian, spectral_embedding
        from python.analysis.fusion import recommend_edges

        L = compute_laplacian(simple_graph, normalized=True)
        eigenvalues, eigenvectors = spectral_embedding(L, k=2)

        # Non-existing edges as candidates
        candidates = [(0, 2), (0, 3), (1, 3)]

        recommendations = recommend_edges(
            candidates, eigenvectors, eigenvalues, semantic_vectors, top_k=2
        )

        assert len(recommendations) == 2
        # Each recommendation should have (i, j, score)
        for rec in recommendations:
            assert len(rec) == 3
            assert 0 <= rec[2] <= 1


# =============================================================================
# Tests for cache.py
# =============================================================================

class TestSpectralCache:
    """Tests for SpectralCache class"""

    def test_cache_hit(self, simple_graph):
        from python.analysis.spectral import compute_laplacian
        from python.analysis.cache import SpectralCache

        L = compute_laplacian(simple_graph, normalized=True)
        cache = SpectralCache()

        # First call - computes and caches
        eigs1, vecs1 = cache.get_or_compute(L, k=2, cache_key="test")

        # Second call - should hit cache
        eigs2, vecs2 = cache.get_or_compute(L, k=2, cache_key="test")

        assert_array_almost_equal(eigs1, eigs2)
        assert_array_almost_equal(vecs1, vecs2)

    def test_cache_invalidation(self, simple_graph, complete_graph):
        from python.analysis.spectral import compute_laplacian
        from python.analysis.cache import SpectralCache

        cache = SpectralCache()

        L1 = compute_laplacian(simple_graph, normalized=True)
        L2 = compute_laplacian(complete_graph, normalized=True)

        eigs1, _ = cache.get_or_compute(L1, k=2, cache_key="test")
        eigs2, _ = cache.get_or_compute(L2, k=2, cache_key="test")

        # Different graphs should give different eigenvalues
        assert not np.allclose(eigs1, eigs2)

    def test_cache_stats(self, simple_graph):
        from python.analysis.spectral import compute_laplacian
        from python.analysis.cache import SpectralCache

        cache = SpectralCache()
        L = compute_laplacian(simple_graph, normalized=True)

        cache.get_or_compute(L, k=2, cache_key="graph1")
        cache.get_or_compute(L, k=2, cache_key="graph2")

        stats = cache.get_stats()
        assert stats['num_entries'] == 2


class TestNystromApproximation:
    """Tests for Nyström approximation"""

    def test_small_graph_fallback(self, simple_graph):
        from python.analysis.cache import nystrom_approximation

        # Small graph should fall back to exact computation
        eigenvalues, eigenvectors = nystrom_approximation(
            simple_graph, k=2, n_samples=10
        )

        assert len(eigenvalues) == 2
        assert eigenvectors.shape[1] == 2


class TestIncrementalTracker:
    """Tests for IncrementalSpectralTracker"""

    def test_add_edges(self):
        from python.analysis.cache import IncrementalSpectralTracker

        tracker = IncrementalSpectralTracker(n_nodes=4, k=2, recompute_every=5)

        tracker.add_edge(0, 1, weight=1.0)
        tracker.add_edge(1, 2, weight=1.0)
        tracker.add_edge(2, 3, weight=1.0)

        eigs, vecs = tracker.get_spectrum()

        assert len(eigs) == 2
        assert vecs.shape == (4, 2)

    def test_fiedler_value(self):
        from python.analysis.cache import IncrementalSpectralTracker

        tracker = IncrementalSpectralTracker(n_nodes=4, k=2, recompute_every=10)

        # Create connected graph
        tracker.add_edge(0, 1)
        tracker.add_edge(1, 2)
        tracker.add_edge(2, 3)

        fiedler = tracker.get_fiedler_value()
        assert fiedler > 0


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """Integration tests for the full pipeline"""

    def test_full_analysis_pipeline(self, temporal_edges, semantic_vectors):
        from python.analysis.temporal import temporal_adjacency
        from python.analysis.spectral import compute_laplacian, spectral_embedding
        from python.analysis.fusion import hybrid_embedding, recommend_edges

        # Build temporal graph
        adj = temporal_adjacency(
            edges=temporal_edges,
            current_time=100.0,
            half_life=25.0,
            n_nodes=4,
        )

        # Compute spectral embedding
        L = compute_laplacian(adj, normalized=True)
        eigenvalues, eigenvectors = spectral_embedding(L, k=2)

        # Create hybrid embedding
        hybrid = hybrid_embedding(semantic_vectors, eigenvectors, alpha=0.5)

        # Get link recommendations
        candidates = [(0, 2), (1, 3)]
        recs = recommend_edges(
            candidates, eigenvectors, eigenvalues, semantic_vectors, top_k=2
        )

        # Verify outputs
        assert hybrid.shape[0] == 4
        assert len(recs) == 2


# =============================================================================
# Run tests if executed directly
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
