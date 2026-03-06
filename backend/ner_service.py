import time
import threading
from typing import Any, Dict, List, Tuple

from config import DEFAULT_MODEL, SUPPORTED_MODELS, CHUNK_CHAR_THRESHOLD
from model_loader import get_model
from chunking import chunk_text

_label_embed_cache: Dict[Tuple[str, Tuple[str, ...]], Any] = {}
_cache_lock = threading.Lock()


def parse_labels(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        labels = [str(x).strip() for x in raw]
        return [x for x in labels if x]
    if isinstance(raw, str):
        labels = [x.strip() for x in raw.split(",")]
        return [x for x in labels if x]
    return []


def clear_label_cache() -> None:
    with _cache_lock:
        _label_embed_cache.clear()


def _run_ner_on_text(
    model: Any,
    text: str,
    labels: List[str],
    threshold: float,
    use_cache: bool,
    model_name: str,
    label_batch_size: int,
) -> Tuple[List[Dict], bool]:
    """Run NER on a single text span; returns (entities, cached_labels)."""
    cached_labels = False
    supports_label_embeds = hasattr(model, "encode_labels") and hasattr(
        model, "batch_predict_with_embeds"
    )

    if use_cache and supports_label_embeds:
        cache_key = (model_name, tuple(labels))
        embeds = None
        with _cache_lock:
            embeds = _label_embed_cache.get(cache_key)
        if embeds is None:
            embeds = model.encode_labels(labels, batch_size=label_batch_size)
            with _cache_lock:
                _label_embed_cache[cache_key] = embeds
        else:
            cached_labels = True
        try:
            outputs = model.batch_predict_with_embeds(
                [text], embeds, labels, threshold=threshold
            )
            entities = outputs[0] if isinstance(outputs, list) and outputs else []
        except Exception:
            entities = model.predict_entities(text, labels, threshold=threshold)
    else:
        entities = model.predict_entities(text, labels, threshold=threshold)
    return entities, cached_labels


def handle_ner(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    model_name = str(payload.get("model") or DEFAULT_MODEL)
    text = str(payload.get("text") or "")
    labels = parse_labels(payload.get("labels"))
    threshold = payload.get("threshold", 0.05)
    use_cache = bool(payload.get("use_cache", True))
    label_batch_size = int(payload.get("label_batch_size", 8))
    use_chunking = bool(payload.get("use_chunking", True))
    chunk_char_threshold = int(payload.get("chunk_char_threshold", CHUNK_CHAR_THRESHOLD))

    if model_name not in SUPPORTED_MODELS:
        return (
            {
                "error": "Unsupported 'model'",
                "supported_models": SUPPORTED_MODELS,
                "default_model": DEFAULT_MODEL,
            },
            400,
        )
    if not text.strip():
        return {"error": "Missing 'text'"}, 400
    if not labels:
        return {"error": "Missing 'labels' (array or comma-separated string)"}, 400

    try:
        threshold = float(threshold)
    except Exception:
        return {"error": "Invalid 'threshold'"}, 400
    threshold = max(0.0, min(1.0, threshold))

    model = get_model(model_name)

    t0 = time.perf_counter()
    entities: List[Dict] = []
    cached_labels = False
    chunks_used: int | None = None

    if use_chunking and len(text) > chunk_char_threshold:
        try:
            chunks = chunk_text(text)
        except Exception as e:
            return {"error": f"Chunking failed: {e!s}"}, 500
        if chunks:
            for c in chunks:
                start_offset = getattr(c, "start_index", 0)
                chunk_text_value = getattr(c, "text", "")
                if not chunk_text_value:
                    continue
                ents, cached = _run_ner_on_text(
                    model,
                    chunk_text_value,
                    labels,
                    threshold,
                    use_cache,
                    model_name,
                    label_batch_size,
                )
                cached_labels = cached_labels or cached
                for e in ents:
                    ent = dict(e)
                    ent["start"] = (ent.get("start") or 0) + start_offset
                    ent["end"] = (ent.get("end") or 0) + start_offset
                    entities.append(ent)
            entities.sort(key=lambda x: (x.get("start", 0), x.get("end", 0)))
            chunks_used = len(chunks)
        else:
            entities, cached_labels = _run_ner_on_text(
                model, text, labels, threshold, use_cache, model_name, label_batch_size
            )
    else:
        entities, cached_labels = _run_ner_on_text(
            model, text, labels, threshold, use_cache, model_name, label_batch_size
        )

    took_ms = int((time.perf_counter() - t0) * 1000)

    out: Dict[str, Any] = {
        "model": model_name,
        "entities": entities,
        "cached_labels": cached_labels,
        "took_ms": took_ms,
    }
    if chunks_used is not None:
        out["chunks_used"] = chunks_used
    return out, 200

