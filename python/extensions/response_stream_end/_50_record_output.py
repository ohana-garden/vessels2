"""
Output Recording Extension

This extension records agent outputs to collective memory for audit
and learning purposes.
"""

import logging
from agent import Agent

logger = logging.getLogger(__name__)


async def execute(agent: Agent, response: str = "", **kwargs):
    """Record agent output to collective memory."""

    try:
        collective_memory = agent.get_data("collective_memory")
        if not collective_memory:
            return

        if not response:
            return

        # Record to memory
        agent_id = agent.get_data("agent_id")
        project_id = agent.get_data("project_id")

        await collective_memory.record_agent_output(
            content=response,
            agent_id=agent_id,
            project_id=project_id
        )

        logger.debug(f"Recorded agent output for agent {agent.number}")

    except Exception as e:
        logger.warning(f"Failed to record agent output: {e}")
