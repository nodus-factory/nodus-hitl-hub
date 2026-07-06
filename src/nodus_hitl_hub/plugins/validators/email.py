"""Validator for send_email action."""

from nodus_hitl_hub.core.validator import ValidatorPlugin


class EmailValidator(ValidatorPlugin):
    """Validates email HITL requests."""

    def accepts(self, action_type: str) -> bool:
        return action_type == "send_email"

    async def validate(self, action_type: str, payload: dict) -> list[str]:
        errors = []

        if not payload.get("to"):
            errors.append("to (recipient) is required for send_email")
        if not payload.get("subject"):
            errors.append("subject is required for send_email")

        return errors
