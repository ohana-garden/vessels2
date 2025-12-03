import aiohttp
from python.helpers import runtime
from python.helpers.guardians import guard_web

URL = "http://localhost:55510/search"

async def search(query:str):
    return await runtime.call_development_function(_search, query=query)

async def _search(query:str):
    async with aiohttp.ClientSession() as session:
        async with session.post(URL, data={"q": query, "format": "json"}) as response:
            result = await response.json()
            # Guard web search results - sanitize any text fields
            if isinstance(result, dict) and "results" in result:
                for item in result.get("results", []):
                    if isinstance(item, dict):
                        for key in ["title", "content", "url"]:
                            if key in item and isinstance(item[key], str):
                                item[key] = guard_web(item[key], source="searxng")
            return result
