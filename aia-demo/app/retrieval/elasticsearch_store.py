import logging
from typing import Any, Dict, List, Optional

from elasticsearch import Elasticsearch
from langchain_core.documents import Document
from langchain_community.embeddings import SentenceTransformerEmbeddings

from app import get_settings

logger = logging.getLogger(__name__)


class ElasticsearchStore:
    def __init__(self):
        settings = get_settings()
        es_cfg = settings.elasticsearch
        emb_cfg = settings.embedding

        self.es_url = es_cfg.get("url", "http://localhost:9200")
        self.index_name = es_cfg.get("index_name", "rag_knowledge_base")
        self.bm25_index_name = es_cfg.get("bm25_index_name", "rag_knowledge_base_bm25")
        self.dimension = emb_cfg.get("dimension", 384)

        es_kwargs: Dict[str, Any] = {"urls": self.es_url}
        if es_cfg.get("username"):
            es_kwargs["http_auth"] = (es_cfg["username"], es_cfg.get("password", ""))
        if es_cfg.get("verify_certs") is False:
            es_kwargs["verify_certs"] = False
            es_kwargs["ssl_show_warn"] = False

        self.es = Elasticsearch(self.es_url, **{k: v for k, v in es_kwargs.items() if k != "urls"})

        self.embedding = SentenceTransformerEmbeddings(model_name=emb_cfg.get("model_name"))

    def create_vector_index(self) -> None:
        mapping = {
            "mappings": {
                "properties": {
                    "content": {"type": "text", "analyzer": "standard"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": self.dimension,
                        "index": True,
                        "similarity": "cosine",
                    },
                    "parent_id": {"type": "keyword"},
                    "child_id": {"type": "keyword"},
                    "doc_type": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "page": {"type": "integer"},
                    "parent_content": {"type": "text", "analyzer": "standard"},
                }
            }
        }
        if not self.es.indices.exists(index=self.index_name):
            self.es.indices.create(index=self.index_name, body=mapping)
            logger.info(f"Created vector index: {self.index_name}")
        else:
            logger.info(f"Vector index already exists: {self.index_name}")

    def create_bm25_index(self) -> None:
        mapping = {
            "mappings": {
                "properties": {
                    "content": {
                        "type": "text",
                        "analyzer": "ik_max_word",
                        "search_analyzer": "ik_smart",
                    },
                    "parent_id": {"type": "keyword"},
                    "doc_type": {"type": "keyword"},
                    "source": {"type": "keyword"},
                    "page": {"type": "integer"},
                }
            }
        }
        if not self.es.indices.exists(index=self.bm25_index_name):
            try:
                self.es.indices.create(index=self.bm25_index_name, body=mapping)
                logger.info(f"Created BM25 index: {self.bm25_index_name}")
            except Exception:
                fallback_mapping = {
                    "mappings": {
                        "properties": {
                            "content": {"type": "text", "analyzer": "standard"},
                            "parent_id": {"type": "keyword"},
                            "doc_type": {"type": "keyword"},
                            "source": {"type": "keyword"},
                            "page": {"type": "integer"},
                        }
                    }
                }
                self.es.indices.create(index=self.bm25_index_name, body=fallback_mapping)
                logger.info(f"Created BM25 index (standard analyzer): {self.bm25_index_name}")
        else:
            logger.info(f"BM25 index already exists: {self.bm25_index_name}")

    def add_documents(self, documents: List[Document]) -> List[str]:
        ids = []
        for doc in documents:
            embedding = self.embedding.embed_query(doc.page_content)
            body = {
                "content": doc.page_content,
                "embedding": embedding,
                "parent_id": doc.metadata.get("parent_id", ""),
                "doc_type": doc.metadata.get("doc_type", "child"),
                "source": doc.metadata.get("source", ""),
                "page": doc.metadata.get("page", 0),
                "parent_content": doc.metadata.get("parent_content", ""),
            }
            if doc.metadata.get("child_id"):
                body["child_id"] = doc.metadata["child_id"]

            result = self.es.index(index=self.index_name, body=body, refresh=True)
            ids.append(result["_id"])

            if doc.metadata.get("doc_type") == "child":
                bm25_body = {
                    "content": doc.page_content,
                    "parent_id": doc.metadata.get("parent_id", ""),
                    "doc_type": doc.metadata.get("doc_type", "child"),
                    "source": doc.metadata.get("source", ""),
                    "page": doc.metadata.get("page", 0),
                }
                self.es.index(index=self.bm25_index_name, body=bm25_body, refresh=True)

        logger.info(f"Indexed {len(documents)} documents")
        return ids

    def vector_search(self, query: str, top_k: int = 5) -> List[Document]:
        query_embedding = self.embedding.embed_query(query)
        script_query = {
            "script_score": {
                "query": {"match_all": {}},
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                    "params": {"query_vector": query_embedding},
                },
            }
        }
        response = self.es.search(
            index=self.index_name,
            body={"size": top_k, "query": script_query, "_source": {"excludes": ["embedding"]}},
        )
        return self._parse_hits(response)

    def bm25_search(self, query: str, top_k: int = 5) -> List[Document]:
        response = self.es.search(
            index=self.bm25_index_name,
            body={
                "size": top_k,
                "query": {"match": {"content": {"query": query, "analyzer": "standard"}}},
            },
        )
        return self._parse_hits(response)

    def hybrid_search(self, query: str, top_k: int = 5, alpha: float = 0.5) -> List[Document]:
        vector_results = self.vector_search(query, top_k=top_k * 2)
        bm25_results = self.bm25_search(query, top_k=top_k * 2)

        scored: Dict[str, Dict[str, Any]] = {}

        for rank, doc in enumerate(vector_results):
            pid = doc.metadata.get("parent_id", doc.page_content[:50])
            score = alpha * (1.0 / (rank + 1))
            if pid not in scored:
                scored[pid] = {"doc": doc, "score": 0.0}
            scored[pid]["score"] += score

        for rank, doc in enumerate(bm25_results):
            pid = doc.metadata.get("parent_id", doc.page_content[:50])
            score = (1 - alpha) * (1.0 / (rank + 1))
            if pid not in scored:
                scored[pid] = {"doc": doc, "score": 0.0}
            scored[pid]["score"] += score

        sorted_results = sorted(scored.values(), key=lambda x: x["score"], reverse=True)[:top_k]
        return [item["doc"] for item in sorted_results]

    def get_parent_content(self, parent_id: str) -> Optional[str]:
        response = self.es.search(
            index=self.index_name,
            body={
                "size": 1,
                "query": {"term": {"parent_id": parent_id}},
                "_source": ["parent_content", "content"],
            },
        )
        if response["hits"]["hits"]:
            hit = response["hits"]["hits"][0]
            source = hit["_source"]
            return source.get("parent_content") or source.get("content", "")
        return None

    def _parse_hits(self, response: Dict) -> List[Document]:
        documents = []
        for hit in response["hits"]["hits"]:
            source = hit["_source"]
            doc = Document(
                page_content=source.get("content", ""),
                metadata={
                    "parent_id": source.get("parent_id", ""),
                    "doc_type": source.get("doc_type", ""),
                    "source": source.get("source", ""),
                    "page": source.get("page", 0),
                    "parent_content": source.get("parent_content", ""),
                    "score": hit.get("_score", 0.0),
                },
            )
            documents.append(doc)
        return documents
