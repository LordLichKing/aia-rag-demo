import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app import get_settings


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", ""),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        extra_fields = [
            "question", "answer", "mode", "latency", "confidence",
            "num_results", "refused", "refusal_reason", "cache_hit",
            "num_documents", "token_usage", "pattern", "text_preview",
            "source", "page", "parent_id", "doc_type",
        ]

        for field in extra_fields:
            value = getattr(record, field, None)
            if value is not None:
                log_entry[field] = value

        if hasattr(record, "extra_data"):
            log_entry.update(record.extra_data)

        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class StructuredLogger:
    _initialized = False

    @classmethod
    def setup(cls, config: Optional[Dict] = None) -> None:
        if cls._initialized:
            return

        settings = get_settings()
        log_cfg = config or settings.logging

        level = getattr(logging, log_cfg.get("level", "INFO").upper(), logging.INFO)
        output_dir = log_cfg.get("output_dir", "logs")

        Path(output_dir).mkdir(parents=True, exist_ok=True)

        formatter = StructuredFormatter()

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)

        file_handler = logging.FileHandler(
            os.path.join(output_dir, f"rag_service_{datetime.now().strftime('%Y%m%d')}.log"),
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

        for logger_name in ["app", "app.generation", "app.retrieval", "app.security", "app.observability"]:
            logger = logging.getLogger(logger_name)
            logger.setLevel(level)

        cls._initialized = True

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        if not cls._initialized:
            cls.setup()
        return logging.getLogger(name)


LOG_FIELD_DICTIONARY = {
    "timestamp": "ISO 8601 UTC timestamp of the log entry",
    "level": "Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    "logger": "Logger name (module path)",
    "message": "Human-readable log message",
    "trace_id": "Unique identifier for tracing a request through the pipeline",
    "module": "Python module name where the log was emitted",
    "function": "Function name where the log was emitted",
    "line": "Line number in the source file",
    "question": "User question (truncated to 100 chars in logs)",
    "answer": "Generated answer (may be redacted for PII)",
    "mode": "Retrieval mode: vector, bm25, hybrid",
    "latency": "End-to-end latency in seconds",
    "confidence": "Retrieval confidence score (0.0-1.0)",
    "num_results": "Number of documents retrieved",
    "refused": "Whether the query was refused (true/false)",
    "refusal_reason": "Reason for refusal: prompt_injection, no_context, low_confidence, out_of_scope",
    "cache_hit": "Whether the result was served from cache (true/false)",
    "num_documents": "Number of documents used for generation",
    "token_usage": "Dict with prompt_tokens, completion_tokens, total_tokens",
    "pattern": "Regex pattern that triggered injection detection",
    "text_preview": "First 100 chars of text being analyzed",
    "source": "Document source filename",
    "page": "Document page number",
    "parent_id": "Parent chunk UUID for parent-child chunking",
    "doc_type": "Chunk type: parent or child",
    "exception": "Exception traceback if error occurred",
}
