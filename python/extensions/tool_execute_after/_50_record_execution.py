"""
Tool Execution Recording Extension

This extension records tool executions to collective memory for
audit and analytics purposes.
"""

import logging
import time
from agent import Agent

logger = logging.getLogger(__name__)


async def execute(
    agent: Agent,
    tool_name: str = "",
    tool_args: dict = None,
    tool_result: any = None,
    success: bool = True,
    execution_time: float = 0,
    **kwargs
):
    """Record tool execution to collective memory."""

    tool_args = tool_args or {}

    try:
        collective_memory = agent.get_data("collective_memory")
        if not collective_memory:
            return

        agent_id = agent.get_data("agent_id")
        project_id = agent.get_data("project_id")

        # Record the tool execution
        await collective_memory.record_tool_execution(
            tool_name=tool_name,
            tool_input=tool_args,
            tool_output=tool_result,
            execution_time=execution_time,
            success=success,
            agent_id=agent_id,
            project_id=project_id
        )

        logger.debug(f"Recorded tool execution: {tool_name} (success={success})")

    except Exception as e:
        logger.warning(f"Failed to record tool execution: {e}")
