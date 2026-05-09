import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


class PIIRedactor:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._analyzer = None
        self._anonymizer = None
        self._presidio_initialized = False

    def _init_presidio(self) -> bool:
        if self._presidio_initialized:
            return self._analyzer is not None

        self._presidio_initialized = True

        if not self.enabled:
            return False

        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine

            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            logger.info("Presidio PII redaction initialized")
            return True
        except ImportError:
            logger.warning("Presidio not installed, using regex fallback")
            return False
        except Exception as e:
            logger.warning(f"Presidio init failed, falling back to regex: {e}")
            self._analyzer = None
            self._anonymizer = None
            return False

    def redact(self, text: str) -> str:
        if not self.enabled or not text:
            return text

        if self._init_presidio() and self._analyzer and self._anonymizer:
            try:
                results = self._analyzer.analyze(
                    text=text,
                    entities=["PHONE_NUMBER", "EMAIL_ADDRESS", "CREDIT_CARD", "PERSON", "LOCATION"],
                    language="en",
                )
                text = self._anonymizer.anonymize(text=text, analyzer_results=results).text
            except Exception as e:
                logger.warning(f"Presidio redaction failed, using regex fallback: {e}")

        text = self._regex_redact(text)
        return text

    def _regex_redact(self, text: str) -> str:
        patterns = [
            (re.compile(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
            (re.compile(r"\b[\w.-]+@[\w.-]+\.\w+\b"), "[EMAIL]"),
            (re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"), "[CREDIT_CARD]"),
            (re.compile(r"\b\d{6}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]\b"), "[ID_CARD]"),
            (re.compile(r"\b1[3-9]\d{9}\b"), "[PHONE_CN]"),
        ]
        for pattern, replacement in patterns:
            text = pattern.sub(replacement, text)
        return text

    def redact_for_logging(self, text: str) -> str:
        if not self.enabled or not text:
            return text
        return self._regex_redact(text)
