"""MCP tool definitions for HITL Hub."""

import logging

from nodus_hitl_hub.core.engine import HITLEngine
from nodus_hitl_hub.models.hitl import HITLRequest

logger = logging.getLogger(__name__)


def register_tools(mcp, engine: HITLEngine) -> None:
    """Register all HITL MCP tools on the FastMCP server."""

    @mcp.tool()
    async def hitl_request_confirmation(
        action_type: str,
        action_description: str,
        user_id: str,
        action_details: dict | None = None,
        tenant_id: str = "default",
        timeout_seconds: int = 300,
        metadata: dict | None = None,
    ) -> dict:
        """Request user confirmation for a sensitive action.

        Creates a HITL event, persists it to the database, and notifies the user
        via all configured channels (Nostr relay, SSE, etc.).

        Args:
            action_type: Type of action (send_email, deploy_sensor, start_recording, etc.)
            action_description: Human-readable description shown to the user
            user_id: User ID who must approve
            action_details: Structured payload with action-specific fields
            tenant_id: Tenant ID for multi-tenant isolation
            timeout_seconds: How long until the request expires (default 300s = 5 min)
            metadata: Extra metadata (session_id, dw_pubkey, tags, etc.)
        """
        req = HITLRequest(
            action_type=action_type,
            action_description=action_description,
            action_details=action_details or {},
            user_id=user_id,
            tenant_id=tenant_id,
            timeout_seconds=timeout_seconds,
            metadata=metadata or {},
        )

        result = await engine.request(req)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def hitl_wait_for_confirmation(
        confirmation_id: str,
        poll_interval_seconds: int = 2,
        max_wait_seconds: int = 300,
    ) -> dict:
        """Wait for a HITL confirmation to be resolved.

        Blocks the calling function (not the agent) until the user approves,
        rejects, or the timeout expires.

        Args:
            confirmation_id: The confirmation ID from hitl_request_confirmation
            poll_interval_seconds: Seconds between status checks (default 2)
            max_wait_seconds: Maximum time to wait (default 300s = 5 min)
        """
        result = await engine.wait(
            confirmation_id=confirmation_id,
            poll_interval=float(poll_interval_seconds),
            max_wait=float(max_wait_seconds),
        )
        return result.model_dump(mode="json")

    @mcp.tool()
    async def hitl_check_status(confirmation_id: str) -> dict:
        """Check the status of a HITL confirmation without blocking.

        Args:
            confirmation_id: The confirmation ID to check
        """
        result = await engine.check(confirmation_id)
        return result.model_dump(mode="json")

    logger.info("MCP tools registered: hitl_request_confirmation, hitl_wait_for_confirmation, hitl_check_status")
