"""MCP resource definitions for HITL Hub."""

import json
import logging

from nodus_hitl_hub.bootstrap import get_engine

logger = logging.getLogger(__name__)


def register_resources(mcp) -> None:
    """Register all HITL MCP resources on the FastMCP server."""

    @mcp.resource("hitl://inbox/{user_id}")
    async def hitl_inbox(user_id: str) -> str:
        """Get all pending HITL items for a user.

        Returns JSON array of HITL events ordered by newest first.
        Groups items by kind: 10003 (constitutional), 10020 (async inbox),
        10100 (recording results), etc.

        This is the single endpoint the frontend uses to render the unified inbox.
        Survives page refresh because it reads from the database.
        """
        engine = await get_engine()
        events = await engine.get_inbox(user_id)
        result = [e.model_dump(mode="json") for e in events]
        logger.debug("Inbox for user %s: %d pending items", user_id, len(result))
        return json.dumps(result, default=str)

    logger.info("MCP resource registered: hitl://inbox/{user_id}")
