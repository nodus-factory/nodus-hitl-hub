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
        """Insert a new HITL event.

        The shared llibreta table declares session_id, dw_pubkey and content
        NOT NULL, so those are always coalesced to a value here.
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO nostr_hitl (
                    event_id, kind, pubkey, session_id, reference_id,
                    dw_pubkey, owner_pubkey, user_id,
                    content, hint, action, payload, tags,
                    status, created_at, expires_at,
                    sig, verified, relay_url, tenant_id, idempotency_key
                ) VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8,
                    $9, $10, $11, $12, $13,
                    $14, $15, $16,
                    $17, $18, $19, $20, $21
                )
                """,
                event.event_id,
                event.kind,
                event.pubkey,
                event.session_id or f"hitl-{event.event_id}",
                event.reference_id,
                event.dw_pubkey or "hitl-hub",
                event.owner_pubkey,
                event.user_id,
                event.content or json.dumps({"hint": event.hint, "action": event.action}),
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
                event.idempotency_key,
            )

    async def get_by_idempotency_key(self, key: str) -> Optional[HITLEvent]:
        """Find an existing HITL event by its producer idempotency key."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM nostr_hitl WHERE idempotency_key = $1",
                key,
            )
            return self._row_to_event(row) if row else None

    async def get_by_reference(self, reference_id: str) -> Optional[HITLEvent]:
        """Find a HITL event by the Nostr event id of its published kind:10020."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM nostr_hitl WHERE reference_id = $1",
                reference_id,
            )
            return self._row_to_event(row) if row else None

    async def set_reference(
        self,
        event_id: str,
        reference_id: str,
        relay_url: Optional[str] = None,
    ) -> None:
        """Record the Nostr event id (and relay) of the published request."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE nostr_hitl
                SET reference_id = $2,
                    relay_url = COALESCE($3, relay_url)
                WHERE event_id = $1
                """,
                event_id,
                reference_id,
                relay_url,
            )

    async def get_user_pubkey(self, user_id: str) -> Optional[str]:
        """Custodial Nostr pubkey (hex) for a numeric user id (users table)."""
        try:
            numeric_id = int(user_id)
        except (TypeError, ValueError):
            return None
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT nostr_pubkey FROM users WHERE id = $1",
                numeric_id,
            )
            return str(row["nostr_pubkey"]) if row and row["nostr_pubkey"] else None

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
        payload = row["payload"] if "payload" in row.keys() else {}
        if isinstance(payload, str):
            payload = json.loads(payload)
        tags = row["tags"]
        if isinstance(tags, str):
            tags = json.loads(tags)

        columns = set(row.keys())

        def col(name: str, default=None):
            return row[name] if name in columns else default

        return HITLEvent(
            event_id=row["event_id"],
            kind=row["kind"],
            pubkey=col("pubkey") or "hitl-hub",
            session_id=row["session_id"],
            reference_id=col("reference_id"),
            dw_pubkey=row["dw_pubkey"],
            owner_pubkey=row["owner_pubkey"],
            # Rows written by llibreta-v2 predate the user_id column.
            user_id=col("user_id") or "",
            content=row["content"],
            hint=row["hint"],
            action=row["action"],
            payload=payload or {},
            tags=tags or [],
            status=HITLStatus(row["status"]),
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            expires_at=col("expires_at"),
            sig=col("sig"),
            verified=col("verified") or False,
            relay_url=col("relay_url"),
            tenant_id=col("tenant_id") or "default",
            idempotency_key=col("idempotency_key"),
        )
