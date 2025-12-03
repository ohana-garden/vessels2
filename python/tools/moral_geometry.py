"""
Moral Geometry Tool - Agent tool for moral space operations.

This tool allows agents to:
- Create and store moral vectors
- Compute moral distances between positions
- Analyze moral trajectories
- Perform spectral decomposition of moral stances

All data is stored graph-natively using the Vessels GraphStore.
Complex computations are agent-delegated (no numpy/scipy imports).
"""

from python.helpers.tool import Tool, Response
from python.helpers.moral_geometry import (
    MoralVector,
    MoralDimension,
    MoralDistance,
    MoralTrajectory,
    MoralGeometryEngine,
    MoralGeometryStore,
)
import json


class MoralGeometry(Tool):
    """
    Tool for moral geometry operations.

    Methods:
        create_vector: Create a new moral vector
        evaluate: Evaluate an action's moral position
        distance: Compute distance between moral positions
        trajectory: Track moral trajectory over time
        decompose: Spectral decomposition of moral vectors
        search: Search for similar moral positions
    """

    async def execute(self, **kwargs) -> Response:
        """Execute the moral geometry operation."""
        method = self.method or kwargs.get("method", "evaluate")

        handlers = {
            "create_vector": self._create_vector,
            "evaluate": self._evaluate,
            "distance": self._distance,
            "trajectory": self._trajectory,
            "decompose": self._decompose,
            "search": self._search,
            "list_dimensions": self._list_dimensions,
        }

        handler = handlers.get(method)
        if not handler:
            return Response(
                message=f"Unknown method: {method}. Available: {', '.join(handlers.keys())}",
                break_loop=False
            )

        return await handler(**kwargs)

    async def _create_vector(self, **kwargs) -> Response:
        """Create a new moral vector from dimension values."""
        name = kwargs.get("name", "")
        description = kwargs.get("description", "")
        source_type = kwargs.get("source_type", "action")
        dimensions = kwargs.get("dimensions", {})

        vector = MoralVector(
            name=name,
            description=description,
            source_type=source_type,
        )

        # Set dimension values
        for dim_name, value in dimensions.items():
            try:
                dim = MoralDimension(dim_name)
                vector.set_dimension(dim, float(value))
            except (ValueError, TypeError):
                # Try as string key
                vector.components[dim_name] = max(-1.0, min(1.0, float(value)))

        # Compute derived properties
        vector.compute_magnitude()
        vector.find_dominant()

        # Store in graph
        store = MoralGeometryStore()
        vector_id = await store.save_moral_vector(vector)

        result = {
            "status": "created",
            "vector_id": vector_id,
            "vector": vector.to_dict(),
            "magnitude": vector.magnitude,
            "dominant_dimension": vector.dominant_dimension,
        }

        return Response(
            message=f"Moral vector created:\n```json\n{json.dumps(result, indent=2)}\n```",
            break_loop=False
        )

    async def _evaluate(self, **kwargs) -> Response:
        """
        Evaluate an action/decision's moral position.

        Analyzes text description and maps to moral dimensions.
        """
        action = kwargs.get("action", "")
        context = kwargs.get("context", "")

        if not action:
            return Response(
                message="Please provide an 'action' to evaluate morally.",
                break_loop=False
            )

        # Create initial vector based on action analysis
        vector = MoralVector(
            name=f"eval_{action[:30]}",
            description=action,
            source_type="action",
        )

        # Analyze action for moral dimensions
        analysis = await self._analyze_moral_content(action, context)

        # Set dimensions from analysis
        for dim, value in analysis["dimensions"].items():
            vector.set_dimension(dim, value)

        vector.compute_magnitude()
        vector.find_dominant()

        # Store
        store = MoralGeometryStore()
        vector_id = await store.save_moral_vector(vector)

        result = {
            "action": action,
            "vector_id": vector_id,
            "moral_position": vector.to_dict(),
            "analysis": analysis["reasoning"],
            "dominant_dimension": vector.dominant_dimension,
            "magnitude": vector.magnitude,
        }

        return Response(
            message=f"Moral evaluation:\n```json\n{json.dumps(result, indent=2)}\n```",
            break_loop=False
        )

    async def _analyze_moral_content(self, action: str, context: str) -> dict:
        """
        Analyze action text for moral content.

        Uses heuristic analysis and optional agent delegation for
        complex moral reasoning.
        """
        dimensions = {}
        reasoning = []

        action_lower = action.lower()

        # Harm/Benefit analysis
        harm_words = ["harm", "hurt", "damage", "destroy", "kill", "attack", "abuse"]
        benefit_words = ["help", "heal", "save", "protect", "support", "benefit", "care"]

        harm_count = sum(1 for w in harm_words if w in action_lower)
        benefit_count = sum(1 for w in benefit_words if w in action_lower)

        if harm_count > 0 or benefit_count > 0:
            harm_benefit = (benefit_count - harm_count) / max(harm_count + benefit_count, 1)
            dimensions["harm_benefit"] = max(-1, min(1, harm_benefit))
            reasoning.append(f"Harm/benefit: {harm_benefit:.2f} (harm words: {harm_count}, benefit words: {benefit_count})")

        # Autonomy analysis
        autonomy_pos = ["choice", "freedom", "consent", "voluntary", "decide"]
        autonomy_neg = ["force", "compel", "coerce", "mandate", "require"]

        auto_pos = sum(1 for w in autonomy_pos if w in action_lower)
        auto_neg = sum(1 for w in autonomy_neg if w in action_lower)

        if auto_pos > 0 or auto_neg > 0:
            autonomy = (auto_pos - auto_neg) / max(auto_pos + auto_neg, 1)
            dimensions["autonomy"] = max(-1, min(1, autonomy))
            reasoning.append(f"Autonomy: {autonomy:.2f}")

        # Truth analysis
        truth_pos = ["honest", "truthful", "transparent", "disclose", "reveal"]
        truth_neg = ["lie", "deceive", "hide", "conceal", "mislead"]

        truth_pos_c = sum(1 for w in truth_pos if w in action_lower)
        truth_neg_c = sum(1 for w in truth_neg if w in action_lower)

        if truth_pos_c > 0 or truth_neg_c > 0:
            truth = (truth_pos_c - truth_neg_c) / max(truth_pos_c + truth_neg_c, 1)
            dimensions["truth"] = max(-1, min(1, truth))
            reasoning.append(f"Truth: {truth:.2f}")

        # Justice analysis
        justice_pos = ["fair", "equal", "just", "equity", "impartial"]
        justice_neg = ["unfair", "biased", "discriminate", "partial", "unjust"]

        just_pos = sum(1 for w in justice_pos if w in action_lower)
        just_neg = sum(1 for w in justice_neg if w in action_lower)

        if just_pos > 0 or just_neg > 0:
            justice = (just_pos - just_neg) / max(just_pos + just_neg, 1)
            dimensions["justice"] = max(-1, min(1, justice))
            reasoning.append(f"Justice: {justice:.2f}")

        # Compassion analysis
        comp_pos = ["compassion", "empathy", "care", "kindness", "gentle"]
        comp_neg = ["cruel", "callous", "indifferent", "cold", "harsh"]

        comp_pos_c = sum(1 for w in comp_pos if w in action_lower)
        comp_neg_c = sum(1 for w in comp_neg if w in action_lower)

        if comp_pos_c > 0 or comp_neg_c > 0:
            compassion = (comp_pos_c - comp_neg_c) / max(comp_pos_c + comp_neg_c, 1)
            dimensions["compassion"] = max(-1, min(1, compassion))
            reasoning.append(f"Compassion: {compassion:.2f}")

        # Fill remaining with neutral
        for dim in MoralDimension:
            if dim.value not in dimensions:
                dimensions[dim.value] = 0.0

        return {
            "dimensions": dimensions,
            "reasoning": reasoning if reasoning else ["No strong moral signals detected"],
        }

    async def _distance(self, **kwargs) -> Response:
        """Compute moral distance between two vectors."""
        vector_a_id = kwargs.get("vector_a_id", kwargs.get("a", ""))
        vector_b_id = kwargs.get("vector_b_id", kwargs.get("b", ""))

        if not vector_a_id or not vector_b_id:
            return Response(
                message="Please provide 'vector_a_id' and 'vector_b_id' to compute distance.",
                break_loop=False
            )

        store = MoralGeometryStore()
        vector_a = await store.load_moral_vector(vector_a_id)
        vector_b = await store.load_moral_vector(vector_b_id)

        if not vector_a:
            return Response(message=f"Vector not found: {vector_a_id}", break_loop=False)
        if not vector_b:
            return Response(message=f"Vector not found: {vector_b_id}", break_loop=False)

        engine = MoralGeometryEngine(self.agent)
        distance = engine.compute_distance(vector_a, vector_b)

        result = distance.to_dict()
        result["interpretation"] = self._interpret_distance(distance)

        return Response(
            message=f"Moral distance analysis:\n```json\n{json.dumps(result, indent=2)}\n```",
            break_loop=False
        )

    def _interpret_distance(self, distance: MoralDistance) -> str:
        """Generate human-readable interpretation of moral distance."""
        alignment = distance.alignment_score

        if alignment > 0.9:
            desc = "Strong moral alignment - positions are nearly identical"
        elif alignment > 0.7:
            desc = "Good moral alignment - positions are compatible"
        elif alignment > 0.5:
            desc = "Moderate alignment - some shared values"
        elif alignment > 0.3:
            desc = "Weak alignment - significant divergence"
        else:
            desc = "Moral opposition - positions are in conflict"

        if distance.conflict_dimensions:
            dims = ", ".join(distance.conflict_dimensions)
            desc += f". Key conflicts: {dims}"

        return desc

    async def _trajectory(self, **kwargs) -> Response:
        """Track or analyze moral trajectory."""
        action = kwargs.get("action", "add")  # add, analyze, get
        entity_id = kwargs.get("entity_id", "")
        vector_id = kwargs.get("vector_id", "")

        store = MoralGeometryStore()

        if action == "add":
            # Add waypoint to trajectory
            if not entity_id or not vector_id:
                return Response(
                    message="Provide 'entity_id' and 'vector_id' to add trajectory waypoint.",
                    break_loop=False
                )

            vector = await store.load_moral_vector(vector_id)
            if not vector:
                return Response(message=f"Vector not found: {vector_id}", break_loop=False)

            # Load or create trajectory
            trajectory = MoralTrajectory(
                entity_type="agent",
                entity_id=entity_id,
                name=f"trajectory_{entity_id}",
            )
            trajectory.add_waypoint(vector)

            traj_id = await store.save_trajectory(trajectory)

            return Response(
                message=f"Waypoint added to trajectory {traj_id}",
                break_loop=False
            )

        return Response(
            message=f"Unknown trajectory action: {action}. Use: add, analyze, get",
            break_loop=False
        )

    async def _decompose(self, **kwargs) -> Response:
        """Perform spectral decomposition of moral vectors."""
        vector_ids = kwargs.get("vector_ids", [])
        num_components = kwargs.get("components", 5)

        if not vector_ids:
            return Response(
                message="Provide 'vector_ids' (list) for spectral decomposition.",
                break_loop=False
            )

        store = MoralGeometryStore()
        vectors = []

        for vid in vector_ids:
            v = await store.load_moral_vector(vid)
            if v:
                vectors.append(v)

        if len(vectors) < 2:
            return Response(
                message="Need at least 2 vectors for spectral decomposition.",
                break_loop=False
            )

        engine = MoralGeometryEngine(self.agent)
        decomposition = await engine.spectral_decompose(vectors, num_components)

        # Save decomposition
        decomp_id = await store.save_spectral_decomposition(decomposition)

        result = {
            "decomposition_id": decomp_id,
            "analysis": decomposition.to_dict(),
            "interpretation": self._interpret_spectrum(decomposition),
        }

        return Response(
            message=f"Spectral decomposition:\n```json\n{json.dumps(result, indent=2)}\n```",
            break_loop=False
        )

    def _interpret_spectrum(self, decomp) -> str:
        """Interpret spectral decomposition results."""
        lines = []

        if decomp.resonance_score > 0.7:
            lines.append("High moral resonance - vectors are harmonically aligned")
        elif decomp.resonance_score > 0.4:
            lines.append("Moderate resonance - some moral harmony")
        else:
            lines.append("Low resonance - moral dissonance present")

        if decomp.harmonics:
            lines.append("Principal moral harmonics:")
            for h in decomp.harmonics[:3]:
                dims = ", ".join(d["dimension"] for d in h.get("dimensions", [])[:2])
                lines.append(f"  - {h.get('name')}: {h.get('description')} ({dims})")

        if decomp.dissonance_dimensions:
            lines.append(f"Dissonance in: {', '.join(decomp.dissonance_dimensions)}")

        return "\n".join(lines)

    async def _search(self, **kwargs) -> Response:
        """Search for moral vectors."""
        query = kwargs.get("query", "")
        limit = kwargs.get("limit", 10)

        if not query:
            return Response(
                message="Provide a 'query' to search moral vectors.",
                break_loop=False
            )

        store = MoralGeometryStore()
        vectors = await store.search_moral_vectors(query, limit)

        results = [v.to_dict() for v in vectors]

        return Response(
            message=f"Found {len(results)} moral vectors:\n```json\n{json.dumps(results, indent=2)}\n```",
            break_loop=False
        )

    async def _list_dimensions(self, **kwargs) -> Response:
        """List all moral dimensions with descriptions."""
        dimensions = []

        descriptions = {
            "harm_benefit": "Consequentialist: -1 (harm) to +1 (benefit)",
            "individual_collective": "Individual vs collective good",
            "short_long_term": "Immediate vs long-term consequences",
            "autonomy": "Respect for individual agency",
            "justice": "Fairness and equity",
            "fidelity": "Keeping promises, loyalty",
            "truth": "Honesty and transparency",
            "compassion": "Care and empathy",
            "courage": "Moral bravery",
            "prudence": "Practical wisdom",
            "temperance": "Moderation and self-control",
            "reciprocity": "Mutual exchange",
            "sanctity": "Purity, sacred values",
            "authority": "Legitimate hierarchy",
            "liberty": "Freedom from constraint",
        }

        for dim in MoralDimension:
            dimensions.append({
                "dimension": dim.value,
                "description": descriptions.get(dim.value, ""),
            })

        return Response(
            message=f"Moral dimensions ({len(dimensions)}):\n```json\n{json.dumps(dimensions, indent=2)}\n```",
            break_loop=False
        )
