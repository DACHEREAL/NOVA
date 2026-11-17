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
    def open_website_in_browser(site_name: str, browser: str = "Google Chrome") -> ExecutionResult:
        """Resolves any website or web app (facebook, fb, twitter, amazon, etc.) and opens it in Chrome/Safari."""
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
        }

        if clean in site_map:
            url = site_map[clean]
        elif clean.startswith("http://") or clean.startswith("https://"):
            url = clean
        elif "." in clean:
            url = f"https://{clean}"
        else:
            url = f"https://www.{clean}.com"

        start_time = time.perf_counter()
        target_browser = "Google Chrome"
        if "safari" in browser.lower():
            target_browser = "Safari"

        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-a", target_browser, url])
            elif sys.platform == "win32":
                subprocess.Popen(["start", target_browser, url], shell=True)
            else:
                subprocess.Popen(["xdg-open", url])

            return ExecutionResult(
                step_id=1,
                success=True,
                action_type=ActionType.LAUNCH_APP,
                output_message=f"Opened {clean} ({url}) in {target_browser}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                state_mutated=True,
            )
        except Exception as e:
            return DesktopSkills.navigate_active_tab(url)

    @staticmethod
    def lookup_dictionary(word: str) -> ExecutionResult:
        """Looks up a word definition using the dict:// URL scheme, AppleScript, or Google fallback."""
        start_time = time.perf_counter()
        clean_word = word.strip().strip(".?!,'\"")
        clean_word = re.sub(
            r"\b(what is the meaning of|what does|meaning of|definition of|define|search for|search|look up|type|just|open|and|in the dictionary|on the dictionary|in dictionary|on dictionary|the dictionary|dictionary|mean|word|the|a|for|of|is|what)\b",
            " ",
            clean_word,
            flags=re.IGNORECASE,
        )
        clean_word = re.sub(r"\s+", " ", clean_word).strip()
        if not clean_word:
            clean_word = "help"

        try:
            if sys.platform == "darwin":
                # Strategy 1: Try the dict:// URL scheme (opens Dictionary.app directly to the word)
                dict_url = f"dict://{urllib.parse.quote(clean_word)}"
                res = subprocess.run(["open", dict_url], capture_output=True, timeout=3)
                if res.returncode == 0:
                    return ExecutionResult(
                        step_id=1,
                        success=True,
                        action_type=ActionType.LAUNCH_APP,
                        output_message=f"Looked up '{clean_word}' in Dictionary",
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                        state_mutated=True,
                    )

                # Strategy 2: Open Dictionary.app directly and search via clipboard
                try:
                    subprocess.run(["open", "-a", "Dictionary"], capture_output=True, timeout=3)
                    time.sleep(0.4)
                    # Copy word to clipboard and paste into Dictionary search bar
                    p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                    p.communicate(clean_word.encode("utf-8"))
                    time.sleep(0.05)
                    script = '''
                    tell application "Dictionary"
                        activate
                    end tell
                    delay 0.2
                    tell application "System Events"
                        tell process "Dictionary"
                            set frontmost to true
                            keystroke "f" using command down
                            delay 0.1
                            keystroke "a" using command down
                            delay 0.05
                            keystroke "v" using command down
                            delay 0.05
                            key code 36
                        end tell
                    end tell
                    '''
                    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
                    return ExecutionResult(
                        step_id=1,
                        success=True,
                        action_type=ActionType.LAUNCH_APP,
                        output_message=f"Looked up '{clean_word}' in Dictionary",
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                        state_mutated=True,
                    )
                except Exception:
                    pass

                # Strategy 3: Fallback to Google define search in browser
                logger.info(f"Dictionary app unavailable, falling back to Google define for '{clean_word}'")
                google_url = f"https://www.google.com/search?q=define+{urllib.parse.quote_plus(clean_word)}"
                return DesktopSkills.navigate_active_tab(google_url)
            else:
                return DesktopSkills.open_web_search("google", f"define {clean_word}")
        except Exception as e:
            # Ultimate fallback: Google search
            logger.warning(f"Dictionary lookup failed for '{clean_word}': {e}")
            google_url = f"https://www.google.com/search?q=define+{urllib.parse.quote_plus(clean_word)}"
            return DesktopSkills.navigate_active_tab(google_url)

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
                # Instant non-blocking open -a (<10ms)
                subprocess.Popen(["open", "-a", target])
                try:
                    subprocess.Popen(["osascript", "-e", f'tell application "{target}" to activate'])
                except Exception:
                    pass
                time.sleep(0.15)
                return True
            elif sys.platform == "win32":
                subprocess.Popen(["start", clean_name], shell=True)
                return True
        except Exception as e:
            logger.warning(f"Failed to focus app '{clean_name}': {e}")
        return False

    @staticmethod
    def type_text(text: str, press_enter: bool = False, use_clipboard: bool = False) -> ExecutionResult:
        """Types text cleanly into the currently focused input field.

        For sentences, punctuation, or dictation, uses pbcopy + Cmd+V for 100% fidelity.
        """
        start_time = time.perf_counter()
        try:
            if sys.platform == "darwin":
                # For dictation, sentences, or special characters, use clipboard paste for 100% reliability
                if use_clipboard or len(text) > 15 or any(c in text for c in ['"', "'", "\n", "\\", ",", ";"]):
                    p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
                    p.communicate(text.encode("utf-8"))
                    time.sleep(0.04)
                    enter_cmd = 'key code 36' if press_enter else ''
                    script = f'''
                    tell application "System Events"
                        keystroke "v" using command down
                        {enter_cmd}
                    end tell
                    '''
                    subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
                else:
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
    def type_in_app(text: str, app_name: Optional[str] = None, press_enter: bool = True) -> ExecutionResult:
        """Focuses target application and enters text. In browsers, focuses address/search bar first."""
        if app_name:
            DesktopSkills.focus_app(app_name)
            time.sleep(0.3)
            # If target is a browser (Chrome, Safari), focus the address/search bar first
            if any(b in app_name.lower() for b in ["chrome", "safari", "browser"]):
                DesktopSkills.press_hotkey(["command", "l"])
                time.sleep(0.15)
                # Determine if the text is a search term vs a URL
                # Search terms: no dots, no protocol prefix, contains spaces or is a plain word
                is_search_term = (
                    "." not in text
                    and not text.lower().startswith("http://")
                    and not text.lower().startswith("https://")
                )
                if is_search_term:
                    # Type search term directly into the address bar and press Enter (triggers search)
                    return DesktopSkills.type_text(text, press_enter=True)
                else:
                    # It looks like a URL, type it and press Enter to navigate
                    return DesktopSkills.type_text(text, press_enter=True)
        return DesktopSkills.type_text(text, press_enter=press_enter)

    @staticmethod
    def _ensure_browser_running() -> str:
        """Ensures at least one browser is running. Returns the browser name that is running."""
        if sys.platform != "darwin":
            return "default"
        try:
            check_script = '''
            tell application "System Events"
                set isChrome to (name of processes) contains "Google Chrome"
                set isSafari to (name of processes) contains "Safari"
            end tell
            if isChrome then
                return "chrome"
            else if isSafari then
                return "safari"
            else
                return "none"
            end if
            '''
            res = subprocess.run(["osascript", "-e", check_script], capture_output=True, text=True, timeout=5)
            result = res.stdout.strip().lower()
            if result == "none":
                # Neither browser is running; launch Chrome
                logger.info("No browser running, launching Google Chrome")
                subprocess.Popen(["open", "-a", "Google Chrome"])
                time.sleep(1.0)
                return "chrome"
            return result
        except Exception as e:
            logger.warning(f"Failed to check browser status: {e}")
            # Try launching Chrome as a fallback
            try:
                subprocess.Popen(["open", "-a", "Google Chrome"])
                time.sleep(1.0)
            except Exception:
                pass
            return "chrome"

    @staticmethod
    def navigate_active_tab(target_query: str) -> ExecutionResult:
        """Navigates the CURRENT active browser tab to a URL or YouTube/Google search without opening new tabs."""
        start_time = time.perf_counter()
        clean = target_query.strip().strip(".?!,'\"")

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
                # Ensure at least one browser is running before attempting navigation
                DesktopSkills._ensure_browser_running()

                as_nav = f'''
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
                res = subprocess.run(["osascript", "-e", as_nav], capture_output=True, text=True)
                if "ok" in res.stdout:
                    return ExecutionResult(
                        step_id=1,
                        success=True,
                        action_type=ActionType.LAUNCH_APP,
                        output_message=f"Navigated active tab to {url}",
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                        state_mutated=True,
                    )

                # Fallback: Focus address bar (Cmd+L), type URL, hit Return
                DesktopSkills.press_hotkey(["command", "l"])
                time.sleep(0.1)
                DesktopSkills.type_text(url, press_enter=True)
                return ExecutionResult(
                    step_id=1,
                    success=True,
                    action_type=ActionType.LAUNCH_APP,
                    output_message=f"Navigated active tab to {url}",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    state_mutated=True,
                )
        except Exception as e:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.LAUNCH_APP,
                output_message=f"Failed to navigate tab: {e}",
                latency_ms=(time.perf_counter() - start_time) * 1000,
                error=str(e),
            )

    @staticmethod
    def switch_browser_tab(tab_number: int) -> ExecutionResult:
        """Switches to a specific tab index (1st tab, 2nd tab, 3rd tab) in Chrome/Safari."""
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
                        step_id=1,
                        success=True,
                        action_type=ActionType.KEY_COMBINATION,
                        output_message=f"Switched to tab {tab_number}",
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                        state_mutated=True,
                    )

                # Fallback via hotkey: Cmd + tab_number (Cmd+1, Cmd+2, etc.)
                if 1 <= tab_number <= 9:
                    DesktopSkills.press_hotkey(["command", str(tab_number)])
                    return ExecutionResult(
                        step_id=1,
                        success=True,
                        action_type=ActionType.KEY_COMBINATION,
                        output_message=f"Switched to tab {tab_number} via Cmd+{tab_number}",
                        latency_ms=(time.perf_counter() - start_time) * 1000,
                        state_mutated=True,
                    )
        except Exception as e:
            return ExecutionResult(
                step_id=1,
                success=False,
                action_type=ActionType.KEY_COMBINATION,
                output_message=f"Failed to switch to tab {tab_number}: {e}",
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
                elif target_key == "down":
                    key_action = f"key code 125 {mod_str}"
                elif target_key == "up":
                    key_action = f"key code 126 {mod_str}"
                elif target_key == "left":
                    key_action = f"key code 123 {mod_str}"
                elif target_key == "right":
                    key_action = f"key code 124 {mod_str}"
                elif target_key == "delete" or target_key == "backspace":
                    key_action = f"key code 51 {mod_str}"
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
        """Brings messaging app to front, searches contact, reliably opens chat, and sends the message."""
        start_time = time.perf_counter()
        target_app = "WhatsApp" if app.lower() == "whatsapp" else app.title()
        clean_contact = re.sub(r"\b(contact|person|user)\b", "", contact, flags=re.IGNORECASE).strip()

        is_whatsapp = target_app == "WhatsApp"

        if sys.platform == "darwin":
            # --- Step 1: Activate / focus the app ---
            try:
                activate_script = f'''
                tell application "{target_app}"
                    activate
                end tell
                '''
                res = subprocess.run(
                    ["osascript", "-e", activate_script],
                    capture_output=True, text=True, timeout=5,
                )
                if res.returncode != 0:
                    # Fallback: try open -a
                    subprocess.Popen(["open", "-a", target_app])
            except Exception as e:
                logger.warning(f"Failed to activate {target_app}: {e}")
                subprocess.Popen(["open", "-a", target_app])

            # Wait for the app to come to foreground (longer for cold launch)
            is_fresh = False
            try:
                check_running = subprocess.run(
                    ["osascript", "-e", f'tell application "System Events" to (name of processes) contains "{target_app}"'],
                    capture_output=True, text=True, timeout=3,
                )
                if "false" in check_running.stdout.lower():
                    is_fresh = True
            except Exception:
                pass
            time.sleep(1.5 if is_fresh else 0.5)

            if is_whatsapp:
                # --- WhatsApp-specific flow using Cmd+K (native search) ---

                # Step 2: Open search with Cmd+K (WhatsApp for Mac native search shortcut)
                search_script = '''
                tell application "System Events"
                    tell process "WhatsApp"
                        set frontmost to true
                        keystroke "k" using command down
                    end tell
                end tell
                '''
                try:
                    subprocess.run(["osascript", "-e", search_script], capture_output=True, timeout=3)
                except Exception as e:
                    logger.warning(f"WhatsApp Cmd+K failed: {e}")
                    # Fallback to Cmd+F
                    DesktopSkills.press_hotkey(["command", "f"])
                time.sleep(0.3)

                # Step 3: Type contact name (allow search to populate)
                DesktopSkills.type_text(clean_contact, press_enter=False)
                time.sleep(0.8)

                # Step 4: Select first search result and ensure chat opens
                select_script = '''
                tell application "System Events"
                    tell process "WhatsApp"
                        set frontmost to true
                        key code 125  -- Down arrow to highlight first result
                        delay 0.15
                        key code 36   -- Return to open the chat
                    end tell
                end tell
                '''
                try:
                    subprocess.run(["osascript", "-e", select_script], capture_output=True, timeout=5)
                except Exception as e:
                    logger.warning(f"WhatsApp contact selection failed: {e}")
                time.sleep(0.3)

                # Step 5: Focus chat & message input via direct coordinate click
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
                    pos_res = subprocess.run(
                        ["osascript", "-e", pos_script],
                        capture_output=True, text=True, timeout=3,
                    )
                    if pos_res.returncode == 0 and "," in pos_res.stdout:
                        parts = [float(p.strip()) for p in pos_res.stdout.strip().split(",")]
                        wx, wy, ww, wh = parts[0], parts[1], parts[2], parts[3]
                        # Click first search result in left sidebar to guarantee opening chat
                        DesktopSkills.physical_click(wx + min(180, ww * 0.18), wy + 160)
                        time.sleep(0.3)
                        # Click message input box at bottom center of chat area
                        DesktopSkills.physical_click(wx + (ww * 0.65), wy + wh - 45)
                        time.sleep(0.2)
                except Exception as e:
                    logger.debug(f"WhatsApp physical click fallback failed: {e}")

                # Step 6: Type message and send
                DesktopSkills.type_text(message, press_enter=True, use_clipboard=True)

                return ExecutionResult(
                    step_id=1,
                    success=True,
                    action_type=ActionType.TYPE_TEXT,
                    output_message=f"Sent message to '{clean_contact}' on WhatsApp: \"{message}\"",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    state_mutated=True,
                )

            else:
                # --- Generic messaging app flow (Messages, Telegram, etc.) ---
                # Use Cmd+F for search
                DesktopSkills.press_hotkey(["command", "f"])
                time.sleep(0.25)

                # Clear any existing search text
                DesktopSkills.press_hotkey(["command", "a"])
                time.sleep(0.1)

                # Type contact name
                DesktopSkills.type_text(clean_contact, press_enter=False)
                time.sleep(0.6)

                # Navigate to first result and open it
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

                # Physical click fallback for contact selection and message input
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
                        # Click first search result
                        DesktopSkills.physical_click(wx + 150, wy + 140)
                        time.sleep(0.3)
                        # Click message input box at bottom
                        DesktopSkills.physical_click(wx + (ww / 2), wy + wh - 40)
                        time.sleep(0.2)
                except Exception:
                    pass

                # Type and send message
                DesktopSkills.type_text(message, press_enter=True, use_clipboard=True)

                return ExecutionResult(
                    step_id=1,
                    success=True,
                    action_type=ActionType.TYPE_TEXT,
                    output_message=f"Sent message to '{clean_contact}' on {target_app}: \"{message}\"",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                    state_mutated=True,
                )
        else:
            return DesktopSkills.type_text(message, press_enter=True)
