import os
from typing import List, Optional

from langchain_core.documents import Document
from pypdf import PdfReader

try:
    from pdf2image import convert_from_path
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


class DocumentLoader:
    @staticmethod
    def load_pdf(file_path: str, use_ocr: bool = False) -> List[Document]:
        documents = []
        reader = PdfReader(file_path)

        for page_num, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                documents.append(
                    Document(
                        page_content=text.strip(),
                        metadata={
                            "source": os.path.basename(file_path),
                            "page": page_num + 1,
                            "type": "pdf",
                        },
                    )
                )
            elif use_ocr and OCR_AVAILABLE:
                ocr_text = DocumentLoader._ocr_page(file_path, page_num)
                if ocr_text:
                    documents.append(
                        Document(
                            page_content=ocr_text,
                            metadata={
                                "source": os.path.basename(file_path),
                                "page": page_num + 1,
                                "type": "pdf_ocr",
                            },
                        )
                    )

        return documents

    @staticmethod
    def _ocr_page(file_path: str, page_num: int) -> Optional[str]:
        if not OCR_AVAILABLE:
            return None
        try:
            images = convert_from_path(file_path, first_page=page_num + 1, last_page=page_num + 1)
            if images:
                text = pytesseract.image_to_string(images[0], lang="chi_sim+eng")
                return text.strip() if text.strip() else None
        except Exception:
            return None
        return None

    @staticmethod
    def load_text(file_path: str) -> List[Document]:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        return [
            Document(
                page_content=text,
                metadata={
                    "source": os.path.basename(file_path),
                    "page": 1,
                    "type": "text",
                },
            )
        ]

    @staticmethod
    def load_directory(dir_path: str, use_ocr: bool = False) -> List[Document]:
        documents = []
        for root, _, files in os.walk(dir_path):
            for fname in files:
                fpath = os.path.join(root, fname)
                if fname.lower().endswith(".pdf"):
                    documents.extend(DocumentLoader.load_pdf(fpath, use_ocr=use_ocr))
                elif fname.lower().endswith((".txt", ".md")):
                    documents.extend(DocumentLoader.load_text(fpath))
        return documents
