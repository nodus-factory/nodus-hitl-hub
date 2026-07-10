"""Fire-and-forget notification router."""

import logging
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from nodus_hitl_hub.core.channels import ChannelRegistry
from nodus_hitl_hub.core.notify_repository import NotificationPreference, NotifyRepository
from nodus_hitl_hub.models.notify import NotifyPriority, NotifyRequest, NotifyResult, priority_gte

logger = logging.getLogger(__name__)

ADDRESS_CHANNELS = frozenset({"email", "whatsapp", "voice"})
LOG_ONLY_CHANNELS = frozenset({"inapp"})


class NotifyEngine:
    """Routes NotifyRequest to channel adapters based on preferences."""

    def __init__(
        self,
        repository: NotifyRepository,
        channels: ChannelRegistry,
    ):
        self.repository = repository
        self.channels = channels

    async def send(self, req: NotifyRequest) -> NotifyResult:
        notification_id = f"notify_{uuid.uuid4().hex[:16]}"
        preferences = await self.repository.get_preferences(req.user_id, req.tenant_id)

        if req.channels is not None:
            target_channels = list(req.channels)
        else:
            target_channels = self._channels_from_preferences(req, preferences)

        pref_by_channel = {p.channel: p for p in preferences}
        hour_utc = datetime.now(timezone.utc).hour

        attempted: list[str] = []
        succeeded: list[str] = []
        failed: list[str] = []

        for channel in target_channels:
            pref = pref_by_channel.get(channel)
            if pref and not pref.enabled:
                continue
            if pref and not self._passes_quiet_hours(pref, req.priority, hour_utc):
                logger.info(
                    "notify %s: skipping %s (quiet hours)",
                    notification_id,
                    channel,
                )
                continue

            send_req = deepcopy(req)
            if channel in ADDRESS_CHANNELS:
                address = pref.address if pref else None
                if not address:
                    logger.info(
                        "notify %s: skipping %s (no address)",
                        notification_id,
                        channel,
                    )
                    continue
                send_req.metadata = dict(send_req.metadata)
                send_req.metadata["address"] = address

            attempted.append(channel)

            if channel in LOG_ONLY_CHANNELS:
                succeeded.append(channel)
                continue

            adapter = self.channels.get(channel)
            if adapter is None:
                failed.append(channel)
                logger.warning("notify %s: no adapter for channel %s", notification_id, channel)
                continue

            try:
                ok = await adapter.send(send_req)
            except Exception as e:
                logger.error("notify %s: adapter %s raised: %s", notification_id, channel, e)
                ok = False

            if ok:
                succeeded.append(channel)
            else:
                failed.append(channel)

        await self.repository.insert_log(
            notification_id=notification_id,
            user_id=req.user_id,
            tenant_id=req.tenant_id,
            title=req.title,
            body=req.body,
            priority=req.priority.value if isinstance(req.priority, NotifyPriority) else req.priority,
            url=req.url,
            channels_attempted=attempted,
            channels_succeeded=succeeded,
        )

        logger.info(
            "notify sent: id=%s user=%s attempted=%s succeeded=%s failed=%s",
            notification_id,
            req.user_id,
            attempted,
            succeeded,
            failed,
        )

        return NotifyResult(
            notification_id=notification_id,
            channels_attempted=attempted,
            channels_succeeded=succeeded,
            channels_failed=failed,
        )

    async def ack(self, notification_id: str) -> bool:
        return await self.repository.mark_acked(notification_id)

    async def history(self, user_id: str, limit: int = 20) -> list[dict]:
        rows = await self.repository.list_history(user_id, limit)
        return [
            {
                "notification_id": r.notification_id,
                "user_id": r.user_id,
                "tenant_id": r.tenant_id,
                "title": r.title,
                "body": r.body,
                "priority": r.priority,
                "url": r.url,
                "channels_attempted": r.channels_attempted,
                "channels_succeeded": r.channels_succeeded,
                "created_at": r.created_at.isoformat(),
                "acked_at": r.acked_at.isoformat() if r.acked_at else None,
            }
            for r in rows
        ]

    def _channels_from_preferences(
        self,
        req: NotifyRequest,
        preferences: list[NotificationPreference],
    ) -> list[str]:
        if not preferences:
            if req.priority == NotifyPriority.INFO:
                return []
            return ["webpush"]

        channels: list[str] = []
        for pref in preferences:
            if not pref.enabled:
                continue
            if not priority_gte(req.priority, pref.min_priority):
                continue
            channels.append(pref.channel)
        return channels

    @staticmethod
    def _passes_quiet_hours(pref: NotificationPreference, priority: NotifyPriority, hour_utc: int) -> bool:
        if priority == NotifyPriority.CRITICAL:
            return True
        start = pref.quiet_hours_start
        end = pref.quiet_hours_end
        if start is None or end is None:
            return True
        if start == end:
            return False
        if start < end:
            in_quiet = start <= hour_utc < end
        else:
            in_quiet = hour_utc >= start or hour_utc < end
        return not in_quiet
