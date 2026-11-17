"""Universal type definitions and data contracts for N.O.V.A."""

from __future__ import annotations

import enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PlatformOS(str, enum.Enum):
    MACOS = "macos"
    WINDOWS = "windows"
    LINUX = "linux"
    UNKNOWN = "unknown"


class UIRole(str, enum.Enum):
    WINDOW = "window"
    BUTTON = "button"
    TEXT_FIELD = "text_field"
    SECURE_TEXT_FIELD = "secure_text_field"  # Password / PIN inputs
    CHECKBOX = "checkbox"
    RADIO_BUTTON = "radio_button"
    COMBO_BOX = "combo_box"
    SLIDER = "slider"
    TAB = "tab"
    MENU = "menu"
    MENU_ITEM = "menu_item"
    SCROLL_AREA = "scroll_area"
    IMAGE = "image"
    LINK = "link"
    CANVAS = "canvas"
    UNKNOWN = "unknown"


class ActionType(str, enum.Enum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    FOCUS = "focus"
    SET_VALUE = "set_value"
    TYPE_TEXT = "type_text"
    KEY_COMBINATION = "key_combination"
    SCROLL = "scroll"
    DRAG_AND_DROP = "drag_and_drop"
    LAUNCH_APP = "launch_app"
    SWITCH_WINDOW = "switch_window"
    RESIZE_WINDOW = "resize_window"
    EXECUTE_SHELL = "execute_shell"
    QUERY_KNOWLEDGE = "query_knowledge"
    TERMINATE = "terminate"


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2.0, self.y + self.height / 2.0)

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height


class UINode(BaseModel):
    """Platform-agnostic representation of an accessibility / visual UI node."""
    id: str
    platform_handle: Optional[str] = None
    role: UIRole
    name: str = ""
    value: Optional[str] = None
    description: Optional[str] = None
    bounding_box: BoundingBox
    is_interactive: bool = True
    is_focused: bool = False
    is_secure: bool = False
    supported_actions: List[ActionType] = Field(default_factory=list)
    children: List[UINode] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def find_node_by_id(self, target_id: str) -> Optional[UINode]:
        if self.id == target_id:
            return self
        for child in self.children:
            found = child.find_node_by_id(target_id)
            if found:
                return found
        return None

    def flatten_interactive(self) -> List[UINode]:
        """Flattens the tree into a concise list of actionable elements for LLM context."""
        items: List[UINode] = []
        if self.is_interactive and self.role != UIRole.WINDOW:
            items.append(self)
        for child in self.children:
            items.extend(child.flatten_interactive())
        return items


class WindowInfo(BaseModel):
    id: str
    title: str
    app_name: str
    pid: int
    bounding_box: BoundingBox
    is_active: bool
    is_minimized: bool


class PlannedAction(BaseModel):
    """Formal schema for an agent's proposed action."""
    step_id: int
    thought: str = Field(description="Reasoning behind selecting this action")
    action_type: ActionType
    target_node_id: Optional[str] = None
    target_app: Optional[str] = None
    coordinates: Optional[tuple[float, float]] = None
    input_text: Optional[str] = None
    key_combo: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)


class SecurityAssessment(BaseModel):
    is_permitted: bool
    requires_biometric: bool = False
    violation_reason: Optional[str] = None
    sanitized_action: Optional[PlannedAction] = None


class ExecutionResult(BaseModel):
    step_id: int
    success: bool
    action_type: ActionType
    output_message: str
    latency_ms: float
    state_mutated: bool = False
    error: Optional[str] = None
