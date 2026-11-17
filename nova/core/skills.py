"""Production-grade Native Desktop Skill Engine for N.O.V.A.

Implements real OS-level automation for:
- Web navigation & search (YouTube, Google, Docs)
- Deep application targeting & auto-focus
- Native typing, keyboard shortcuts, and text entry
- Semantic UI element finding & physical clicking
- File system search and file transfer
"""

import logging
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from nova.core.types import ActionType, BoundingBox, ExecutionResult, PlannedAction, UINode

logger = logging.getLogger("nova.core.skills")


class DesktopSkills:
    """Universal cross-app execution skills running on native OS APIs."""

    @staticmethod
    def open_web_search(platform_name: str, query: str) -> ExecutionResult:
        """Opens search queries directly in the user's default browser (YouTube, Google, etc.)."""
        start_time = time.perf_counter()
        encoded_query = urllib.parse.quote_plus(query.strip())

        urls = {
            "youtube": f"https://www.youtube.com/results?search_query={encoded_query}",
            "google": f"https://www.google.com/search?q={encoded_query}",
            "reddit": f"https://www.reddit.com/search/?q={encoded_query}",
            "github": f"https://github.com/search?q={encoded_query}",
        }

        url = urls.get(platform_name.lower(), f"https://www.google.com/search?q={encoded_query}")

        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", url])
            elif sys.platform == "win32":
                subprocess.Popen(["start", url], shell=True)
            else:
                subprocess.Popen(["xdg-open", url])

            latency = (time.perf_counter() - start_time) * 1000
            return ExecutionResult(
                step_id=1,
                success=True,
                action_type=ActionType.LAUNCH_APP,
                output_message=f"Opened {platform_name.title()} search for '{query}'",
                latency_ms=latency,
                state_mutated=True,
            )
        except Exception as e:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.LAUNCH_APP,
                output_message=f"Failed to open web search: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    @staticmethod
    def focus_app(app_name: str) -> bool:
        """Brings the designated application window to the foreground."""
        clean_name = app_name.strip()
        try:
            if sys.platform == "darwin":
                # Check for standard app aliases
                alias_map = {
                    "word": "Microsoft Word",
                    "google word": "Microsoft Word",
                    "docs": "Google Chrome",
                    "whatsapp": "WhatsApp",
                    "notes": "Notes",
                    "finder": "Finder",
                    "safari": "Safari",
                    "chrome": "Google Chrome",
                    "code": "Visual Studio Code",
                    "vs code": "Visual Studio Code",
                }
                target = alias_map.get(clean_name.lower(), clean_name)
                script = f'''
                tell application "{target}"
                    activate
                end tell
                '''
                res = subprocess.run(["osascript", "-e", script], capture_output=True, timeout=3)
                if res.returncode == 0:
                    time.sleep(0.3)
                    return True
                # Fallback to open -a
                subprocess.Popen(["open", "-a", target])
                time.sleep(0.4)
                return True
            elif sys.platform == "win32":
                subprocess.Popen(["start", clean_name], shell=True)
                return True
        except Exception as e:
            logger.warning(f"Failed to focus app '{clean_name}': {e}")
        return False

    @staticmethod
    def type_text(text: str, press_enter: bool = False) -> ExecutionResult:
        """Types text cleanly into the currently focused input field."""
        start_time = time.perf_counter()
        try:
            if sys.platform == "darwin":
                # Escape quotes in text
                escaped = text.replace('"', '\\"')
                enter_cmd = 'key code 36' if press_enter else ''
                script = f'''
                tell application "System Events"
                    keystroke "{escaped}"
                    {enter_cmd}
                end tell
                '''
                subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
                return ExecutionResult(
                    step_id=1,
                    success=True,
                    action_type=ActionType.TYPE_TEXT,
                    output_message=f"Typed '{text}'",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.TYPE_TEXT,
                output_message=f"Failed to type text: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    @staticmethod
    def press_hotkey(keys: List[str]) -> ExecutionResult:
        """Dispatches keyboard shortcuts (e.g. Cmd+F, Return, Tab, Cmd+V)."""
        start_time = time.perf_counter()
        try:
            if sys.platform == "darwin":
                key_lower = [k.lower() for k in keys]
                using_modifiers = []
                if "cmd" in key_lower or "command" in key_lower:
                    using_modifiers.append("command down")
                if "ctrl" in key_lower or "control" in key_lower:
                    using_modifiers.append("control down")
                if "shift" in key_lower:
                    using_modifiers.append("shift down")
                if "alt" in key_lower or "option" in key_lower:
                    using_modifiers.append("option down")

                mod_str = f"using {{{', '.join(using_modifiers)}}}" if using_modifiers else ""

                # Target key
                target_key = keys[-1].lower()
                if target_key in ["enter", "return"]:
                    key_action = f"key code 36 {mod_str}"
                elif target_key == "space":
                    key_action = f"key code 49 {mod_str}"
                elif target_key == "tab":
                    key_action = f"key code 48 {mod_str}"
                elif target_key == "escape":
                    key_action = f"key code 53 {mod_str}"
                else:
                    key_action = f'keystroke "{target_key}" {mod_str}'

                script = f'''
                tell application "System Events"
                    {key_action}
                end tell
                '''
                subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
                return ExecutionResult(
                    step_id=1,
                    success=True,
                    action_type=ActionType.KEY_COMBINATION,
                    output_message=f"Pressed hotkey {'+'.join(keys)}",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.KEY_COMBINATION,
                output_message=f"Hotkey failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    @staticmethod
    def click_semantic_element(tree: UINode, target_label: str) -> Optional[Tuple[float, float, str]]:
        """Searches the UI tree for an interactive node matching target_label and returns its center coordinates."""
        label_clean = target_label.lower().strip()
        interactive_nodes = tree.flatten_interactive()

        # 1. Exact match
        for node in interactive_nodes:
            name = (node.name or "").lower().strip()
            desc = (node.description or "").lower().strip()
            if label_clean == name or label_clean == desc:
                return (node.bounding_box.center[0], node.bounding_box.center[1], node.id)

        # 2. Substring match
        for node in interactive_nodes:
            name = (node.name or "").lower().strip()
            desc = (node.description or "").lower().strip()
            if label_clean in name or label_clean in desc:
                return (node.bounding_box.center[0], node.bounding_box.center[1], node.id)

        # 3. Fuzzy synonyms (e.g. create -> new, blank)
        synonyms = {
            "create": ["new", "blank", "add", "+"],
            "search": ["find", "filter", "query", "magnifyingglass"],
            "send": ["submit", "paperplane", "post"],
        }
        for syn in synonyms.get(label_clean, []):
            for node in interactive_nodes:
                name = (node.name or "").lower().strip()
                if syn in name:
                    return (node.bounding_box.center[0], node.bounding_box.center[1], node.id)

        return None

    @staticmethod
    def physical_click(x: float, y: float) -> ExecutionResult:
        """Dispatches an OS-level physical mouse click at (x, y)."""
        start_time = time.perf_counter()
        try:
            if sys.platform == "darwin":
                import Quartz
                point = Quartz.CGPointMake(x, y)
                down = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft)
                up = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
                time.sleep(0.05)
                Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
                return ExecutionResult(
                    step_id=1,
                    success=True,
                    action_type=ActionType.CLICK,
                    output_message=f"Clicked at coordinates ({int(x)}, {int(y)})",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.CLICK,
                output_message=f"Click failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    @staticmethod
    def move_file(source_name: str, target_dir_name: str) -> ExecutionResult:
        """Finds a local file and moves it to the target directory hands-free."""
        start_time = time.perf_counter()
        user_home = Path.home()
        common_dirs = {
            "downloads": user_home / "Downloads",
            "documents": user_home / "Documents",
            "desktop": user_home / "Desktop",
            "pictures": user_home / "Pictures",
        }

        dest_dir = common_dirs.get(target_dir_name.lower().strip(), user_home / target_dir_name)
        if not dest_dir.exists():
            dest_dir.mkdir(parents=True, exist_ok=True)

        # Search for source file across home directories
        found_source: Optional[Path] = None
        for search_dir in [user_home / "Downloads", user_home / "Desktop", user_home / "Documents"]:
            try:
                if search_dir.exists():
                    for p in search_dir.glob(f"*{source_name}*"):
                        if p.is_file():
                            found_source = p
                            break
            except (PermissionError, OSError):
                continue
            if found_source:
                break

        if not found_source:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.EXECUTE_SHELL,
                output_message=f"Could not locate file matching '{source_name}'",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error="FileNotFound",
            )

        try:
            target_path = dest_dir / found_source.name
            shutil.move(str(found_source), str(target_path))
            return ExecutionResult(
                step_id=1,
                success=True,
                action_type=ActionType.EXECUTE_SHELL,
                output_message=f"Moved '{found_source.name}' to '{dest_dir.name}'",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                state_mutated=True,
            )
        except Exception as e:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.EXECUTE_SHELL,
                output_message=f"Failed to move file: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    @staticmethod
    def system_control(action: str) -> ExecutionResult:
        """Controls system hardware settings: volume, mute, screenshot, display."""
        start_time = time.perf_counter()
        try:
            if sys.platform == "darwin":
                if action == "volume_up":
                    cmd = "set volume output volume ((output volume of (get volume settings)) + 12)"
                    subprocess.run(["osascript", "-e", cmd], check=True)
                    msg = "Increased system volume."
                elif action == "volume_down":
                    cmd = "set volume output volume ((output volume of (get volume settings)) - 12)"
                    subprocess.run(["osascript", "-e", cmd], check=True)
                    msg = "Decreased system volume."
                elif action == "mute":
                    subprocess.run(["osascript", "-e", "set volume with output muted"], check=True)
                    msg = "Muted system audio."
                elif action == "unmute":
                    subprocess.run(["osascript", "-e", "set volume without output muted"], check=True)
                    msg = "Unmuted system audio."
                elif action == "screenshot":
                    desktop = Path.home() / "Desktop"
                    out_path = desktop / f"Screenshot_{int(time.time())}.png"
                    subprocess.run(["screencapture", "-x", str(out_path)], check=True)
                    msg = f"Saved screenshot to Desktop: {out_path.name}"
                else:
                    msg = f"System control '{action}' executed."

                return ExecutionResult(
                    step_id=1,
                    success=True,
                    action_type=ActionType.EXECUTE_SHELL,
                    output_message=msg,
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.EXECUTE_SHELL,
                output_message=f"System control failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    @staticmethod
    def scroll(direction: str = "down", amount: int = 5) -> ExecutionResult:
        """Scrolls the active window content."""
        start_time = time.perf_counter()
        try:
            if sys.platform == "darwin":
                try:
                    import Quartz
                    delta = -amount if direction == "down" else amount
                    event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, delta)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                except ImportError:
                    # Fallback to key code Page Down (121) or Page Up (116)
                    code = 121 if direction == "down" else 116
                    subprocess.run(["osascript", "-e", f'tell application "System Events" to key code {code}'], capture_output=True)

                return ExecutionResult(
                    step_id=1,
                    success=True,
                    action_type=ActionType.SCROLL,
                    output_message=f"Scrolled {direction}",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.SCROLL,
                output_message=f"Scroll failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    @staticmethod
    def browser_control(action: str) -> ExecutionResult:
        """Automates browser tabs, reloading, and navigation."""
        key_map = {
            "new_tab": ["command", "t"],
            "close_tab": ["command", "w"],
            "next_tab": ["control", "tab"],
            "prev_tab": ["control", "shift", "tab"],
            "refresh": ["command", "r"],
        }
        keys = key_map.get(action, ["command", "r"])
        return DesktopSkills.press_hotkey(keys)

    @staticmethod
    def edit_action(action: str) -> ExecutionResult:
        """Executes clipboard, selection, and document editing shortcuts."""
        key_map = {
            "copy": ["command", "c"],
            "paste": ["command", "v"],
            "cut": ["command", "x"],
            "undo": ["command", "z"],
            "redo": ["command", "shift", "z"],
            "save": ["command", "s"],
            "select_all": ["command", "a"],
        }
        keys = key_map.get(action, ["command", "s"])
        return DesktopSkills.press_hotkey(keys)

    @staticmethod
    def insert_photo_into_doc(photo_query: str) -> ExecutionResult:
        """Locates an image file on disk, copies it to clipboard, and pastes it into the active doc."""
        start_time = time.perf_counter()
        user_home = Path.home()
        search_dirs = [user_home / "Pictures", user_home / "Downloads", user_home / "Desktop"]

        found_img = None
        for d in search_dirs:
            try:
                if d.exists():
                    for ext in ["*.png", "*.jpg", "*.jpeg", "*.webp"]:
                        for img in d.glob(ext):
                            if not photo_query or photo_query.lower() in img.name.lower():
                                found_img = img
                                break
                        if found_img:
                            break
            except (PermissionError, OSError):
                continue
            if found_img:
                break

        if not found_img:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.TYPE_TEXT,
                output_message=f"No photo found matching '{photo_query}' in Pictures/Downloads/Desktop",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error="PhotoNotFound",
            )

        try:
            if sys.platform == "darwin":
                # Copy image file to macOS clipboard via AppleScript
                as_cmd = f'''
                set the clipboard to (read (POSIX file "{found_img.resolve()}") as JPEG picture)
                '''
                subprocess.run(["osascript", "-e", as_cmd], capture_output=True)
                time.sleep(0.1)
                # Paste into active document
                DesktopSkills.press_hotkey(["command", "v"])
                return ExecutionResult(
                    step_id=1,
                    success=True,
                    action_type=ActionType.TYPE_TEXT,
                    output_message=f"Copied and inserted '{found_img.name}' into active document.",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.TYPE_TEXT,
                output_message=f"Failed to insert photo: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    @staticmethod
    def send_message_flow(app: str, contact: str, message: str) -> ExecutionResult:
        """Brings messaging app to front, searches contact, and sends the message."""
        start_time = time.perf_counter()
        DesktopSkills.focus_app(app)
        time.sleep(0.35)
        # Search contact via Cmd+F
        DesktopSkills.press_hotkey(["command", "f"])
        time.sleep(0.2)
        DesktopSkills.type_text(contact, press_enter=True)
        time.sleep(0.35)
        # Focus chat input, type message, and hit Return
        DesktopSkills.type_text(message, press_enter=True)
        return ExecutionResult(
            step_id=1,
            success=True,
            action_type=ActionType.TYPE_TEXT,
            output_message=f"Sent message to '{contact}' on {app.title()}: \"{message}\"",
            latency_ms=(time.perf_counter() - start_time) * 1000,
            state_mutated=True,
        )

