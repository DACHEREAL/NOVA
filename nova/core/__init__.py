from nova.core.types import (
    PlatformOS,
    UIRole,
    ActionType,
    BoundingBox,
    UINode,
    WindowInfo,
    PlannedAction,
    SecurityAssessment,
    ExecutionResult,
)


def __getattr__(name: str):
    if name == "AgentOrchestrator":
        from nova.core.orchestrator import AgentOrchestrator
        return AgentOrchestrator
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "PlatformOS",
    "UIRole",
    "ActionType",
    "BoundingBox",
    "UINode",
    "WindowInfo",
    "PlannedAction",
    "SecurityAssessment",
    "ExecutionResult",
    "AgentOrchestrator",
]
