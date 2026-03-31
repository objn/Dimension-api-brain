"""
Document parsing service.
Extract text from .docx, .pdf (including scanned), .jpg, .png.
When local extraction fails (e.g. image-only PDF), can fall back to LLM vision (batched by pages).
"""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Optional OCR (Tesseract must be installed on system)
_ocr_available: Optional[bool] = None


def _check_ocr() -> bool:
    global _ocr_available
    if _ocr_available is not None:
        return _ocr_available
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        _ocr_available = True
    except Exception as e:
        logger.warning("OCR (pytesseract) not available: %s. Scanned PDFs and images may not be parsed.", e)
        _ocr_available = False
    return _ocr_available


def parse_docx(file_path: str) -> str:
    """Extract text from a .docx file."""
    try:
        from docx import Document
        doc = Document(file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        logger.error("Failed to parse docx %s: %s", file_path, e)
        raise ValueError(f"Failed to parse DOCX: {e}") from e


def _pdf_extract_text_pymupdf(file_path: str) -> str:
    """Extract text from PDF using pymupdf (works for text-based PDFs)."""
    try:
        import fitz  # pymupdf
        doc = fitz.open(file_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts).strip()
    except Exception as e:
        logger.warning("pymupdf PDF extraction failed: %s", e)
        return ""


def _pdf_extract_ocr(file_path: str) -> str:
    """Extract text from PDF using OCR (for scanned PDFs). Requires pdf2image and pytesseract."""
    if not _check_ocr():
        return ""
    try:
        from pdf2image import convert_from_path
        import pytesseract
        images = convert_from_path(file_path)
        text_parts = []
        for img in images:
            text_parts.append(pytesseract.image_to_string(img))
        return "\n".join(text_parts).strip()
    except Exception as e:
        logger.warning("PDF OCR failed for %s: %s", file_path, e)
        return ""


def parse_pdf(file_path: str, use_ocr_for_scanned: bool = True) -> str:
    """
    Extract text from PDF. Uses pymupdf first; if little or no text (scanned PDF), falls back to OCR.
    Raises ValueError only when no text could be extracted (caller may then try LLM vision).
    """
    text = _pdf_extract_text_pymupdf(file_path)
    if use_ocr_for_scanned and (not text or len(text.strip()) < 100):
        ocr_text = _pdf_extract_ocr(file_path)
        if ocr_text:
            text = ocr_text
    if not text or not text.strip():
        raise ValueError("Could not extract text from PDF (may be empty or image-only without OCR).")
    return text.strip()


def parse_pdf_via_llm_vision(
    file_path: str,
    provider: str = "openai",
    max_pages_per_call: int = 5,
    timeout_per_batch: float = 120.0,
) -> str:
    """
    Extract text from a PDF by rendering each page to an image and sending to a vision LLM
    (OCR-style: one page per call by default). Loop over each page, extract text, concatenate.
    Set max_pages_per_call > 1 to batch pages and reduce API calls (e.g. 5 for speed).

    Requires Poppler (e.g. poppler-utils) on PATH for pdf2image; no fallback.
    """
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ValueError("pdf2image is required for LLM vision PDF extraction. Install: pip install pdf2image")

    try:
        import src.services.llm_router as LLM
    except ImportError:
        raise ValueError("LLM router is required for vision extraction")

    images = convert_from_path(file_path)
    if not images:
        return ""

    text_parts = []
    total = len(images)
    for start in range(0, total, max_pages_per_call):
        batch = images[start : start + max_pages_per_call]
        page_start = start + 1
        page_end = min(start + max_pages_per_call, total)
        batch_num = start // max_pages_per_call + 1
        total_batches = (total + max_pages_per_call - 1) // max_pages_per_call
        logger.info(
            "PDF vision extraction (OCR-style) page %s-%s of %s (batch %s/%s)",
            page_start, page_end, total, batch_num, total_batches,
        )
        chunk = LLM.extract_text_from_images_vision(
            batch,
            provider=provider,
            timeout=timeout_per_batch,
            single_page_prompt=(len(batch) == 1),
        )
        if chunk:
            if total > 1 and len(batch) == 1:
                text_parts.append(f"--- Page {page_start} ---\n{chunk}")
            else:
                text_parts.append(chunk)
    return "\n\n".join(text_parts).strip()


def parse_image_via_llm_vision(
    file_path: str, provider: str = "openai", timeout: float = 120.0
) -> str:
    """Extract text from a raster image (.jpg, .png) using a vision LLM (high-accuracy path)."""
    try:
        from PIL import Image
        import src.services.llm_router as LLM
    except ImportError as e:
        raise ValueError(f"Vision image parsing requires Pillow and LLM router: {e}") from e
    try:
        img = Image.open(file_path)
        return LLM.extract_text_from_images_vision(
            [img],
            provider=provider,
            timeout=timeout,
            single_page_prompt=True,
        )
    except Exception as e:
        logger.error("Failed vision image parse %s: %s", file_path, e)
        raise ValueError(f"Failed to parse image via vision: {e}") from e


def parse_image(file_path: str) -> str:
    """Extract text from image (.jpg, .png) using OCR."""
    if not _check_ocr():
        raise ValueError("OCR (Tesseract) is not available. Install Tesseract and pytesseract for image parsing.")
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(file_path)
        text = pytesseract.image_to_string(img)
        return text.strip() if text else ""
    except Exception as e:
        logger.error("Failed to parse image %s: %s", file_path, e)
        raise ValueError(f"Failed to parse image: {e}") from e


def parse_document(file_path: str, mime_type: Optional[str] = None, filename: Optional[str] = None) -> str:
    """
    Extract text from a document file. Dispatches by extension or mime type.
    Returns normalized text (or markdown) for storage in a node.
    """
    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"File not found: {file_path}")

    ext = path.suffix.lower()
    if ext == ".docx":
        return parse_docx(file_path)
    if ext == ".pdf":
        return parse_pdf(file_path)
    if ext in (".jpg", ".jpeg", ".png"):
        return parse_image(file_path)

    # Fallback by mime
    if mime_type:
        m = mime_type.split(";")[0].strip().lower()
        if "wordprocessing" in m or "docx" in m:
            return parse_docx(file_path)
        if m == "application/pdf":
            return parse_pdf(file_path)
        if m.startswith("image/"):
            return parse_image(file_path)

    raise ValueError(f"Unsupported file type: {ext or mime_type}")
