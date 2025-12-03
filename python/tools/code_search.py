"""
A0 Tool - Code Search

Search and retrieve code from the indexed codebase.
Enables A0 to find tools, instruments, helpers, and any code it needs.

Operations:
- search: Find code by description
- get: Get full code content by path
- list: List all indexed code of a type
- find_tool: Find a specific tool
- find_instrument: Find an instrument
"""

from python.helpers.tool import Tool, Response
from python.helpers.code_store import CodeStore, CodeType


class CodeSearch(Tool):
    """Search and retrieve code from the codebase."""

    async def execute(self, operation: str = "search", **kwargs) -> Response:
        store = await CodeStore.get()

        if operation == "search":
            return await self._search(store, **kwargs)
        elif operation == "get":
            return await self._get(store, **kwargs)
        elif operation == "list":
            return await self._list(store, **kwargs)
        elif operation == "find_tool":
            return await self._find_tool(store, **kwargs)
        elif operation == "find_instrument":
            return await self._find_instrument(store, **kwargs)
        elif operation == "find_helper":
            return await self._find_helper(store, **kwargs)
        else:
            return Response(
                message=f"Unknown operation: {operation}. Use: search, get, list, find_tool, find_instrument, find_helper",
                break_loop=False,
            )

    async def _search(self, store: CodeStore, query: str = "", code_type: str = "", limit: int = 10, **kwargs) -> Response:
        """Search code by description."""
        if not query:
            return Response(message="Query is required for search", break_loop=False)

        # Parse code type if provided
        ct = None
        if code_type:
            try:
                ct = CodeType(code_type.lower())
            except ValueError:
                pass

        results = await store.search(query, code_type=ct, limit=limit)

        if not results:
            return Response(message=f"No code found matching: {query}", break_loop=False)

        # Format results
        output = [f"Found {len(results)} matching code files:\n"]
        for r in results:
            output.append(f"- {r['path']} (score: {r['score']:.2f})")
            if r.get('summary'):
                # First line of summary
                first_line = r['summary'].split('\n')[0][:100]
                output.append(f"  {first_line}")

        return Response(message="\n".join(output), break_loop=False)

    async def _get(self, store: CodeStore, path: str = "", **kwargs) -> Response:
        """Get full code content."""
        if not path:
            return Response(message="Path is required", break_loop=False)

        data = await store.get_code(path)
        if not data:
            return Response(message=f"Code not found: {path}", break_loop=False)

        content = data.get("content", "")
        metadata = data.get("metadata", {})

        output = [f"File: {path}"]
        if metadata.get("code_type"):
            output.append(f"Type: {metadata['code_type']}")
        if metadata.get("module_docstring"):
            output.append(f"Description: {metadata['module_docstring'][:200]}")

        # List entities
        entities = metadata.get("entities", [])
        if entities:
            classes = [e for e in entities if e.get("type") == "class"]
            functions = [e for e in entities if e.get("type") == "function"]

            if classes:
                output.append(f"\nClasses: {', '.join(c['name'] for c in classes)}")
            if functions:
                output.append(f"Functions: {', '.join(f['name'] for f in functions[:10])}")

        output.append(f"\n--- Code ({len(content)} chars) ---\n")
        output.append(content)

        return Response(message="\n".join(output), break_loop=False)

    async def _list(self, store: CodeStore, code_type: str = "", **kwargs) -> Response:
        """List indexed code files."""
        ct = None
        if code_type:
            try:
                ct = CodeType(code_type.lower())
            except ValueError:
                return Response(
                    message=f"Invalid code_type. Use: tool, extension, helper, api, instrument, model, config, test, other",
                    break_loop=False,
                )

        paths = await store.list_code(code_type=ct)

        if not paths:
            type_msg = f" of type '{code_type}'" if code_type else ""
            return Response(message=f"No indexed code files{type_msg}", break_loop=False)

        output = [f"Indexed code files ({len(paths)}):\n"]
        for path in sorted(paths):
            output.append(f"- {path}")

        return Response(message="\n".join(output), break_loop=False)

    async def _find_tool(self, store: CodeStore, description: str = "", **kwargs) -> Response:
        """Find a tool by description."""
        if not description:
            return Response(message="Description is required", break_loop=False)

        data = await store.find_tool(description)
        if not data:
            return Response(message=f"No tool found matching: {description}", break_loop=False)

        return await self._format_code_result(data)

    async def _find_instrument(self, store: CodeStore, description: str = "", **kwargs) -> Response:
        """Find an instrument by description."""
        if not description:
            return Response(message="Description is required", break_loop=False)

        # Search instruments specifically
        results = await store.search(description, code_type=CodeType.INSTRUMENT, limit=1)
        if results:
            data = await store.get_code(results[0]["path"])
            if data:
                return await self._format_code_result(data)

        return Response(message=f"No instrument found matching: {description}", break_loop=False)

    async def _find_helper(self, store: CodeStore, description: str = "", **kwargs) -> Response:
        """Find a helper by description."""
        if not description:
            return Response(message="Description is required", break_loop=False)

        data = await store.find_helper(description)
        if not data:
            return Response(message=f"No helper found matching: {description}", break_loop=False)

        return await self._format_code_result(data)

    async def _format_code_result(self, data: dict) -> Response:
        """Format code result for output."""
        path = data.get("path", "unknown")
        content = data.get("content", "")
        metadata = data.get("metadata", {})

        output = [f"Found: {path}"]
        if metadata.get("code_type"):
            output.append(f"Type: {metadata['code_type']}")
        if metadata.get("module_docstring"):
            output.append(f"Description: {metadata['module_docstring'][:300]}")

        output.append(f"\n--- Code ---\n{content}")

        return Response(message="\n".join(output), break_loop=False)
