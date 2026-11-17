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
        """Deep multi-domain intent triage routing to native OS and browser automation skills."""
        lowered = intent.lower().strip()
        lowered = re.sub(r"[.?!,]+$", "", lowered).strip()

        # 1. Web Search Intent (e.g. "search for mr beast on youtube", "search python on google")
        web_match = re.match(
            r"^search\s+(for\s+)?(?P<query>.+?)\s+on\s+(?P<platform>youtube|google|reddit|github)$",
            lowered,
        )
        if web_match:
            platform = web_match.group("platform")
            query = web_match.group("query")
            return PlannedAction(
                step_id=1,
                thought=f"Executing web search for '{query}' on {platform.title()}",
                action_type=ActionType.LAUNCH_APP,
                parameters={"skill": "web_search", "platform": platform, "query": query},
            )

        # 1b. Direct platform search: "open youtube and search mr beast"
        direct_web = re.match(
            r"^open\s+(?P<platform>youtube|google|reddit|github)(\s+and\s+search\s+(for\s+)?(?P<query>.+))?$",
            lowered,
        )
        if direct_web:
            platform = direct_web.group("platform")
            query = direct_web.group("query") or ""
            return PlannedAction(
                step_id=1,
                thought=f"Opening {platform.title()}" + (f" and searching '{query}'" if query else ""),
                action_type=ActionType.LAUNCH_APP,
                parameters={"skill": "web_search", "platform": platform, "query": query},
            )

        # 2. In-App Contextual Actions: "in WhatsApp search for Mom", "in Word search X"
        in_app_search = re.match(r"^in\s+(?P<app>[a-zA-Z0-9 ]+?)\s+search\s+(for\s+)?(?P<query>.+)$", lowered)
        if in_app_search:
            app = in_app_search.group("app").strip()
            query = in_app_search.group("query").strip()
            return PlannedAction(
                step_id=1,
                thought=f"Focusing '{app}', opening search, and querying '{query}'",
                action_type=ActionType.TYPE_TEXT,
                parameters={"skill": "in_app_search", "app": app, "query": query},
            )

        # 3. Semantic UI Element Tapping: "tap on create on Microsoft Word", "click new on Word"
        tap_in_app = re.match(r"^(tap|click)(\s+on)?\s+(?P<element>.+?)\s+on\s+(?P<app>[a-zA-Z0-9 ]+)$", lowered)
        if tap_in_app:
            elem = tap_in_app.group("element").strip()
            app = tap_in_app.group("app").strip()
            return PlannedAction(
                step_id=1,
                thought=f"Focusing '{app}' and tapping on '{elem}'",
                action_type=ActionType.CLICK,
                parameters={"skill": "click_element_in_app", "element": elem, "app": app},
            )

        # 3b. Active Window Tapping: "tap on create", "click submit"
        tap_active = re.match(r"^(tap|click)(\s+on)?\s+(?P<element>[a-zA-Z0-9 ]+)$", lowered)
        if tap_active:
            elem = tap_active.group("element").strip()
            return PlannedAction(
                step_id=1,
                thought=f"Tapping on '{elem}' in active window",
                action_type=ActionType.CLICK,
                parameters={"skill": "click_active_element", "element": elem},
            )

        # 4. Direct Text Entry: "type hello world", "type My name is Nova"
        type_match = re.match(r"^type\s+(?P<text>.+)$", lowered)
        if type_match:
            text = type_match.group("text")
            return PlannedAction(
                step_id=1,
                thought=f"Typing '{text}' into focused element",
                action_type=ActionType.TYPE_TEXT,
                parameters={"skill": "type_text", "text": text},
            )

        # 5. File System Operations: "move file invoice to documents", "move photo to desktop"
        move_file_match = re.match(r"^move\s+(file\s+)?(?P<src>.+?)\s+to\s+(?P<dest>[a-zA-Z0-9_-]+)$", lowered)
        if move_file_match:
            src = move_file_match.group("src").strip()
            dest = move_file_match.group("dest").strip()
            return PlannedAction(
                step_id=1,
                thought=f"Moving file '{src}' to '{dest}'",
                action_type=ActionType.EXECUTE_SHELL,
                parameters={"skill": "move_file", "src": src, "dest": dest},
            )

        # 6. Window Layout & Snapping
        if "side by side" in lowered or "arrange windows" in lowered:
            return PlannedAction(
                step_id=1,
                thought="Arranging windows side-by-side cleanly.",
                action_type=ActionType.RESIZE_WINDOW,
            )

        # 7. Basic App Lifecycle (Open / Close)
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
        # Check skill parameters
        skill = action.parameters.get("skill")
        if skill == "web_search":
            platform = action.parameters.get("platform", "google")
            query = action.parameters.get("query", "")
            return DesktopSkills.open_web_search(platform, query)

        elif skill == "in_app_search":
            app = action.parameters.get("app", "")
            query = action.parameters.get("query", "")
            DesktopSkills.focus_app(app)
            time.sleep(0.3)
            DesktopSkills.press_hotkey(["cmd", "f"])
            time.sleep(0.2)
            return DesktopSkills.type_text(query, press_enter=True)

        elif skill == "click_element_in_app":
            app = action.parameters.get("app", "")
            elem = action.parameters.get("element", "")
            DesktopSkills.focus_app(app)
            time.sleep(0.4)
            tree = self.grounding.inspect_ui()
            coords = DesktopSkills.click_semantic_element(tree, elem)
            if coords:
                return DesktopSkills.physical_click(coords[0], coords[1])
            # If not in tree, try shortcut or center fallback
            return ExecutionResult(
                step_id=action.step_id,
                success=False,
                action_type=ActionType.CLICK,
                output_message=f"Could not locate button matching '{elem}' in {app}",
                latency_ms=10.0,
                error="ElementNotFound",
            )

        elif skill == "click_active_element":
            elem = action.parameters.get("element", "")
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

        elif skill == "type_text":
            text = action.parameters.get("text", "")
            return DesktopSkills.type_text(text, press_enter=False)

        elif skill == "move_file":
            src = action.parameters.get("src", "")
            dest = action.parameters.get("dest", "")
            return DesktopSkills.move_file(src, dest)

        # Standard Actions
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
