"""Windows native UIAutomation (UIA3) and Win32 Window Management Driver."""

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

logger = logging.getLogger("nova.grounding.windows")

WIN_AVAILABLE = False
if sys.platform == "win32":
    try:
        import win32gui
        import win32process
        import win32con
        import comtypes.client
        WIN_AVAILABLE = True
    except ImportError:
        logger.warning("Windows COM/Win32 libraries not found. Run `pip install .[windows]`.")


class WindowsAccessibilityDriver(BaseAccessibilityDriver):
    """Native Windows driver using modern UI Automation v3 and Win32 system APIs."""

    def __init__(self):
        self._uia: Any = None
        self._node_cache: Dict[str, Any] = {}
        if WIN_AVAILABLE:
            try:
                # Initialize CUIAutomation COM object
                self._uia = comtypes.client.CreateObject("{ff48dba4-60ef-4201-aa87-54103eef594e}")
            except Exception as e:
                logger.error(f"Failed to initialize UIAutomation COM: {e}")

    def is_available(self) -> bool:
        return WIN_AVAILABLE and self._uia is not None

    def list_windows(self) -> List[WindowInfo]:
        if not WIN_AVAILABLE:
            return []

        import win32gui
        import win32process

        windows: List[WindowInfo] = []

        def enum_windows_callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    rect = win32gui.GetWindowRect(hwnd)
                    x, y, r, b = rect
                    w = r - x
                    h = b - y
                    if w > 50 and h > 50:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        windows.append(
                            WindowInfo(
                                id=str(hwnd),
                                title=title,
                                app_name=title.split(" - ")[-1],
                                pid=pid,
                                bounding_box=BoundingBox(x=float(x), y=float(y), width=float(w), height=float(h)),
                                is_active=False,
                                is_minimized=win32gui.IsIconic(hwnd) != 0,
                            )
                        )
            return True

        win32gui.EnumWindows(enum_windows_callback, None)
        return windows

    def get_active_window(self) -> Optional[WindowInfo]:
        if not WIN_AVAILABLE:
            return None

        import win32gui
        import win32process

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None

        title = win32gui.GetWindowText(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        x, y, r, b = rect
        _, pid = win32process.GetWindowThreadProcessId(hwnd)

        return WindowInfo(
            id=str(hwnd),
            title=title,
            app_name=title.split(" - ")[-1] if title else "Unknown",
            pid=pid,
            bounding_box=BoundingBox(x=float(x), y=float(y), width=float(r - x), height=float(b - y)),
            is_active=True,
            is_minimized=win32gui.IsIconic(hwnd) != 0,
        )

    def get_window_tree(self, window: WindowInfo, max_depth: int = 8) -> UINode:
        self._node_cache.clear()
        if not self.is_available():
            return UINode(
                id="win_root_dummy",
                role=UIRole.WINDOW,
                name=window.title,
                bounding_box=window.bounding_box,
                children=[],
            )

        try:
            hwnd = int(window.id)
            root_elem = self._uia.ElementFromHandle(hwnd)
            return self._traverse_element(root_elem, depth=0, max_depth=max_depth, prefix=window.id)
        except Exception as e:
            logger.error(f"UIA tree extraction failed: {e}")
            return UINode(
                id="win_err",
                role=UIRole.WINDOW,
                name=window.title,
                bounding_box=window.bounding_box,
                children=[],
            )

    def _traverse_element(self, element: Any, depth: int, max_depth: int, prefix: str) -> UINode:
        node_id = f"win_{prefix}_{depth}_{len(self._node_cache)}"
        self._node_cache[node_id] = element

        try:
            name = element.CurrentName or ""
            control_type = element.CurrentControlType
            rect = element.CurrentBoundingRectangle
            bbox = BoundingBox(
                x=float(rect.left),
                y=float(rect.top),
                width=float(rect.right - rect.left),
                height=float(rect.bottom - rect.top),
            )
            role = self._map_control_type(control_type)
            is_password = bool(getattr(element, "CurrentIsPassword", False))
        except Exception:
            return UINode(
                id=node_id,
                role=UIRole.UNKNOWN,
                name="",
                bounding_box=BoundingBox(x=0, y=0, width=0, height=0),
            )

        children_nodes: List[UINode] = []
        if depth < max_depth:
            try:
                tree_walker = self._uia.RawViewWalker
                child = tree_walker.GetFirstChildElement(element)
                count = 0
                while child and count < 25:
                    child_node = self._traverse_element(child, depth + 1, max_depth, prefix=f"{prefix}_{count}")
                    children_nodes.append(child_node)
                    child = tree_walker.GetNextSiblingElement(child)
                    count += 1
            except Exception:
                pass

        return UINode(
            id=node_id,
            role=role,
            name=name,
            bounding_box=bbox,
            is_interactive=role in [UIRole.BUTTON, UIRole.TEXT_FIELD, UIRole.CHECKBOX, UIRole.TAB],
            is_secure=is_password,
            children=children_nodes,
        )

    def execute_action(self, action: PlannedAction) -> ExecutionResult:
        start_time = time.perf_counter()
        if not self.is_available():
            return ExecutionResult(
                step_id=action.step_id,
                success=False,
                action_type=action.action_type,
                output_message="Windows UIA driver not available",
                latency_ms=0.0,
                error="UIAUnavailable",
            )

        elem = self._node_cache.get(action.target_node_id) if action.target_node_id else None

        try:
            if action.action_type == ActionType.CLICK and elem:
                # Try InvokePattern
                UIA_InvokePatternId = 10000
                pattern = elem.GetCurrentPattern(UIA_InvokePatternId)
                if pattern:
                    pattern.Invoke()
                    return ExecutionResult(
                        step_id=action.step_id,
                        success=True,
                        action_type=action.action_type,
                        output_message=f"Invoked UIA element {action.target_node_id}",
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                        state_mutated=True,
                    )

            elif action.action_type == ActionType.SET_VALUE and elem and action.input_text is not None:
                UIA_ValuePatternId = 10002
                pattern = elem.GetCurrentPattern(UIA_ValuePatternId)
                if pattern:
                    pattern.SetValue(action.input_text)
                    return ExecutionResult(
                        step_id=action.step_id,
                        success=True,
                        action_type=action.action_type,
                        output_message=f"Set text value via UIA ValuePattern on {action.target_node_id}",
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                        state_mutated=True,
                    )

            # Fallback to physical mouse coordinate input
            if action.coordinates:
                cx, cy = action.coordinates
                self._dispatch_win32_click(int(cx), int(cy))
                return ExecutionResult(
                    step_id=action.step_id,
                    success=True,
                    action_type=action.action_type,
                    output_message=f"Dispatched physical Win32 mouse click at ({cx}, {cy})",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    state_mutated=True,
                )

            return ExecutionResult(
                step_id=action.step_id,
                success=False,
                action_type=action.action_type,
                output_message="UIA action pattern unsupported on target",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error="PatternUnsupported",
            )
        except Exception as ex:
            return ExecutionResult(
                step_id=action.step_id,
                success=False,
                action_type=action.action_type,
                output_message=f"Windows execution failed: {str(ex)}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(ex),
            )

    def focus_window(self, window_id: str) -> bool:
        if not WIN_AVAILABLE:
            return False
        import win32gui
        import win32con

        hwnd = int(window_id)
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        win32gui.SetForegroundWindow(hwnd)
        return True

    def move_resize_window(self, window_id: str, x: float, y: float, width: float, height: float) -> bool:
        if not WIN_AVAILABLE:
            return False
        import win32gui
        hwnd = int(window_id)
        win32gui.MoveWindow(hwnd, int(x), int(y), int(width), int(height), True)
        return True

    def _dispatch_win32_click(self, x: int, y: int):
        import win32api
        import win32con
        win32api.SetCursorPos((x, y))
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)

    def _map_control_type(self, ctype: int) -> UIRole:
        mapping = {
            50000: UIRole.BUTTON,
            50004: UIRole.TEXT_FIELD,
            50002: UIRole.CHECKBOX,
            50013: UIRole.RADIO_BUTTON,
            50003: UIRole.COMBO_BOX,
            50032: UIRole.WINDOW,
            50019: UIRole.TAB,
            50009: UIRole.MENU,
            50011: UIRole.MENU_ITEM,
            50006: UIRole.IMAGE,
        }
        return mapping.get(ctype, UIRole.UNKNOWN)
