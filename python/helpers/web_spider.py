"""
Web Spider for Vessels A0 Framework

This module implements autonomous web crawling and API discovery capabilities.
The spider can crawl documentation sites, API registries, and tool repositories
to discover new capabilities that can be dynamically registered.

Key features:
1. Crawl web pages following links up to configurable depth
2. Detect and parse API specifications (OpenAPI, JSON-RPC, GraphQL)
3. Extract tool definitions from documentation
4. Track discovered content in the graph store
5. Support for rate limiting and politeness
6. Security-first with guardian sanitization
"""

import asyncio
import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class SourceType(Enum):
    """Types of sources that can be spidered."""
    OPENAPI = "openapi"
    SWAGGER = "swagger"
    JSON_RPC = "json_rpc"
    GRAPHQL = "graphql"
    REST_DOCS = "rest_docs"
    MCP_REGISTRY = "mcp_registry"
    TOOL_REGISTRY = "tool_registry"
    DOCUMENTATION = "documentation"
    GITHUB_REPO = "github_repo"
    NPM_PACKAGE = "npm_package"
    PYPI_PACKAGE = "pypi_package"
    UNKNOWN = "unknown"


class CrawlStatus(Enum):
    """Status of a crawl operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    BLOCKED = "blocked"


@dataclass
class CrawlConfig:
    """Configuration for web crawling."""
    max_depth: int = 3
    max_pages: int = 100
    rate_limit_requests: int = 10  # requests per second
    rate_limit_period: float = 1.0  # seconds
    request_timeout: float = 30.0
    user_agent: str = "Vessels-Spider/1.0 (Autonomous Agent Framework)"
    respect_robots_txt: bool = True
    allowed_domains: List[str] = field(default_factory=list)
    blocked_domains: List[str] = field(default_factory=list)
    follow_external_links: bool = False
    extract_api_specs: bool = True
    parse_documentation: bool = True
    store_content: bool = True


@dataclass
class DiscoveredPage:
    """A page discovered during crawling."""
    url: str
    title: str
    content: str
    source_type: SourceType
    links: List[str]
    api_specs: List[Dict[str, Any]]
    discovered_tools: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    crawled_at: datetime
    content_hash: str
    status_code: int
    headers: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content[:1000] if self.content else "",
            "source_type": self.source_type.value,
            "links": self.links[:50],  # Limit stored links
            "api_specs": self.api_specs,
            "discovered_tools": self.discovered_tools,
            "metadata": self.metadata,
            "crawled_at": self.crawled_at.isoformat(),
            "content_hash": self.content_hash,
            "status_code": self.status_code,
        }


@dataclass
class DiscoveredAPI:
    """An API discovered from documentation or specs."""
    api_id: str
    name: str
    description: str
    base_url: str
    spec_url: str
    spec_type: SourceType
    version: str
    endpoints: List[Dict[str, Any]]
    auth_methods: List[str]
    discovered_at: datetime
    source_url: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "api_id": self.api_id,
            "name": self.name,
            "description": self.description,
            "base_url": self.base_url,
            "spec_url": self.spec_url,
            "spec_type": self.spec_type.value,
            "version": self.version,
            "endpoints": self.endpoints,
            "auth_methods": self.auth_methods,
            "discovered_at": self.discovered_at.isoformat(),
            "source_url": self.source_url,
        }


@dataclass
class DiscoveredTool:
    """A tool discovered from MCP registries or documentation."""
    tool_id: str
    name: str
    description: str
    source_type: str  # mcp, instrument, api_endpoint
    source_url: str
    parameters: Dict[str, Any]
    return_type: str
    installation: Dict[str, Any]  # How to install/configure
    discovered_at: datetime
    confidence: float  # 0-1, how confident we are about the extraction

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "parameters": self.parameters,
            "return_type": self.return_type,
            "installation": self.installation,
            "discovered_at": self.discovered_at.isoformat(),
            "confidence": self.confidence,
        }


@dataclass
class CrawlResult:
    """Result of a crawl operation."""
    seed_url: str
    pages_crawled: int
    pages_failed: int
    apis_discovered: int
    tools_discovered: int
    duration_seconds: float
    status: CrawlStatus
    errors: List[str]
    discovered_pages: List[DiscoveredPage]
    discovered_apis: List[DiscoveredAPI]
    discovered_tools: List[DiscoveredTool]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "seed_url": self.seed_url,
            "pages_crawled": self.pages_crawled,
            "pages_failed": self.pages_failed,
            "apis_discovered": self.apis_discovered,
            "tools_discovered": self.tools_discovered,
            "duration_seconds": self.duration_seconds,
            "status": self.status.value,
            "errors": self.errors[:20],  # Limit stored errors
            "discovered_apis": [a.to_dict() for a in self.discovered_apis],
            "discovered_tools": [t.to_dict() for t in self.discovered_tools],
        }


class ContentParser(ABC):
    """Abstract base for content parsers."""

    @abstractmethod
    def can_parse(self, content: str, content_type: str, url: str) -> bool:
        """Check if this parser can handle the content."""
        pass

    @abstractmethod
    def parse(self, content: str, url: str) -> Tuple[List[DiscoveredAPI], List[DiscoveredTool]]:
        """Parse content and extract APIs/tools."""
        pass


class OpenAPIParser(ContentParser):
    """Parser for OpenAPI/Swagger specifications."""

    def can_parse(self, content: str, content_type: str, url: str) -> bool:
        if not content:
            return False
        # Check for OpenAPI indicators
        try:
            data = json.loads(content) if content.strip().startswith('{') else None
            if data:
                return 'openapi' in data or 'swagger' in data
        except:
            pass
        # Check URL patterns
        return any(x in url.lower() for x in ['openapi', 'swagger', 'api-docs'])

    def parse(self, content: str, url: str) -> Tuple[List[DiscoveredAPI], List[DiscoveredTool]]:
        apis = []
        tools = []

        try:
            data = json.loads(content)

            # Extract API info
            info = data.get('info', {})
            servers = data.get('servers', [{'url': url}])
            base_url = servers[0].get('url', url) if servers else url

            spec_type = SourceType.OPENAPI if 'openapi' in data else SourceType.SWAGGER

            # Extract endpoints as potential tools
            endpoints = []
            paths = data.get('paths', {})

            for path, methods in paths.items():
                for method, details in methods.items():
                    if method in ['get', 'post', 'put', 'patch', 'delete']:
                        endpoint = {
                            'path': path,
                            'method': method.upper(),
                            'operation_id': details.get('operationId', ''),
                            'summary': details.get('summary', ''),
                            'description': details.get('description', ''),
                            'parameters': details.get('parameters', []),
                            'request_body': details.get('requestBody', {}),
                            'responses': details.get('responses', {}),
                            'tags': details.get('tags', []),
                        }
                        endpoints.append(endpoint)

                        # Create a tool for each endpoint
                        tool_id = hashlib.sha256(
                            f"{base_url}{path}{method}".encode()
                        ).hexdigest()[:16]

                        tool = DiscoveredTool(
                            tool_id=tool_id,
                            name=details.get('operationId', f"{method}_{path.replace('/', '_')}"),
                            description=details.get('summary', details.get('description', '')),
                            source_type='api_endpoint',
                            source_url=url,
                            parameters=self._extract_parameters(details),
                            return_type=self._infer_return_type(details.get('responses', {})),
                            installation={
                                'type': 'http',
                                'base_url': base_url,
                                'path': path,
                                'method': method.upper(),
                            },
                            discovered_at=datetime.now(),
                            confidence=0.9,  # High confidence for OpenAPI specs
                        )
                        tools.append(tool)

            # Extract auth methods
            auth_methods = []
            security_schemes = data.get('components', {}).get('securitySchemes', {})
            for name, scheme in security_schemes.items():
                auth_methods.append(f"{name}:{scheme.get('type', 'unknown')}")

            api = DiscoveredAPI(
                api_id=hashlib.sha256(url.encode()).hexdigest()[:16],
                name=info.get('title', 'Unknown API'),
                description=info.get('description', ''),
                base_url=base_url,
                spec_url=url,
                spec_type=spec_type,
                version=info.get('version', '1.0.0'),
                endpoints=endpoints,
                auth_methods=auth_methods,
                discovered_at=datetime.now(),
                source_url=url,
            )
            apis.append(api)

        except Exception as e:
            logger.warning(f"Failed to parse OpenAPI spec from {url}: {e}")

        return apis, tools

    def _extract_parameters(self, operation: Dict) -> Dict[str, Any]:
        """Extract parameters from operation."""
        params = {}

        # Query/path/header parameters
        for param in operation.get('parameters', []):
            params[param.get('name', '')] = {
                'type': param.get('schema', {}).get('type', 'string'),
                'required': param.get('required', False),
                'in': param.get('in', 'query'),
                'description': param.get('description', ''),
            }

        # Request body
        request_body = operation.get('requestBody', {})
        if request_body:
            content = request_body.get('content', {})
            for media_type, schema in content.items():
                params['_body'] = {
                    'type': 'object',
                    'media_type': media_type,
                    'schema': schema.get('schema', {}),
                    'required': request_body.get('required', False),
                }

        return params

    def _infer_return_type(self, responses: Dict) -> str:
        """Infer return type from responses."""
        for code, response in responses.items():
            if code.startswith('2'):
                content = response.get('content', {})
                for media_type in content:
                    return media_type
        return 'application/json'


class MCPRegistryParser(ContentParser):
    """Parser for MCP server/tool registries."""

    # Known MCP registry patterns
    MCP_INDICATORS = ['mcp', 'model-context-protocol', 'mcp-server', 'mcp-tool']

    def can_parse(self, content: str, content_type: str, url: str) -> bool:
        if not content:
            return False
        url_lower = url.lower()
        return any(ind in url_lower for ind in self.MCP_INDICATORS)

    def parse(self, content: str, url: str) -> Tuple[List[DiscoveredAPI], List[DiscoveredTool]]:
        apis = []
        tools = []

        try:
            # Try to parse as JSON first (npm package, GitHub API, etc.)
            if content.strip().startswith('{'):
                data = json.loads(content)
                tools.extend(self._parse_package_json(data, url))
            else:
                # Parse as HTML/Markdown documentation
                tools.extend(self._parse_documentation(content, url))

        except Exception as e:
            logger.warning(f"Failed to parse MCP registry from {url}: {e}")

        return apis, tools

    def _parse_package_json(self, data: Dict, url: str) -> List[DiscoveredTool]:
        """Parse npm package.json for MCP server info."""
        tools = []

        # Check if it's an MCP server package
        name = data.get('name', '')
        description = data.get('description', '')

        if 'mcp' in name.lower() or 'mcp' in description.lower():
            # Extract MCP tool info
            tool = DiscoveredTool(
                tool_id=hashlib.sha256(name.encode()).hexdigest()[:16],
                name=name,
                description=description,
                source_type='mcp',
                source_url=url,
                parameters={},  # Will be populated when server is connected
                return_type='dynamic',
                installation={
                    'type': 'npm' if 'npm' in url else 'github',
                    'package': name,
                    'version': data.get('version', 'latest'),
                    'bin': data.get('bin', {}),
                },
                discovered_at=datetime.now(),
                confidence=0.7,  # Medium confidence - needs connection to verify
            )
            tools.append(tool)

        return tools

    def _parse_documentation(self, content: str, url: str) -> List[DiscoveredTool]:
        """Parse documentation for MCP tool info."""
        tools = []

        # Use BeautifulSoup to parse HTML
        soup = BeautifulSoup(content, 'html.parser')

        # Look for common documentation patterns
        # This is a simplified heuristic - could be enhanced with LLM
        code_blocks = soup.find_all(['code', 'pre'])

        for block in code_blocks:
            text = block.get_text()
            # Look for MCP server configuration patterns
            if 'mcp' in text.lower() and ('server' in text.lower() or 'tool' in text.lower()):
                try:
                    # Try to extract JSON configuration
                    json_match = re.search(r'\{[^{}]*"name"[^{}]*\}', text, re.DOTALL)
                    if json_match:
                        config = json.loads(json_match.group())
                        tool = DiscoveredTool(
                            tool_id=hashlib.sha256(str(config).encode()).hexdigest()[:16],
                            name=config.get('name', 'unknown'),
                            description=config.get('description', ''),
                            source_type='mcp',
                            source_url=url,
                            parameters={},
                            return_type='dynamic',
                            installation=config,
                            discovered_at=datetime.now(),
                            confidence=0.5,  # Lower confidence for extracted configs
                        )
                        tools.append(tool)
                except:
                    pass

        return tools


class GraphQLParser(ContentParser):
    """Parser for GraphQL schemas and introspection results."""

    def can_parse(self, content: str, content_type: str, url: str) -> bool:
        if not content:
            return False
        return 'graphql' in url.lower() or (
            content.strip().startswith('{') and
            '__schema' in content
        )

    def parse(self, content: str, url: str) -> Tuple[List[DiscoveredAPI], List[DiscoveredTool]]:
        apis = []
        tools = []

        try:
            data = json.loads(content)
            schema = data.get('data', {}).get('__schema', data.get('__schema', {}))

            if not schema:
                return apis, tools

            # Extract query/mutation types as tools
            query_type = schema.get('queryType', {})
            mutation_type = schema.get('mutationType', {})

            types = schema.get('types', [])
            type_map = {t['name']: t for t in types}

            for type_name in [query_type.get('name'), mutation_type.get('name')]:
                if type_name and type_name in type_map:
                    type_def = type_map[type_name]
                    for field in type_def.get('fields', []):
                        tool = DiscoveredTool(
                            tool_id=hashlib.sha256(
                                f"{url}:{type_name}:{field['name']}".encode()
                            ).hexdigest()[:16],
                            name=field['name'],
                            description=field.get('description', ''),
                            source_type='graphql',
                            source_url=url,
                            parameters=self._extract_args(field.get('args', [])),
                            return_type=self._format_type(field.get('type', {})),
                            installation={
                                'type': 'graphql',
                                'endpoint': url,
                                'operation': 'query' if type_name == query_type.get('name') else 'mutation',
                            },
                            discovered_at=datetime.now(),
                            confidence=0.85,
                        )
                        tools.append(tool)

            api = DiscoveredAPI(
                api_id=hashlib.sha256(url.encode()).hexdigest()[:16],
                name=f"GraphQL API at {urlparse(url).netloc}",
                description="GraphQL API discovered via introspection",
                base_url=url,
                spec_url=url,
                spec_type=SourceType.GRAPHQL,
                version="1.0",
                endpoints=[{'type': 'graphql', 'url': url}],
                auth_methods=[],
                discovered_at=datetime.now(),
                source_url=url,
            )
            apis.append(api)

        except Exception as e:
            logger.warning(f"Failed to parse GraphQL schema from {url}: {e}")

        return apis, tools

    def _extract_args(self, args: List[Dict]) -> Dict[str, Any]:
        """Extract arguments as parameters."""
        params = {}
        for arg in args:
            params[arg['name']] = {
                'type': self._format_type(arg.get('type', {})),
                'description': arg.get('description', ''),
                'default': arg.get('defaultValue'),
            }
        return params

    def _format_type(self, type_def: Dict) -> str:
        """Format GraphQL type as string."""
        kind = type_def.get('kind', '')
        if kind == 'NON_NULL':
            return f"{self._format_type(type_def.get('ofType', {}))}!"
        elif kind == 'LIST':
            return f"[{self._format_type(type_def.get('ofType', {}))}]"
        else:
            return type_def.get('name', 'unknown')


class WebSpider:
    """
    Autonomous web spider for discovering APIs and tools.

    This spider crawls web pages, detects API specifications,
    and extracts tool definitions that can be registered dynamically.
    """

    def __init__(self, config: Optional[CrawlConfig] = None):
        self.config = config or CrawlConfig()
        self._parsers: List[ContentParser] = [
            OpenAPIParser(),
            MCPRegistryParser(),
            GraphQLParser(),
        ]
        self._visited_urls: Set[str] = set()
        self._content_hashes: Set[str] = set()
        self._rate_limiter = asyncio.Semaphore(self.config.rate_limit_requests)
        self._collective_memory = None
        self._graph_store = None
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
            headers = {'User-Agent': self.config.user_agent}
            self._session = aiohttp.ClientSession(timeout=timeout, headers=headers)
        return self._session

    async def close(self):
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def set_integrations(self, collective_memory=None, graph_store=None):
        """Set framework integrations."""
        self._collective_memory = collective_memory
        self._graph_store = graph_store

    def add_parser(self, parser: ContentParser):
        """Add a custom content parser."""
        self._parsers.append(parser)

    async def crawl(
        self,
        seed_url: str,
        depth: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> CrawlResult:
        """
        Crawl starting from a seed URL.

        Args:
            seed_url: Starting URL for the crawl
            depth: Maximum depth to crawl (overrides config)
            max_pages: Maximum pages to crawl (overrides config)

        Returns:
            CrawlResult with discovered pages, APIs, and tools
        """
        max_depth = depth if depth is not None else self.config.max_depth
        max_pages = max_pages if max_pages is not None else self.config.max_pages

        start_time = datetime.now()
        self._visited_urls.clear()
        self._content_hashes.clear()

        discovered_pages: List[DiscoveredPage] = []
        discovered_apis: List[DiscoveredAPI] = []
        discovered_tools: List[DiscoveredTool] = []
        errors: List[str] = []
        pages_failed = 0

        # Queue: (url, depth)
        queue: asyncio.Queue[Tuple[str, int]] = asyncio.Queue()
        await queue.put((seed_url, 0))

        try:
            while not queue.empty() and len(discovered_pages) < max_pages:
                url, current_depth = await queue.get()

                # Skip if already visited
                if url in self._visited_urls:
                    continue

                # Skip if exceeds max depth
                if current_depth > max_depth:
                    continue

                # Check domain restrictions
                if not self._is_allowed_domain(url):
                    continue

                self._visited_urls.add(url)

                try:
                    # Rate limiting
                    async with self._rate_limiter:
                        await asyncio.sleep(
                            self.config.rate_limit_period / self.config.rate_limit_requests
                        )
                        page = await self._fetch_and_parse(url)

                    if page:
                        # Check for duplicate content
                        if page.content_hash in self._content_hashes:
                            continue
                        self._content_hashes.add(page.content_hash)

                        discovered_pages.append(page)
                        discovered_apis.extend(page.api_specs)  # type: ignore
                        discovered_tools.extend(page.discovered_tools)  # type: ignore

                        # Add discovered links to queue
                        if current_depth < max_depth:
                            for link in page.links:
                                if link not in self._visited_urls:
                                    await queue.put((link, current_depth + 1))

                        # Store in graph if available
                        if self._graph_store:
                            await self._store_page(page)

                        logger.info(
                            f"Crawled {url}: {len(page.discovered_tools)} tools, "
                            f"{len(page.api_specs)} APIs"
                        )

                except Exception as e:
                    pages_failed += 1
                    error_msg = f"Failed to crawl {url}: {str(e)}"
                    errors.append(error_msg)
                    logger.warning(error_msg)

        finally:
            await self.close()

        duration = (datetime.now() - start_time).total_seconds()

        return CrawlResult(
            seed_url=seed_url,
            pages_crawled=len(discovered_pages),
            pages_failed=pages_failed,
            apis_discovered=len(discovered_apis),
            tools_discovered=len(discovered_tools),
            duration_seconds=duration,
            status=CrawlStatus.COMPLETED if pages_failed < len(discovered_pages) else CrawlStatus.FAILED,
            errors=errors,
            discovered_pages=discovered_pages,
            discovered_apis=discovered_apis,
            discovered_tools=discovered_tools,
        )

    async def discover_api(self, spec_url: str) -> Optional[DiscoveredAPI]:
        """
        Discover API from a specification URL.

        Args:
            spec_url: URL to an API specification (OpenAPI, GraphQL, etc.)

        Returns:
            DiscoveredAPI if successful, None otherwise
        """
        try:
            page = await self._fetch_and_parse(spec_url)
            if page and page.api_specs:
                return page.api_specs[0]  # type: ignore
        except Exception as e:
            logger.warning(f"Failed to discover API from {spec_url}: {e}")
        return None

    async def discover_mcp_server(self, url: str) -> List[DiscoveredTool]:
        """
        Discover MCP server tools from a URL.

        Args:
            url: URL to MCP server documentation or registry

        Returns:
            List of discovered tools
        """
        try:
            page = await self._fetch_and_parse(url)
            if page:
                return [t for t in page.discovered_tools if t.source_type == 'mcp']  # type: ignore
        except Exception as e:
            logger.warning(f"Failed to discover MCP server from {url}: {e}")
        return []

    def _is_allowed_domain(self, url: str) -> bool:
        """Check if URL domain is allowed."""
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Check blocked domains
        for blocked in self.config.blocked_domains:
            if blocked.lower() in domain:
                return False

        # Check allowed domains (if specified)
        if self.config.allowed_domains:
            for allowed in self.config.allowed_domains:
                if allowed.lower() in domain:
                    return True
            return False

        return True

    async def _fetch_and_parse(self, url: str) -> Optional[DiscoveredPage]:
        """Fetch and parse a single URL."""
        session = await self._get_session()

        try:
            async with session.get(url) as response:
                if response.status != 200:
                    return None

                content = await response.text()
                content_type = response.headers.get('Content-Type', '')

                # Sanitize content
                from python.helpers.guardians import guard_web
                content = guard_web(content, source=f"spider:{url}")

                # Detect source type
                source_type = self._detect_source_type(content, content_type, url)

                # Parse content
                apis, tools = await self._parse_content(content, content_type, url)

                # Extract links
                links = self._extract_links(content, url) if self.config.parse_documentation else []

                # Extract title
                title = self._extract_title(content)

                # Calculate content hash
                content_hash = hashlib.sha256(content.encode()).hexdigest()

                return DiscoveredPage(
                    url=url,
                    title=title,
                    content=content if self.config.store_content else "",
                    source_type=source_type,
                    links=links,
                    api_specs=apis,  # type: ignore
                    discovered_tools=tools,  # type: ignore
                    metadata={
                        'content_type': content_type,
                        'content_length': len(content),
                    },
                    crawled_at=datetime.now(),
                    content_hash=content_hash,
                    status_code=response.status,
                    headers=dict(response.headers),
                )

        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

    def _detect_source_type(self, content: str, content_type: str, url: str) -> SourceType:
        """Detect the type of source based on content and URL."""
        url_lower = url.lower()

        # Check URL patterns first
        if 'openapi' in url_lower or 'swagger' in url_lower:
            return SourceType.OPENAPI
        if 'graphql' in url_lower:
            return SourceType.GRAPHQL
        if 'mcp' in url_lower:
            return SourceType.MCP_REGISTRY
        if 'github.com' in url_lower:
            return SourceType.GITHUB_REPO
        if 'npmjs.com' in url_lower or 'registry.npmjs.org' in url_lower:
            return SourceType.NPM_PACKAGE
        if 'pypi.org' in url_lower:
            return SourceType.PYPI_PACKAGE

        # Check content
        try:
            if content.strip().startswith('{'):
                data = json.loads(content)
                if 'openapi' in data:
                    return SourceType.OPENAPI
                if 'swagger' in data:
                    return SourceType.SWAGGER
                if '__schema' in str(data):
                    return SourceType.GRAPHQL
        except:
            pass

        return SourceType.DOCUMENTATION

    async def _parse_content(
        self,
        content: str,
        content_type: str,
        url: str
    ) -> Tuple[List[DiscoveredAPI], List[DiscoveredTool]]:
        """Parse content using available parsers."""
        all_apis = []
        all_tools = []

        for parser in self._parsers:
            if parser.can_parse(content, content_type, url):
                try:
                    apis, tools = parser.parse(content, url)
                    all_apis.extend(apis)
                    all_tools.extend(tools)
                except Exception as e:
                    logger.warning(f"Parser {parser.__class__.__name__} failed: {e}")

        return all_apis, all_tools

    def _extract_links(self, content: str, base_url: str) -> List[str]:
        """Extract links from HTML content."""
        links = []

        try:
            soup = BeautifulSoup(content, 'html.parser')

            for a in soup.find_all('a', href=True):
                href = a['href']

                # Skip fragment-only links
                if href.startswith('#'):
                    continue

                # Make absolute
                absolute_url = urljoin(base_url, href)
                parsed = urlparse(absolute_url)

                # Only HTTP(S)
                if parsed.scheme not in ['http', 'https']:
                    continue

                # Check external link policy
                if not self.config.follow_external_links:
                    base_domain = urlparse(base_url).netloc
                    link_domain = parsed.netloc
                    if base_domain != link_domain:
                        continue

                links.append(absolute_url)

        except Exception as e:
            logger.warning(f"Failed to extract links: {e}")

        return list(set(links))[:100]  # Deduplicate and limit

    def _extract_title(self, content: str) -> str:
        """Extract title from HTML content."""
        try:
            soup = BeautifulSoup(content, 'html.parser')
            title_tag = soup.find('title')
            if title_tag:
                return title_tag.get_text().strip()[:200]
        except:
            pass
        return ""

    async def _store_page(self, page: DiscoveredPage):
        """Store discovered page in graph store."""
        if not self._graph_store:
            return

        try:
            # Store as knowledge node
            await self._graph_store.add_memory(
                area="INSTRUMENTS",
                content=json.dumps(page.to_dict()),
                metadata={
                    'type': 'discovered_page',
                    'source_type': page.source_type.value,
                    'url': page.url,
                    'tools_count': len(page.discovered_tools),
                    'apis_count': len(page.api_specs),
                }
            )
        except Exception as e:
            logger.warning(f"Failed to store page in graph: {e}")


# Factory function
async def create_spider(
    config: Optional[CrawlConfig] = None,
    collective_memory=None,
    graph_store=None,
) -> WebSpider:
    """Create and configure a web spider."""
    spider = WebSpider(config)
    await spider.set_integrations(collective_memory, graph_store)
    return spider


# Convenience functions for common use cases
async def discover_openapi(url: str) -> Optional[DiscoveredAPI]:
    """Quick function to discover an OpenAPI spec."""
    spider = WebSpider(CrawlConfig(max_depth=0, max_pages=1))
    result = await spider.crawl(url, depth=0, max_pages=1)
    await spider.close()
    return result.discovered_apis[0] if result.discovered_apis else None


async def discover_mcp_tools(url: str) -> List[DiscoveredTool]:
    """Quick function to discover MCP tools from a URL."""
    spider = WebSpider(CrawlConfig(max_depth=1, max_pages=10))
    return await spider.discover_mcp_server(url)
