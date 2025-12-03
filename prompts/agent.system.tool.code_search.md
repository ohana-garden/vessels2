### code_search
Agentic code discovery and execution. Find code by intent, not by path. All code lives in FalkorDB.

**Operations:**
- `run_tool`: Find and execute a tool by describing what it should do
- `run_instrument`: Find and execute an instrument by intent
- `create_tool`: Create a new tool
- `create_instrument`: Create a new instrument
- `search`: Find code by description
- `get`: Get code content by path
- `list`: List all code of a type
- `store`: Write code to database
- `update`: Update existing code
- `delete`: Delete code
- `execute`: Execute code by path

**Arguments:**
- `operation`: (required) One of the operations above
- `intent`: What the code should do (for run_tool, run_instrument)
- `name`: Name for new tool/instrument (for create_*)
- `description`: Description of what code does
- `code`: Python code content
- `query`: Search query
- `path`: Code path (when known)
- `code_type`: tool, extension, helper, api, instrument, script

**Agentic Examples:**
~~~json
// Find and run a tool by intent (no path needed!)
{"tool_name": "code_search", "tool_args": {"operation": "run_tool", "intent": "execute shell commands", "command": "ls -la"}}

// Find and run an instrument by intent
{"tool_name": "code_search", "tool_args": {"operation": "run_instrument", "intent": "parse JSON data", "data": "{\"key\": \"value\"}"}}

// Create a new tool
{"tool_name": "code_search", "tool_args": {"operation": "create_tool", "name": "greeter", "description": "Says hello", "code": "from python.helpers.tool import Tool, Response\n\nclass Greeter(Tool):\n    async def execute(self, name='World', **kwargs) -> Response:\n        return Response(message=f'Hello, {name}!', break_loop=False)"}}

// Create a new instrument
{"tool_name": "code_search", "tool_args": {"operation": "create_instrument", "name": "data_processor", "description": "Processes data files", "code": "def run(data):\n    return data.upper()"}}
~~~

**Traditional Examples:**
~~~json
// Search for code
{"tool_name": "code_search", "tool_args": {"operation": "search", "query": "browser automation", "code_type": "tool"}}

// Get code by path
{"tool_name": "code_search", "tool_args": {"operation": "get", "path": "python/tools/browser_agent.py"}}

// List all instruments
{"tool_name": "code_search", "tool_args": {"operation": "list", "code_type": "instrument"}}
~~~

**Key Principle:** Discover code by *intent*, not by file path. Describe what you need and the system finds it.
