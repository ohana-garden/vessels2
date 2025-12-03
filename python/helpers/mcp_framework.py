"""
MCP Framework Integration for Vessels A0 Framework

This module provides enhanced Model Context Protocol (MCP) integration
with full A0 framework compliance, including:

1. Ethical validation of all MCP tool calls
2. Recording of all MCP interactions in collective memory
3. Project-aware server management
4. Capability tracking and discovery
5. Resource management
"""

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MCPServerType(Enum):
    """Types of MCP servers."""
    STDIO = "stdio"
    HTTP = "http"
    SSE = "sse"
    WEBSOCKET = "websocket"


class MCPServerStatus(Enum):
    """Status of an MCP server."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class MCPTool:
    """An MCP tool definition."""
    name: str
    description: str
    server_name: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    ethical_constraints: List[str] = field(default_factory=list)
    call_count: int = 0
    last_called: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "server_name": self.server_name,
            "input_schema": self.input_schema,
            "requires_confirmation": self.requires_confirmation,
            "ethical_constraints": self.ethical_constraints,
            "call_count": self.call_count,
            "last_called": self.last_called.isoformat() if self.last_called else None
        }


@dataclass
class MCPResource:
    """An MCP resource definition."""
    uri: str
    name: str
    description: str
    server_name: str
    mime_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "server_name": self.server_name,
            "mime_type": self.mime_type
        }


@dataclass
class MCPServer:
    """Represents an MCP server with its capabilities."""
    name: str
    server_type: MCPServerType
    status: MCPServerStatus = MCPServerStatus.DISCONNECTED
    config: Dict[str, Any] = field(default_factory=dict)
    tools: List[MCPTool] = field(default_factory=list)
    resources: List[MCPResource] = field(default_factory=list)
    prompts: List[Dict[str, Any]] = field(default_factory=list)
    connected_at: Optional[datetime] = None
    last_error: Optional[str] = None
    total_calls: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "server_type": self.server_type.value,
            "status": self.status.value,
            "config": {k: v for k, v in self.config.items() if k not in ("api_key", "token", "secret")},
            "tools": [t.to_dict() for t in self.tools],
            "resources": [r.to_dict() for r in self.resources],
            "prompts": self.prompts,
            "connected_at": self.connected_at.isoformat() if self.connected_at else None,
            "last_error": self.last_error,
            "total_calls": self.total_calls,
            "metadata": self.metadata
        }


@dataclass
class MCPExecution:
    """Record of an MCP tool execution."""
    execution_id: str
    server_name: str
    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    success: bool
    execution_time_ms: float
    agent_id: Optional[str] = None
    project_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None
    ethical_validated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "server_name": self.server_name,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result": str(self.result)[:1000] if self.result else None,
            "success": self.success,
            "execution_time_ms": self.execution_time_ms,
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
            "ethical_validated": self.ethical_validated
        }


class MCPFramework:
    """
    Enhanced MCP framework with full A0 integration.

    This class wraps the basic MCP handler and adds:
    - Ethical validation of all tool calls
    - Recording to collective memory
    - Server lifecycle management
    - Project context awareness
    """

    _instance: Optional['MCPFramework'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._servers: Dict[str, MCPServer] = {}
        self._mcp_handler = None
        self._collective_memory = None
        self._ethics_engine = None
        self._initialized = False
        self._hooks: Dict[str, List[Callable]] = {
            "server_connected": [],
            "server_disconnected": [],
            "tool_called": [],
            "tool_completed": [],
            "tool_error": [],
        }

    @classmethod
    async def get_instance(cls) -> 'MCPFramework':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize the MCP framework."""
        if self._initialized:
            return

        # Initialize MCP handler
        try:
            from python.helpers.mcp_handler import MCPConfig
            self._mcp_handler = MCPConfig
        except Exception as e:
            logger.warning(f"MCP handler not available: {e}")

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

        # Load existing MCP servers
        await self._load_servers()

        self._initialized = True
        logger.info(f"MCPFramework initialized with {len(self._servers)} servers")

    async def _load_servers(self):
        """Load MCP servers from configuration."""
        if not self._mcp_handler:
            return

        try:
            servers = self._mcp_handler.get_servers()
            for server_config in servers:
                name = server_config.get("name", "")
                if not name:
                    continue

                server = MCPServer(
                    name=name,
                    server_type=MCPServerType.STDIO,  # Default
                    config=server_config
                )

                # Try to get tools
                try:
                    tools = await self._mcp_handler.get_tools(name)
                    for tool in tools:
                        mcp_tool = MCPTool(
                            name=tool.get("name", ""),
                            description=tool.get("description", ""),
                            server_name=name,
                            input_schema=tool.get("inputSchema", {})
                        )
                        server.tools.append(mcp_tool)
                    server.status = MCPServerStatus.CONNECTED
                    server.connected_at = datetime.now()
                except Exception:
                    server.status = MCPServerStatus.DISCONNECTED

                self._servers[name] = server

        except Exception as e:
            logger.error(f"Failed to load MCP servers: {e}")

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
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        context: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """Validate tool call against ethical principles."""
        if not self._ethics_engine:
            return True, ""

        try:
            validation = await self._ethics_engine.validate(
                action_type=f"mcp_tool_{tool_name}",
                data={
                    "server": server_name,
                    "tool": tool_name,
                    "arguments": arguments
                },
                context=context
            )
            return validation.is_approved, validation.explanation
        except Exception as e:
            logger.error(f"Ethics validation failed: {e}")
            return False, str(e)

    async def _record_execution(self, execution: MCPExecution):
        """Record execution to collective memory."""
        if not self._collective_memory:
            return

        try:
            await self._collective_memory.record_mcp_interaction(
                server_name=execution.server_name,
                tool_name=execution.tool_name,
                request=execution.arguments,
                response=execution.result,
                success=execution.success,
                agent_id=execution.agent_id,
                project_id=execution.project_id
            )
        except Exception as e:
            logger.error(f"Failed to record execution: {e}")

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: Optional[str] = None,
        project_id: Optional[str] = None,
        require_confirmation: bool = False
    ) -> Tuple[Any, bool, str]:
        """
        Call an MCP tool with full A0 framework integration.

        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool to call
            arguments: Tool arguments
            agent_id: Optional agent ID for tracking
            project_id: Optional project context
            require_confirmation: Whether to require user confirmation

        Returns:
            Tuple of (result, success, error_message)
        """
        execution_id = hashlib.sha256(
            f"{server_name}:{tool_name}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        # Validate ethics first
        context = {"agent_id": agent_id, "project_id": project_id}
        approved, explanation = await self._validate_ethics(
            server_name, tool_name, arguments, context
        )

        if not approved:
            logger.warning(f"MCP tool call blocked by ethics: {explanation}")
            return None, False, f"Blocked by ethics: {explanation}"

        start_time = datetime.now()
        result = None
        success = False
        error_msg = ""

        try:
            # Call via underlying MCP handler
            if self._mcp_handler:
                result = await self._mcp_handler.execute_tool(
                    server_name, tool_name, arguments
                )
                success = True

                # Update tool stats
                server = self._servers.get(server_name)
                if server:
                    for tool in server.tools:
                        if tool.name == tool_name:
                            tool.call_count += 1
                            tool.last_called = datetime.now()
                            break
                    server.total_calls += 1

                await self._run_hooks("tool_completed", {
                    "server": server_name,
                    "tool": tool_name,
                    "result": result
                })

        except Exception as e:
            error_msg = str(e)
            logger.error(f"MCP tool call failed: {e}")
            await self._run_hooks("tool_error", {
                "server": server_name,
                "tool": tool_name,
                "error": error_msg
            })

        finally:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            execution = MCPExecution(
                execution_id=execution_id,
                server_name=server_name,
                tool_name=tool_name,
                arguments=arguments,
                result=result,
                success=success,
                execution_time_ms=execution_time,
                agent_id=agent_id,
                project_id=project_id,
                error_message=error_msg if error_msg else None,
                ethical_validated=approved
            )

            await self._record_execution(execution)
            await self._run_hooks("tool_called", execution)

        return result, success, error_msg

    async def connect_server(
        self,
        name: str,
        config: Dict[str, Any],
        auto_discover: bool = True
    ) -> Optional[MCPServer]:
        """Connect to an MCP server."""
        try:
            if not self._mcp_handler:
                return None

            # Add to MCP handler
            await self._mcp_handler.add_server(name, config)

            server = MCPServer(
                name=name,
                server_type=MCPServerType(config.get("type", "stdio")),
                config=config,
                status=MCPServerStatus.CONNECTING
            )

            # Discover tools if requested
            if auto_discover:
                try:
                    tools = await self._mcp_handler.get_tools(name)
                    for tool in tools:
                        mcp_tool = MCPTool(
                            name=tool.get("name", ""),
                            description=tool.get("description", ""),
                            server_name=name,
                            input_schema=tool.get("inputSchema", {})
                        )
                        server.tools.append(mcp_tool)
                except Exception as e:
                    logger.warning(f"Failed to discover tools: {e}")

            server.status = MCPServerStatus.CONNECTED
            server.connected_at = datetime.now()
            self._servers[name] = server

            await self._run_hooks("server_connected", server)

            # Record to memory
            if self._collective_memory:
                from python.helpers.collective_memory import MemoryType, MemoryScope, MemoryPriority
                await self._collective_memory.store(
                    memory_type=MemoryType.EVENT,
                    content={
                        "event": "mcp_server_connected",
                        "server": name,
                        "tools_count": len(server.tools)
                    },
                    scope=MemoryScope.GLOBAL,
                    priority=MemoryPriority.NORMAL,
                    tags=["mcp", "server", name]
                )

            return server

        except Exception as e:
            logger.error(f"Failed to connect MCP server {name}: {e}")
            return None

    async def disconnect_server(self, name: str) -> bool:
        """Disconnect from an MCP server."""
        server = self._servers.get(name)
        if not server:
            return False

        try:
            if self._mcp_handler:
                await self._mcp_handler.remove_server(name)

            server.status = MCPServerStatus.DISCONNECTED
            del self._servers[name]

            await self._run_hooks("server_disconnected", server)

            return True

        except Exception as e:
            logger.error(f"Failed to disconnect MCP server {name}: {e}")
            server.status = MCPServerStatus.ERROR
            server.last_error = str(e)
            return False

    def get_server(self, name: str) -> Optional[MCPServer]:
        """Get an MCP server by name."""
        return self._servers.get(name)

    def list_servers(self) -> List[MCPServer]:
        """List all MCP servers."""
        return list(self._servers.values())

    def list_all_tools(self) -> List[MCPTool]:
        """List all available MCP tools across all servers."""
        tools = []
        for server in self._servers.values():
            if server.status == MCPServerStatus.CONNECTED:
                tools.extend(server.tools)
        return tools

    def get_tool(self, server_name: str, tool_name: str) -> Optional[MCPTool]:
        """Get a specific tool."""
        server = self._servers.get(server_name)
        if not server:
            return None

        for tool in server.tools:
            if tool.name == tool_name:
                return tool
        return None

    def get_tools_prompt(self) -> str:
        """Get the tools prompt for all connected MCP servers."""
        if self._mcp_handler:
            return self._mcp_handler.get_tools_prompt()
        return ""

    async def get_statistics(self) -> Dict[str, Any]:
        """Get MCP framework statistics."""
        connected = sum(1 for s in self._servers.values() if s.status == MCPServerStatus.CONNECTED)
        total_tools = sum(len(s.tools) for s in self._servers.values())
        total_calls = sum(s.total_calls for s in self._servers.values())

        return {
            "servers": {
                "total": len(self._servers),
                "connected": connected,
                "disconnected": len(self._servers) - connected
            },
            "tools": {
                "total": total_tools,
                "by_server": {
                    s.name: len(s.tools) for s in self._servers.values()
                }
            },
            "calls": {
                "total": total_calls,
                "by_server": {
                    s.name: s.total_calls for s in self._servers.values()
                }
            }
        }


# Convenience functions
async def get_mcp_framework() -> MCPFramework:
    """Get the MCP framework instance."""
    return await MCPFramework.get_instance()


async def call_mcp_tool(
    server_name: str,
    tool_name: str,
    arguments: Dict[str, Any],
    **kwargs
) -> Tuple[Any, bool, str]:
    """Call an MCP tool."""
    framework = await get_mcp_framework()
    return await framework.call_tool(server_name, tool_name, arguments, **kwargs)


async def list_mcp_tools() -> List[MCPTool]:
    """List all available MCP tools."""
    framework = await get_mcp_framework()
    return framework.list_all_tools()
