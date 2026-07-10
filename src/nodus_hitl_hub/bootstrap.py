"""Process-level initialization of the HITL engine.

The MCP SDK runs the FastMCP lifespan once per MCP *session*, which is the
wrong scope for a DB pool, the Nostr bridge and background tasks (and the
previous lifespan-based init crashed: the generator was never wrapped as an
async context manager, so the hub ran uninitialized). Instead we lazily build
one engine per process, on first use, from any entrypoint (MCP tool, REST
route, health probe).
"""

import asyncio
import logging
import os

from nodus_hitl_hub.core.channels import ChannelRegistry
from nodus_hitl_hub.core.dispatcher import DispatcherRegistry
from nodus_hitl_hub.core.engine import HITLEngine
from nodus_hitl_hub.core.lifecycle import LifecycleManager
from nodus_hitl_hub.core.notify_engine import NotifyEngine
from nodus_hitl_hub.core.notify_repository import NotifyRepository
from nodus_hitl_hub.core.nostr_bridge import NostrBridge
from nodus_hitl_hub.core.repository import Repository
from nodus_hitl_hub.core.validator import ValidatorRegistry
from nodus_hitl_hub.db.queries import create_pool, run_migrations

logger = logging.getLogger(__name__)

_engine: HITLEngine | None = None
_notify_engine: NotifyEngine | None = None
_pool = None
_lock = asyncio.Lock()


async def get_engine() -> HITLEngine:
    """Return the process-wide engine, initializing it on first call."""
    global _engine
    if _engine is not None:
        return _engine

    async with _lock:
        if _engine is not None:
            return _engine

        logger.info("Initializing HITL Hub engine...")

        global _pool

        dsn = os.getenv("DATABASE_URL", "postgresql://nodus:nodus@localhost:5432/nodus_db")
        pool = await create_pool(dsn)
        _pool = pool
        migrations_dir = os.path.join(os.path.dirname(__file__), "db", "migrations")
        await run_migrations(pool, migrations_dir)
        repository = Repository(pool)
        notify_repository = NotifyRepository(pool)

        validators = ValidatorRegistry()
        lifecycle = LifecycleManager()
        dispatcher = DispatcherRegistry()
        channel_registry = ChannelRegistry()
        logger.info(
            "Plugins loaded: %d validators, %d hooks, %d notifiers, %d notify channels",
            validators.count,
            lifecycle.count,
            dispatcher.count,
            channel_registry.count,
        )

        bridge = NostrBridge()
        try:
            await bridge.start()
        except Exception as e:  # noqa: BLE001 — hub works without Nostr (DB-only)
            logger.error("Nostr bridge failed to start (continuing without it): %s", e)

        engine = HITLEngine(
            repository=repository,
            validators=validators,
            lifecycle=lifecycle,
            dispatcher=dispatcher,
            nostr_bridge=bridge,
        )

        # Background tasks
        from nodus_hitl_hub.plugins.hooks.expiry import ExpiryHook

        expiry = ExpiryHook(repository=repository)
        expiry.start()
        bridge.start_resolution_listener(engine)

        _engine = engine

        global _notify_engine
        _notify_engine = NotifyEngine(repository=notify_repository, channels=channel_registry)
        logger.info("HITL Hub engine ready (notify channels: %s)", channel_registry.names)
        return _engine


async def get_notify_engine() -> NotifyEngine:
    """Return the process-wide NotifyEngine, initializing the hub on first call."""
    global _notify_engine
    if _notify_engine is not None:
        return _notify_engine
    await get_engine()
    if _notify_engine is None:
        raise RuntimeError("NotifyEngine failed to initialize")
    return _notify_engine


def is_initialized() -> bool:
    return _engine is not None
