"""Production-grade Native Desktop Skill Engine for N.O.V.A.

Implements real OS-level automation for:
- Web navigation & search (YouTube, Google, Docs)
- Deep application targeting & auto-focus
- Native typing, keyboard shortcuts, and text entry
- Dictionary word lookup via dict:// URL scheme
- WhatsApp messaging flow (search contact → open chat → type message → send)
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

    # =========================================================================
    # WEB SEARCH
    # =========================================================================

    @staticmethod
    def open_web_search(platform_name: str, query: str) -> ExecutionResult:
        """Opens search queries directly in the default browser."""
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

            return ExecutionResult(
                step_id=1, success=True, action_type=ActionType.LAUNCH_APP,
                output_message=f"Opened {platform_name.title()} search for '{query}'",
                latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
            )
        except Exception as e:
            return ExecutionResult(
                step_id=1, success=False, action_type=ActionType.LAUNCH_APP,
                output_message=f"Failed to open web search: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000, error=str(e),
            )

    # =========================================================================
    # WEBSITE OPENING
    # =========================================================================

    @staticmethod
    def open_website_in_browser(site_name: str, browser: str = "Google Chrome") -> ExecutionResult:
        """Resolves any website name (facebook, fb, twitter, etc.) and opens it in Chrome."""
        clean = site_name.strip().lower()
        site_map = {
            "fb": "https://www.facebook.com",
            "facebook": "https://www.facebook.com",
            "insta": "https://www.instagram.com",
            "instagram": "https://www.instagram.com",
            "twitter": "https://www.x.com",
            "x": "https://www.x.com",
            "whatsapp": "https://web.whatsapp.com",
            "whatsapp web": "https://web.whatsapp.com",
            "yt": "https://www.youtube.com",
            "youtube": "https://www.youtube.com",
            "netflix": "https://www.netflix.com",
            "amazon": "https://www.amazon.com",
            "reddit": "https://www.reddit.com",
            "github": "https://www.github.com",
            "chatgpt": "https://chatgpt.com",
            "openai": "https://chatgpt.com",
            "linkedin": "https://www.linkedin.com",
            "spotify": "https://open.spotify.com",
            "gmail": "https://mail.google.com",
            "g-mail": "https://mail.google.com",
            "docs": "https://docs.google.com",
            "google docs": "https://docs.google.com",
            "google word": "https://docs.google.com",
            "drive": "https://drive.google.com",
            "google drive": "https://drive.google.com",
            "wikipedia": "https://www.wikipedia.org",
            "pinterest": "https://www.pinterest.com",
            "twitch": "https://www.twitch.tv",
            "tiktok": "https://www.tiktok.com",
            "discord": "https://discord.com",
            "notion": "https://www.notion.so",
            "figma": "https://www.figma.com",
            "canva": "https://www.canva.com",
            "meet": "https://meet.google.com",
            "google meet": "https://meet.google.com",
            "maps": "https://maps.google.com",
            "google maps": "https://maps.google.com",
        }

        if clean in site_map:
            url = site_map[clean]
        elif clean.startswith("http://") or clean.startswith("https://"):
            url = clean
        elif "." in clean:
            url = f"https://{clean}"
        else:
            url = f"https://www.{clean}.com"

        return DesktopSkills.navigate_active_tab(url)

    # =========================================================================
    # DICTIONARY LOOKUP
    # =========================================================================

    @staticmethod
    def lookup_dictionary(word: str) -> ExecutionResult:
        """Looks up a word definition using the macOS dict:// URL scheme."""
        start_time = time.perf_counter()

        # Clean the word — strip filler, verbs, prepositions
        clean_word = word.strip().strip(".?!,'\"")
        clean_word = re.sub(
            r"\b(what is the meaning of|what does|meaning of|definition of|define|search for|search|"
            r"look up|type|just|open|and|in the dictionary|on the dictionary|in dictionary|on dictionary|"
            r"the dictionary|dictionary|mean|word|the|a|for|of|is|what)\b",
            " ", clean_word, flags=re.IGNORECASE,
        )
        clean_word = re.sub(r"\s+", " ", clean_word).strip()
        if not clean_word:
            clean_word = "help"  # Safe fallback

        try:
            if sys.platform == "darwin":
                # Strategy 1: dict:// URL scheme (opens Dictionary.app directly to the word)
                dict_url = f"dict://{urllib.parse.quote(clean_word)}"
                res = subprocess.run(["open", dict_url], capture_output=True, timeout=3)
                if res.returncode == 0:
                    return ExecutionResult(
                        step_id=1, success=True, action_type=ActionType.LAUNCH_APP,
                        output_message=f"Looked up '{clean_word}' in Dictionary",
                        latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                    )

                # Strategy 2: Open Dictionary.app + search manually
                try:
                    subprocess.run(["open", "-a", "Dictionary"], capture_output=True, timeout=3)
                    time.sleep(0.5)
                    script = '''
                    tell application "Dictionary" to activate
                    delay 0.3
                    tell application "System Events"
                        tell process "Dictionary"
                            set frontmost to true
                            keystroke "f" using command down
                            delay 0.1
                            keystroke "a" using command down
                        end tell
                    end tell
                    '''
                    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
                    time.sleep(0.15)
                    DesktopSkills.type_text(clean_word, press_enter=True)
                    return ExecutionResult(
                        step_id=1, success=True, action_type=ActionType.LAUNCH_APP,
                        output_message=f"Looked up '{clean_word}' in Dictionary",
                        latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                    )
                except Exception:
                    pass

                # Strategy 3: Fallback to Google define
                google_url = f"https://www.google.com/search?q=define+{urllib.parse.quote_plus(clean_word)}"
                return DesktopSkills.navigate_active_tab(google_url)
            else:
                return DesktopSkills.open_web_search("google", f"define {clean_word}")
        except Exception as e:
            google_url = f"https://www.google.com/search?q=define+{urllib.parse.quote_plus(clean_word)}"
            return DesktopSkills.navigate_active_tab(google_url)

    # =========================================================================
    # APP FOCUS
    # =========================================================================

    @staticmethod
    def focus_app(app_name: str) -> bool:
        """Brings the designated application to the foreground."""
        clean_name = app_name.strip()
        try:
            if sys.platform == "darwin":
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
                    "spotify": "Spotify",
                    "discord": "Discord",
                    "telegram": "Telegram",
                    "messages": "Messages",
                    "mail": "Mail",
                    "calendar": "Calendar",
                    "photos": "Photos",
                    "preview": "Preview",
                    "terminal": "Terminal",
                    "iterm": "iTerm2",
                    "iterm2": "iTerm2",
                    "slack": "Slack",
                    "zoom": "zoom.us",
                    "music": "Music",
                }
                target = alias_map.get(clean_name.lower(), clean_name)
                script = f'tell application "{target}" to activate'
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

    # =========================================================================
    # TEXT TYPING
    # =========================================================================

    @staticmethod
    def type_text(text: str, press_enter: bool = False, use_clipboard: bool = False) -> ExecutionResult:
        """Types text into the currently focused field. Uses clipboard paste for reliability."""
        start_time = time.perf_counter()
        try:
            if sys.platform == "darwin":
                # Use clipboard for long text, punctuation, or when explicitly requested
                if use_clipboard or len(text) > 15 or any(c in text for c in ['"', "'", "\n", "\\", ",", ";"]):
                    p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                    p.communicate(text.encode("utf-8"))
                    time.sleep(0.04)
                    enter_cmd = "key code 36" if press_enter else ""
                    script = f'''
                    tell application "System Events"
                        keystroke "v" using command down
                        {enter_cmd}
                    end tell
                    '''
                    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
                else:
                    escaped = text.replace('"', '\\"')
                    enter_cmd = "key code 36" if press_enter else ""
                    script = f'''
                    tell application "System Events"
                        keystroke "{escaped}"
                        {enter_cmd}
                    end tell
                    '''
                    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)

                return ExecutionResult(
                    step_id=1, success=True, action_type=ActionType.TYPE_TEXT,
                    output_message=f"Typed '{text}'",
                    latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1, success=False, action_type=ActionType.TYPE_TEXT,
                output_message=f"Failed to type text: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000, error=str(e),
            )

    @staticmethod
    def type_in_app(text: str, app_name: Optional[str] = None, press_enter: bool = True) -> ExecutionResult:
        """Focuses target application and enters text. In browsers, focuses address bar first."""
        if app_name:
            DesktopSkills.focus_app(app_name)
            time.sleep(0.3)
            if any(b in app_name.lower() for b in ["chrome", "safari", "browser"]):
                DesktopSkills.press_hotkey(["command", "l"])
                time.sleep(0.15)
                return DesktopSkills.type_text(text, press_enter=True)
        return DesktopSkills.type_text(text, press_enter=press_enter)

    # =========================================================================
    # BROWSER NAVIGATION
    # =========================================================================

    @staticmethod
    def _ensure_browser_running() -> str:
        """Ensures at least one browser is running."""
        if sys.platform != "darwin":
            return "default"
        try:
            check_script = '''
            tell application "System Events"
                set isChrome to (name of processes) contains "Google Chrome"
                set isSafari to (name of processes) contains "Safari"
            end tell
            if isChrome then return "chrome"
            else if isSafari then return "safari"
            else return "none"
            end if
            '''
            res = subprocess.run(["osascript", "-e", check_script], capture_output=True, text=True, timeout=5)
            result = res.stdout.strip().lower()
            if result == "none":
                subprocess.Popen(["open", "-a", "Google Chrome"])
                time.sleep(1.0)
                return "chrome"
            return result
        except Exception:
            try:
                subprocess.Popen(["open", "-a", "Google Chrome"])
                time.sleep(1.0)
            except Exception:
                pass
            return "chrome"

    @staticmethod
    def navigate_active_tab(target_query: str) -> ExecutionResult:
        """Navigates the CURRENT active browser tab to a URL."""
        start_time = time.perf_counter()
        clean = target_query.strip().rstrip(".?!,'\"")

        # Resolve destination URL
        if clean.lower() in ["youtube", "youtube.com", "www.youtube.com"]:
            url = "https://www.youtube.com"
        elif "youtube" in clean.lower():
            q = re.sub(r"\b(youtube|search|on|for|the|tab|this)\b", "", clean, flags=re.IGNORECASE).strip()
            url = f"https://www.youtube.com/results?search_query={urllib.parse.quote_plus(q)}" if q else "https://www.youtube.com"
        elif clean.startswith("http://") or clean.startswith("https://"):
            url = clean
        elif "." in clean and " " not in clean:
            url = f"https://{clean}"
        else:
            url = f"https://www.google.com/search?q={urllib.parse.quote_plus(clean)}"

        try:
            if sys.platform == "darwin":
                DesktopSkills._ensure_browser_running()

                nav_script = f'''
                tell application "System Events"
                    set isChrome to (name of processes) contains "Google Chrome"
                    set isSafari to (name of processes) contains "Safari"
                end tell
                if isChrome then
                    tell application "Google Chrome"
                        activate
                        if (count of windows) > 0 then
                            set URL of active tab of front window to "{url}"
                            return "ok"
                        else
                            open location "{url}"
                            return "ok"
                        end if
                    end tell
                else if isSafari then
                    tell application "Safari"
                        activate
                        if (count of windows) > 0 then
                            set URL of current tab of front window to "{url}"
                            return "ok"
                        else
                            open location "{url}"
                            return "ok"
                        end if
                    end tell
                else
                    do shell script "open " & quoted form of "{url}"
                    return "ok"
                end if
                '''
                res = subprocess.run(["osascript", "-e", nav_script], capture_output=True, text=True)
                if "ok" in res.stdout:
                    return ExecutionResult(
                        step_id=1, success=True, action_type=ActionType.LAUNCH_APP,
                        output_message=f"Navigated to {url}",
                        latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                    )

                # Fallback: Cmd+L then type URL
                DesktopSkills.press_hotkey(["command", "l"])
                time.sleep(0.1)
                DesktopSkills.type_text(url, press_enter=True)
                return ExecutionResult(
                    step_id=1, success=True, action_type=ActionType.LAUNCH_APP,
                    output_message=f"Navigated to {url}",
                    latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1, success=False, action_type=ActionType.LAUNCH_APP,
                output_message=f"Navigation failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000, error=str(e),
            )

    @staticmethod
    def switch_browser_tab(tab_number: int) -> ExecutionResult:
        """Switches to a specific browser tab by index."""
        start_time = time.perf_counter()
        try:
            if sys.platform == "darwin":
                script = f'''
                tell application "System Events"
                    set isChrome to (name of processes) contains "Google Chrome"
                    set isSafari to (name of processes) contains "Safari"
                end tell
                if isChrome then
                    tell application "Google Chrome"
                        activate
                        if (count of windows) > 0 then
                            set active tab index of front window to {tab_number}
                            return "ok"
                        end if
                    end tell
                else if isSafari then
                    tell application "Safari"
                        activate
                        if (count of windows) > 0 then
                            set current tab of front window to tab {tab_number}
                            return "ok"
                        end if
                    end tell
                end if
                return "fallback"
                '''
                res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
                if "ok" in res.stdout:
                    return ExecutionResult(
                        step_id=1, success=True, action_type=ActionType.KEY_COMBINATION,
                        output_message=f"Switched to tab {tab_number}",
                        latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                    )

                # Fallback: Cmd+number
                if 1 <= tab_number <= 9:
                    DesktopSkills.press_hotkey(["command", str(tab_number)])
                    return ExecutionResult(
                        step_id=1, success=True, action_type=ActionType.KEY_COMBINATION,
                        output_message=f"Switched to tab {tab_number}",
                        latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                    )
        except Exception as e:
            return ExecutionResult(
                step_id=1, success=False, action_type=ActionType.KEY_COMBINATION,
                output_message=f"Tab switch failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000, error=str(e),
            )

    # =========================================================================
    # KEYBOARD SHORTCUTS
    # =========================================================================

    @staticmethod
    def press_hotkey(keys: List[str]) -> ExecutionResult:
        """Dispatches keyboard shortcuts via AppleScript."""
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

                target_key = keys[-1].lower()
                key_codes = {
                    "enter": 36, "return": 36, "space": 49, "tab": 48,
                    "escape": 53, "down": 125, "up": 126, "left": 123,
                    "right": 124, "delete": 51, "backspace": 51,
                }

                if target_key in key_codes:
                    key_action = f"key code {key_codes[target_key]} {mod_str}"
                else:
                    key_action = f'keystroke "{target_key}" {mod_str}'

                script = f'''
                tell application "System Events"
                    {key_action}
                end tell
                '''
                subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
                return ExecutionResult(
                    step_id=1, success=True, action_type=ActionType.KEY_COMBINATION,
                    output_message=f"Pressed {'+'.join(keys)}",
                    latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1, success=False, action_type=ActionType.KEY_COMBINATION,
                output_message=f"Hotkey failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000, error=str(e),
            )

    # =========================================================================
    # SEMANTIC UI CLICKING
    # =========================================================================

    @staticmethod
    def click_semantic_element(tree: UINode, target_label: str) -> Optional[Tuple[float, float, str]]:
        """Finds an interactive UI node matching target_label and returns its center."""
        label_clean = target_label.lower().strip()
        interactive_nodes = tree.flatten_interactive()

        # Exact match
        for node in interactive_nodes:
            name = (node.name or "").lower().strip()
            desc = (node.description or "").lower().strip()
            if label_clean == name or label_clean == desc:
                return (node.bounding_box.center[0], node.bounding_box.center[1], node.id)

        # Substring match
        for node in interactive_nodes:
            name = (node.name or "").lower().strip()
            desc = (node.description or "").lower().strip()
            if label_clean in name or label_clean in desc:
                return (node.bounding_box.center[0], node.bounding_box.center[1], node.id)

        # Fuzzy synonyms
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
        """Dispatches OS-level mouse click at (x, y)."""
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
                    step_id=1, success=True, action_type=ActionType.CLICK,
                    output_message=f"Clicked at ({int(x)}, {int(y)})",
                    latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1, success=False, action_type=ActionType.CLICK,
                output_message=f"Click failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000, error=str(e),
            )

    # =========================================================================
    # FILE OPERATIONS
    # =========================================================================

    @staticmethod
    def move_file(source_name: str, target_dir_name: str) -> ExecutionResult:
        """Finds and moves a file to the target directory."""
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
                step_id=1, success=False, action_type=ActionType.EXECUTE_SHELL,
                output_message=f"Could not find file matching '{source_name}'",
                latency_ms=(time.perf_counter() - start_time) * 1000, error="FileNotFound",
            )

        try:
            target_path = dest_dir / found_source.name
            shutil.move(str(found_source), str(target_path))
            return ExecutionResult(
                step_id=1, success=True, action_type=ActionType.EXECUTE_SHELL,
                output_message=f"Moved '{found_source.name}' to '{dest_dir.name}'",
                latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
            )
        except Exception as e:
            return ExecutionResult(
                step_id=1, success=False, action_type=ActionType.EXECUTE_SHELL,
                output_message=f"Move failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000, error=str(e),
            )

    # =========================================================================
    # SYSTEM CONTROLS
    # =========================================================================

    @staticmethod
    def system_control(action: str) -> ExecutionResult:
        """Controls system hardware: volume, mute, screenshot."""
        start_time = time.perf_counter()
        try:
            if sys.platform == "darwin":
                if action == "volume_up":
                    subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) + 12)"], check=True)
                    msg = "Increased volume."
                elif action == "volume_down":
                    subprocess.run(["osascript", "-e", "set volume output volume ((output volume of (get volume settings)) - 12)"], check=True)
                    msg = "Decreased volume."
                elif action == "mute":
                    subprocess.run(["osascript", "-e", "set volume with output muted"], check=True)
                    msg = "Muted."
                elif action == "unmute":
                    subprocess.run(["osascript", "-e", "set volume without output muted"], check=True)
                    msg = "Unmuted."
                elif action == "screenshot":
                    desktop = Path.home() / "Desktop"
                    out_path = desktop / f"Screenshot_{int(time.time())}.png"
                    subprocess.run(["screencapture", "-x", str(out_path)], check=True)
                    msg = f"Screenshot saved: {out_path.name}"
                else:
                    msg = f"System control '{action}' executed."

                return ExecutionResult(
                    step_id=1, success=True, action_type=ActionType.EXECUTE_SHELL,
                    output_message=msg,
                    latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1, success=False, action_type=ActionType.EXECUTE_SHELL,
                output_message=f"System control failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000, error=str(e),
            )

    # =========================================================================
    # SCROLLING
    # =========================================================================

    @staticmethod
    def scroll(direction: str = "down", amount: int = 5) -> ExecutionResult:
        """Scrolls the active window."""
        start_time = time.perf_counter()
        try:
            if sys.platform == "darwin":
                try:
                    import Quartz
                    delta = -amount if direction == "down" else amount
                    event = Quartz.CGEventCreateScrollWheelEvent(None, Quartz.kCGScrollEventUnitLine, 1, delta)
                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                except ImportError:
                    code = 121 if direction == "down" else 116
                    subprocess.run(["osascript", "-e", f'tell application "System Events" to key code {code}'], capture_output=True)

                return ExecutionResult(
                    step_id=1, success=True, action_type=ActionType.SCROLL,
                    output_message=f"Scrolled {direction}",
                    latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1, success=False, action_type=ActionType.SCROLL,
                output_message=f"Scroll failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000, error=str(e),
            )

    # =========================================================================
    # BROWSER & EDIT CONTROLS
    # =========================================================================

    @staticmethod
    def browser_control(action: str) -> ExecutionResult:
        key_map = {
            "new_tab": ["command", "t"],
            "close_tab": ["command", "w"],
            "next_tab": ["control", "tab"],
            "prev_tab": ["control", "shift", "tab"],
            "refresh": ["command", "r"],
        }
        return DesktopSkills.press_hotkey(key_map.get(action, ["command", "r"]))

    @staticmethod
    def edit_action(action: str) -> ExecutionResult:
        key_map = {
            "copy": ["command", "c"],
            "paste": ["command", "v"],
            "cut": ["command", "x"],
            "undo": ["command", "z"],
            "redo": ["command", "shift", "z"],
            "save": ["command", "s"],
            "select_all": ["command", "a"],
        }
        return DesktopSkills.press_hotkey(key_map.get(action, ["command", "s"]))

    # =========================================================================
    # PHOTO INSERTION
    # =========================================================================

    @staticmethod
    def insert_photo_into_doc(photo_query: str) -> ExecutionResult:
        """Finds an image file, copies to clipboard, pastes into active doc."""
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
                step_id=1, success=False, action_type=ActionType.TYPE_TEXT,
                output_message=f"No photo found matching '{photo_query}'",
                latency_ms=(time.perf_counter() - start_time) * 1000, error="PhotoNotFound",
            )

        try:
            if sys.platform == "darwin":
                script = f'set the clipboard to (read (POSIX file "{found_img.resolve()}") as JPEG picture)'
                subprocess.run(["osascript", "-e", script], capture_output=True)
                time.sleep(0.1)
                DesktopSkills.press_hotkey(["command", "v"])
                return ExecutionResult(
                    step_id=1, success=True, action_type=ActionType.TYPE_TEXT,
                    output_message=f"Inserted '{found_img.name}' into document.",
                    latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1, success=False, action_type=ActionType.TYPE_TEXT,
                output_message=f"Photo insert failed: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000, error=str(e),
            )

    # =========================================================================
    # WHATSAPP & MESSAGING FLOW
    # =========================================================================

    @staticmethod
    def send_message_flow(app: str, contact: str, message: str) -> ExecutionResult:
        """Full messaging flow: activate app → search contact → open chat → type message → send.

        WhatsApp-specific flow uses Cmd+K (native search), then navigates to chat.
        """
        start_time = time.perf_counter()
        target_app = "WhatsApp" if app.lower() == "whatsapp" else app.title()
        clean_contact = re.sub(r"\b(contact|person|user)\b", "", contact, flags=re.IGNORECASE).strip()
        is_whatsapp = target_app == "WhatsApp"

        if sys.platform != "darwin":
            return DesktopSkills.type_text(message, press_enter=True)

        # === Step 1: Activate the app ===
        try:
            script = f'tell application "{target_app}" to activate'
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                subprocess.Popen(["open", "-a", target_app])
        except Exception:
            subprocess.Popen(["open", "-a", target_app])

        # Wait for app to come to foreground
        time.sleep(1.0)

        if is_whatsapp:
            # === WhatsApp Flow ===
            # Step 2: Open search with Cmd+K (WhatsApp native search)
            try:
                search_script = '''
                tell application "System Events"
                    tell process "WhatsApp"
                        set frontmost to true
                    end tell
                end tell
                '''
                subprocess.run(["osascript", "-e", search_script], capture_output=True, timeout=3)
                time.sleep(0.3)
            except Exception:
                pass

            # Try Cmd+K first, then Cmd+F as fallback
            DesktopSkills.press_hotkey(["command", "k"])
            time.sleep(0.4)

            # Step 3: Type contact name
            DesktopSkills.type_text(clean_contact, press_enter=False, use_clipboard=True)
            time.sleep(1.0)  # Wait for search results to populate

            # Step 4: Select first search result with Down arrow + Enter
            select_script = '''
            tell application "System Events"
                tell process "WhatsApp"
                    set frontmost to true
                    key code 125  -- Down arrow
                    delay 0.3
                    key code 36   -- Return (open the chat)
                end tell
            end tell
            '''
            try:
                subprocess.run(["osascript", "-e", select_script], capture_output=True, timeout=5)
            except Exception as e:
                logger.warning(f"WhatsApp contact selection failed: {e}")
            time.sleep(0.8)

            # Step 5: Focus message input area
            # Strategy A: Try clicking the message input box at the bottom of the window
            try:
                pos_script = '''
                tell application "System Events"
                    tell process "WhatsApp"
                        set {wx, wy} to position of window 1
                        set {ww, wh} to size of window 1
                        return "" & wx & "," & wy & "," & ww & "," & wh
                    end tell
                end tell
                '''
                pos_res = subprocess.run(["osascript", "-e", pos_script], capture_output=True, text=True, timeout=3)
                if pos_res.returncode == 0 and "," in pos_res.stdout:
                    parts = [float(p.strip()) for p in pos_res.stdout.strip().split(",")]
                    wx, wy, ww, wh = parts[0], parts[1], parts[2], parts[3]
                    # Click on the message input box (bottom center of chat area, right side)
                    input_x = wx + (ww * 0.6)
                    input_y = wy + wh - 50
                    DesktopSkills.physical_click(input_x, input_y)
                    time.sleep(0.3)
            except Exception as e:
                logger.debug(f"WhatsApp click fallback: {e}")

            # Strategy B: Also try Tab key cycling to message input
            try:
                tab_script = '''
                tell application "System Events"
                    tell process "WhatsApp"
                        set frontmost to true
                        key code 48  -- Tab
                        delay 0.15
                        key code 48  -- Tab
                    end tell
                end tell
                '''
                subprocess.run(["osascript", "-e", tab_script], capture_output=True, timeout=3)
            except Exception:
                pass
            time.sleep(0.2)

            # Step 6: Type message and press Enter to send
            DesktopSkills.type_text(message, press_enter=True, use_clipboard=True)

            return ExecutionResult(
                step_id=1, success=True, action_type=ActionType.TYPE_TEXT,
                output_message=f"Sent '{message}' to '{clean_contact}' on WhatsApp",
                latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
            )

        else:
            # === Generic messaging app flow ===
            DesktopSkills.press_hotkey(["command", "f"])
            time.sleep(0.25)
            DesktopSkills.press_hotkey(["command", "a"])
            time.sleep(0.1)
            DesktopSkills.type_text(clean_contact, press_enter=False)
            time.sleep(0.6)

            # Navigate to first result
            open_script = f'''
            tell application "System Events"
                tell process "{target_app}"
                    set frontmost to true
                    key code 125 -- Down arrow
                    delay 0.2
                    key code 36  -- Return
                    delay 0.3
                end tell
            end tell
            '''
            subprocess.run(["osascript", "-e", open_script], capture_output=True)
            time.sleep(0.4)

            # Try clicking message input
            try:
                pos_script = f'''
                tell application "System Events"
                    tell process "{target_app}"
                        set {{wx, wy}} to position of window 1
                        set {{ww, wh}} to size of window 1
                        return "" & wx & "," & wy & "," & ww & "," & wh
                    end tell
                end tell
                '''
                pos_res = subprocess.run(["osascript", "-e", pos_script], capture_output=True, text=True)
                if pos_res.returncode == 0 and "," in pos_res.stdout:
                    parts = [float(p.strip()) for p in pos_res.stdout.strip().split(",")]
                    wx, wy, ww, wh = parts[0], parts[1], parts[2], parts[3]
                    DesktopSkills.physical_click(wx + 150, wy + 140)
                    time.sleep(0.3)
                    DesktopSkills.physical_click(wx + (ww / 2), wy + wh - 40)
                    time.sleep(0.2)
            except Exception:
                pass

            DesktopSkills.type_text(message, press_enter=True, use_clipboard=True)

            return ExecutionResult(
                step_id=1, success=True, action_type=ActionType.TYPE_TEXT,
                output_message=f"Sent '{message}' to '{clean_contact}' on {target_app}",
                latency_ms=(time.perf_counter() - start_time) * 1000, state_mutated=True,
            )
