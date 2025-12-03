"""
Canvas Generation Tool

Allows agents to generate visual content on the canvas.
The canvas displays contextual content based on conversation.
"""

from python.helpers.tool import Tool, Response
from python.helpers.canvas import (
    ConversationRoom,
    CanvasElement,
    CanvasContentType,
    EntityAgent,
    get_room,
)
from python.helpers import guids
import json


class CanvasGenerate(Tool):
    """
    Generate visual content on the canvas.

    Usage:
        canvas_generate:
            room_id: "room_abc123"
            content_type: "map|calendar|visualization|gallery|entity_view|ambient"
            content:
                title: "My Content"
                # ... type-specific content fields
    """

    async def execute(self, **kwargs):
        room_id = self.args.get("room_id")
        content_type = self.args.get("content_type", "ambient")
        content = self.args.get("content", {})
        priority = int(self.args.get("priority", 5))

        if not room_id:
            return Response(
                message="Error: room_id is required",
                break_loop=False,
            )

        # Get or create room
        room = await get_room(room_id)
        if not room:
            return Response(
                message=f"Error: Room {room_id} not found",
                break_loop=False,
            )

        # Parse content if string
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                content = {"text": content}

        # Generate based on content type
        try:
            ctype = CanvasContentType(content_type)
        except ValueError:
            return Response(
                message=f"Error: Invalid content_type '{content_type}'. "
                        f"Valid types: {[e.value for e in CanvasContentType]}",
                break_loop=False,
            )

        # Get triggering participant
        triggered_by = self.args.get("triggered_by", self.agent.agent_name)

        element = None

        if ctype == CanvasContentType.MAP:
            element = room.generate_map(
                title=content.get("title", "Map"),
                locations=content.get("locations", []),
                center=content.get("center"),
                zoom=content.get("zoom", 12),
                routes=content.get("routes", []),
                triggered_by=triggered_by,
                priority=priority,
            )

        elif ctype == CanvasContentType.CALENDAR:
            element = room.generate_calendar(
                title=content.get("title", "Schedule"),
                events=content.get("events", []),
                view=content.get("view", "week"),
                highlighted=content.get("highlighted", []),
                triggered_by=triggered_by,
                priority=priority,
            )

        elif ctype == CanvasContentType.VISUALIZATION:
            element = room.generate_visualization(
                title=content.get("title", "Data"),
                data=content.get("data", {}),
                chart_type=content.get("chart_type", "bar"),
                triggered_by=triggered_by,
                priority=priority,
            )

        elif ctype == CanvasContentType.GALLERY:
            element = room.generate_gallery(
                title=content.get("title", "Gallery"),
                images=content.get("images", []),
                layout=content.get("layout", "grid"),
                triggered_by=triggered_by,
                priority=priority,
            )

        elif ctype == CanvasContentType.ENTITY_VIEW:
            entity_id = content.get("entity_id")
            if entity_id:
                entity = room.get_participant(entity_id)
                if isinstance(entity, EntityAgent):
                    element = room.generate_entity_view(
                        entity=entity,
                        triggered_by=triggered_by,
                        priority=priority,
                    )

        elif ctype == CanvasContentType.AMBIENT:
            element = room.generate_ambient(
                mood=content.get("mood", "calm"),
                imagery=content.get("imagery", {}),
                triggered_by=triggered_by,
                priority=priority,
            )

        elif ctype == CanvasContentType.RELATIONSHIP:
            element = CanvasElement(
                id=guids.generate_id(8),
                content_type=ctype,
                content={
                    "entities": content.get("entities", []),
                    "relationships": content.get("relationships", []),
                    "layout": content.get("layout", "force"),
                    **content,
                },
                priority=priority,
                triggered_by=triggered_by,
            )
            room.set_canvas(element)

        if element:
            return Response(
                message=f"Generated {content_type} canvas element: {element.id}",
                break_loop=False,
            )
        else:
            return Response(
                message=f"Failed to generate {content_type} content",
                break_loop=False,
            )

    async def before_execution(self, **kwargs):
        self.log = self.agent.context.log.log(
            type="canvas",
            heading=f"Generating canvas: {self.args.get('content_type', 'content')}",
            content="",
        )

    async def after_execution(self, response, **kwargs):
        self.log.update(content=response.message)
