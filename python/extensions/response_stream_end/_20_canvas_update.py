"""
Canvas Update Extension

After each agent response, analyze the conversation and potentially
update the canvas with contextually relevant content.
"""

import asyncio
from python.helpers.extension import Extension
from python.helpers.canvas import (
    ConversationRoom,
    get_room_manager,
)
from python.helpers.gist_analyzer import ContentGenerator
from agent import LoopData


# Track canvas update state per room
_last_update_turn: dict[str, int] = {}
UPDATE_INTERVAL = 3  # Update every N turns


class CanvasUpdate(Extension):
    """
    Analyzes conversation after each response and updates canvas if appropriate.
    """

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        # Check if we're in a conversation room context
        room_id = self.agent.get_data("current_room_id")
        if not room_id:
            return

        try:
            manager = await get_room_manager()
            room = await manager.get_room(room_id)
            if not room:
                return

            # Check if we should update
            current_turn = len(room.turns)
            last_update = _last_update_turn.get(room_id, 0)

            if current_turn - last_update < UPDATE_INTERVAL:
                return

            # Create content generator and update
            generator = ContentGenerator(self.agent)

            # Check if update is warranted
            should_update = await generator.analyzer.should_update_canvas(room)

            if should_update:
                # Log the canvas update
                log_item = self.agent.context.log.log(
                    type="util",
                    heading="Updating canvas...",
                )

                # Generate content
                generated = await generator.generate_for_room(room)

                if generated:
                    _last_update_turn[room_id] = current_turn
                    log_item.update(
                        heading=f"Canvas updated with {len(generated)} elements",
                    )
                else:
                    log_item.update(heading="No canvas updates needed")

        except Exception as e:
            # Don't break the main flow for canvas errors
            from python.helpers.print_style import PrintStyle
            PrintStyle.error(f"Canvas update error: {e}")
