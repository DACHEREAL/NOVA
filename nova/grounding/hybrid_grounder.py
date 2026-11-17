"""Hybrid Dual-Engine Grounding coordinator combining Accessibility Trees and Visual SOM."""

import logging
import sys
from typing import List, Optional

from nova.core.types import (
    BoundingBox,
    ExecutionResult,
    PlannedAction,
    PlatformOS,
    UINode,
    UIRole,
    WindowInfo,
)
from nova.grounding.base import BaseAccessibilityDriver
from nova.grounding.macos import MacOSAccessibilityDriver
from nova.grounding.windows import WindowsAccessibilityDriver
from nova.grounding.linux import LinuxAccessibilityDriver
from nova.grounding.vision_som import VisualGroundingEngine

logger = logging.getLogger("nova.grounding.hybrid")


class HybridGroundingEngine:
    """Orchestrates structured accessibility tree queries with visual fallback for universal app coverage."""

    def __init__(self, visual_fallback: bool = True):
        self.os_type = self._detect_platform()
        self.driver: BaseAccessibilityDriver = self._init_native_driver()
        self.vision_engine = VisualGroundingEngine() if visual_fallback else None
        logger.info(f"HybridGroundingEngine initialized for {self.os_type.value}. Native driver: {type(self.driver).__name__}")

    def _detect_platform(self) -> PlatformOS:
        if sys.platform == "darwin":
            return PlatformOS.MACOS
        elif sys.platform == "win32":
            return PlatformOS.WINDOWS
        elif sys.platform.startswith("linux"):
            return PlatformOS.LINUX
        return PlatformOS.UNKNOWN

    def _init_native_driver(self) -> BaseAccessibilityDriver:
        if self.os_type == PlatformOS.MACOS:
            return MacOSAccessibilityDriver()
        elif self.os_type == PlatformOS.WINDOWS:
            return WindowsAccessibilityDriver()
        elif self.os_type == PlatformOS.LINUX:
            return LinuxAccessibilityDriver()
        raise RuntimeError(f"Unsupported operating system: {sys.platform}")

    def get_active_window(self) -> Optional[WindowInfo]:
        return self.driver.get_active_window()

    def list_windows(self) -> List[WindowInfo]:
        return self.driver.list_windows()

    def inspect_ui(self, window: Optional[WindowInfo] = None) -> UINode:
        """Inspects the target UI using the fastest structured path, falling back to visual SOM if needed."""
        target_window = window or self.get_active_window()
        if not target_window:
            return UINode(
                id="desktop_root",
                role=UIRole.WINDOW,
                name="Desktop",
                bounding_box=BoundingBox(x=0, y=0, width=1920, height=1080),
                children=[],
            )

        # 1. Fast Path: Native Accessibility Tree
        tree = self.driver.get_window_tree(target_window)
        interactive_nodes = tree.flatten_interactive()

        # 2. Check if a11y tree is barren (e.g. Electron app with a11y disabled, or Canvas app)
        if len(interactive_nodes) == 0 and self.vision_engine is not None:
            logger.info(f"Accessibility tree empty for '{target_window.title}'. Triggering Visual SOM Fallback.")
            # Trigger hardware screen capture and visual detector
            # (In production, grab frame bytes via native OS screen API)
            dummy_frame = b"\x00" * 1024
            visual_nodes = self.vision_engine.detect_interactive_regions(dummy_frame, target_window.bounding_box)
            tree.children.extend(visual_nodes)

        return tree

    def execute(self, action: PlannedAction) -> ExecutionResult:
        """Executes the planned action via the native OS driver with coordinate translation."""
        return self.driver.execute_action(action)

    def focus_window(self, window_id: str) -> bool:
        return self.driver.focus_window(window_id)

    def arrange_windows_side_by_side(self, win1_id: str, win2_id: str, screen_width: float = 1920, screen_height: float = 1080) -> bool:
        """Snaps two windows side-by-side cleanly."""
        half_w = screen_width / 2.0
        r1 = self.driver.move_resize_window(win1_id, 0, 0, half_w, screen_height)
        r2 = self.driver.move_resize_window(win2_id, half_w, 0, half_w, screen_height)
        return r1 and r2
