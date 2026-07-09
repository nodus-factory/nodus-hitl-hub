"""Model Book side-effect hook: resolve compiler conflicts in Memorium.

When a modelbook_conflict HITL is approved or rejected, this hook calls
Memorium's resolve-conflict endpoint, which (on approve) rebases the proposal
onto the latest version, commits it as a new hitl/vN version and publishes the
signed state root (kind:34009).
"""

import logging
import os

import httpx

from nodus_hitl_hub.core.lifecycle import LifecycleHook
from nodus_hitl_hub.models.events import HITLEvent

logger = logging.getLogger(__name__)

ACTION_TYPE = "modelbook_conflict"


class ModelBookHook(LifecycleHook):
    """Executes the Memorium side-effect when a modelbook_conflict resolves."""

    async def on_created(self, event: HITLEvent) -> None:
        pass

    async def on_approved(self, event: HITLEvent) -> None:
        await self._resolve(event, approved=True)

    async def on_rejected(self, event: HITLEvent) -> None:
        await self._resolve(event, approved=False)

    async def on_expired(self, event: HITLEvent) -> None:
        pass  # expired conflicts stay pending in Memorium; re-notified if still relevant

    async def _resolve(self, event: HITLEvent, approved: bool) -> None:
        if event.action != ACTION_TYPE:
            return

        memorium_url = os.getenv("MEMORIUM_URL", "").rstrip("/")
        if not memorium_url:
            logger.error("MEMORIUM_URL not set — cannot resolve modelbook conflict %s", event.event_id)
            return

        proposal_id = (event.payload or {}).get("proposal_id")
        tenant_id = (event.payload or {}).get("tenant_id") or event.tenant_id or "nodus"
        if not proposal_id:
            logger.error("modelbook_conflict %s has no proposal_id in payload", event.event_id)
            return

        body = {
            "tenant_id": tenant_id,
            "proposal_id": proposal_id,
            "approved": approved,
            "reviewer": f"hitl:{event.user_id or 'unknown'}",
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                res = await client.post(f"{memorium_url}/modelbook/proposals/resolve-conflict", json=body)
            if res.status_code >= 400:
                logger.error(
                    "Memorium resolve-conflict failed for %s: HTTP %d %s",
                    event.event_id,
                    res.status_code,
                    res.text[:300],
                )
                return
            data = res.json()
            logger.info(
                "Model Book conflict resolved hitl=%s proposal=%s approved=%s version=%s",
                event.event_id,
                proposal_id,
                approved,
                data.get("version_num"),
            )
        except Exception as exc:  # noqa: BLE001 — hook must not break other hooks
            logger.error("Memorium resolve-conflict call failed for %s: %s", event.event_id, exc)
