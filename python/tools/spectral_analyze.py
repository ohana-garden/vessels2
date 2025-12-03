"""
Spectral Analysis Tool - Agent tool for spectral/eigenvalue operations.

This tool allows agents to perform spectral analysis operations
without importing numpy/scipy. Computations are either:
1. Agent-delegated (for complex operations)
2. Locally computed (for basic operations)

This follows the A0 paradigm: no imports, agents instead.
"""

from python.helpers.tool import Tool, Response
from python.helpers.spectral_agent import (
    SpectralAgent,
    SpectralRequest,
    compute_eigenvalues,
    compute_pca,
    compute_covariance,
)
import json


class SpectralAnalyze(Tool):
    """
    Tool for spectral analysis operations.

    Methods:
        eigenvalues: Compute eigenvalues/eigenvectors of a matrix
        pca: Principal Component Analysis
        covariance: Compute covariance matrix
        correlate: Compute correlation between signals
        decompose: Generic spectral decomposition
    """

    async def execute(self, **kwargs) -> Response:
        """Execute the spectral analysis operation."""
        method = self.method or kwargs.get("method", "eigenvalues")

        handlers = {
            "eigenvalues": self._eigenvalues,
            "pca": self._pca,
            "covariance": self._covariance,
            "correlate": self._correlate,
            "decompose": self._decompose,
            "normalize": self._normalize,
            "magnitude": self._magnitude,
        }

        handler = handlers.get(method)
        if not handler:
            return Response(
                message=f"Unknown method: {method}. Available: {', '.join(handlers.keys())}",
                break_loop=False
            )

        return await handler(**kwargs)

    async def _eigenvalues(self, **kwargs) -> Response:
        """
        Compute eigenvalues and eigenvectors of a matrix.

        Args:
            matrix: Square matrix as nested list
            num_eigenvalues: Number to compute (default: all)
        """
        matrix = kwargs.get("matrix", [])
        num_eigenvalues = kwargs.get("num_eigenvalues", 5)

        if not matrix:
            return Response(
                message="Provide a 'matrix' (nested list) for eigenvalue computation.",
                break_loop=False
            )

        # Validate matrix
        if not isinstance(matrix, list) or not all(isinstance(row, list) for row in matrix):
            return Response(
                message="Matrix must be a nested list: [[row1], [row2], ...]",
                break_loop=False
            )

        n = len(matrix)
        if n == 0:
            return Response(message="Matrix is empty.", break_loop=False)

        for row in matrix:
            if len(row) != n:
                return Response(
                    message=f"Matrix must be square. Got {n} rows but row has {len(row)} columns.",
                    break_loop=False
                )

        # Compute using agent delegation
        result = await compute_eigenvalues(matrix, self.agent, num_eigenvalues)

        # Format result
        output = {
            "eigenvalues": result.get("eigenvalues", []),
            "eigenvectors": result.get("eigenvectors", []),
            "matrix_size": n,
            "num_computed": len(result.get("eigenvalues", [])),
        }

        # Add interpretation
        eigenvalues = output["eigenvalues"]
        if eigenvalues:
            output["interpretation"] = {
                "largest": eigenvalues[0] if eigenvalues else 0,
                "total_variance": sum(abs(e) for e in eigenvalues),
                "condition_number": abs(eigenvalues[0] / eigenvalues[-1]) if eigenvalues[-1] != 0 else float("inf"),
            }

        return Response(
            message=f"Eigenvalue decomposition:\n```json\n{json.dumps(output, indent=2)}\n```",
            break_loop=False
        )

    async def _pca(self, **kwargs) -> Response:
        """
        Perform Principal Component Analysis.

        Args:
            data: Data matrix (rows = samples, columns = features)
            n_components: Number of principal components (default: 2)
        """
        data = kwargs.get("data", [])
        n_components = kwargs.get("n_components", 2)

        if not data:
            return Response(
                message="Provide 'data' (nested list: rows=samples, cols=features) for PCA.",
                break_loop=False
            )

        if not isinstance(data, list) or not data[0]:
            return Response(
                message="Data must be a nested list with at least one sample.",
                break_loop=False
            )

        n_samples = len(data)
        n_features = len(data[0])

        result = await compute_pca(data, n_components, self.agent)

        output = {
            "n_samples": n_samples,
            "n_features": n_features,
            "n_components": n_components,
            "components": result.get("components", []),
            "explained_variance": result.get("explained_variance", []),
            "transformed_data": result.get("transformed", []),
        }

        # Interpretation
        exp_var = output["explained_variance"]
        if exp_var:
            total_explained = sum(exp_var)
            output["interpretation"] = {
                "total_variance_explained": total_explained,
                "first_component_explains": exp_var[0] if exp_var else 0,
                "dimensionality_reduction": f"{n_features} -> {n_components}",
            }

        return Response(
            message=f"PCA result:\n```json\n{json.dumps(output, indent=2)}\n```",
            break_loop=False
        )

    async def _covariance(self, **kwargs) -> Response:
        """
        Compute covariance matrix.

        Args:
            data: Data matrix (rows = samples, columns = features)
        """
        data = kwargs.get("data", [])

        if not data:
            return Response(
                message="Provide 'data' (nested list) for covariance computation.",
                break_loop=False
            )

        cov = await compute_covariance(data, self.agent)

        output = {
            "covariance_matrix": cov,
            "n_features": len(cov) if cov else 0,
            "n_samples": len(data),
        }

        # Extract diagonal (variances)
        if cov:
            variances = [cov[i][i] for i in range(len(cov))]
            output["variances"] = variances
            output["std_devs"] = [v ** 0.5 for v in variances]

        return Response(
            message=f"Covariance matrix:\n```json\n{json.dumps(output, indent=2)}\n```",
            break_loop=False
        )

    async def _correlate(self, **kwargs) -> Response:
        """
        Compute correlation between two signals/vectors.

        Args:
            signal_a: First signal (list of values)
            signal_b: Second signal (list of values)
        """
        signal_a = kwargs.get("signal_a", kwargs.get("a", []))
        signal_b = kwargs.get("signal_b", kwargs.get("b", []))

        if not signal_a or not signal_b:
            return Response(
                message="Provide 'signal_a' and 'signal_b' (lists of numbers) for correlation.",
                break_loop=False
            )

        if len(signal_a) != len(signal_b):
            return Response(
                message=f"Signals must have same length. Got {len(signal_a)} and {len(signal_b)}.",
                break_loop=False
            )

        n = len(signal_a)

        # Compute means
        mean_a = sum(signal_a) / n
        mean_b = sum(signal_b) / n

        # Compute covariance and standard deviations
        cov = sum((signal_a[i] - mean_a) * (signal_b[i] - mean_b) for i in range(n)) / n
        std_a = (sum((x - mean_a) ** 2 for x in signal_a) / n) ** 0.5
        std_b = (sum((x - mean_b) ** 2 for x in signal_b) / n) ** 0.5

        # Pearson correlation
        correlation = cov / (std_a * std_b) if std_a > 0 and std_b > 0 else 0

        # Interpretation
        if abs(correlation) > 0.8:
            strength = "strong"
        elif abs(correlation) > 0.5:
            strength = "moderate"
        elif abs(correlation) > 0.2:
            strength = "weak"
        else:
            strength = "negligible"

        direction = "positive" if correlation > 0 else "negative"

        output = {
            "correlation": correlation,
            "covariance": cov,
            "n_samples": n,
            "mean_a": mean_a,
            "mean_b": mean_b,
            "std_a": std_a,
            "std_b": std_b,
            "interpretation": f"{strength} {direction} correlation ({correlation:.3f})",
        }

        return Response(
            message=f"Correlation analysis:\n```json\n{json.dumps(output, indent=2)}\n```",
            break_loop=False
        )

    async def _decompose(self, **kwargs) -> Response:
        """
        Generic spectral decomposition.

        Args:
            data: Data to decompose (matrix or vector)
            method: Decomposition method (svd, eigen, fft)
        """
        data = kwargs.get("data", [])
        decomp_method = kwargs.get("decomposition_method", "eigen")

        if not data:
            return Response(
                message="Provide 'data' for spectral decomposition.",
                break_loop=False
            )

        agent = SpectralAgent(self.agent)
        request = SpectralRequest(
            operation=decomp_method,
            data=data,
            params=kwargs.get("params", {})
        )

        result = await agent.compute(request)

        if result:
            return Response(
                message=f"Spectral decomposition ({decomp_method}):\n```json\n{json.dumps(result, indent=2)}\n```",
                break_loop=False
            )

        return Response(
            message=f"Decomposition failed for method: {decomp_method}",
            break_loop=False
        )

    async def _normalize(self, **kwargs) -> Response:
        """
        Normalize a vector to unit length.

        Args:
            vector: List of numbers
        """
        vector = kwargs.get("vector", [])

        if not vector:
            return Response(
                message="Provide a 'vector' (list of numbers) to normalize.",
                break_loop=False
            )

        magnitude = sum(x * x for x in vector) ** 0.5

        if magnitude == 0:
            return Response(
                message="Cannot normalize zero vector.",
                break_loop=False
            )

        normalized = [x / magnitude for x in vector]

        output = {
            "original": vector,
            "normalized": normalized,
            "original_magnitude": magnitude,
            "new_magnitude": 1.0,
        }

        return Response(
            message=f"Normalized vector:\n```json\n{json.dumps(output, indent=2)}\n```",
            break_loop=False
        )

    async def _magnitude(self, **kwargs) -> Response:
        """
        Compute the magnitude (L2 norm) of a vector.

        Args:
            vector: List of numbers
        """
        vector = kwargs.get("vector", [])

        if not vector:
            return Response(
                message="Provide a 'vector' (list of numbers) to compute magnitude.",
                break_loop=False
            )

        magnitude = sum(x * x for x in vector) ** 0.5
        l1_norm = sum(abs(x) for x in vector)
        linf_norm = max(abs(x) for x in vector)

        output = {
            "vector": vector,
            "l2_norm": magnitude,
            "l1_norm": l1_norm,
            "linf_norm": linf_norm,
            "dimension": len(vector),
        }

        return Response(
            message=f"Vector magnitude:\n```json\n{json.dumps(output, indent=2)}\n```",
            break_loop=False
        )
