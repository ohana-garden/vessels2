from python.helpers.memory import Memory
from python.helpers.tool import Tool, Response
from python.helpers.guardians import guard_memory

DEFAULT_THRESHOLD = 0.7
DEFAULT_LIMIT = 10


class MemoryLoad(Tool):

    async def execute(self, query="", threshold=DEFAULT_THRESHOLD, limit=DEFAULT_LIMIT, filter="", **kwargs):
        db = await Memory.get(self.agent)
        docs = await db.search_similarity_threshold(query=query, limit=limit, threshold=threshold, filter=filter)

        if len(docs) == 0:
            result = self.agent.read_prompt("fw.memories_not_found.md", query=query)
        else:
            text = "\n\n".join(Memory.format_docs_plain(docs))
            # Guard memory output - stored data may contain injection patterns
            result = guard_memory(str(text), source="memory_load_tool")

        return Response(message=result, break_loop=False)
