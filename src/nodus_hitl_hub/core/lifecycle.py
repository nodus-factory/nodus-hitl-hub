"""Lifecycle manager: transicions d'estat + hook execution."""

import importlib
import logging
import pkgutil
from abc import ABC, abstractmethod

from nodus_hitl_hub.models.events import HITLEvent

logger = logging.getLogger(__name__)


class LifecycleHook(ABC):
    """Base class for lifecycle hooks. Executed on state transitions."""

    @abstractmethod
    async def on_created(self, event: HITLEvent) -> None:
        """Called when a new HITL event is created (status=pending)."""
        ...

    @abstractmethod
    async def on_approved(self, event: HITLEvent) -> None:
        """Called when a HITL event is approved."""
        ...

    @abstractmethod
    async def on_rejected(self, event: HITLEvent) -> None:
        """Called when a HITL event is rejected."""
        ...

    @abstractmethod
    async def on_expired(self, event: HITLEvent) -> None:
        """Called when a HITL event expires."""
        ...


class LifecycleManager:
    """Manages state transitions and executes registered hooks."""

    def __init__(self):
        self._hooks: list[LifecycleHook] = []
        self._discover()

    def _discover(self) -> None:
        """Auto-load all hooks from plugins.hooks package."""
        try:
            from nodus_hitl_hub.plugins import hooks as pkg

            for _, name, _ in pkgutil.iter_modules(pkg.__path__):
                if name == "base":
                    continue
                module = importlib.import_module(f"nodus_hitl_hub.plugins.hooks.{name}")
                for attr_name in dir(module):
                    obj = getattr(module, attr_name)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, LifecycleHook)
                        and obj is not LifecycleHook
                    ):
                        instance = obj()
                        self._hooks.append(instance)
                        logger.info("Hook registered: %s → %s", name, type(instance).__name__)
        except Exception as e:
            logger.warning("Hook auto-discovery failed: %s", e)

    def register(self, hook: LifecycleHook) -> None:
        """Manual registration for dynamic hooks."""
        self._hooks.append(hook)
        logger.info("Hook manually registered: %s", type(hook).__name__)

    async def on_created(self, event: HITLEvent) -> None:
        for hook in self._hooks:
            try:
                await hook.on_created(event)
            except Exception as e:
                logger.error("Hook %s.on_created failed: %s", type(hook).__name__, e)

    async def on_approved(self, event: HITLEvent) -> None:
        for hook in self._hooks:
            try:
                await hook.on_approved(event)
            except Exception as e:
                logger.error("Hook %s.on_approved failed: %s", type(hook).__name__, e)

    async def on_rejected(self, event: HITLEvent) -> None:
        for hook in self._hooks:
            try:
                await hook.on_rejected(event)
            except Exception as e:
                logger.error("Hook %s.on_rejected failed: %s", type(hook).__name__, e)

    async def on_expired(self, event: HITLEvent) -> None:
        for hook in self._hooks:
            try:
                await hook.on_expired(event)
            except Exception as e:
                logger.error("Hook %s.on_expired failed: %s", type(hook).__name__, e)

    @property
    def count(self) -> int:
        return len(self._hooks)
