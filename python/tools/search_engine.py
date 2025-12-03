"""
A0 Tool - Search Engine

Web search tool using SearXNG backend.
Following A0 pattern with guardian integration for web content.
"""

from python.helpers.tool import Tool, Response
from python.helpers.errors import handle_error
from python.helpers.searxng import search as searxng
from python.helpers.guardians import guard_web

SEARCH_ENGINE_RESULTS = 10


class SearchEngine(Tool):
    """Web search tool using SearXNG metasearch engine."""

    async def execute(self, query="", **kwargs) -> Response:
        """Execute web search query."""
        result = await self._search(query)

        await self.agent.handle_intervention(result)

        return Response(message=result, break_loop=False)

    async def _search(self, query: str) -> str:
        """Perform search and format results."""
        try:
            results = await searxng(query)
            return self._format_results(results)
        except Exception as e:
            handle_error(e)
            return f"Search failed: {str(e)}"

    def _format_results(self, results: dict) -> str:
        """Format search results with guardian sanitization."""
        if not results or "results" not in results:
            return "No results found"

        outputs = []
        for item in results["results"][:SEARCH_ENGINE_RESULTS]:
            title = guard_web(item.get("title", ""), source="search.title")
            url = item.get("url", "")
            content = guard_web(item.get("content", ""), source="search.content")

            outputs.append(f"{title}\n{url}\n{content}")

        return "\n\n".join(outputs).strip() if outputs else "No results found"
