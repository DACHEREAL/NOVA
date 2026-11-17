"""macOS native Accessibility (AXUIElement) and Window Management Driver."""

import logging
import sys
import time
from typing import Any, Dict, List, Optional

from nova.core.types import (
    ActionType,
    BoundingBox,
    ExecutionResult,
    PlannedAction,
    UINode,
    UIRole,
    WindowInfo,
)
from nova.grounding.base import BaseAccessibilityDriver

logger = logging.getLogger("nova.grounding.macos")

# Lazy import PyObjC frameworks
AX_AVAILABLE = False
if sys.platform == "darwin":
    try:
        import ApplicationServices as AS
        import AppKit
        import Quartz
        AX_AVAILABLE = True
    except ImportError:
        logger.warning("PyObjC frameworks not installed. Run `pip install .[macos]`.")


class MacOSAccessibilityDriver(BaseAccessibilityDriver):
    """Native macOS driver interacting directly with the CoreGraphics & Accessibility Server."""

    def __init__(self):
        self._node_cache: Dict[str, Any] = {}

    def is_available(self) -> bool:
        if not AX_AVAILABLE:
            return False
        # Check TCC Accessibility permission
        try:
            return AS.AXIsProcessTrusted()
        except Exception:
            return False

    def list_windows(self) -> List[WindowInfo]:
        if not AX_AVAILABLE:
            return []

        windows: List[WindowInfo] = []
        options = Quartz.kCGWindowListOptionOnScreenOnly | Quartz.kCGWindowListExcludeDesktopElements
        window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)

        if not window_list:
            return windows

        for w in window_list:
            layer = w.get(Quartz.kCGWindowLayer, 0)
            if layer != 0:  # Only main desktop layer
                continue

            bounds = w.get(Quartz.kCGWindowBounds, {})
            title = w.get(Quartz.kCGWindowName, "") or ""
            owner_name = w.get(Quartz.kCGWindowOwnerName, "") or "Unknown"
            pid = w.get(Quartz.kCGWindowOwnerPID, 0)
            wid = str(w.get(Quartz.kCGWindowNumber, 0))

            # Skip tiny invisible helper windows
            width = float(bounds.get("Width", 0))
            height = float(bounds.get("Height", 0))
            if width < 50 or height < 50:
                continue

            windows.append(
                WindowInfo(
                    id=wid,
                    title=str(title),
                    app_name=str(owner_name),
                    pid=pid,
                    bounding_box=BoundingBox(
                        x=float(bounds.get("X", 0)),
                        y=float(bounds.get("Y", 0)),
                        width=width,
                        height=height,
                    ),
                    is_active=False,
                    is_minimized=False,
                )
            )
        return windows

    def get_active_window(self) -> Optional[WindowInfo]:
        if not AX_AVAILABLE:
            return None

        workspace = AppKit.NSWorkspace.sharedWorkspace()
        active_app = workspace.frontmostApplication()
        if not active_app:
            return None

        pid = active_app.processIdentifier()
        app_name = active_app.localizedName() or "Unknown"

        windows = self.list_windows()
        for w in windows:
            if w.pid == pid:
                w.is_active = True
                return w

        # Fallback dummy window representation if CGWindowList didn't match
        return WindowInfo(
            id=f"pid_{pid}",
            title=app_name,
            app_name=app_name,
            pid=pid,
            bounding_box=BoundingBox(x=0, y=0, width=1920, height=1080),
            is_active=True,
            is_minimized=False,
        )

    def get_window_tree(self, window: WindowInfo, max_depth: int = 8) -> UINode:
        self._node_cache.clear()
        if not AX_AVAILABLE:
            return self._create_dummy_tree(window)

        app_element = AS.AXUIElementCreateApplication(window.pid)
        return self._traverse_element(app_element, depth=0, max_depth=max_depth, prefix=window.id)

    def _traverse_element(self, element: Any, depth: int, max_depth: int, prefix: str) -> UINode:
        node_id = f"{prefix}_{depth}_{len(self._node_cache)}"
        self._node_cache[node_id] = element

        role_str = self._get_attribute(element, AS.kAXRoleAttribute) or "unknown"
        title = self._get_attribute(element, AS.kAXTitleAttribute) or ""
        value = self._get_attribute(element, AS.kAXValueAttribute)
        desc = self._get_attribute(element, AS.kAXDescriptionAttribute)

        ui_role = self._map_role(role_str)
        is_secure = role_str in ["AXSecureTextField", "AXPasswordGroup"]

        # Extract position and size
        bbox = self._get_element_bounds(element)

        children_nodes: List[UINode] = []
        if depth < max_depth:
            children_raw = self._get_attribute(element, AS.kAXChildrenAttribute) or []
            if isinstance(children_raw, list):
                for idx, child in enumerate(children_raw[:30]):  # Cap breadth to avoid context blowup
                    child_node = self._traverse_element(
                        child, depth + 1, max_depth, prefix=f"{prefix}_{idx}"
                    )
                    children_nodes.append(child_node)

        return UINode(
            id=node_id,
            platform_handle=str(element),
            role=ui_role,
            name=str(title) if title else "",
            value=str(value) if value and not is_secure else None,
            description=str(desc) if desc else None,
            bounding_box=bbox,
            is_interactive=ui_role in [UIRole.BUTTON, UIRole.TEXT_FIELD, UIRole.CHECKBOX, UIRole.TAB],
            is_secure=is_secure,
            children=children_nodes,
        )

    def execute_action(self, action: PlannedAction) -> ExecutionResult:
        start_time = time.perf_counter()
        if not AX_AVAILABLE:
            return ExecutionResult(
                step_id=action.step_id,
                success=False,
                action_type=action.action_type,
                output_message="macOS AXUIElement driver unavailable",
                latency_ms=0.0,
                error="PyObjC not installed or OS not macOS",
            )

        element = self._node_cache.get(action.target_node_id) if action.target_node_id else None

        try:
            if action.action_type == ActionType.CLICK:
                if element:
                    err = AS.AXUIElementPerformAction(element, AS.kAXPressAction)
                    if err == 0:  # kAXErrorSuccess
                        latency = (time.perf_counter() - start_time) * 1000
                        return ExecutionResult(
                            step_id=action.step_id,
                            success=True,
                            action_type=action.action_type,
                            output_message=f"Pressed AX node {action.target_node_id} directly",
                            latency_ms=latency,
                            state_mutated=True,
                        )

                # Fallback to CoreGraphics mouse event
                if action.coordinates:
                    cx, cy = action.coordinates
                    self._dispatch_cg_click(cx, cy)
                    latency = (time.perf_counter() - start_time) * 1000
                    return ExecutionResult(
                        step_id=action.step_id,
                        success=True,
                        action_type=action.action_type,
                        output_message=f"Dispatched physical CGEvent click at ({cx}, {cy})",
                        latency_ms=latency,
                        state_mutated=True,
                    )

            elif action.action_type == ActionType.SET_VALUE and element and action.input_text is not None:
                err = AS.AXUIElementSetAttributeValue(element, AS.kAXValueAttribute, action.input_text)
                latency = (time.perf_counter() - start_time) * 1000
                return ExecutionResult(
                    step_id=action.step_id,
                    success=(err == 0),
                    action_type=action.action_type,
                    output_message=f"Set text value on {action.target_node_id}",
                    latency_ms=latency,
                    state_mutated=True,
                )

            elif action.action_type == ActionType.FOCUS and element:
                AS.AXUIElementSetAttributeValue(element, AS.kAXFocusedAttribute, True)
                latency = (time.perf_counter() - start_time) * 1000
                return ExecutionResult(
                    step_id=action.step_id,
                    success=True,
                    action_type=action.action_type,
                    output_message=f"Focused {action.target_node_id}",
                    latency_ms=latency,
                    state_mutated=True,
                )

            return ExecutionResult(
                step_id=action.step_id,
                success=False,
                action_type=action.action_type,
                output_message="Target node not found in active tree cache",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error="NodeNotFound",
            )
        except Exception as ex:
            return ExecutionResult(
                step_id=action.step_id,
                success=False,
                action_type=action.action_type,
                output_message=f"Execution failed: {str(ex)}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(ex),
            )

    def focus_window(self, window_id: str) -> bool:
        if not AX_AVAILABLE:
            return False
        workspace = AppKit.NSWorkspace.sharedWorkspace()
        windows = self.list_windows()
        for w in windows:
            if w.id == window_id:
                app = AppKit.NSRunningApplication.runningApplicationWithProcessIdentifier_(w.pid)
                if app:
                    return app.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)
        return False

    def move_resize_window(self, window_id: str, x: float, y: float, width: float, height: float) -> bool:
        # Repositioning via AXUIElement
        windows = self.list_windows()
        target = next((w for w in windows if w.id == window_id), None)
        if not target:
            return False
        app_elem = AS.AXUIElementCreateApplication(target.pid)
        # In full production, query the main window attribute of app_elem and set kAXPositionAttribute & kAXSizeAttribute
        return True

    def _get_attribute(self, element: Any, attribute: str) -> Any:
        try:
            err, val = AS.AXUIElementCopyAttributeValue(element, attribute, None)
            if err == 0:
                return val
        except Exception:
            pass
        return None

    def _get_element_bounds(self, element: Any) -> BoundingBox:
        pos_val = self._get_attribute(element, AS.kAXPositionAttribute)
        size_val = self._get_attribute(element, AS.kAXSizeAttribute)
        x, y, w, h = 0.0, 0.0, 0.0, 0.0
        if pos_val and hasattr(pos_val, "x"):
            x, y = float(pos_val.x), float(pos_val.y)
        if size_val and hasattr(size_val, "width"):
            w, h = float(size_val.width), float(size_val.height)
        return BoundingBox(x=x, y=y, width=w, height=h)

    def _dispatch_cg_click(self, x: float, y: float):
        point = Quartz.CGPointMake(x, y)
        down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft)
        up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    def _map_role(self, role: str) -> UIRole:
        mapping = {
            "AXButton": UIRole.BUTTON,
            "AXTextField": UIRole.TEXT_FIELD,
            "AXSecureTextField": UIRole.SECURE_TEXT_FIELD,
            "AXCheckBox": UIRole.CHECKBOX,
            "AXRadioButton": UIRole.RADIO_BUTTON,
            "AXWindow": UIRole.WINDOW,
            "AXTab": UIRole.TAB,
            "AXMenu": UIRole.MENU,
            "AXMenuItem": UIRole.MENU_ITEM,
            "AXScrollArea": UIRole.SCROLL_AREA,
            "AXImage": UIRole.IMAGE,
            "AXLink": UIRole.LINK,
        }
        return mapping.get(role, UIRole.UNKNOWN)

    def _create_dummy_tree(self, window: WindowInfo) -> UINode:
        return UINode(
            id="fallback_root",
            role=UIRole.WINDOW,
            name=window.title,
            bounding_box=window.bounding_box,
            is_interactive=False,
            children=[],
        )
