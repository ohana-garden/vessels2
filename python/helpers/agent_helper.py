"""
A0 Framework - Agent Helper Base Class

Base class for helper modules that work with Agent instances.
Provides consistent patterns for state management and async operations.

Usage:
    from python.helpers.agent_helper import AgentHelper

    class MyHelper(AgentHelper):
        @classmethod
        async def get(cls, agent: Agent) -> "MyHelper":
            return await cls._get_or_create(agent, "_my_helper_state")

        async def do_something(self) -> str:
            # Access agent via self.agent
            return await self._async_operation()
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Any, Optional, TYPE_CHECKING
import asyncio

if TYPE_CHECKING:
    from agent import Agent


T = TypeVar("T", bound="AgentHelper")


class AgentHelper(ABC):
    """
    Base class for A0 helper modules that maintain state per-agent.

    Provides:
    - Consistent state storage pattern using agent.data
    - Factory pattern for helper retrieval/creation
    - Async operation support
    - Cleanup lifecycle
    """

    def __init__(self, agent: "Agent"):
        """Initialize helper with agent reference."""
        self.agent = agent

    @classmethod
    async def _get_or_create(
        cls: type[T],
        agent: "Agent",
        state_key: str,
        **init_kwargs: Any
    ) -> T:
        """
        Get existing helper instance or create new one.

        Args:
            agent: The agent to associate with
            state_key: Key to use in agent.data for storage
            **init_kwargs: Additional kwargs for initialization

        Returns:
            Helper instance (cached or newly created)
        """
        existing = agent.get_data(state_key)
        if existing is not None and isinstance(existing, cls):
            return existing

        instance = cls(agent, **init_kwargs)
        await instance._initialize()
        agent.set_data(state_key, instance)
        return instance

    async def _initialize(self) -> None:
        """
        Override to perform async initialization after creation.
        Called automatically by _get_or_create.
        """
        pass

    async def cleanup(self) -> None:
        """
        Override to perform cleanup when helper is disposed.
        Should release resources, close connections, etc.
        """
        pass

    def _store(self, key: str, value: Any) -> None:
        """Store a value in agent's data store with helper prefix."""
        full_key = f"_{self.__class__.__name__}_{key}"
        self.agent.set_data(full_key, value)

    def _retrieve(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from agent's data store with helper prefix."""
        full_key = f"_{self.__class__.__name__}_{key}"
        return self.agent.get_data(full_key) or default


class StatefulHelper(AgentHelper, Generic[T]):
    """
    Helper that manages a typed state object.

    Usage:
        @dataclass
        class BrowserState:
            session: Optional[BrowserSession] = None
            task: Optional[DeferredTask] = None

        class BrowserHelper(StatefulHelper[BrowserState]):
            STATE_KEY = "_browser_state"

            @classmethod
            async def get(cls, agent: Agent) -> "BrowserHelper":
                return await cls._get_or_create(agent, cls.STATE_KEY)

            def _create_initial_state(self) -> BrowserState:
                return BrowserState()
    """

    STATE_KEY: str = "_helper_state"

    def __init__(self, agent: "Agent"):
        super().__init__(agent)
        self._state: Optional[Any] = None

    @property
    def state(self) -> Any:
        """Get the current state object."""
        if self._state is None:
            self._state = self._create_initial_state()
        return self._state

    @abstractmethod
    def _create_initial_state(self) -> Any:
        """Create the initial state object. Override in subclasses."""
        pass

    async def reset_state(self) -> None:
        """Reset to initial state, cleaning up existing state first."""
        await self.cleanup()
        self._state = self._create_initial_state()
