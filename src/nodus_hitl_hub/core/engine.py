"""Core engine: orquestra el flux complet d'un HITL request."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from nodus_hitl_hub.core.validator import ValidatorRegistry
from nodus_hitl_hub.core.lifecycle import LifecycleManager
from nodus_hitl_hub.core.dispatcher import DispatcherRegistry
from nodus_hitl_hub.core.repository import Repository
from nodus_hitl_hub.models.hitl import HITLRequest, HITLResponse, HITLStatus
from nodus_hitl_hub.models.events import HITLEvent

logger = logging.getLogger(__name__)


class HITLEngine:
    """Orquestra el flux complet: validar → crear → notificar → esperar → resoldre."""

    def __init__(
        self,
        repository: Repository,
        validators: ValidatorRegistry,
        lifecycle: LifecycleManager,
        dispatcher: DispatcherRegistry,
    ):
        self.repository = repository
        self.validators = validators
        self.lifecycle = lifecycle
        self.dispatcher = dispatcher

    async def request(self, req: HITLRequest) -> HITLResponse:
        """Crea un nou HITL request: valida, persisteix, notifica."""

        # 1. Validate
        validator = self.validators.get_validator(req.action_type)
        if validator:
            errors = await validator.validate(req.action_type, req.action_details)
            if errors:
                return HITLResponse(
                    confirmation_id=None,
                    status=HITLStatus.ERROR,
                    error=f"Validation failed: {'; '.join(errors)}",
                )

        # 2. Persist
        event = HITLEvent.from_request(req)
        await self.repository.insert(event)

        # 3. Lifecycle: on_created
        await self.lifecycle.on_created(event)

        # 4. Notify
        await self.dispatcher.notify_all(event)

        logger.info("HITL request created: id=%s action=%s user=%s", event.event_id, req.action_type, req.user_id)

        return HITLResponse(
            confirmation_id=event.event_id,
            status=HITLStatus.PENDING,
            expires_at=event.expires_at,
        )

    async def wait(self, confirmation_id: str, poll_interval: float = 2.0, max_wait: float = 300.0) -> HITLResponse:
        """Espera fins que un HITL es resolgui o expiri."""

        start = datetime.utcnow()
        deadline = start + timedelta(seconds=max_wait)

        while datetime.utcnow() < deadline:
            event = await self.repository.get(confirmation_id)
            if event is None:
                return HITLResponse(
                    confirmation_id=confirmation_id,
                    status=HITLStatus.ERROR,
                    error="Confirmation not found",
                )

            if event.status in (HITLStatus.APPROVED, HITLStatus.REJECTED):
                return HITLResponse(
                    confirmation_id=confirmation_id,
                    status=event.status,
                    response=event.payload,
                    confirmed_at=event.resolved_at,
                )

            if event.status == HITLStatus.EXPIRED:
                return HITLResponse(
                    confirmation_id=confirmation_id,
                    status=HITLStatus.TIMEOUT,
                    error="Confirmation expired",
                )

            await self._sleep(poll_interval)

        return HITLResponse(
            confirmation_id=confirmation_id,
            status=HITLStatus.TIMEOUT,
            error=f"Timeout after {max_wait}s",
        )

    async def check(self, confirmation_id: str) -> HITLResponse:
        """Comprova l'estat d'un HITL sense bloquejar."""

        event = await self.repository.get(confirmation_id)
        if event is None:
            return HITLResponse(
                confirmation_id=confirmation_id,
                status=HITLStatus.ERROR,
                error="Confirmation not found",
            )

        return HITLResponse(
            confirmation_id=confirmation_id,
            status=event.status,
            response=event.payload if event.status in (HITLStatus.APPROVED, HITLStatus.REJECTED) else None,
            confirmed_at=event.resolved_at,
        )

    async def approve(self, confirmation_id: str, response: Optional[dict] = None) -> HITLResponse:
        """Aprova un HITL."""

        event = await self.repository.get(confirmation_id)
        if event is None:
            return HITLResponse(confirmation_id=confirmation_id, status=HITLStatus.ERROR, error="Not found")
        if event.status != HITLStatus.PENDING:
            return HITLResponse(confirmation_id=confirmation_id, status=HITLStatus.ERROR, error=f"Already {event.status}")

        await self.repository.update_status(confirmation_id, HITLStatus.APPROVED, response)
        event.status = HITLStatus.APPROVED
        event.payload = response or event.payload
        await self.lifecycle.on_approved(event)

        logger.info("HITL approved: id=%s", confirmation_id)
        return HITLResponse(confirmation_id=confirmation_id, status=HITLStatus.APPROVED)

    async def reject(self, confirmation_id: str, reason: Optional[str] = None) -> HITLResponse:
        """Rebutja un HITL."""

        event = await self.repository.get(confirmation_id)
        if event is None:
            return HITLResponse(confirmation_id=confirmation_id, status=HITLStatus.ERROR, error="Not found")
        if event.status != HITLStatus.PENDING:
            return HITLResponse(confirmation_id=confirmation_id, status=HITLStatus.ERROR, error=f"Already {event.status}")

        await self.repository.update_status(confirmation_id, HITLStatus.REJECTED, {"reason": reason})
        event.status = HITLStatus.REJECTED
        await self.lifecycle.on_rejected(event)

        logger.info("HITL rejected: id=%s reason=%s", confirmation_id, reason)
        return HITLResponse(confirmation_id=confirmation_id, status=HITLStatus.REJECTED)

    async def get_inbox(self, user_id: str) -> list[HITLEvent]:
        """Retorna tots els HITL pendents per un usuari."""

        return await self.repository.list_pending(user_id)

    async def _sleep(self, seconds: float) -> None:
        """Wrapper per async sleep (facilita testing)."""
        import asyncio

        await asyncio.sleep(seconds)
