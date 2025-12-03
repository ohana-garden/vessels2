# Web Spidering and Tool Discovery

The Vessels framework includes an autonomous web spidering system that can discover, validate, and register new tools and APIs from web sources.

## Overview

The web spidering system consists of several interconnected components:

1. **Web Spider** (`python/helpers/web_spider.py`) - Crawls web pages and extracts structured data
2. **Tool Discovery Engine** (`python/helpers/tool_discovery.py`) - Validates and registers discovered tools
3. **Spider Scheduler** (`python/helpers/spider_scheduler.py`) - Manages scheduled crawling
4. **Graph Integration** (`python/helpers/spider_graph_integration.py`) - Persists discoveries
5. **Spider Agent** (`agents/spider/`) - Specialized agent for discovery tasks

## Quick Start

### Discover tools from a URL

```python
from python.helpers.tool_discovery import discover_and_register

# Discover and register tools from an API documentation site
tools = await discover_and_register(
    url="https://api.example.com/docs",
    auto_register=True,
    min_quality=ToolQuality.MEDIUM,
)

print(f"Registered {len(tools)} tools")
```

### Manual crawling

```python
from python.helpers.web_spider import WebSpider, CrawlConfig

# Configure the spider
config = CrawlConfig(
    max_depth=3,
    max_pages=100,
    extract_api_specs=True,
    parse_documentation=True,
)

# Create and run spider
spider = WebSpider(config)
result = await spider.crawl("https://modelcontextprotocol.io")
await spider.close()

# Process results
print(f"Pages crawled: {result.pages_crawled}")
print(f"APIs discovered: {result.apis_discovered}")
print(f"Tools discovered: {result.tools_discovered}")
```

### Set up continuous monitoring

```python
from python.helpers.spider_scheduler import (
    get_spider_scheduler,
    ScheduleFrequency,
)

scheduler = await get_spider_scheduler()

# Add a source to monitor
await scheduler.add_source(
    url="https://mcp-registry.example.com",
    name="MCP Tool Registry",
    frequency=ScheduleFrequency.DAILY,
    auto_register=False,  # Review before registering
    min_quality=ToolQuality.HIGH,
)

# Start the scheduler
await scheduler.start()
```

## Components

### Web Spider

The `WebSpider` class handles web crawling with these features:

- **Rate limiting**: Configurable requests per second
- **Depth control**: Limit how deep to crawl
- **Domain filtering**: Allow/block specific domains
- **Content parsing**: Extract APIs and tools from pages
- **Duplicate detection**: Skip already-crawled content

#### Configuration Options

```python
@dataclass
class CrawlConfig:
    max_depth: int = 3              # Maximum link depth
    max_pages: int = 100            # Maximum pages to crawl
    rate_limit_requests: int = 10   # Requests per second
    rate_limit_period: float = 1.0  # Rate limit window
    request_timeout: float = 30.0   # Request timeout
    user_agent: str = "Vessels-Spider/1.0"
    respect_robots_txt: bool = True
    allowed_domains: List[str] = []
    blocked_domains: List[str] = []
    follow_external_links: bool = False
    extract_api_specs: bool = True
    parse_documentation: bool = True
    store_content: bool = True
```

### Content Parsers

The spider includes specialized parsers for different content types:

#### OpenAPI Parser
Parses OpenAPI 3.x and Swagger 2.x specifications:
- Extracts API metadata (name, version, base URL)
- Creates tool definitions for each endpoint
- Identifies authentication requirements

#### GraphQL Parser
Parses GraphQL introspection results:
- Extracts queries and mutations as tools
- Maps arguments to parameters
- Identifies return types

#### MCP Registry Parser
Discovers MCP servers from:
- npm package documentation
- GitHub repositories
- MCP registry listings

### Tool Discovery Engine

The `ToolDiscoveryEngine` processes discoveries:

1. **Validation**: Check tool quality and security
2. **Quality Assessment**: Rate tools as HIGH, MEDIUM, or LOW
3. **Risk Analysis**: Identify potential security concerns
4. **Registration**: Convert to usable instruments

#### Quality Criteria

| Quality | Criteria |
|---------|----------|
| HIGH | Trusted source, high confidence, well-documented |
| MEDIUM | Standard source, reasonable confidence |
| LOW | Unknown source, minimal documentation |

#### Risk Levels

| Risk | Description |
|------|-------------|
| safe | Read-only operations |
| low | Limited writes, reversible |
| medium | Significant operations |
| high | System-affecting, needs confirmation |

### Spider Scheduler

The scheduler enables continuous monitoring:

```python
from python.helpers.spider_scheduler import (
    SpiderScheduler,
    ScheduleFrequency,
)

scheduler = await SpiderScheduler.get_instance()

# Add sources with different frequencies
await scheduler.add_source(
    url="https://api-docs.example.com",
    frequency=ScheduleFrequency.HOURLY,
)

await scheduler.add_source(
    url="https://github.com/org/repo",
    frequency=ScheduleFrequency.WEEKLY,
)

# Start automated crawling
await scheduler.start()
```

#### Scheduling Frequencies

- `HOURLY`: Check every hour
- `DAILY`: Check once per day
- `WEEKLY`: Check once per week
- `MONTHLY`: Check once per month
- `MANUAL`: Only crawl on-demand

### Graph Store Integration

Discoveries are persisted in the graph store:

```python
from python.helpers.spider_graph_integration import (
    get_spider_graph_integration,
)

integration = await get_spider_graph_integration()

# Store a crawl result
await integration.store_crawl_result(crawl_result)

# Search for tools
tools = await integration.search_discovered_tools(
    query="file system",
    min_quality=ToolQuality.MEDIUM,
)

# Get statistics
stats = await integration.get_discovery_statistics()
```

## Spider Agent

The spider agent (`agents/spider/`) is a specialized profile for discovery tasks:

### Usage

```python
# Create a spider agent
agent = await agent_factory.create_agent(profile="spider")

# The agent can use the spider tool
await agent.process_message({
    "tool_name": "spider",
    "tool_args": {
        "action": "crawl",
        "url": "https://example.com/api-docs",
        "auto_register": True,
    }
})
```

### Available Actions

| Action | Description |
|--------|-------------|
| `crawl` | Crawl a URL and discover tools |
| `discover_api` | Parse an OpenAPI/Swagger spec |
| `discover_mcp` | Find MCP servers from a URL |
| `list_discovered` | List all discovered tools |
| `register` | Register a specific tool |
| `get_mcp_configs` | Get generated MCP configs |
| `statistics` | Get discovery statistics |

## Node Types

The spider system adds these node types to the graph:

| Type | Description |
|------|-------------|
| `DISCOVERED_API` | API specifications |
| `DISCOVERED_TOOL` | Tools from registries/docs |
| `CRAWL_SOURCE` | Monitored web sources |
| `CRAWL_EVENT` | Crawl operation records |
| `REGISTERED_TOOL` | Registered instruments |

## Security

The spider system includes multiple security layers:

1. **Guardian Sanitization**: All web content is sanitized
2. **Domain Filtering**: Control which domains can be crawled
3. **Quality Validation**: Assess tool quality before registration
4. **Risk Assessment**: Identify and flag high-risk tools
5. **Rate Limiting**: Respect server resources
6. **Human Confirmation**: High-risk tools require approval

## Best Practices

1. **Start conservative**: Use `min_quality=HIGH` initially
2. **Review before registering**: Set `auto_register=False` first
3. **Use domain filtering**: Limit to trusted domains
4. **Monitor crawl events**: Check for errors and issues
5. **Test discovered tools**: Verify before production use
6. **Track provenance**: Keep source URLs for auditing

## Example Workflows

### Discover and integrate a new API

```python
# 1. Discover the API
from python.helpers.web_spider import discover_openapi

api = await discover_openapi("https://api.example.com/openapi.json")
print(f"Found API: {api.name} with {len(api.endpoints)} endpoints")

# 2. Register tools
from python.helpers.tool_discovery import get_discovery_engine

engine = await get_discovery_engine()
# Process with crawl result
result = CrawlResult(
    seed_url=api.spec_url,
    # ... populate from discovery
)
tools = await engine.process_crawl_result(result, auto_register=True)

# 3. Use the new tools
for tool in tools:
    print(f"Registered: {tool.name}")
```

### Monitor multiple registries

```python
# Set up monitoring for multiple sources
sources = [
    ("https://mcp-registry-1.com", ScheduleFrequency.DAILY),
    ("https://mcp-registry-2.com", ScheduleFrequency.WEEKLY),
    ("https://api-hub.com", ScheduleFrequency.HOURLY),
]

scheduler = await get_spider_scheduler()

for url, freq in sources:
    await scheduler.add_source(
        url=url,
        frequency=freq,
        auto_register=False,
    )

# Start monitoring
await scheduler.start()

# Check status
stats = scheduler.get_statistics()
print(f"Monitoring {stats['sources_active']} sources")
```

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     Spider Agent                         │
│                   (agents/spider/)                       │
└──────────────────────┬───────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────┐
│                   Spider Tool                            │
│             (agents/spider/tools/)                       │
└──────────────────────┬───────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          │            │            │
          ▼            ▼            ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Web Spider  │ │  Discovery  │ │  Scheduler  │
│             │ │   Engine    │ │             │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │
       │    ┌──────────┴──────────┐    │
       │    │                     │    │
       ▼    ▼                     ▼    ▼
┌─────────────────────────────────────────────┐
│           Graph Store Integration           │
│      (spider_graph_integration.py)          │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│              FalkorDB Graph                 │
│     (DISCOVERED_API, DISCOVERED_TOOL,       │
│      CRAWL_SOURCE, REGISTERED_TOOL)         │
└─────────────────────────────────────────────┘
```

## API Reference

### WebSpider

```python
class WebSpider:
    async def crawl(
        self,
        seed_url: str,
        depth: Optional[int] = None,
        max_pages: Optional[int] = None,
    ) -> CrawlResult:
        """Crawl starting from seed URL."""

    async def discover_api(
        self,
        spec_url: str,
    ) -> Optional[DiscoveredAPI]:
        """Discover API from specification URL."""

    async def discover_mcp_server(
        self,
        url: str,
    ) -> List[DiscoveredTool]:
        """Discover MCP tools from URL."""
```

### ToolDiscoveryEngine

```python
class ToolDiscoveryEngine:
    async def process_crawl_result(
        self,
        result: CrawlResult,
        auto_register: bool = False,
        min_quality: ToolQuality = ToolQuality.MEDIUM,
    ) -> List[RegisteredTool]:
        """Process crawl result and optionally register tools."""

    async def register_tool(
        self,
        tool_id: str,
    ) -> bool:
        """Register a validated tool by ID."""

    def get_registered_tools(self) -> List[RegisteredTool]:
        """Get all registered tools."""
```

### SpiderScheduler

```python
class SpiderScheduler:
    async def add_source(
        self,
        url: str,
        name: Optional[str] = None,
        frequency: ScheduleFrequency = ScheduleFrequency.DAILY,
        auto_register: bool = False,
        min_quality: ToolQuality = ToolQuality.MEDIUM,
    ) -> MonitoredSource:
        """Add a source to monitor."""

    async def start(self):
        """Start the scheduler loop."""

    async def stop(self):
        """Stop the scheduler loop."""

    async def trigger_crawl(
        self,
        source_id: str,
    ) -> Optional[CrawlEvent]:
        """Manually trigger a crawl."""
```
