"""
Input Recording Extension

This extension records user inputs to collective memory for audit
and learning purposes.
"""

import logging
from agent import Agent, LoopData

logger = logging.getLogger(__name__)


async def execute(agent: Agent, loop_data: LoopData, **kwargs):
    """Record user input to collective memory."""

    try:
        collective_memory = agent.get_data("collective_memory")
        if not collective_memory:
            return

        # Get the user message from loop_data
        user_message = None
        if hasattr(loop_data, "user_message") and loop_data.user_message:
            user_message = loop_data.user_message
        elif hasattr(loop_data, "message") and loop_data.message:
            user_message = loop_data.message

        if not user_message:
            return

        # Extract content
        content = user_message if isinstance(user_message, str) else str(user_message)

        # Record to memory
        agent_id = agent.get_data("agent_id")
        project_id = agent.get_data("project_id")

        await collective_memory.record_user_input(
            content=content,
            agent_id=agent_id,
            project_id=project_id
        )

        logger.debug(f"Recorded user input for agent {agent.number}")

    except Exception as e:
        logger.warning(f"Failed to record user input: {e}")
