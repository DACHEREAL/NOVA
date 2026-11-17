"""Order-Independent Natural Language Intent Resolver for N.O.V.A.

Parses arbitrary, conversational, open-ended human speech regardless of word order,
slang, phrasing variations, or sentence structure into precise executable OS actions.
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

    @classmethod
    def resolve(cls, utterance: str, active_app: Optional[str] = None) -> Optional[ResolvedIntent]:
        text = utterance.strip()
        # Clean leading wake word if present
        text = re.sub(r"^(hey\s+)?(nova|no\s*a|no\s*v|no)[,;\s]+", "", text, flags=re.IGNORECASE).strip()
        text_lower = text.lower().strip().strip(".?!,'\"")

        # Strip common conversational pleasantries and filler phrases
        text_clean = re.sub(
            r"\b(can you|could you|please|would you mind|would you|i want you to|go ahead and|just|i need you to|go on|go to)\b",
            "",
            text_lower,
            flags=re.IGNORECASE,
        ).strip()
        text_clean = re.sub(r"\s+", " ", text_clean)
        tokens = set(re.findall(r"\b\w+\b", text_clean))

        # -------------------------------------------------------------
        # 1. DICTIONARY & WORD DEFINITIONS
        # E.g. "type help in dictionary", "meaning of help", "define help", "search help in dictionary"
        # -------------------------------------------------------------
        if "dictionary" in tokens or any(w in text_clean for w in ["meaning of", "definition of", "define ", "what does", "what is the meaning of"]):
            target_word = text_clean
            target_word = re.sub(
                r"\b(what is the meaning of|what does|meaning of|definition of|define|search for|search|look up|type|just|open|and|in the dictionary|on the dictionary|in dictionary|on dictionary|the dictionary|dictionary|mean|word|the|a|for|of|is|what)\b",
                " ",
                target_word,
                flags=re.IGNORECASE,
            )
            target_word = re.sub(r"\s+", " ", target_word).strip()
            if target_word:
                return ResolvedIntent(
                    "dictionary_lookup",
                    0.98,
                    {"word": target_word},
                    f"Looking up definition of '{target_word}' in Dictionary."
                )

        # -------------------------------------------------------------
        # 2. OPEN WEBSITE / WEB APP ON CHROME / BROWSER
        # E.g. "open facebook on chrome", "open fb on chrome", "open facebook chrome", "open fb chrome", "open facebook"
        # -------------------------------------------------------------
        known_websites = {
            "facebook", "fb", "instagram", "insta", "twitter", "x", "reddit",
            "youtube", "yt", "netflix", "amazon", "github", "chatgpt", "openai",
            "linkedin", "gmail", "g-mail", "wikipedia", "docs", "google docs",
            "google word", "drive", "google drive", "whatsapp web"
        }

        # Explicit website invocation: e.g. "open facebook on chrome", "open fb chrome"
        open_web_match = re.search(
            r"^(open|go to|launch)\s+(?P<site>[a-zA-Z0-9_\-\. ]+?)\s+((on|in)\s+)?(chrome|safari|browser|google)(\s+tab)?$",
            text_clean,
            flags=re.IGNORECASE,
        ) or re.search(
            r"^(on|in)\s+(chrome|safari|browser|google)\s+(open|go to|launch)\s+(?P<site>[a-zA-Z0-9_\-\. ]+)",
            text_clean,
            flags=re.IGNORECASE,
        )
        if open_web_match:
            site = open_web_match.group("site").strip()
            if site and site.lower() not in ["chrome", "safari", "google", "browser"]:
                return ResolvedIntent(
                    "open_website",
                    0.96,
                    {"site": site},
                    f"Opening website '{site}' in Chrome."
                )

        # Direct open web service: e.g. "open facebook", "open fb", "open reddit", "open google word"
        open_direct = re.search(r"^(open|go to|launch)\s+(?P<target>[a-zA-Z0-9_\-\. ]+)$", text_clean, flags=re.IGNORECASE)
        if open_direct:
            target = open_direct.group("target").strip().lower()
            if target in known_websites or target.endswith((".com", ".org", ".net", ".io", ".co")):
                return ResolvedIntent(
                    "open_website",
                    0.95,
                    {"site": target},
                    f"Opening website '{target}' in Chrome."
                )

        # -------------------------------------------------------------
        # 3. CHAINED & CONTEXTUAL IN-APP SEARCH & MESSAGE
        # E.g. "search frosty in whatsapp and type hi", "open whatsapp and send hi to frosty",
        # "open whatsapp and send frosty hi", "search for frosty contact and type hi", "send hi to frosty"
        # -------------------------------------------------------------
        # 3A: "open <app> and send <msg> to <contact>"
        m_open_send_to = re.search(
            r"(?:open|launch)\s+(?P<app>whatsapp|slack|telegram|messages)\s+(?:and|then)?\s*(?:send|text|message|type)\s+(?P<msg>.+?)\s+to\s+(?P<contact>[a-zA-Z0-9 ]+)",
            text_clean, flags=re.IGNORECASE
        )
        if m_open_send_to:
            app = m_open_send_to.group("app").strip()
            contact = re.sub(r"\b(contact|person|user)\b", "", m_open_send_to.group("contact"), flags=re.IGNORECASE).strip()
            msg = m_open_send_to.group("msg").strip()
            return ResolvedIntent(
                "send_message",
                0.98,
                {"app": app, "contact": contact, "message": msg},
                f"Opening {app.title()}, searching '{contact}', and sending '{msg}'."
            )

        # 3B: "open <app> and send <contact> <msg>"
        m_open_send = re.search(
            r"(?:open|launch)\s+(?P<app>whatsapp|slack|telegram|messages)\s+(?:and|then)?\s*(?:send|text|message|type)\s+(?P<contact>[a-zA-Z0-9 ]+?)\s+(?P<msg>.+)",
            text_clean, flags=re.IGNORECASE
        )
        if m_open_send and not m_open_send.group("contact").lower().startswith("to "):
            app = m_open_send.group("app").strip()
            contact = re.sub(r"\b(contact|person|user)\b", "", m_open_send.group("contact"), flags=re.IGNORECASE).strip()
            msg = m_open_send.group("msg").strip()
            return ResolvedIntent(
                "send_message",
                0.98,
                {"app": app, "contact": contact, "message": msg},
                f"Opening {app.title()}, searching '{contact}', and sending '{msg}'."
            )

        # 3C: "open <app> and search [for] <contact> and (type|send) <msg>"
        m_open_search = re.search(
            r"(?:open|launch)\s+(?P<app>whatsapp|slack|telegram|messages)\s+(?:and|then)?\s*(?:search|find)(?:\s+for)?\s+(?P<contact>[a-zA-Z0-9 ]+?)(?:\s+contact)?\s+and\s+(?:type|send|say|message)\s+(?P<msg>.+)",
            text_clean, flags=re.IGNORECASE
        )
        if m_open_search:
            app = m_open_search.group("app").strip()
            contact = re.sub(r"\b(contact|person|user)\b", "", m_open_search.group("contact"), flags=re.IGNORECASE).strip()
            msg = m_open_search.group("msg").strip()
            return ResolvedIntent(
                "send_message",
                0.98,
                {"app": app, "contact": contact, "message": msg},
                f"Opening {app.title()}, searching '{contact}', and sending '{msg}'."
            )

        # 3D: "search [for] <contact> in/on <app> and (type|send) <msg>"
        m_search_in = (
            re.search(
                r"(?:search|find)(?:\s+for)?\s+(?P<contact>[a-zA-Z0-9 ]+?)(?:\s+contact)?\s+(?:in|on)\s+(?P<app>whatsapp|slack|telegram|messages)\s+and\s+(?:type|send|say|message|tell\s+\w+)\s+(?P<msg>.+)",
                text_clean, flags=re.IGNORECASE
            )
            or re.search(
                r"(?:in|on)\s+(?P<app>whatsapp|slack|telegram|messages)\s+(?:search|find)(?:\s+for)?\s+(?P<contact>[a-zA-Z0-9 ]+?)(?:\s+contact)?\s+and\s+(?:type|send|say|message|tell\s+\w+)\s+(?P<msg>.+)",
                text_clean, flags=re.IGNORECASE
            )
        )
        if m_search_in:
            app = m_search_in.group("app").strip()
            contact = re.sub(r"\b(contact|person|user)\b", "", m_search_in.group("contact"), flags=re.IGNORECASE).strip()
            msg = m_search_in.group("msg").strip()
            return ResolvedIntent(
                "send_message",
                0.98,
                {"app": app, "contact": contact, "message": msg},
                f"In {app.title()}, searching '{contact}', and sending '{msg}'."
            )

        # 3E: Contextual: "search for <contact> [contact] and type/send <msg>" (when in WhatsApp or messaging app)
        m_contextual_search = re.search(
            r"(?:search|find)(?:\s+for)?\s+(?P<contact>[a-zA-Z0-9 ]+?)(?:\s+contact)?\s+and\s+(?:type|send|say|message|tell\s+\w+)\s+(?P<msg>.+)",
            text_clean, flags=re.IGNORECASE
        )
        if m_contextual_search:
            contact = re.sub(r"\b(contact|person|user)\b", "", m_contextual_search.group("contact"), flags=re.IGNORECASE).strip()
            msg = m_contextual_search.group("msg").strip()
            target_app = active_app or "WhatsApp"
            return ResolvedIntent(
                "send_message",
                0.98,
                {"app": target_app, "contact": contact, "message": msg},
                f"In {target_app}, searching '{contact}', and sending '{msg}'."
            )

        # 3F: Contextual: "send <msg> to <contact>" without app name
        m_send_to = re.search(
            r"(?:send|text|message|type)\s+(?P<msg>.+?)\s+to\s+(?P<contact>[a-zA-Z0-9 ]+)",
            text_clean, flags=re.IGNORECASE
        )
        if m_send_to and not any(w in tokens for w in ["search", "find", "google"]):
            contact = re.sub(r"\b(contact|person|user)\b", "", m_send_to.group("contact"), flags=re.IGNORECASE).strip()
            msg = m_send_to.group("msg").strip()
            target_app = active_app or "WhatsApp"
            return ResolvedIntent(
                "send_message",
                0.95,
                {"app": target_app, "contact": contact, "message": msg},
                f"Sending '{msg}' to '{contact}' in {target_app}."
            )

        # 3G: Contextual: "send <contact> <msg>" (e.g. "send frosty hi", "text frosty I will be late")
        m_send_contact = re.search(
            r"^(?:send|text|message|tell)\s+(?P<contact>[a-zA-Z0-9]+)\s+(?P<msg>.+)",
            text_clean, flags=re.IGNORECASE
        )
        if m_send_contact and not any(w in tokens for w in ["search", "find", "google", "to"]):
            contact = re.sub(r"\b(contact|person|user)\b", "", m_send_contact.group("contact"), flags=re.IGNORECASE).strip()
            msg = m_send_contact.group("msg").strip()
            target_app = active_app or "WhatsApp"
            return ResolvedIntent(
                "send_message",
                0.95,
                {"app": target_app, "contact": contact, "message": msg},
                f"Sending '{msg}' to '{contact}' in {target_app}."
            )

        # -------------------------------------------------------------
        # 4. SYSTEM AUDIO & HARDWARE CONTROLS
        # -------------------------------------------------------------
        if any(w in tokens for w in ["volume", "sound", "audio", "louder", "quieter", "mute", "unmute"]):
            if any(w in tokens for w in ["up", "increase", "raise", "higher", "louder", "boost"]):
                return ResolvedIntent("system_control", 0.95, {"action": "volume_up"}, "Increasing system volume.")
            if any(w in tokens for w in ["down", "decrease", "lower", "quieter", "soft", "reduce"]):
                return ResolvedIntent("system_control", 0.95, {"action": "volume_down"}, "Decreasing system volume.")
            if "unmute" in tokens:
                return ResolvedIntent("system_control", 0.95, {"action": "unmute"}, "Unmuting system audio.")
            if "mute" in tokens or "silence" in tokens:
                return ResolvedIntent("system_control", 0.95, {"action": "mute"}, "Muting system audio.")

        if any(w in tokens for w in ["screenshot", "screen capture", "screencap"]):
            return ResolvedIntent("system_control", 0.95, {"action": "screenshot"}, "Capturing screenshot to Desktop.")

        # -------------------------------------------------------------
        # 2. SCROLLING & NAVIGATION
        # -------------------------------------------------------------
        if "scroll" in tokens or "page" in tokens:
            if any(w in tokens for w in ["down", "bottom", "lower"]):
                return ResolvedIntent("scroll", 0.90, {"direction": "down", "amount": 5}, "Scrolling down the active page.")
            if any(w in tokens for w in ["up", "top", "higher"]):
                return ResolvedIntent("scroll", 0.90, {"direction": "up", "amount": 5}, "Scrolling up the active page.")

        # -------------------------------------------------------------
        # 3. BROWSER CONTROLS (TABS, NAVIGATION, ACTIVE TAB SEARCH)
        # -------------------------------------------------------------
        # Active tab navigation: "open youtube on the tab", "search mrbeast on this tab", "go to youtube on this tab"
        if any(phrase in text_lower for phrase in ["on the tab", "on this tab", "in this tab", "in the tab", "current tab", "this tab"]):
            nav_query = text_clean
            nav_query = re.sub(r"\b(on the tab|on this tab|in this tab|in the tab|current tab|this tab|open|go to|search for|search|look up)\b", "", nav_query, flags=re.IGNORECASE).strip()
            if nav_query:
                return ResolvedIntent(
                    "navigate_active_tab",
                    0.95,
                    {"query": nav_query},
                    f"Navigating active browser tab to '{nav_query}'."
                )

        # Tab index switching: "go to 1st tab", "go to 2nd tab", "switch to 3rd tab", "first tab", "tab 1"
        tab_num_match = re.search(r"\b(go to|switch to|open)?\s*(?P<num>1st|2nd|3rd|4th|5th|6th|7th|8th|9th|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|last|[1-9])\s*(tab)?\b", text_lower)
        if tab_num_match and ("tab" in tokens or "switch" in tokens or "go" in tokens):
            num_str = tab_num_match.group("num").lower()
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
            tab_idx = num_map.get(num_str)
            if tab_idx:
                return ResolvedIntent(
                    "switch_tab",
                    0.95,
                    {"tab_number": tab_idx},
                    f"Switching to browser tab {tab_idx}."
                )

        if any(w in tokens for w in ["tab", "tabs", "reload", "refresh"]):
            if "new" in tokens:
                return ResolvedIntent("browser_control", 0.90, {"action": "new_tab"}, "Opening new browser tab.")
            if any(w in tokens for w in ["close", "kill"]):
                return ResolvedIntent("browser_control", 0.90, {"action": "close_tab"}, "Closing current tab.")
            if any(w in tokens for w in ["next", "switch", "right"]):
                return ResolvedIntent("browser_control", 0.90, {"action": "next_tab"}, "Switching to next tab.")
            if any(w in tokens for w in ["previous", "prev", "left"]):
                return ResolvedIntent("browser_control", 0.90, {"action": "prev_tab"}, "Switching to previous tab.")
            if any(w in tokens for w in ["reload", "refresh"]):
                return ResolvedIntent("browser_control", 0.90, {"action": "refresh"}, "Reloading page.")

        # -------------------------------------------------------------
        # 4. EDITING SHORTCUTS (SELECT ALL, COPY, PASTE, UNDO, SAVE)
        # -------------------------------------------------------------
        if any(w in tokens for w in ["copy", "paste", "cut", "undo", "redo", "save"]):
            if "copy" in tokens:
                return ResolvedIntent("edit_action", 0.90, {"action": "copy"}, "Copying selected content to clipboard.")
            if "paste" in tokens:
                return ResolvedIntent("edit_action", 0.90, {"action": "paste"}, "Pasting from clipboard.")
            if "undo" in tokens:
                return ResolvedIntent("edit_action", 0.90, {"action": "undo"}, "Undoing previous action.")
            if "redo" in tokens:
                return ResolvedIntent("edit_action", 0.90, {"action": "redo"}, "Redoing previous action.")
            if "save" in tokens:
                return ResolvedIntent("edit_action", 0.90, {"action": "save"}, "Saving active document/file.")
            if "select" in tokens and "all" in tokens:
                return ResolvedIntent("edit_action", 0.90, {"action": "select_all"}, "Selecting all text/items.")

        # -------------------------------------------------------------
        # 5. PHOTO INSERTION INTO DOCS / NOTES
        # -------------------------------------------------------------
        if any(w in tokens for w in ["insert", "place", "add", "paste"]) and any(w in tokens for w in ["photo", "image", "picture", "screenshot", "pic"]):
            photo_match = re.search(r"(photo|image|picture|pic)\s+(of\s+)?(?P<name>[a-zA-Z0-9_\- ]+)", text_lower)
            photo_name = photo_match.group("name").strip() if photo_match else ""
            return ResolvedIntent(
                "insert_photo",
                0.90,
                {"photo_name": photo_name},
                f"Locating photo '{photo_name or 'recent'}' and inserting into open document."
            )

        # -------------------------------------------------------------
        # 6. WEB SEARCH IN ANY WORD ORDER
        # E.g. "search for mr beast on youtube", "on youtube search mr beast",
        # "find mr beast on youtube", "pull up mr beast on youtube", "look up mr beast on youtube"
        # -------------------------------------------------------------
        platforms = {"youtube": "youtube", "google": "google", "reddit": "reddit", "github": "github"}
        for p_key, p_name in platforms.items():
            if p_key in tokens:
                # Remove platform word and search action words to isolate query
                query = text_clean
                query = re.sub(rf"\b(on|in|from|using|at)?\s*{p_key}\b", "", query)
                query = re.sub(r"\b(search for|search|look up|look for|find|pull up|play|watch|google|show me|open|for)\b", "", query)
                query = re.sub(r"\b(and|the|a|video|videos|channel|please)\b", "", query)
                query = re.sub(r"\s+", " ", query).strip()
                if query:
                    return ResolvedIntent(
                        "web_search",
                        0.95,
                        {"platform": p_name, "query": query},
                        f"Opening {p_name.title()} search for '{query}'"
                    )
                else:
                    return ResolvedIntent(
                        "launch_app",
                        0.85,
                        {"app_name": p_name},
                        f"Opening {p_name.title()}"
                    )

        # Generic Google search: "search for X", "google X", "look up X"
        if any(w in text_lower for w in ["search for ", "google ", "look up ", "find online "]):
            query = re.sub(r"^(search for|google|look up|find online)\s+", "", text_lower).strip()
            if query:
                return ResolvedIntent(
                    "web_search",
                    0.85,
                    {"platform": "google", "query": query},
                    f"Searching Google for '{query}'"
                )

        # -------------------------------------------------------------
        # 7. IN-APP MESSAGING & COMMUNICATION IN ANY WORD ORDER
        # E.g. "in whatsapp search for mom", "send message to mom on whatsapp saying hello",
        # "text mom hello on whatsapp", "tell mom i am on my way on whatsapp"
        # -------------------------------------------------------------
        messaging_apps = ["whatsapp", "telegram", "messages", "slack", "discord"]
        for m_app in messaging_apps:
            if m_app in tokens:
                # Pattern A: "send [msg] to [contact]" or "text [contact] [msg]"
                send_match = re.search(
                    r"(send|text|message|tell)\s+(a\s+message\s+to\s+|to\s+)?(?P<contact>[a-zA-Z0-9 ]+?)\s+(saying\s+|that\s+|msg\s+)?(?P<msg>.+)",
                    text_lower
                )
                if send_match and not any(w in tokens for w in ["search", "find"]):
                    contact = send_match.group("contact").replace(m_app, "").replace("on", "").strip()
                    msg = send_match.group("msg").replace(m_app, "").replace("on", "").strip()
                    msg = re.sub(r"^(a\s+message\s+(saying|that|with)\s+|saying\s+|that\s+)", "", msg, flags=re.IGNORECASE).strip()
                    if contact and msg:
                        return ResolvedIntent(
                            "send_message",
                            0.95,
                            {"app": m_app, "contact": contact, "message": msg},
                            f"Opening {m_app.title()}, focusing contact '{contact}', and sending message."
                        )

                # Pattern B: "search for [contact] in [app]" / "in [app] search for [contact]"
                search_match = re.search(r"search\s+(for\s+)?(?P<query>[a-zA-Z0-9 ]+)", text_lower)
                if search_match:
                    query = search_match.group("query").replace(m_app, "").replace("in", "").replace("on", "").strip()
                    if query:
                        return ResolvedIntent(
                            "in_app_search",
                            0.95,
                            {"app": m_app, "query": query},
                            f"Focusing {m_app.title()} and searching for '{query}'."
                        )

        # -------------------------------------------------------------
        # 8. SEMANTIC UI ELEMENT CLICKING / TAPPING
        # E.g. "tap on create on microsoft word", "in word click new",
        # "click create in word", "press the blank button on word"
        # -------------------------------------------------------------
        click_verbs = ["tap", "click", "press", "hit", "select", "choose"]
        if any(v in tokens for v in click_verbs):
            # Check if an application is mentioned
            app_names = [
                ("microsoft word", "Microsoft Word"),
                ("word", "Microsoft Word"),
                ("google word", "Microsoft Word"),
                ("notes", "Notes"),
                ("whatsapp", "WhatsApp"),
                ("safari", "Safari"),
                ("chrome", "Google Chrome"),
                ("finder", "Finder"),
                ("slack", "Slack"),
            ]
            target_app = None
            for alias, formal in app_names:
                if alias in text_lower:
                    target_app = formal
                    break

            # Extract target element label
            elem_text = text_lower
            for alias, _ in app_names:
                elem_text = elem_text.replace(alias, "")
            elem_text = re.sub(r"\b(tap|click|press|hit|select|choose|on|in|at|the|button|icon|tab)\b", "", elem_text).strip()

            if elem_text:
                return ResolvedIntent(
                    "click_semantic",
                    0.90,
                    {"element": elem_text, "app": target_app},
                    f"Tapping on element '{elem_text}'" + (f" in {target_app}" if target_app else " in active window")
                )

        # -------------------------------------------------------------
        # 9. DIRECT TYPING / DICTATION / SEARCH BAR TYPING
        # E.g. "type mrbeast on chrome", "type hello world", "dictate: this is a test"
        # -------------------------------------------------------------
        # Check typing into specific app / search: "type mrbeast on chrome", "search mrbeast in chrome"
        type_app_match = re.search(
            r"^(type|write|search|enter)\s+(?P<text>.+?)\s+(on|in|into)\s+(?P<app>chrome|safari|browser|word|notes|whatsapp|google)",
            text_clean,
            flags=re.IGNORECASE,
        )
        if type_app_match:
            app_raw = type_app_match.group("app").lower()
            app_clean = "Google Chrome" if app_raw in ["chrome", "browser", "google"] else ("Microsoft Word" if app_raw == "word" else app_raw.title())
            clean_typed = type_app_match.group("text").strip().strip("'\"")
            return ResolvedIntent(
                "type_in_app",
                0.95,
                {"app": app_clean, "text": clean_typed},
                f"Entering '{clean_typed}' in {app_clean}."
            )

        if any(w in tokens for w in ["type", "write", "dictate", "enter"]):
            type_match = re.search(r"^(type\s+this[:\s]*|write\s+this[:\s]*|dictate[:\s]*|type[:\s]*|write[:\s]*|enter[:\s]*)\s*(?P<text>.+)", text, flags=re.IGNORECASE)
            if type_match:
                content = type_match.group("text").strip()
                return ResolvedIntent(
                    "type_text",
                    0.90,
                    {"text": content},
                    f"Typing '{content}' into active document/field."
                )
            # Fallback
            words_after = re.sub(r"^(type|write|dictate|enter)\s+", "", text, flags=re.IGNORECASE).strip()
            if words_after:
                return ResolvedIntent(
                    "type_text",
                    0.90,
                    {"text": words_after},
                    f"Typing '{words_after}' into active document/field."
                )

        # -------------------------------------------------------------
        # 10. LOCAL FILE OPERATIONS
        # E.g. "move invoice from downloads to documents", "move photo to desktop"
        # -------------------------------------------------------------
        if "move" in tokens or "transfer" in tokens or "relocate" in tokens:
            destinations = ["documents", "downloads", "desktop", "pictures", "music", "movies"]
            target_dest = next((d for d in destinations if d in tokens), "Documents")
            # Extract source file
            src_text = text_lower
            for d in destinations:
                src_text = src_text.replace(d, "")
            src_text = re.sub(r"\b(move|transfer|relocate|file|from|to|into|folder)\b", "", src_text).strip()
            if src_text:
                return ResolvedIntent(
                    "move_file",
                    0.90,
                    {"src": src_text, "dest": target_dest},
                    f"Moving file '{src_text}' to {target_dest.title()}."
                )

        # -------------------------------------------------------------
        # 11. WINDOW MANAGEMENT & SNAPPING
        # E.g. "arrange windows side by side", "split screen", "snap windows"
        # -------------------------------------------------------------
        if any(w in text_lower for w in ["side by side", "arrange windows", "split screen", "snap left", "tile windows"]):
            return ResolvedIntent(
                "window_layout",
                0.95,
                {"action": "side_by_side"},
                "Arranging top windows side-by-side cleanly."
            )

        # -------------------------------------------------------------
        # 12. APP LIFECYCLE (OPEN / CLOSE / QUIT) IN ANY ORDER
        # E.g. "open WhatsApp", "close Safari", "launch Notes", "quit Word"
        # -------------------------------------------------------------
        if any(w in tokens for w in ["open", "launch", "start"]):
            app = text_lower
            app = re.sub(r"\b(open|launch|start|up|app|application|the)\b", "", app).strip()
            if app:
                return ResolvedIntent(
                    "launch_app",
                    0.90,
                    {"app_name": app},
                    f"Launching application '{app}'"
                )

        if any(w in tokens for w in ["close", "quit", "terminate", "exit", "kill"]):
            app = text_lower
            app = re.sub(r"\b(close|quit|terminate|exit|kill|down|app|application|the)\b", "", app).strip()
            if app:
                return ResolvedIntent(
                    "terminate_app",
                    0.90,
                    {"app_name": app},
                    f"Closing application '{app}'"
                )

        # Default fallback: Treat as open-ended search / query
        return ResolvedIntent(
            "open_ended_task",
            0.50,
            {"raw_intent": text},
            f"Analyzing open-ended task: '{text}'"
        )
