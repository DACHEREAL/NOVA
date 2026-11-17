"""Order-Independent Natural Language Intent Resolver for N.O.V.A.

Parses arbitrary, conversational, open-ended human speech regardless of word order,
slang, phrasing variations, or sentence structure into precise executable OS actions.

PRIORITY ORDER (critical — higher priority patterns are checked first):
1. Dictionary lookups (ANY mention of "dictionary" or "meaning of" or "define")
2. Messaging (send/search + contact + app compound commands)
3. Open website on browser
4. System controls (volume, screenshot)
5. Scrolling
6. Browser tab controls
7. Editing shortcuts
8. Web search
9. In-app messaging
10. Semantic clicking
11. Direct typing into apps
12. Plain typing
13. File operations
14. Window management
15. App lifecycle (open/close)
16. Fallback
"""

import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class ResolvedIntent:
    intent_type: str
    confidence: float
    parameters: Dict[str, Any] = field(default_factory=dict)
    thought: str = ""


class NaturalLanguageIntentResolver:
    """Robust, flexible NLP parser understanding human speech in any word order."""

    # Comprehensive set of known websites / web services
    KNOWN_WEBSITES = {
        "facebook", "fb", "instagram", "insta", "twitter", "x", "reddit",
        "youtube", "yt", "netflix", "amazon", "github", "chatgpt", "openai",
        "linkedin", "gmail", "g-mail", "wikipedia", "docs", "google docs",
        "google word", "drive", "google drive", "whatsapp web",
        "pinterest", "twitch", "tiktok", "snapchat", "threads", "quora",
        "medium", "stackoverflow", "stack overflow", "notion", "figma",
        "canva", "zoom", "meet", "google meet", "maps", "google maps",
        "spotify", "discord",
    }

    # Messaging apps
    MESSAGING_APPS = ["whatsapp", "telegram", "messages", "slack", "discord"]

    # App name aliases for detection
    APP_ALIASES = {
        "word": "Microsoft Word",
        "google word": "Microsoft Word",
        "notes": "Notes",
        "whatsapp": "WhatsApp",
        "finder": "Finder",
        "safari": "Safari",
        "chrome": "Google Chrome",
        "code": "Visual Studio Code",
        "vs code": "Visual Studio Code",
        "spotify": "Spotify",
        "discord": "Discord",
        "telegram": "Telegram",
        "slack": "Slack",
        "music": "Music",
        "photos": "Photos",
        "calendar": "Calendar",
        "mail": "Mail",
        "preview": "Preview",
        "terminal": "Terminal",
    }

    @classmethod
    def resolve(cls, utterance: str, active_app: Optional[str] = None) -> Optional[ResolvedIntent]:
        text = utterance.strip()
        # Clean leading wake word
        text = re.sub(r"^(hey\s+)?(nova|no\s*v?\s*a|no va|noa)[,;:\s!.\-]+", "", text, flags=re.IGNORECASE).strip()
        text_lower = text.lower().strip().rstrip(".?!,;:'\"")

        # Strip common filler phrases
        text_clean = re.sub(
            r"\b(can you|could you|please|would you mind|would you|i want you to|go ahead and|just|i need you to|go on)\b",
            "",
            text_lower,
            flags=re.IGNORECASE,
        ).strip()
        text_clean = re.sub(r"\s+", " ", text_clean)
        tokens = set(re.findall(r"\b\w+\b", text_clean))

        # === 1. DICTIONARY & WORD DEFINITIONS ===
        # HIGHEST PRIORITY: ANY mention of "dictionary", "meaning of", "define", "definition of"
        # e.g. "type help in dictionary", "search help in dictionary", "just type help in dictionary",
        #      "meaning of help", "define love", "what does resilience mean"
        dict_trigger = (
            "dictionary" in tokens
            or "meaning of" in text_clean
            or "definition of" in text_clean
            or text_clean.startswith("define ")
            or "what does" in text_clean and "mean" in tokens
            or "what is the meaning" in text_clean
        )
        if dict_trigger:
            word = cls._extract_dictionary_word(text_clean)
            if word:
                return ResolvedIntent(
                    "dictionary_lookup", 0.99,
                    {"word": word},
                    f"Looking up definition of '{word}' in Dictionary."
                )

        # === 2. COMPOUND MESSAGING COMMANDS ===
        # Must be checked BEFORE open_website and launch_app
        msg_result = cls._resolve_messaging(text_clean, tokens, active_app)
        if msg_result:
            return msg_result

        # === 3. OPEN WEBSITE ON BROWSER ===
        web_result = cls._resolve_open_website(text_clean, tokens)
        if web_result:
            return web_result

        # === 4. SYSTEM CONTROLS ===
        sys_result = cls._resolve_system_control(tokens)
        if sys_result:
            return sys_result

        # === 5. SCROLLING ===
        if "scroll" in tokens or "page" in tokens:
            if any(w in tokens for w in ["down", "bottom", "lower"]):
                return ResolvedIntent("scroll", 0.90, {"direction": "down", "amount": 5}, "Scrolling down.")
            if any(w in tokens for w in ["up", "top", "higher"]):
                return ResolvedIntent("scroll", 0.90, {"direction": "up", "amount": 5}, "Scrolling up.")

        # === 6. BROWSER TAB CONTROLS ===
        tab_result = cls._resolve_tab_controls(text_lower, text_clean, tokens)
        if tab_result:
            return tab_result

        # === 7. EDITING SHORTCUTS ===
        edit_result = cls._resolve_edit_actions(tokens)
        if edit_result:
            return edit_result

        # === 8. PHOTO INSERTION ===
        if any(w in tokens for w in ["insert", "place", "add"]) and any(w in tokens for w in ["photo", "image", "picture", "pic"]):
            photo_match = re.search(r"(photo|image|picture|pic)\s+(of\s+)?(?P<name>[a-zA-Z0-9_\- ]+)", text_lower)
            photo_name = photo_match.group("name").strip() if photo_match else ""
            return ResolvedIntent("insert_photo", 0.90, {"photo_name": photo_name},
                                  f"Inserting photo '{photo_name or 'recent'}' into document.")

        # === 9. WEB SEARCH ===
        search_result = cls._resolve_web_search(text_clean, text_lower, tokens)
        if search_result:
            return search_result

        # === 10. IN-APP SEARCH (messaging apps) ===
        inapp_result = cls._resolve_in_app_search(text_clean, text_lower, tokens, active_app)
        if inapp_result:
            return inapp_result

        # === 11. SEMANTIC UI CLICKING ===
        click_result = cls._resolve_click(text_lower, tokens)
        if click_result:
            return click_result

        # === 12. TYPING INTO SPECIFIC APP ===
        # "type mrbeast on chrome", "type hello in notes", "search mrbeast in chrome"
        type_app_match = re.search(
            r"^(type|write|search|enter)\s+(?P<text>.+?)\s+(on|in|into)\s+(?P<app>chrome|safari|browser|word|notes|whatsapp|google)",
            text_clean, flags=re.IGNORECASE,
        )
        if type_app_match:
            app_raw = type_app_match.group("app").lower()
            app_resolved = {
                "chrome": "Google Chrome", "browser": "Google Chrome", "google": "Google Chrome",
                "safari": "Safari", "word": "Microsoft Word",
            }.get(app_raw, app_raw.title())
            typed_text = type_app_match.group("text").strip().strip("'\"")
            return ResolvedIntent(
                "type_in_app", 0.95,
                {"app": app_resolved, "text": typed_text},
                f"Entering '{typed_text}' in {app_resolved}."
            )

        # === 13. PLAIN TYPING / DICTATION ===
        if any(w in tokens for w in ["type", "write", "dictate", "enter"]):
            type_match = re.search(
                r"^(type\s+this[:\s]*|write\s+this[:\s]*|dictate[:\s]*|type[:\s]*|write[:\s]*|enter[:\s]*)\s*(?P<text>.+)",
                text, flags=re.IGNORECASE,
            )
            if type_match:
                content = type_match.group("text").strip()
                return ResolvedIntent("type_text", 0.90, {"text": content}, f"Typing '{content}'.")
            words_after = re.sub(r"^(type|write|dictate|enter)\s+", "", text, flags=re.IGNORECASE).strip()
            if words_after:
                return ResolvedIntent("type_text", 0.90, {"text": words_after}, f"Typing '{words_after}'.")

        # === 14. FILE OPERATIONS ===
        if any(w in tokens for w in ["move", "transfer", "relocate"]):
            destinations = ["documents", "downloads", "desktop", "pictures", "music", "movies"]
            target_dest = next((d for d in destinations if d in tokens), "Documents")
            src_text = text_lower
            for d in destinations:
                src_text = src_text.replace(d, "")
            src_text = re.sub(r"\b(move|transfer|relocate|file|from|to|into|folder)\b", "", src_text).strip()
            if src_text:
                return ResolvedIntent("move_file", 0.90, {"src": src_text, "dest": target_dest},
                                      f"Moving '{src_text}' to {target_dest.title()}.")

        # === 15. WINDOW MANAGEMENT ===
        if any(w in text_lower for w in ["side by side", "arrange windows", "split screen", "snap left", "tile windows"]):
            return ResolvedIntent("window_layout", 0.95, {"action": "side_by_side"}, "Arranging windows side-by-side.")

        # === 16. APP LIFECYCLE (OPEN / CLOSE) ===
        if any(w in tokens for w in ["open", "launch", "start"]):
            app = text_lower
            app = re.sub(r"\b(open|launch|start|up|app|application|the)\b", "", app).strip()
            if app:
                # Check if it's a known website first
                if app in cls.KNOWN_WEBSITES or app.endswith((".com", ".org", ".net", ".io", ".co")):
                    return ResolvedIntent("open_website", 0.90, {"site": app}, f"Opening website '{app}'.")
                return ResolvedIntent("launch_app", 0.90, {"app_name": app}, f"Launching '{app}'.")

        if any(w in tokens for w in ["close", "quit", "terminate", "exit", "kill"]):
            app = text_lower
            app = re.sub(r"\b(close|quit|terminate|exit|kill|down|app|application|the)\b", "", app).strip()
            if app:
                return ResolvedIntent("terminate_app", 0.90, {"app_name": app}, f"Closing '{app}'.")

        # === 17. FALLBACK ===
        return ResolvedIntent("open_ended_task", 0.50, {"raw_intent": text}, f"Analyzing: '{text}'")

    # =========================================================================
    # HELPER METHODS
    # =========================================================================

    @classmethod
    def _extract_dictionary_word(cls, text: str) -> str:
        """Extracts the actual word to look up from dictionary-related commands."""
        word = text
        # Remove ALL action verbs, prepositions, articles, filler, and "dictionary"
        word = re.sub(
            r"\b(what is the meaning of|what does|meaning of|definition of|define|search for|search|"
            r"look up|look|type|write|enter|just|open|and|"
            r"in the dictionary|on the dictionary|in dictionary|on dictionary|the dictionary|dictionary|"
            r"mean|word|the|a|for|of|is|what|it|me|tell|give|show|find|up|help me|"
            r"can you|could you|please|would you|i want|go ahead|i need you to)\b",
            " ", word, flags=re.IGNORECASE,
        )
        word = re.sub(r"\s+", " ", word).strip()
        return word if word else ""

    @classmethod
    def _resolve_messaging(cls, text_clean: str, tokens: set, active_app: Optional[str]) -> Optional[ResolvedIntent]:
        """Resolves compound messaging commands like 'open whatsapp and send hi to frosty'."""
        _msg_app_pat = "|".join(cls.MESSAGING_APPS)

        # Pattern A: "open <app> and send <msg> to <contact>"
        m = re.search(
            rf"(?:open|launch)\s+(?P<app>{_msg_app_pat})\s+(?:and|then)?\s*(?:send|text|message|type)\s+(?P<msg>.+?)\s+to\s+(?P<contact>[a-zA-Z0-9 ]+)",
            text_clean, flags=re.IGNORECASE,
        )
        if m:
            return cls._make_send_intent(m.group("app"), m.group("contact"), m.group("msg"))

        # Pattern B: "open <app> and search <contact> and type/send <msg>"
        m = re.search(
            rf"(?:open|launch)\s+(?P<app>{_msg_app_pat})\s+(?:and|then)?\s*(?:search|find)(?:\s+for)?\s+(?P<contact>[a-zA-Z0-9 ]+?)(?:\s+contact)?\s+and\s+(?:type|send|say|message)\s+(?P<msg>.+)",
            text_clean, flags=re.IGNORECASE,
        )
        if m:
            return cls._make_send_intent(m.group("app"), m.group("contact"), m.group("msg"))

        # Pattern C: "search <contact> in/on <app> and type/send <msg>"
        m = re.search(
            rf"(?:search|find)(?:\s+for)?\s+(?P<contact>[a-zA-Z0-9 ]+?)(?:\s+contact)?\s+(?:in|on)\s+(?P<app>{_msg_app_pat})\s+and\s+(?:type|send|say|message)\s+(?P<msg>.+)",
            text_clean, flags=re.IGNORECASE,
        )
        if m:
            return cls._make_send_intent(m.group("app"), m.group("contact"), m.group("msg"))

        # Pattern D: "search <contact> [contact] and type/send <msg>" (contextual — uses active app)
        m = re.search(
            r"(?:search|find)(?:\s+for)?\s+(?P<contact>[a-zA-Z0-9 ]+?)(?:\s+contact)?\s+and\s+(?:type|send|say|message)\s+(?P<msg>.+)",
            text_clean, flags=re.IGNORECASE,
        )
        if m:
            app = active_app or "WhatsApp"
            return cls._make_send_intent(app, m.group("contact"), m.group("msg"))

        # Pattern E: "send <msg> to <contact> [on <app>]"
        m = re.search(
            r"(?:send|text|message)\s+(?P<msg>.+?)\s+to\s+(?P<contact>[a-zA-Z0-9 ]+?)(?:\s+(?:on|in)\s+(?P<app>\w+))?$",
            text_clean, flags=re.IGNORECASE,
        )
        if m and not any(w in tokens for w in ["search", "find", "google"]):
            app = m.group("app") or active_app or "WhatsApp"
            return cls._make_send_intent(app, m.group("contact"), m.group("msg"))

        # Pattern F: "tell <contact> [on <app>] [that/saying] <msg>"
        m = re.search(
            rf"(?:tell)\s+(?P<contact>[a-zA-Z0-9]+)\s+(?:on\s+(?P<app>{_msg_app_pat})\s+)?(?:that\s+|saying\s+)?(?P<msg>.+)",
            text_clean, flags=re.IGNORECASE,
        )
        if m:
            app = m.group("app") or active_app or "WhatsApp"
            msg = m.group("msg").strip()
            # Strip trailing "on <app>" from message
            msg = re.sub(rf"\s+(?:on|in)\s+(?:{_msg_app_pat})\s*$", "", msg, flags=re.IGNORECASE).strip()
            return cls._make_send_intent(app, m.group("contact"), msg)

        # Pattern G: "send/text <contact> <msg>" (simple two-part)
        m = re.search(
            r"^(?:send|text|message)\s+(?P<contact>[a-zA-Z0-9]+)\s+(?P<msg>.+)",
            text_clean, flags=re.IGNORECASE,
        )
        if m and not any(w in tokens for w in ["search", "find", "google", "to"]):
            contact = m.group("contact").strip()
            msg = m.group("msg").strip()
            app = active_app or "WhatsApp"
            # Check if app name is in msg and extract it
            for _ma in cls.MESSAGING_APPS:
                if _ma in tokens:
                    app = _ma.title() if _ma != "whatsapp" else "WhatsApp"
                    msg = re.sub(rf"\b(?:on|in)\s+{_ma}\b", "", msg, flags=re.IGNORECASE).strip()
                    break
            msg = re.sub(r"^(?:that\s+|saying\s+)", "", msg, flags=re.IGNORECASE).strip()
            if contact and msg:
                return cls._make_send_intent(app, contact, msg)

        return None

    @classmethod
    def _make_send_intent(cls, app: str, contact: str, message: str) -> ResolvedIntent:
        """Creates a standardized send_message intent."""
        contact = re.sub(r"\b(contact|person|user)\b", "", contact, flags=re.IGNORECASE).strip()
        app_clean = app.strip()
        if app_clean.lower() == "whatsapp":
            app_clean = "WhatsApp"
        elif app_clean.lower() not in ["whatsapp"]:
            app_clean = app_clean.title()
        return ResolvedIntent(
            "send_message", 0.98,
            {"app": app_clean, "contact": contact, "message": message.strip()},
            f"Sending '{message.strip()}' to '{contact}' on {app_clean}."
        )

    @classmethod
    def _resolve_open_website(cls, text_clean: str, tokens: set) -> Optional[ResolvedIntent]:
        """Resolves 'open facebook on chrome', 'open fb chrome', 'open facebook'."""

        # Explicit: "open <site> [on/in] chrome/safari/browser"
        m = re.search(
            r"^(?:open|go to|launch)\s+(?P<site>[a-zA-Z0-9_\-\. ]+?)\s+(?:(?:on|in)\s+)?(?:chrome|safari|browser|google)(?:\s+tab)?$",
            text_clean, flags=re.IGNORECASE,
        )
        if m:
            site = m.group("site").strip()
            if site and site.lower() not in ["chrome", "safari", "google", "browser"]:
                return ResolvedIntent("open_website", 0.96, {"site": site}, f"Opening '{site}' in Chrome.")

        # Reverse: "on chrome open <site>"
        m = re.search(
            r"^(?:on|in)\s+(?:chrome|safari|browser|google)\s+(?:open|go to|launch)\s+(?P<site>[a-zA-Z0-9_\-\. ]+)",
            text_clean, flags=re.IGNORECASE,
        )
        if m:
            site = m.group("site").strip()
            if site:
                return ResolvedIntent("open_website", 0.96, {"site": site}, f"Opening '{site}' in Chrome.")

        # Direct: "open facebook" where target is a known website
        m = re.search(r"^(?:open|go to|launch)\s+(?P<target>[a-zA-Z0-9_\-\. ]+)$", text_clean, flags=re.IGNORECASE)
        if m:
            target = m.group("target").strip().lower()
            if target in cls.KNOWN_WEBSITES or target.endswith((".com", ".org", ".net", ".io", ".co")):
                return ResolvedIntent("open_website", 0.95, {"site": target}, f"Opening '{target}'.")

        return None

    @classmethod
    def _resolve_system_control(cls, tokens: set) -> Optional[ResolvedIntent]:
        """Resolves volume, mute, screenshot commands."""
        if any(w in tokens for w in ["volume", "sound", "audio", "louder", "quieter", "mute", "unmute"]):
            if any(w in tokens for w in ["up", "increase", "raise", "higher", "louder", "boost"]):
                return ResolvedIntent("system_control", 0.95, {"action": "volume_up"}, "Increasing volume.")
            if any(w in tokens for w in ["down", "decrease", "lower", "quieter", "soft", "reduce"]):
                return ResolvedIntent("system_control", 0.95, {"action": "volume_down"}, "Decreasing volume.")
            if "unmute" in tokens:
                return ResolvedIntent("system_control", 0.95, {"action": "unmute"}, "Unmuting audio.")
            if "mute" in tokens or "silence" in tokens:
                return ResolvedIntent("system_control", 0.95, {"action": "mute"}, "Muting audio.")

        if any(w in tokens for w in ["screenshot", "screencap"]) or "screen capture" in " ".join(tokens):
            return ResolvedIntent("system_control", 0.95, {"action": "screenshot"}, "Taking screenshot.")

        return None

    @classmethod
    def _resolve_tab_controls(cls, text_lower: str, text_clean: str, tokens: set) -> Optional[ResolvedIntent]:
        """Resolves browser tab switching and navigation."""

        # Active tab navigation: "open youtube on this tab", "go to youtube on the tab"
        tab_phrases = ["on the tab", "on this tab", "in this tab", "in the tab", "current tab", "this tab"]
        if any(phrase in text_lower for phrase in tab_phrases):
            nav_query = text_clean
            for phrase in tab_phrases:
                nav_query = nav_query.replace(phrase, "")
            nav_query = re.sub(r"\b(open|go to|search for|search|look up)\b", "", nav_query, flags=re.IGNORECASE).strip()
            if nav_query:
                return ResolvedIntent("navigate_active_tab", 0.95, {"query": nav_query},
                                      f"Navigating tab to '{nav_query}'.")

        # Tab number switching: "go to 1st tab", "switch to 3rd tab", "first tab", "tab 1"
        # Strip trailing "from Xth" noise
        tab_text = re.sub(r"\s+from\s+(\d+(?:st|nd|rd|th)|first|second|third|fourth|fifth|last|\d+)\s*$", "", text_lower)

        num_map = {
            "1st": 1, "first": 1, "1": 1,
            "2nd": 2, "second": 2, "2": 2,
            "3rd": 3, "third": 3, "3": 3,
            "4th": 4, "fourth": 4, "4": 4,
            "5th": 5, "fifth": 5, "5": 5,
            "6th": 6, "sixth": 6, "6": 6,
            "7th": 7, "seventh": 7, "7": 7,
            "8th": 8, "eighth": 8, "8": 8,
            "9th": 9, "ninth": 9, "9": 9,
            "last": 9,
        }

        tab_match = (
            re.search(r"(?:go\s+to|switch\s+to|open)\s+(?:the\s+)?(?P<num>\d+(?:st|nd|rd|th)|first|second|third|fourth|fifth|last)\s+tab", tab_text, re.I)
            or re.search(r"tab\s+(?P<num>[1-9])", tab_text, re.I)
            or re.search(r"\b(?P<num>1st|2nd|3rd|4th|5th|6th|7th|8th|9th|first|second|third|fourth|fifth|last)\s+tab\b", tab_text, re.I)
        )
        if tab_match and ("tab" in tab_text.split() or "switch" in tab_text.split() or "go" in tab_text.split()):
            num_str = tab_match.group("num").lower()
            tab_idx = num_map.get(num_str)
            if tab_idx:
                return ResolvedIntent("switch_tab", 0.95, {"tab_number": tab_idx}, f"Switching to tab {tab_idx}.")

        # Generic browser controls
        if any(w in tokens for w in ["tab", "tabs", "reload", "refresh"]):
            if "new" in tokens:
                return ResolvedIntent("browser_control", 0.90, {"action": "new_tab"}, "Opening new tab.")
            if any(w in tokens for w in ["close", "kill"]):
                return ResolvedIntent("browser_control", 0.90, {"action": "close_tab"}, "Closing tab.")
            if any(w in tokens for w in ["next", "right"]) and "switch" not in tokens:
                return ResolvedIntent("browser_control", 0.90, {"action": "next_tab"}, "Next tab.")
            if any(w in tokens for w in ["previous", "prev", "left"]):
                return ResolvedIntent("browser_control", 0.90, {"action": "prev_tab"}, "Previous tab.")
            if any(w in tokens for w in ["reload", "refresh"]):
                return ResolvedIntent("browser_control", 0.90, {"action": "refresh"}, "Refreshing page.")

        return None

    @classmethod
    def _resolve_edit_actions(cls, tokens: set) -> Optional[ResolvedIntent]:
        """Resolves copy, paste, undo, redo, save shortcuts."""
        actions = {
            "copy": ("copy", "Copying selection."),
            "paste": ("paste", "Pasting from clipboard."),
            "cut": ("cut", "Cutting selection."),
            "undo": ("undo", "Undoing."),
            "redo": ("redo", "Redoing."),
            "save": ("save", "Saving."),
        }
        for keyword, (action, thought) in actions.items():
            if keyword in tokens:
                return ResolvedIntent("edit_action", 0.90, {"action": action}, thought)

        if "select" in tokens and "all" in tokens:
            return ResolvedIntent("edit_action", 0.90, {"action": "select_all"}, "Selecting all.")

        return None

    @classmethod
    def _resolve_web_search(cls, text_clean: str, text_lower: str, tokens: set) -> Optional[ResolvedIntent]:
        """Resolves web searches on YouTube, Google, Reddit, GitHub."""
        platforms = {"youtube": "youtube", "google": "google", "reddit": "reddit", "github": "github"}

        for p_key, p_name in platforms.items():
            if p_key in tokens:
                query = text_clean
                query = re.sub(rf"\b(?:on|in|from|using|at)?\s*{p_key}\b", "", query)
                query = re.sub(r"\b(search for|search|look up|look for|find|pull up|play|watch|google|show me|open|for)\b", "", query)
                query = re.sub(r"\b(and|the|a|video|videos|channel|please)\b", "", query)
                query = re.sub(r"\s+", " ", query).strip()
                if query:
                    return ResolvedIntent("web_search", 0.95, {"platform": p_name, "query": query},
                                          f"Searching {p_name.title()} for '{query}'.")
                else:
                    return ResolvedIntent("open_website", 0.85, {"site": p_name}, f"Opening {p_name.title()}.")

        # Generic: "search for X", "google X", "look up X"
        for prefix in ["search for ", "google ", "look up ", "find online "]:
            if text_lower.startswith(prefix):
                query = text_lower[len(prefix):].strip()
                if query:
                    return ResolvedIntent("web_search", 0.85, {"platform": "google", "query": query},
                                          f"Searching Google for '{query}'.")

        # Bare "search <query>"
        m = re.search(r"^search\s+(?P<query>.+)$", text_clean, re.I)
        if m:
            query = m.group("query").strip()
            if query:
                return ResolvedIntent("web_search", 0.80, {"platform": "google", "query": query},
                                      f"Searching Google for '{query}'.")

        return None

    @classmethod
    def _resolve_in_app_search(cls, text_clean: str, text_lower: str, tokens: set, active_app: Optional[str]) -> Optional[ResolvedIntent]:
        """Resolves in-app search/messaging for messaging apps."""
        for m_app in cls.MESSAGING_APPS:
            if m_app in tokens:
                # Send pattern
                send_match = re.search(
                    r"(send|text|message|tell)\s+(a\s+message\s+to\s+|to\s+)?(?P<contact>[a-zA-Z0-9 ]+?)\s+(saying\s+|that\s+)?(?P<msg>.+)",
                    text_lower,
                )
                if send_match and not any(w in tokens for w in ["search", "find"]):
                    contact = re.sub(rf"\b(on|in|{m_app})\b", "", send_match.group("contact"), re.I).strip()
                    msg = re.sub(rf"\b(on|in)\s+{m_app}\b", "", send_match.group("msg"), re.I).strip()
                    msg = re.sub(r"^(a\s+message\s+(saying|that|with)\s+|saying\s+|that\s+)", "", msg, re.I).strip()
                    if contact and msg:
                        return cls._make_send_intent(m_app, contact, msg)

                # Search pattern
                search_match = re.search(r"search\s+(for\s+)?(?P<query>[a-zA-Z0-9 ]+)", text_lower)
                if search_match:
                    query = search_match.group("query").replace(m_app, "").replace("in", "").replace("on", "").strip()
                    if query:
                        return ResolvedIntent("in_app_search", 0.95, {"app": m_app, "query": query},
                                              f"Searching '{query}' in {m_app.title()}.")

        return None

    @classmethod
    def _resolve_click(cls, text_lower: str, tokens: set) -> Optional[ResolvedIntent]:
        """Resolves semantic UI element clicking."""
        click_verbs = ["tap", "click", "press", "hit", "select", "choose"]
        if not any(v in tokens for v in click_verbs):
            return None

        app_names = [
            ("microsoft word", "Microsoft Word"), ("word", "Microsoft Word"),
            ("notes", "Notes"), ("whatsapp", "WhatsApp"),
            ("safari", "Safari"), ("chrome", "Google Chrome"),
            ("finder", "Finder"), ("slack", "Slack"),
        ]
        target_app = None
        for alias, formal in app_names:
            if alias in text_lower:
                target_app = formal
                break

        elem_text = text_lower
        for alias, _ in app_names:
            elem_text = elem_text.replace(alias, "")
        elem_text = re.sub(r"\b(tap|click|press|hit|select|choose|on|in|at|the|button|icon|tab)\b", "", elem_text).strip()

        if elem_text:
            return ResolvedIntent(
                "click_semantic", 0.90,
                {"element": elem_text, "app": target_app},
                f"Clicking '{elem_text}'" + (f" in {target_app}" if target_app else ".")
            )

        return None
