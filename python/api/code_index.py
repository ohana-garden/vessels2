"""
A0 API - Code Indexing

API endpoints for managing the code index in FalkorDB.
"""

from python.helpers.api import ApiHandler, Request
from python.helpers.code_store import CodeStore, CodeType


class CodeIndex(ApiHandler):
    """Index codebase into FalkorDB."""

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST", "GET"]

    async def process(self, input: dict, request: Request) -> dict:
        operation = input.get("operation", "status")

        if operation == "index_all":
            return await self._index_all()
        elif operation == "index_file":
            return await self._index_file(input.get("path", ""))
        elif operation == "index_directory":
            return await self._index_directory(input.get("directory", ""))
        elif operation == "search":
            return await self._search(input.get("query", ""), input.get("code_type", ""))
        elif operation == "status":
            return await self._status()
        else:
            return {"error": f"Unknown operation: {operation}"}

    async def _index_all(self) -> dict:
        """Index entire codebase."""
        store = await CodeStore.get()
        count = await store.index_codebase()
        return {"status": "ok", "indexed": count}

    async def _index_file(self, path: str) -> dict:
        """Index a single file."""
        if not path:
            return {"error": "path is required"}

        store = await CodeStore.get()
        result = await store.index_file(path)
        if result:
            return {"status": "ok", "path": path, "type": result.code_type.value}
        return {"error": f"Failed to index: {path}"}

    async def _index_directory(self, directory: str) -> dict:
        """Index a directory."""
        if not directory:
            return {"error": "directory is required"}

        store = await CodeStore.get()
        count = await store.index_directory(directory)
        return {"status": "ok", "directory": directory, "indexed": count}

    async def _search(self, query: str, code_type: str) -> dict:
        """Search indexed code."""
        if not query:
            return {"error": "query is required"}

        store = await CodeStore.get()

        ct = None
        if code_type:
            try:
                ct = CodeType(code_type.lower())
            except ValueError:
                pass

        results = await store.search(query, code_type=ct)
        return {"status": "ok", "results": results}

    async def _status(self) -> dict:
        """Get indexing status."""
        store = await CodeStore.get()
        paths = await store.list_code()

        # Count by type
        type_counts = {}
        for path in paths:
            data = await store.get_code(path)
            if data:
                ct = data.get("metadata", {}).get("code_type", "other")
                type_counts[ct] = type_counts.get(ct, 0) + 1

        return {
            "status": "ok",
            "total_files": len(paths),
            "by_type": type_counts,
        }
