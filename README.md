# HITL Hub

> **Nodus OS** — Unified Human-In-The-Loop MCP server
>
> "Wires, Governance, UX. One call, any service, consistent cards."

## What is HITL Hub?

HITL Hub is the single MCP server that standardizes **all Human-In-The-Loop confirmations** across Nodus OS.
Any service — graph, agent, DW, script — requests a user confirmation with ONE MCP call.

## Architecture

```
MCP Interface (wires)
    ↓
Core Engine (validator → persist → notify)
    ↓
Plugin System (validators, notifications, hooks)
    ↓
Persistence (PostgreSQL)
```

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Run (needs DATABASE_URL in env)
DATABASE_URL=postgresql://nodus:nodus@localhost:5432/nodus_db python -m nodus_hitl_hub.server

# Or with uvicorn
uvicorn nodus_hitl_hub.server:app --host 0.0.0.0 --port 3000 --reload
```

## MCP Tools

| Tool | Description |
|---|---|
| `hitl.request_confirmation` | Create a HITL request |
| `hitl.wait_for_confirmation` | Block until approved/rejected |
| `hitl.check_status` | Non-blocking status check |

## MCP Resources

| Resource | Returns |
|---|---|
| `hitl://inbox/{user_id}` | All pending HITLs for a user |

## Calling from other services

### From an lg-worker graph

```json
{
  "id": "request_hitl_0",
  "type": "mcp.tool",
  "config": {
    "server": "nodus-hitl-hub",
    "tool": "hitl.request_confirmation",
    "params": {
      "action_type": "send_email",
      "action_description": "Send email to client@example.com",
      "action_details": {"to": "client@example.com"},
      "user_id": "${input.user_id}",
      "tenant_id": "${input.tenant_id}"
    }
  }
}
```

### From ADK Runtime (Python)

```python
from nodus_adk_runtime.adapters.mcp_adapter import MCPAdapter

mcp = MCPAdapter()

result = await mcp.call_tool("nodus-hitl-hub", "hitl.wait_for_confirmation", {
    "confirmation_id": await mcp.call_tool("nodus-hitl-hub", "hitl.request_confirmation", {
        "action_type": "send_email",
        "action_description": f"Send email to {recipient}",
        "user_id": get_current_user_id(),
    })["confirmation_id"]
})
```

### From any HTTP client

```bash
curl -X POST https://hitl-hub.nodus-dev:3000/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "tool": "hitl.request_confirmation",
    "params": {
      "action_type": "deploy_to_production",
      "action_description": "Deploy to production",
      "user_id": "user-123"
    }
  }'
```

## Adding a new plugin

1. Create a file in `plugins/{validators,notifications,hooks}/`
2. Implement the base class (ABC)
3. The registry auto-discovers and loads it
4. Zero changes to the core engine

### Example: add Slack notifications

```python
# plugins/notifications/slack.py
from plugins.notifications.base import NotificationPlugin

class SlackNotify(NotificationPlugin):
    async def notify(self, event):
        await slack.chat_postMessage(
            channel=event.user_slack_channel,
            text=f"HITL pending: {event.hint}"
        )
```

## Docs

- [Architecture](docs/HITL_HUB_ARCHITECTURE.md)
- [Full HITL System Redesign](https://github.com/nodus-factory/nodus-os-adk/blob/main/docs/HITL_SYSTEM_REDESIGN.md)
- [HITL Full Audit 2026](https://github.com/nodus-factory/nodus-os-adk/blob/main/docs/HITL_FULL_AUDIT_2026-07-06.md)

## License

Proprietary — Nodus Factory
