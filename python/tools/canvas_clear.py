"""
Canvas Clear Tool

Clear canvas elements - either specific ones or all content.
"""

from python.helpers.tool import Tool, Response
from python.helpers.canvas import get_room


class CanvasClear(Tool):
    """
    Clear canvas content.

    Usage:
        canvas_clear:
            room_id: "room_abc123"
            element_id: "optional_specific_element"  # omit to clear all
    """

    async def execute(self, **kwargs):
        room_id = self.args.get("room_id")
        element_id = self.args.get("element_id")

        if not room_id:
            return Response(
                message="Error: room_id is required",
                break_loop=False,
            )

        room = await get_room(room_id)
        if not room:
            return Response(
                message=f"Error: Room {room_id} not found",
                break_loop=False,
            )

        if element_id:
            room.clear_canvas(element_id)
            return Response(
                message=f"Cleared canvas element: {element_id}",
                break_loop=False,
            )
        else:
            room.clear_canvas()
            return Response(
                message="Cleared all canvas content",
                break_loop=False,
            )

    async def before_execution(self, **kwargs):
        element_id = self.args.get("element_id")
        heading = f"Clearing canvas element: {element_id}" if element_id else "Clearing all canvas"
        self.log = self.agent.context.log.log(
            type="canvas",
            heading=heading,
            content="",
        )

    async def after_execution(self, response, **kwargs):
        self.log.update(content=response.message)
