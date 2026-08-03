"""
Extracts plain text (with page numbers where available) from uploaded
documents. Returns a list of (page_number, text) tuples so downstream
chunking can retain page-level metadata.
"""
from pathlib import Path

from app.core.exceptions import DocumentProcessingError
from app.models.document import DocumentType
from app.core.logging import logger

PageText = tuple[int, str]


def _ocr_page(path: Path, page_number: int) -> str:
    from pdf2image import convert_from_path
    import pytesseract

    images = convert_from_path(str(path), first_page=page_number, last_page=page_number, dpi=200)
    if not images:
        return ""
    return pytesseract.image_to_string(images[0])


def parse_pdf(path: Path) -> list[PageText]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        pages: list[PageText] = []
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                # No embedded text layer (or an unmappable font) — fall back to OCR.
                try:
                    text = _ocr_page(path, i)
                except Exception:  # noqa: BLE001
                    logger.exception(f"OCR fallback failed for page {i} of {path.name}")
                    text = ""
            if text.strip():
                pages.append((i, text))
        return pages
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"Failed to parse PDF document: {path.name}")
        raise DocumentProcessingError("Document parsing failed.") from exc


def parse_docx(path: Path) -> list[PageText]:
    from docx import Document as DocxDocument

    try:
        doc = DocxDocument(str(path))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        return [(1, text)] if text.strip() else []
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"Failed to parse DOCX document: {path.name}")
        raise DocumentProcessingError("Document parsing failed.") from exc


def parse_txt(path: Path) -> list[PageText]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return [(1, text)] if text.strip() else []
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"Failed to parse TXT document: {path.name}")
        raise DocumentProcessingError("Document parsing failed.") from exc


_PARSERS = {
    DocumentType.PDF: parse_pdf,
    DocumentType.DOCX: parse_docx,
    DocumentType.TXT: parse_txt,
}


def extract_pages(path: Path, doc_type: DocumentType) -> list[PageText]:
    parser = _PARSERS.get(doc_type)
    if parser is None:
        raise DocumentProcessingError("Unsupported document type.")

    pages = parser(path)
    if not pages:
        raise DocumentProcessingError("No extractable text found in document.")
    return pages
