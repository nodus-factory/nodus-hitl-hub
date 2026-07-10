"""MCP tool definitions for HITL Hub."""

import logging

from collections.abc import Awaitable, Callable

from nodus_hitl_hub.bootstrap import get_engine, get_notify_engine
from nodus_hitl_hub.core.engine import HITLEngine
from nodus_hitl_hub.core.notify_engine import NotifyEngine
from nodus_hitl_hub.models.hitl import HITLRequest
from nodus_hitl_hub.models.notify import NotifyPriority, NotifyRequest

logger = logging.getLogger(__name__)


def register_tools(
    mcp,
    hitl_engine_factory: Callable[[], Awaitable[HITLEngine]] = get_engine,
    notify_engine_factory: Callable[[], Awaitable[NotifyEngine]] = get_notify_engine,
) -> None:
    """Register all HITL and Notify MCP tools on the FastMCP server."""

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

        Creates a HITL event, persists it to the database, publishes a
        kind:10020 inbox item to the Nostr relay (llibreta inbox) and notifies
        the remaining configured channels.

        Args:
            action_type: Type of action (send_email, deploy_sensor, modelbook_conflict, etc.)
            action_description: Human-readable description shown to the user
            user_id: User ID who must approve
            action_details: Structured payload with action-specific fields
            tenant_id: Tenant ID for multi-tenant isolation
            timeout_seconds: How long until the request expires (default 300s = 5 min)
            metadata: Extra metadata (session_id, dw_pubkey, idempotency_key, tags, etc.)
        """
        engine = await hitl_engine_factory()
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
        engine = await hitl_engine_factory()
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
        engine = await hitl_engine_factory()
        result = await engine.check(confirmation_id)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def notify_send(
        user_id: str,
        title: str,
        body: str,
        priority: str = "normal",
        url: str | None = None,
        channels: list[str] | None = None,
        tenant_id: str = "default",
    ) -> dict:
        """Send a fire-and-forget notification to the user's configured channels.

        Args:
            user_id: Target user ID
            title: Notification title
            body: Notification body
            priority: info | normal | urgent | critical
            url: Optional deep link
            channels: Explicit channel override (webpush, email, whatsapp, inapp, voice)
            tenant_id: Tenant ID for preference lookup
        """
        notify_engine = await notify_engine_factory()
        req = NotifyRequest(
            user_id=user_id,
            title=title,
            body=body,
            priority=NotifyPriority(priority),
            url=url,
            channels=channels,
            tenant_id=tenant_id,
        )
        result = await notify_engine.send(req)
        return result.model_dump(mode="json")

    @mcp.tool()
    async def notify_ack(notification_id: str) -> dict:
        """Mark a notification as acknowledged by the user."""
        notify_engine = await notify_engine_factory()
        acked = await notify_engine.ack(notification_id)
        return {"notification_id": notification_id, "acked": acked}

    @mcp.tool()
    async def notify_history(user_id: str, limit: int = 20) -> list[dict]:
        """Return recent notification log entries for a user."""
        notify_engine = await notify_engine_factory()
        return await notify_engine.history(user_id, limit=limit)

    logger.info(
        "MCP tools registered: hitl_request_confirmation, hitl_wait_for_confirmation, "
        "hitl_check_status, notify_send, notify_ack, notify_history"
    )
