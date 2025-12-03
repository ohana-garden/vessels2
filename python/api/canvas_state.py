"""
Canvas State API

Get current canvas state and subscribe to updates.
"""

import json
import asyncio
from flask import Request, Response, stream_with_context
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.canvas import get_room, get_room_manager


class canvas_state(ApiHandler):
    """
    Get canvas state for a room.

    GET: Get current canvas state
    POST with stream=true: Stream canvas updates via SSE
    """

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["GET", "POST"]

    async def process(self, input: Input, request: Request) -> Output:
        room_id = input.get("room_id") or request.args.get("room_id")
        stream = input.get("stream", False)

        if not room_id:
            return {"error": "room_id required"}

        room = await get_room(room_id)
        if not room:
            return {"error": f"Room {room_id} not found"}

        if stream:
            return self._stream_updates(room_id)

        return {
            "room_id": room.id,
            "room_name": room.name,
            "canvas": room.get_canvas_state(),
            "subtitles": room.get_active_subtitles(),
            "gist": room.gist.to_dict(),
        }

    def _stream_updates(self, room_id: str) -> Response:
        """Stream canvas updates via Server-Sent Events."""

        def generate():
            # Queue for receiving updates
            update_queue = asyncio.Queue()

            async def on_canvas_update(event):
                await update_queue.put(("canvas", event))

            async def on_subtitle_update(event):
                await update_queue.put(("subtitle", event))

            # Get room and register listeners
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def setup():
                room = await get_room(room_id)
                if room:
                    room.on_canvas_update(lambda e: asyncio.run_coroutine_threadsafe(
                        update_queue.put(("canvas", e)), loop
                    ))
                    room.on_subtitle_update(lambda e: asyncio.run_coroutine_threadsafe(
                        update_queue.put(("subtitle", e)), loop
                    ))
                    # Send initial state
                    return {
                        "type": "initial",
                        "canvas": room.get_canvas_state(),
                        "subtitles": room.get_active_subtitles(),
                    }
                return None

            initial = loop.run_until_complete(setup())
            if initial:
                yield f"data: {json.dumps(initial)}\n\n"

            # Stream updates
            while True:
                try:
                    event_type, event = loop.run_until_complete(
                        asyncio.wait_for(update_queue.get(), timeout=30.0)
                    )
                    yield f"data: {json.dumps({'type': event_type, 'event': event})}\n\n"
                except asyncio.TimeoutError:
                    # Send keepalive
                    yield f": keepalive\n\n"
                except Exception:
                    break

        return Response(
            stream_with_context(generate()),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            }
        )
