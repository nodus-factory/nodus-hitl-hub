"""Repository for notification_log and notification_preferences."""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class NotificationPreference:
    user_id: str
    tenant_id: str
    channel: str
    enabled: bool
    address: Optional[str]
    min_priority: str
    quiet_hours_start: Optional[int]
    quiet_hours_end: Optional[int]


@dataclass
class NotificationLogRow:
    notification_id: str
    user_id: str
    tenant_id: str
    title: Optional[str]
    body: Optional[str]
    priority: str
    url: Optional[str]
    channels_attempted: list[str]
    channels_succeeded: list[str]
    created_at: datetime
    acked_at: Optional[datetime]


class NotifyRepository:
    """Async PostgreSQL access for notification tables."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def insert_log(
        self,
        notification_id: str,
        user_id: str,
        tenant_id: str,
        title: str,
        body: str,
        priority: str,
        url: Optional[str],
        channels_attempted: list[str],
        channels_succeeded: list[str],
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO notification_log (
                    notification_id, user_id, tenant_id, title, body, priority, url,
                    channels_attempted, channels_succeeded
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb)
                """,
                notification_id,
                user_id,
                tenant_id,
                title,
                body,
                priority,
                url,
                json.dumps(channels_attempted),
                json.dumps(channels_succeeded),
            )

    async def mark_acked(self, notification_id: str) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE notification_log
                SET acked_at = NOW()
                WHERE notification_id = $1 AND acked_at IS NULL
                """,
                notification_id,
            )
            return result.endswith("1")

    async def get_preferences(self, user_id: str, tenant_id: str = "default") -> list[NotificationPreference]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, tenant_id, channel, enabled, address,
                       min_priority, quiet_hours_start, quiet_hours_end
                FROM notification_preferences
                WHERE user_id = $1 AND tenant_id = $2
                """,
                user_id,
                tenant_id,
            )
            return [self._row_to_pref(row) for row in rows]

    async def list_history(self, user_id: str, limit: int = 20) -> list[NotificationLogRow]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT notification_id, user_id, tenant_id, title, body, priority, url,
                       channels_attempted, channels_succeeded, created_at, acked_at
                FROM notification_log
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                user_id,
                limit,
            )
            return [self._row_to_log(row) for row in rows]

    def _row_to_pref(self, row: asyncpg.Record) -> NotificationPreference:
        return NotificationPreference(
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
            channel=row["channel"],
            enabled=row["enabled"],
            address=row["address"],
            min_priority=row["min_priority"] or "normal",
            quiet_hours_start=row["quiet_hours_start"],
            quiet_hours_end=row["quiet_hours_end"],
        )

    def _row_to_log(self, row: asyncpg.Record) -> NotificationLogRow:
        attempted = row["channels_attempted"]
        if isinstance(attempted, str):
            attempted = json.loads(attempted)
        succeeded = row["channels_succeeded"]
        if isinstance(succeeded, str):
            succeeded = json.loads(succeeded)
        return NotificationLogRow(
            notification_id=row["notification_id"],
            user_id=row["user_id"],
            tenant_id=row["tenant_id"],
            title=row["title"],
            body=row["body"],
            priority=row["priority"] or "normal",
            url=row["url"],
            channels_attempted=list(attempted or []),
            channels_succeeded=list(succeeded or []),
            created_at=row["created_at"],
            acked_at=row["acked_at"],
        )
