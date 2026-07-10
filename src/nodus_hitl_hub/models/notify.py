"""Pydantic models for fire-and-forget notifications."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class NotifyPriority(str, Enum):
    INFO = "info"
    NORMAL = "normal"
    URGENT = "urgent"
    CRITICAL = "critical"


PRIORITY_ORDER: dict[str, int] = {
    NotifyPriority.INFO: 0,
    NotifyPriority.NORMAL: 1,
    NotifyPriority.URGENT: 2,
    NotifyPriority.CRITICAL: 3,
}


def priority_gte(actual: NotifyPriority | str, minimum: str) -> bool:
    """True when actual priority is at or above minimum."""
    a = actual.value if isinstance(actual, NotifyPriority) else actual
    return PRIORITY_ORDER.get(a, 1) >= PRIORITY_ORDER.get(minimum, 1)


class NotifyRequest(BaseModel):
    """Incoming notification request."""

    user_id: str
    title: str
    body: str
    priority: NotifyPriority = NotifyPriority.NORMAL
    url: Optional[str] = None
    tenant_id: str = "default"
    channels: Optional[list[str]] = None
    metadata: dict = Field(default_factory=dict)


class NotifyResult(BaseModel):
    """Result of a notification dispatch."""

    notification_id: str
    channels_attempted: list[str]
    channels_succeeded: list[str]
    channels_failed: list[str]
