from __future__ import annotations

from typing import Any, Dict, Tuple

import trafilatura


def extract_web_text(url: str) -> Tuple[Dict[str, Any], int]:
    u = (url or "").strip()
    if not u:
        return {"error": "Missing 'url'"}, 400

    try:
        downloaded = trafilatura.fetch_url(u)
    except Exception as e:
        return {"error": f"Failed to fetch URL: {e!s}"}, 502

    if not downloaded:
        return {"error": "Failed to fetch URL (empty response)."}, 502

    try:
        text = trafilatura.extract(downloaded)
    except Exception as e:
        return {"error": f"Failed to extract text: {e!s}"}, 500

    if not text or not str(text).strip():
        return {
            "error": "No readable main text found (temporary). Try another URL or provide the content as a document."
        }, 422

    out_text = str(text).strip()
    return {"text": out_text, "url": u, "char_count": len(out_text)}, 200

