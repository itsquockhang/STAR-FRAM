"""Compute dense embeddings for saved NER chunks (sentence-transformers)."""

from __future__ import annotations

import threading
from typing import List, Optional

from config import SAVED_CHUNK_EMBEDDING_MODEL

_lock = threading.Lock()
_model = None
_model_name: str | None = None


def _get_model():
    global _model, _model_name
    name = SAVED_CHUNK_EMBEDDING_MODEL
    with _lock:
        if _model is None or _model_name != name:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(name)
            _model_name = name
        return _model


def embed_text(text: str) -> Optional[List[float]]:
    t = (text or "").strip()
    if not t:
        return None
    try:
        m = _get_model()
        v = m.encode(t, normalize_embeddings=True, prompt_name='sts_query')
        if hasattr(v, "tolist"):
            return [float(x) for x in v.tolist()]
        return [float(x) for x in list(v)]
    except Exception:
        return None
