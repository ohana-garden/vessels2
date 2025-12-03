from python.helpers.api import ApiHandler, Request, Response
from agent import AgentContext


class StuckStatus(ApiHandler):
    """API endpoint to diagnose stuck session states.

    This endpoint provides detailed information about whether a session
    appears to be stuck and why, enabling clients to take appropriate
    recovery actions.
    """

    async def process(self, input: dict, request: Request) -> dict | Response:
        ctxid = input.get("ctxid", "")
        if not ctxid:
            raise Exception("No context id provided")

        context = AgentContext.get(ctxid)
        if not context:
            raise Exception(f"Context '{ctxid}' not found")

        # Get detailed stuck status
        stuck_info = context.is_stuck()

        return {
            "ctxid": context.id,
            "stuck": stuck_info["stuck"],
            "reason": stuck_info["reason"],
            "details": stuck_info["details"],
            "can_nudge": stuck_info["stuck"],  # If stuck, nudge is recommended
            "message": (
                f"Session appears stuck: {stuck_info['reason']}"
                if stuck_info["stuck"]
                else "Session is healthy"
            ),
        }
