"""WhatsApp delivery adapter.

Backoffice currently exposes only an inbound webhook at POST /api/whatsapp/webhook
and uses sendWhatsAppMessage() internally — there is no service-to-service
/internal/whatsapp send endpoint yet.

This adapter calls BACKOFFICE_WHATSAPP_SEND_URL when set (expected future contract:
POST JSON { to, body } with Authorization: Bearer BACKOFFICE_SERVICE_TOKEN).
Until that endpoint exists in backoffice, configure the URL or expect failures.
"""

import logging
import os

import httpx

from nodus_hitl_hub.models.notify import NotifyRequest
from nodus_hitl_hub.plugins.channels.base import ChannelAdapter

logger = logging.getLogger(__name__)


class WhatsAppAdapter(ChannelAdapter):
    """Pending backoffice-side outbound WhatsApp internal endpoint."""

    name = "whatsapp"

    def __init__(self) -> None:
        default_url = os.getenv("BACKOFFICE_URL", "http://backoffice:5001").rstrip("/")
        self._send_url = os.getenv("BACKOFFICE_WHATSAPP_SEND_URL", f"{default_url}/internal/whatsapp").rstrip("/")
        self._service_token = os.getenv("BACKOFFICE_SERVICE_TOKEN", "")

    async def send(self, req: NotifyRequest) -> bool:
        to = req.metadata.get("address")
        if not to:
            logger.warning("whatsapp skipped: no address in metadata")
            return False

        if not self._service_token:
            logger.warning("whatsapp skipped: BACKOFFICE_SERVICE_TOKEN not configured")
            return False

        payload = {"to": to, "body": req.body}
        if req.title:
            payload["body"] = f"*{req.title}*\n{req.body}"

        headers = {"Authorization": f"Bearer {self._service_token}"}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(self._send_url, json=payload, headers=headers)
                if 200 <= resp.status_code < 300:
                    return True
                logger.warning(
                    "whatsapp failed (endpoint may not exist yet): status=%s url=%s body=%s",
                    resp.status_code,
                    self._send_url,
                    resp.text[:200],
                )
                return False
        except Exception as e:
            logger.error("whatsapp error: %s", e)
            return False
