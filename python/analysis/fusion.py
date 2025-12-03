"""
Semantic-Structural Fusion for Knowledge Graphs

This module combines semantic embeddings (from LLMs) with spectral/structural
embeddings to create hybrid node representations. Also provides methods for
relationship prediction using spectral features.
"""

from typing import Tuple, Optional, Union, List, Dict
import numpy as np
from scipy.sparse import csr_matrix

# Optional PyTorch import for neural network components
try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    torch = None
    nn = None


def hybrid_embedding(
    semantic_vectors: np.ndarray,
    spectral_coords: np.ndarray,
    alpha: float = 0.5,
    normalize: bool = True,
) -> np.ndarray:
    """
    Combine semantic embeddings with spectral position coordinates.

    Creates a unified representation that captures both:
    - Semantic meaning (from LLM embeddings)
    - Structural position (from spectral embedding)

    Args:
        semantic_vectors: Shape (n_nodes, d_semantic) from LLM embeddings.
        spectral_coords: Shape (n_nodes, k) from spectral embedding.
        alpha: Weighting factor in [0, 1]:
              - 0 = pure semantic
              - 1 = pure structural
              - 0.5 = balanced
        normalize: If True, normalize each space before combining.

    Returns:
        combined: Shape (n_nodes, d_semantic + k) hybrid embedding.

    Notes:
        - Both inputs should have same number of nodes (first dimension)
        - Normalization helps balance different embedding scales
        - Result preserves interpretability: first d_semantic dims are
          semantic, last k dims are structural
    """
    if semantic_vectors.shape[0] != spectral_coords.shape[0]:
        raise ValueError(
            f"Node count mismatch: semantic has {semantic_vectors.shape[0]}, "
            f"spectral has {spectral_coords.shape[0]}"
        )

    if normalize:
        # Normalize to unit norm per row
        sem_norms = np.linalg.norm(semantic_vectors, axis=1, keepdims=True)
        sem_norms[sem_norms == 0] = 1  # Avoid division by zero
        sem_norm = semantic_vectors / sem_norms

        spec_norms = np.linalg.norm(spectral_coords, axis=1, keepdims=True)
        spec_norms[spec_norms == 0] = 1
        spec_norm = spectral_coords / spec_norms
    else:
        sem_norm = semantic_vectors
        spec_norm = spectral_coords

    # Weight and concatenate
    combined = np.hstack([
        (1 - alpha) * sem_norm,
        alpha * spec_norm,
    ])

    return combined


def hybrid_similarity(
    embedding1: np.ndarray,
    embedding2: np.ndarray,
    semantic_dim: int,
    alpha: float = 0.5,
) -> float:
    """
    Compute similarity between two hybrid embeddings.

    Separates semantic and structural components for weighted comparison.

    Args:
        embedding1: First hybrid embedding.
        embedding2: Second hybrid embedding.
        semantic_dim: Number of semantic dimensions (remaining are structural).
        alpha: Weight for structural vs semantic (same as hybrid_embedding).

    Returns:
        similarity: Combined similarity score in [0, 1].
    """
    sem1, struct1 = embedding1[:semantic_dim], embedding1[semantic_dim:]
    sem2, struct2 = embedding2[:semantic_dim], embedding2[semantic_dim:]

    # Cosine similarities
    def cosine_sim(a, b):
        norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return np.dot(a, b) / (norm_a * norm_b)

    sem_sim = cosine_sim(sem1, sem2)
    struct_sim = cosine_sim(struct1, struct2)

    # Weighted combination
    combined_sim = (1 - alpha) * sem_sim + alpha * struct_sim

    # Map from [-1, 1] to [0, 1]
    return (combined_sim + 1) / 2


def edge_spectral_features(
    node_i: int,
    node_j: int,
    spectral_coords: np.ndarray,
    eigenvalues: np.ndarray,
) -> np.ndarray:
    """
    Compute spectral features for a potential edge (i, j).

    These features capture structural proximity and alignment in
    spectral space, useful for link prediction.

    Args:
        node_i: First node index.
        node_j: Second node index.
        spectral_coords: Shape (n_nodes, k) spectral embedding.
        eigenvalues: Shape (k,) Laplacian eigenvalues.

    Returns:
        features: Vector of spectral edge features including:
            - spectral_distance: Weighted distance in spectral space
            - cosine_similarity: Angle between spectral coordinates
            - freq_alignment: Per-eigenmode alignment (k values)

    Notes:
        - Lower spectral distance suggests higher connection probability
        - Frequency alignment shows which scales predict the edge
    """
    coord_i = spectral_coords[node_i]
    coord_j = spectral_coords[node_j]

    # Spectral distance (weighted by inverse eigenvalue = low-frequency emphasis)
    # Small eigenvalues correspond to global structure
    weights = 1.0 / (eigenvalues + 1e-6)
    diff_squared = (coord_i - coord_j) ** 2
    spectral_dist = np.sqrt(np.sum(weights * diff_squared))

    # Spectral angle (cosine similarity)
    norm_i = np.linalg.norm(coord_i)
    norm_j = np.linalg.norm(coord_j)
    if norm_i > 0 and norm_j > 0:
        cos_sim = np.dot(coord_i, coord_j) / (norm_i * norm_j)
    else:
        cos_sim = 0.0

    # Per-frequency alignment (element-wise product)
    # Positive = same side in that eigenmode
    freq_alignment = coord_i * coord_j

    return np.concatenate([[spectral_dist, cos_sim], freq_alignment])


def batch_edge_features(
    node_pairs: List[Tuple[int, int]],
    spectral_coords: np.ndarray,
    eigenvalues: np.ndarray,
) -> np.ndarray:
    """
    Compute spectral edge features for multiple node pairs.

    Efficient batch version of edge_spectral_features.

    Args:
        node_pairs: List of (i, j) node index pairs.
        spectral_coords: Shape (n_nodes, k) spectral embedding.
        eigenvalues: Shape (k,) Laplacian eigenvalues.

    Returns:
        features: Shape (n_pairs, k+2) feature matrix.
    """
    n_pairs = len(node_pairs)
    k = len(eigenvalues)
    features = np.zeros((n_pairs, k + 2))

    weights = 1.0 / (eigenvalues + 1e-6)

    for idx, (i, j) in enumerate(node_pairs):
        coord_i = spectral_coords[i]
        coord_j = spectral_coords[j]

        # Spectral distance
        diff = coord_i - coord_j
        features[idx, 0] = np.sqrt(np.sum(weights * diff ** 2))

        # Cosine similarity
        norm_i = np.linalg.norm(coord_i)
        norm_j = np.linalg.norm(coord_j)
        if norm_i > 0 and norm_j > 0:
            features[idx, 1] = np.dot(coord_i, coord_j) / (norm_i * norm_j)

        # Frequency alignment
        features[idx, 2:] = coord_i * coord_j

    return features


def link_prediction_score(
    node_i: int,
    node_j: int,
    spectral_coords: np.ndarray,
    eigenvalues: np.ndarray,
    semantic_vectors: Optional[np.ndarray] = None,
    alpha: float = 0.5,
) -> float:
    """
    Compute a link prediction score for edge (i, j).

    Higher scores indicate higher likelihood of edge existence.

    Args:
        node_i: First node index.
        node_j: Second node index.
        spectral_coords: Shape (n_nodes, k) spectral embedding.
        eigenvalues: Shape (k,) eigenvalues.
        semantic_vectors: Optional (n_nodes, d) semantic embeddings.
        alpha: Weight for structural vs semantic (if semantic provided).

    Returns:
        score: Prediction score in [0, 1].
    """
    features = edge_spectral_features(node_i, node_j, spectral_coords, eigenvalues)

    # Base score from spectral proximity
    spectral_dist = features[0]
    cos_sim = features[1]

    # Convert distance to similarity
    spectral_sim = np.exp(-spectral_dist)

    # Combine with cosine (already in [-1, 1])
    structural_score = 0.5 * spectral_sim + 0.5 * (cos_sim + 1) / 2

    if semantic_vectors is not None:
        # Add semantic similarity
        vec_i = semantic_vectors[node_i]
        vec_j = semantic_vectors[node_j]

        norm_i = np.linalg.norm(vec_i)
        norm_j = np.linalg.norm(vec_j)

        if norm_i > 0 and norm_j > 0:
            semantic_sim = np.dot(vec_i, vec_j) / (norm_i * norm_j)
            semantic_sim = (semantic_sim + 1) / 2  # Map to [0, 1]
        else:
            semantic_sim = 0.5

        score = (1 - alpha) * semantic_sim + alpha * structural_score
    else:
        score = structural_score

    return float(score)


def recommend_edges(
    candidate_pairs: List[Tuple[int, int]],
    spectral_coords: np.ndarray,
    eigenvalues: np.ndarray,
    semantic_vectors: Optional[np.ndarray] = None,
    alpha: float = 0.5,
    top_k: int = 10,
) -> List[Tuple[int, int, float]]:
    """
    Recommend top edges to add based on prediction scores.

    Args:
        candidate_pairs: List of potential edges to evaluate.
        spectral_coords: Spectral embedding.
        eigenvalues: Laplacian eigenvalues.
        semantic_vectors: Optional semantic embeddings.
        alpha: Structural vs semantic weight.
        top_k: Number of recommendations to return.

    Returns:
        recommendations: List of (node_i, node_j, score) sorted by score.
    """
    scored_pairs = []
    for i, j in candidate_pairs:
        score = link_prediction_score(
            i, j, spectral_coords, eigenvalues, semantic_vectors, alpha
        )
        scored_pairs.append((i, j, score))

    # Sort by score descending
    scored_pairs.sort(key=lambda x: -x[2])

    return scored_pairs[:top_k]


# =============================================================================
# Neural Network Components (requires PyTorch)
# =============================================================================

if TORCH_AVAILABLE:

    class SpectralAttentionLayer(nn.Module):
        """
        Graph convolution with learned spectral weighting.

        Uses Chebyshev polynomial approximation for efficient spectral filtering.
        Learns which frequency components are most important for the task.
        """

        def __init__(
            self,
            in_features: int,
            out_features: int,
            k_hops: int = 5,
            bias: bool = True,
        ):
            """
            Args:
                in_features: Input feature dimension.
                out_features: Output feature dimension.
                k_hops: Number of Chebyshev polynomial terms (controls receptive field).
                bias: Whether to include bias in linear transform.
            """
            super().__init__()
            self.k_hops = k_hops

            # Learnable weights for each polynomial term
            self.spectral_weights = nn.Parameter(torch.ones(k_hops))

            # Output transformation
            self.linear = nn.Linear(in_features, out_features, bias=bias)

            self._init_weights()

        def _init_weights(self):
            # Initialize spectral weights to decay with polynomial order
            with torch.no_grad():
                for i in range(self.k_hops):
                    self.spectral_weights[i] = 1.0 / (i + 1)

        def forward(
            self,
            x: torch.Tensor,
            laplacian: torch.Tensor,
        ) -> torch.Tensor:
            """
            Args:
                x: Node features, shape (n_nodes, in_features).
                laplacian: Normalized Laplacian, shape (n_nodes, n_nodes).
                          Should be sparse for efficiency.

            Returns:
                out: Transformed features, shape (n_nodes, out_features).
            """
            # Chebyshev polynomial approximation of spectral filter
            # T_0(L) = I, T_1(L) = L
            # T_k(L) = 2*L*T_{k-1}(L) - T_{k-2}(L)

            T_0 = x  # T_0(L)x = x
            out = self.spectral_weights[0] * T_0

            if self.k_hops > 1:
                # T_1(L)x = Lx
                if laplacian.is_sparse:
                    T_1 = torch.sparse.mm(laplacian, x)
                else:
                    T_1 = torch.mm(laplacian, x)
                out = out + self.spectral_weights[1] * T_1

                # Higher order terms via recurrence
                T_prev, T_curr = T_0, T_1
                for i in range(2, self.k_hops):
                    if laplacian.is_sparse:
                        T_next = 2 * torch.sparse.mm(laplacian, T_curr) - T_prev
                    else:
                        T_next = 2 * torch.mm(laplacian, T_curr) - T_prev

                    out = out + self.spectral_weights[i] * T_next
                    T_prev, T_curr = T_curr, T_next

            return self.linear(out)


    class HybridEmbeddingLayer(nn.Module):
        """
        Neural layer that learns to combine semantic and spectral embeddings.
        """

        def __init__(
            self,
            semantic_dim: int,
            spectral_dim: int,
            output_dim: int,
            hidden_dim: Optional[int] = None,
        ):
            """
            Args:
                semantic_dim: Dimension of semantic input.
                spectral_dim: Dimension of spectral input.
                output_dim: Dimension of fused output.
                hidden_dim: Hidden layer dimension (defaults to output_dim).
            """
            super().__init__()
            hidden_dim = hidden_dim or output_dim

            # Separate projections for each modality
            self.semantic_proj = nn.Linear(semantic_dim, hidden_dim)
            self.spectral_proj = nn.Linear(spectral_dim, hidden_dim)

            # Learnable fusion weights
            self.fusion_gate = nn.Linear(hidden_dim * 2, 2)

            # Output projection
            self.output_proj = nn.Linear(hidden_dim, output_dim)

        def forward(
            self,
            semantic: torch.Tensor,
            spectral: torch.Tensor,
        ) -> torch.Tensor:
            """
            Args:
                semantic: Semantic features (n_nodes, semantic_dim).
                spectral: Spectral features (n_nodes, spectral_dim).

            Returns:
                fused: Fused embedding (n_nodes, output_dim).
            """
            # Project each modality
            sem_h = F.relu(self.semantic_proj(semantic))
            spec_h = F.relu(self.spectral_proj(spectral))

            # Compute attention/gating weights
            concat = torch.cat([sem_h, spec_h], dim=-1)
            gate_weights = F.softmax(self.fusion_gate(concat), dim=-1)

            # Weighted combination
            fused = gate_weights[:, 0:1] * sem_h + gate_weights[:, 1:2] * spec_h

            return self.output_proj(fused)


    class LinkPredictionHead(nn.Module):
        """
        MLP head for link prediction using spectral and semantic features.
        """

        def __init__(
            self,
            spectral_dim: int,
            semantic_dim: int = 0,
            hidden_dim: int = 64,
        ):
            """
            Args:
                spectral_dim: Dimension of spectral features (k + 2 from edge_spectral_features).
                semantic_dim: Dimension of semantic features (0 if not using).
                hidden_dim: Hidden layer dimension.
            """
            super().__init__()
            input_dim = spectral_dim + 2 * semantic_dim  # concat of both node semantics

            self.mlp = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(hidden_dim, hidden_dim // 2),
                nn.ReLU(),
                nn.Linear(hidden_dim // 2, 1),
                nn.Sigmoid(),
            )

        def forward(
            self,
            spectral_features: torch.Tensor,
            semantic_i: Optional[torch.Tensor] = None,
            semantic_j: Optional[torch.Tensor] = None,
        ) -> torch.Tensor:
            """
            Args:
                spectral_features: Shape (batch, spectral_dim).
                semantic_i: Optional semantic features for source nodes.
                semantic_j: Optional semantic features for target nodes.

            Returns:
                scores: Shape (batch,) link prediction scores.
            """
            if semantic_i is not None and semantic_j is not None:
                features = torch.cat([spectral_features, semantic_i, semantic_j], dim=-1)
            else:
                features = spectral_features

            return self.mlp(features).squeeze(-1)


else:
    # Placeholder classes when PyTorch not available

    class SpectralAttentionLayer:
        """Placeholder - requires PyTorch."""
        def __init__(self, *args, **kwargs):
            raise ImportError("SpectralAttentionLayer requires PyTorch")


    class HybridEmbeddingLayer:
        """Placeholder - requires PyTorch."""
        def __init__(self, *args, **kwargs):
            raise ImportError("HybridEmbeddingLayer requires PyTorch")


    class LinkPredictionHead:
        """Placeholder - requires PyTorch."""
        def __init__(self, *args, **kwargs):
            raise ImportError("LinkPredictionHead requires PyTorch")
