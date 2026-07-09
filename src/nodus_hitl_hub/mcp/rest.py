"""Plain HTTP routes for machine-to-machine producers (no MCP client needed).

TypeScript services like Memorium create HITL requests with a single POST
instead of speaking the MCP protocol. Auth is an optional shared bearer token
(HITL_HUB_SERVICE_TOKEN); when unset, in-cluster calls are trusted.
"""

import logging
import os

from starlette.requests import Request
from starlette.responses import JSONResponse

from nodus_hitl_hub.bootstrap import get_engine
from nodus_hitl_hub.models.hitl import HITLRequest

logger = logging.getLogger(__name__)


def _unauthorized(request: Request) -> bool:
    token = os.getenv("HITL_HUB_SERVICE_TOKEN", "")
    if not token:
        return False
    return request.headers.get("authorization", "") != f"Bearer {token}"


def register_rest_routes(mcp) -> None:
    """Register REST endpoints on the FastMCP Starlette app."""

    @mcp.custom_route("/health", methods=["GET"])
    async def health(request: Request) -> JSONResponse:
        # Probe also warms up the engine (DB pool, migrations, Nostr bridge).
        try:
            await get_engine()
            return JSONResponse({"status": "ok"})
        except Exception as exc:  # noqa: BLE001
            logger.error("Health check init failed: %s", exc)
            return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)

    @mcp.custom_route("/hitl/requests", methods=["POST"])
    async def create_request(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        engine = await get_engine()

        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"error": "invalid_json"}, status_code=400)

        try:
            req = HITLRequest(
                action_type=str(body["action_type"]),
                action_description=str(body["action_description"]),
                action_details=body.get("action_details") or {},
                user_id=str(body["user_id"]),
                tenant_id=str(body.get("tenant_id") or "default"),
                timeout_seconds=int(body.get("timeout_seconds") or 300),
                metadata=body.get("metadata") or {},
            )
        except (KeyError, TypeError, ValueError) as exc:
            return JSONResponse({"error": f"invalid_body: {exc}"}, status_code=400)

        result = await engine.request(req)
        status_code = 400 if result.status == "error" else 201
        return JSONResponse(result.model_dump(mode="json"), status_code=status_code)

    @mcp.custom_route("/hitl/requests/{confirmation_id}", methods=["GET"])
    async def get_request(request: Request) -> JSONResponse:
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        engine = await get_engine()
        result = await engine.check(request.path_params["confirmation_id"])
        return JSONResponse(result.model_dump(mode="json"))

    @mcp.custom_route("/hitl/requests/{confirmation_id}/resolve", methods=["POST"])
    async def resolve_request(request: Request) -> JSONResponse:
        """Manual resolution path (admin/testing) — the normal path is kind:10021."""
        if _unauthorized(request):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        engine = await get_engine()

        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            return JSONResponse({"error": "invalid_json"}, status_code=400)

        confirmation_id = request.path_params["confirmation_id"]
        if body.get("approved") is True:
            result = await engine.approve(confirmation_id, body.get("response"))
        else:
            result = await engine.reject(confirmation_id, body.get("reason"))
        status_code = 400 if result.status == "error" else 200
        return JSONResponse(result.model_dump(mode="json"), status_code=status_code)

    logger.info("REST routes registered: /health, /hitl/requests[...]")
