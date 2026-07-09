"""HITL Hub — FastMCP server entrypoint."""

import logging
import os

from nodus_hitl_hub.mcp.tools import register_tools
from nodus_hitl_hub.mcp.resources import register_resources
from nodus_hitl_hub.mcp.rest import register_rest_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("nodus-hitl-hub")


def create_app():
    """Create and configure the FastMCP application.

    Engine initialization (DB pool, migrations, plugins, Nostr bridge) is
    lazy and process-wide — see bootstrap.get_engine(). The previous
    lifespan-based init never ran (the MCP SDK expects an async context
    manager and got a bare async generator, crashing every session), so all
    entrypoints now call get_engine() themselves.
    """
    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP("nodus-hitl-hub")

    register_tools(mcp)
    register_resources(mcp)
    register_rest_routes(mcp)

    return mcp


# Module-level app instance (imported by uvicorn / fastmcp run)
app = create_app()


def main():
    """Entry point for development and production."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "3000"))
    app.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
