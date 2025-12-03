### code_search
Search, retrieve, write, and execute code stored in FalkorDB. This is your primary interface for managing your own codebase.

**Operations:**
- `search`: Find code by natural language description
- `get`: Get full code content by path
- `list`: List all stored code of a type
- `store`: Write new code to the database
- `update`: Update existing code
- `delete`: Delete code from the database
- `execute`: Execute stored code
- `run_function`: Run a specific function from stored code
- `find_tool`: Find a tool by description
- `find_instrument`: Find an instrument by description

**Arguments:**
- `operation`: (required) One of the operations above
- `query`: Search query (for search operations)
- `description`: What you're looking for (for find_* operations)
- `path`: Virtual file path (e.g., "python/tools/my_tool.py")
- `content`: Python code content (for store/update)
- `code_type`: tool, extension, helper, api, instrument, script
- `function`: Function name (for run_function)
- `args`: List of arguments (for run_function)
- `limit`: Max search results (default 10)

**Examples:**
~~~json
// Search for code that handles browser automation
{"tool_name": "code_search", "tool_args": {"operation": "search", "query": "browser automation", "code_type": "tool"}}

// Get code content
{"tool_name": "code_search", "tool_args": {"operation": "get", "path": "python/tools/browser_agent.py"}}

// Store a new tool
{"tool_name": "code_search", "tool_args": {"operation": "store", "path": "python/tools/my_new_tool.py", "content": "from python.helpers.tool import Tool, Response\n\nclass MyNewTool(Tool):\n    async def execute(self, **kwargs) -> Response:\n        return Response(message='Hello!', break_loop=False)", "code_type": "tool", "description": "A simple greeting tool"}}

// Update existing code
{"tool_name": "code_search", "tool_args": {"operation": "update", "path": "python/tools/my_tool.py", "content": "..."}}

// Execute stored code
{"tool_name": "code_search", "tool_args": {"operation": "execute", "path": "instruments/my_script.py"}}

// Run a specific function
{"tool_name": "code_search", "tool_args": {"operation": "run_function", "path": "python/helpers/utils.py", "function": "calculate", "args": [1, 2, 3]}}

// List all tools
{"tool_name": "code_search", "tool_args": {"operation": "list", "code_type": "tool"}}
~~~

**Important:** All code is stored in FalkorDB, not the filesystem. Use this tool to:
1. Find existing code before writing new code
2. Retrieve code you need to modify or learn from
3. Store new tools, instruments, or helpers you create
4. Execute code dynamically
