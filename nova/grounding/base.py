"""Base interfaces for Cross-Platform Window Management and Accessibility Grounding."""

from abc import ABC, abstractmethod
from typing import List, Optional
from nova.core.types import UINode, WindowInfo, PlannedAction, ExecutionResult


class BaseAccessibilityDriver(ABC):
    """Abstract driver interface that all OS-specific accessibility backends must implement."""

    @abstractmethod
    def is_available(self) -> bool:
        """Checks if required OS accessibility permissions and system APIs are available."""
        pass

    @abstractmethod
    def get_active_window(self) -> Optional[WindowInfo]:
        """Returns details about the currently focused top-level window."""
        pass

    @abstractmethod
    def list_windows(self) -> List[WindowInfo]:
        """Lists all visible top-level application windows across monitors."""
        pass

    @abstractmethod
    def get_window_tree(self, window: WindowInfo, max_depth: int = 8) -> UINode:
        """Extracts and normalizes the accessibility tree of the target window."""
        pass

    @abstractmethod
    def execute_action(self, action: PlannedAction) -> ExecutionResult:
        """Directly invokes an action on the operating system's native accessibility tree."""
        pass

    @abstractmethod
    def focus_window(self, window_id: str) -> bool:
        """Brings the designated window to the foreground."""
        pass

    @abstractmethod
    def move_resize_window(self, window_id: str, x: float, y: float, width: float, height: float) -> bool:
        """Repositions and resizes a window deterministically."""
        pass
