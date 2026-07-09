"""Validator for Model Book compiler conflicts (Memorium → HITL)."""

from nodus_hitl_hub.core.validator import ValidatorPlugin


class ModelBookConflictValidator(ValidatorPlugin):
    """Validates modelbook_conflict requests coming from the Memorium compiler.

    The payload must carry enough for the resolution side-effect (proposal_id,
    tenant_id) and for the human to decide (claim coordinates + values).
    """

    def accepts(self, action_type: str) -> bool:
        return action_type == "modelbook_conflict"

    async def validate(self, action_type: str, payload: dict) -> list[str]:
        errors = []
        if not payload.get("proposal_id"):
            errors.append("proposal_id is required for modelbook_conflict")
        if not payload.get("tenant_id"):
            errors.append("tenant_id is required for modelbook_conflict")
        if not payload.get("region_id"):
            errors.append("region_id is required for modelbook_conflict")
        if not payload.get("claim_key"):
            errors.append("claim_key is required for modelbook_conflict")
        if "proposed_value" not in payload:
            errors.append("proposed_value is required for modelbook_conflict")
        return errors
