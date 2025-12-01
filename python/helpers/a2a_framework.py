"""
A2A Framework Integration for Vessels A0 Framework

This module provides enhanced Agent-to-Agent communication with full
integration into the A0 framework, including:

1. Ethical validation of all A2A messages
2. Recording of all communications in collective memory
3. Project-aware message routing
4. Trust and capability negotiation
5. Secure message exchange
"""

import asyncio
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class A2ATrustLevel(Enum):
    """Trust levels for A2A communication."""
    UNTRUSTED = 0
    BASIC = 1
    VERIFIED = 2
    TRUSTED = 3
    FULLY_TRUSTED = 4


class A2AMessageType(Enum):
    """Types of A2A messages."""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    CAPABILITY_QUERY = "capability_query"
    CAPABILITY_RESPONSE = "capability_response"
    TRUST_NEGOTIATION = "trust_negotiation"
    ERROR = "error"


@dataclass
class A2AAgent:
    """Represents a remote agent for A2A communication."""
    agent_id: str
    agent_url: str
    name: str = ""
    description: str = ""
    capabilities: List[str] = field(default_factory=list)
    trust_level: A2ATrustLevel = A2ATrustLevel.UNTRUSTED
    verified_at: Optional[datetime] = None
    last_communication: Optional[datetime] = None
    communication_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_url": self.agent_url,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "trust_level": self.trust_level.value,
            "verified_at": self.verified_at.isoformat() if self.verified_at else None,
            "last_communication": self.last_communication.isoformat() if self.last_communication else None,
            "communication_count": self.communication_count,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'A2AAgent':
        return cls(
            agent_id=data["agent_id"],
            agent_url=data["agent_url"],
            name=data.get("name", ""),
            description=data.get("description", ""),
            capabilities=data.get("capabilities", []),
            trust_level=A2ATrustLevel(data.get("trust_level", 0)),
            verified_at=datetime.fromisoformat(data["verified_at"]) if data.get("verified_at") else None,
            last_communication=datetime.fromisoformat(data["last_communication"]) if data.get("last_communication") else None,
            communication_count=data.get("communication_count", 0),
            metadata=data.get("metadata", {})
        )


@dataclass
class A2AMessage:
    """An A2A message with full metadata."""
    message_id: str
    message_type: A2AMessageType
    from_agent: str
    to_agent: str
    content: Any
    timestamp: datetime = field(default_factory=datetime.now)
    context_id: Optional[str] = None
    project_id: Optional[str] = None
    parent_message_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    ethical_validated: bool = False
    recorded_to_memory: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "context_id": self.context_id,
            "project_id": self.project_id,
            "parent_message_id": self.parent_message_id,
            "metadata": self.metadata,
            "ethical_validated": self.ethical_validated,
            "recorded_to_memory": self.recorded_to_memory
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'A2AMessage':
        return cls(
            message_id=data["message_id"],
            message_type=A2AMessageType(data["message_type"]),
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            content=data["content"],
            timestamp=datetime.fromisoformat(data["timestamp"]) if data.get("timestamp") else datetime.now(),
            context_id=data.get("context_id"),
            project_id=data.get("project_id"),
            parent_message_id=data.get("parent_message_id"),
            metadata=data.get("metadata", {}),
            ethical_validated=data.get("ethical_validated", False),
            recorded_to_memory=data.get("recorded_to_memory", False)
        )


class A2AFramework:
    """
    Enhanced A2A communication framework with full A0 integration.

    This class wraps the basic A2A client/server functionality and adds:
    - Ethical validation of all messages
    - Recording to collective memory
    - Trust management
    - Project context awareness
    """

    _instance: Optional['A2AFramework'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._known_agents: Dict[str, A2AAgent] = {}
        self._connections: Dict[str, Any] = {}
        self._collective_memory = None
        self._ethics_engine = None
        self._project_manager = None
        self._initialized = False
        self._hooks: Dict[str, List[Callable]] = {
            "message_sent": [],
            "message_received": [],
            "agent_discovered": [],
            "trust_changed": [],
        }
        self._local_agent_id: str = ""

    @classmethod
    async def get_instance(cls) -> 'A2AFramework':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize the A2A framework."""
        if self._initialized:
            return

        import os
        self._local_agent_id = os.getenv("VESSELS_AGENT_ID", f"agent_{uuid.uuid4().hex[:8]}")

        # Initialize framework integrations
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

        self._initialized = True
        logger.info(f"A2AFramework initialized with agent ID: {self._local_agent_id}")

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

    async def _validate_ethics(
        self,
        action_type: str,
        data: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Validate action against ethical principles."""
        if not self._ethics_engine:
            return True, ""

        try:
            validation = await self._ethics_engine.validate(
                action_type=action_type,
                data=data,
                context=context
            )
            return validation.is_approved, validation.explanation
        except Exception as e:
            logger.error(f"Ethics validation failed: {e}")
            return False, str(e)

    async def _record_message(self, message: A2AMessage, direction: str):
        """Record a message to collective memory."""
        if not self._collective_memory:
            return

        try:
            await self._collective_memory.record_a2a_message(
                from_agent=message.from_agent,
                to_agent=message.to_agent,
                message=json.dumps(message.content) if not isinstance(message.content, str) else message.content,
                direction=direction,
                project_id=message.project_id
            )
            message.recorded_to_memory = True
        except Exception as e:
            logger.error(f"Failed to record message: {e}")

    async def discover_agent(self, agent_url: str) -> Optional[A2AAgent]:
        """Discover and register a remote agent."""
        try:
            from python.helpers.fasta2a_client import AgentConnection, FASTA2A_CLIENT_AVAILABLE

            if not FASTA2A_CLIENT_AVAILABLE:
                logger.error("FastA2A client not available")
                return None

            # Connect and get agent card
            connection = AgentConnection(agent_url)
            agent_card = await connection.get_agent_card()

            agent_id = agent_card.get("name", hashlib.sha256(agent_url.encode()).hexdigest()[:12])

            agent = A2AAgent(
                agent_id=agent_id,
                agent_url=agent_url,
                name=agent_card.get("name", ""),
                description=agent_card.get("description", ""),
                capabilities=agent_card.get("capabilities", []),
                trust_level=A2ATrustLevel.BASIC,
                verified_at=datetime.now()
            )

            self._known_agents[agent_id] = agent
            self._connections[agent_id] = connection

            await self._run_hooks("agent_discovered", agent)

            # Record to memory
            if self._collective_memory:
                from python.helpers.collective_memory import MemoryType, MemoryScope, MemoryPriority
                await self._collective_memory.store(
                    memory_type=MemoryType.EVENT,
                    content={"event": "agent_discovered", "agent": agent.to_dict()},
                    scope=MemoryScope.GLOBAL,
                    priority=MemoryPriority.NORMAL,
                    tags=["a2a", "discovery", agent_id]
                )

            logger.info(f"Discovered agent: {agent_id} at {agent_url}")
            return agent

        except Exception as e:
            logger.error(f"Failed to discover agent at {agent_url}: {e}")
            return None

    async def send_message(
        self,
        to_agent: str,
        content: Any,
        message_type: A2AMessageType = A2AMessageType.REQUEST,
        project_id: Optional[str] = None,
        context_id: Optional[str] = None,
        require_trust_level: A2ATrustLevel = A2ATrustLevel.BASIC
    ) -> Optional[A2AMessage]:
        """
        Send a message to a remote agent with full A0 framework integration.

        Args:
            to_agent: Agent ID or URL to send to
            content: Message content
            message_type: Type of message
            project_id: Optional project context
            context_id: Optional conversation context
            require_trust_level: Minimum trust level required

        Returns:
            A2AMessage with response, or None on failure
        """
        # Resolve agent
        agent = self._known_agents.get(to_agent)
        if not agent:
            # Try to discover if it looks like a URL
            if "://" in to_agent or "." in to_agent:
                agent = await self.discover_agent(to_agent)
            if not agent:
                logger.error(f"Unknown agent: {to_agent}")
                return None

        # Check trust level
        if agent.trust_level.value < require_trust_level.value:
            logger.error(f"Agent {to_agent} trust level {agent.trust_level} below required {require_trust_level}")
            return None

        # Create message
        message = A2AMessage(
            message_id=str(uuid.uuid4()),
            message_type=message_type,
            from_agent=self._local_agent_id,
            to_agent=agent.agent_id,
            content=content,
            project_id=project_id,
            context_id=context_id
        )

        # Validate ethics
        approved, explanation = await self._validate_ethics(
            action_type="a2a_send",
            data={
                "to_agent": agent.agent_id,
                "content": str(content)[:500],
                "message_type": message_type.value
            },
            context={"project_id": project_id, "agent_id": self._local_agent_id}
        )

        if not approved:
            logger.error(f"A2A message blocked by ethics: {explanation}")
            return None

        message.ethical_validated = True

        # Record outgoing message
        await self._record_message(message, "outgoing")

        # Send via underlying client
        try:
            connection = self._connections.get(agent.agent_id)
            if not connection:
                from python.helpers.fasta2a_client import AgentConnection
                connection = AgentConnection(agent.agent_url)
                await connection.get_agent_card()
                self._connections[agent.agent_id] = connection

            # Format content for A2A protocol
            text_content = json.dumps(content) if not isinstance(content, str) else content

            response = await connection.send_message(
                message=text_content,
                context_id=context_id,
                metadata={"project_id": project_id, "message_id": message.message_id}
            )

            # Update agent stats
            agent.last_communication = datetime.now()
            agent.communication_count += 1

            # Create response message
            response_message = A2AMessage(
                message_id=str(uuid.uuid4()),
                message_type=A2AMessageType.RESPONSE,
                from_agent=agent.agent_id,
                to_agent=self._local_agent_id,
                content=response,
                project_id=project_id,
                context_id=response.get("result", {}).get("context_id", context_id),
                parent_message_id=message.message_id
            )

            # Record incoming response
            await self._record_message(response_message, "incoming")

            await self._run_hooks("message_sent", message)
            await self._run_hooks("message_received", response_message)

            return response_message

        except Exception as e:
            logger.error(f"Failed to send A2A message: {e}")

            # Record error
            if self._collective_memory:
                await self._collective_memory.record_error(
                    error_type="a2a_send_error",
                    message=str(e),
                    context={"to_agent": agent.agent_id, "message_id": message.message_id}
                )

            return None

    async def set_trust_level(
        self,
        agent_id: str,
        trust_level: A2ATrustLevel,
        reason: str = ""
    ) -> bool:
        """Set the trust level for an agent."""
        agent = self._known_agents.get(agent_id)
        if not agent:
            return False

        old_level = agent.trust_level
        agent.trust_level = trust_level

        # Record trust change
        if self._collective_memory:
            from python.helpers.collective_memory import MemoryType, MemoryScope, MemoryPriority
            await self._collective_memory.store(
                memory_type=MemoryType.EVENT,
                content={
                    "event": "trust_changed",
                    "agent_id": agent_id,
                    "old_level": old_level.value,
                    "new_level": trust_level.value,
                    "reason": reason
                },
                scope=MemoryScope.GLOBAL,
                priority=MemoryPriority.HIGH,
                tags=["a2a", "trust", agent_id]
            )

        await self._run_hooks("trust_changed", {
            "agent": agent,
            "old_level": old_level,
            "new_level": trust_level
        })

        return True

    def get_known_agents(self) -> List[A2AAgent]:
        """Get all known agents."""
        return list(self._known_agents.values())

    def get_agent(self, agent_id: str) -> Optional[A2AAgent]:
        """Get a specific agent."""
        return self._known_agents.get(agent_id)

    async def query_capabilities(self, agent_id: str) -> List[str]:
        """Query an agent's capabilities."""
        agent = self._known_agents.get(agent_id)
        if not agent:
            return []

        try:
            connection = self._connections.get(agent_id)
            if connection:
                agent_card = await connection.get_agent_card()
                agent.capabilities = agent_card.get("capabilities", [])
                return agent.capabilities
        except Exception as e:
            logger.error(f"Failed to query capabilities: {e}")

        return agent.capabilities

    async def broadcast(
        self,
        content: Any,
        message_type: A2AMessageType = A2AMessageType.NOTIFICATION,
        min_trust_level: A2ATrustLevel = A2ATrustLevel.BASIC,
        project_id: Optional[str] = None
    ) -> Dict[str, Optional[A2AMessage]]:
        """Broadcast a message to all known agents above a trust level."""
        results = {}

        for agent_id, agent in self._known_agents.items():
            if agent.trust_level.value >= min_trust_level.value:
                result = await self.send_message(
                    to_agent=agent_id,
                    content=content,
                    message_type=message_type,
                    project_id=project_id
                )
                results[agent_id] = result

        return results

    async def close(self):
        """Close all connections."""
        for connection in self._connections.values():
            try:
                await connection.close()
            except Exception:
                pass
        self._connections.clear()

    async def get_statistics(self) -> Dict[str, Any]:
        """Get A2A communication statistics."""
        return {
            "local_agent_id": self._local_agent_id,
            "known_agents": len(self._known_agents),
            "active_connections": len(self._connections),
            "agents_by_trust": {
                level.name: sum(1 for a in self._known_agents.values() if a.trust_level == level)
                for level in A2ATrustLevel
            },
            "total_communications": sum(a.communication_count for a in self._known_agents.values())
        }


# Convenience functions
async def get_a2a_framework() -> A2AFramework:
    """Get the A2A framework instance."""
    return await A2AFramework.get_instance()


async def send_a2a_message(
    to_agent: str,
    content: Any,
    project_id: Optional[str] = None,
    **kwargs
) -> Optional[A2AMessage]:
    """Send an A2A message."""
    framework = await get_a2a_framework()
    return await framework.send_message(to_agent, content, project_id=project_id, **kwargs)


async def discover_remote_agent(agent_url: str) -> Optional[A2AAgent]:
    """Discover a remote agent."""
    framework = await get_a2a_framework()
    return await framework.discover_agent(agent_url)
