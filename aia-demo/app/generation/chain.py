import logging
import math
import time
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_openai import ChatOpenAI

from app import get_settings
from app.generation.prompt import get_rag_prompt, RAG_SYSTEM_PROMPT, REFUSAL_PROMPT
from app.retrieval.retriever import RetrievalService
from app.security.pii_redaction import PIIRedactor
from app.security.prompt_injection import PromptInjectionDetector
from app.security.refusal_handler import RefusalHandler
from app.cache.cache_manager import CacheManager
from app.observability.metrics import MetricsCollector
from app.observability.faithfulness import estimate_faithfulness, estimate_context_relevance

logger = logging.getLogger(__name__)


class RAGChain:
    def __init__(
        self,
        retrieval_service: Optional[RetrievalService] = None,
        cache_manager: Optional[CacheManager] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        settings = get_settings()
        llm_cfg = settings.llm
        safety_cfg = settings.safety

        self.llm = ChatOpenAI(
            model=llm_cfg.get("model_name", "gpt-3.5-turbo"),
            temperature=llm_cfg.get("temperature", 0.1),
            max_tokens=llm_cfg.get("max_tokens", 1024),
            api_key=llm_cfg.get("api_key"),
            base_url=llm_cfg.get("api_base"),
        )

        self.retrieval_service = retrieval_service or RetrievalService()
        self.cache_manager = cache_manager or CacheManager()
        self.metrics_collector = metrics_collector or MetricsCollector()

        self.pii_redactor = PIIRedactor(enabled=safety_cfg.get("pii_redaction_enabled", True))
        self.prompt_injection_detector = PromptInjectionDetector(
            enabled=safety_cfg.get("prompt_injection_defense", True)
        )
        self.refusal_handler = RefusalHandler(
            low_confidence_threshold=safety_cfg.get("low_confidence_threshold", 0.3),
            refusal_message=safety_cfg.get("refusal_message", ""),
        )

        self.retrieval_cfg = settings.retrieval
        self._reranker_enabled = self.retrieval_cfg.get("reranker", {}).get("enabled", False)

        self.prompt = get_rag_prompt()

    def query(
        self,
        question: str,
        mode: Optional[str] = None,
        top_k: Optional[int] = None,
        use_reranker: Optional[bool] = None,
    ) -> Dict[str, Any]:
        start_time = time.time()
        trace_id = self.metrics_collector.generate_trace_id()

        base_mode = mode or self.retrieval_cfg.get("mode", "hybrid")
        should_rerank = use_reranker if use_reranker is not None else self._reranker_enabled
        effective_mode = f"{base_mode}+rerank" if should_rerank else base_mode

        logger.info(
            "RAG query received",
            extra={"trace_id": trace_id, "question": question[:100], "mode": effective_mode},
        )

        if self.prompt_injection_detector.is_injection(question):
            refusal = self.refusal_handler.get_injection_refusal()
            self.metrics_collector.record_query(
                trace_id=trace_id,
                question=question,
                answer=refusal,
                latency=time.time() - start_time,
                mode=effective_mode,
                refused=True,
                refusal_reason="prompt_injection",
            )
            return self._build_response(
                question=question,
                answer=refusal,
                sources=[],
                mode=effective_mode,
                trace_id=trace_id,
                refused=True,
                refusal_reason="prompt_injection",
                latency=time.time() - start_time,
            )

        cached = self.cache_manager.get(question, mode=effective_mode)
        if cached:
            logger.info("Cache hit", extra={"trace_id": trace_id})
            self.metrics_collector.record_query(
                trace_id=trace_id,
                question=question,
                answer=cached["answer"],
                latency=time.time() - start_time,
                mode=effective_mode,
                cache_hit=True,
            )
            cached["trace_id"] = trace_id
            cached["cache_hit"] = True
            return cached

        try:
            documents = self.retrieval_service.retrieve(
                query=question, mode=base_mode, top_k=top_k, use_reranker=should_rerank
            )
        except Exception as e:
            logger.error(f"Retrieval failed: {e}", extra={"trace_id": trace_id})
            documents = []

        if not documents:
            refusal = self.refusal_handler.get_no_context_refusal()
            self.metrics_collector.record_query(
                trace_id=trace_id,
                question=question,
                answer=refusal,
                latency=time.time() - start_time,
                mode=effective_mode,
                refused=True,
                refusal_reason="no_context",
            )
            return self._build_response(
                question=question,
                answer=refusal,
                sources=[],
                mode=effective_mode,
                trace_id=trace_id,
                refused=True,
                refusal_reason="no_context",
                latency=time.time() - start_time,
            )

        context_text = self._format_context(documents)

        confidence = self._estimate_confidence(documents)
        if confidence < self.refusal_handler.low_confidence_threshold:
            refusal = self.refusal_handler.get_low_confidence_refusal()
            self.metrics_collector.record_query(
                trace_id=trace_id,
                question=question,
                answer=refusal,
                latency=time.time() - start_time,
                mode=effective_mode,
                refused=True,
                refusal_reason="low_confidence",
                confidence=confidence,
            )
            return self._build_response(
                question=question,
                answer=refusal,
                sources=self._extract_sources(documents),
                mode=effective_mode,
                trace_id=trace_id,
                refused=True,
                refusal_reason="low_confidence",
                confidence=confidence,
                latency=time.time() - start_time,
            )

        chain_input = {"context": context_text, "question": question}
        formatted = self.prompt.format_messages(**chain_input)

        try:
            response = self.llm.invoke(formatted)
            answer = response.content
        except Exception as e:
            logger.error(f"LLM invocation failed: {e}", extra={"trace_id": trace_id})
            answer = self.refusal_handler.get_error_refusal()

        if self.pii_redactor.enabled:
            answer = self.pii_redactor.redact(answer)

        sources = self._extract_sources(documents)
        latency = time.time() - start_time

        faithfulness_est = estimate_faithfulness(answer, context_text)
        context_rel_est = estimate_context_relevance(question, context_text)

        result = self._build_response(
            question=question,
            answer=answer,
            sources=sources,
            mode=effective_mode,
            trace_id=trace_id,
            refused=False,
            confidence=confidence,
            latency=latency,
            num_documents=len(documents),
            faithfulness_estimate=faithfulness_est,
            context_relevance_estimate=context_rel_est,
        )

        self.cache_manager.set(question, result, mode=effective_mode)

        self.metrics_collector.record_query(
            trace_id=trace_id,
            question=question,
            answer=answer,
            latency=latency,
            mode=effective_mode,
            refused=False,
            confidence=confidence,
            num_documents=len(documents),
            token_usage=self._estimate_tokens(context_text, answer),
            faithfulness_estimate=faithfulness_est,
            context_relevance_estimate=context_rel_est,
        )

        logger.info(
            "RAG query completed",
            extra={
                "trace_id": trace_id,
                "latency": latency,
                "confidence": confidence,
                "num_documents": len(documents),
            },
        )

        return result

    def _format_context(self, documents: List[Document]) -> str:
        context_parts = []
        for i, doc in enumerate(documents, 1):
            source = doc.metadata.get("source", "unknown")
            page = doc.metadata.get("page", 0)
            content = doc.page_content
            parent_content = doc.metadata.get("parent_content", "")
            if parent_content and len(parent_content) > len(content):
                content = parent_content
            context_parts.append(f"[文档{i}] 来源: {source}, 页码: {page}\n{content}")
        return "\n\n---\n\n".join(context_parts)

    def _estimate_confidence(self, documents: List[Document]) -> float:
        if not documents:
            return 0.0
        has_rerank = any(doc.metadata.get("rerank_score") is not None for doc in documents)
        if has_rerank:
            reranked = sorted(
                documents,
                key=lambda d: d.metadata.get("rerank_score", float("-inf")),
                reverse=True,
            )
            top_docs = reranked[:min(3, len(reranked))]
            scores = []
            for doc in top_docs:
                rs = doc.metadata.get("rerank_score", 0.0)
                scores.append(1.0 / (1.0 + math.exp(-rs)))
            return sum(scores) / len(scores) if scores else 0.0
        scores = []
        for doc in documents:
            score = doc.metadata.get("score", 0.0)
            if score > 0:
                scores.append(min(score / 2.0, 1.0))
            else:
                scores.append(0.5)
        return sum(scores) / len(scores) if scores else 0.0

    def _extract_sources(self, documents: List[Document]) -> List[Dict[str, Any]]:
        sources = []
        for doc in documents:
            sources.append({
                "source": doc.metadata.get("source", "unknown"),
                "page": doc.metadata.get("page", 0),
                "content_preview": doc.page_content[:200],
                "content_full": doc.page_content,
            })
        return sources

    def _estimate_tokens(self, context: str, answer: str) -> Dict[str, int]:
        prompt_tokens = len(context) // 4
        completion_tokens = len(answer) // 4
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }

    def _build_response(
        self,
        question: str,
        answer: str,
        sources: List[Dict],
        mode: Optional[str],
        trace_id: str,
        refused: bool = False,
        refusal_reason: Optional[str] = None,
        confidence: float = 0.0,
        latency: float = 0.0,
        num_documents: int = 0,
        cache_hit: bool = False,
        faithfulness_estimate: Optional[float] = None,
        context_relevance_estimate: Optional[float] = None,
    ) -> Dict[str, Any]:
        return {
            "question": question,
            "answer": answer,
            "sources": sources,
            "mode": mode,
            "trace_id": trace_id,
            "refused": refused,
            "refusal_reason": refusal_reason,
            "confidence": round(confidence, 4),
            "latency_seconds": round(latency, 3),
            "num_documents_retrieved": num_documents,
            "cache_hit": cache_hit,
            "faithfulness_estimate": faithfulness_estimate,
            "context_relevance_estimate": context_relevance_estimate,
        }
