# Notify — Estat i roadmap

Sistema de notificacions de Nodus OS: Web Push a la PWA (llibreta-v2) + router multicanal al HITL Hub.

Última actualització: 2026-07-10.

## Estat actual (desplegat a nodus-dev)

### Fase 1 — Web Push (llibreta-v2) ✅

- Subscripcions VAPID per usuari/dispositiu (taula `push_subscriptions`, migració 026)
- Endpoints: `GET /api/push/vapid-public-key`, `POST /api/push/subscribe`, `POST /api/push/unsubscribe`
- `POST /internal/push/send` protegit amb header `X-Internal-Token` (env `INTERNAL_PUSH_TOKEN`) — entrada per a serveis (hitl-hub)
- Trigger automàtic: push en persistir notificacions Nostr (`POST /api/nostr/notifications`)
- UI: toggle campana (`PushNotificationToggle`) al costat de l'InboxButton
- iOS: requereix PWA instal·lada a pantalla d'inici (iOS 16.4+)

### Fase 2 — Router Notify (hitl-hub) ✅

- Models: `NotifyRequest`/`NotifyResult`, prioritats `info < normal < urgent < critical`
- Taules: `notification_log`, `notification_preferences` (migració 002)
- Adapters (`plugins/channels/`): `webpush` (→ llibreta-v2), `email` (→ backoffice `/internal/email`), `whatsapp` (esquelet, vegeu pendents)
- `NotifyEngine`: routing per preferències, `min_priority`, quiet hours (UTC, critical les ignora), injecció d'adreça per canal
- Eines MCP: `notify_send`, `notify_ack`, `notify_history`
- Env al deployment: `LLIBRETA_URL=http://llibreta-v2-app:5002`, `INTERNAL_PUSH_TOKEN`, `BACKOFFICE_SERVICE_TOKEN` (secrets a `nodus-secrets`)

## Pendent

### P1 — WhatsApp outbound (backoffice)

L'adapter `plugins/channels/whatsapp.py` està llest però **el backoffice no exposa cap endpoint HTTP d'enviament**: `sendWhatsAppMessage()` (Twilio/Meta, a `server/services/whatsappService.ts`) només s'usa internament per respondre webhooks.

Feina:
- Crear `POST /internal/whatsapp` al backoffice amb body `{ to, body }` i auth `Authorization: Bearer $BACKOFFICE_SERVICE_TOKEN` (mateix patró que `/internal/email`)
- L'adapter ja apunta a `BACKOFFICE_WHATSAPP_SEND_URL` (default `{BACKOFFICE_URL}/internal/whatsapp`) — no cal tocar hitl-hub

### P2 — Trucades de veu (Twilio Voice)

- Adapter nou `plugins/channels/voice.py`: Twilio Calls API amb TwiML `<Say>` que llegeixi el missatge
- Credencials ja existents al cluster: `twilio-account-sid`, `twilio-auth-token` a `nodus-secrets`
- El canal `voice` ja està contemplat al routing (preferències + adreça); només falta l'adapter

### P3 — Motor d'escalada

Ara el routing és single-shot. Falta l'escalada per prioritat amb ack-tracking:

| Prioritat | Inicial | Escalada sense ack |
|-----------|---------|--------------------|
| `urgent` | webpush | WhatsApp després de N min |
| `critical` | webpush + WhatsApp | Trucada després de N min |

Feina:
- Background task (patró `ExpiryHook`) que revisi `notification_log` amb `acked_at IS NULL` i priority urgent/critical passats N minuts, i reenviï pel canal següent
- Registrar l'ack des del client: el SW de llibreta-v2 (`notificationclick`) hauria de cridar `notify_ack` (via endpoint proxy a llibreta server → hitl-hub MCP, o endpoint HTTP directe al hub)
- Columna `escalation_level` a `notification_log`

### P4 — UI de preferències (llibreta-v2)

No hi ha cap UI per gestionar `notification_preferences` (canals, telèfon, quiet hours, min_priority). Ara només es poden editar per SQL.

Feina:
- Pàgina/secció de settings a llibreta-v2 amb CRUD de preferències
- Endpoints proxy al servidor de llibreta o accés directe a les taules del hub (mateixa BD `nodus_db`)

### P5 — Integrar productors amb notify_send

Ningú crida `notify_send` encara. Candidats:
- ADK Runtime: HITL creat / recording complete → notify urgent
- lg-worker: pla generat, acta llesta → notify normal
- Backoffice: events de negoci

Via MCP Gateway (`hitl-hub` ja registrat amb scopes `hitl:*`, `confirmation:*` — afegir scope `notify:*` a `nodus-mcp-gateway/config/servers.json`).

### P6 — Deutes tècnics

- **hitl-hub fora de GitOps**: desplegat amb `kubectl apply` manual + patches d'env. Cal migrar-lo a `nodus-gitops` (l'intent anterior va fallar per conflicte de templates Helm — reintentar amb template alineat amb l'estructura `platform.*` existent)
- **Notificadors HITL a mig fer**: `plugins/notifications/nostr.py` (publish al relay TODO) i `sse.py` (asyncio.Queue TODO)
- **Frontend no integrat amb el HITL Hub**: les cards HITL de llibreta-v2 segueixen amb els seus fluxos propis (SSE ADK Runtime + Nostr); la migració cap a `hitl://inbox/{user_id}` està per fer
- **Test E2E del push**: provar cicle complet subscripció → `notify_send` → push rebut a mòbil i desktop

## Referències

- Arquitectura hub: `docs/HITL_HUB_ARCHITECTURE.md`
- Convenció de cards HITL (frontend): `nodus-llibreta-v2/docs/HITL_CARDS.md`
- Claus i secrets: `nodus-secrets` a nodus-dev (`vapid-public-key`, `vapid-private-key`, `internal-push-token`)
