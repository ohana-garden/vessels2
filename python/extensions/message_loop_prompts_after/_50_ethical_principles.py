"""
Ethical Principles Injection Extension

This extension injects ethical principles into the agent's prompts,
ensuring that ethical guidelines are always present in the agent's context.
"""

import logging
from agent import Agent, LoopData

logger = logging.getLogger(__name__)


async def execute(agent: Agent, loop_data: LoopData, **kwargs):
    """Inject ethical principles into prompts."""

    # Only inject for top-level prompts (not every iteration)
    if loop_data.iteration > 0:
        return

    try:
        prompt_manager = agent.get_data("prompt_manager")
        if not prompt_manager:
            return

        # Get ethical prompt
        ethical_prompt = await prompt_manager.get_ethical_prompt()

        if ethical_prompt:
            # Add to system prompt
            if hasattr(loop_data, "system_prompt"):
                loop_data.system_prompt = ethical_prompt + "\n\n" + loop_data.system_prompt
            elif hasattr(loop_data, "prompts") and isinstance(loop_data.prompts, list):
                # Prepend ethical prompt to prompts list
                loop_data.prompts.insert(0, {
                    "role": "system",
                    "content": ethical_prompt
                })

            logger.debug("Ethical principles injected into prompts")

    except Exception as e:
        logger.warning(f"Failed to inject ethical principles: {e}")
