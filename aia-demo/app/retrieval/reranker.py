from typing import List, Optional

from sentence_transformers import CrossEncoder

from app import get_settings


class Reranker:
    def __init__(self, model_name: Optional[str] = None):
        settings = get_settings()
        reranker_cfg = settings.retrieval.get("reranker", {})
        self.model_name = model_name or reranker_cfg.get("model_name", "cross-encoder/ms-marco-MiniLM-L-6-v2")
        self.top_n = reranker_cfg.get("top_n", 3)
        self._model = None

    @property
    def model(self):
        if self._model is None:
            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, query: str, documents: List[dict], top_n: Optional[int] = None) -> List[dict]:
        if not documents:
            return []

        top_n = top_n or self.top_n
        pairs = [(query, doc.get("content", doc.get("page_content", ""))) for doc in documents]
        scores = self.model.predict(pairs)

        scored_docs = list(zip(documents, scores))
        scored_docs.sort(key=lambda x: x[1], reverse=True)

        results = []
        for doc, score in scored_docs[:top_n]:
            result = dict(doc) if isinstance(doc, dict) else {"content": doc.page_content, "metadata": doc.metadata}
            result["rerank_score"] = float(score)
            results.append(result)

        return results
