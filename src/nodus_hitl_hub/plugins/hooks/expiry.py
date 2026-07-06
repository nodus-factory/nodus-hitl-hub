"""Expiry hook: periodically marks stale pending events as expired."""

import asyncio
import logging

from nodus_hitl_hub.core.lifecycle import LifecycleHook
from nodus_hitl_hub.models.events import HITLEvent

logger = logging.getLogger(__name__)


class ExpiryHook(LifecycleHook):
    """Background task that periodically expires stale HITL events."""

    def __init__(self, repository=None, interval_seconds: int = 60):
        self._repository = repository
        self._interval = interval_seconds
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        """Start the background expiry task."""
        if self._task is None:
            self._task = asyncio.create_task(self._expire_loop())
            logger.info("Expiry background task started (interval=%ds)", self._interval)

    def stop(self) -> None:
        """Stop the background expiry task."""
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("Expiry background task stopped")

    async def _expire_loop(self) -> None:
        """Periodically expire stale events."""
        while True:
            try:
                await asyncio.sleep(self._interval)
                if self._repository:
                    count = await self._repository.expire_stale()
                    if count:
                        logger.info("Expired %d stale HITL events", count)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Expiry loop error: %s", e)

    async def on_created(self, event: HITLEvent) -> None:
        pass  # No action needed on individual creates

    async def on_approved(self, event: HITLEvent) -> None:
        pass

    async def on_rejected(self, event: HITLEvent) -> None:
        pass

    async def on_expired(self, event: HITLEvent) -> None:
        pass  # Already handled by the background loop
