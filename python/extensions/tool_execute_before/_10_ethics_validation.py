"""
Tool Ethics Validation Extension

This extension validates tool executions against ethical principles
before they are executed.
"""

import logging
from agent import Agent

logger = logging.getLogger(__name__)


async def execute(agent: Agent, tool_name: str = "", tool_args: dict = None, **kwargs):
    """Validate tool execution against ethical principles."""

    tool_args = tool_args or {}

    try:
        ethics_engine = agent.get_data("ethics_engine")
        if not ethics_engine:
            return  # Continue without validation if ethics not available

        agent_id = agent.get_data("agent_id")
        project_id = agent.get_data("project_id")

        # Validate the tool call
        validation = await ethics_engine.validate(
            action_type=f"tool_{tool_name}",
            data={
                "tool_name": tool_name,
                "arguments": tool_args
            },
            context={
                "agent_id": agent_id,
                "project_id": project_id,
                "agent_number": agent.number
            }
        )

        if validation.is_blocked:
            logger.warning(f"Tool {tool_name} blocked by ethics: {validation.explanation}")
            # Raise exception to prevent tool execution
            raise PermissionError(f"Tool execution blocked by ethical validation: {validation.explanation}")

        if not validation.is_approved:
            logger.info(f"Tool {tool_name} has ethical warnings: {validation.explanation}")

    except PermissionError:
        raise  # Re-raise permission errors
    except Exception as e:
        logger.warning(f"Ethics validation failed for tool {tool_name}: {e}")
        # Continue with execution if validation fails (fail-open)
