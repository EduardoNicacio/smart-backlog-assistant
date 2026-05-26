"""
src/document_loader.py
-----------------------
Loads product specification documents from .txt or .pdf files.

Supported formats
-----------------
.txt, .md - read directly as UTF-8 text.
.pdf - text extracted page-by-page using pypdf.

Usage
-----
    from src.document_loader import load_document

    spec = load_document("inputs/sample_requirements.txt")
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load document helper
# ---------------------------------------------------------------------------

def load_document(path: str) -> str:
    """
    Load and return the text content of a text, markdown or PDF file.

    Parameters
    ----------
    path : str
        Absolute or relative path to the document.

    Returns
    -------
    str
        The extracted text content.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    ValueError
        If the file extension is not supported.
    """
    p = Path(path)

    if not p.exists():
        raise FileNotFoundError(f"Document not found: {path}")

    ext = p.suffix.lower()

    if ext == ".txt" or ext == ".md":
        return _load_txt(p)
    elif ext == ".pdf":
        return _load_pdf(p)
    else:
        raise ValueError(f"Unsupported document format '{ext}'. Supported: .txt, .md, .pdf")

# ---------------------------------------------------------------------------
# Load _txt_ and _md_ helper
# ---------------------------------------------------------------------------

def _load_txt(path: Path) -> str:
    """Read a plain-text or markdown file."""
    try:
        content = path.read_text(encoding="utf-8")
        logger.info("Loaded text document: %s (%d chars)", path.name, len(content))
        return content
    except Exception:
        logger.exception("Failed to read text file: %s", path)
        raise

# ---------------------------------------------------------------------------
# Load _pdf_ helper
# ---------------------------------------------------------------------------

def _load_pdf(path: Path) -> str:
    """Extract text from a PDF using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError(
            "pypdf is required to load PDF files. Install it with: pip install pypdf"
        ) from exc

    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        content = "\n\n".join(pages).strip()
        logger.info(
            "Loaded PDF document: %s (%d pages, %d chars)",
            path.name,
            len(reader.pages),
            len(content),
        )
        return content
    except Exception:
        logger.exception("Failed to read PDF file: %s", path)
        raise
