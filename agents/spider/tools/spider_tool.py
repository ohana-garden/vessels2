"""
Spider Tool - Web crawling and tool discovery for agents

This tool allows agents to crawl web sources and discover new tools/APIs
that can be registered for use by the agent ecosystem.
"""

import json
from typing import Any, Dict, List, Optional
from python.helpers.tool import Tool, Response
from python.helpers.web_spider import (
    WebSpider,
    CrawlConfig,
    CrawlResult,
    SourceType,
)
from python.helpers.tool_discovery import (
    ToolDiscoveryEngine,
    ToolQuality,
    RegisteredTool,
)
from python.helpers.guardians import guard_web


class SpiderTool(Tool):
    """
    Web spidering tool for discovering APIs and tools.

    This tool crawls web sources to discover new capabilities
    that can be registered as instruments or MCP servers.
    """

    async def execute(
        self,
        url: str = "",
        action: str = "crawl",
        depth: int = 2,
        max_pages: int = 50,
        auto_register: bool = False,
        min_quality: str = "medium",
        **kwargs
    ) -> Response:
        """
        Execute spider operations.

        Args:
            url: URL to crawl or discover from
            action: One of: crawl, discover_api, discover_mcp, list_discovered, register
            depth: Maximum crawl depth (default: 2)
            max_pages: Maximum pages to crawl (default: 50)
            auto_register: Whether to auto-register discovered tools
            min_quality: Minimum quality for registration (low, medium, high)

        Returns:
            Response with discovery results
        """
        try:
            if action == "crawl":
                result = await self._crawl(url, depth, max_pages, auto_register, min_quality)
            elif action == "discover_api":
                result = await self._discover_api(url)
            elif action == "discover_mcp":
                result = await self._discover_mcp(url)
            elif action == "list_discovered":
                result = await self._list_discovered()
            elif action == "register":
                result = await self._register_tool(url)  # url is tool_id in this case
            elif action == "get_mcp_configs":
                result = await self._get_mcp_configs()
            elif action == "statistics":
                result = await self._get_statistics()
            else:
                result = f"Unknown action: {action}. Available actions: crawl, discover_api, discover_mcp, list_discovered, register, get_mcp_configs, statistics"

            return Response(message=str(result), break_loop=False)

        except Exception as e:
            return Response(
                message=f"Spider operation failed: {str(e)}",
                break_loop=False
            )

    async def _crawl(
        self,
        url: str,
        depth: int,
        max_pages: int,
        auto_register: bool,
        min_quality: str,
    ) -> str:
        """Crawl a URL and discover tools."""
        if not url:
            return "Error: URL is required for crawl action"

        config = CrawlConfig(
            max_depth=depth,
            max_pages=max_pages,
            extract_api_specs=True,
            parse_documentation=True,
            store_content=False,  # Don't store full content to save memory
        )

        spider = WebSpider(config)
        crawl_result = await spider.crawl(url)
        await spider.close()

        # Process with discovery engine
        engine = await ToolDiscoveryEngine.get_instance()
        quality_map = {
            'low': ToolQuality.LOW,
            'medium': ToolQuality.MEDIUM,
            'high': ToolQuality.HIGH,
        }
        quality = quality_map.get(min_quality.lower(), ToolQuality.MEDIUM)

        registered = await engine.process_crawl_result(
            crawl_result,
            auto_register=auto_register,
            min_quality=quality,
        )

        # Format result
        output = [
            f"## Crawl Results for {url}",
            f"",
            f"**Pages Crawled:** {crawl_result.pages_crawled}",
            f"**APIs Discovered:** {crawl_result.apis_discovered}",
            f"**Tools Discovered:** {crawl_result.tools_discovered}",
            f"**Duration:** {crawl_result.duration_seconds:.2f}s",
            f"**Status:** {crawl_result.status.value}",
        ]

        if crawl_result.discovered_apis:
            output.append("\n### Discovered APIs:")
            for api in crawl_result.discovered_apis[:10]:
                output.append(f"- **{api.name}** ({api.spec_type.value})")
                output.append(f"  - Base URL: {api.base_url}")
                output.append(f"  - Endpoints: {len(api.endpoints)}")
                output.append(f"  - Auth: {', '.join(api.auth_methods) or 'None'}")

        if crawl_result.discovered_tools:
            output.append("\n### Discovered Tools:")
            for tool in crawl_result.discovered_tools[:20]:
                output.append(f"- **{tool.name}** ({tool.source_type})")
                output.append(f"  - {tool.description[:100]}...")
                output.append(f"  - Confidence: {tool.confidence:.0%}")

        if registered:
            output.append(f"\n### Registered Tools ({len(registered)}):")
            for reg in registered:
                output.append(f"- {reg.name} ({reg.status.value})")

        if crawl_result.errors:
            output.append(f"\n### Errors ({len(crawl_result.errors)}):")
            for error in crawl_result.errors[:5]:
                output.append(f"- {error[:100]}")

        return "\n".join(output)

    async def _discover_api(self, url: str) -> str:
        """Discover API from a specification URL."""
        if not url:
            return "Error: URL is required"

        from python.helpers.web_spider import discover_openapi

        api = await discover_openapi(url)

        if not api:
            return f"No API specification found at {url}"

        output = [
            f"## API Discovered: {api.name}",
            f"",
            f"**Type:** {api.spec_type.value}",
            f"**Version:** {api.version}",
            f"**Base URL:** {api.base_url}",
            f"**Description:** {api.description[:200]}",
            f"**Endpoints:** {len(api.endpoints)}",
            f"**Auth Methods:** {', '.join(api.auth_methods) or 'None'}",
            "",
            "### Sample Endpoints:",
        ]

        for endpoint in api.endpoints[:10]:
            output.append(
                f"- `{endpoint['method']} {endpoint['path']}`: {endpoint.get('summary', 'No description')[:60]}"
            )

        return "\n".join(output)

    async def _discover_mcp(self, url: str) -> str:
        """Discover MCP servers from a URL."""
        if not url:
            return "Error: URL is required"

        from python.helpers.web_spider import discover_mcp_tools

        tools = await discover_mcp_tools(url)

        if not tools:
            return f"No MCP tools found at {url}"

        output = [
            f"## MCP Tools Discovered from {url}",
            f"",
            f"**Total Tools:** {len(tools)}",
            "",
        ]

        for tool in tools:
            output.append(f"### {tool.name}")
            output.append(f"- **Description:** {tool.description[:150]}")
            output.append(f"- **Source URL:** {tool.source_url}")
            output.append(f"- **Confidence:** {tool.confidence:.0%}")

            if tool.installation:
                output.append(f"- **Installation:**")
                for key, value in tool.installation.items():
                    output.append(f"  - {key}: {value}")

            output.append("")

        return "\n".join(output)

    async def _list_discovered(self) -> str:
        """List all discovered tools."""
        engine = await ToolDiscoveryEngine.get_instance()
        tools = engine.get_registered_tools()

        if not tools:
            return "No tools discovered yet. Use `spider crawl <url>` to discover tools."

        output = [
            "## Discovered Tools",
            f"",
            f"**Total:** {len(tools)}",
            "",
        ]

        # Group by status
        by_status: Dict[str, List[RegisteredTool]] = {}
        for tool in tools:
            status = tool.status.value
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(tool)

        for status, status_tools in by_status.items():
            output.append(f"### {status.title()} ({len(status_tools)})")
            for tool in status_tools[:20]:
                quality = tool.validation.quality.value
                output.append(f"- **{tool.name}** [{quality}] ({tool.source})")
                output.append(f"  - ID: `{tool.tool_id}`")
                output.append(f"  - Risk: {tool.validation.risk_level}")
            output.append("")

        return "\n".join(output)

    async def _register_tool(self, tool_id: str) -> str:
        """Register a discovered tool by ID."""
        if not tool_id:
            return "Error: tool_id is required"

        engine = await ToolDiscoveryEngine.get_instance()
        success = await engine.register_tool(tool_id)

        if success:
            tool = engine.get_tool(tool_id)
            return f"Successfully registered tool: {tool.name}"
        else:
            return f"Failed to register tool: {tool_id}. Check if it exists and is validated."

    async def _get_mcp_configs(self) -> str:
        """Get generated MCP configurations."""
        engine = await ToolDiscoveryEngine.get_instance()
        configs = engine.get_mcp_configs()

        if not configs:
            return "No MCP configurations generated yet."

        output = [
            "## Generated MCP Configurations",
            "",
        ]

        for config in configs:
            output.append(f"### {config.name}")
            output.append(f"- **Description:** {config.description[:100]}")
            output.append(f"- **Type:** {config.type}")
            output.append(f"- **Source:** {config.source_url}")
            output.append(f"- **Tools:** {len(config.tools)}")
            output.append(f"- **Config:**")
            output.append(f"```json")
            output.append(json.dumps(config.to_mcp_config(), indent=2))
            output.append(f"```")
            output.append("")

        return "\n".join(output)

    async def _get_statistics(self) -> str:
        """Get discovery engine statistics."""
        engine = await ToolDiscoveryEngine.get_instance()
        stats = engine.get_statistics()

        output = [
            "## Discovery Engine Statistics",
            "",
            f"**Total Tools Discovered:** {stats['total_tools']}",
            f"**MCP Configs Generated:** {stats['mcp_configs']}",
            "",
            "### By Status:",
        ]

        for status, count in stats['status_breakdown'].items():
            output.append(f"- {status}: {count}")

        output.append("")
        output.append("### By Source:")

        for source, count in stats['tools_by_source'].items():
            output.append(f"- {source}: {count}")

        return "\n".join(output)


# Tool prompt for the system
SPIDER_TOOL_PROMPT = '''
## Tool: spider

Web spidering tool for discovering APIs, MCP servers, and tools.

### Actions:

1. **crawl** - Crawl a URL to discover tools
   - `url`: Starting URL (required)
   - `depth`: Max depth (default: 2)
   - `max_pages`: Max pages (default: 50)
   - `auto_register`: Auto-register tools (default: false)
   - `min_quality`: Minimum quality - low/medium/high (default: medium)

2. **discover_api** - Discover API from OpenAPI/Swagger URL
   - `url`: URL to API specification

3. **discover_mcp** - Discover MCP tools from URL
   - `url`: URL to MCP documentation/registry

4. **list_discovered** - List all discovered tools

5. **register** - Register a discovered tool
   - `url`: Tool ID to register

6. **get_mcp_configs** - Get generated MCP configurations

7. **statistics** - Get discovery statistics

### Examples:

```json
{"tool_name": "spider", "tool_args": {"action": "crawl", "url": "https://api.example.com/docs"}}
{"tool_name": "spider", "tool_args": {"action": "discover_api", "url": "https://api.example.com/openapi.json"}}
{"tool_name": "spider", "tool_args": {"action": "list_discovered"}}
```
'''
