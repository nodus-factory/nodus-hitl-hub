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

from nodus_hitl_hub.core.dispatcher import DispatcherRegistry
from nodus_hitl_hub.core.engine import HITLEngine
from nodus_hitl_hub.core.lifecycle import LifecycleManager
from nodus_hitl_hub.core.nostr_bridge import NostrBridge
from nodus_hitl_hub.core.repository import Repository
from nodus_hitl_hub.core.validator import ValidatorRegistry
from nodus_hitl_hub.db.queries import create_pool, run_migrations

logger = logging.getLogger(__name__)

_engine: HITLEngine | None = None
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

        dsn = os.getenv("DATABASE_URL", "postgresql://nodus:nodus@localhost:5432/nodus_db")
        pool = await create_pool(dsn)
        migrations_dir = os.path.join(os.path.dirname(__file__), "db", "migrations")
        await run_migrations(pool, migrations_dir)
        repository = Repository(pool)

        validators = ValidatorRegistry()
        lifecycle = LifecycleManager()
        dispatcher = DispatcherRegistry()
        logger.info(
            "Plugins loaded: %d validators, %d hooks, %d notifiers",
            validators.count,
            lifecycle.count,
            dispatcher.count,
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
        logger.info("HITL Hub engine ready")
        return _engine


def is_initialized() -> bool:
    return _engine is not None
