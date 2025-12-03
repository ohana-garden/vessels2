"""
Spectral Analysis Module for Temporal Semantic Graphs

This module provides spectral methods for analyzing evolving knowledge graphs
(Graphiti-style) for semantic pattern recognition and relationship prediction.

Key Components:
- spectral: Core spectral analysis (Laplacian, embeddings, divergence)
- temporal: Temporal analysis patterns (sliding window, perturbation)
- fusion: Semantic-structural fusion and prediction
- cache: Performance utilities and caching
- graphiti_integration: Integration with GraphStore/Graphiti
"""

from python.analysis.spectral import (
    compute_laplacian,
    spectral_embedding,
    spectral_divergence,
    safe_spectral_decomposition,
)

from python.analysis.temporal import (
    temporal_adjacency,
    perturb_eigenvalues,
    sliding_window_spectrum,
)

from python.analysis.fusion import (
    hybrid_embedding,
    edge_spectral_features,
    SpectralAttentionLayer,
)

from python.analysis.cache import (
    SpectralCache,
)

from python.analysis.graphiti_integration import (
    GraphitiSpectralAnalyzer,
)

__all__ = [
    # Spectral core
    "compute_laplacian",
    "spectral_embedding",
    "spectral_divergence",
    "safe_spectral_decomposition",
    # Temporal
    "temporal_adjacency",
    "perturb_eigenvalues",
    "sliding_window_spectrum",
    # Fusion
    "hybrid_embedding",
    "edge_spectral_features",
    "SpectralAttentionLayer",
    # Cache
    "SpectralCache",
    # Integration
    "GraphitiSpectralAnalyzer",
]
