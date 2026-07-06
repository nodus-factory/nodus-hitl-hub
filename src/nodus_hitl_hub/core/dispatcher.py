"""Dispatcher: routeja notificacions als canals configurats."""

import importlib
import logging
import pkgutil
from abc import ABC, abstractmethod

from nodus_hitl_hub.models.events import HITLEvent

logger = logging.getLogger(__name__)


class NotificationPlugin(ABC):
    """Base class for notification plugins. Sends HITL events to a channel."""

    @abstractmethod
    async def notify(self, event: HITLEvent) -> None:
        """Send notification about a HITL event to this channel."""
        ...


class DispatcherRegistry:
    """Auto-discovers and registers all NotificationPlugins. Routes events to all channels."""

    def __init__(self):
        self._plugins: list[NotificationPlugin] = []
        self._discover()

    def _discover(self) -> None:
        """Auto-load all notifiers from plugins.notifications package."""
        try:
            from nodus_hitl_hub.plugins import notifications as pkg

            for _, name, _ in pkgutil.iter_modules(pkg.__path__):
                if name == "base":
                    continue
                module = importlib.import_module(f"nodus_hitl_hub.plugins.notifications.{name}")
                for attr_name in dir(module):
                    obj = getattr(module, attr_name)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, NotificationPlugin)
                        and obj is not NotificationPlugin
                    ):
                        instance = obj()
                        self._plugins.append(instance)
                        logger.info("Notification plugin registered: %s → %s", name, type(instance).__name__)
        except Exception as e:
            logger.warning("Notification plugin auto-discovery failed: %s", e)

    def register(self, plugin: NotificationPlugin) -> None:
        """Manual registration for dynamic notification plugins."""
        self._plugins.append(plugin)
        logger.info("Notification plugin manually registered: %s", type(plugin).__name__)

    async def notify_all(self, event: HITLEvent) -> None:
        """Route the event to ALL registered notification plugins."""
        for plugin in self._plugins:
            try:
                await plugin.notify(event)
            except Exception as e:
                logger.error("Notification plugin %s failed: %s", type(plugin).__name__, e)

    @property
    def count(self) -> int:
        return len(self._plugins)
