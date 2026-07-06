"""Validator plugin system: auto-discovery + base class."""

import importlib
import logging
import pkgutil
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ValidatorPlugin(ABC):
    """Base class for HITL validators. Validates action_details before accepting a HITL request."""

    @abstractmethod
    def accepts(self, action_type: str) -> bool:
        """Returns True if this validator handles this action_type."""
        ...

    @abstractmethod
    async def validate(self, action_type: str, payload: dict) -> list[str]:
        """Returns list of validation errors (empty list = valid)."""
        ...


class ValidatorRegistry:
    """Auto-discovers and registers all ValidatorPlugins from plugins/validators/."""

    def __init__(self):
        self._validators: list[ValidatorPlugin] = []
        self._discover()

    def _discover(self) -> None:
        """Auto-load all validators from plugins.validators package."""
        try:
            from nodus_hitl_hub.plugins import validators as pkg

            for _, name, _ in pkgutil.iter_modules(pkg.__path__):
                if name == "base":
                    continue
                module = importlib.import_module(f"nodus_hitl_hub.plugins.validators.{name}")
                for attr_name in dir(module):
                    obj = getattr(module, attr_name)
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, ValidatorPlugin)
                        and obj is not ValidatorPlugin
                    ):
                        instance = obj()
                        self._validators.append(instance)
                        logger.info("Validator registered: %s → %s", name, type(instance).__name__)
        except Exception as e:
            logger.warning("Validator auto-discovery failed: %s", e)

    def register(self, validator: ValidatorPlugin) -> None:
        """Manual registration for dynamic/conditional plugins."""
        self._validators.append(validator)
        logger.info("Validator manually registered: %s", type(validator).__name__)

    def get_validator(self, action_type: str) -> ValidatorPlugin | None:
        """Find the first validator that accepts this action_type."""
        for v in self._validators:
            if v.accepts(action_type):
                return v
        return None

    @property
    def count(self) -> int:
        return len(self._validators)
