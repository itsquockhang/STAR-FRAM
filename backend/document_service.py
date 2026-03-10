from __future__ import annotations

import io
import os
from typing import Any, Dict, Tuple

from docx import Document


def _read_txt(data: bytes) -> str:
    # Try UTF-8 with BOM, then fallback to latin-1 as last resort
    for enc in ("utf-8-sig", "utf-8", "cp1258", "latin-1"):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode("utf-8", errors="replace")


def _read_docx(data: bytes) -> str:
    with io.BytesIO(data) as f:
        doc = Document(f)
        paras = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        return "\n".join(paras).strip()


def extract_text_from_upload(filename: str, data: bytes) -> Tuple[Dict[str, Any], int]:
    """
    Extract plain text from an uploaded file.

    Supported:
    - .txt
    - .docx

    Not supported yet:
    - .doc (legacy Word format) -> returns a temporary error
    """
    name = (filename or "").strip()
    if not name:
        return {"error": "Missing filename"}, 400

    ext = os.path.splitext(name)[1].lower()
    if not data:
        return {"error": "Empty file"}, 400

    try:
        if ext == ".txt":
            text = _read_txt(data).strip()
        elif ext == ".docx":
            text = _read_docx(data).strip()
        elif ext == ".doc":
            return {
                "error": "DOC format (.doc) is not supported yet (temporary). Please convert to .docx or .txt."
            }, 415
        else:
            return {"error": f"Unsupported file type: {ext or '(no extension)'}"}, 415
    except Exception as e:
        return {"error": f"Failed to extract text: {e!s}"}, 500

    if not text:
        return {"error": "No readable text found in file."}, 422

    return {
        "text": text,
        "filename": name,
        "byte_size": len(data),
        "file_type": ext.lstrip("."),
    }, 200

