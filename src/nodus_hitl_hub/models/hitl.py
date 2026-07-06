"""Pydantic models for HITL requests and responses."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class HITLStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    TIMEOUT = "timeout"
    ERROR = "error"


class HITLRequest(BaseModel):
    """Incoming HITL request from any service."""

    action_type: str = Field(..., description="Type of action: send_email, deploy_sensor, start_recording, etc.")
    action_description: str = Field(..., description="Human-readable description for the user")
    action_details: dict = Field(default_factory=dict, description="Structured payload with action-specific fields")
    user_id: str = Field(..., description="User ID who must approve")
    tenant_id: str = Field(default="default", description="Tenant ID")
    timeout_seconds: int = Field(default=300, description="Timeout in seconds (default 5 min)")
    metadata: dict = Field(default_factory=dict, description="Extra metadata: session_id, dw_pubkey, tags, etc.")


class HITLResponse(BaseModel):
    """Response from the HITL Hub."""

    confirmation_id: Optional[str] = Field(default=None, description="Confirmation event ID")
    status: HITLStatus = Field(..., description="Current status")
    expires_at: Optional[datetime] = Field(default=None, description="Expiration timestamp")
    response: Optional[dict] = Field(default=None, description="Response payload (if approved/rejected)")
    confirmed_at: Optional[datetime] = Field(default=None, description="When the user responded")
    error: Optional[str] = Field(default=None, description="Error message (if status=error/timeout)")
