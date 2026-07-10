"""Channel adapter registry: auto-discovery from plugins.channels."""

import importlib
import logging
import pkgutil

from nodus_hitl_hub.plugins.channels.base import ChannelAdapter

logger = logging.getLogger(__name__)


class ChannelRegistry:
    """Auto-discovers ChannelAdapter subclasses from plugins.channels."""

    def __init__(self) -> None:
        self._adapters: dict[str, ChannelAdapter] = {}
        self._discover()

    def _discover(self) -> None:
        try:
            from nodus_hitl_hub.plugins import channels as pkg

            for _, name, _ in pkgutil.iter_modules(pkg.__path__):
                if name in ("base",):
                    continue
                module = importlib.import_module(f"nodus_hitl_hub.plugins.channels.{name}")
                for attr_name in dir(module):
                    obj = getattr(module, attr_name)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, ChannelAdapter)
                        and obj is not ChannelAdapter
                    ):
                        instance = obj()
                        self._adapters[instance.name] = instance
                        logger.info("Channel adapter registered: %s → %s", instance.name, type(instance).__name__)
        except Exception as e:
            logger.warning("Channel adapter auto-discovery failed: %s", e)

    def register(self, adapter: ChannelAdapter) -> None:
        self._adapters[adapter.name] = adapter
        logger.info("Channel adapter manually registered: %s", adapter.name)

    def get(self, name: str) -> ChannelAdapter | None:
        return self._adapters.get(name)

    @property
    def names(self) -> list[str]:
        return list(self._adapters.keys())

    @property
    def count(self) -> int:
        return len(self._adapters)
