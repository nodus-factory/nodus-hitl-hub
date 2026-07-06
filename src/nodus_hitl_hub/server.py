"""HITL Hub — FastMCP server entrypoint."""

import logging
import os
import sys

from nodus_hitl_hub.core.engine import HITLEngine
from nodus_hitl_hub.core.validator import ValidatorRegistry
from nodus_hitl_hub.core.lifecycle import LifecycleManager
from nodus_hitl_hub.core.dispatcher import DispatcherRegistry
from nodus_hitl_hub.core.repository import Repository
from nodus_hitl_hub.db.queries import create_pool, close_pool, run_migrations
from nodus_hitl_hub.mcp.tools import register_tools
from nodus_hitl_hub.mcp.resources import register_resources

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nodus-hitl-hub")


def create_app():
    """Create and configure the FastMCP application."""
    from mcp.server.fastmcp import FastMCP

    async def lifespan(server):
        """Startup/shutdown lifecycle for database pool, plugin registries, and background tasks."""
        logger.info("Starting HITL Hub...")

        # Database
        dsn = os.getenv("DATABASE_URL", "postgresql://nodus:nodus@localhost:5432/nodus_db")
        pool = await create_pool(dsn)
        migrations_dir = os.path.join(os.path.dirname(__file__), "db", "migrations")
        await run_migrations(pool, migrations_dir)
        repository = Repository(pool)

        # Plugin registries (auto-discover from plugins/ directories)
        validators = ValidatorRegistry()
        lifecycle = LifecycleManager()
        dispatcher = DispatcherRegistry()

        logger.info(
            "Plugins loaded: %d validators, %d hooks, %d notifiers",
            validators.count,
            lifecycle.count,
            dispatcher.count,
        )

        # Engine
        engine = HITLEngine(
            repository=repository,
            validators=validators,
            lifecycle=lifecycle,
            dispatcher=dispatcher,
        )

        # MCP tools and resources
        register_tools(server, engine)
        register_resources(server, engine)

        # Background tasks
        from nodus_hitl_hub.plugins.hooks.expiry import ExpiryHook

        expiry = ExpiryHook(repository=repository)
        expiry.start()

        # Store engine reference for health checks
        server._hitl_engine = engine

        logger.info("HITL Hub started")
        yield

        logger.info("Shutting down HITL Hub...")
        expiry.stop()
        await close_pool()
        logger.info("HITL Hub stopped")

    mcp = FastMCP("nodus-hitl-hub", lifespan=lifespan)

    return mcp


# Module-level app instance (imported by uvicorn)
app = create_app()


def main():
    """Entry point for development and production."""
    import os

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "3000"))
    app.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
