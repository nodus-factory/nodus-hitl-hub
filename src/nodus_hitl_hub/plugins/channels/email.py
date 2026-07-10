"""Email delivery via backoffice internal email endpoint."""

import logging
import os

import httpx

from nodus_hitl_hub.models.notify import NotifyRequest
from nodus_hitl_hub.plugins.channels.base import ChannelAdapter

logger = logging.getLogger(__name__)


class EmailAdapter(ChannelAdapter):
    """POST to backoffice POST /internal/email (service token auth)."""

    name = "email"

    def __init__(self) -> None:
        self._base_url = os.getenv("BACKOFFICE_URL", "http://backoffice:5001").rstrip("/")
        self._service_token = os.getenv("BACKOFFICE_SERVICE_TOKEN", "")

    async def send(self, req: NotifyRequest) -> bool:
        to = req.metadata.get("address")
        if not to:
            logger.warning("email skipped: no address in metadata")
            return False

        if not self._service_token:
            logger.warning("email skipped: BACKOFFICE_SERVICE_TOKEN not configured")
            return False

        payload = {
            "to": to,
            "subject": req.title,
            "body": req.body,
        }
        url = f"{self._base_url}/internal/email"
        headers = {"Authorization": f"Bearer {self._service_token}"}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if 200 <= resp.status_code < 300:
                    data = resp.json()
                    return bool(data.get("sent", True))
                logger.warning("email failed: status=%s body=%s", resp.status_code, resp.text[:200])
                return False
        except Exception as e:
            logger.error("email error: %s", e)
            return False
