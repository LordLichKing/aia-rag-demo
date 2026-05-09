#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "========================================="
echo "  RAG Service One-Click Evaluation"
echo "========================================="
echo ""

echo "[1/4] Checking dependencies..."
pip install -r requirements.txt -q 2>/dev/null || {
    echo "ERROR: Failed to install dependencies"
    exit 1
}
echo "  Dependencies OK"

echo ""
echo "[2/4] Checking Elasticsearch..."
if curl -s http://localhost:9200/_cluster/health > /dev/null 2>&1; then
    echo "  Elasticsearch is running"
else
    echo "  WARNING: Elasticsearch is not running at localhost:9200"
    echo "  Please start Elasticsearch before continuing"
    echo "  You can start it with: docker run -d -p 9200:9200 -e discovery.type=single-node -e xpack.security.enabled=false docker.elastic.co/elasticsearch/elasticsearch:8.13.0"
    read -p "  Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo ""
echo "[3/4] Ingesting documents..."
python3 scripts/ingest.py --input-dir data/sample_docs --config config.yaml

echo ""
echo "[4/4] Running full evaluation (vector, hybrid, hybrid+rerank)..."
python3 scripts/evaluate.py \
    --questions eval/test_questions.json \
    --config config.yaml \
    --modes vector,hybrid,hybrid+rerank \
    --run-ragas \
    --output-dir eval/eval_results

echo ""
echo "========================================="
echo "  Evaluation Complete!"
echo "========================================="
echo ""
echo "Results saved to: eval/eval_results/"
echo "Logs saved to: logs/"
echo "Issue diagnosis: docs/issue_diagnosis.md"
echo ""
echo "To start the API server:"
echo "  python3 main.py"
echo ""
echo "To query the API:"
echo "  curl -X POST http://localhost:8000/query -H 'Content-Type: application/json' -d '{\"question\": \"公司的年假政策是什么？\", \"mode\": \"hybrid\"}'"
echo ""
echo "To test hybrid+rerank mode:"
echo "  curl -X POST http://localhost:8000/query -H 'Content-Type: application/json' -d '{\"question\": \"公司的年假政策是什么？\", \"mode\": \"hybrid\", \"use_reranker\": true}'"
