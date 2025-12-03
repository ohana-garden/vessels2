"""
Moral Trajectory Extension - Post-execution moral tracking

Tracks the moral trajectory of the agent over time by recording
moral positions after significant tool executions.
"""

from typing import Any
from python.helpers.extension import Extension
from python.helpers.tool import Tool, Response


class MoralTrajectory(Extension):
    """Extension to track moral trajectory after tool execution."""

    async def execute(
        self,
        tool: Tool = None,
        response: Response = None,
        **kwargs: Any
    ):
        """
        Track moral position after tool execution.

        This extension:
        1. Checks if the tool was morally significant
        2. Records the moral vector for the action taken
        3. Updates the agent's moral trajectory
        """
        if tool is None or response is None:
            return

        # Check if we logged moral awareness for this tool
        moral_log = self.agent.get_data("moral_awareness_log") or []
        if not moral_log:
            return

        # Find the most recent entry for this tool
        recent_entry = None
        for entry in reversed(moral_log):
            if entry["tool"] == tool.name:
                recent_entry = entry
                break

        if not recent_entry or recent_entry["significance"] < 0.3:
            return

        # Record this as a trajectory waypoint
        await self._record_waypoint(tool, response, recent_entry)

    async def _record_waypoint(
        self,
        tool: Tool,
        response: Response,
        moral_entry: dict
    ) -> None:
        """Record a waypoint in the agent's moral trajectory."""
        try:
            from python.helpers.moral_geometry import (
                MoralVector,
                MoralDimension,
                MoralTrajectory as MoralTraj,
                MoralGeometryStore,
            )
            from python.helpers import guids

            # Create moral vector for this action
            vector = MoralVector(
                id=guids.generate_id(10),
                name=f"tool_{tool.name}",
                description=f"Tool execution: {tool.name}",
                source_type="tool_execution",
                source_id=tool.name,
            )

            # Set dimensions based on moral entry
            dimension_values = self._compute_dimension_values(tool, moral_entry)
            for dim, value in dimension_values.items():
                vector.set_dimension(dim, value)

            vector.compute_magnitude()
            vector.find_dominant()

            # Get or create trajectory for this agent
            agent_id = str(self.agent.number) if self.agent else "unknown"
            trajectory_key = f"moral_trajectory_{agent_id}"

            # Store vector (trajectory tracking happens in graph)
            store = MoralGeometryStore()
            await store.save_moral_vector(vector)

            # Update trajectory in agent data
            traj_points = self.agent.get_data(trajectory_key) or []
            traj_points.append({
                "vector_id": vector.id,
                "tool": tool.name,
                "significance": moral_entry["significance"],
                "timestamp": vector.timestamp,
            })
            # Keep last 50 waypoints
            self.agent.set_data(trajectory_key, traj_points[-50:])

        except Exception as e:
            # Don't let moral tracking errors affect tool execution
            from python.helpers.print_style import PrintStyle
            PrintStyle(font_color="#888888").print(
                f"[Moral Trajectory] Recording skipped: {e}"
            )

    def _compute_dimension_values(
        self,
        tool: Tool,
        moral_entry: dict
    ) -> dict[str, float]:
        """
        Compute dimension values based on tool and moral entry.

        Returns dict mapping dimension names to values.
        """
        values = {}
        args_str = str(tool.args).lower() if tool.args else ""

        # Start with neutral values for flagged dimensions
        for dim in moral_entry.get("dimensions", []):
            values[dim] = 0.0

        # Adjust based on action type
        warnings = " ".join(moral_entry.get("warnings", [])).lower()

        # Destructive actions lean negative on harm_benefit
        if "destructive" in warnings:
            values["harm_benefit"] = values.get("harm_benefit", 0.0) - 0.3

        # Privacy actions affect truth dimension
        if "privacy" in warnings:
            values["truth"] = values.get("truth", 0.0) - 0.1
            values["sanctity"] = values.get("sanctity", 0.0) - 0.2

        # Financial actions require fairness consideration
        if "financial" in warnings:
            values["justice"] = values.get("justice", 0.0) + 0.1  # Neutral-positive

        # User-affecting actions require compassion
        if "people" in warnings:
            values["compassion"] = values.get("compassion", 0.0) + 0.2

        # Check for positive indicators in args
        positive_words = ["help", "save", "protect", "create", "improve"]
        if any(w in args_str for w in positive_words):
            values["harm_benefit"] = values.get("harm_benefit", 0.0) + 0.4
            values["compassion"] = values.get("compassion", 0.0) + 0.2

        # Clamp all values to [-1, 1]
        for dim in values:
            values[dim] = max(-1.0, min(1.0, values[dim]))

        return values
