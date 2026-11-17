"""Continuous habit learning and user preference memory engine for N.O.V.A."""

import json
import logging
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("nova.memory.habits")


class HabitMemoryEngine:
    """Tracks user habits, frequent contacts, preferred applications, and past workflows.

    Learns continuously from successful voice interactions and injects personalized
    context into the local LLM brain.
    """

    def __init__(self, storage_dir: Optional[str] = None):
        default_dir = os.environ.get("NOVA_MEMORY_PATH", "./data/memory")
        self.storage_dir = Path(os.path.abspath(os.path.expanduser(storage_dir or default_dir)))
        self.habits_file = self.storage_dir / "habits.json"
        self.history_file = self.storage_dir / "interaction_history.json"

        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not create memory directory: {e}")

        self.habits: Dict[str, Any] = self._load_habits()
        self.recent_interactions: List[Dict[str, Any]] = self._load_history()

    def _load_habits(self) -> Dict[str, Any]:
        """Loads persistent user habits from disk."""
        if self.habits_file.exists():
            try:
                with open(self.habits_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read habits file, initializing fresh: {e}")

        # Default habit profile
        return {
            "contacts": {
                "whatsapp": {},
                "messages": {},
                "slack": {},
                "telegram": {},
            },
            "apps": {},
            "websites": {},
            "file_destinations": {},
            "custom_aliases": {
                "google word": "Google Docs",
                "docs": "Google Docs",
                "fb": "Facebook",
                "yt": "YouTube",
                "wa": "WhatsApp",
            },
            "user_preferences": {
                "default_browser": "Google Chrome",
                "dictation_clipboard": True,
            },
            "last_updated": time.time(),
        }

    def _save_habits(self):
        """Persists habits safely to disk."""
        try:
            self.habits["last_updated"] = time.time()
            with open(self.habits_file, "w", encoding="utf-8") as f:
                json.dump(self.habits, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist habits to {self.habits_file}: {e}")

    def _load_history(self) -> List[Dict[str, Any]]:
        """Loads recent interaction history."""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)[-50:]  # Keep latest 50
            except Exception:
                pass
        return []

    def _save_history(self):
        """Persists recent interaction history to disk."""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.recent_interactions[-50:], f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to persist interaction history: {e}")

    def record_interaction(
        self,
        raw_utterance: str,
        action_type: str,
        parameters: Dict[str, Any],
        thought: str = "",
        success: bool = True,
    ):
        """Records a completed action and incrementally updates user habit models."""
        if not success:
            return

        timestamp = time.time()
        record = {
            "timestamp": timestamp,
            "iso": datetime.now().isoformat(),
            "utterance": raw_utterance,
            "action_type": action_type,
            "parameters": parameters,
            "thought": thought,
        }
        self.recent_interactions.append(record)
        self._save_history()

        # 1. Track Messaging Contacts
        if action_type in ["send_message", "in_app_search"] or parameters.get("skill") == "send_message":
            app = parameters.get("app", "whatsapp").lower()
            contact = parameters.get("contact") or parameters.get("query")
            if contact:
                c_clean = contact.strip().title()
                app_contacts = self.habits.setdefault("contacts", {}).setdefault(app, {})
                app_contacts[c_clean] = app_contacts.get(c_clean, 0) + 1

        # 2. Track Application Usage
        app_name = parameters.get("app") or parameters.get("app_name") or parameters.get("target_app")
        if app_name:
            a_clean = str(app_name).strip()
            self.habits.setdefault("apps", {})[a_clean] = self.habits.get("apps", {}).get(a_clean, 0) + 1

        # 3. Track Website Visits
        site = parameters.get("site") or (parameters.get("query") if parameters.get("skill") == "navigate_active_tab" else None)
        if site:
            s_clean = str(site).strip().lower()
            self.habits.setdefault("websites", {})[s_clean] = self.habits.get("websites", {}).get(s_clean, 0) + 1

        # 4. Track File Move Destinations
        dest = parameters.get("dest")
        if dest:
            d_clean = str(dest).strip().lower()
            self.habits.setdefault("file_destinations", {})[d_clean] = self.habits.get("file_destinations", {}).get(d_clean, 0) + 1

        self._save_habits()
        logger.debug(f"Learned habit updated for: '{raw_utterance}' -> {action_type}")

    def get_top_contacts(self, app: str = "whatsapp", limit: int = 3) -> List[str]:
        """Returns the user's most frequently messaged contacts."""
        contacts = self.habits.get("contacts", {}).get(app.lower(), {})
        sorted_c = sorted(contacts.items(), key=lambda x: x[1], reverse=True)
        return [name for name, _ in sorted_c[:limit]]

    def get_top_apps(self, limit: int = 5) -> List[str]:
        """Returns the user's most used applications."""
        apps = self.habits.get("apps", {})
        sorted_a = sorted(apps.items(), key=lambda x: x[1], reverse=True)
        return [name for name, _ in sorted_a[:limit]]

    def get_top_websites(self, limit: int = 5) -> List[str]:
        """Returns the user's most frequented websites."""
        sites = self.habits.get("websites", {})
        sorted_s = sorted(sites.items(), key=lambda x: x[1], reverse=True)
        return [name for name, _ in sorted_s[:limit]]

    def get_last_interaction(self) -> Optional[Dict[str, Any]]:
        """Returns the most recent completed interaction."""
        return self.recent_interactions[-1] if self.recent_interactions else None

    def get_context_prompt(self) -> str:
        """Synthesizes learned habits into a compact context block for the LLM prompt."""
        lines = []

        # Top Contacts
        top_wa = self.get_top_contacts("whatsapp", limit=3)
        if top_wa:
            lines.append(f"- Frequent WhatsApp contacts: {', '.join(top_wa)}")

        # Top Apps
        top_apps = self.get_top_apps(limit=4)
        if top_apps:
            lines.append(f"- Frequently used apps: {', '.join(top_apps)}")

        # Top Websites
        top_sites = self.get_top_websites(limit=4)
        if top_sites:
            lines.append(f"- Favorite websites: {', '.join(top_sites)}")

        # Custom Aliases
        aliases = self.habits.get("custom_aliases", {})
        if aliases:
            alias_strs = [f"'{k}' -> {v}" for k, v in list(aliases.items())[:5]]
            lines.append(f"- User custom aliases: {', '.join(alias_strs)}")

        # Recent Context
        last = self.get_last_interaction()
        if last:
            last_action = last.get("action_type")
            last_thought = last.get("thought", "")
            lines.append(f"- Previous user action: {last_thought or last_action}")

        if not lines:
            return "No prior user habits recorded yet. Adapt to the user's instructions directly."

        return "\n".join(lines)
