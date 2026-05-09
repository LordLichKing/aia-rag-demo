import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import get_settings
from app.observability.logger import StructuredLogger
from app.chunking.loader import DocumentLoader
from app.chunking.splitter import ParentChildSplitter
from app.retrieval.vector_store import InMemoryVectorStore

logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Ingest documents into vector store")
    parser.add_argument("--input-dir", type=str, default="data/sample_docs", help="Directory containing documents")
    parser.add_argument("--use-ocr", action="store_true", help="Enable OCR for scanned PDFs")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    StructuredLogger.setup()
    settings = get_settings(args.config)

    logger.info(f"Loading documents from {args.input_dir}")
    if not os.path.exists(args.input_dir):
        logger.error(f"Input directory not found: {args.input_dir}")
        os.makedirs(args.input_dir, exist_ok=True)
        logger.info(f"Created input directory: {args.input_dir}")
        print(f"请将文档放入 {args.input_dir} 目录后重新运行此脚本")
        return

    documents = DocumentLoader.load_directory(args.input_dir, use_ocr=args.use_ocr)
    logger.info(f"Loaded {len(documents)} document pages")

    if not documents:
        logger.warning("No documents found. Please add documents to the input directory.")
        return

    splitter = ParentChildSplitter()
    parent_docs, child_docs = splitter.split_documents(documents)
    logger.info(f"Split into {len(parent_docs)} parent chunks and {len(child_docs)} child chunks")

    store = InMemoryVectorStore()

    logger.info("Indexing child documents (with embeddings)...")
    batch_size = 50
    for i in range(0, len(child_docs), batch_size):
        batch = child_docs[i : i + batch_size]
        store.add_documents(batch)
        logger.info(f"Indexed batch {i // batch_size + 1}/{(len(child_docs) + batch_size - 1) // batch_size}")

    logger.info("Indexing parent documents...")
    for i in range(0, len(parent_docs), batch_size):
        batch = parent_docs[i : i + batch_size]
        store.add_documents(batch)

    store.save()
    logger.info("Document ingestion completed successfully!")

    print(f"\n入库完成！")
    print(f"  - 原始文档页数: {len(documents)}")
    print(f"  - 父文档块数: {len(parent_docs)}")
    print(f"  - 子文档块数: {len(child_docs)}")
    print(f"  - 向量库保存至: data/vector_store/")


if __name__ == "__main__":
    main()
