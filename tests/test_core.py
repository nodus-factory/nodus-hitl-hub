"""Tests for HITL Hub core engine."""

import pytest
from datetime import datetime, timedelta

from nodus_hitl_hub.models.hitl import HITLRequest, HITLResponse, HITLStatus
from nodus_hitl_hub.models.events import HITLEvent


class TestHITLRequest:
    """Test HITLRequest model."""

    def test_request_creation(self):
        req = HITLRequest(
            action_type="send_email",
            action_description="Send email to test@example.com",
            action_details={"to": "test@example.com", "subject": "Test"},
            user_id="user-123",
            tenant_id="test",
            timeout_seconds=300,
        )
        assert req.action_type == "send_email"
        assert req.timeout_seconds == 300
        assert req.tenant_id == "test"

    def test_request_defaults(self):
        req = HITLRequest(
            action_type="deploy_sensor",
            action_description="Deploy gmail sensor",
            action_details={"sensor": "gmail"},
            user_id="user-456",
        )
        assert req.tenant_id == "default"
        assert req.timeout_seconds == 300
        assert req.metadata == {}


class TestHITLEvent:
    """Test HITLEvent model."""

    def test_from_request(self):
        req = HITLRequest(
            action_type="send_email",
            action_description="Send email to admin@example.com",
            action_details={"to": "admin@example.com"},
            user_id="user-789",
            tenant_id="nodus",
            timeout_seconds=600,
            metadata={"session_id": "sess-abc", "dw_pubkey": "abc123"},
        )
        event = HITLEvent.from_request(req)

        assert event.user_id == "user-789"
        assert event.tenant_id == "nodus"
        assert event.action == "send_email"
        assert event.hint == "Send email to admin@example.com"
        assert event.payload == {"to": "admin@example.com"}
        assert event.session_id == "sess-abc"
        assert event.dw_pubkey == "abc123"
        assert event.status == HITLStatus.PENDING
        assert event.event_id.startswith("hitl_")
        assert event.expires_at is not None
        assert event.expires_at > datetime.utcnow()

    def test_event_defaults(self):
        event = HITLEvent(
            user_id="user-001",
            action="test_action",
            hint="Test action",
        )
        assert event.event_id.startswith("hitl_")
        assert event.kind == 10020
        assert event.pubkey == "hitl-hub"
        assert event.status == HITLStatus.PENDING
        assert event.verified is False
        assert event.tenant_id == "default"


class TestHITLResponse:
    """Test HITLResponse model."""

    def test_pending_response(self):
        resp = HITLResponse(
            confirmation_id="hitl_abc123",
            status=HITLStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(seconds=300),
        )
        assert resp.status == HITLStatus.PENDING
        assert resp.confirmation_id == "hitl_abc123"
        assert resp.error is None

    def test_error_response(self):
        resp = HITLResponse(
            confirmation_id=None,
            status=HITLStatus.ERROR,
            error="Validation failed: action_type is required",
        )
        assert resp.status == HITLStatus.ERROR
        assert resp.confirmation_id is None
        assert "Validation failed" in resp.error
