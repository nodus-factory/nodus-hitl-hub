"""Nostr notification: publishes kind:10003 to the relay."""

import json
import logging

from nodus_hitl_hub.core.dispatcher import NotificationPlugin
from nodus_hitl_hub.models.events import HITLEvent

logger = logging.getLogger(__name__)


class NostrNotify(NotificationPlugin):
    """Publishes a kind:10003 Nostr event when a HITL is created."""

    def __init__(self):
        self._relay_url = None    # Will be set from env/config at startup
        self._publisher_sk = None  # Server-side signing key (custodial)

    async def notify(self, event: HITLEvent) -> None:
        """Publish kind:10003 HITL request to Nostr relay."""
        if not self._relay_url:
            logger.debug("Nostr relay not configured, skipping nostr notification")
            return

        content = json.dumps({
            "_hitl_required": True,
            "action": event.action,
            "action_description": event.hint,
            "action_data": event.payload,
            "message_to_user": event.hint,
            "agent": "hitl-hub",
        })

        tags = [
            ["p", event.owner_pubkey or ""],
            ["session", event.session_id or ""],
            ["hint", event.hint or ""],
            ["action", event.action or ""],
        ]

        nostr_event = {
            "kind": 10003,
            "content": content,
            "tags": tags,
            "created_at": int(event.created_at.timestamp()),
        }

        logger.info(
            "Would publish Nostr kind:10003 for HITL %s to %s",
            event.event_id,
            self._relay_url,
        )
        # TODO: Sign with publisher_sk and publish to relay_url
        # await relay.publish(signed_event)
