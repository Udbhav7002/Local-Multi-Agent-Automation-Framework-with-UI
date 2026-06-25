"""
Type-safe data models for the Multi-Agent Automation Framework.
Replaces raw dict/string passing with validated dataclasses and enums.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Union


class ActionType(str, Enum):
    """All supported action verbs in the execution pipeline."""
    RUN_COMMAND = "run_command"
    CLICK = "click"
    TYPE = "type"
    HOTKEY = "hotkey"
    GOTO = "goto"
    SLEEP = "sleep"
    CLOSE_BROWSER = "close_browser"
    OPEN_APP = "open_app"
    CLICK_DOM = "click_dom"
    TYPE_DOM = "type_dom"
    SEARCH_START_MENU = "search_start_menu"


class MethodType(str, Enum):
    """Execution backend identifiers."""
    CLI = "cli"
    GUI = "gui"
    BROWSER = "browser"
    SYSTEM = "system"


# Mapping from action to its canonical method
ACTION_TO_METHOD = {
    ActionType.RUN_COMMAND: MethodType.CLI,
    ActionType.CLICK: MethodType.GUI,
    ActionType.TYPE: MethodType.GUI,
    ActionType.HOTKEY: MethodType.GUI,
    ActionType.SEARCH_START_MENU: MethodType.GUI,
    ActionType.GOTO: MethodType.BROWSER,
    ActionType.CLICK_DOM: MethodType.BROWSER,
    ActionType.TYPE_DOM: MethodType.BROWSER,
    ActionType.SLEEP: MethodType.SYSTEM,
    ActionType.CLOSE_BROWSER: MethodType.SYSTEM,
    ActionType.OPEN_APP: MethodType.SYSTEM,
}


@dataclass
class ActionStep:
    """
    A single executable step produced by the Worker agent.
    Replaces raw Dict[str, Any] passing throughout the pipeline.
    Supports arbitrary strings for action/method to allow for custom plugins.
    """
    action: Union[ActionType, str]
    target: str
    method: Union[MethodType, str]
    expected_outcome: str = ""
    undo_action: Optional[ActionType] = None
    undo_target: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: dict) -> "ActionStep":
        """
        Construct an ActionStep from a raw dict (as parsed from Worker JSON).
        Performs validation and auto-corrects the method field based on the action.
        """
        raw_action = str(raw.get("action", "unknown")).lower().strip()
        raw_target = str(raw.get("target", ""))
        raw_method = str(raw.get("method", "cli")).lower().strip()
        expected = str(raw.get("expected_outcome", ""))

        # Handle common LLM hallucination: action="browser", target="goto ..."
        if raw_action == "browser" and raw_target.startswith("goto "):
            raw_action = "goto"
            raw_target = raw_target.replace("goto ", "", 1).strip()

        # Parse action, supporting custom plugin actions
        try:
            action = ActionType(raw_action)
            # Force the canonical method based on the action (override LLM mistakes)
            method = ACTION_TO_METHOD.get(action, MethodType.CLI)
        except ValueError:
            # Custom plugin action
            action = raw_action
            method = raw_method

        undo_raw_action = raw.get("undo_action")
        undo_target = raw.get("undo_target")
        undo_action = None
        if undo_raw_action:
            try:
                undo_action = ActionType(str(undo_raw_action).lower().strip())
            except ValueError:
                pass

        return cls(
            action=action,
            target=raw_target,
            method=method,
            expected_outcome=expected,
            undo_action=undo_action,
            undo_target=undo_target,
        )

    def to_dict(self) -> dict:
        """Convert back to a plain dict for backward compatibility."""
        res = {
            "action": self.action.value if isinstance(self.action, Enum) else self.action,
            "target": self.target,
            "method": self.method.value if isinstance(self.method, Enum) else self.method,
            "expected_outcome": self.expected_outcome,
        }
        if self.undo_action and self.undo_target:
            res["undo_action"] = self.undo_action.value if isinstance(self.undo_action, Enum) else self.undo_action
            res["undo_target"] = self.undo_target
        return res


@dataclass
class StepResult:
    """The outcome of executing a single ActionStep."""
    success: bool
    output: str
    step: Optional[ActionStep] = None
