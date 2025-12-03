"""
A0 Extension - Save Tool Call Results to Graph

Stores large tool outputs in FalkorDB graph instead of filesystem.
Following A0 pattern: all persistence goes through graph_store.
"""

from typing import Any
from python.helpers.extension import Extension
from python.helpers.graph_store import GraphStore

LEN_MIN = 500


class SaveToolCallToGraph(Extension):
    """Save large tool call results to graph storage."""

    async def execute(self, data: dict[str, Any] | None = None, **kwargs):
        if not data:
            return

        # Get tool call result
        result = data.get("tool_result") if isinstance(data, dict) else None
        if result is None:
            return

        # Skip short results
        if len(str(result)) < LEN_MIN:
            return

        # Get context ID
        context_id = self.agent.context.id if self.agent.context else "unknown"

        # Get tool name from data or agent state
        tool_name = data.get("tool_name", "unknown")

        # Save to graph store
        try:
            graph_store = await GraphStore.get_instance()
            result_id = await graph_store.save_tool_result(
                context_id=context_id,
                tool_name=tool_name,
                content=str(result),
                metadata={
                    "agent_name": self.agent.agent_name,
                    "agent_number": self.agent.number,
                },
            )

            # Store the reference ID instead of file path
            data["tool_result_id"] = result_id

        except Exception as e:
            # Fall back gracefully - don't break tool execution
            from python.helpers.print_style import PrintStyle
            PrintStyle.error(f"Failed to save tool result to graph: {e}")
