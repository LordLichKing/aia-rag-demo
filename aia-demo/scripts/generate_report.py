import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import get_settings
from app.observability.logger import StructuredLogger
from app.observability.metrics import MetricsCollector
from app.report.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Generate operations report")
    parser.add_argument("--config", type=str, default="config.yaml", help="Config file path")
    parser.add_argument("--output-dir", type=str, default="reports", help="Output directory")
    parser.add_argument("--format", type=str, default="both", choices=["text", "csv", "both"], help="Report format")
    args = parser.parse_args()

    StructuredLogger.setup()
    settings = get_settings(args.config)

    os.makedirs(args.output_dir, exist_ok=True)

    metrics_collector = MetricsCollector()
    generator = ReportGenerator(metrics_collector)

    if args.format in ("text", "both"):
        text_path = os.path.join(args.output_dir, "operations_report.txt")
        generator.generate_text_report(text_path)
        print(f"Text report: {text_path}")

    if args.format in ("csv", "both"):
        csv_path = os.path.join(args.output_dir, "operations_report.csv")
        generator.generate_csv_report(csv_path)
        print(f"CSV report: {csv_path}")


if __name__ == "__main__":
    main()
