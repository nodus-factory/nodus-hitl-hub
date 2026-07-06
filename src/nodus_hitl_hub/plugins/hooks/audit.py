"""Audit hook: logs all state transitions to the event store (append-only)."""

import json
import logging

from nodus_hitl_hub.core.lifecycle import LifecycleHook
from nodus_hitl_hub.models.events import HITLEvent

logger = logging.getLogger(__name__)


class AuditHook(LifecycleHook):
    """Logs all HITL lifecycle events. Extend to write to a dedicated audit table."""

    async def on_created(self, event: HITLEvent) -> None:
        logger.info(
            "AUDIT | HITL created | id=%s action=%s user=%s tenant=%s",
            event.event_id,
            event.action,
            event.user_id,
            event.tenant_id,
        )

    async def on_approved(self, event: HITLEvent) -> None:
        logger.info(
            "AUDIT | HITL approved | id=%s action=%s user=%s",
            event.event_id,
            event.action,
            event.user_id,
        )

    async def on_rejected(self, event: HITLEvent) -> None:
        reason = event.payload.get("reason", "unknown") if isinstance(event.payload, dict) else "unknown"
        logger.info(
            "AUDIT | HITL rejected | id=%s action=%s user=%s reason=%s",
            event.event_id,
            event.action,
            event.user_id,
            reason,
        )

    async def on_expired(self, event: HITLEvent) -> None:
        logger.info(
            "AUDIT | HITL expired | id=%s action=%s user=%s",
            event.event_id,
            event.action,
            event.user_id,
        )
