"""
A0 Framework Integration Extension

This extension initializes the A0 framework components when an agent is created,
ensuring that ethics, collective memory, and other framework components are
properly integrated into the agent lifecycle.
"""

import logging
from agent import Agent

logger = logging.getLogger(__name__)


async def execute(agent: Agent, **kwargs):
    """Initialize A0 framework integration for the agent."""

    # Initialize collective memory context
    try:
        from python.helpers.collective_memory import CollectiveMemory
        memory = await CollectiveMemory.get_instance()

        agent_id = f"agent_{agent.number}"
        project_id = agent.config.get("project_id") if hasattr(agent.config, "get") else None

        memory.set_context(
            agent_id=agent_id,
            project_id=project_id
        )

        # Store on agent.data for access by tools
        agent.set_data("collective_memory", memory)
        agent.set_data("agent_id", agent_id)

        logger.debug(f"Collective memory initialized for agent {agent_id}")

    except Exception as e:
        logger.warning(f"Failed to initialize collective memory: {e}")

    # Initialize ethics engine
    try:
        from python.helpers.ethics import EthicsEngine
        ethics = await EthicsEngine.get_instance()

        agent.set_data("ethics_engine", ethics)

        logger.debug(f"Ethics engine initialized for agent {agent.number}")

    except Exception as e:
        logger.warning(f"Failed to initialize ethics engine: {e}")

    # Initialize prompt manager
    try:
        from python.helpers.prompt_manager import PromptManager
        prompts = await PromptManager.get_instance()

        agent.set_data("prompt_manager", prompts)

        logger.debug(f"Prompt manager initialized for agent {agent.number}")

    except Exception as e:
        logger.warning(f"Failed to initialize prompt manager: {e}")

    # Initialize tool registry
    try:
        from python.helpers.tool_framework import ToolRegistry
        tools = await ToolRegistry.get_instance()

        agent.set_data("tool_registry", tools)

        logger.debug(f"Tool registry initialized for agent {agent.number}")

    except Exception as e:
        logger.warning(f"Failed to initialize tool registry: {e}")

    # Initialize instrument registry
    try:
        from python.helpers.instruments import InstrumentRegistry
        instruments = await InstrumentRegistry.get_instance()

        agent.set_data("instrument_registry", instruments)

        logger.debug(f"Instrument registry initialized for agent {agent.number}")

    except Exception as e:
        logger.warning(f"Failed to initialize instrument registry: {e}")

    # Store framework version
    agent.set_data("a0_framework_version", "1.0.0")
    agent.set_data("a0_framework_enabled", True)

    logger.info(f"A0 framework integration complete for agent {agent.number}")
