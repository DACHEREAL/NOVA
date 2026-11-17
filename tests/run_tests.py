"""Unit test runner using Python standard library unittest."""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from nova.core.types import (
    ActionType,
    BoundingBox,
    PlannedAction,
    UINode,
    UIRole,
)
from nova.security.interceptor import SecurityInterceptor
from nova.grounding.hybrid_grounder import HybridGroundingEngine


class TestNovaCore(unittest.TestCase):

    def test_bounding_box_center_and_contains(self):
        bbox = BoundingBox(x=100.0, y=200.0, width=50.0, height=20.0)
        self.assertEqual(bbox.center, (125.0, 210.0))
        self.assertTrue(bbox.contains(120.0, 205.0))
        self.assertFalse(bbox.contains(50.0, 50.0))

    def test_uinode_flattening(self):
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
        self.assertEqual(len(interactive), 2)
        self.assertEqual(interactive[0].id, "btn_ok")
        self.assertEqual(interactive[1].id, "txt_input")

    def test_security_interceptor_destructive_command(self):
        interceptor = SecurityInterceptor()

        safe_action = PlannedAction(
            step_id=1,
            thought="List directory contents",
            action_type=ActionType.EXECUTE_SHELL,
            parameters={"command": "ls -la /tmp"},
        )
        assessment = interceptor.audit_action(safe_action)
        self.assertTrue(assessment.is_permitted)
        self.assertFalse(assessment.requires_biometric)

        destructive_action = PlannedAction(
            step_id=2,
            thought="Clean system",
            action_type=ActionType.EXECUTE_SHELL,
            parameters={"command": "rm -rf / --no-preserve-root"},
        )
        destructive_assessment = interceptor.audit_action(destructive_action)
        self.assertFalse(destructive_assessment.is_permitted)
        self.assertIn("destructive pattern", destructive_assessment.violation_reason)

    def test_security_interceptor_password_shield(self):
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
        self.assertFalse(assessment.is_permitted)
        self.assertIn("Autonomous input into secure credential fields is prohibited", assessment.violation_reason)

    def test_hybrid_grounding_platform_initialization(self):
        engine = HybridGroundingEngine()
        self.assertIn(engine.os_type.value, ["macos", "windows", "linux"])
        self.assertIsNotNone(engine.driver)

    def test_orchestrator_fast_triage(self):
        from nova.core.orchestrator import AgentOrchestrator
        from nova.sensory.tts import StreamingTTS
        from nova.memory.lancedb_store import LocalMemoryStore

        grounding = HybridGroundingEngine()
        security = SecurityInterceptor()
        tts = StreamingTTS()
        memory = LocalMemoryStore()

        orchestrator = AgentOrchestrator(
            grounding=grounding,
            security=security,
            tts=tts,
            memory=memory,
        )

        results = orchestrator.execute_user_intent("arrange windows side by side")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].action_type, ActionType.RESIZE_WINDOW)


if __name__ == "__main__":
    unittest.main()
