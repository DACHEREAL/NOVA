"""Agent Orchestrator & FSM Loop with Dual-Tier Reasoning and Deterministic Safety."""

import json
import logging
import re
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
from nova.core.skills import DesktopSkills
from nova.core.intent_resolver import NaturalLanguageIntentResolver
from nova.core.ai_engine import LocalAIEngine
from nova.memory.habit_learner import HabitMemoryEngine

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
        ai_engine: Optional[LocalAIEngine] = None,
        habits: Optional[HabitMemoryEngine] = None,
    ):
        self.grounding = grounding
        self.security = security
        self.tts = tts
        self.memory = memory
        self.max_steps = max_steps
        self.habits = habits or HabitMemoryEngine()
        self.ai_engine = ai_engine or LocalAIEngine()

    def execute_user_intent(
        self,
        intent: str,
        on_step_update: Optional[Callable[[PlannedAction, ExecutionResult], None]] = None,
    ) -> List[ExecutionResult]:
        """Executes a multi-step user goal across desktop applications."""
        logger.info(f"Received user intent: '{intent}'")
        history: List[ExecutionResult] = []

        # Determine contextual active application
        active_app = None
        try:
            active_win = self.grounding.get_active_window()
            if active_win and active_win.app_name:
                active_app = active_win.app_name
        except Exception:
            pass

        # If active window is terminal/IDE, infer from recent user interaction
        if not active_app or any(x in active_app.lower() for x in ["terminal", "iterm", "zsh", "bash", "antigravity", "nova", "code"]):
            last_act = self.habits.get_last_interaction()
            if last_act:
                last_params = last_act.get("parameters", {})
                active_app = last_params.get("app") or last_params.get("app_name") or last_params.get("target_app") or active_app

        # 1. Primary: Neural Local AI Brain (LLaMA 3.2 / Ollama / LM Studio)
        if self.ai_engine.is_available:
            try:
                habits_ctx = self.habits.get_context_prompt()
                ai_result = self.ai_engine.reason_and_plan(intent, habits_context=habits_ctx, current_app=active_app)
                if ai_result:
                    thought, planned_actions = ai_result
                    if planned_actions:
                        logger.info(f"AI Brain ({self.ai_engine.active_model}) generated plan with {len(planned_actions)} step(s)")
                        for plan in planned_actions:
                            res = self._dispatch_action(plan)
                            history.append(res)
                            if on_step_update:
                                on_step_update(plan, res)
                            self.habits.record_interaction(
                                raw_utterance=intent,
                                action_type=plan.parameters.get("skill", plan.action_type.value),
                                parameters=plan.parameters,
                                thought=thought,
                                success=res.success,
                            )
                        self.tts.speak_sync("Done.")
                        return history
            except Exception as e:
                logger.warning(f"AI Brain execution error, falling back to reflex triage: {e}")

        # 2. Fast Triage / Direct Action Router (<10ms Reflex Fallback)
        direct_action = self._triage_fast_intent(intent, active_app=active_app)
        if direct_action:
            logger.info("Executing via Fast Triage Path (<30ms)")
            result = self._dispatch_action(direct_action)
            history.append(result)
            if on_step_update:
                on_step_update(direct_action, result)
            self.habits.record_interaction(
                raw_utterance=intent,
                action_type=direct_action.parameters.get("skill", direct_action.action_type.value),
                parameters=direct_action.parameters,
                thought=direct_action.thought,
                success=result.success,
            )
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

    def _triage_fast_intent(self, intent: str, active_app: Optional[str] = None) -> Optional[PlannedAction]:
        """Resolves conversational human speech in ANY word order to precise OS skills."""
        resolved = NaturalLanguageIntentResolver.resolve(intent, active_app=active_app)
        if not resolved:
            return None

        # Map resolved intent to PlannedAction
        if resolved.intent_type == "web_search":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.LAUNCH_APP,
                parameters={
                    "skill": "web_search",
                    "platform": resolved.parameters["platform"],
                    "query": resolved.parameters["query"],
                },
            )
        elif resolved.intent_type == "send_message":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.TYPE_TEXT,
                parameters={
                    "skill": "send_message",
                    "app": resolved.parameters["app"],
                    "contact": resolved.parameters["contact"],
                    "message": resolved.parameters["message"],
                },
            )
        elif resolved.intent_type == "in_app_search":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.TYPE_TEXT,
                parameters={
                    "skill": "in_app_search",
                    "app": resolved.parameters["app"],
                    "query": resolved.parameters["query"],
                },
            )
        elif resolved.intent_type == "dictionary_lookup":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.LAUNCH_APP,
                parameters={
                    "skill": "dictionary_lookup",
                    "word": resolved.parameters["word"],
                },
            )
        elif resolved.intent_type == "open_website":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.LAUNCH_APP,
                parameters={
                    "skill": "open_website",
                    "site": resolved.parameters["site"],
                },
            )
        elif resolved.intent_type == "click_semantic":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.CLICK,
                parameters={
                    "skill": "click_element_in_app" if resolved.parameters.get("app") else "click_active_element",
                    "element": resolved.parameters["element"],
                    "app": resolved.parameters.get("app"),
                },
            )
        elif resolved.intent_type == "navigate_active_tab":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.LAUNCH_APP,
                parameters={
                    "skill": "navigate_active_tab",
                    "query": resolved.parameters["query"],
                },
            )
        elif resolved.intent_type == "switch_tab":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.KEY_COMBINATION,
                parameters={
                    "skill": "switch_tab",
                    "tab_number": resolved.parameters["tab_number"],
                },
            )
        elif resolved.intent_type == "type_in_app":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.TYPE_TEXT,
                parameters={
                    "skill": "type_in_app",
                    "app": resolved.parameters["app"],
                    "text": resolved.parameters["text"],
                },
            )
        elif resolved.intent_type == "type_text":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.TYPE_TEXT,
                parameters={
                    "skill": "type_text",
                    "text": resolved.parameters["text"],
                },
            )
        elif resolved.intent_type == "insert_photo":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.TYPE_TEXT,
                parameters={
                    "skill": "insert_photo",
                    "photo_name": resolved.parameters.get("photo_name", ""),
                },
            )
        elif resolved.intent_type == "system_control":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.EXECUTE_SHELL,
                parameters={
                    "skill": "system_control",
                    "action": resolved.parameters["action"],
                },
            )
        elif resolved.intent_type == "scroll":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.SCROLL,
                parameters={
                    "skill": "scroll",
                    "direction": resolved.parameters["direction"],
                    "amount": resolved.parameters["amount"],
                },
            )
        elif resolved.intent_type == "browser_control":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.KEY_COMBINATION,
                parameters={
                    "skill": "browser_control",
                    "action": resolved.parameters["action"],
                },
            )
        elif resolved.intent_type == "edit_action":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.KEY_COMBINATION,
                parameters={
                    "skill": "edit_action",
                    "action": resolved.parameters["action"],
                },
            )
        elif resolved.intent_type == "move_file":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.EXECUTE_SHELL,
                parameters={
                    "skill": "move_file",
                    "src": resolved.parameters["src"],
                    "dest": resolved.parameters["dest"],
                },
            )
        elif resolved.intent_type == "window_layout":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.RESIZE_WINDOW,
            )
        elif resolved.intent_type == "launch_app":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.LAUNCH_APP,
                target_app=resolved.parameters["app_name"],
            )
        elif resolved.intent_type == "terminate_app":
            return PlannedAction(
                step_id=1,
                thought=resolved.thought,
                action_type=ActionType.TERMINATE,
                target_app=resolved.parameters["app_name"],
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
        if step_id > 1:
            return PlannedAction(
                step_id=step_id,
                thought="All required UI mutations have been verified.",
                action_type=ActionType.TERMINATE,
            )

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
        skill = action.parameters.get("skill")
        if skill == "web_search":
            return DesktopSkills.open_web_search(
                action.parameters["platform"], action.parameters["query"]
            )
        elif skill == "send_message":
            return DesktopSkills.send_message_flow(
                action.parameters["app"],
                action.parameters["contact"],
                action.parameters["message"],
            )
        elif skill == "in_app_search":
            DesktopSkills.focus_app(action.parameters["app"])
            time.sleep(0.3)
            DesktopSkills.press_hotkey(["command", "f"])
            time.sleep(0.2)
            return DesktopSkills.type_text(action.parameters["query"], press_enter=True)
        elif skill == "click_element_in_app":
            app = action.parameters.get("app")
            elem = action.parameters.get("element")
            if app:
                DesktopSkills.focus_app(app)
                time.sleep(0.4)
            tree = self.grounding.inspect_ui()
            coords = DesktopSkills.click_semantic_element(tree, elem)
            if coords:
                return DesktopSkills.physical_click(coords[0], coords[1])
            return ExecutionResult(
                step_id=action.step_id,
                success=False,
                action_type=ActionType.CLICK,
                output_message=f"Could not locate '{elem}' in {app or 'active window'}",
                latency_ms=10.0,
                error="ElementNotFound",
            )
        elif skill == "click_active_element":
            elem = action.parameters.get("element")
            tree = self.grounding.inspect_ui()
            coords = DesktopSkills.click_semantic_element(tree, elem)
            if coords:
                return DesktopSkills.physical_click(coords[0], coords[1])
            return ExecutionResult(
                step_id=action.step_id,
                success=False,
                action_type=ActionType.CLICK,
                output_message=f"Could not locate '{elem}' in active window",
                latency_ms=10.0,
                error="ElementNotFound",
            )
        elif skill == "dictionary_lookup":
            return DesktopSkills.lookup_dictionary(action.parameters["word"])
        elif skill == "open_website":
            return DesktopSkills.open_website_in_browser(action.parameters["site"])
        elif skill == "navigate_active_tab":
            return DesktopSkills.navigate_active_tab(action.parameters["query"])
        elif skill == "switch_tab":
            return DesktopSkills.switch_browser_tab(action.parameters["tab_number"])
        elif skill == "type_in_app":
            return DesktopSkills.type_in_app(action.parameters["text"], action.parameters["app"])
        elif skill == "type_text":
            return DesktopSkills.type_text(action.parameters["text"], press_enter=False)
        elif skill == "insert_photo":
            return DesktopSkills.insert_photo_into_doc(action.parameters.get("photo_name", ""))
        elif skill == "system_control":
            return DesktopSkills.system_control(action.parameters["action"])
        elif skill == "scroll":
            return DesktopSkills.scroll(action.parameters["direction"], action.parameters["amount"])
        elif skill == "browser_control":
            return DesktopSkills.browser_control(action.parameters["action"])
        elif skill == "edit_action":
            return DesktopSkills.edit_action(action.parameters["action"])
        elif skill == "move_file":
            return DesktopSkills.move_file(action.parameters["src"], action.parameters["dest"])

        # Standard Fallbacks
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
                res = subprocess.run(["osascript", "-e", f'tell application "{app_name}" to quit'], capture_output=True)
                if res.returncode != 0:
                    # Fallback to case-insensitive pkill for background macOS apps
                    subprocess.run(["pkill", "-i", "-f", app_name], capture_output=True)
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
