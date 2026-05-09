import logging
from typing import List, Optional

from langchain_core.documents import Document

from app import get_settings
from app.retrieval.vector_store import InMemoryVectorStore
from app.retrieval.reranker import Reranker

logger = logging.getLogger(__name__)


class RetrievalService:
    def __init__(self, store: Optional[InMemoryVectorStore] = None):
        settings = get_settings()
        self.retrieval_cfg = settings.retrieval
        self.store = store or InMemoryVectorStore()
        self.reranker = Reranker()
        self._reranker_enabled = self.retrieval_cfg.get("reranker", {}).get("enabled", True)

    def retrieve(
        self,
        query: str,
        mode: Optional[str] = None,
        top_k: Optional[int] = None,
        use_reranker: Optional[bool] = None,
        hybrid_alpha: Optional[float] = None,
    ) -> List[Document]:
        mode = mode or self.retrieval_cfg.get("mode", "hybrid")
        top_k = top_k or self.retrieval_cfg.get("top_k", 5)
        alpha = hybrid_alpha or self.retrieval_cfg.get("hybrid_alpha", 0.5)
        should_rerank = use_reranker if use_reranker is not None else self._reranker_enabled

        logger.info(
            "Retrieval started",
            extra={
                "query": query[:100],
                "mode": mode,
                "top_k": top_k,
                "use_reranker": should_rerank,
            },
        )

        if mode == "vector":
            documents = self.store.vector_search(query, top_k=top_k * 2 if should_rerank else top_k)
        elif mode == "bm25":
            documents = self.store.bm25_search(query, top_k=top_k * 2 if should_rerank else top_k)
        elif mode == "hybrid":
            documents = self.store.hybrid_search(query, top_k=top_k * 2 if should_rerank else top_k, alpha=alpha)
        else:
            raise ValueError(f"Unknown retrieval mode: {mode}. Supported: vector, bm25, hybrid")

        if should_rerank and documents:
            documents = self._apply_reranker(query, documents, top_n=top_k)

        enriched_docs = self._enrich_with_parent_content(documents)

        logger.info(
            "Retrieval completed",
            extra={"num_results": len(enriched_docs), "mode": mode},
        )

        return enriched_docs[:top_k]

    def _apply_reranker(self, query: str, documents: List[Document], top_n: int = 3) -> List[Document]:
        doc_dicts = []
        for doc in documents:
            doc_dicts.append({
                "content": doc.page_content,
                "metadata": doc.metadata,
            })

        reranked = self.reranker.rerank(query, doc_dicts, top_n=top_n)

        result_docs = []
        for item in reranked:
            doc = Document(
                page_content=item["content"],
                metadata=item["metadata"],
            )
            doc.metadata["rerank_score"] = item.get("rerank_score", 0.0)
            result_docs.append(doc)

        return result_docs

    def _enrich_with_parent_content(self, documents: List[Document]) -> List[Document]:
        for doc in documents:
            parent_id = doc.metadata.get("parent_id", "")
            if parent_id and not doc.metadata.get("parent_content"):
                parent_content = self.store.get_parent_content(parent_id)
                if parent_content:
                    doc.metadata["parent_content"] = parent_content
        return documents
