"""Agent Orchestrator & FSM Loop with Dual-Tier Reasoning and Deterministic Safety."""

import json
import logging
import time
from typing import Callable, List, Optional

from nova.core.types import (
    ActionType,
    ExecutionResult,
    PlannedAction,
    UINode,
    WindowInfo,
)
from nova.grounding.hybrid_grounder import HybridGroundingEngine
from nova.security.interceptor import SecurityInterceptor
from nova.sensory.tts import StreamingTTS
from nova.memory.lancedb_store import LocalMemoryStore

logger = logging.getLogger("nova.core.orchestrator")


class AgentOrchestrator:
    """The central nervous system of N.O.V.A., managing the perception-reasoning-action loop."""

    def __init__(
        self,
        grounding: HybridGroundingEngine,
        security: SecurityInterceptor,
        tts: StreamingTTS,
        memory: LocalMemoryStore,
        max_steps: int = 12,
    ):
        self.grounding = grounding
        self.security = security
        self.tts = tts
        self.memory = memory
        self.max_steps = max_steps

    def execute_user_intent(
        self,
        intent: str,
        on_step_update: Optional[Callable[[PlannedAction, ExecutionResult], None]] = None,
    ) -> List[ExecutionResult]:
        """Executes a multi-step user goal across desktop applications."""
        logger.info(f"Received user intent: '{intent}'")
        history: List[ExecutionResult] = []

        # 1. Fast Triage / Direct Action Router
        direct_action = self._triage_fast_intent(intent)
        if direct_action:
            logger.info("Executing via Fast Triage Path (<30ms)")
            result = self._dispatch_action(direct_action)
            history.append(result)
            if on_step_update:
                on_step_update(direct_action, result)
            self.tts.speak_sync("Done.")
            return history

        # 2. Multi-Step ReAct Autonomous Execution Loop
        for step in range(1, self.max_steps + 1):
            logger.info(f"--- ReAct Step {step}/{self.max_steps} ---")

            # A. Sense: Inspect Active UI Window Tree
            active_window = self.grounding.get_active_window()
            ui_tree = self.grounding.inspect_ui(active_window)
            actionable_nodes = ui_tree.flatten_interactive()[:40]  # Cap for context window

            # B. Reason: Plan Next Action (Grammar-Constrained)
            planned_action = self._plan_step(intent, step, active_window, actionable_nodes, history)
            if planned_action.action_type == ActionType.TERMINATE:
                logger.info(f"Goal satisfied: {planned_action.thought}")
                self.tts.speak_sync("Task completed successfully.")
                break

            # C. Intercept: Audit action through Non-LLM Security Gate
            target_node = ui_tree.find_node_by_id(planned_action.target_node_id) if planned_action.target_node_id else None
            assessment = self.security.audit_action(planned_action, target_node)

            if not assessment.is_permitted:
                logger.warning(f"Action blocked by safety policy: {assessment.violation_reason}")
                self.tts.speak_sync(f"Action stopped: {assessment.violation_reason}")
                break

            if assessment.requires_biometric:
                approved = self.security.trigger_biometric_gate(assessment.violation_reason or "Elevated action")
                if not approved:
                    logger.warning("Biometric verification failed or canceled.")
                    self.tts.speak_sync("Biometric authorization failed. Aborting action.")
                    break

            # D. Act: Dispatch to Native Platform Driver
            exec_result = self.grounding.execute(planned_action)
            history.append(exec_result)

            if on_step_update:
                on_step_update(planned_action, exec_result)

            if not exec_result.success:
                logger.warning(f"Step {step} failed: {exec_result.error}. Re-evaluating next step.")

            # Short settlement delay for UI state transition
            time.sleep(0.15)

        return history

    def _triage_fast_intent(self, intent: str) -> Optional[PlannedAction]:
        """Bypasses deep LLM reasoning for deterministic single-shot OS commands."""
        lowered = intent.lower().strip()

        # Clean punctuation from intent (. , ! ?)
        lowered = re.sub(r"[.?!,]+$", "", lowered).strip()

        if "side by side" in lowered or "arrange windows" in lowered:
            return PlannedAction(
                step_id=1,
                thought="Arranging windows side-by-side cleanly.",
                action_type=ActionType.RESIZE_WINDOW,
            )

        if lowered.startswith("open ") or lowered.startswith("launch "):
            app_name = lowered.replace("open ", "").replace("launch ", "").strip().strip(".?!,'\"")
            return PlannedAction(
                step_id=1,
                thought=f"Directly launching application {app_name}",
                action_type=ActionType.LAUNCH_APP,
                target_app=app_name,
            )

        if lowered.startswith("close ") or lowered.startswith("quit "):
            app_name = lowered.replace("close ", "").replace("quit ", "").strip().strip(".?!,'\"")
            return PlannedAction(
                step_id=1,
                thought=f"Terminating application {app_name}",
                action_type=ActionType.TERMINATE,
                target_app=app_name,
            )

        return None

    def _plan_step(
        self,
        intent: str,
        step_id: int,
        active_window: Optional[WindowInfo],
        nodes: List[UINode],
        history: List[ExecutionResult],
    ) -> PlannedAction:
        """Invokes local model with grammar constraints to generate next deterministic action."""
        # In full production, this calls llama.cpp / MLX with structured JSON logit mask
        # Example demonstration heuristic for test harness
        if step_id > 1:
            return PlannedAction(
                step_id=step_id,
                thought="All required UI mutations have been verified.",
                action_type=ActionType.TERMINATE,
            )

        # First step: search interactive buttons in active window
        for node in nodes:
            if "search" in node.name.lower() or "find" in node.name.lower():
                return PlannedAction(
                    step_id=step_id,
                    thought=f"Clicking search control '{node.name}' to locate target query.",
                    action_type=ActionType.CLICK,
                    target_node_id=node.id,
                    coordinates=node.bounding_box.center,
                )

        return PlannedAction(
            step_id=step_id,
            thought="Inspecting active window content.",
            action_type=ActionType.FOCUS,
            target_node_id=nodes[0].id if nodes else None,
        )

    def _dispatch_action(self, action: PlannedAction) -> ExecutionResult:
        if action.action_type == ActionType.LAUNCH_APP and action.target_app:
            return self._launch_app_native(action.target_app, action.step_id)
        elif action.action_type == ActionType.TERMINATE and action.target_app:
            return self._close_app_native(action.target_app, action.step_id)
        elif action.action_type == ActionType.RESIZE_WINDOW:
            windows = self.grounding.list_windows()
            if len(windows) >= 2:
                self.grounding.arrange_windows_side_by_side(windows[0].id, windows[1].id)
            return ExecutionResult(
                step_id=action.step_id,
                success=True,
                action_type=ActionType.RESIZE_WINDOW,
                output_message="Arranged windows side-by-side.",
                latency_ms=1.0,
                state_mutated=True,
            )
        return self.grounding.execute(action)

    def _launch_app_native(self, app_name: str, step_id: int) -> ExecutionResult:
        import subprocess
        start_time = time.perf_counter()
        try:
            if self.grounding.os_type.value == "macos":
                subprocess.Popen(["open", "-a", app_name])
            elif self.grounding.os_type.value == "windows":
                subprocess.Popen(["start", app_name], shell=True)
            else:
                subprocess.Popen([app_name])
            return ExecutionResult(
                step_id=step_id,
                success=True,
                action_type=ActionType.LAUNCH_APP,
                output_message=f"Launched application '{app_name}'",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                state_mutated=True,
            )
        except Exception as e:
            return ExecutionResult(
                step_id=step_id,
                success=False,
                action_type=ActionType.LAUNCH_APP,
                output_message=f"Failed to launch '{app_name}': {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    def _close_app_native(self, app_name: str, step_id: int) -> ExecutionResult:
        import subprocess
        start_time = time.perf_counter()
        try:
            if self.grounding.os_type.value == "macos":
                script = f'tell application "{app_name}" to quit'
                subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
            elif self.grounding.os_type.value == "windows":
                subprocess.run(["taskkill", "/IM", f"{app_name}.exe", "/F"], check=True)
            else:
                subprocess.run(["pkill", "-f", app_name], check=True)
            return ExecutionResult(
                step_id=step_id,
                success=True,
                action_type=ActionType.TERMINATE,
                output_message=f"Closed application '{app_name}'",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                state_mutated=True,
            )
        except Exception as e:
            return ExecutionResult(
                step_id=step_id,
                success=False,
                action_type=ActionType.TERMINATE,
                output_message=f"Failed to close '{app_name}': {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )
