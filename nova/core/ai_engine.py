"""Local Open-Source AI Brain and Neural Intent Resolver for N.O.V.A."""

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from nova.core.types import ActionType, PlannedAction

logger = logging.getLogger("nova.core.ai_engine")


SYSTEM_PROMPT_TEMPLATE = """You are N.O.V.A., an advanced local autonomous Operating System agent running directly on the user's computer.
Your job is to translate ANY free-form, casual, colloquial, or messy human voice command into an exact, machine-executable sequence of OS actions.

AVAILABLE OS SKILLS:
- launch_app(app_name): Launches a desktop application (e.g. "WhatsApp", "Microsoft Word", "Google Chrome", "Dictionary", "Notes", "Finder").
- terminate_app(app_name): Closes an open application.
- open_website(site): Opens official website/service in Chrome (e.g. "facebook", "youtube", "netflix", "reddit", "gmail", "github", "chatgpt").
- web_search(platform, query): Searches on a web platform (platform="youtube"|"google"|"reddit"|"github", query="...").
- dictionary_lookup(word): Looks up definition of a word in macOS Dictionary (e.g. word="help").
- send_message(app, contact, message): Opens messaging app (WhatsApp/Slack/Telegram/Messages), finds contact, and sends message.
- in_app_search(app, query): Focuses app and searches for contact or item.
- type_in_app(app, text): Focuses application and enters text into its search or active field.
- type_text(text): Types text directly into the currently active cursor position.
- switch_tab(tab_number): Switches to a browser tab by number (1 to 9).
- navigate_active_tab(query): Navigates the CURRENT active browser tab without opening new windows.
- browser_control(action): Browser action ("new_tab"|"close_tab"|"next_tab"|"prev_tab"|"refresh").
- edit_action(action): Edit action ("copy"|"paste"|"undo"|"redo"|"save"|"select_all").
- move_file(src, dest): Moves a local file (e.g. src="invoice", dest="documents").
- system_control(action): Hardware controls ("volume_up"|"volume_down"|"mute"|"unmute"|"screenshot").
- scroll(direction, amount=5): Scrolls page ("up"|"down").
- click_semantic(element, app=None): Clicks a UI button or element by name (e.g. element="create", app="Microsoft Word").

CURRENT APPLICATION & SYSTEM STATE:
- Active Foreground App: {current_app}

LEARNED USER HABITS & PROFILE:
{habits_context}

RULES:
1. Always output strictly valid JSON with keys "thought" and "plan".
2. "plan" must be a list of action objects with "action" and "parameters".
3. Extract only the real search term or payload, stripping conversational fillers ("please", "can you", "i want you to", "type", "just").
4. If the user refers to an action without naming an app (e.g. "search for frosty contact and type hi", "send hi to frosty"), use the Active Foreground App (e.g. "WhatsApp").
5. Never output markdown code fences, commentary, or text outside the JSON object.

FEW-SHOT EXAMPLES:
User: "search for mr beast on youtube"
{{"thought": "Search YouTube for 'mr beast'", "plan": [{{"action": "web_search", "parameters": {{"platform": "youtube", "query": "mr beast"}}}}]}}

User: "open youtube on this tab"
{{"thought": "Navigate current active tab to YouTube", "plan": [{{"action": "navigate_active_tab", "parameters": {{"query": "youtube"}}}}]}}

User: "switch to 3rd tab"
{{"thought": "Switch to tab number 3", "plan": [{{"action": "switch_tab", "parameters": {{"tab_number": 3}}}}]}}

User: "type help in dictionary"
{{"thought": "Look up definition of 'help' in Dictionary", "plan": [{{"action": "dictionary_lookup", "parameters": {{"word": "help"}}}}]}}

User: "open facebook on chrome"
{{"thought": "Open Facebook in Google Chrome", "plan": [{{"action": "open_website", "parameters": {{"site": "facebook"}}}}]}}

User: "open fb chrome"
{{"thought": "Open Facebook in Google Chrome", "plan": [{{"action": "open_website", "parameters": {{"site": "facebook"}}}}]}}

User: "open whatsapp and send hi to frosty"
{{"thought": "Open WhatsApp, locate Frosty, and send 'hi'", "plan": [{{"action": "send_message", "parameters": {{"app": "WhatsApp", "contact": "Frosty", "message": "hi"}}}}]}}

User: "search frosty in whatsapp and type hi"
{{"thought": "Send WhatsApp message to Frosty saying 'hi'", "plan": [{{"action": "send_message", "parameters": {{"app": "WhatsApp", "contact": "Frosty", "message": "hi"}}}}]}}

User: "search for frosty contact and type hi"
{{"thought": "Search contact Frosty in active app and send message 'hi'", "plan": [{{"action": "send_message", "parameters": {{"app": "WhatsApp", "contact": "Frosty", "message": "hi"}}}}]}}

User: "send hi to frosty"
{{"thought": "Send message 'hi' to Frosty in WhatsApp", "plan": [{{"action": "send_message", "parameters": {{"app": "WhatsApp", "contact": "Frosty", "message": "hi"}}}}]}}

User: "tell frosty on whatsapp that I will be late"
{{"thought": "Send WhatsApp message to Frosty", "plan": [{{"action": "send_message", "parameters": {{"app": "WhatsApp", "contact": "Frosty", "message": "I will be late"}}}}]}}

User: "turn up the sound"
{{"thought": "Increase system audio volume", "plan": [{{"action": "system_control", "parameters": {{"action": "volume_up"}}}}]}}

User: "take a screenshot"
{{"thought": "Capture screen to Desktop", "plan": [{{"action": "system_control", "parameters": {{"action": "screenshot"}}}}]}}

User: "move my resume from downloads to documents"
{{"thought": "Move resume file to Documents directory", "plan": [{{"action": "move_file", "parameters": {{"src": "resume", "dest": "documents"}}}}]}}
"""


class LocalAIEngine:
    """Offline local neural LLM orchestrator for N.O.V.A.

    Communicates with local LLM runners (Ollama, LM Studio, llama.cpp, LocalAI)
    over local loopback without cloud dependency or latency.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        preferred_model: Optional[str] = None,
        timeout: float = 6.0,
    ):
        self.base_url = (base_url or os.environ.get("NOVA_LLM_URL", "http://127.0.0.1:11434")).rstrip("/")
        self.preferred_model = preferred_model or os.environ.get("NOVA_LLM_MODEL", "llama3.2")
        self.timeout = timeout
        self.active_backend: Optional[str] = None  # "ollama", "openai_compatible", None
        self.active_model: Optional[str] = None
        self._check_connectivity()

    def _find_ollama_bin(self) -> Optional[str]:
        import shutil
        return shutil.which("ollama") or (
            "/opt/homebrew/bin/ollama" if os.path.exists("/opt/homebrew/bin/ollama") else None
        ) or (
            "/usr/local/bin/ollama" if os.path.exists("/usr/local/bin/ollama") else None
        )

    def _ensure_ollama_daemon(self) -> bool:
        """If ollama binary is installed on Mac/Linux but daemon is stopped, auto-starts 'ollama serve'."""
        ollama_bin = self._find_ollama_bin()
        if not ollama_bin:
            return False

        import subprocess
        import time
        logger.info(f"Ollama CLI found at '{ollama_bin}'. Auto-starting server daemon in background...")
        try:
            subprocess.Popen(
                [ollama_bin, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(1.5)
            req = urllib.request.Request(f"{self.base_url}/api/tags", headers={"User-Agent": "NOVA-Agent"})
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    self.active_backend = "ollama"
                    self.active_model = self._select_best_model(models)
                    logger.info(f"Ollama server auto-started and connected with model: '{self.active_model}'")
                    return True
        except Exception as e:
            logger.debug(f"Could not auto-start ollama serve: {e}")
        return False

    def _check_connectivity(self) -> bool:
        """Probes local endpoints to detect active LLM runner and available models."""
        # 1. Probe Ollama API (/api/tags)
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", headers={"User-Agent": "NOVA-Agent"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    models = [m.get("name", "") for m in data.get("models", [])]
                    self.active_backend = "ollama"
                    self.active_model = self._select_best_model(models)
                    logger.info(f"Connected to Ollama with model: '{self.active_model}'")
                    return True
        except Exception:
            pass

        # 2. Probe OpenAI-Compatible Endpoint (/v1/models) e.g. LM Studio / llama.cpp
        for url in [self.base_url, "http://127.0.0.1:1234/v1", "http://127.0.0.1:8080/v1"]:
            try:
                endpoint = f"{url}/models" if not url.endswith("/v1") else f"{url}/models"
                req = urllib.request.Request(endpoint, headers={"User-Agent": "NOVA-Agent"})
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        models = [m.get("id", "") for m in data.get("data", [])]
                        self.base_url = url
                        self.active_backend = "openai_compatible"
                        self.active_model = self._select_best_model(models)
                        logger.info(f"Connected to local OpenAI-compatible LLM at {url} with model: '{self.active_model}'")
                        return True
            except Exception:
                continue

        # 3. If local Ollama binary exists, try auto-starting 'ollama serve'
        if self._ensure_ollama_daemon():
            return True

        self.active_backend = None
        self.active_model = None
        return False

    def _select_best_model(self, available_models: List[str]) -> str:
        """Selects the best local model according to priority."""
        if not available_models:
            return self.preferred_model

        # Check for explicit match
        for m in available_models:
            if self.preferred_model in m:
                return m

        # Priority list of top local models
        priority = [
            "llama3.2",
            "llama3.1",
            "llama3",
            "qwen2.5",
            "qwen",
            "mistral",
            "phi3",
            "gemma2",
            "codellama",
        ]
        for p in priority:
            for m in available_models:
                if p in m.lower():
                    return m

        return available_models[0]

    @property
    def is_available(self) -> bool:
        if not self.active_backend:
            # Quick re-probe in case user just started Ollama
            return self._check_connectivity()
        return True

    def reason_and_plan(
        self,
        user_utterance: str,
        habits_context: str = "",
        current_app: Optional[str] = None,
    ) -> Optional[Tuple[str, List[PlannedAction]]]:
        """Translates arbitrary unstructured human speech into structured planned actions using the local LLM.

        Returns (thought, List[PlannedAction]) or None if LLM is unavailable / failed.
        """
        if not self.is_available:
            return None

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            habits_context=habits_context or "No recorded habits yet.",
            current_app=current_app or "Desktop",
        )

        try:
            if self.active_backend == "ollama":
                raw_json = self._call_ollama(user_utterance, system_prompt)
            else:
                raw_json = self._call_openai_compatible(user_utterance, system_prompt)

            if not raw_json:
                return None

            return self._parse_llm_plan(raw_json)
        except Exception as e:
            logger.warning(f"Local AI inference failed: {e}")
            return None

    def _call_ollama(self, prompt: str, system: str) -> Optional[Dict[str, Any]]:
        """Calls local Ollama REST API with native JSON mode."""
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.active_model or self.preferred_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 300,
            },
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "NOVA-Agent"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                msg_content = body.get("message", {}).get("content", "")
                return self._extract_json_dict(msg_content)
        return None

    def _call_openai_compatible(self, prompt: str, system: str) -> Optional[Dict[str, Any]]:
        """Calls OpenAI-compatible local endpoints (LM Studio, llama.cpp, Jan)."""
        url = f"{self.base_url}/chat/completions" if self.base_url.endswith("/v1") else f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.active_model or self.preferred_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 300,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "NOVA-Agent"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            if resp.status == 200:
                body = json.loads(resp.read().decode("utf-8"))
                choice = body.get("choices", [{}])[0]
                content = choice.get("message", {}).get("content", "")
                return self._extract_json_dict(content)
        return None

    def _extract_json_dict(self, text: str) -> Optional[Dict[str, Any]]:
        """Extracts and parses JSON object from LLM response text, stripping any markdown wrappers."""
        text = text.strip()
        # Strip markdown fences if any
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        try:
            return json.loads(text)
        except Exception:
            # Fallback regex search for { ... }
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
        return None

    def _parse_llm_plan(self, data: Dict[str, Any]) -> Tuple[str, List[PlannedAction]]:
        """Converts raw LLM JSON structure into verified PlannedAction objects."""
        thought = data.get("thought", "Executing user voice intent via local AI.")
        raw_plan = data.get("plan", [])
        actions: List[PlannedAction] = []

        for idx, item in enumerate(raw_plan, start=1):
            act_name = item.get("action", "")
            params = item.get("parameters", {})

            # Map to ActionType
            if act_name == "launch_app":
                target_app = params.get("app_name") or params.get("app")
                actions.append(
                    PlannedAction(
                        step_id=idx,
                        thought=thought,
                        action_type=ActionType.LAUNCH_APP,
                        target_app=target_app,
                        parameters=params,
                    )
                )
            elif act_name == "terminate_app":
                target_app = params.get("app_name") or params.get("app")
                actions.append(
                    PlannedAction(
                        step_id=idx,
                        thought=thought,
                        action_type=ActionType.TERMINATE,
                        target_app=target_app,
                        parameters=params,
                    )
                )
            elif act_name in [
                "open_website",
                "web_search",
                "dictionary_lookup",
                "send_message",
                "in_app_search",
                "navigate_active_tab",
                "switch_tab",
                "type_in_app",
                "type_text",
                "scroll",
                "system_control",
                "browser_control",
                "edit_action",
                "move_file",
                "click_semantic",
            ]:
                params_with_skill = dict(params)
                params_with_skill["skill"] = act_name

                # ActionType selection
                action_type_map = {
                    "open_website": ActionType.LAUNCH_APP,
                    "web_search": ActionType.LAUNCH_APP,
                    "dictionary_lookup": ActionType.LAUNCH_APP,
                    "send_message": ActionType.TYPE_TEXT,
                    "in_app_search": ActionType.TYPE_TEXT,
                    "navigate_active_tab": ActionType.LAUNCH_APP,
                    "switch_tab": ActionType.KEY_COMBINATION,
                    "type_in_app": ActionType.TYPE_TEXT,
                    "type_text": ActionType.TYPE_TEXT,
                    "scroll": ActionType.SCROLL,
                    "system_control": ActionType.EXECUTE_SHELL,
                    "browser_control": ActionType.KEY_COMBINATION,
                    "edit_action": ActionType.KEY_COMBINATION,
                    "move_file": ActionType.EXECUTE_SHELL,
                    "click_semantic": ActionType.CLICK,
                }

                actions.append(
                    PlannedAction(
                        step_id=idx,
                        thought=thought,
                        action_type=action_type_map.get(act_name, ActionType.CUSTOM),
                        parameters=params_with_skill,
                    )
                )

        return thought, actions
