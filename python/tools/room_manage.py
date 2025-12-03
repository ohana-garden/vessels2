"""
Conversation Room Management Tool

Create, join, and manage multi-agent conversation rooms.
"""

from python.helpers.tool import Tool, Response
from python.helpers.canvas import (
    ConversationRoom,
    HumanProxy,
    EntityAgent,
    EntityKind,
    SpeakerStyle,
    get_room,
    get_room_manager,
)
import json


class RoomManage(Tool):
    """
    Manage conversation rooms for multi-agent dialogue.

    Methods:
        create: Create a new room
        join: Add a participant to a room
        leave: Remove a participant
        list: List room participants
        speak: Add a turn to the conversation
        direct: Human directs their proxy
        barge_in: Human speaks directly

    Usage:
        room_manage:
            method: "create"
            name: "Garden Council"

        room_manage:
            method: "join"
            room_id: "room_abc123"
            participant:
                type: "entity_agent"
                name: "Old Breadfruit"
                entity_kind: "plant"
                personality: "Wise and patient, has seen many seasons"
    """

    async def execute(self, **kwargs):
        method = self.method or self.args.get("method", "list")

        if method == "create":
            return await self._create_room()
        elif method == "join":
            return await self._join_room()
        elif method == "leave":
            return await self._leave_room()
        elif method == "list":
            return await self._list_participants()
        elif method == "speak":
            return await self._speak()
        elif method == "direct":
            return await self._direct_proxy()
        elif method == "barge_in":
            return await self._barge_in()
        else:
            return Response(
                message=f"Unknown method: {method}",
                break_loop=False,
            )

    async def _create_room(self) -> Response:
        """Create a new conversation room."""
        name = self.args.get("name", "")

        manager = await get_room_manager()
        room = await manager.create_room(name)

        return Response(
            message=f"Created room: {room.id} ({room.name})",
            break_loop=False,
        )

    async def _join_room(self) -> Response:
        """Add a participant to a room."""
        room_id = self.args.get("room_id")
        participant_data = self.args.get("participant", {})

        if not room_id:
            return Response(message="Error: room_id required", break_loop=False)

        room = await get_room(room_id)
        if not room:
            return Response(message=f"Room {room_id} not found", break_loop=False)

        # Parse participant data
        if isinstance(participant_data, str):
            try:
                participant_data = json.loads(participant_data)
            except json.JSONDecodeError:
                return Response(message="Invalid participant data", break_loop=False)

        ptype = participant_data.get("type", "entity_agent")

        # Create style if provided
        style_data = participant_data.get("style", {})
        style = SpeakerStyle(**style_data) if style_data else SpeakerStyle()

        from python.helpers import guids
        participant_id = participant_data.get("id", guids.generate_id(8))

        if ptype == "human_proxy":
            participant = HumanProxy(
                id=participant_id,
                name=participant_data.get("name", "Human"),
                human_id=participant_data.get("human_id", ""),
                role=participant_data.get("role", "participant"),
                style=style,
                voice_id=participant_data.get("voice_id", ""),
                personality=participant_data.get("personality", ""),
            )
        else:
            entity_kind = participant_data.get("entity_kind", "plant")
            try:
                kind = EntityKind(entity_kind)
            except ValueError:
                kind = EntityKind.PLANT

            participant = EntityAgent(
                id=participant_id,
                name=participant_data.get("name", "Entity"),
                entity_kind=kind,
                entity_data=participant_data.get("entity_data", {}),
                location=participant_data.get("location"),
                style=style,
                voice_id=participant_data.get("voice_id", ""),
                personality=participant_data.get("personality", ""),
                knowledge_areas=participant_data.get("knowledge_areas", []),
            )

        room.add_participant(participant)

        return Response(
            message=f"Added {participant.name} to room {room.name}",
            break_loop=False,
        )

    async def _leave_room(self) -> Response:
        """Remove a participant from a room."""
        room_id = self.args.get("room_id")
        participant_id = self.args.get("participant_id")

        if not room_id or not participant_id:
            return Response(
                message="Error: room_id and participant_id required",
                break_loop=False,
            )

        room = await get_room(room_id)
        if not room:
            return Response(message=f"Room {room_id} not found", break_loop=False)

        room.remove_participant(participant_id)

        return Response(
            message=f"Removed participant {participant_id} from room",
            break_loop=False,
        )

    async def _list_participants(self) -> Response:
        """List participants in a room."""
        room_id = self.args.get("room_id")

        if not room_id:
            return Response(message="Error: room_id required", break_loop=False)

        room = await get_room(room_id)
        if not room:
            return Response(message=f"Room {room_id} not found", break_loop=False)

        participants = room.get_active_participants()
        lines = [f"Room: {room.name} ({room.id})"]
        lines.append(f"Participants ({len(participants)}):")

        for p in participants:
            ptype = p.participant_type.value
            if isinstance(p, HumanProxy):
                lines.append(f"  - {p.name} [{ptype}] role: {p.role}")
            elif isinstance(p, EntityAgent):
                lines.append(f"  - {p.name} [{ptype}] kind: {p.entity_kind.value}")
            else:
                lines.append(f"  - {p.name} [{ptype}]")

        return Response(
            message="\n".join(lines),
            break_loop=False,
        )

    async def _speak(self) -> Response:
        """Add a turn to the conversation as a participant."""
        room_id = self.args.get("room_id")
        participant_id = self.args.get("participant_id")
        content = self.args.get("content", "")

        if not room_id or not participant_id:
            return Response(
                message="Error: room_id and participant_id required",
                break_loop=False,
            )

        room = await get_room(room_id)
        if not room:
            return Response(message=f"Room {room_id} not found", break_loop=False)

        participant = room.get_participant(participant_id)
        if not participant:
            return Response(
                message=f"Participant {participant_id} not in room",
                break_loop=False,
            )

        # Check for canvas references
        references_canvas = any(word in content.lower() for word in [
            "see", "show", "map", "calendar", "chart", "image", "looking at",
            "on screen", "displayed", "visible"
        ])

        turn = room.add_turn(
            participant_id=participant_id,
            content=content,
            references_canvas=references_canvas,
        )

        return Response(
            message=f"{participant.name}: {content}",
            break_loop=False,
        )

    async def _direct_proxy(self) -> Response:
        """Human gives direction to their proxy."""
        room_id = self.args.get("room_id")
        human_id = self.args.get("human_id")
        proxy_id = self.args.get("proxy_id")
        direction = self.args.get("direction", "")

        if not all([room_id, human_id, proxy_id, direction]):
            return Response(
                message="Error: room_id, human_id, proxy_id, and direction required",
                break_loop=False,
            )

        room = await get_room(room_id)
        if not room:
            return Response(message=f"Room {room_id} not found", break_loop=False)

        room.human_directs_proxy(human_id, proxy_id, direction)

        return Response(
            message=f"Direction queued for proxy: {direction}",
            break_loop=False,
        )

    async def _barge_in(self) -> Response:
        """Human speaks directly, interrupting the conversation."""
        room_id = self.args.get("room_id")
        human_id = self.args.get("human_id")
        content = self.args.get("content", "")

        if not all([room_id, human_id, content]):
            return Response(
                message="Error: room_id, human_id, and content required",
                break_loop=False,
            )

        room = await get_room(room_id)
        if not room:
            return Response(message=f"Room {room_id} not found", break_loop=False)

        turn = room.human_barge_in(human_id, content)

        return Response(
            message=f"[Human Direct]: {content}",
            break_loop=False,
        )

    async def before_execution(self, **kwargs):
        method = self.method or self.args.get("method", "")
        self.log = self.agent.context.log.log(
            type="room",
            heading=f"Room: {method}",
            content="",
        )

    async def after_execution(self, response, **kwargs):
        self.log.update(content=response.message)
