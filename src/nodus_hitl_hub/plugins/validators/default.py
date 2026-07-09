"""Default validator: accepts any action_type with minimal validation."""

from nodus_hitl_hub.core.validator import ValidatorPlugin


class DefaultValidator(ValidatorPlugin):
    """Fallback validator that accepts any action_type."""

    is_fallback = True

    def accepts(self, action_type: str) -> bool:
        return True

    async def validate(self, action_type: str, payload: dict) -> list[str]:
        errors = []

        if not action_type:
            errors.append("action_type is required")

        if not isinstance(payload, dict):
            errors.append("payload must be a JSON object")

        return errors
