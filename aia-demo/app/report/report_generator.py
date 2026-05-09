import csv
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional

from app.observability.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class ReportGenerator:
    def __init__(self, metrics_collector: Optional[MetricsCollector] = None):
        self.metrics_collector = metrics_collector or MetricsCollector()

    def generate_text_report(self, output_path: Optional[str] = None) -> str:
        summary = self.metrics_collector.get_summary()
        mode_summary = self.metrics_collector.get_summary_by_mode()

        lines = [
            "=" * 60,
            "RAG Service Operations Report",
            f"Generated at: {datetime.now().isoformat()}",
            "=" * 60,
            "",
            "## Overall",
            f"  Total Queries:    {summary.get('total_queries', 0)}",
            f"  Uptime (seconds): {summary.get('uptime_seconds', 0)}",
            "",
        ]

        latency = summary.get("latency", {})
        if latency:
            lines.extend([
                "## Overall Latency",
                f"  P50:  {latency.get('p50', 'N/A')}s",
                f"  P95:  {latency.get('p95', 'N/A')}s",
                f"  Min:  {latency.get('min', 'N/A')}s",
                f"  Max:  {latency.get('max', 'N/A')}s",
                f"  Avg:  {latency.get('avg', 'N/A')}s",
            ])
        else:
            lines.append("  No latency data available")

        lines.extend([
            "",
            "## Overall Quality",
            f"  Cache Hit Rate:              {summary.get('cache_hit_rate', 0):.2%}",
            f"  Refusal Rate:                {summary.get('refusal_rate', 0):.2%}",
            f"  Avg Confidence:              {summary.get('avg_confidence', 0):.4f}",
            f"  Avg Faithfulness Estimate:   {summary.get('avg_faithfulness_estimate', 'N/A')}",
            f"  Avg Context Relevance Est:   {summary.get('avg_context_relevance_estimate', 'N/A')}",
        ])

        token_usage = summary.get("token_usage", {})
        if token_usage:
            lines.extend([
                "",
                "## Overall Token Usage",
                f"  Total Prompt Tokens:     {token_usage.get('total_prompt_tokens', 0)}",
                f"  Total Completion Tokens: {token_usage.get('total_completion_tokens', 0)}",
                f"  Total Tokens:            {token_usage.get('total_tokens', 0)}",
                f"  Avg Tokens per Query:    {token_usage.get('avg_tokens_per_query', 0)}",
            ])

        refusal_reasons = summary.get("refusal_reasons", {})
        if refusal_reasons:
            lines.extend(["", "## Refusal Reasons"])
            for reason, count in refusal_reasons.items():
                lines.append(f"  - {reason}: {count}")

        if mode_summary:
            lines.extend([
                "",
                "=" * 60,
                "## Per-Mode Breakdown",
                "=" * 60,
            ])

            for mode, data in sorted(mode_summary.items()):
                mode_latency = data.get("latency", {})
                mode_token = data.get("token_usage", {})
                lines.extend([
                    "",
                    f"### Mode: {mode}",
                    f"  Queries:           {data.get('total_queries', 0)}",
                    f"  Latency P50:       {mode_latency.get('p50', 'N/A')}s",
                    f"  Latency P95:       {mode_latency.get('p95', 'N/A')}s",
                    f"  Latency Avg:       {mode_latency.get('avg', 'N/A')}s",
                    f"  Cache Hit Rate:    {data.get('cache_hit_rate', 0):.2%}",
                    f"  Refusal Rate:      {data.get('refusal_rate', 0):.2%}",
                    f"  Avg Confidence:    {data.get('avg_confidence', 0):.4f}",
                    f"  Avg Faithfulness:  {data.get('avg_faithfulness_estimate', 'N/A')}",
                    f"  Total Tokens:      {mode_token.get('total_tokens', 0)}",
                ])

            if len(mode_summary) >= 2:
                lines.extend([
                    "",
                    "### Mode Comparison",
                    "",
                    f"  {'Metric':<25}" + "".join(f"{m:<18}" for m in sorted(mode_summary.keys())),
                    "  " + "-" * (25 + 18 * len(mode_summary)),
                ])
                compare_keys = [
                    ("Latency Avg", lambda d: f"{d.get('latency', {}).get('avg', 'N/A')}s"),
                    ("Latency P95", lambda d: f"{d.get('latency', {}).get('p95', 'N/A')}s"),
                    ("Avg Faithfulness", lambda d: str(d.get('avg_faithfulness_estimate', 'N/A'))),
                    ("Avg Confidence", lambda d: f"{d.get('avg_confidence', 0):.4f}"),
                    ("Cache Hit Rate", lambda d: f"{d.get('cache_hit_rate', 0):.2%}"),
                    ("Refusal Rate", lambda d: f"{d.get('refusal_rate', 0):.2%}"),
                    ("Total Tokens", lambda d: str(d.get('token_usage', {}).get('total_tokens', 0))),
                ]
                for label, extractor in compare_keys:
                    row = f"  {label:<25}"
                    for m in sorted(mode_summary.keys()):
                        row += f"{extractor(mode_summary[m]):<18}"
                    lines.append(row)

        lines.extend(["", "=" * 60])

        report_text = "\n".join(lines)

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            logger.info(f"Text report saved to {output_path}")

        return report_text

    def generate_csv_report(self, output_path: Optional[str] = None) -> str:
        summary = self.metrics_collector.get_summary()
        mode_summary = self.metrics_collector.get_summary_by_mode()
        latency = summary.get("latency", {})
        token_usage = summary.get("token_usage", {})

        rows = [
            {"metric": "total_queries", "value": summary.get("total_queries", 0)},
            {"metric": "uptime_seconds", "value": summary.get("uptime_seconds", 0)},
            {"metric": "latency_p50", "value": latency.get("p50", "N/A")},
            {"metric": "latency_p95", "value": latency.get("p95", "N/A")},
            {"metric": "latency_avg", "value": latency.get("avg", "N/A")},
            {"metric": "cache_hit_rate", "value": summary.get("cache_hit_rate", 0)},
            {"metric": "refusal_rate", "value": summary.get("refusal_rate", 0)},
            {"metric": "avg_confidence", "value": summary.get("avg_confidence", 0)},
            {"metric": "avg_faithfulness_estimate", "value": summary.get("avg_faithfulness_estimate", "N/A")},
            {"metric": "total_prompt_tokens", "value": token_usage.get("total_prompt_tokens", 0)},
            {"metric": "total_completion_tokens", "value": token_usage.get("total_completion_tokens", 0)},
            {"metric": "total_tokens", "value": token_usage.get("total_tokens", 0)},
        ]

        for mode, data in sorted(mode_summary.items()):
            mode_latency = data.get("latency", {})
            rows.extend([
                {"metric": f"{mode}_queries", "value": data.get("total_queries", 0)},
                {"metric": f"{mode}_latency_p50", "value": mode_latency.get("p50", "N/A")},
                {"metric": f"{mode}_latency_p95", "value": mode_latency.get("p95", "N/A")},
                {"metric": f"{mode}_latency_avg", "value": mode_latency.get("avg", "N/A")},
                {"metric": f"{mode}_avg_faithfulness", "value": data.get("avg_faithfulness_estimate", "N/A")},
                {"metric": f"{mode}_avg_confidence", "value": data.get("avg_confidence", 0)},
                {"metric": f"{mode}_cache_hit_rate", "value": data.get("cache_hit_rate", 0)},
                {"metric": f"{mode}_refusal_rate", "value": data.get('refusal_rate', 0)},
                {"metric": f"{mode}_total_tokens", "value": data.get("token_usage", {}).get("total_tokens", 0)},
            ])

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["metric", "value"])
                writer.writeheader()
                writer.writerows(rows)
            logger.info(f"CSV report saved to {output_path}")

        return "\n".join(f"{r['metric']},{r['value']}" for r in rows)
