"""
Tool Discovery Engine for Vessels A0 Framework

This module converts discovered APIs and tools from web spidering
into registerable instruments and MCP server configurations.

The engine:
1. Validates discovered tools
2. Generates instrument/MCP configurations
3. Creates tool wrappers for HTTP APIs
4. Manages the discovered tool registry
5. Syncs with the graph store
"""

import asyncio
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from python.helpers.web_spider import (
    DiscoveredAPI,
    DiscoveredTool,
    SourceType,
    CrawlResult,
)
from python.helpers.instruments import (
    Instrument,
    InstrumentCapability,
    InstrumentMetadata,
    InstrumentRegistry,
    InstrumentStatus,
    InstrumentType,
    InstrumentExecution,
)

logger = logging.getLogger(__name__)


class ToolQuality(Enum):
    """Quality assessment of a discovered tool."""
    HIGH = "high"       # Well-documented, tested, from trusted source
    MEDIUM = "medium"   # Reasonably documented, needs verification
    LOW = "low"         # Minimal documentation, experimental
    UNKNOWN = "unknown" # Cannot assess quality


class RegistrationStatus(Enum):
    """Status of tool registration."""
    PENDING = "pending"
    VALIDATED = "validated"
    REGISTERED = "registered"
    FAILED = "failed"
    DISABLED = "disabled"


@dataclass
class ToolValidation:
    """Result of tool validation."""
    is_valid: bool
    quality: ToolQuality
    issues: List[str]
    suggestions: List[str]
    risk_level: str  # safe, low, medium, high, critical
    requires_auth: bool
    auth_type: Optional[str]


@dataclass
class RegisteredTool:
    """A tool that has been registered in the system."""
    tool_id: str
    name: str
    description: str
    source: str  # instrument, mcp, http_api
    original: DiscoveredTool
    validation: ToolValidation
    status: RegistrationStatus
    registered_at: datetime
    last_used: Optional[datetime]
    use_count: int
    config: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "source": self.source,
            "status": self.status.value,
            "quality": self.validation.quality.value,
            "risk_level": self.validation.risk_level,
            "registered_at": self.registered_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "use_count": self.use_count,
        }


@dataclass
class MCPServerConfig:
    """Configuration for a dynamically generated MCP server."""
    name: str
    description: str
    type: str  # stdio, sse, http-stream
    source_url: str
    tools: List[Dict[str, Any]]
    connection: Dict[str, Any]  # command/args or url/headers
    generated_at: datetime

    def to_mcp_config(self) -> Dict[str, Any]:
        """Convert to MCP configuration format."""
        config = {
            "name": self.name,
            "description": self.description,
            "type": self.type,
        }
        config.update(self.connection)
        return config


class ToolValidator:
    """Validates discovered tools before registration."""

    # Trusted domains for higher quality assessment
    TRUSTED_DOMAINS = [
        'github.com',
        'npmjs.com',
        'pypi.org',
        'api.openai.com',
        'api.anthropic.com',
        'googleapis.com',
    ]

    # Risky patterns to check for
    RISKY_PATTERNS = [
        'exec', 'eval', 'system', 'shell', 'rm -rf',
        'drop table', 'delete from', 'truncate',
    ]

    def validate(self, tool: DiscoveredTool) -> ToolValidation:
        """Validate a discovered tool."""
        issues = []
        suggestions = []
        risk_level = "safe"
        requires_auth = False
        auth_type = None

        # Check basic info
        if not tool.name:
            issues.append("Tool has no name")
        if not tool.description:
            issues.append("Tool has no description")
            suggestions.append("Consider adding a description for better usability")

        # Assess quality based on source
        quality = self._assess_quality(tool)

        # Check for risky patterns
        tool_str = json.dumps(tool.to_dict()).lower()
        for pattern in self.RISKY_PATTERNS:
            if pattern in tool_str:
                issues.append(f"Contains potentially risky pattern: {pattern}")
                risk_level = "high"

        # Check confidence level
        if tool.confidence < 0.5:
            issues.append(f"Low extraction confidence: {tool.confidence}")
            quality = ToolQuality.LOW

        # Determine auth requirements
        if tool.source_type == 'api_endpoint':
            install = tool.installation
            if 'auth' in str(install).lower() or 'key' in str(install).lower():
                requires_auth = True
                auth_type = "api_key"

        # Determine risk level from source type
        if tool.source_type == 'mcp':
            # MCP tools can execute arbitrary code
            risk_level = max(risk_level, "medium")
        elif tool.source_type == 'api_endpoint':
            # HTTP APIs are generally safer
            risk_level = max(risk_level, "low")

        is_valid = len([i for i in issues if "no name" in i or "risky" in i]) == 0

        return ToolValidation(
            is_valid=is_valid,
            quality=quality,
            issues=issues,
            suggestions=suggestions,
            risk_level=risk_level,
            requires_auth=requires_auth,
            auth_type=auth_type,
        )

    def _assess_quality(self, tool: DiscoveredTool) -> ToolQuality:
        """Assess tool quality based on various factors."""
        score = 0

        # Check source URL
        source_url = tool.source_url.lower()
        for domain in self.TRUSTED_DOMAINS:
            if domain in source_url:
                score += 2
                break

        # Check confidence
        if tool.confidence >= 0.8:
            score += 2
        elif tool.confidence >= 0.6:
            score += 1

        # Check documentation
        if len(tool.description) > 50:
            score += 1
        if tool.parameters:
            score += 1

        # Determine quality level
        if score >= 5:
            return ToolQuality.HIGH
        elif score >= 3:
            return ToolQuality.MEDIUM
        elif score >= 1:
            return ToolQuality.LOW
        else:
            return ToolQuality.UNKNOWN


class HTTPAPIInstrument(Instrument):
    """
    Dynamic instrument for HTTP API endpoints.

    This instrument is generated from discovered OpenAPI/REST endpoints
    and provides a standardized interface for calling HTTP APIs.
    """

    def __init__(
        self,
        api: DiscoveredAPI,
        endpoint: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None
    ):
        super().__init__(config)
        self._api = api
        self._endpoint = endpoint
        self._http_client = None

        # Generate metadata
        endpoint_name = endpoint.get('operation_id') or \
            f"{endpoint['method'].lower()}_{endpoint['path'].replace('/', '_')}"

        self._metadata = InstrumentMetadata(
            instrument_id=hashlib.sha256(
                f"{api.base_url}{endpoint['path']}{endpoint['method']}".encode()
            ).hexdigest()[:16],
            name=endpoint_name,
            description=endpoint.get('summary', endpoint.get('description', '')),
            version=api.version,
            instrument_type=InstrumentType.API,
            author="Discovered via Web Spider",
            documentation_url=api.spec_url,
            capabilities=[
                InstrumentCapability(
                    name="call",
                    description=f"Call {endpoint['method']} {endpoint['path']}",
                    parameters=endpoint.get('parameters', {}),
                    return_type="dict",
                    async_only=True,
                )
            ],
            config_schema={
                "base_url": {"type": "string", "default": api.base_url},
                "headers": {"type": "object", "default": {}},
                "timeout": {"type": "integer", "default": 30},
            },
            tags=endpoint.get('tags', []) + ['discovered', 'http-api'],
        )

    @property
    def metadata(self) -> InstrumentMetadata:
        return self._metadata

    async def initialize(self) -> bool:
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(
                total=self._config.get('timeout', 30)
            )
            self._http_client = aiohttp.ClientSession(timeout=timeout)
            self._status = InstrumentStatus.AVAILABLE
            return True
        except Exception as e:
            logger.error(f"Failed to initialize HTTP API instrument: {e}")
            self._status = InstrumentStatus.ERROR
            return False

    async def shutdown(self) -> bool:
        if self._http_client:
            await self._http_client.close()
        self._status = InstrumentStatus.DISABLED
        return True

    async def health_check(self) -> bool:
        return self._http_client is not None and not self._http_client.closed

    async def execute(
        self,
        capability: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None
    ) -> Any:
        if capability != "call":
            raise ValueError(f"Unknown capability: {capability}")

        context = context or {}

        # Validate ethics
        if not await self._validate_ethics(capability, parameters, context):
            raise ValueError("Action blocked by ethical validation")

        start_time = datetime.now()
        success = False
        result = None
        error_msg = None

        try:
            # Build request
            base_url = self._config.get('base_url', self._api.base_url)
            path = self._endpoint['path']
            method = self._endpoint['method'].upper()

            # Substitute path parameters
            for key, value in parameters.items():
                if f'{{{key}}}' in path:
                    path = path.replace(f'{{{key}}}', str(value))

            url = f"{base_url.rstrip('/')}{path}"

            # Prepare request kwargs
            kwargs: Dict[str, Any] = {
                'headers': {
                    **self._config.get('headers', {}),
                    'Content-Type': 'application/json',
                }
            }

            # Add query parameters
            query_params = {
                k: v for k, v in parameters.items()
                if f'{{{k}}}' not in self._endpoint['path']
                and k != '_body'
            }
            if query_params:
                kwargs['params'] = query_params

            # Add body if present
            if '_body' in parameters:
                kwargs['json'] = parameters['_body']

            # Make request
            async with self._http_client.request(method, url, **kwargs) as response:
                result = {
                    'status': response.status,
                    'headers': dict(response.headers),
                    'body': await response.json() if 'json' in response.content_type else await response.text(),
                }
                success = response.status < 400

        except Exception as e:
            error_msg = str(e)
            raise

        finally:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            execution = InstrumentExecution(
                execution_id=hashlib.sha256(
                    f"{capability}:{datetime.now().isoformat()}".encode()
                ).hexdigest()[:16],
                instrument_id=self.metadata.instrument_id,
                capability_name=capability,
                parameters=parameters,
                result=result,
                success=success,
                execution_time_ms=execution_time,
                agent_id=context.get("agent_id"),
                project_id=context.get("project_id"),
                error_message=error_msg,
            )
            await self._record_execution(execution)

        return result


class ToolDiscoveryEngine:
    """
    Engine for discovering, validating, and registering tools.

    This engine takes discovered tools from web spidering and converts
    them into usable instruments and MCP server configurations.
    """

    _instance: Optional['ToolDiscoveryEngine'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._validator = ToolValidator()
        self._registered_tools: Dict[str, RegisteredTool] = {}
        self._mcp_configs: Dict[str, MCPServerConfig] = {}
        self._instrument_registry: Optional[InstrumentRegistry] = None
        self._graph_store = None
        self._collective_memory = None
        self._initialized = False
        self._hooks: Dict[str, List[Callable]] = {
            "tool_discovered": [],
            "tool_validated": [],
            "tool_registered": [],
            "tool_failed": [],
        }

    @classmethod
    async def get_instance(cls) -> 'ToolDiscoveryEngine':
        """Get or create the singleton instance."""
        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self):
        """Initialize the discovery engine."""
        if self._initialized:
            return

        try:
            self._instrument_registry = await InstrumentRegistry.get_instance()
        except Exception as e:
            logger.warning(f"Instrument registry not available: {e}")

        self._initialized = True
        logger.info("ToolDiscoveryEngine initialized")

    async def set_integrations(self, graph_store=None, collective_memory=None):
        """Set framework integrations."""
        self._graph_store = graph_store
        self._collective_memory = collective_memory

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

    async def process_crawl_result(
        self,
        result: CrawlResult,
        auto_register: bool = False,
        min_quality: ToolQuality = ToolQuality.MEDIUM,
    ) -> List[RegisteredTool]:
        """
        Process a crawl result and register discovered tools.

        Args:
            result: CrawlResult from web spider
            auto_register: Whether to automatically register validated tools
            min_quality: Minimum quality level for registration

        Returns:
            List of registered tools
        """
        registered = []

        # Process discovered tools
        for tool in result.discovered_tools:
            await self._run_hooks("tool_discovered", tool)

            # Validate tool
            validation = self._validator.validate(tool)
            await self._run_hooks("tool_validated", {"tool": tool, "validation": validation})

            if not validation.is_valid:
                await self._run_hooks("tool_failed", {"tool": tool, "reason": "validation_failed"})
                continue

            # Check quality threshold
            quality_order = [ToolQuality.UNKNOWN, ToolQuality.LOW, ToolQuality.MEDIUM, ToolQuality.HIGH]
            if quality_order.index(validation.quality) < quality_order.index(min_quality):
                logger.info(f"Tool {tool.name} below quality threshold: {validation.quality.value}")
                continue

            # Create registered tool entry
            reg_tool = RegisteredTool(
                tool_id=tool.tool_id,
                name=tool.name,
                description=tool.description,
                source=tool.source_type,
                original=tool,
                validation=validation,
                status=RegistrationStatus.VALIDATED,
                registered_at=datetime.now(),
                last_used=None,
                use_count=0,
                config=tool.installation,
            )

            self._registered_tools[tool.tool_id] = reg_tool

            # Auto-register if enabled
            if auto_register:
                success = await self._register_tool(reg_tool)
                if success:
                    registered.append(reg_tool)
                    await self._run_hooks("tool_registered", reg_tool)

        # Process discovered APIs
        for api in result.discovered_apis:
            mcp_config = await self._generate_mcp_config(api)
            if mcp_config:
                self._mcp_configs[mcp_config.name] = mcp_config

        # Store in graph
        await self._store_discoveries(result)

        return registered

    async def register_tool(self, tool_id: str) -> bool:
        """Register a validated tool by ID."""
        if tool_id not in self._registered_tools:
            return False

        reg_tool = self._registered_tools[tool_id]
        if reg_tool.status != RegistrationStatus.VALIDATED:
            return False

        return await self._register_tool(reg_tool)

    async def _register_tool(self, reg_tool: RegisteredTool) -> bool:
        """Internal method to register a tool."""
        try:
            if reg_tool.source == 'api_endpoint':
                # Register as HTTP API instrument
                success = await self._register_http_instrument(reg_tool)
            elif reg_tool.source == 'mcp':
                # Generate MCP server config
                success = await self._register_mcp_tool(reg_tool)
            elif reg_tool.source == 'graphql':
                # Register GraphQL endpoint
                success = await self._register_graphql_tool(reg_tool)
            else:
                logger.warning(f"Unknown tool source type: {reg_tool.source}")
                success = False

            if success:
                reg_tool.status = RegistrationStatus.REGISTERED
                reg_tool.registered_at = datetime.now()
                logger.info(f"Registered tool: {reg_tool.name}")
            else:
                reg_tool.status = RegistrationStatus.FAILED

            return success

        except Exception as e:
            logger.error(f"Failed to register tool {reg_tool.name}: {e}")
            reg_tool.status = RegistrationStatus.FAILED
            return False

    async def _register_http_instrument(self, reg_tool: RegisteredTool) -> bool:
        """Register an HTTP API as an instrument."""
        if not self._instrument_registry:
            logger.warning("Instrument registry not available")
            return False

        # For HTTP APIs, we need the original API spec
        # This is a simplified version - would need the full API object
        original = reg_tool.original
        install = original.installation

        # Create a simple instrument class
        class DynamicHTTPInstrument(Instrument):
            def __init__(self, tool_config):
                super().__init__(tool_config)
                self._tool_config = tool_config
                self._metadata = InstrumentMetadata(
                    instrument_id=tool_config['tool_id'],
                    name=tool_config['name'],
                    description=tool_config['description'],
                    version="1.0.0",
                    instrument_type=InstrumentType.API,
                    capabilities=[
                        InstrumentCapability(
                            name="call",
                            description=f"Call the {tool_config['name']} API",
                            parameters=tool_config.get('parameters', {}),
                            return_type="dict",
                            async_only=True,
                        )
                    ],
                    tags=['discovered', 'http-api'],
                )

            @property
            def metadata(self):
                return self._metadata

            async def initialize(self):
                self._status = InstrumentStatus.AVAILABLE
                return True

            async def shutdown(self):
                self._status = InstrumentStatus.DISABLED
                return True

            async def health_check(self):
                return True

            async def execute(self, capability, parameters, context=None):
                import aiohttp

                install = self._tool_config.get('installation', {})
                base_url = install.get('base_url', '')
                path = install.get('path', '')
                method = install.get('method', 'GET')

                url = f"{base_url.rstrip('/')}{path}"

                async with aiohttp.ClientSession() as session:
                    async with session.request(method, url, json=parameters) as resp:
                        return {
                            'status': resp.status,
                            'body': await resp.json() if 'json' in resp.content_type else await resp.text(),
                        }

        # Register the instrument class
        tool_config = {
            'tool_id': original.tool_id,
            'name': original.name,
            'description': original.description,
            'parameters': original.parameters,
            'installation': install,
        }

        # Add to registry's instrument classes
        self._instrument_registry._instrument_classes[original.tool_id] = \
            lambda config=tool_config: DynamicHTTPInstrument(config)

        # Register instance
        instrument = await self._instrument_registry.register(
            original.tool_id,
            config=tool_config,
            auto_initialize=True,
        )

        return instrument is not None

    async def _register_mcp_tool(self, reg_tool: RegisteredTool) -> bool:
        """Register an MCP tool configuration."""
        original = reg_tool.original
        install = original.installation

        # Generate MCP server config
        mcp_config = MCPServerConfig(
            name=original.name.replace(' ', '_').lower(),
            description=original.description,
            type=install.get('type', 'stdio'),
            source_url=original.source_url,
            tools=[{
                'name': original.name,
                'description': original.description,
                'parameters': original.parameters,
            }],
            connection=self._build_mcp_connection(install),
            generated_at=datetime.now(),
        )

        self._mcp_configs[mcp_config.name] = mcp_config

        # Note: Actual MCP server connection happens through MCPConfig
        # This just prepares the configuration
        logger.info(f"Generated MCP config for: {mcp_config.name}")
        return True

    async def _register_graphql_tool(self, reg_tool: RegisteredTool) -> bool:
        """Register a GraphQL endpoint as a tool."""
        # Similar to HTTP but with GraphQL query building
        # For now, treat as HTTP with special handling
        return await self._register_http_instrument(reg_tool)

    def _build_mcp_connection(self, install: Dict[str, Any]) -> Dict[str, Any]:
        """Build MCP connection config from installation info."""
        if install.get('type') == 'npm':
            return {
                'command': 'npx',
                'args': ['-y', install.get('package', '')],
            }
        elif install.get('type') == 'pip':
            return {
                'command': 'python',
                'args': ['-m', install.get('package', '')],
            }
        elif 'command' in install:
            return {
                'command': install['command'],
                'args': install.get('args', []),
            }
        elif 'url' in install:
            return {
                'url': install['url'],
                'headers': install.get('headers', {}),
            }
        else:
            return install

    async def _generate_mcp_config(self, api: DiscoveredAPI) -> Optional[MCPServerConfig]:
        """Generate MCP config from discovered API."""
        if not api.endpoints:
            return None

        # Generate tool definitions from endpoints
        tools = []
        for endpoint in api.endpoints[:20]:  # Limit endpoints
            tools.append({
                'name': endpoint.get('operation_id', f"{endpoint['method']}_{endpoint['path']}"),
                'description': endpoint.get('summary', endpoint.get('description', '')),
                'input_schema': {
                    'type': 'object',
                    'properties': {
                        p['name']: {'type': p.get('schema', {}).get('type', 'string')}
                        for p in endpoint.get('parameters', [])
                    },
                },
            })

        return MCPServerConfig(
            name=api.name.replace(' ', '_').lower(),
            description=api.description,
            type='http-stream',  # Use HTTP streaming for remote APIs
            source_url=api.spec_url,
            tools=tools,
            connection={
                'url': api.base_url,
                'headers': {},
            },
            generated_at=datetime.now(),
        )

    async def _store_discoveries(self, result: CrawlResult):
        """Store discoveries in graph store."""
        if not self._graph_store:
            return

        try:
            # Store crawl result summary
            await self._graph_store.add_memory(
                area="INSTRUMENTS",
                content=json.dumps({
                    'type': 'crawl_result',
                    'seed_url': result.seed_url,
                    'pages_crawled': result.pages_crawled,
                    'apis_discovered': result.apis_discovered,
                    'tools_discovered': result.tools_discovered,
                    'timestamp': datetime.now().isoformat(),
                }),
                metadata={
                    'type': 'crawl_result',
                    'seed_url': result.seed_url,
                }
            )

            # Store each registered tool
            for tool_id, reg_tool in self._registered_tools.items():
                await self._graph_store.add_memory(
                    area="INSTRUMENTS",
                    content=json.dumps(reg_tool.to_dict()),
                    metadata={
                        'type': 'registered_tool',
                        'tool_id': tool_id,
                        'status': reg_tool.status.value,
                    }
                )

        except Exception as e:
            logger.warning(f"Failed to store discoveries: {e}")

    # Query methods
    def get_registered_tools(self) -> List[RegisteredTool]:
        """Get all registered tools."""
        return list(self._registered_tools.values())

    def get_tool(self, tool_id: str) -> Optional[RegisteredTool]:
        """Get a registered tool by ID."""
        return self._registered_tools.get(tool_id)

    def get_mcp_configs(self) -> List[MCPServerConfig]:
        """Get all generated MCP configurations."""
        return list(self._mcp_configs.values())

    def get_mcp_config(self, name: str) -> Optional[MCPServerConfig]:
        """Get an MCP config by name."""
        return self._mcp_configs.get(name)

    def get_statistics(self) -> Dict[str, Any]:
        """Get discovery engine statistics."""
        status_counts = {}
        for tool in self._registered_tools.values():
            status = tool.status.value
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            'total_tools': len(self._registered_tools),
            'mcp_configs': len(self._mcp_configs),
            'status_breakdown': status_counts,
            'tools_by_source': self._count_by_source(),
        }

    def _count_by_source(self) -> Dict[str, int]:
        """Count tools by source type."""
        counts = {}
        for tool in self._registered_tools.values():
            source = tool.source
            counts[source] = counts.get(source, 0) + 1
        return counts


# Convenience functions
async def get_discovery_engine() -> ToolDiscoveryEngine:
    """Get the tool discovery engine instance."""
    return await ToolDiscoveryEngine.get_instance()


async def discover_and_register(
    url: str,
    auto_register: bool = True,
    min_quality: ToolQuality = ToolQuality.MEDIUM,
) -> List[RegisteredTool]:
    """
    Discover and register tools from a URL.

    This is a convenience function that combines web spidering
    with tool discovery and registration.
    """
    from python.helpers.web_spider import WebSpider, CrawlConfig

    # Create spider
    config = CrawlConfig(
        max_depth=2,
        max_pages=50,
        extract_api_specs=True,
        parse_documentation=True,
    )
    spider = WebSpider(config)

    # Crawl
    result = await spider.crawl(url)
    await spider.close()

    # Process results
    engine = await get_discovery_engine()
    return await engine.process_crawl_result(
        result,
        auto_register=auto_register,
        min_quality=min_quality,
    )
