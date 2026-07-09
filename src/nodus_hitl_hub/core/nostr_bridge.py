"""Nostr bridge: publish kind:10020 requests + listen for kind:10021 resolutions.

The hub signs inbox items with its own key (HITL_HUB_NSEC) and targets the
owner's custodial pubkey via the `p` tag — that is the filter llibreta-v2's
inbox already subscribes to, so requests published here appear in the UI with
zero frontend changes. Resolutions come back as kind:10021 signed by the
owner; the listener maps them to hub rows via the `request` tag and drives
engine.approve/reject, which triggers lifecycle hooks (side-effects).
"""

import asyncio
import json
import logging
import os
from typing import TYPE_CHECKING, Optional

from nodus_hitl_hub.models.events import HITLEvent
from nodus_hitl_hub.models.hitl import HITLStatus

if TYPE_CHECKING:
    from nodus_hitl_hub.core.engine import HITLEngine

logger = logging.getLogger(__name__)


class NostrBridge:
    """Owns the nostr-sdk client: one connection for publish + subscribe."""

    def __init__(self, relay_url: Optional[str] = None, nsec: Optional[str] = None):
        self.relay_url = relay_url or os.getenv("RELAY_URL", "")
        self.nsec = nsec or os.getenv("HITL_HUB_NSEC", "")
        self._client = None
        self._keys = None
        self._listener_task: Optional[asyncio.Task] = None

    @property
    def enabled(self) -> bool:
        return bool(self.relay_url and self.nsec)

    @property
    def pubkey_hex(self) -> Optional[str]:
        return self._keys.public_key().to_hex() if self._keys else None

    async def start(self) -> None:
        if not self.enabled:
            logger.warning(
                "Nostr bridge disabled (RELAY_URL=%s HITL_HUB_NSEC=%s)",
                "set" if self.relay_url else "missing",
                "set" if self.nsec else "missing",
            )
            return

        from nostr_sdk import Client, Keys, NostrSigner

        self._keys = Keys.parse(self.nsec)
        self._client = Client(NostrSigner.keys(self._keys))
        await self._client.add_relay(self.relay_url)
        await self._client.connect()
        logger.info(
            "Nostr bridge connected relay=%s pubkey=%s",
            self.relay_url,
            self.pubkey_hex[:12] if self.pubkey_hex else "?",
        )

    async def stop(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001 — best-effort shutdown
                pass
            self._client = None

    # ------------------------------------------------------------------
    # Publish (kind:10020)
    # ------------------------------------------------------------------

    def _inbox_content(self, event: HITLEvent) -> str:
        """Content JSON compatible with llibreta's parseInboxContent."""
        intent = "permission"
        delivery_page = "system"
        if isinstance(event.payload, dict):
            intent = str(event.payload.get("intent") or intent)
            delivery_page = str(event.payload.get("delivery_page") or delivery_page)
        body = {
            "intent": intent,
            "delivery_page": delivery_page,
            "action": event.action,
            "hint": event.hint,
            "hub_id": event.event_id,
            "tenant_id": event.tenant_id,
            "user_id": event.user_id,
        }
        if isinstance(event.payload, dict):
            for key, value in event.payload.items():
                body.setdefault(key, value)
        return json.dumps(body, default=str, ensure_ascii=False)

    async def publish_request(self, event: HITLEvent, owner_pubkey: str) -> Optional[str]:
        """Publish a kind:10020 INBOX_ITEM for this HITL event.

        Returns the Nostr event id, or None when the bridge is disabled.
        """
        if not self._client:
            return None

        from nostr_sdk import EventBuilder, Kind, Tag

        tags = [
            Tag.parse(["p", owner_pubkey]),
            Tag.parse(["session", event.session_id or f"hitl-{event.event_id}"]),
            Tag.parse(["action", event.action or ""]),
            Tag.parse(["hint", event.hint or ""]),
            Tag.parse(["hub", event.event_id]),
        ]
        builder = EventBuilder(Kind(10020), self._inbox_content(event)).tags(tags)
        output = await self._client.send_event_builder(builder)
        nostr_event_id = output.id.to_hex()
        logger.info(
            "Published kind:10020 hitl=%s nostr=%s owner=%s",
            event.event_id,
            nostr_event_id[:12],
            owner_pubkey[:12],
        )
        return nostr_event_id

    # ------------------------------------------------------------------
    # Listen (kind:10021)
    # ------------------------------------------------------------------

    def start_resolution_listener(self, engine: "HITLEngine") -> None:
        """Spawn the background task that resolves hub rows from kind:10021."""
        if not self._client:
            return
        self._listener_task = asyncio.create_task(self._listen_loop(engine))

    async def _listen_loop(self, engine: "HITLEngine") -> None:
        from nostr_sdk import Filter, HandleNotification, Kind, Timestamp

        bridge = self

        class ResolutionHandler(HandleNotification):
            async def handle(self, relay_url, subscription_id, event):  # noqa: ANN001
                try:
                    await bridge._handle_resolution(engine, json.loads(event.as_json()))
                except Exception as exc:  # noqa: BLE001 — never kill the listener
                    logger.error("kind:10021 handler failed: %s", exc)

            async def handle_msg(self, relay_url, msg):  # noqa: ANN001
                pass

        while True:
            try:
                fltr = Filter().kind(Kind(10021)).since(Timestamp.now())
                await self._client.subscribe(fltr)
                logger.info("Listening for kind:10021 resolutions on %s", self.relay_url)
                await self._client.handle_notifications(ResolutionHandler())
            except asyncio.CancelledError:
                return
            except Exception as exc:  # noqa: BLE001
                logger.error("Resolution listener crashed, retrying in 10s: %s", exc)
                await asyncio.sleep(10)

    async def _handle_resolution(self, engine: "HITLEngine", event_json: dict) -> None:
        if event_json.get("kind") != 10021:
            return
        tags = {t[0]: t[1] for t in event_json.get("tags", []) if len(t) >= 2}
        request_id = tags.get("request")
        if not request_id:
            return

        row = await engine.repository.get_by_reference(request_id)
        if row is None:
            return  # 10021 for a request not created by the hub — not ours
        if row.status != HITLStatus.PENDING:
            return  # already resolved (or expired)

        resolver_pubkey = str(event_json.get("pubkey", ""))
        if row.owner_pubkey and resolver_pubkey != row.owner_pubkey:
            logger.warning(
                "kind:10021 for hitl=%s signed by %s but owner is %s — ignored",
                row.event_id,
                resolver_pubkey[:12],
                row.owner_pubkey[:12],
            )
            return

        approved = tags.get("approved") in ("true", "1") or event_json.get("content") == "approved"
        logger.info(
            "Resolution kind:10021 hitl=%s approved=%s resolver=%s",
            row.event_id,
            approved,
            resolver_pubkey[:12],
        )
        if approved:
            await engine.approve(row.event_id, {"resolved_via": "nostr", "resolver": resolver_pubkey})
        else:
            await engine.reject(row.event_id, reason="rejected via llibreta inbox")
