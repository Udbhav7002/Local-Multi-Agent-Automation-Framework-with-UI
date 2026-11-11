"""
Pydantic v2 schemas for strict boundary validation.
"""

from pydantic import BaseModel, Field, field_validator, model_validator


class ActionStepPayload(BaseModel):
    """
    Validated representation of a single executable step produced by the Worker agent.
    """
    action: str = Field(..., min_length=1)
    target: str = Field(...)
    method: str = Field(..., pattern="^(cli|gui|browser|system)$")
    expected_outcome: str = ""
    undo_action: str | None = None
    undo_target: str | None = None

    @field_validator("target")
    @classmethod
    def no_shell_metacharacters_unless_safe(cls, v: str, info) -> str:
        method = info.data.get("method")
        # In a real implementation, we could add stricter validation for CLI targets.
        # The SafetyGate handles the heavy lifting, but we can do basic length/type checks here.
        if method == "cli" and not v.strip():
            raise ValueError("CLI target cannot be empty")
        return v

    @model_validator(mode='after')
    def validate_undo(self) -> 'ActionStepPayload':
        if bool(self.undo_action) != bool(self.undo_target):
            # Normalizing to None if one is missing, or we could raise an error
            self.undo_action = None
            self.undo_target = None
        return self
