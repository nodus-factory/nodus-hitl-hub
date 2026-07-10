"""Tests for NotifyEngine routing logic."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from nodus_hitl_hub.core.channels import ChannelRegistry
from nodus_hitl_hub.core.notify_engine import NotifyEngine
from nodus_hitl_hub.core.notify_repository import NotificationPreference
from nodus_hitl_hub.models.notify import NotifyPriority, NotifyRequest, priority_gte
from nodus_hitl_hub.plugins.channels.base import ChannelAdapter


class FakeAdapter(ChannelAdapter):
    def __init__(self, name: str, succeed: bool = True):
        self.name = name
        self.succeed = succeed
        self.calls: list[NotifyRequest] = []

    async def send(self, req: NotifyRequest) -> bool:
        self.calls.append(req)
        return self.succeed


def make_registry(*adapters: ChannelAdapter) -> ChannelRegistry:
    reg = ChannelRegistry.__new__(ChannelRegistry)
    reg._adapters = {a.name: a for a in adapters}
    return reg


def make_repo(preferences: list[NotificationPreference] | None = None) -> MagicMock:
    repo = MagicMock()
    repo.get_preferences = AsyncMock(return_value=preferences or [])
    repo.insert_log = AsyncMock()
    repo.mark_acked = AsyncMock(return_value=True)
    repo.list_history = AsyncMock(return_value=[])
    return repo


def pref(
    channel: str,
    *,
    enabled: bool = True,
    min_priority: str = "normal",
    address: str | None = None,
    quiet_start: int | None = None,
    quiet_end: int | None = None,
) -> NotificationPreference:
    return NotificationPreference(
        user_id="user-1",
        tenant_id="default",
        channel=channel,
        enabled=enabled,
        address=address,
        min_priority=min_priority,
        quiet_hours_start=quiet_start,
        quiet_hours_end=quiet_end,
    )


class TestPriorityGte:
    def test_ordering(self):
        assert priority_gte(NotifyPriority.CRITICAL, "normal")
        assert priority_gte(NotifyPriority.NORMAL, "normal")
        assert not priority_gte(NotifyPriority.INFO, "normal")


class TestNotifyEngineRouting:
    @pytest.mark.asyncio
    async def test_no_preferences_normal_defaults_webpush(self):
        webpush = FakeAdapter("webpush")
        engine = NotifyEngine(make_repo([]), make_registry(webpush))
        req = NotifyRequest(user_id="user-1", title="Hi", body="There", priority=NotifyPriority.NORMAL)

        result = await engine.send(req)

        assert result.channels_attempted == ["webpush"]
        assert result.channels_succeeded == ["webpush"]
        assert result.channels_failed == []
        assert len(webpush.calls) == 1

    @pytest.mark.asyncio
    async def test_no_preferences_info_logs_only(self):
        webpush = FakeAdapter("webpush")
        engine = NotifyEngine(make_repo([]), make_registry(webpush))
        req = NotifyRequest(user_id="user-1", title="Hi", body="There", priority=NotifyPriority.INFO)

        result = await engine.send(req)

        assert result.channels_attempted == []
        assert result.channels_succeeded == []
        assert len(webpush.calls) == 0

    @pytest.mark.asyncio
    async def test_preferences_filter_by_min_priority(self):
        webpush = FakeAdapter("webpush")
        prefs = [
            pref("webpush", min_priority="urgent"),
            pref("email", min_priority="normal", address="a@b.com"),
        ]
        email = FakeAdapter("email")
        engine = NotifyEngine(make_repo(prefs), make_registry(webpush, email))
        req = NotifyRequest(user_id="user-1", title="T", body="B", priority=NotifyPriority.NORMAL)

        result = await engine.send(req)

        assert "webpush" not in result.channels_attempted
        assert "email" in result.channels_attempted
        assert result.channels_succeeded == ["email"]
        assert email.calls[0].metadata["address"] == "a@b.com"

    @pytest.mark.asyncio
    async def test_explicit_channels_override(self):
        webpush = FakeAdapter("webpush")
        email = FakeAdapter("email")
        prefs = [pref("webpush"), pref("email", address="x@y.com")]
        engine = NotifyEngine(make_repo(prefs), make_registry(webpush, email))
        req = NotifyRequest(
            user_id="user-1",
            title="T",
            body="B",
            channels=["webpush"],
        )

        result = await engine.send(req)

        assert result.channels_attempted == ["webpush"]
        assert len(email.calls) == 0

    @pytest.mark.asyncio
    async def test_email_skipped_without_address(self):
        email = FakeAdapter("email")
        prefs = [pref("email", address=None)]
        engine = NotifyEngine(make_repo(prefs), make_registry(email))
        req = NotifyRequest(user_id="user-1", title="T", body="B", channels=["email"])

        result = await engine.send(req)

        assert result.channels_attempted == []
        assert len(email.calls) == 0

    @pytest.mark.asyncio
    async def test_quiet_hours_skips_unless_critical(self, monkeypatch):
        webpush = FakeAdapter("webpush")
        prefs = [pref("webpush", quiet_start=0, quiet_end=24)]
        engine = NotifyEngine(make_repo(prefs), make_registry(webpush))

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        monkeypatch.setattr("nodus_hitl_hub.core.notify_engine.datetime", FixedDatetime)

        normal = NotifyRequest(user_id="user-1", title="T", body="B", priority=NotifyPriority.NORMAL)
        result = await engine.send(normal)
        assert result.channels_attempted == []

        critical = NotifyRequest(user_id="user-1", title="T", body="B", priority=NotifyPriority.CRITICAL)
        result = await engine.send(critical)
        assert result.channels_attempted == ["webpush"]

    @pytest.mark.asyncio
    async def test_inapp_is_log_only_success(self):
        prefs = [pref("inapp", min_priority="info")]
        engine = NotifyEngine(make_repo(prefs), make_registry())
        req = NotifyRequest(user_id="user-1", title="T", body="B", priority=NotifyPriority.INFO)

        result = await engine.send(req)

        assert result.channels_attempted == ["inapp"]
        assert result.channels_succeeded == ["inapp"]

    @pytest.mark.asyncio
    async def test_adapter_failure_tracked(self):
        webpush = FakeAdapter("webpush", succeed=False)
        engine = NotifyEngine(make_repo([]), make_registry(webpush))
        req = NotifyRequest(user_id="user-1", title="T", body="B")

        result = await engine.send(req)

        assert result.channels_failed == ["webpush"]

    @pytest.mark.asyncio
    async def test_disabled_preference_skipped(self):
        webpush = FakeAdapter("webpush")
        prefs = [pref("webpush", enabled=False)]
        engine = NotifyEngine(make_repo(prefs), make_registry(webpush))
        req = NotifyRequest(user_id="user-1", title="T", body="B")

        result = await engine.send(req)

        assert result.channels_attempted == []
