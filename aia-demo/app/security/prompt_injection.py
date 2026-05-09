import logging
import re
from typing import List

logger = logging.getLogger(__name__)

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(previous|above|all)\s+(instructions?|rules?|prompts?)", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|previous|your\s+instructions)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+a", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"DAN\s+mode", re.IGNORECASE),
    re.compile(r"override\s+(safety|security|filter)", re.IGNORECASE),
    re.compile(r"disregard\s+(your|all|the)\s+(training|instructions?|rules?)", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you\s+(have\s+no|don't\s+have)\s+(restrictions|limits|rules)", re.IGNORECASE),
    re.compile(r"reveal\s+(your|the)\s+(system|initial|original)\s+(prompt|instructions?)", re.IGNORECASE),
]


class PromptInjectionDetector:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled

    def is_injection(self, text: str) -> bool:
        if not self.enabled or not text:
            return False

        for pattern in INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning(
                    "Prompt injection detected",
                    extra={"pattern": pattern.pattern, "text_preview": text[:100]},
                )
                return True

        if self._has_suspicious_structure(text):
            logger.warning("Suspicious prompt structure detected", extra={"text_preview": text[:100]})
            return True

        return False

    def _has_suspicious_structure(self, text: str) -> bool:
        system_mentions = len(re.findall(r"\bsystem\b", text, re.IGNORECASE))
        instruction_mentions = len(re.findall(r"\binstruction\b", text, re.IGNORECASE))
        if system_mentions >= 2 and instruction_mentions >= 1:
            return True

        role_patterns = len(re.findall(r"(human|assistant|system)\s*:", text, re.IGNORECASE))
        if role_patterns >= 2:
            return True

        return False

    def get_safety_score(self, text: str) -> float:
        if not text:
            return 1.0

        score = 1.0
        for pattern in INJECTION_PATTERNS:
            if pattern.search(text):
                score -= 0.2

        if self._has_suspicious_structure(text):
            score -= 0.3

        return max(score, 0.0)
