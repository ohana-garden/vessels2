"""
A0 API - Code Management

API endpoints for managing code stored in FalkorDB.
All code lives in the database - no filesystem dependency.
"""

from python.helpers.api import ApiHandler, Request
from python.helpers.code_loader import CodeLoader, CodeType


class CodeIndex(ApiHandler):
    """Manage code stored in FalkorDB."""

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST", "GET"]

    async def process(self, input: dict, request: Request) -> dict:
        operation = input.get("operation", "status")

        if operation == "store":
            return await self._store(input)
        elif operation == "get":
            return await self._get(input.get("path", ""))
        elif operation == "delete":
            return await self._delete(input.get("path", ""))
        elif operation == "search":
            return await self._search(input.get("query", ""), input.get("code_type", ""))
        elif operation == "list":
            return await self._list(input.get("code_type", ""))
        elif operation == "status":
            return await self._status()
        else:
            return {"error": f"Unknown operation: {operation}. Use: store, get, delete, search, list, status"}

    async def _store(self, input: dict) -> dict:
        """Store code in FalkorDB."""
        path = input.get("path", "")
        content = input.get("content", "")
        code_type = input.get("code_type", "script")

        if not path:
            return {"error": "path is required"}
        if not content:
            return {"error": "content is required"}

        try:
            ct = CodeType(code_type.lower())
        except ValueError:
            ct = CodeType.SCRIPT

        loader = await CodeLoader.get()
        stored = await loader.store(path, content, ct, input.get("metadata"))
        return {
            "status": "ok",
            "path": stored.path,
            "hash": stored.hash,
            "code_type": stored.code_type.value,
        }

    async def _get(self, path: str) -> dict:
        """Get code from FalkorDB."""
        if not path:
            return {"error": "path is required"}

        loader = await CodeLoader.get()
        stored = await loader.get_code(path)

        if not stored:
            return {"error": f"Code not found: {path}"}

        return {
            "status": "ok",
            "path": stored.path,
            "content": stored.content,
            "code_type": stored.code_type.value,
            "hash": stored.hash,
            "metadata": stored.metadata,
        }

    async def _delete(self, path: str) -> dict:
        """Delete code from FalkorDB."""
        if not path:
            return {"error": "path is required"}

        loader = await CodeLoader.get()
        await loader.delete(path)
        return {"status": "ok", "deleted": path}

    async def _search(self, query: str, code_type: str) -> dict:
        """Search stored code."""
        if not query:
            return {"error": "query is required"}

        loader = await CodeLoader.get()

        ct = None
        if code_type:
            try:
                ct = CodeType(code_type.lower())
            except ValueError:
                pass

        results = await loader.search(query, code_type=ct)
        return {"status": "ok", "results": results}

    async def _list(self, code_type: str) -> dict:
        """List all stored code."""
        loader = await CodeLoader.get()

        ct = None
        if code_type:
            try:
                ct = CodeType(code_type.lower())
            except ValueError:
                pass

        paths = await loader.list_code(code_type=ct)
        return {"status": "ok", "paths": paths, "count": len(paths)}

    async def _status(self) -> dict:
        """Get code storage status."""
        loader = await CodeLoader.get()

        # Count by type
        type_counts = {}
        for code_type in CodeType:
            paths = await loader.list_code(code_type=code_type)
            if paths:
                type_counts[code_type.value] = len(paths)

        total = sum(type_counts.values())

        return {
            "status": "ok",
            "total_files": total,
            "by_type": type_counts,
        }
