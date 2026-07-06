"""Validator for start_recording action."""

from nodus_hitl_hub.core.validator import ValidatorPlugin


class RecordingValidator(ValidatorPlugin):
    """Validates recording HITL requests (kind:10100)."""

    def accepts(self, action_type: str) -> bool:
        return action_type == "start_recording"

    async def validate(self, action_type: str, payload: dict) -> list[str]:
        errors = []

        if not payload.get("recording_id"):
            errors.append("recording_id is required for start_recording")
        if not payload.get("recorder_url"):
            errors.append("recorder_url is required for start_recording")
        if not payload.get("recording_type"):
            errors.append("recording_type is required (audio, video, or screen)")

        recording_type = payload.get("recording_type", "")
        if recording_type not in ("audio", "video", "screen"):
            errors.append("recording_type must be 'audio', 'video', or 'screen'")

        return errors
