"""
Tool Framework for Vessels A0 Framework

This module provides enhanced tool execution with full A0 framework integration:

1. Ethical validation before every tool execution
2. Recording of all tool I/O in collective memory
3. Project-aware tool context
4. Performance monitoring and analytics
5. Tool permission management
"""

import asyncio
import functools
import hashlib
import inspect
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Type, Union

logger = logging.getLogger(__name__)


class ToolCategory(Enum):
    """Categories of tools."""
    SYSTEM = "system"
    CODE = "code"
    MEMORY = "memory"
    COMMUNICATION = "communication"
    FILE = "file"
    NETWORK = "network"
    DATA = "data"
    UTILITY = "utility"
    FINANCIAL = "financial"
    CUSTOM = "custom"


class ToolRiskLevel(Enum):
    """Risk levels for tools."""
    SAFE = 0  # No side effects, read-only
    LOW = 1  # Minor side effects, easily reversible
    MEDIUM = 2  # Moderate side effects
    HIGH = 3  # Significant side effects, hard to reverse
    CRITICAL = 4  # Irreversible or highly impactful


class ToolPermission(Enum):
    """Permissions for tool execution."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    NETWORK = "network"
    FINANCIAL = "financial"
    ADMIN = "admin"


@dataclass
class ToolMetadata:
    """Metadata about a tool."""
    tool_id: str
    name: str
    description: str
    category: ToolCategory
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW
    permissions_required: List[ToolPermission] = field(default_factory=list)
    ethical_constraints: List[str] = field(default_factory=list)
    requires_confirmation: bool = False
    async_execution: bool = True
    parameters_schema: Dict[str, Any] = field(default_factory=dict)
    return_schema: Dict[str, Any] = field(default_factory=dict)
    examples: List[Dict[str, Any]] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    version: str = "1.0.0"
    author: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "risk_level": self.risk_level.value,
            "permissions_required": [p.value for p in self.permissions_required],
            "ethical_constraints": self.ethical_constraints,
            "requires_confirmation": self.requires_confirmation,
            "async_execution": self.async_execution,
            "parameters_schema": self.parameters_schema,
            "return_schema": self.return_schema,
            "examples": self.examples,
            "tags": self.tags,
            "version": self.version,
            "author": self.author
        }


@dataclass
class ToolExecution:
    """Record of a tool execution."""
    execution_id: str
    tool_id: str
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
    permission_checked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "arguments": {k: str(v)[:100] for k, v in self.arguments.items()},
            "result": str(self.result)[:500] if self.result else None,
            "success": self.success,
            "execution_time_ms": self.execution_time_ms,
            "agent_id": self.agent_id,
            "project_id": self.project_id,
            "timestamp": self.timestamp.isoformat(),
            "error_message": self.error_message,
            "ethical_validated": self.ethical_validated,
            "permission_checked": self.permission_checked
        }


class A0Tool(ABC):
    """
    Enhanced abstract base class for A0 Framework tools.

    All tools should inherit from this class to get full A0 integration
    including ethics validation and memory recording.
    """

    def __init__(self):
        self._metadata: Optional[ToolMetadata] = None
        self._collective_memory = None
        self._ethics_engine = None
        self._agent = None
        self._context: Dict[str, Any] = {}

    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """Get tool metadata."""
        pass

    @abstractmethod
    async def execute_impl(self, **kwargs) -> Any:
        """Implement the actual tool logic. Override this in subclasses."""
        pass

    async def set_context(
        self,
        agent: Any = None,
        collective_memory: Any = None,
        ethics_engine: Any = None,
        **kwargs
    ):
        """Set the execution context."""
        self._agent = agent
        self._collective_memory = collective_memory
        self._ethics_engine = ethics_engine
        self._context.update(kwargs)

    async def execute(self, **kwargs) -> Any:
        """
        Execute the tool with full A0 framework integration.

        This method:
        1. Validates ethics
        2. Checks permissions
        3. Records input to memory
        4. Executes the tool
        5. Records output to memory
        """
        execution_id = hashlib.sha256(
            f"{self.metadata.tool_id}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        agent_id = self._context.get("agent_id")
        project_id = self._context.get("project_id")

        # Validate ethics
        ethical_validated = await self._validate_ethics(kwargs)
        if not ethical_validated:
            raise PermissionError(f"Tool {self.metadata.name} blocked by ethical validation")

        # Check permissions
        permission_checked = await self._check_permissions()
        if not permission_checked:
            raise PermissionError(f"Insufficient permissions for tool {self.metadata.name}")

        start_time = time.time()
        result = None
        success = False
        error_msg = None

        try:
            # Execute the actual tool logic
            result = await self.execute_impl(**kwargs)
            success = True

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Tool {self.metadata.name} failed: {e}")
            raise

        finally:
            execution_time = (time.time() - start_time) * 1000

            execution = ToolExecution(
                execution_id=execution_id,
                tool_id=self.metadata.tool_id,
                tool_name=self.metadata.name,
                arguments=kwargs,
                result=result,
                success=success,
                execution_time_ms=execution_time,
                agent_id=agent_id,
                project_id=project_id,
                error_message=error_msg,
                ethical_validated=ethical_validated,
                permission_checked=permission_checked
            )

            await self._record_execution(execution)

        return result

    async def _validate_ethics(self, arguments: Dict[str, Any]) -> bool:
        """Validate tool execution against ethical principles."""
        if not self._ethics_engine:
            return True

        try:
            validation = await self._ethics_engine.validate(
                action_type=f"tool_{self.metadata.name}",
                data={
                    "tool": self.metadata.name,
                    "category": self.metadata.category.value,
                    "arguments": arguments
                },
                context=self._context
            )
            return validation.is_approved
        except Exception as e:
            logger.error(f"Ethics validation failed: {e}")
            return False

    async def _check_permissions(self) -> bool:
        """Check if the current context has required permissions."""
        # For now, always return True
        # In production, this would check against a permission system
        return True

    async def _record_execution(self, execution: ToolExecution):
        """Record tool execution to collective memory."""
        if not self._collective_memory:
            return

        try:
            await self._collective_memory.record_tool_execution(
                tool_name=execution.tool_name,
                tool_input=execution.arguments,
                tool_output=execution.result,
                execution_time=execution.execution_time_ms,
                success=execution.success,
                agent_id=execution.agent_id,
                project_id=execution.project_id
            )
        except Exception as e:
            logger.error(f"Failed to record execution: {e}")


def a0_tool(
    name: str,
    description: str,
    category: ToolCategory = ToolCategory.UTILITY,
    risk_level: ToolRiskLevel = ToolRiskLevel.LOW,
    permissions: Optional[List[ToolPermission]] = None,
    ethical_constraints: Optional[List[str]] = None,
    requires_confirmation: bool = False
):
    """
    Decorator to convert a function into an A0 tool.

    Usage:
        @a0_tool(
            name="my_tool",
            description="Does something useful",
            category=ToolCategory.UTILITY
        )
        async def my_tool(arg1: str, arg2: int) -> str:
            return f"{arg1}: {arg2}"
    """
    def decorator(func: Callable) -> Callable:
        # Generate tool ID
        tool_id = f"tool_{hashlib.sha256(name.encode()).hexdigest()[:8]}"

        # Create metadata
        metadata = ToolMetadata(
            tool_id=tool_id,
            name=name,
            description=description,
            category=category,
            risk_level=risk_level,
            permissions_required=permissions or [],
            ethical_constraints=ethical_constraints or [],
            requires_confirmation=requires_confirmation,
            async_execution=asyncio.iscoroutinefunction(func)
        )

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get framework integrations from context if available
            context = kwargs.pop("_a0_context", {})
            collective_memory = context.get("collective_memory")
            ethics_engine = context.get("ethics_engine")

            execution_id = hashlib.sha256(
                f"{tool_id}:{datetime.now().isoformat()}".encode()
            ).hexdigest()[:16]

            # Validate ethics
            ethical_validated = True
            if ethics_engine:
                try:
                    validation = await ethics_engine.validate(
                        action_type=f"tool_{name}",
                        data={"tool": name, "arguments": kwargs},
                        context=context
                    )
                    ethical_validated = validation.is_approved
                    if not ethical_validated:
                        raise PermissionError(f"Tool {name} blocked by ethical validation")
                except PermissionError:
                    raise
                except Exception as e:
                    logger.error(f"Ethics validation failed: {e}")

            start_time = time.time()
            result = None
            success = False
            error_msg = None

            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                success = True

            except Exception as e:
                error_msg = str(e)
                raise

            finally:
                execution_time = (time.time() - start_time) * 1000

                # Record to memory
                if collective_memory:
                    try:
                        await collective_memory.record_tool_execution(
                            tool_name=name,
                            tool_input=kwargs,
                            tool_output=result,
                            execution_time=execution_time,
                            success=success,
                            agent_id=context.get("agent_id"),
                            project_id=context.get("project_id")
                        )
                    except Exception as e:
                        logger.error(f"Failed to record execution: {e}")

            return result

        # Attach metadata to the wrapper
        wrapper._a0_metadata = metadata
        wrapper._a0_tool = True

        return wrapper

    return decorator


class ToolRegistry:
    """
    Central registry for all tools in the A0 framework.

    This singleton manages tool discovery, registration, and execution
    with full framework integration.
    """

    _instance: Optional['ToolRegistry'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._tools: Dict[str, Union[A0Tool, Callable]] = {}
        self._tool_metadata: Dict[str, ToolMetadata] = {}
        self._collective_memory = None
        self._ethics_engine = None
        self._initialized = False
        self._hooks: Dict[str, List[Callable]] = {
            "tool_registered": [],
            "tool_executed": [],
            "tool_error": [],
        }

    @classmethod
    async def get_instance(cls) -> 'ToolRegistry':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize the tool registry."""
        if self._initialized:
            return

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

        # Load tools from the tools directory
        await self._load_tools()

        self._initialized = True
        logger.info(f"ToolRegistry initialized with {len(self._tools)} tools")

    async def _load_tools(self):
        """Load tools from the python/tools directory."""
        import importlib
        import importlib.util
        import os
        from python.helpers import files

        tools_dir = files.get_abs_path("python", "tools")
        if not os.path.exists(tools_dir):
            return

        for filename in os.listdir(tools_dir):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            try:
                module_name = filename.replace(".py", "")
                filepath = os.path.join(tools_dir, filename)

                spec = importlib.util.spec_from_file_location(
                    f"python.tools.{module_name}",
                    filepath
                )
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                    # Look for A0Tool subclasses or decorated functions
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)

                        if isinstance(attr, type) and issubclass(attr, A0Tool) and attr is not A0Tool:
                            # Register class-based tool
                            tool_instance = attr()
                            self._tools[tool_instance.metadata.tool_id] = tool_instance
                            self._tool_metadata[tool_instance.metadata.tool_id] = tool_instance.metadata
                            logger.debug(f"Loaded class tool: {attr_name}")

                        elif callable(attr) and hasattr(attr, "_a0_tool"):
                            # Register decorator-based tool
                            metadata = attr._a0_metadata
                            self._tools[metadata.tool_id] = attr
                            self._tool_metadata[metadata.tool_id] = metadata
                            logger.debug(f"Loaded decorated tool: {attr_name}")

            except Exception as e:
                logger.error(f"Failed to load tool module {filename}: {e}")

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

    def register(
        self,
        tool: Union[A0Tool, Callable],
        metadata: Optional[ToolMetadata] = None
    ) -> str:
        """Register a tool with the registry."""
        if isinstance(tool, A0Tool):
            tool_id = tool.metadata.tool_id
            self._tools[tool_id] = tool
            self._tool_metadata[tool_id] = tool.metadata
        elif hasattr(tool, "_a0_metadata"):
            metadata = tool._a0_metadata
            tool_id = metadata.tool_id
            self._tools[tool_id] = tool
            self._tool_metadata[tool_id] = metadata
        elif metadata:
            tool_id = metadata.tool_id
            self._tools[tool_id] = tool
            self._tool_metadata[tool_id] = metadata
        else:
            raise ValueError("Tool must be an A0Tool, decorated function, or have metadata provided")

        logger.info(f"Registered tool: {tool_id}")
        return tool_id

    def unregister(self, tool_id: str) -> bool:
        """Unregister a tool."""
        if tool_id in self._tools:
            del self._tools[tool_id]
            del self._tool_metadata[tool_id]
            return True
        return False

    def get_tool(self, tool_id: str) -> Optional[Union[A0Tool, Callable]]:
        """Get a tool by ID."""
        return self._tools.get(tool_id)

    def get_metadata(self, tool_id: str) -> Optional[ToolMetadata]:
        """Get tool metadata."""
        return self._tool_metadata.get(tool_id)

    def list_tools(self) -> List[str]:
        """List all registered tool IDs."""
        return list(self._tools.keys())

    def list_all_metadata(self) -> List[ToolMetadata]:
        """Get metadata for all registered tools."""
        return list(self._tool_metadata.values())

    def get_tools_by_category(self, category: ToolCategory) -> List[ToolMetadata]:
        """Get tools by category."""
        return [m for m in self._tool_metadata.values() if m.category == category]

    async def execute(
        self,
        tool_id: str,
        arguments: Dict[str, Any],
        agent_id: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> Tuple[Any, bool, str]:
        """
        Execute a tool with full framework integration.

        Returns:
            Tuple of (result, success, error_message)
        """
        tool = self._tools.get(tool_id)
        if not tool:
            return None, False, f"Tool not found: {tool_id}"

        context = {
            "agent_id": agent_id,
            "project_id": project_id,
            "collective_memory": self._collective_memory,
            "ethics_engine": self._ethics_engine
        }

        try:
            if isinstance(tool, A0Tool):
                await tool.set_context(
                    collective_memory=self._collective_memory,
                    ethics_engine=self._ethics_engine,
                    **context
                )
                result = await tool.execute(**arguments)
            else:
                # Decorated function
                arguments["_a0_context"] = context
                result = await tool(**arguments)

            await self._run_hooks("tool_executed", {
                "tool_id": tool_id,
                "success": True
            })

            return result, True, ""

        except Exception as e:
            error_msg = str(e)
            await self._run_hooks("tool_error", {
                "tool_id": tool_id,
                "error": error_msg
            })
            return None, False, error_msg

    async def get_statistics(self) -> Dict[str, Any]:
        """Get tool registry statistics."""
        return {
            "total_tools": len(self._tools),
            "by_category": {
                cat.value: len(self.get_tools_by_category(cat))
                for cat in ToolCategory
            },
            "by_risk_level": {
                level.value: sum(1 for m in self._tool_metadata.values() if m.risk_level == level)
                for level in ToolRiskLevel
            }
        }


# Convenience functions
async def get_tool_registry() -> ToolRegistry:
    """Get the tool registry instance."""
    return await ToolRegistry.get_instance()


async def execute_tool(
    tool_id: str,
    arguments: Dict[str, Any],
    **kwargs
) -> Tuple[Any, bool, str]:
    """Execute a tool."""
    registry = await get_tool_registry()
    return await registry.execute(tool_id, arguments, **kwargs)


async def list_available_tools() -> List[ToolMetadata]:
    """List all available tools."""
    registry = await get_tool_registry()
    return registry.list_all_metadata()
