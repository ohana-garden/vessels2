"""
Agent Factory for Vessels A0 Framework

This module provides a factory for creating and managing agents with full
A0 framework integration:

1. Agent creation with ethical principles baked in
2. Agent configuration management
3. Agent lifecycle management
4. Integration with all framework components
5. Agent hierarchy and delegation
"""

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


class AgentType(Enum):
    """Types of agents."""
    PRIMARY = "primary"  # User-facing agent (A0)
    SUBORDINATE = "subordinate"  # Subordinate agent (A1, A2, etc.)
    BACKGROUND = "background"  # Background task agent
    SPECIALIZED = "specialized"  # Specialized task agent
    A2A = "a2a"  # Agent-to-agent communication agent


class AgentStatus(Enum):
    """Status of an agent."""
    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"


@dataclass
class AgentCapability:
    """A capability that an agent has."""
    name: str
    description: str
    enabled: bool = True
    config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled,
            "config": self.config
        }


@dataclass
class A0AgentConfig:
    """Configuration for an A0 agent."""

    # Identity
    agent_id: str
    name: str = "Vessels Agent"
    profile: str = "vessels"

    # Type and hierarchy
    agent_type: AgentType = AgentType.PRIMARY
    agent_number: int = 0  # 0 for primary, 1+ for subordinates

    # Model configuration
    chat_model: str = ""
    utility_model: str = ""
    embedding_model: str = ""
    browser_model: str = ""

    # Framework integration
    ethics_enabled: bool = True
    memory_enabled: bool = True
    project_id: Optional[str] = None

    # Capabilities
    capabilities: List[AgentCapability] = field(default_factory=list)

    # Resource limits
    max_iterations: int = 50
    max_subordinates: int = 5
    max_tool_calls_per_iteration: int = 10

    # Ethical constraints
    ethical_constraints: List[str] = field(default_factory=list)

    # Custom settings
    settings: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "profile": self.profile,
            "agent_type": self.agent_type.value,
            "agent_number": self.agent_number,
            "chat_model": self.chat_model,
            "utility_model": self.utility_model,
            "embedding_model": self.embedding_model,
            "browser_model": self.browser_model,
            "ethics_enabled": self.ethics_enabled,
            "memory_enabled": self.memory_enabled,
            "project_id": self.project_id,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "max_iterations": self.max_iterations,
            "max_subordinates": self.max_subordinates,
            "max_tool_calls_per_iteration": self.max_tool_calls_per_iteration,
            "ethical_constraints": self.ethical_constraints,
            "settings": self.settings,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'A0AgentConfig':
        return cls(
            agent_id=data["agent_id"],
            name=data.get("name", "Vessels Agent"),
            profile=data.get("profile", "vessels"),
            agent_type=AgentType(data.get("agent_type", "primary")),
            agent_number=data.get("agent_number", 0),
            chat_model=data.get("chat_model", ""),
            utility_model=data.get("utility_model", ""),
            embedding_model=data.get("embedding_model", ""),
            browser_model=data.get("browser_model", ""),
            ethics_enabled=data.get("ethics_enabled", True),
            memory_enabled=data.get("memory_enabled", True),
            project_id=data.get("project_id"),
            capabilities=[AgentCapability(**c) for c in data.get("capabilities", [])],
            max_iterations=data.get("max_iterations", 50),
            max_subordinates=data.get("max_subordinates", 5),
            max_tool_calls_per_iteration=data.get("max_tool_calls_per_iteration", 10),
            ethical_constraints=data.get("ethical_constraints", []),
            settings=data.get("settings", {}),
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now()
        )


@dataclass
class A0AgentInstance:
    """Represents a running agent instance."""
    config: A0AgentConfig
    status: AgentStatus = AgentStatus.INITIALIZING
    underlying_agent: Any = None  # The actual Agent instance from agent.py
    context: Any = None  # AgentContext
    subordinates: List['A0AgentInstance'] = field(default_factory=list)
    message_count: int = 0
    tool_calls: int = 0
    errors: int = 0
    started_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.config.agent_id,
            "name": self.config.name,
            "status": self.status.value,
            "agent_type": self.config.agent_type.value,
            "agent_number": self.config.agent_number,
            "subordinates": [s.config.agent_id for s in self.subordinates],
            "message_count": self.message_count,
            "tool_calls": self.tool_calls,
            "errors": self.errors,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None
        }


class AgentFactory:
    """
    Factory for creating and managing A0 agents.

    This singleton provides:
    - Agent creation with full framework integration
    - Agent lifecycle management
    - Agent registry
    - Ethics validation on agent creation
    """

    _instance: Optional['AgentFactory'] = None
    _lock = asyncio.Lock()

    # Default capabilities for all agents
    DEFAULT_CAPABILITIES = [
        AgentCapability(name="memory", description="Access to collective memory"),
        AgentCapability(name="tools", description="Tool execution capability"),
        AgentCapability(name="subordinates", description="Ability to create subordinate agents"),
        AgentCapability(name="mcp", description="MCP server access"),
        AgentCapability(name="instruments", description="Instrument access"),
    ]

    def __init__(self):
        self._agents: Dict[str, A0AgentInstance] = {}
        self._collective_memory = None
        self._ethics_engine = None
        self._project_manager = None
        self._prompt_manager = None
        self._tool_registry = None
        self._initialized = False
        self._hooks: Dict[str, List[Callable]] = {
            "agent_created": [],
            "agent_started": [],
            "agent_stopped": [],
            "agent_error": [],
            "subordinate_created": [],
        }

    @classmethod
    async def get_instance(cls) -> 'AgentFactory':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize the agent factory."""
        if self._initialized:
            return

        # Initialize framework components
        try:
            from python.helpers.collective_memory import CollectiveMemory
            self._collective_memory = await CollectiveMemory.get_instance()
        except Exception as e:
            logger.warning(f"Collective memory not available: {e}")

        try:
            from python.helpers.ethics import EthicsEngine
            self._ethics_engine = await EthicsEngine.get_instance()
        except Exception as e:
            logger.warning(f"Ethics engine not available: {e}")

        try:
            from python.helpers.projects import ProjectManager
            self._project_manager = await ProjectManager.get_instance()
        except Exception as e:
            logger.warning(f"Project manager not available: {e}")

        try:
            from python.helpers.prompt_manager import PromptManager
            self._prompt_manager = await PromptManager.get_instance()
        except Exception as e:
            logger.warning(f"Prompt manager not available: {e}")

        try:
            from python.helpers.tool_framework import ToolRegistry
            self._tool_registry = await ToolRegistry.get_instance()
        except Exception as e:
            logger.warning(f"Tool registry not available: {e}")

        self._initialized = True
        logger.info("AgentFactory initialized")

    def add_hook(self, hook_name: str, callback: Callable):
        """Add a hook callback."""
        if hook_name in self._hooks:
            self._hooks[hook_name].append(callback)

    async def _run_hooks(self, hook_name: str, data: Any):
        """Run registered hooks."""
        for hook in self._hooks.get(hook_name, []):
            try:
                result = hook(data)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(f"Hook {hook_name} failed: {e}")

    def _generate_agent_id(self, name: str) -> str:
        """Generate a unique agent ID."""
        unique = f"{name}:{datetime.now().isoformat()}:{uuid.uuid4().hex[:8]}"
        return f"agent_{hashlib.sha256(unique.encode()).hexdigest()[:12]}"

    async def _validate_creation(self, config: A0AgentConfig) -> bool:
        """Validate agent creation against ethical principles."""
        if not self._ethics_engine or not config.ethics_enabled:
            return True

        try:
            validation = await self._ethics_engine.validate(
                action_type="agent_create",
                data={
                    "name": config.name,
                    "profile": config.profile,
                    "agent_type": config.agent_type.value,
                    "capabilities": [c.name for c in config.capabilities]
                },
                context={"project_id": config.project_id}
            )
            return validation.is_approved
        except Exception as e:
            logger.error(f"Ethics validation failed: {e}")
            return False

    async def create_agent(
        self,
        name: str = "Vessels Agent",
        profile: str = "vessels",
        agent_type: AgentType = AgentType.PRIMARY,
        project_id: Optional[str] = None,
        capabilities: Optional[List[AgentCapability]] = None,
        ethical_constraints: Optional[List[str]] = None,
        settings: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Optional[A0AgentInstance]:
        """
        Create a new A0 agent with full framework integration.

        Args:
            name: Agent name
            profile: Agent profile (vessels, developer, researcher, hacker)
            agent_type: Type of agent
            project_id: Optional project context
            capabilities: Agent capabilities (defaults are added automatically)
            ethical_constraints: Additional ethical constraints
            settings: Additional settings
            **kwargs: Additional config options

        Returns:
            A0AgentInstance or None if creation fails
        """
        agent_id = self._generate_agent_id(name)

        # Merge capabilities with defaults
        all_capabilities = list(self.DEFAULT_CAPABILITIES)
        if capabilities:
            for cap in capabilities:
                if cap.name not in [c.name for c in all_capabilities]:
                    all_capabilities.append(cap)

        # Create config
        config = A0AgentConfig(
            agent_id=agent_id,
            name=name,
            profile=profile,
            agent_type=agent_type,
            agent_number=kwargs.get("agent_number", 0),
            project_id=project_id,
            capabilities=all_capabilities,
            ethical_constraints=ethical_constraints or [],
            settings=settings or {},
            **{k: v for k, v in kwargs.items() if k in A0AgentConfig.__dataclass_fields__}
        )

        # Validate creation
        if not await self._validate_creation(config):
            logger.error(f"Agent creation blocked by ethics validation: {agent_id}")
            return None

        # Create the agent instance
        instance = A0AgentInstance(
            config=config,
            status=AgentStatus.INITIALIZING
        )

        # Create underlying Agent from agent.py
        try:
            from agent import Agent, AgentContext
            from initialize import initialize_agent

            # Get agent config from framework
            agent_config = initialize_agent()

            # Override with our settings
            agent_config.profile = profile
            if config.chat_model:
                agent_config.chat_model = config.chat_model

            # Create context
            context = AgentContext(
                config=agent_config,
                id=agent_id,
                name=name
            )

            # Create agent
            underlying_agent = Agent(number=config.agent_number, config=agent_config)

            instance.underlying_agent = underlying_agent
            instance.context = context
            instance.status = AgentStatus.READY
            instance.started_at = datetime.now()

            # Set up memory context
            if self._collective_memory and config.memory_enabled:
                self._collective_memory.set_context(
                    agent_id=agent_id,
                    project_id=project_id
                )

        except Exception as e:
            logger.error(f"Failed to create underlying agent: {e}")
            instance.status = AgentStatus.ERROR

        # Register the agent
        self._agents[agent_id] = instance

        # Record creation
        if self._collective_memory:
            from python.helpers.collective_memory import MemoryType, MemoryScope, MemoryPriority
            await self._collective_memory.store(
                memory_type=MemoryType.EVENT,
                content={
                    "event": "agent_created",
                    "agent_id": agent_id,
                    "name": name,
                    "profile": profile,
                    "agent_type": agent_type.value
                },
                scope=MemoryScope.GLOBAL,
                priority=MemoryPriority.NORMAL,
                tags=["agent", "created", profile],
                agent_id=agent_id,
                project_id=project_id
            )

        await self._run_hooks("agent_created", instance)

        logger.info(f"Created agent: {agent_id} ({name}, {profile})")
        return instance

    async def create_subordinate(
        self,
        superior_agent_id: str,
        name: Optional[str] = None,
        profile: Optional[str] = None,
        **kwargs
    ) -> Optional[A0AgentInstance]:
        """Create a subordinate agent for an existing agent."""
        superior = self._agents.get(superior_agent_id)
        if not superior:
            logger.error(f"Superior agent not found: {superior_agent_id}")
            return None

        # Check subordinate limit
        if len(superior.subordinates) >= superior.config.max_subordinates:
            logger.error(f"Subordinate limit reached for agent: {superior_agent_id}")
            return None

        # Create subordinate
        subordinate_name = name or f"{superior.config.name} Sub-{len(superior.subordinates) + 1}"
        subordinate_profile = profile or superior.config.profile

        subordinate = await self.create_agent(
            name=subordinate_name,
            profile=subordinate_profile,
            agent_type=AgentType.SUBORDINATE,
            agent_number=superior.config.agent_number + 1,
            project_id=superior.config.project_id,
            **kwargs
        )

        if subordinate:
            superior.subordinates.append(subordinate)
            await self._run_hooks("subordinate_created", {
                "superior": superior,
                "subordinate": subordinate
            })

        return subordinate

    def get_agent(self, agent_id: str) -> Optional[A0AgentInstance]:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def list_agents(
        self,
        agent_type: Optional[AgentType] = None,
        status: Optional[AgentStatus] = None,
        project_id: Optional[str] = None
    ) -> List[A0AgentInstance]:
        """List agents with optional filters."""
        agents = list(self._agents.values())

        if agent_type:
            agents = [a for a in agents if a.config.agent_type == agent_type]
        if status:
            agents = [a for a in agents if a.status == status]
        if project_id:
            agents = [a for a in agents if a.config.project_id == project_id]

        return agents

    async def terminate_agent(self, agent_id: str) -> bool:
        """Terminate an agent."""
        agent = self._agents.get(agent_id)
        if not agent:
            return False

        # Terminate subordinates first
        for sub in agent.subordinates:
            await self.terminate_agent(sub.config.agent_id)

        agent.status = AgentStatus.TERMINATED

        # Record termination
        if self._collective_memory:
            from python.helpers.collective_memory import MemoryType, MemoryScope, MemoryPriority
            await self._collective_memory.store(
                memory_type=MemoryType.EVENT,
                content={
                    "event": "agent_terminated",
                    "agent_id": agent_id,
                    "message_count": agent.message_count,
                    "tool_calls": agent.tool_calls
                },
                scope=MemoryScope.GLOBAL,
                priority=MemoryPriority.NORMAL,
                tags=["agent", "terminated"],
                agent_id=agent_id
            )

        await self._run_hooks("agent_stopped", agent)

        logger.info(f"Terminated agent: {agent_id}")
        return True

    async def get_ethical_prompt_for_agent(self, agent_id: str) -> str:
        """Get the ethical prompt for an agent."""
        agent = self._agents.get(agent_id)
        if not agent or not self._prompt_manager:
            return ""

        return await self._prompt_manager.get_ethical_prompt()

    async def get_statistics(self) -> Dict[str, Any]:
        """Get agent factory statistics."""
        return {
            "total_agents": len(self._agents),
            "by_type": {
                at.value: len([a for a in self._agents.values() if a.config.agent_type == at])
                for at in AgentType
            },
            "by_status": {
                st.value: len([a for a in self._agents.values() if a.status == st])
                for st in AgentStatus
            },
            "total_messages": sum(a.message_count for a in self._agents.values()),
            "total_tool_calls": sum(a.tool_calls for a in self._agents.values()),
            "total_errors": sum(a.errors for a in self._agents.values())
        }


# Convenience functions
async def get_agent_factory() -> AgentFactory:
    """Get the agent factory instance."""
    return await AgentFactory.get_instance()


async def create_agent(
    name: str = "Vessels Agent",
    profile: str = "vessels",
    **kwargs
) -> Optional[A0AgentInstance]:
    """Create a new agent."""
    factory = await get_agent_factory()
    return await factory.create_agent(name=name, profile=profile, **kwargs)


async def get_agent(agent_id: str) -> Optional[A0AgentInstance]:
    """Get an agent by ID."""
    factory = await get_agent_factory()
    return factory.get_agent(agent_id)
