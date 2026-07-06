"""Cache hook: invalidates Redis cache on state transitions."""

import logging

from nodus_hitl_hub.core.lifecycle import LifecycleHook
from nodus_hitl_hub.models.events import HITLEvent

logger = logging.getLogger(__name__)


class CacheHook(LifecycleHook):
    """Handles cache invalidation for inbox queries."""

    def __init__(self):
        self._redis = None  # Will be set at startup

    async def on_created(self, event: HITLEvent) -> None:
        await self._invalidate_inbox(event.user_id)

    async def on_approved(self, event: HITLEvent) -> None:
        await self._invalidate_inbox(event.user_id)

    async def on_rejected(self, event: HITLEvent) -> None:
        await self._invalidate_inbox(event.user_id)

    async def on_expired(self, event: HITLEvent) -> None:
        await self._invalidate_inbox(event.user_id)

    async def _invalidate_inbox(self, user_id: str | None) -> None:
        """Invalidate the inbox cache for a user."""
        if not user_id or not self._redis:
            return
        try:
            await self._redis.delete(f"inbox:{user_id}")
            logger.debug("Cache invalidated for inbox:%s", user_id)
        except Exception as e:
            logger.warning("Cache invalidation failed for %s: %s", user_id, e)
