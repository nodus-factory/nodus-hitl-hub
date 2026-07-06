"""Validator for calendar actions."""

from nodus_hitl_hub.core.validator import ValidatorPlugin


class CalendarValidator(ValidatorPlugin):
    """Validates calendar HITL requests."""

    CALENDAR_ACTIONS = (
        "create_calendar_event",
        "update_calendar_event",
        "delete_calendar_event",
    )

    def accepts(self, action_type: str) -> bool:
        return action_type in self.CALENDAR_ACTIONS

    async def validate(self, action_type: str, payload: dict) -> list[str]:
        errors = []

        if action_type in ("create_calendar_event", "update_calendar_event"):
            if not payload.get("title"):
                errors.append("title is required for calendar events")

        if action_type == "create_calendar_event":
            if not payload.get("start"):
                errors.append("start date is required for create_calendar_event")

        return errors
