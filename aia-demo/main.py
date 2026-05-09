import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import get_settings
from app.observability.logger import StructuredLogger
from app.generation.chain import RAGChain
from app.observability.metrics import MetricsCollector
from app.report.report_generator import ReportGenerator
from app.retrieval.vector_store import InMemoryVectorStore
from app.retrieval.retriever import RetrievalService

logger = logging.getLogger(__name__)

rag_chain: Optional[RAGChain] = None
metrics_collector: Optional[MetricsCollector] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_chain, metrics_collector
    StructuredLogger.setup()
    settings = get_settings()
    metrics_collector = MetricsCollector()

    store = InMemoryVectorStore()
    loaded = store.load()
    if loaded:
        logger.info("Vector store loaded from disk")
    else:
        logger.warning("No vector store found on disk. Run 'python3 scripts/ingest.py' first.")

    retrieval_service = RetrievalService(store=store)
    rag_chain = RAGChain(
        retrieval_service=retrieval_service,
        metrics_collector=metrics_collector,
    )
    logger.info("RAG QA Service started")
    yield
    logger.info("RAG QA Service shutting down")


app = FastAPI(
    title="RAG QA Service",
    description="Multi-turn RAG QA + Generative Service over Internal Knowledge Base",
    version="1.0.0",
    lifespan=lifespan,
)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000, description="User question")
    mode: Optional[str] = Field(None, description="Retrieval mode: vector, hybrid, bm25")
    top_k: Optional[int] = Field(None, ge=1, le=20, description="Number of documents to retrieve")
    use_reranker: Optional[bool] = Field(None, description="Enable reranker")


class QueryResponse(BaseModel):
    question: str
    answer: str
    sources: list = []
    mode: Optional[str] = None
    trace_id: str = ""
    refused: bool = False
    refusal_reason: Optional[str] = None
    confidence: float = 0.0
    latency_seconds: float = 0.0
    num_documents_retrieved: int = 0
    cache_hit: bool = False
    faithfulness_estimate: Optional[float] = None
    context_relevance_estimate: Optional[float] = None


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    if rag_chain is None:
        raise HTTPException(status_code=503, detail="Service not initialized")

    result = rag_chain.query(
        question=request.question,
        mode=request.mode,
        top_k=request.top_k,
        use_reranker=request.use_reranker,
    )
    return QueryResponse(**result)


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": time.time()}


@app.get("/metrics")
async def get_metrics():
    if metrics_collector is None:
        raise HTTPException(status_code=503, detail="Metrics not initialized")
    return metrics_collector.get_summary()


@app.get("/metrics/queries")
async def get_recent_queries(limit: int = 50):
    if metrics_collector is None:
        raise HTTPException(status_code=503, detail="Metrics not initialized")
    return {"queries": metrics_collector.get_recent_queries(limit=limit)}


@app.post("/report")
async def generate_report(format: str = "text"):
    if metrics_collector is None:
        raise HTTPException(status_code=503, detail="Metrics not initialized")
    generator = ReportGenerator(metrics_collector)
    if format == "csv":
        return {"report": generator.generate_csv_report()}
    return {"report": generator.generate_text_report()}


if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    app_cfg = settings.app
    uvicorn.run(
        "main:app",
        host=app_cfg.get("host", "0.0.0.0"),
        port=app_cfg.get("port", 8000),
        reload=False,
    )
