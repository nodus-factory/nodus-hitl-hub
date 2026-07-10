"""Base class for outbound notification channel adapters."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nodus_hitl_hub.models.notify import NotifyRequest


class ChannelAdapter(ABC):
    """Sends a NotifyRequest to an external delivery channel."""

    name: str

    @abstractmethod
    async def send(self, req: "NotifyRequest") -> bool:
        """Deliver the notification. Returns True on success."""
        ...
