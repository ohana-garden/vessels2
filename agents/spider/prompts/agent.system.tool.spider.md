# Spider Tool

The spider tool enables autonomous discovery of APIs, MCP servers, and tools from web sources.

## Usage

```json
{
    "thoughts": ["I need to discover tools from this API documentation"],
    "tool_name": "spider",
    "tool_args": {
        "action": "<action>",
        "url": "<url>",
        ...additional args...
    }
}
```

## Actions

### crawl
Crawl a website to discover all available tools and APIs.

**Arguments:**
- `url` (required): Starting URL to crawl
- `depth`: Maximum link depth to follow (default: 2)
- `max_pages`: Maximum pages to crawl (default: 50)
- `auto_register`: Whether to auto-register discovered tools (default: false)
- `min_quality`: Minimum quality threshold - "low", "medium", "high" (default: "medium")

**Example:**
```json
{
    "thoughts": ["Crawling the MCP ecosystem documentation to discover available servers"],
    "tool_name": "spider",
    "tool_args": {
        "action": "crawl",
        "url": "https://modelcontextprotocol.io/docs",
        "depth": 3,
        "auto_register": true,
        "min_quality": "medium"
    }
}
```

### discover_api
Directly discover an API from an OpenAPI/Swagger specification URL.

**Arguments:**
- `url` (required): URL to the API specification (JSON or YAML)

**Example:**
```json
{
    "thoughts": ["Fetching and parsing the OpenAPI specification for this API"],
    "tool_name": "spider",
    "tool_args": {
        "action": "discover_api",
        "url": "https://api.example.com/openapi.json"
    }
}
```

### discover_mcp
Discover MCP server tools from documentation or registry.

**Arguments:**
- `url` (required): URL to MCP documentation, npm package, or GitHub repo

**Example:**
```json
{
    "thoughts": ["Looking for MCP server tools in this npm package"],
    "tool_name": "spider",
    "tool_args": {
        "action": "discover_mcp",
        "url": "https://www.npmjs.com/package/@modelcontextprotocol/server-filesystem"
    }
}
```

### list_discovered
List all tools that have been discovered.

**Arguments:** None

**Example:**
```json
{
    "thoughts": ["Checking what tools have been discovered so far"],
    "tool_name": "spider",
    "tool_args": {
        "action": "list_discovered"
    }
}
```

### register
Register a specific discovered tool by its ID.

**Arguments:**
- `url` (required): The tool ID to register (shown in list_discovered output)

**Example:**
```json
{
    "thoughts": ["Registering this validated tool for use"],
    "tool_name": "spider",
    "tool_args": {
        "action": "register",
        "url": "abc123def456"
    }
}
```

### get_mcp_configs
Get all generated MCP server configurations.

**Arguments:** None

**Example:**
```json
{
    "thoughts": ["Getting the MCP configurations that were generated from discoveries"],
    "tool_name": "spider",
    "tool_args": {
        "action": "get_mcp_configs"
    }
}
```

### statistics
Get statistics about the discovery engine.

**Arguments:** None

**Example:**
```json
{
    "thoughts": ["Checking discovery statistics"],
    "tool_name": "spider",
    "tool_args": {
        "action": "statistics"
    }
}
```

## Workflow

1. **Discover**: Use `crawl` or `discover_*` to find tools
2. **Review**: Use `list_discovered` to see what was found
3. **Assess**: Check quality ratings and risk levels
4. **Register**: Use `register` to activate high-quality tools
5. **Configure**: Use `get_mcp_configs` to see MCP configurations

## Quality Levels

- **high**: Well-documented, from trusted sources, high confidence extraction
- **medium**: Reasonably documented, standard sources, good confidence
- **low**: Minimal documentation, unknown sources, lower confidence

## Risk Levels

- **safe**: Read-only operations, no side effects
- **low**: Limited write operations, reversible
- **medium**: Significant operations, needs verification
- **high**: System-affecting operations, requires confirmation

## Best Practices

1. Start with `min_quality: high` to get only the best tools
2. Review discovered tools before enabling auto_register
3. Check risk levels before registering
4. Use shallow depth for API specs (1-2), deeper for documentation (3-4)
5. Prefer specific URLs over broad crawls when possible
