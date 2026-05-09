import uuid
from typing import Dict, List, Optional, Tuple

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app import get_settings


class ParentChildSplitter:
    def __init__(
        self,
        parent_chunk_size: Optional[int] = None,
        parent_chunk_overlap: Optional[int] = None,
        child_chunk_size: Optional[int] = None,
        child_chunk_overlap: Optional[int] = None,
    ):
        settings = get_settings()
        chunking_cfg = settings.chunking

        self.parent_chunk_size = parent_chunk_size or chunking_cfg.get("parent_chunk_size", 1500)
        self.parent_chunk_overlap = parent_chunk_overlap or chunking_cfg.get("parent_chunk_overlap", 200)
        self.child_chunk_size = child_chunk_size or chunking_cfg.get("child_chunk_size", 300)
        self.child_chunk_overlap = child_chunk_overlap or chunking_cfg.get("child_chunk_overlap", 50)

        self.parent_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.parent_chunk_size,
            chunk_overlap=self.parent_chunk_overlap,
            separators=["\n\n", "\n", "。", ".", "！", "!", "？", "?", "；", ";", " ", ""],
            length_function=len,
        )

        self.child_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.child_chunk_size,
            chunk_overlap=self.child_chunk_overlap,
            separators=["\n\n", "\n", "。", ".", "！", "!", "？", "?", "；", ";", " ", ""],
            length_function=len,
        )

    def split_documents(
        self, documents: List[Document]
    ) -> Tuple[List[Document], List[Document]]:
        parent_docs = []
        child_docs = []

        for doc in documents:
            parent_chunks = self.parent_splitter.split_documents([doc])

            for parent_chunk in parent_chunks:
                parent_id = str(uuid.uuid4())
                parent_chunk.metadata["parent_id"] = parent_id
                parent_chunk.metadata["doc_type"] = "parent"
                parent_chunk.metadata["source"] = doc.metadata.get("source", "unknown")
                parent_chunk.metadata["page"] = doc.metadata.get("page", 0)

                child_chunks = self.child_splitter.split_documents([parent_chunk])

                for child_chunk in child_chunks:
                    child_id = str(uuid.uuid4())
                    child_chunk.metadata["child_id"] = child_id
                    child_chunk.metadata["parent_id"] = parent_id
                    child_chunk.metadata["doc_type"] = "child"
                    child_chunk.metadata["source"] = doc.metadata.get("source", "unknown")
                    child_chunk.metadata["page"] = doc.metadata.get("page", 0)
                    child_chunk.metadata["parent_content"] = parent_chunk.page_content

                parent_docs.append(parent_chunk)
                child_docs.extend(child_chunks)

        return parent_docs, child_docs

    def split_text(self, text: str, metadata: Optional[Dict] = None) -> Tuple[List[Document], List[Document]]:
        doc = Document(page_content=text, metadata=metadata or {})
        return self.split_documents([doc])
