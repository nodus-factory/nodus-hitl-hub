"""Event models for audit trail and persistence."""

import uuid
from datetime import datetime, timedelta
from typing import Optional

from pydantic import BaseModel, Field

from nodus_hitl_hub.models.hitl import HITLRequest, HITLStatus


class HITLEvent(BaseModel):
    """Full HITL event as stored in PostgreSQL."""

    event_id: str = Field(default_factory=lambda: f"hitl_{uuid.uuid4().hex[:12]}")
    kind: int = Field(default=10003, description="Nostr kind (10003 = HITL_REQUEST)")
    pubkey: str = Field(default="hitl-hub", description="Publisher pubkey")
    session_id: Optional[str] = None
    reference_id: Optional[str] = None
    dw_pubkey: Optional[str] = None
    owner_pubkey: Optional[str] = None
    user_id: str
    content: Optional[str] = None
    hint: Optional[str] = None
    action: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    tags: list = Field(default_factory=list)
    status: HITLStatus = Field(default=HITLStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    sig: Optional[str] = None
    verified: bool = False
    relay_url: Optional[str] = None
    tenant_id: Optional[str] = "default"

    @classmethod
    def from_request(cls, req: HITLRequest) -> "HITLEvent":
        """Create a HITLEvent from an incoming HITLRequest."""
        return cls(
            user_id=req.user_id,
            tenant_id=req.tenant_id,
            action=req.action_type,
            hint=req.action_description,
            payload=req.action_details,
            session_id=req.metadata.get("session_id"),
            dw_pubkey=req.metadata.get("dw_pubkey"),
            owner_pubkey=req.metadata.get("owner_pubkey"),
            tags=req.metadata.get("tags", []),
            expires_at=datetime.utcnow() + timedelta(seconds=req.timeout_seconds),
        )
