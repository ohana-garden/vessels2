"""
Spectral Agent - Agent-based spectral analysis for Vessels.

This module provides spectral (eigenvalue/eigenvector) computations
through agent delegation, following the A0 pattern:
"No imports, agents instead."

Instead of importing numpy or scipy for linear algebra,
computations are delegated to specialized agents that can
use code execution tools to perform the calculations.
"""

from dataclasses import dataclass
from typing import Any, Optional
import json
import math


@dataclass
class SpectralRequest:
    """A request for spectral computation."""

    operation: str  # eigenvalues, svd, pca, fft
    data: Any  # Matrix or vector data
    params: dict  # Operation-specific parameters

    def to_prompt(self) -> str:
        """Convert request to agent prompt."""
        prompts = {
            "eigenvalues": self._eigenvalue_prompt,
            "svd": self._svd_prompt,
            "pca": self._pca_prompt,
            "fft": self._fft_prompt,
            "covariance": self._covariance_prompt,
        }

        generator = prompts.get(self.operation, self._generic_prompt)
        return generator()

    def _eigenvalue_prompt(self) -> str:
        return f"""Compute the eigenvalue decomposition of this matrix.

Matrix (as nested list):
{json.dumps(self.data, indent=2)}

Requirements:
1. Compute eigenvalues in descending order by absolute value
2. Compute corresponding eigenvectors (normalized)
3. Return result as JSON: {{"eigenvalues": [...], "eigenvectors": [[...], ...]}}

Use the code execution tool to compute this using numpy if available,
otherwise implement power iteration or QR algorithm.

Return ONLY the JSON result."""

    def _svd_prompt(self) -> str:
        return f"""Compute the Singular Value Decomposition (SVD) of this matrix.

Matrix:
{json.dumps(self.data, indent=2)}

Return as JSON: {{"U": [[...]], "S": [...], "V": [[...]]}}
Where A = U @ diag(S) @ V.T

Use code execution with numpy if available."""

    def _pca_prompt(self) -> str:
        n_components = self.params.get("n_components", 2)
        return f"""Perform Principal Component Analysis (PCA) on this data.

Data points (each row is a sample):
{json.dumps(self.data, indent=2)}

Number of components: {n_components}

Return as JSON:
{{
  "components": [[...], ...],  // Principal component vectors
  "explained_variance": [...],  // Variance explained by each component
  "transformed": [[...], ...]  // Data projected onto components
}}

Use code execution with sklearn or numpy."""

    def _fft_prompt(self) -> str:
        return f"""Compute the Fast Fourier Transform (FFT) of this signal.

Signal values:
{json.dumps(self.data, indent=2)}

Return as JSON:
{{
  "frequencies": [...],  // Frequency bins
  "magnitudes": [...],   // Amplitude spectrum
  "phases": [...]        // Phase spectrum
}}

Use code execution with numpy.fft or scipy.fft."""

    def _covariance_prompt(self) -> str:
        return f"""Compute the covariance matrix of this data.

Data points (each row is a sample, columns are variables):
{json.dumps(self.data, indent=2)}

Return as JSON: {{"covariance": [[...]]}}

Use numpy.cov or manual computation."""

    def _generic_prompt(self) -> str:
        return f"""Perform spectral operation: {self.operation}

Data:
{json.dumps(self.data, indent=2)}

Parameters:
{json.dumps(self.params, indent=2)}

Return result as JSON."""


class SpectralAgent:
    """
    Agent-based spectral computation service.

    This class wraps agent delegation for mathematical operations,
    implementing the "no imports, agents instead" paradigm.
    """

    def __init__(self, parent_agent: Any = None):
        """
        Initialize the spectral agent.

        Args:
            parent_agent: The agent delegating spectral work
        """
        self.parent_agent = parent_agent
        self._subordinate = None

    async def get_subordinate(self):
        """Get or create the subordinate computation agent."""
        if self._subordinate is not None:
            return self._subordinate

        if self.parent_agent is None:
            return None

        from agent import Agent
        from initialize import initialize_agent

        config = initialize_agent()
        config.profile = "vessels"

        self._subordinate = Agent(
            self.parent_agent.number + 1,
            config,
            self.parent_agent.context
        )
        self._subordinate.set_data(Agent.DATA_NAME_SUPERIOR, self.parent_agent)
        self.parent_agent.set_data("spectral_subordinate", self._subordinate)

        return self._subordinate

    async def compute(self, request: SpectralRequest) -> Optional[dict]:
        """
        Execute a spectral computation via agent delegation.

        Returns parsed JSON result or None on failure.
        """
        subordinate = await self.get_subordinate()

        if subordinate is None:
            # Fallback to local computation
            return self._local_compute(request)

        try:
            from agent import UserMessage

            prompt = request.to_prompt()
            subordinate.hist_add_user_message(
                UserMessage(message=prompt, attachments=[])
            )

            result_text = await subordinate.monologue()

            # Extract JSON from response
            return self._extract_json(result_text)

        except Exception as e:
            return self._local_compute(request)

    def _extract_json(self, text: str) -> Optional[dict]:
        """Extract JSON from agent response text."""
        # Try to find JSON in the response
        start = text.find('{')
        end = text.rfind('}') + 1

        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

        # Try finding JSON array
        start = text.find('[')
        end = text.rfind(']') + 1

        if start >= 0 and end > start:
            try:
                return {"result": json.loads(text[start:end])}
            except json.JSONDecodeError:
                pass

        return None

    def _local_compute(self, request: SpectralRequest) -> Optional[dict]:
        """
        Fallback local computation without external dependencies.

        Uses pure Python implementations for basic operations.
        """
        operations = {
            "eigenvalues": self._local_eigenvalues,
            "covariance": self._local_covariance,
            "pca": self._local_pca,
        }

        handler = operations.get(request.operation)
        if handler:
            return handler(request.data, request.params)

        return None

    def _local_eigenvalues(
        self,
        matrix: list[list[float]],
        params: dict
    ) -> dict:
        """Power iteration for eigenvalue computation."""
        n = len(matrix)
        if n == 0:
            return {"eigenvalues": [], "eigenvectors": []}

        num_eigenvalues = params.get("num_eigenvalues", min(5, n))
        num_iterations = params.get("iterations", 100)

        eigenvalues = []
        eigenvectors = []

        # Copy matrix for deflation
        A = [row[:] for row in matrix]

        for _ in range(num_eigenvalues):
            # Initialize vector
            v = [1.0 / math.sqrt(n)] * n
            eigenvalue = 0.0

            for _ in range(num_iterations):
                # Matrix-vector multiply
                Av = [sum(A[i][j] * v[j] for j in range(n)) for i in range(n)]

                # Rayleigh quotient
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

            # Deflate
            for i in range(n):
                for j in range(n):
                    A[i][j] -= eigenvalue * v[i] * v[j]

        return {"eigenvalues": eigenvalues, "eigenvectors": eigenvectors}

    def _local_covariance(
        self,
        data: list[list[float]],
        params: dict
    ) -> dict:
        """Compute covariance matrix."""
        if not data or not data[0]:
            return {"covariance": []}

        n_samples = len(data)
        n_features = len(data[0])

        # Compute means
        means = [
            sum(data[i][j] for i in range(n_samples)) / n_samples
            for j in range(n_features)
        ]

        # Compute covariance
        cov = [[0.0] * n_features for _ in range(n_features)]

        for i in range(n_features):
            for j in range(n_features):
                c = 0.0
                for k in range(n_samples):
                    c += (data[k][i] - means[i]) * (data[k][j] - means[j])
                cov[i][j] = c / (n_samples - 1) if n_samples > 1 else 0.0

        return {"covariance": cov}

    def _local_pca(
        self,
        data: list[list[float]],
        params: dict
    ) -> dict:
        """Simple PCA via covariance eigendecomposition."""
        n_components = params.get("n_components", 2)

        # Compute covariance
        cov_result = self._local_covariance(data, {})
        cov = cov_result["covariance"]

        # Compute eigenvalues/vectors of covariance
        eigen_result = self._local_eigenvalues(cov, {
            "num_eigenvalues": n_components,
            "iterations": 100
        })

        eigenvalues = eigen_result["eigenvalues"]
        eigenvectors = eigen_result["eigenvectors"]

        # Total variance
        total_var = sum(eigenvalues) if eigenvalues else 1.0

        # Project data onto components
        n_samples = len(data)
        n_features = len(data[0]) if data else 0

        # Center data
        means = [
            sum(data[i][j] for i in range(n_samples)) / n_samples
            for j in range(n_features)
        ]
        centered = [
            [data[i][j] - means[j] for j in range(n_features)]
            for i in range(n_samples)
        ]

        # Transform
        transformed = []
        for sample in centered:
            projected = []
            for component in eigenvectors[:n_components]:
                proj = sum(sample[i] * component[i] for i in range(min(len(sample), len(component))))
                projected.append(proj)
            transformed.append(projected)

        return {
            "components": eigenvectors[:n_components],
            "explained_variance": [
                ev / total_var for ev in eigenvalues[:n_components]
            ] if total_var > 0 else [],
            "transformed": transformed,
        }


# =============================================================================
# Convenience Functions
# =============================================================================

async def compute_eigenvalues(
    matrix: list[list[float]],
    parent_agent: Any = None,
    num_eigenvalues: int = 5
) -> dict:
    """
    Compute eigenvalues of a matrix using agent delegation.

    Args:
        matrix: Square matrix as nested lists
        parent_agent: Agent for delegation (optional)
        num_eigenvalues: Number of eigenvalues to compute

    Returns:
        Dict with 'eigenvalues' and 'eigenvectors'
    """
    agent = SpectralAgent(parent_agent)
    request = SpectralRequest(
        operation="eigenvalues",
        data=matrix,
        params={"num_eigenvalues": num_eigenvalues}
    )
    result = await agent.compute(request)
    return result or {"eigenvalues": [], "eigenvectors": []}


async def compute_pca(
    data: list[list[float]],
    n_components: int = 2,
    parent_agent: Any = None
) -> dict:
    """
    Perform PCA using agent delegation.

    Args:
        data: Data matrix (rows = samples, cols = features)
        n_components: Number of principal components
        parent_agent: Agent for delegation (optional)

    Returns:
        Dict with 'components', 'explained_variance', 'transformed'
    """
    agent = SpectralAgent(parent_agent)
    request = SpectralRequest(
        operation="pca",
        data=data,
        params={"n_components": n_components}
    )
    result = await agent.compute(request)
    return result or {"components": [], "explained_variance": [], "transformed": []}


async def compute_covariance(
    data: list[list[float]],
    parent_agent: Any = None
) -> list[list[float]]:
    """
    Compute covariance matrix using agent delegation.

    Args:
        data: Data matrix (rows = samples, cols = features)
        parent_agent: Agent for delegation (optional)

    Returns:
        Covariance matrix as nested lists
    """
    agent = SpectralAgent(parent_agent)
    request = SpectralRequest(
        operation="covariance",
        data=data,
        params={}
    )
    result = await agent.compute(request)
    return result.get("covariance", []) if result else []
