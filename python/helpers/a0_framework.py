"""
A0 Framework - Central Integration Module for Vessels

This module provides the central entry point for the A0 Framework, integrating
all components into a cohesive system:

Components:
- Ethics Engine: Validates all actions against ethical principles
- Collective Memory: Records all I/O for audit and learning
- Projects: Organizes agent activities and resources
- Instruments: External tools and services
- A2A: Agent-to-agent communication
- MCP: Model Context Protocol integration
- Prompts: Versioned prompt management
- Tools: Standardized tool framework
- Agent Factory: Agent lifecycle management

Usage:
    from python.helpers.a0_framework import A0Framework

    # Initialize the framework
    framework = await A0Framework.initialize()

    # Access components
    ethics = framework.ethics
    memory = framework.memory
    projects = framework.projects
    ...
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class A0FrameworkConfig:
    """Configuration for the A0 Framework."""
    ethics_enabled: bool = True
    memory_enabled: bool = True
    projects_enabled: bool = True
    instruments_enabled: bool = True
    a2a_enabled: bool = True
    mcp_enabled: bool = True
    prompts_enabled: bool = True
    tools_enabled: bool = True


class A0Framework:
    """
    Central A0 Framework integration class.

    This singleton provides access to all framework components and
    ensures they are properly initialized and coordinated.
    """

    _instance: Optional['A0Framework'] = None
    _lock = asyncio.Lock()

    VERSION = "1.0.0"
    NAME = "Vessels A0 Framework"

    def __init__(self):
        self._config: Optional[A0FrameworkConfig] = None
        self._ethics = None
        self._memory = None
        self._projects = None
        self._instruments = None
        self._a2a = None
        self._mcp = None
        self._prompts = None
        self._tools = None
        self._agents = None
        self._initialized = False
        self._initialization_time: Optional[datetime] = None

    @classmethod
    async def get_instance(cls) -> 'A0Framework':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    async def initialize(
        cls,
        config: Optional[A0FrameworkConfig] = None
    ) -> 'A0Framework':
        """
        Initialize the A0 Framework with all components.

        Args:
            config: Optional configuration override

        Returns:
            Initialized A0Framework instance
        """
        instance = await cls.get_instance()
        if not instance._initialized:
            await instance._initialize(config)
        return instance

    async def _initialize(self, config: Optional[A0FrameworkConfig] = None):
        """Initialize all framework components."""
        if self._initialized:
            return

        self._config = config or A0FrameworkConfig()
        start_time = datetime.now()

        logger.info(f"Initializing {self.NAME} v{self.VERSION}...")

        # Initialize components in order of dependencies

        # 1. Ethics Engine (no dependencies)
        if self._config.ethics_enabled:
            try:
                from python.helpers.ethics import EthicsEngine
                self._ethics = await EthicsEngine.get_instance()
                logger.info("Ethics Engine initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Ethics Engine: {e}")

        # 2. Collective Memory (depends on ethics for validation)
        if self._config.memory_enabled:
            try:
                from python.helpers.collective_memory import CollectiveMemory
                self._memory = await CollectiveMemory.get_instance()
                logger.info("Collective Memory initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Collective Memory: {e}")

        # 3. Projects (depends on memory, ethics)
        if self._config.projects_enabled:
            try:
                from python.helpers.projects import ProjectManager
                self._projects = await ProjectManager.get_instance()
                logger.info("Project Manager initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Project Manager: {e}")

        # 4. Instruments (depends on memory, ethics)
        if self._config.instruments_enabled:
            try:
                from python.helpers.instruments import InstrumentRegistry
                self._instruments = await InstrumentRegistry.get_instance()
                logger.info("Instrument Registry initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Instrument Registry: {e}")

        # 5. A2A Framework (depends on memory, ethics)
        if self._config.a2a_enabled:
            try:
                from python.helpers.a2a_framework import A2AFramework
                self._a2a = await A2AFramework.get_instance()
                logger.info("A2A Framework initialized")
            except Exception as e:
                logger.error(f"Failed to initialize A2A Framework: {e}")

        # 6. MCP Framework (depends on memory, ethics)
        if self._config.mcp_enabled:
            try:
                from python.helpers.mcp_framework import MCPFramework
                self._mcp = await MCPFramework.get_instance()
                logger.info("MCP Framework initialized")
            except Exception as e:
                logger.error(f"Failed to initialize MCP Framework: {e}")

        # 7. Prompt Manager (depends on memory, ethics)
        if self._config.prompts_enabled:
            try:
                from python.helpers.prompt_manager import PromptManager
                self._prompts = await PromptManager.get_instance()
                logger.info("Prompt Manager initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Prompt Manager: {e}")

        # 8. Tool Registry (depends on memory, ethics)
        if self._config.tools_enabled:
            try:
                from python.helpers.tool_framework import ToolRegistry
                self._tools = await ToolRegistry.get_instance()
                logger.info("Tool Registry initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Tool Registry: {e}")

        # 9. Agent Factory (depends on all above)
        try:
            from python.helpers.agent_factory import AgentFactory
            self._agents = await AgentFactory.get_instance()
            logger.info("Agent Factory initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Agent Factory: {e}")

        self._initialized = True
        self._initialization_time = datetime.now()

        elapsed = (self._initialization_time - start_time).total_seconds()
        logger.info(f"{self.NAME} v{self.VERSION} initialized in {elapsed:.2f}s")

    # Component accessors

    @property
    def ethics(self):
        """Get the Ethics Engine."""
        return self._ethics

    @property
    def memory(self):
        """Get the Collective Memory system."""
        return self._memory

    @property
    def projects(self):
        """Get the Project Manager."""
        return self._projects

    @property
    def instruments(self):
        """Get the Instrument Registry."""
        return self._instruments

    @property
    def a2a(self):
        """Get the A2A Framework."""
        return self._a2a

    @property
    def mcp(self):
        """Get the MCP Framework."""
        return self._mcp

    @property
    def prompts(self):
        """Get the Prompt Manager."""
        return self._prompts

    @property
    def tools(self):
        """Get the Tool Registry."""
        return self._tools

    @property
    def agents(self):
        """Get the Agent Factory."""
        return self._agents

    @property
    def is_initialized(self) -> bool:
        """Check if the framework is initialized."""
        return self._initialized

    async def get_status(self) -> Dict[str, Any]:
        """Get the status of all framework components."""
        return {
            "framework": {
                "name": self.NAME,
                "version": self.VERSION,
                "initialized": self._initialized,
                "initialization_time": self._initialization_time.isoformat() if self._initialization_time else None
            },
            "components": {
                "ethics": self._ethics is not None,
                "memory": self._memory is not None,
                "projects": self._projects is not None,
                "instruments": self._instruments is not None,
                "a2a": self._a2a is not None,
                "mcp": self._mcp is not None,
                "prompts": self._prompts is not None,
                "tools": self._tools is not None,
                "agents": self._agents is not None
            }
        }

    async def get_statistics(self) -> Dict[str, Any]:
        """Get statistics from all components."""
        stats = {
            "framework": await self.get_status()
        }

        if self._ethics:
            stats["ethics"] = self._ethics.get_violation_stats()

        if self._memory:
            stats["memory"] = await self._memory.get_statistics()

        if self._instruments:
            stats["instruments"] = {
                "registered": self._instruments.list_registered(),
                "available": self._instruments.list_available()
            }

        if self._a2a:
            stats["a2a"] = await self._a2a.get_statistics()

        if self._mcp:
            stats["mcp"] = await self._mcp.get_statistics()

        if self._prompts:
            stats["prompts"] = await self._prompts.get_statistics()

        if self._tools:
            stats["tools"] = await self._tools.get_statistics()

        if self._agents:
            stats["agents"] = await self._agents.get_statistics()

        return stats

    async def shutdown(self):
        """Shutdown all framework components."""
        logger.info("Shutting down A0 Framework...")

        if self._a2a:
            await self._a2a.close()

        # Add other cleanup as needed

        self._initialized = False
        logger.info("A0 Framework shutdown complete")


# Convenience functions
async def initialize_a0_framework(
    config: Optional[A0FrameworkConfig] = None
) -> A0Framework:
    """Initialize the A0 Framework."""
    return await A0Framework.initialize(config)


async def get_a0_framework() -> A0Framework:
    """Get the A0 Framework instance."""
    return await A0Framework.get_instance()


# Export all component types for convenience
__all__ = [
    "A0Framework",
    "A0FrameworkConfig",
    "initialize_a0_framework",
    "get_a0_framework",
]
