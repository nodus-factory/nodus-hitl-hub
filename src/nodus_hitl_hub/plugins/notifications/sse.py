"""SSE notification: pushes real-time event to connected users."""

import logging

from nodus_hitl_hub.core.dispatcher import NotificationPlugin
from nodus_hitl_hub.models.events import HITLEvent

logger = logging.getLogger(__name__)


class SSENotify(NotificationPlugin):
    """Pushes SSE events to connected users in real-time."""

    def __init__(self):
        self._queues: dict[str, list] = {}  # user_id → list of asyncio queues

    def register_user(self, user_id: str) -> None:
        """Register a user for SSE notifications. Creates a queue if not exists."""
        if user_id not in self._queues:
            self._queues[user_id] = []

    def unregister_user(self, user_id: str) -> None:
        """Unregister a user."""
        self._queues.pop(user_id, None)

    def get_queue(self, user_id: str) -> list | None:
        """Get the asyncio queue for a user, creating it if needed."""
        if user_id not in self._queues:
            self._queues[user_id] = []
        return self._queues[user_id]  # TODO: Replace with asyncio.Queue for real streaming

    async def notify(self, event: HITLEvent) -> None:
        """Push SSE event to the affected user if they are connected."""
        user_id = event.user_id
        if not user_id or user_id not in self._queues:
            return

        sse_event = {
            "event_id": event.event_id,
            "event_type": "confirmation_required",
            "action_type": event.action,
            "action_description": event.hint,
            "action_data": event.payload,
            "status": "pending",
            "expires_at": event.expires_at.isoformat() if event.expires_at else None,
            "created_at": event.created_at.isoformat(),
        }

        # TODO: Put into asyncio.Queue for the user's SSE stream
        logger.info("SSE event queued for user %s: HITL %s", user_id, event.event_id)
