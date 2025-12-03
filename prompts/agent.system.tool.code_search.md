### code_search
Search and retrieve code from the indexed codebase. Find tools, instruments, helpers, and any code you need.

**Operations:**
- `search`: Find code by description
- `get`: Get full code content by path
- `list`: List all indexed code of a type
- `find_tool`: Find a specific tool by description
- `find_instrument`: Find an instrument by description
- `find_helper`: Find a helper by description

**Arguments:**
- `operation`: (required) One of: search, get, list, find_tool, find_instrument, find_helper
- `query`: Search query (for search operations)
- `description`: Description of what you're looking for (for find_* operations)
- `path`: File path (for get operation)
- `code_type`: Filter by type: tool, extension, helper, api, instrument, model, config, test, other
- `limit`: Max results (default 10)

**Examples:**
~~~json
// Search for code that handles browser automation
{"tool_name": "code_search", "tool_args": {"operation": "search", "query": "browser automation", "code_type": "tool"}}

// Get full code of a specific file
{"tool_name": "code_search", "tool_args": {"operation": "get", "path": "python/tools/browser_agent.py"}}

// Find a tool that executes shell commands
{"tool_name": "code_search", "tool_args": {"operation": "find_tool", "description": "execute shell commands"}}

// List all indexed tools
{"tool_name": "code_search", "tool_args": {"operation": "list", "code_type": "tool"}}

// Find an instrument for file operations
{"tool_name": "code_search", "tool_args": {"operation": "find_instrument", "description": "read and write files"}}
~~~

Use this tool to discover existing code before writing new code. Find and reuse existing implementations.
