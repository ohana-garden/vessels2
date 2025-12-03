"""
Conversation Room API

Manage multi-agent conversation rooms.
"""

import json
from flask import Request
from python.helpers.api import ApiHandler, Input, Output
from python.helpers.canvas import (
    ConversationRoom,
    HumanProxy,
    EntityAgent,
    EntityKind,
    SpeakerStyle,
    EmotionalState,
    get_room,
    get_room_manager,
    create_room,
)
from python.helpers import guids


class room_api(ApiHandler):
    """
    Conversation room management API.

    Methods:
        create: Create a new room
        get: Get room state
        list: List all rooms
        join: Add participant to room
        leave: Remove participant
        speak: Add conversation turn
        direct: Human directs proxy
        barge_in: Human speaks directly
        update_emotion: Update participant emotional state
    """

    @classmethod
    def get_methods(cls) -> list[str]:
        return ["POST"]

    async def process(self, input: Input, request: Request) -> Output:
        method = input.get("method", "get")

        handlers = {
            "create": self._create,
            "get": self._get,
            "list": self._list,
            "join": self._join,
            "leave": self._leave,
            "speak": self._speak,
            "direct": self._direct,
            "barge_in": self._barge_in,
            "update_emotion": self._update_emotion,
        }

        handler = handlers.get(method)
        if not handler:
            return {"error": f"Unknown method: {method}"}

        return await handler(input)

    async def _create(self, input: Input) -> Output:
        """Create a new conversation room."""
        name = input.get("name", "")
        room = await create_room(name)

        return {
            "success": True,
            "room": {
                "id": room.id,
                "name": room.name,
            }
        }

    async def _get(self, input: Input) -> Output:
        """Get room state."""
        room_id = input.get("room_id")
        if not room_id:
            return {"error": "room_id required"}

        room = await get_room(room_id)
        if not room:
            return {"error": f"Room {room_id} not found"}

        return {
            "success": True,
            "room": room.to_dict(),
        }

    async def _list(self, input: Input) -> Output:
        """List all rooms."""
        manager = await get_room_manager()
        rooms = manager.get_all_rooms()

        return {
            "success": True,
            "rooms": [
                {
                    "id": r.id,
                    "name": r.name,
                    "participants": len(r.participants),
                    "turns": len(r.turns),
                    "lastActivity": r.last_activity.isoformat(),
                }
                for r in rooms
            ]
        }

    async def _join(self, input: Input) -> Output:
        """Add participant to room."""
        room_id = input.get("room_id")
        participant_data = input.get("participant", {})

        if not room_id:
            return {"error": "room_id required"}

        room = await get_room(room_id)
        if not room:
            return {"error": f"Room {room_id} not found"}

        ptype = participant_data.get("type", "entity_agent")
        pid = participant_data.get("id", guids.generate_id(8))

        # Build style
        style_data = participant_data.get("style", {})
        style = SpeakerStyle(**style_data) if style_data else SpeakerStyle()

        if ptype == "human_proxy":
            participant = HumanProxy(
                id=pid,
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
                id=pid,
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

        return {
            "success": True,
            "participant": participant.to_dict(),
        }

    async def _leave(self, input: Input) -> Output:
        """Remove participant from room."""
        room_id = input.get("room_id")
        participant_id = input.get("participant_id")

        if not room_id or not participant_id:
            return {"error": "room_id and participant_id required"}

        room = await get_room(room_id)
        if not room:
            return {"error": f"Room {room_id} not found"}

        room.remove_participant(participant_id)

        return {"success": True}

    async def _speak(self, input: Input) -> Output:
        """Add a conversation turn."""
        room_id = input.get("room_id")
        participant_id = input.get("participant_id")
        content = input.get("content", "")
        emotional_state = input.get("emotional_state", "neutral")

        if not room_id or not participant_id:
            return {"error": "room_id and participant_id required"}

        room = await get_room(room_id)
        if not room:
            return {"error": f"Room {room_id} not found"}

        try:
            emotion = EmotionalState(emotional_state)
        except ValueError:
            emotion = EmotionalState.NEUTRAL

        # Check for canvas references
        references_canvas = any(word in content.lower() for word in [
            "see", "show", "map", "calendar", "chart", "image",
            "looking at", "on screen", "displayed", "visible"
        ])

        turn = room.add_turn(
            participant_id=participant_id,
            content=content,
            emotional_state=emotion,
            references_canvas=references_canvas,
        )

        return {
            "success": True,
            "turn": turn.to_dict(),
        }

    async def _direct(self, input: Input) -> Output:
        """Human directs their proxy."""
        room_id = input.get("room_id")
        human_id = input.get("human_id")
        proxy_id = input.get("proxy_id")
        direction = input.get("direction", "")

        if not all([room_id, human_id, proxy_id, direction]):
            return {"error": "room_id, human_id, proxy_id, and direction required"}

        room = await get_room(room_id)
        if not room:
            return {"error": f"Room {room_id} not found"}

        room.human_directs_proxy(human_id, proxy_id, direction)

        return {"success": True, "direction": direction}

    async def _barge_in(self, input: Input) -> Output:
        """Human speaks directly."""
        room_id = input.get("room_id")
        human_id = input.get("human_id")
        content = input.get("content", "")

        if not all([room_id, human_id, content]):
            return {"error": "room_id, human_id, and content required"}

        room = await get_room(room_id)
        if not room:
            return {"error": f"Room {room_id} not found"}

        turn = room.human_barge_in(human_id, content)

        return {
            "success": True,
            "turn": turn.to_dict(),
        }

    async def _update_emotion(self, input: Input) -> Output:
        """Update participant emotional state (from Hume.ai)."""
        room_id = input.get("room_id")
        participant_id = input.get("participant_id")
        emotions = input.get("emotions", {})

        if not room_id or not participant_id:
            return {"error": "room_id and participant_id required"}

        room = await get_room(room_id)
        if not room:
            return {"error": f"Room {room_id} not found"}

        # Import emotional context handler
        from python.helpers.gist_analyzer import EmotionalContext
        ctx = EmotionalContext()
        state = ctx.update_emotional_state(participant_id, emotions)
        adaptations = ctx.get_adaptation_hints(participant_id)

        return {
            "success": True,
            "emotional_state": state.value,
            "adaptations": adaptations,
        }
