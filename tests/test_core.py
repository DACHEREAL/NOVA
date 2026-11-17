"""Test suite for N.O.V.A. Core, Security Interceptor, and Grounding."""

import pytest
from nova.core.types import (
    ActionType,
    BoundingBox,
    PlannedAction,
    UINode,
    UIRole,
    WindowInfo,
)
from nova.security.interceptor import SecurityInterceptor
from nova.grounding.hybrid_grounder import HybridGroundingEngine


def test_bounding_box_center_and_contains():
    bbox = BoundingBox(x=100.0, y=200.0, width=50.0, height=20.0)
    assert bbox.center == (125.0, 210.0)
    assert bbox.contains(120.0, 205.0) is True
    assert bbox.contains(50.0, 50.0) is False


def test_uinode_flattening():
    root = UINode(
        id="win_1",
        role=UIRole.WINDOW,
        bounding_box=BoundingBox(x=0, y=0, width=800, height=600),
        children=[
            UINode(
                id="btn_ok",
                role=UIRole.BUTTON,
                name="OK",
                bounding_box=BoundingBox(x=10, y=10, width=80, height=30),
                is_interactive=True,
            ),
            UINode(
                id="txt_input",
                role=UIRole.TEXT_FIELD,
                name="Username",
                bounding_box=BoundingBox(x=10, y=50, width=150, height=30),
                is_interactive=True,
            ),
        ],
    )
    interactive = root.flatten_interactive()
    assert len(interactive) == 2
    assert interactive[0].id == "btn_ok"
    assert interactive[1].id == "txt_input"


def test_security_interceptor_destructive_command():
    interceptor = SecurityInterceptor()

    safe_action = PlannedAction(
        step_id=1,
        thought="List directory contents",
        action_type=ActionType.EXECUTE_SHELL,
        parameters={"command": "ls -la /tmp"},
    )
    assessment = interceptor.audit_action(safe_action)
    assert assessment.is_permitted is True
    assert assessment.requires_biometric is False

    destructive_action = PlannedAction(
        step_id=2,
        thought="Clean system",
        action_type=ActionType.EXECUTE_SHELL,
        parameters={"command": "rm -rf / --no-preserve-root"},
    )
    destructive_assessment = interceptor.audit_action(destructive_action)
    assert destructive_assessment.is_permitted is False
    assert "destructive pattern" in destructive_assessment.violation_reason


def test_security_interceptor_password_shield():
    interceptor = SecurityInterceptor()
    secure_node = UINode(
        id="pass_1",
        role=UIRole.SECURE_TEXT_FIELD,
        name="Master Password",
        bounding_box=BoundingBox(x=0, y=0, width=100, height=20),
        is_secure=True,
    )
    input_action = PlannedAction(
        step_id=1,
        thought="Type password",
        action_type=ActionType.SET_VALUE,
        target_node_id="pass_1",
        input_text="Secret123",
    )
    assessment = interceptor.audit_action(input_action, secure_node)
    assert assessment.is_permitted is False
    assert "Autonomous input into secure credential fields is prohibited" in assessment.violation_reason


def test_hybrid_grounding_platform_initialization():
    engine = HybridGroundingEngine()
    assert engine.os_type.value in ["macos", "windows", "linux"]
    assert engine.driver is not None
