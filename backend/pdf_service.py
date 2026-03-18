from __future__ import annotations

import base64
import io
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

try:
    import fitz
except ImportError:
    fitz = None

from llm_agri_service import ocr_image_base64

MIN_TEXT_PER_PAGE_FOR_PYMUPDF = 50
PDF_RENDER_DPI = 150
MAX_OCR_WORKERS = 4
MAX_PAGES_TO_EXTRACT = 10


def _extract_text_pymupdf(doc: Any) -> str:
    parts: List[str] = []
    for i in range(len(doc)):
        page = doc[i]
        text = (page.get_text() or "").strip()
        if text:
            parts.append(text)
    return "\n\n".join(parts).strip()


def _page_has_enough_text(doc: Any) -> bool:
    total = 0
    for i in range(len(doc)):
        page = doc[i]
        total += len((page.get_text() or "").strip())
    if len(doc) == 0:
        return False
    return total >= len(doc) * MIN_TEXT_PER_PAGE_FOR_PYMUPDF


def _render_page_to_base64(doc: Any, page_num: int) -> str:
    page = doc[page_num]
    pix = page.get_pixmap(dpi=PDF_RENDER_DPI, alpha=False)
    img_bytes = pix.tobytes("png")
    return base64.b64encode(img_bytes).decode("ascii")


def extract_text_from_pdf(data: bytes, filename: str) -> Tuple[Dict[str, Any], int]:
    """
    Extract text from PDF. Prefer PyMuPDF (fitz) direct text extraction.
    If the PDF has little or no extractable text (e.g. scanned), render pages
    to images and use LLM vision OCR.
    """
    if fitz is None:
        return {
            "error": "PyMuPDF is not installed. Install with: pip install PyMuPDF",
        }, 501

    if not data:
        return {"error": "Empty file"}, 400

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as e:
        return {"error": f"Failed to open PDF: {e!s}"}, 400

    try:
        num_pages = len(doc)
        if num_pages == 0:
            return {"error": "PDF has no pages."}, 422
        
        if num_pages > MAX_PAGES_TO_EXTRACT:
            doc.close()
            return {
                "error": f"PDF has {num_pages} pages. Maximum allowed is {MAX_PAGES_TO_EXTRACT} pages."
            }, 422

        # Prefer direct text extraction
        if _page_has_enough_text(doc):
            text = _extract_text_pymupdf(doc)
            doc.close()
            if text:
                return {
                    "text": text,
                    "filename": filename or "document.pdf",
                    "byte_size": len(data),
                    "method": "pymupdf",
                    "page_count": num_pages,
                }, 200

        # Fallback: render each page to image and OCR with LLM
        page_texts: List[str] = [""] * num_pages
        workers = min(MAX_OCR_WORKERS, num_pages)

        def ocr_page(page_idx: int) -> Tuple[int, str]:
            b64 = _render_page_to_base64(doc, page_idx)
            content = ocr_image_base64(b64, mime="image/png")
            return (page_idx, content)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(ocr_page, i): i for i in range(num_pages)}
            for future in as_completed(futures):
                page_idx, content = future.result()
                page_texts[page_idx] = content

        doc.close()

        combined = "\n\n".join(
            f"--- Page {i + 1} ---\n{t}" for i, t in enumerate(page_texts) if t.strip()
        ).strip()
        if not combined:
            return {"error": "LLM OCR returned no text for any page."}, 502

        return {
            "text": combined,
            "filename": filename or "document.pdf",
            "byte_size": len(data),
            "method": "llm_ocr",
            "page_count": num_pages,
        }, 200

    except Exception as e:
        try:
            doc.close()
        except Exception:
            pass
        return {"error": f"PDF extraction failed: {e!s}"}, 500
