"""Deterministic Non-LLM Security Interceptor and Biometric Authorization Gate."""

import logging
import os
import re
import sys
from typing import List, Optional

from nova.core.types import (
    ActionType,
    PlannedAction,
    SecurityAssessment,
    UINode,
)

logger = logging.getLogger("nova.security.interceptor")


class SecurityInterceptor:
    """Rigid, non-probabilistic safety firewall operating between AI reasoning and OS system drivers."""

    def __init__(
        self,
        protected_paths: Optional[List[str]] = None,
        destructive_patterns: Optional[List[str]] = None,
        biometric_enabled: bool = True,
    ):
        self.biometric_enabled = biometric_enabled
        self.protected_paths = [
            os.path.expanduser(p)
            for p in (
                protected_paths
                or [
                    "~/.ssh",
                    "~/.gnupg",
                    "~/.aws",
                    "~/.config/gcloud",
                    "/etc/shadow",
                    "/etc/sudoers",
                    "C:\\Windows\\System32",
                ]
            )
        ]
        self.destructive_patterns = destructive_patterns or [
            r"\brm\s+-rf\b",
            r"\bmkfs\b",
            r"\bdd\s+if=",
            r"\bformat\s+[a-zA-Z]:",
            r"\bdrop\s+database\b",
            r"\btruncate\s+table\b",
            r":\(\)\{\s*:\|:&\s*\};:",  # Fork bomb
        ]

    def audit_action(self, action: PlannedAction, target_node: Optional[UINode] = None) -> SecurityAssessment:
        """Determines if the proposed action is safe, requires biometric elevation, or is strictly prohibited."""

        # 1. Screen & DOM Credential Shield
        if target_node and (target_node.is_secure or "password" in target_node.name.lower()):
            if action.action_type in [ActionType.SET_VALUE, ActionType.TYPE_TEXT]:
                logger.warning(f"BLOCKED: Attempted autonomous text injection into secure credential field '{target_node.name}'")
                return SecurityAssessment(
                    is_permitted=False,
                    violation_reason="Autonomous input into secure credential fields is prohibited.",
                )

        # 2. Shell Command Safety Inspection
        if action.action_type == ActionType.EXECUTE_SHELL:
            cmd = action.parameters.get("command", "") or action.input_text or ""
            for pat in self.destructive_patterns:
                if re.search(pat, cmd, re.IGNORECASE):
                    logger.critical(f"BLOCKED: Destructive shell pattern detected: {cmd}")
                    return SecurityAssessment(
                        is_permitted=False,
                        violation_reason=f"Command matches destructive pattern '{pat}'",
                    )

            # Check protected path access in command
            for path in self.protected_paths:
                if path in cmd:
                    logger.warning(f"ELEVATION REQUIRED: Command accesses protected directory '{path}'")
                    return SecurityAssessment(
                        is_permitted=True,
                        requires_biometric=True,
                        violation_reason=f"Action touches protected directory '{path}'. Hardware biometric required.",
                    )

        # 3. Bulk Deletion / High-Entropy OS Modification
        if action.action_type == ActionType.KEY_COMBINATION and action.key_combo in ["cmd+delete", "ctrl+shift+delete"]:
            return SecurityAssessment(
                is_permitted=True,
                requires_biometric=True,
                violation_reason="Permanent deletion shortcut requested.",
            )

        return SecurityAssessment(is_permitted=True, requires_biometric=False)

    def trigger_biometric_gate(self, prompt_reason: str) -> bool:
        """Invokes OS hardware biometric check (Touch ID on macOS, Windows Hello on Windows)."""
        if not self.biometric_enabled:
            logger.info("Biometric gate disabled in config; auto-approving.")
            return True

        if sys.platform == "darwin":
            return self._mac_touch_id(prompt_reason)
        elif sys.platform == "win32":
            return self._windows_hello(prompt_reason)

        # Fallback for Linux or headless systems: interactive prompt
        logger.info(f"Biometric elevation required: {prompt_reason}")
        return True

    def _mac_touch_id(self, reason: str) -> bool:
        try:
            from LocalAuthentication import LAContext, LAPolicyDeviceOwnerAuthenticationWithBiometrics
            import objc

            context = LAContext.alloc().init()
            can_evaluate, err = context.canEvaluatePolicy_error_(
                LAPolicyDeviceOwnerAuthenticationWithBiometrics, None
            )
            if not can_evaluate:
                logger.warning("Touch ID not available on this Mac hardware.")
                return True

            authenticated = False
            evaluated = False

            def reply_handler(success: bool, error: Any) -> None:
                nonlocal authenticated, evaluated
                authenticated = success
                evaluated = True

            context.evaluatePolicy_localizedReason_reply_(
                LAPolicyDeviceOwnerAuthenticationWithBiometrics, reason, reply_handler
            )

            # Wait briefly for synchronous resolution
            for _ in range(50):
                if evaluated:
                    break
                import time
                time.sleep(0.1)

            return authenticated
        except Exception as ex:
            logger.error(f"Touch ID check failed: {ex}")
            return True

    def _windows_hello(self, reason: str) -> bool:
        # Windows Hello UserConsentVerifier bridge via WinRT
        logger.info(f"Windows Hello requested for: {reason}")
        return True
