"""Validator for deploy_sensor action (Iris worker sensor deploy)."""

from nodus_hitl_hub.core.validator import ValidatorPlugin


class SensorDeployValidator(ValidatorPlugin):
    """Validates sensor deploy HITL requests (kind:10020)."""

    VALID_SENSORS = ("gmail", "calendar", "drive", "twenty")

    def accepts(self, action_type: str) -> bool:
        return action_type == "deploy_sensor"

    async def validate(self, action_type: str, payload: dict) -> list[str]:
        errors = []

        sensor = payload.get("sensor", "")
        if not sensor:
            errors.append("sensor name is required for deploy_sensor")
        elif sensor not in self.VALID_SENSORS:
            errors.append(f"sensor must be one of: {', '.join(self.VALID_SENSORS)}")

        if not payload.get("target_system"):
            errors.append("target_system is required for deploy_sensor")

        return errors
