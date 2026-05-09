import logging
import pickle
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.documents import Document
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import FAISS
from rank_bm25 import BM25Okapi

from app import get_settings

logger = logging.getLogger(__name__)


class InMemoryVectorStore:
    def __init__(self):
        settings = get_settings()
        emb_cfg = settings.embedding

        self.embedding = SentenceTransformerEmbeddings(
            model_name=emb_cfg.get("model_name", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        )

        self._faiss_store: Optional[FAISS] = None
        self._bm25: Optional[BM25Okapi] = None
        self._bm25_corpus: List[str] = []
        self._bm25_docs: List[Document] = []
        self._all_docs: List[Document] = []
        self._lock = threading.Lock()
        self._persist_dir = "data/vector_store"

    def add_documents(self, documents: List[Document]) -> List[str]:
        with self._lock:
            if not documents:
                return []

            if self._faiss_store is None:
                self._faiss_store = FAISS.from_documents(documents, self.embedding)
            else:
                self._faiss_store.add_documents(documents)

            for doc in documents:
                if doc.metadata.get("doc_type") == "child":
                    self._bm25_corpus.append(doc.page_content)
                    self._bm25_docs.append(doc)

            self._rebuild_bm25()
            self._all_docs.extend(documents)

            ids = [doc.metadata.get("child_id", doc.metadata.get("parent_id", str(i))) for i, doc in enumerate(documents)]
            logger.info(f"Indexed {len(documents)} documents (FAISS + BM25)")
            return ids

    def _rebuild_bm25(self) -> None:
        if not self._bm25_corpus:
            return
        tokenized_corpus = [self._tokenize(doc) for doc in self._bm25_corpus]
        self._bm25 = BM25Okapi(tokenized_corpus)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        tokens = []
        current = []
        for ch in text:
            if '\u4e00' <= ch <= '\u9fff':
                if current:
                    tokens.append("".join(current).lower())
                    current = []
                tokens.append(ch)
            elif ch.isalnum():
                current.append(ch)
            else:
                if current:
                    tokens.append("".join(current).lower())
                    current = []
        if current:
            tokens.append("".join(current).lower())
        return tokens

    def vector_search(self, query: str, top_k: int = 5) -> List[Document]:
        if self._faiss_store is None:
            return []

        results = self._faiss_store.similarity_search_with_score(query, k=top_k)
        documents = []
        for doc, score in results:
            doc.metadata["score"] = float(score)
            documents.append(doc)
        return documents

    def bm25_search(self, query: str, top_k: int = 5) -> List[Document]:
        if self._bm25 is None or not self._bm25_docs:
            return []

        tokenized_query = self._tokenize(query)
        scores = self._bm25.get_scores(tokenized_query)
        scored_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = []
        for idx in scored_indices:
            if scores[idx] > 0:
                doc = self._bm25_docs[idx]
                doc.metadata["score"] = float(scores[idx])
                results.append(doc)
        return results

    def hybrid_search(self, query: str, top_k: int = 5, alpha: float = 0.5) -> List[Document]:
        vector_results = self.vector_search(query, top_k=top_k * 2)
        bm25_results = self.bm25_search(query, top_k=top_k * 2)

        scored: Dict[str, Dict[str, Any]] = {}

        for rank, doc in enumerate(vector_results):
            key = doc.metadata.get("parent_id", doc.page_content[:50])
            score = alpha * (1.0 / (rank + 1))
            if key not in scored:
                scored[key] = {"doc": doc, "score": 0.0}
            scored[key]["score"] += score

        for rank, doc in enumerate(bm25_results):
            key = doc.metadata.get("parent_id", doc.page_content[:50])
            score = (1 - alpha) * (1.0 / (rank + 1))
            if key not in scored:
                scored[key] = {"doc": doc, "score": 0.0}
            scored[key]["score"] += score

        sorted_results = sorted(scored.values(), key=lambda x: x["score"], reverse=True)[:top_k]
        return [item["doc"] for item in sorted_results]

    def get_parent_content(self, parent_id: str) -> Optional[str]:
        for doc in self._all_docs:
            if doc.metadata.get("parent_id") == parent_id and doc.metadata.get("doc_type") == "parent":
                return doc.page_content
        for doc in self._all_docs:
            if doc.metadata.get("parent_id") == parent_id and doc.metadata.get("parent_content"):
                return doc.metadata["parent_content"]
        return None

    def save(self, persist_dir: Optional[str] = None) -> None:
        persist_dir = persist_dir or self._persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        if self._faiss_store is not None:
            self._faiss_store.save_local(persist_dir)

        meta = {
            "bm25_corpus": self._bm25_corpus,
            "bm25_docs": [
                {"page_content": d.page_content, "metadata": d.metadata}
                for d in self._bm25_docs
            ],
            "all_docs": [
                {"page_content": d.page_content, "metadata": d.metadata}
                for d in self._all_docs
            ],
        }
        with open(Path(persist_dir) / "bm25_meta.pkl", "wb") as f:
            pickle.dump(meta, f)

        logger.info(f"Vector store saved to {persist_dir}")

    def load(self, persist_dir: Optional[str] = None) -> bool:
        persist_dir = persist_dir or self._persist_dir
        path = Path(persist_dir)

        if not path.exists():
            return False

        try:
            if (path / "index.faiss").exists():
                self._faiss_store = FAISS.load_local(
                    persist_dir, self.embedding, allow_dangerous_deserialization=True
                )

            meta_path = path / "bm25_meta.pkl"
            if meta_path.exists():
                with open(meta_path, "rb") as f:
                    meta = pickle.load(f)

                self._bm25_corpus = meta.get("bm25_corpus", [])
                self._bm25_docs = [
                    Document(page_content=d["page_content"], metadata=d["metadata"])
                    for d in meta.get("bm25_docs", [])
                ]
                self._all_docs = [
                    Document(page_content=d["page_content"], metadata=d["metadata"])
                    for d in meta.get("all_docs", [])
                ]
                self._rebuild_bm25()

            logger.info(f"Vector store loaded from {persist_dir}")
            return True
        except Exception as e:
            logger.error(f"Failed to load vector store: {e}")
            return False
