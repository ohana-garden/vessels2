"""
A0 Tool - Code Management (Agentic)

Search, retrieve, write, and execute code stored in FalkorDB.
All discovery is semantic - find code by intent, not by path.

Operations:
- search: Find code by description
- get: Get code content by path
- list: List all code of a type
- store: Write new code to the database
- update: Update existing code
- delete: Delete code
- run_tool: Find and execute a tool by intent
- run_instrument: Find and execute an instrument by intent
- create_tool: Create a new tool
- create_instrument: Create a new instrument
"""

from python.helpers.tool import Tool, Response
from python.helpers.code_loader import CodeLoader, CodeType
from python.helpers.agentic_loader import AgenticLoader


class CodeSearch(Tool):
    """Agentic code discovery and execution from FalkorDB."""

    async def execute(self, operation: str = "search", **kwargs) -> Response:
        loader = await CodeLoader.get()
        agentic = await AgenticLoader.get()

        if operation == "search":
            return await self._search(loader, **kwargs)
        elif operation == "get":
            return await self._get(loader, **kwargs)
        elif operation == "list":
            return await self._list(loader, **kwargs)
        elif operation == "store":
            return await self._store(loader, **kwargs)
        elif operation == "update":
            return await self._update(loader, **kwargs)
        elif operation == "delete":
            return await self._delete(loader, **kwargs)
        elif operation == "run_tool":
            return await self._run_tool(agentic, **kwargs)
        elif operation == "run_instrument":
            return await self._run_instrument(agentic, **kwargs)
        elif operation == "create_tool":
            return await self._create_tool(agentic, **kwargs)
        elif operation == "create_instrument":
            return await self._create_instrument(agentic, **kwargs)
        elif operation == "execute":
            return await self._execute(loader, **kwargs)
        else:
            ops = "search, get, list, store, update, delete, run_tool, run_instrument, create_tool, create_instrument, execute"
            return Response(message=f"Unknown operation: {operation}. Use: {ops}", break_loop=False)

    async def _search(self, loader: CodeLoader, query: str = "", code_type: str = "", limit: int = 10, **kwargs) -> Response:
        """Search code by description."""
        if not query:
            return Response(message="Query is required for search", break_loop=False)

        ct = self._parse_code_type(code_type)
        results = await loader.search(query, code_type=ct, limit=limit)

        if not results:
            return Response(message=f"No code found matching: {query}", break_loop=False)

        output = [f"Found {len(results)} matching:\n"]
        for r in results:
            output.append(f"- {r['path']} (score: {r['score']:.2f})")

        return Response(message="\n".join(output), break_loop=False)

    async def _get(self, loader: CodeLoader, path: str = "", **kwargs) -> Response:
        """Get full code content."""
        if not path:
            return Response(message="Path is required", break_loop=False)

        stored = await loader.get_code(path)
        if not stored:
            return Response(message=f"Code not found: {path}", break_loop=False)

        output = [
            f"Path: {stored.path}",
            f"Type: {stored.code_type.value}",
            f"Hash: {stored.hash}",
        ]

        if stored.metadata.get("description"):
            output.append(f"Description: {stored.metadata['description']}")

        output.append(f"\n--- Code ---\n{stored.content}")

        return Response(message="\n".join(output), break_loop=False)

    async def _list(self, loader: CodeLoader, code_type: str = "", **kwargs) -> Response:
        """List all stored code."""
        ct = self._parse_code_type(code_type)
        paths = await loader.list_code(code_type=ct)

        if not paths:
            type_msg = f" of type '{code_type}'" if code_type else ""
            return Response(message=f"No stored code{type_msg}", break_loop=False)

        output = [f"Stored code ({len(paths)}):\n"]
        for path in paths:
            output.append(f"- {path}")

        return Response(message="\n".join(output), break_loop=False)

    async def _store(self, loader: CodeLoader, path: str = "", content: str = "", code_type: str = "script", description: str = "", **kwargs) -> Response:
        """Store new code in the database."""
        if not path:
            return Response(message="Path is required", break_loop=False)
        if not content:
            return Response(message="Content is required", break_loop=False)

        ct = self._parse_code_type(code_type) or CodeType.SCRIPT

        metadata = {}
        if description:
            metadata["description"] = description

        stored = await loader.store(path, content, ct, metadata)

        return Response(
            message=f"Stored: {stored.path} ({stored.code_type.value})",
            break_loop=False,
        )

    async def _update(self, loader: CodeLoader, path: str = "", content: str = "", **kwargs) -> Response:
        """Update existing code."""
        if not path:
            return Response(message="Path is required", break_loop=False)
        if not content:
            return Response(message="Content is required", break_loop=False)

        existing = await loader.get_code(path)
        if not existing:
            return Response(message=f"Not found: {path}. Use 'store' for new code.", break_loop=False)

        stored = await loader.store(path, content, existing.code_type, existing.metadata)

        return Response(message=f"Updated: {stored.path}", break_loop=False)

    async def _delete(self, loader: CodeLoader, path: str = "", **kwargs) -> Response:
        """Delete stored code."""
        if not path:
            return Response(message="Path is required", break_loop=False)

        existing = await loader.get_code(path)
        if not existing:
            return Response(message=f"Not found: {path}", break_loop=False)

        await loader.delete(path)
        return Response(message=f"Deleted: {path}", break_loop=False)

    async def _run_tool(self, agentic: AgenticLoader, intent: str = "", **kwargs) -> Response:
        """Find and execute a tool by intent."""
        if not intent:
            return Response(message="Intent is required (describe what the tool should do)", break_loop=False)

        try:
            # Remove intent from kwargs so it's not passed to the tool
            tool_kwargs = {k: v for k, v in kwargs.items() if k != "intent"}

            result = await agentic.execute_tool(intent, self.agent, **tool_kwargs)

            if hasattr(result, 'message'):
                return Response(message=f"Tool executed:\n{result.message}", break_loop=result.break_loop)
            return Response(message=f"Tool executed:\n{result}", break_loop=False)

        except ValueError as e:
            return Response(message=str(e), break_loop=False)
        except Exception as e:
            return Response(message=f"Tool execution failed: {str(e)}", break_loop=False)

    async def _run_instrument(self, agentic: AgenticLoader, intent: str = "", **kwargs) -> Response:
        """Find and execute an instrument by intent."""
        if not intent:
            return Response(message="Intent is required (describe what the instrument should do)", break_loop=False)

        try:
            # Remove intent from kwargs
            inst_kwargs = {k: v for k, v in kwargs.items() if k != "intent"}

            result = await agentic.run_instrument(intent, **inst_kwargs)

            return Response(message=f"Instrument executed:\n{result}", break_loop=False)

        except ValueError as e:
            return Response(message=str(e), break_loop=False)
        except Exception as e:
            return Response(message=f"Instrument execution failed: {str(e)}", break_loop=False)

    async def _create_tool(self, agentic: AgenticLoader, name: str = "", description: str = "", code: str = "", **kwargs) -> Response:
        """Create a new tool."""
        if not name:
            return Response(message="Name is required", break_loop=False)
        if not code:
            return Response(message="Code is required", break_loop=False)

        path = await agentic.create_tool(name, description or f"Tool: {name}", code)

        return Response(message=f"Tool created: {path}", break_loop=False)

    async def _create_instrument(self, agentic: AgenticLoader, name: str = "", description: str = "", code: str = "", **kwargs) -> Response:
        """Create a new instrument."""
        if not name:
            return Response(message="Name is required", break_loop=False)
        if not code:
            return Response(message="Code is required", break_loop=False)

        path = await agentic.create_instrument(name, description or f"Instrument: {name}", code)

        return Response(message=f"Instrument created: {path}", break_loop=False)

    async def _execute(self, loader: CodeLoader, path: str = "", **kwargs) -> Response:
        """Execute stored code by path."""
        if not path:
            return Response(message="Path is required", break_loop=False)

        try:
            result = await loader.execute(path)
            return Response(message=f"Executed:\n{result}", break_loop=False)
        except FileNotFoundError:
            return Response(message=f"Not found: {path}", break_loop=False)
        except Exception as e:
            return Response(message=f"Execution failed: {str(e)}", break_loop=False)

    def _parse_code_type(self, code_type: str) -> CodeType | None:
        """Parse code type string to enum."""
        if not code_type:
            return None
        try:
            return CodeType(code_type.lower())
        except ValueError:
            return None
