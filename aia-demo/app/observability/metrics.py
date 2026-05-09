import csv
import os
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.observability.logger import StructuredLogger

logger = StructuredLogger.get_logger("app.observability.metrics")

CSV_FIELDS = [
    "trace_id", "timestamp", "question", "answer", "latency", "mode",
    "refused", "refusal_reason", "confidence", "cache_hit", "num_documents",
    "prompt_tokens", "completion_tokens", "total_tokens",
    "faithfulness_estimate", "context_relevance_estimate",
]


class MetricsCollector:
    def __init__(self, persist_dir: str = "logs/metrics"):
        self._lock = threading.Lock()
        self._queries: List[Dict[str, Any]] = []
        self._start_time = time.time()
        self._persist_dir = persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._csv_path = os.path.join(
            persist_dir, f"query_metrics_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        self._init_csv()

    def _init_csv(self) -> None:
        if not os.path.exists(self._csv_path):
            with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writeheader()

    def generate_trace_id(self) -> str:
        return str(uuid.uuid4())

    def record_query(
        self,
        trace_id: str,
        question: str,
        answer: str,
        latency: float,
        mode: str = "default",
        refused: bool = False,
        refusal_reason: Optional[str] = None,
        confidence: float = 0.0,
        cache_hit: bool = False,
        num_documents: int = 0,
        token_usage: Optional[Dict[str, int]] = None,
        faithfulness_estimate: Optional[float] = None,
        context_relevance_estimate: Optional[float] = None,
    ) -> None:
        record = {
            "trace_id": trace_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "question": question[:200],
            "answer": answer[:500],
            "latency": latency,
            "mode": mode,
            "refused": refused,
            "refusal_reason": refusal_reason,
            "confidence": confidence,
            "cache_hit": cache_hit,
            "num_documents": num_documents,
            "token_usage": token_usage or {},
            "faithfulness_estimate": faithfulness_estimate,
            "context_relevance_estimate": context_relevance_estimate,
        }

        with self._lock:
            self._queries.append(record)

        self._persist_record(record)

        logger.info(
            "Query metric recorded",
            extra={
                "trace_id": trace_id,
                "latency": latency,
                "mode": mode,
                "refused": refused,
                "cache_hit": cache_hit,
                "faithfulness_estimate": faithfulness_estimate,
            },
        )

    def _persist_record(self, record: Dict[str, Any]) -> None:
        try:
            row = {
                "trace_id": record.get("trace_id", ""),
                "timestamp": record.get("timestamp", ""),
                "question": record.get("question", "")[:200],
                "answer": record.get("answer", "")[:500],
                "latency": record.get("latency", 0),
                "mode": record.get("mode", ""),
                "refused": record.get("refused", False),
                "refusal_reason": record.get("refusal_reason", ""),
                "confidence": record.get("confidence", 0),
                "cache_hit": record.get("cache_hit", False),
                "num_documents": record.get("num_documents", 0),
                "prompt_tokens": record.get("token_usage", {}).get("prompt_tokens", 0),
                "completion_tokens": record.get("token_usage", {}).get("completion_tokens", 0),
                "total_tokens": record.get("token_usage", {}).get("total_tokens", 0),
                "faithfulness_estimate": record.get("faithfulness_estimate", ""),
                "context_relevance_estimate": record.get("context_relevance_estimate", ""),
            }
            with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                writer.writerow(row)
        except Exception as e:
            logger.warning(f"Failed to persist metric record: {e}")

    def get_summary(self) -> Dict[str, Any]:
        with self._lock:
            queries = list(self._queries)

        if not queries:
            return {
                "total_queries": 0,
                "uptime_seconds": time.time() - self._start_time,
            }

        latencies = [q["latency"] for q in queries]
        latencies_sorted = sorted(latencies)

        total = len(queries)
        p50_idx = int(total * 0.50)
        p95_idx = int(total * 0.95)

        cache_hits = sum(1 for q in queries if q.get("cache_hit"))
        refusals = sum(1 for q in queries if q.get("refused"))

        total_prompt_tokens = sum(q.get("token_usage", {}).get("prompt_tokens", 0) for q in queries)
        total_completion_tokens = sum(q.get("token_usage", {}).get("completion_tokens", 0) for q in queries)

        mode_counts = defaultdict(int)
        refusal_reasons = defaultdict(int)
        for q in queries:
            mode_counts[q.get("mode", "unknown")] += 1
            if q.get("refusal_reason"):
                refusal_reasons[q["refusal_reason"]] += 1

        avg_confidence = sum(q.get("confidence", 0) for q in queries) / total if total > 0 else 0

        faithfulness_values = [q.get("faithfulness_estimate") for q in queries if q.get("faithfulness_estimate") is not None]
        avg_faithfulness = sum(faithfulness_values) / len(faithfulness_values) if faithfulness_values else None

        context_rel_values = [q.get("context_relevance_estimate") for q in queries if q.get("context_relevance_estimate") is not None]
        avg_context_relevance = sum(context_rel_values) / len(context_rel_values) if context_rel_values else None

        return {
            "total_queries": total,
            "uptime_seconds": round(time.time() - self._start_time, 1),
            "latency": {
                "p50": round(latencies_sorted[min(p50_idx, total - 1)], 3),
                "p95": round(latencies_sorted[min(p95_idx, total - 1)], 3),
                "min": round(min(latencies), 3),
                "max": round(max(latencies), 3),
                "avg": round(sum(latencies) / total, 3),
            },
            "cache_hit_rate": round(cache_hits / total, 4) if total > 0 else 0.0,
            "refusal_rate": round(refusals / total, 4) if total > 0 else 0.0,
            "avg_confidence": round(avg_confidence, 4),
            "avg_faithfulness_estimate": round(avg_faithfulness, 4) if avg_faithfulness is not None else None,
            "avg_context_relevance_estimate": round(avg_context_relevance, 4) if avg_context_relevance is not None else None,
            "token_usage": {
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "avg_tokens_per_query": round(
                    (total_prompt_tokens + total_completion_tokens) / total, 1
                ) if total > 0 else 0,
            },
            "mode_distribution": dict(mode_counts),
            "refusal_reasons": dict(refusal_reasons),
            "per_mode": self._compute_per_mode(queries),
        }

    def get_recent_queries(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._queries[-limit:])

    def _compute_per_mode(self, queries: List[Dict]) -> Dict[str, Dict[str, Any]]:
        mode_queries: Dict[str, List[Dict]] = defaultdict(list)
        for q in queries:
            mode_queries[q.get("mode", "unknown")].append(q)

        result = {}
        for mode, mode_q in mode_queries.items():
            total = len(mode_q)
            latencies = sorted(q["latency"] for q in mode_q)
            cache_hits = sum(1 for q in mode_q if q.get("cache_hit"))
            refusals = sum(1 for q in mode_q if q.get("refused"))
            avg_confidence = sum(q.get("confidence", 0) for q in mode_q) / total if total > 0 else 0
            faith_values = [q.get("faithfulness_estimate") for q in mode_q if q.get("faithfulness_estimate") is not None]
            avg_faith = sum(faith_values) / len(faith_values) if faith_values else None
            prompt_tokens = sum(q.get("token_usage", {}).get("prompt_tokens", 0) for q in mode_q)
            completion_tokens = sum(q.get("token_usage", {}).get("completion_tokens", 0) for q in mode_q)

            result[mode] = {
                "total_queries": total,
                "latency": {
                    "p50": round(latencies[int(total * 0.5)], 3) if total > 0 else 0,
                    "p95": round(latencies[min(int(total * 0.95), total - 1)], 3) if total > 0 else 0,
                    "avg": round(sum(latencies) / total, 3) if total > 0 else 0,
                },
                "cache_hit_rate": round(cache_hits / total, 4) if total > 0 else 0.0,
                "refusal_rate": round(refusals / total, 4) if total > 0 else 0.0,
                "avg_confidence": round(avg_confidence, 4),
                "avg_faithfulness_estimate": round(avg_faith, 4) if avg_faith is not None else None,
                "token_usage": {
                    "total_prompt_tokens": prompt_tokens,
                    "total_completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
        return result

    def get_summary_by_mode(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            queries = list(self._queries)

        mode_queries: Dict[str, List[Dict]] = defaultdict(list)
        for q in queries:
            mode_queries[q.get("mode", "unknown")].append(q)

        result = {}
        for mode, mode_q in mode_queries.items():
            total = len(mode_q)
            latencies = sorted(q["latency"] for q in mode_q)
            cache_hits = sum(1 for q in mode_q if q.get("cache_hit"))
            refusals = sum(1 for q in mode_q if q.get("refused"))
            avg_confidence = sum(q.get("confidence", 0) for q in mode_q) / total if total > 0 else 0
            faith_values = [q.get("faithfulness_estimate") for q in mode_q if q.get("faithfulness_estimate") is not None]
            avg_faith = sum(faith_values) / len(faith_values) if faith_values else None
            prompt_tokens = sum(q.get("token_usage", {}).get("prompt_tokens", 0) for q in mode_q)
            completion_tokens = sum(q.get("token_usage", {}).get("completion_tokens", 0) for q in mode_q)

            result[mode] = {
                "total_queries": total,
                "latency": {
                    "p50": round(latencies[int(total * 0.5)], 3) if total > 0 else 0,
                    "p95": round(latencies[min(int(total * 0.95), total - 1)], 3) if total > 0 else 0,
                    "avg": round(sum(latencies) / total, 3) if total > 0 else 0,
                },
                "cache_hit_rate": round(cache_hits / total, 4) if total > 0 else 0.0,
                "refusal_rate": round(refusals / total, 4) if total > 0 else 0.0,
                "avg_confidence": round(avg_confidence, 4),
                "avg_faithfulness_estimate": round(avg_faith, 4) if avg_faith is not None else None,
                "token_usage": {
                    "total_prompt_tokens": prompt_tokens,
                    "total_completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }

        return result

    def reset(self) -> None:
        with self._lock:
            self._queries.clear()
            self._start_time = time.time()
