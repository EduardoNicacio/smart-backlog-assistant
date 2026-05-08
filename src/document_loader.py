"""
src/document_loader.py
======================
Loads input documents and returns their text content.

Supported formats:
  - .txt  (plain text)
  - .md   (markdown - treated as plain text)
  - .pdf  (requires pypdf: pip install pypdf)

Candidate note: extend this to support:
  - .docx (python-docx)
  - URLs  (requests + BeautifulSoup)
  - Confluence / Notion API integration
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_document(path: str) -> str:
    """
    Load a document from disk and return its text content.
    Supported formats: txt, md, pdf

    Args:
        path: File path to the document.

    Returns:
        Extracted text content as a string.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file format is not supported.
    """
    file_path = Path(path)

    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = file_path.suffix.lower()

    if suffix in (".txt", ".md"):
        return _load_text(file_path)
    elif suffix == ".pdf":
        return _load_pdf(file_path)
    else:
        raise ValueError(
            f"Unsupported file format '{suffix}'. Supported: .txt, .md, .pdf"
        )


def _load_text(path: Path) -> str:
    """Load a plain text or markdown file."""
    logger.debug(f"Reading text file: {path}")
    text = path.read_text(encoding="utf-8")
    logger.debug(f"Loaded {len(text)} characters from {path.name}")
    return text


def _load_pdf(path: Path) -> str:
    """
    Extract text from a PDF file using pypdf.

    Candidate note: for complex PDFs (tables, scanned pages) consider:
      - pdfplumber for better layout-aware extraction
      - pytesseract for OCR on scanned documents
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError(
            "pypdf is required for PDF support. Install it with: pip install pypdf"
        )

    logger.debug(f"Reading PDF file: {path}")
    reader = PdfReader(str(path))
    pages = []

    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        if text:
            pages.append(text)
            logger.debug(f"Extracted {len(text)} chars from page {i + 1}")
        else:
            logger.warning(f"Page {i + 1} yielded no text (may be image-based)")

    full_text = "\n\n".join(pages)
    logger.info(
        f"PDF extracted: {len(reader.pages)} pages, {len(full_text)} characters"
    )
    return full_text
