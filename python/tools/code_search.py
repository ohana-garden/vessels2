"""
A0 Tool - Code Management

Search, retrieve, write, and execute code stored in FalkorDB.
Enables A0 to be fully self-aware and self-modifying.

Operations:
- search: Find code by description
- get: Get code content by path
- list: List all code of a type
- store: Write new code to the database
- update: Update existing code
- delete: Delete code
- execute: Execute stored code
- run_function: Run a specific function from stored code
"""

from python.helpers.tool import Tool, Response
from python.helpers.code_loader import CodeLoader, CodeType, StoredCode


class CodeSearch(Tool):
    """Search, retrieve, write, and execute code from FalkorDB."""

    async def execute(self, operation: str = "search", **kwargs) -> Response:
        loader = await CodeLoader.get()

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
        elif operation == "execute":
            return await self._execute(loader, **kwargs)
        elif operation == "run_function":
            return await self._run_function(loader, **kwargs)
        elif operation == "find_tool":
            return await self._find_tool(loader, **kwargs)
        elif operation == "find_instrument":
            return await self._find_instrument(loader, **kwargs)
        else:
            return Response(
                message=f"Unknown operation: {operation}. Use: search, get, list, store, update, delete, execute, run_function, find_tool, find_instrument",
                break_loop=False,
            )

    async def _search(self, loader: CodeLoader, query: str = "", code_type: str = "", limit: int = 10, **kwargs) -> Response:
        """Search code by description."""
        if not query:
            return Response(message="Query is required for search", break_loop=False)

        ct = self._parse_code_type(code_type)
        results = await loader.search(query, code_type=ct, limit=limit)

        if not results:
            return Response(message=f"No code found matching: {query}", break_loop=False)

        output = [f"Found {len(results)} matching code files:\n"]
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
            f"Updated: {stored.updated_at}",
        ]

        if stored.metadata:
            output.append(f"Metadata: {stored.metadata}")

        output.append(f"\n--- Code ({len(stored.content)} chars) ---\n")
        output.append(stored.content)

        return Response(message="\n".join(output), break_loop=False)

    async def _list(self, loader: CodeLoader, code_type: str = "", **kwargs) -> Response:
        """List all stored code."""
        ct = self._parse_code_type(code_type)
        paths = await loader.list_code(code_type=ct)

        if not paths:
            type_msg = f" of type '{code_type}'" if code_type else ""
            return Response(message=f"No stored code{type_msg}", break_loop=False)

        output = [f"Stored code ({len(paths)} files):\n"]
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
            message=f"Code stored successfully:\n- Path: {stored.path}\n- Type: {stored.code_type.value}\n- Hash: {stored.hash}",
            break_loop=False,
        )

    async def _update(self, loader: CodeLoader, path: str = "", content: str = "", **kwargs) -> Response:
        """Update existing code."""
        if not path:
            return Response(message="Path is required", break_loop=False)
        if not content:
            return Response(message="Content is required", break_loop=False)

        # Get existing to preserve type and metadata
        existing = await loader.get_code(path)
        if not existing:
            return Response(message=f"Code not found: {path}. Use 'store' to create new code.", break_loop=False)

        stored = await loader.store(path, content, existing.code_type, existing.metadata)

        return Response(
            message=f"Code updated successfully:\n- Path: {stored.path}\n- New hash: {stored.hash}",
            break_loop=False,
        )

    async def _delete(self, loader: CodeLoader, path: str = "", **kwargs) -> Response:
        """Delete stored code."""
        if not path:
            return Response(message="Path is required", break_loop=False)

        existing = await loader.get_code(path)
        if not existing:
            return Response(message=f"Code not found: {path}", break_loop=False)

        await loader.delete(path)
        return Response(message=f"Code deleted: {path}", break_loop=False)

    async def _execute(self, loader: CodeLoader, path: str = "", **kwargs) -> Response:
        """Execute stored code."""
        if not path:
            return Response(message="Path is required", break_loop=False)

        try:
            result = await loader.execute(path)
            return Response(
                message=f"Execution complete.\nResult: {result}",
                break_loop=False,
            )
        except FileNotFoundError:
            return Response(message=f"Code not found: {path}", break_loop=False)
        except Exception as e:
            return Response(message=f"Execution failed: {str(e)}", break_loop=False)

    async def _run_function(self, loader: CodeLoader, path: str = "", function: str = "", args: list = None, **kwargs) -> Response:
        """Run a specific function from stored code."""
        if not path:
            return Response(message="Path is required", break_loop=False)
        if not function:
            return Response(message="Function name is required", break_loop=False)

        try:
            result = await loader.execute_function(path, function, *(args or []))
            return Response(
                message=f"Function '{function}' executed.\nResult: {result}",
                break_loop=False,
            )
        except FileNotFoundError:
            return Response(message=f"Code not found: {path}", break_loop=False)
        except AttributeError:
            return Response(message=f"Function '{function}' not found in {path}", break_loop=False)
        except Exception as e:
            return Response(message=f"Execution failed: {str(e)}", break_loop=False)

    async def _find_tool(self, loader: CodeLoader, description: str = "", **kwargs) -> Response:
        """Find a tool by description."""
        if not description:
            return Response(message="Description is required", break_loop=False)

        results = await loader.search(description, code_type=CodeType.TOOL, limit=1)
        if not results:
            return Response(message=f"No tool found matching: {description}", break_loop=False)

        path = results[0]["path"]
        stored = await loader.get_code(path)
        if stored:
            return Response(
                message=f"Found tool: {path}\n\n{stored.content}",
                break_loop=False,
            )
        return Response(message=f"Tool not found: {path}", break_loop=False)

    async def _find_instrument(self, loader: CodeLoader, description: str = "", **kwargs) -> Response:
        """Find an instrument by description."""
        if not description:
            return Response(message="Description is required", break_loop=False)

        results = await loader.search(description, code_type=CodeType.INSTRUMENT, limit=1)
        if not results:
            return Response(message=f"No instrument found matching: {description}", break_loop=False)

        path = results[0]["path"]
        stored = await loader.get_code(path)
        if stored:
            return Response(
                message=f"Found instrument: {path}\n\n{stored.content}",
                break_loop=False,
            )
        return Response(message=f"Instrument not found: {path}", break_loop=False)

    def _parse_code_type(self, code_type: str) -> CodeType | None:
        """Parse code type string to enum."""
        if not code_type:
            return None
        try:
            return CodeType(code_type.lower())
        except ValueError:
            return None
