# HITL Hub — Architecture

> Peça core del sistema HITL de Nodus OS · 2026-07-06
> Dissenyat per evolució: "Plugins, no patches"

---

## 1. Visió

**HITL Hub** és el servidor MCP que unifica tots els mecanismes HITL de Nodus OS.
Qualsevol servei (graph, agent, DW, script) demana un HITL amb una sola crida MCP.
Qualsevol funcionalitat nova s'afegeix com un plugin, sense tocar el core.

### Principis

- **Additiu**: conviu amb el legacy, no el substitueix de cop
- **Extensible**: plugins per validació, notificació i hooks de lifecycle
- **Traçable**: cada event té signatura Nostr, audit chain completa
- **Un sol source of truth**: taula `nostr_hitl` PostgreSQL

---

## 2. Arquitectura en capes

```
┌──────────────────────────────────────────────────────────────────┐
│                         HITL HUB                                  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                   MCP INTERFACE (wires)                      │ │
│  │  hitl.request | hitl.wait | hitl.check | hitl://inbox/{uid}  │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                              │                                    │
│  ┌──────────────────────────▼──────────────────────────────────┐ │
│  │                   CORE ENGINE                                │ │
│  │                                                              │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │ │
│  │  │  Validator   │  │  Lifecycle   │  │  Dispatcher  │      │ │
│  │  │  Registry    │  │  Manager     │  │  Registry    │      │ │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │ │
│  │         │                 │                 │               │ │
│  │  ┌──────▼─────────────────▼─────────────────▼───────────┐  │ │
│  │  │                 PLUGIN SYSTEM                         │  │ │
│  │  │  ValidatorPlugin  │  NotificationPlugin  │  HookPlugin │  │ │
│  │  └──────────────────────────────────────────────────────┘  │ │
│  └──────────────────────────┬──────────────────────────────────┘ │
│                              │                                    │
│  ┌──────────────────────────▼──────────────────────────────────┐ │
│  │                   PERSISTENCE LAYER                          │ │
│  │  Repository (PostgreSQL) │ Event Store │ Cache (Redis)       │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Capa MCP (Wires)

### Tools

| Tool | Input | Output | Bloqueja? |
|---|---|---|---|
| `hitl.request_confirmation` | action_type, action_description, action_details, user_id, tenant_id, timeout_seconds, metadata | confirmation_id, status, expires_at | No |
| `hitl.wait_for_confirmation` | confirmation_id, poll_interval_seconds, max_wait_seconds | status, response, confirmed_at | Sí (polla fins resolved) |
| `hitl.check_status` | confirmation_id | status, response | No |

### Resources

| Resource | Retorna |
|---|---|
| `hitl://inbox/{user_id}` | Tots els HITL pendents per l'usuari, agrupats per kind |

---

## 4. Core Engine

### 4.1 Validator Registry

Cada `action_type` té un validador que comprova la forma del `action_details`.

```python
class ValidatorPlugin(ABC):
    @abstractmethod
    def accepts(self, action_type: str) -> bool: ...
    @abstractmethod
    async def validate(self, action_type: str, payload: dict) -> list[str]: ...
```

**Validators inclosos:**

| Validator | action_type |
|---|---|
| `RecordingValidator` | `start_recording` |
| `SensorDeployValidator` | `deploy_sensor` |
| `EmailValidator` | `send_email` |
| `CalendarValidator` | `create_calendar_event`, `update_calendar_event`, `delete_calendar_event` |
| `DefaultValidator` | Qualsevol (fallback) |

### 4.2 Lifecycle Manager

Gestiona les transicions d'estat: `pending → approved | rejected | expired`.

Executa hooks en cada transició:

```python
class LifecycleHook(ABC):
    @abstractmethod
    async def on_created(self, event: HITLEvent) -> None: ...
    @abstractmethod
    async def on_approved(self, event: HITLEvent) -> None: ...
    @abstractmethod
    async def on_rejected(self, event: HITLEvent) -> None: ...
    @abstractmethod
    async def on_expired(self, event: HITLEvent) -> None: ...
```

### 4.3 Dispatcher Registry

Routeja notificacions als canals configurats:

```python
class NotificationPlugin(ABC):
    @abstractmethod
    async def notify(self, event: HITLEvent) -> None: ...
```

**Notificacions incloses:**

| Plugin | Canal |
|---|---|
| `NostrNotify` | Publica kind:10003 al relay |
| `SSENotify` | Push SSE a l'usuari connectat |

**Notificacions preparades per afegir:**

| Plugin | Canal | Què cal crear |
|---|---|---|
| `EmailNotify` | Email | `plugins/notifications/email.py` |
| `SlackNotify` | Slack | `plugins/notifications/slack.py` |
| `WebhookNotify` | Webhook HTTP | `plugins/notifications/webhook.py` |

---

## 5. Plugin System

### Auto-discovery

Els plugins es descobreixen automàticament des dels directoris `plugins/validators/`, `plugins/notifications/`, `plugins/hooks/`. Qualsevol fitxer nou dins d'aquests directoris que implementi la classe base corresponent s'activa automàticament.

### Com afegir un plugin nou

```
1. Crear fitxer dins de plugins/{validators,notifications,hooks}/
2. Implementar la classe base (ABC)
3. El registry el descobreix automàticament
4. Zero canvis al core engine
```

### Exemple: afegir notificació per Slack

```python
# plugins/notifications/slack.py
from plugins.notifications.base import NotificationPlugin
class SlackNotify(NotificationPlugin):
    async def notify(self, event):
        await slack_client.chat_postMessage(
            channel=event.user_slack_channel,
            text=f"⚠️ HITL pending: {event.hint}"
        )
```

### Configuració per entorn

```yaml
# k8s/configmap.yaml
hitl_hub:
  plugins:
    validators:
      recording: true
      sensor_deploy: true
      email: true
      calendar: true
    notifications:
      nostr: true
      sse: true
      email: false   # futur
      slack: false   # futur
    hooks:
      audit: true
      cache: true
      expiry: true
```

---

## 6. Persistence Layer

### Taula `nostr_hitl`

```sql
CREATE TABLE nostr_hitl (
    event_id       TEXT PRIMARY KEY,
    kind           INTEGER NOT NULL,
    pubkey         TEXT NOT NULL,
    session_id     TEXT,
    reference_id   TEXT,
    dw_pubkey      TEXT,
    owner_pubkey   TEXT,
    user_id        TEXT,
    content        TEXT,
    hint           TEXT,
    action         TEXT,
    payload        JSONB,
    tags           JSONB,
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at    TIMESTAMPTZ,
    expires_at     TIMESTAMPTZ,
    sig            TEXT,
    verified       BOOLEAN DEFAULT false,
    relay_url      TEXT,
    tenant_id      TEXT
);
```

### Event Store (append-only)

Registre immutable de tots els events HITL per audit trail.

### Cache (Redis)

Hot path reads per l'inbox i status checks freqüents.

---

## 7. Estructura del repositori

```
nodus-hitl-hub/
├── docs/
│   └── HITL_HUB_ARCHITECTURE.md
├── src/nodus_hitl_hub/
│   ├── __init__.py
│   ├── server.py              # FastMCP entrypoint
│   ├── core/
│   │   ├── engine.py          # Orquestra validació → lifecycle → dispatch
│   │   ├── validator.py       # ValidatorPlugin base + registry
│   │   ├── lifecycle.py       # LifecycleManager + transicions
│   │   ├── dispatcher.py      # Dispatcher: routeja a notification channels
│   │   └── repository.py      # PostgreSQL CRUD
│   ├── plugins/
│   │   ├── validators/
│   │   │   ├── base.py        # ValidatorPlugin (ABC)
│   │   │   ├── recording.py
│   │   │   ├── sensor_deploy.py
│   │   │   ├── email.py
│   │   │   ├── calendar.py
│   │   │   └── default.py
│   │   ├── notifications/
│   │   │   ├── base.py        # NotificationPlugin (ABC)
│   │   │   ├── nostr.py
│   │   │   └── sse.py
│   │   └── hooks/
│   │       ├── base.py        # LifecycleHook (ABC)
│   │       ├── audit.py
│   │       ├── cache.py
│   │       └── expiry.py
│   ├── models/
│   │   ├── hitl.py            # Pydantic: HITLRequest, HITLResponse
│   │   └── events.py          # Event models per audit
│   ├── mcp/
│   │   ├── tools.py           # 3 tools MCP
│   │   └── resources.py       # hitl://inbox/{user_id}
│   └── db/
│       ├── migrations/
│       │   └── 001_create_nostr_hitl.sql
│       └── queries.py
├── k8s/
│   ├── deployment.yaml
│   └── configmap.yaml
├── tests/
│   ├── __init__.py
│   └── test_core.py
├── pyproject.toml
├── Dockerfile
└── README.md
```

---

## 8. Pla d'evolució

### Funcionalitats preparades per afegir

| Funcionalitat | Què cal crear | Esforç |
|---|---|---|
| Notificacions per email | `plugins/notifications/email.py` | 1h |
| Notificacions per Slack | `plugins/notifications/slack.py` | 1h |
| Aprovació per delegació | `plugins/validators/delegation.py` + hook | 2h |
| Aprovació batch | Tool MCP `hitl.batch_approve` | 2h |
| Caducitat configurable per action_type | Camp `default_timeout` al validador | 30 min |
| Webhook en approved/rejected | `plugins/notifications/webhook.py` | 1h |
| Dashboard d'auditoria | Frontend sobre event store | 2h |
| Prioritat de HITLs | Camp `priority` al JSONB payload | 1h |

### Migració des del legacy

Cada servei legacy es connecta al Hub de forma independent, sense dependre dels altres:

```
lg-worker graphs    → mcp.tool → HUB
ADK Runtime agents  → MCPAdapter → HUB
Iris Worker         → MCP SDK client → HUB
NostrRelayBridge    → HUB (via POST /api/inbox/ingest)
Frontend            → HUB.hitl://inbox/{user_id}
```

---

> Document d'arquitectura. Per implementar, veure `server.py`.
