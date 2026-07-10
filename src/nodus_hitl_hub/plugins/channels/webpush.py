"""Web push delivery via llibreta-v2 internal push endpoint."""

import logging
import os

import httpx

from nodus_hitl_hub.models.notify import NotifyRequest
from nodus_hitl_hub.plugins.channels.base import ChannelAdapter

logger = logging.getLogger(__name__)


class WebPushAdapter(ChannelAdapter):
    """POST to llibreta-v2 /internal/push/send."""

    name = "webpush"

    def __init__(self) -> None:
        self._base_url = os.getenv("LLIBRETA_URL", "http://llibreta-v2-app:5002").rstrip("/")
        self._token = os.getenv("INTERNAL_PUSH_TOKEN", "")

    async def send(self, req: NotifyRequest) -> bool:
        if not self._token:
            logger.warning("webpush skipped: INTERNAL_PUSH_TOKEN not configured")
            return False

        payload = {
            "user_id": req.user_id,
            "title": req.title,
            "body": req.body,
        }
        if req.url:
            payload["url"] = req.url
        tag = req.metadata.get("tag")
        if tag:
            payload["tag"] = tag

        url = f"{self._base_url}/internal/push/send"
        headers = {"X-Internal-Token": self._token}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if 200 <= resp.status_code < 300:
                    return True
                logger.warning("webpush failed: status=%s body=%s", resp.status_code, resp.text[:200])
                return False
        except Exception as e:
            logger.error("webpush error: %s", e)
            return False
