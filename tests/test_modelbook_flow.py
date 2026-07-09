"""Tests for the Model Book conflict flow: validator, dedup, resolution, hook."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nodus_hitl_hub.core.dispatcher import DispatcherRegistry
from nodus_hitl_hub.core.engine import HITLEngine
from nodus_hitl_hub.core.lifecycle import LifecycleManager
from nodus_hitl_hub.core.nostr_bridge import NostrBridge
from nodus_hitl_hub.core.validator import ValidatorRegistry
from nodus_hitl_hub.models.events import HITLEvent
from nodus_hitl_hub.models.hitl import HITLRequest, HITLStatus
from nodus_hitl_hub.plugins.hooks.modelbook import ModelBookHook
from nodus_hitl_hub.plugins.validators.modelbook_conflict import ModelBookConflictValidator


def make_repository() -> MagicMock:
    repo = MagicMock()
    repo.insert = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.get_by_idempotency_key = AsyncMock(return_value=None)
    repo.get_by_reference = AsyncMock(return_value=None)
    repo.set_reference = AsyncMock()
    repo.get_user_pubkey = AsyncMock(return_value="a" * 64)
    repo.update_status = AsyncMock()
    return repo


def make_engine(repo=None, bridge=None) -> HITLEngine:
    return HITLEngine(
        repository=repo or make_repository(),
        validators=ValidatorRegistry(),
        lifecycle=LifecycleManager(),
        dispatcher=DispatcherRegistry(),
        nostr_bridge=bridge,
    )


def conflict_request(**overrides) -> HITLRequest:
    details = {
        "proposal_id": "11111111-2222-3333-4444-555555555555",
        "tenant_id": "nodus",
        "region_id": "tenant:nodus:domain:crm",
        "facet": "fact",
        "claim_key": "parlem-status",
        "proposed_value": {"summary": "Parlem passa a client actiu"},
        "current_value": {"summary": "Parlem en negociació"},
    }
    details.update(overrides.pop("action_details", {}))
    base = dict(
        action_type="modelbook_conflict",
        action_description="Conflicte al Model Book: parlem-status",
        action_details=details,
        user_id="4",
        tenant_id="nodus",
        timeout_seconds=604800,
        metadata={"idempotency_key": "modelbook:nodus:11111111-2222-3333-4444-555555555555"},
    )
    base.update(overrides)
    return HITLRequest(**base)


class TestValidatorRegistry:
    def test_specific_validator_wins_over_default_fallback(self):
        registry = ValidatorRegistry()
        validator = registry.get_validator("modelbook_conflict")
        assert isinstance(validator, ModelBookConflictValidator)

    def test_default_still_catches_unknown_actions(self):
        registry = ValidatorRegistry()
        validator = registry.get_validator("something_unknown")
        assert validator is not None
        assert validator.is_fallback


class TestModelBookConflictValidator:
    @pytest.mark.asyncio
    async def test_valid_payload(self):
        v = ModelBookConflictValidator()
        errors = await v.validate("modelbook_conflict", conflict_request().action_details)
        assert errors == []

    @pytest.mark.asyncio
    async def test_missing_fields(self):
        v = ModelBookConflictValidator()
        errors = await v.validate("modelbook_conflict", {})
        assert any("proposal_id" in e for e in errors)
        assert any("tenant_id" in e for e in errors)
        assert any("claim_key" in e for e in errors)


class TestEngineRequestFlow:
    @pytest.mark.asyncio
    async def test_request_persists_and_publishes(self):
        repo = make_repository()
        bridge = MagicMock(spec=NostrBridge)
        bridge.enabled = True
        bridge.relay_url = "ws://relay"
        bridge.publish_request = AsyncMock(return_value="f" * 64)
        engine = make_engine(repo, bridge)

        result = await engine.request(conflict_request())

        assert result.status == HITLStatus.PENDING
        repo.insert.assert_awaited_once()
        inserted: HITLEvent = repo.insert.await_args.args[0]
        assert inserted.kind == 10020
        assert inserted.owner_pubkey == "a" * 64
        assert inserted.idempotency_key.startswith("modelbook:nodus:")
        bridge.publish_request.assert_awaited_once()
        repo.set_reference.assert_awaited_once_with(inserted.event_id, "f" * 64, "ws://relay")

    @pytest.mark.asyncio
    async def test_request_dedupes_on_idempotency_key(self):
        repo = make_repository()
        existing = HITLEvent(user_id="4", action="modelbook_conflict", hint="dup")
        repo.get_by_idempotency_key = AsyncMock(return_value=existing)
        engine = make_engine(repo)

        result = await engine.request(conflict_request())

        assert result.confirmation_id == existing.event_id
        repo.insert.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_request_survives_publish_failure(self):
        repo = make_repository()
        bridge = MagicMock(spec=NostrBridge)
        bridge.enabled = True
        bridge.relay_url = "ws://relay"
        bridge.publish_request = AsyncMock(side_effect=RuntimeError("relay down"))
        engine = make_engine(repo, bridge)

        result = await engine.request(conflict_request())

        assert result.status == HITLStatus.PENDING
        repo.insert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_invalid_conflict_payload_rejected(self):
        engine = make_engine()
        result = await engine.request(conflict_request(action_details={"proposal_id": ""}))
        assert result.status == HITLStatus.ERROR
        assert "proposal_id" in result.error


class TestResolutionListener:
    def make_row(self, owner: str = "b" * 64) -> HITLEvent:
        return HITLEvent(
            event_id="hitl_row1",
            user_id="4",
            action="modelbook_conflict",
            hint="conflicte",
            owner_pubkey=owner,
            reference_id="e" * 64,
            status=HITLStatus.PENDING,
        )

    def make_resolution(self, approved: bool, pubkey: str = "b" * 64) -> dict:
        return {
            "kind": 10021,
            "pubkey": pubkey,
            "content": "approved" if approved else "rejected",
            "tags": [["request", "e" * 64], ["approved", "true" if approved else "false"]],
        }

    @pytest.mark.asyncio
    async def test_approval_drives_engine_approve(self):
        engine = MagicMock()
        engine.repository.get_by_reference = AsyncMock(return_value=self.make_row())
        engine.approve = AsyncMock()
        engine.reject = AsyncMock()

        bridge = NostrBridge(relay_url="ws://x", nsec="")
        await bridge._handle_resolution(engine, self.make_resolution(approved=True))

        engine.approve.assert_awaited_once()
        engine.reject.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejection_drives_engine_reject(self):
        engine = MagicMock()
        engine.repository.get_by_reference = AsyncMock(return_value=self.make_row())
        engine.approve = AsyncMock()
        engine.reject = AsyncMock()

        bridge = NostrBridge(relay_url="ws://x", nsec="")
        await bridge._handle_resolution(engine, self.make_resolution(approved=False))

        engine.reject.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_wrong_signer_is_ignored(self):
        engine = MagicMock()
        engine.repository.get_by_reference = AsyncMock(return_value=self.make_row(owner="c" * 64))
        engine.approve = AsyncMock()
        engine.reject = AsyncMock()

        bridge = NostrBridge(relay_url="ws://x", nsec="")
        await bridge._handle_resolution(engine, self.make_resolution(approved=True, pubkey="d" * 64))

        engine.approve.assert_not_awaited()
        engine.reject.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_request_is_ignored(self):
        engine = MagicMock()
        engine.repository.get_by_reference = AsyncMock(return_value=None)
        engine.approve = AsyncMock()

        bridge = NostrBridge(relay_url="ws://x", nsec="")
        await bridge._handle_resolution(engine, self.make_resolution(approved=True))

        engine.approve.assert_not_awaited()


class TestModelBookHook:
    def make_event(self) -> HITLEvent:
        return HITLEvent(
            event_id="hitl_hook1",
            user_id="4",
            tenant_id="nodus",
            action="modelbook_conflict",
            hint="conflicte",
            payload={"proposal_id": "prop-1", "tenant_id": "nodus"},
        )

    @pytest.mark.asyncio
    async def test_approved_calls_memorium(self):
        hook = ModelBookHook()
        response = MagicMock(status_code=200)
        response.json.return_value = {"version_num": 84}
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        client.post = AsyncMock(return_value=response)

        with patch.dict("os.environ", {"MEMORIUM_URL": "http://memorium:8082"}), patch(
            "httpx.AsyncClient", return_value=client
        ):
            await hook.on_approved(self.make_event())

        client.post.assert_awaited_once()
        url = client.post.await_args.args[0]
        body = client.post.await_args.kwargs["json"]
        assert url == "http://memorium:8082/modelbook/proposals/resolve-conflict"
        assert body == {
            "tenant_id": "nodus",
            "proposal_id": "prop-1",
            "approved": True,
            "reviewer": "hitl:4",
        }

    @pytest.mark.asyncio
    async def test_other_actions_are_ignored(self):
        hook = ModelBookHook()
        event = self.make_event()
        event.action = "send_email"
        with patch("httpx.AsyncClient") as client_cls:
            await hook.on_approved(event)
        client_cls.assert_not_called()


class TestInboxContent:
    def test_content_is_llibreta_compatible(self):
        bridge = NostrBridge(relay_url="", nsec="")
        event = HITLEvent(
            user_id="4",
            tenant_id="nodus",
            action="modelbook_conflict",
            hint="Conflicte: parlem-status",
            payload={"proposal_id": "p1", "claim_key": "parlem-status"},
        )
        content = json.loads(bridge._inbox_content(event))
        assert content["intent"] == "permission"
        assert content["delivery_page"] == "system"
        assert content["action"] == "modelbook_conflict"
        assert content["proposal_id"] == "p1"
