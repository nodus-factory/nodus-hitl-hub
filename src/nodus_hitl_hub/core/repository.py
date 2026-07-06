"""Repository: PostgreSQL CRUD operations on nostr_hitl table."""

import json
import logging
from datetime import datetime
from typing import Optional

import asyncpg

from nodus_hitl_hub.models.hitl import HITLStatus
from nodus_hitl_hub.models.events import HITLEvent

logger = logging.getLogger(__name__)


class Repository:
    """Async PostgreSQL repository for nostr_hitl table."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def insert(self, event: HITLEvent) -> None:
        """Insert a new HITL event."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO nostr_hitl (
                    event_id, kind, pubkey, session_id, reference_id,
                    dw_pubkey, owner_pubkey, user_id,
                    content, hint, action, payload, tags,
                    status, created_at, expires_at,
                    sig, verified, relay_url, tenant_id
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8,
                    $9, $10, $11, $12, $13,
                    $14, $15, $16,
                    $17, $18, $19, $20
                )
                """,
                event.event_id,
                event.kind,
                event.pubkey,
                event.session_id,
                event.reference_id,
                event.dw_pubkey,
                event.owner_pubkey,
                event.user_id,
                event.content,
                event.hint,
                event.action,
                json.dumps(event.payload or {}),
                json.dumps(event.tags or []),
                event.status.value if isinstance(event.status, HITLStatus) else event.status,
                event.created_at,
                event.expires_at,
                event.sig,
                event.verified,
                event.relay_url,
                event.tenant_id,
            )

    async def get(self, event_id: str) -> Optional[HITLEvent]:
        """Get a HITL event by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM nostr_hitl WHERE event_id = $1",
                event_id,
            )
            if row is None:
                return None
            return self._row_to_event(row)

    async def update_status(
        self,
        event_id: str,
        status: HITLStatus,
        response: Optional[dict] = None,
    ) -> None:
        """Update the status and optionally the payload of a HITL event."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE nostr_hitl
                SET status = $2,
                    resolved_at = NOW(),
                    payload = CASE WHEN $3 IS NOT NULL THEN $3::jsonb ELSE payload END
                WHERE event_id = $1
                """,
                event_id,
                status.value,
                json.dumps(response) if response else None,
            )

    async def list_pending(self, user_id: str) -> list[HITLEvent]:
        """List all pending HITL events for a user, ordered by newest first."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM nostr_hitl
                WHERE user_id = $1
                  AND status IN ('pending', 'active')
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY created_at DESC
                LIMIT 100
                """,
                user_id,
            )
            return [self._row_to_event(row) for row in rows]

    async def expire_stale(self) -> int:
        """Mark all expired pending events as expired. Returns count of expired."""
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE nostr_hitl
                SET status = 'expired', resolved_at = NOW()
                WHERE status = 'pending'
                  AND expires_at IS NOT NULL
                  AND expires_at < NOW()
                """
            )
            count = int(result.split()[-1]) if result else 0
            if count:
                logger.info("Expired %d stale HITL events", count)
            return count

    def _row_to_event(self, row: asyncpg.Record) -> HITLEvent:
        """Convert a database row to a HITLEvent."""
        payload = row["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        tags = row["tags"]
        if isinstance(tags, str):
            tags = json.loads(tags)

        return HITLEvent(
            event_id=row["event_id"],
            kind=row["kind"],
            pubkey=row["pubkey"],
            session_id=row["session_id"],
            reference_id=row["reference_id"],
            dw_pubkey=row["dw_pubkey"],
            owner_pubkey=row["owner_pubkey"],
            user_id=row["user_id"],
            content=row["content"],
            hint=row["hint"],
            action=row["action"],
            payload=payload or {},
            tags=tags or [],
            status=HITLStatus(row["status"]),
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            expires_at=row["expires_at"],
            sig=row["sig"],
            verified=row["verified"] or False,
            relay_url=row["relay_url"],
            tenant_id=row["tenant_id"],
        )
