import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

import torch

from config import (
    CHUNK_MAX_WORKERS,
    CHUNK_SIZE_TOKENS,
    DEFAULT_MODEL,
    SUPPORTED_MODELS,
    CHUNK_CHAR_THRESHOLD,
)
from model_loader import get_model, release_model
from chunking import chunk_text, release_chunking_resources
from text_corrector import correct_text

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


def clear_label_cache_for_model(model_name: str) -> None:
    with _cache_lock:
        keys = [k for k in _label_embed_cache if k[0] == model_name]
        for key in keys:
            _label_embed_cache.pop(key, None)


def _run_ner_on_text(
    model: Any,
    text: str,
    labels: List[str],
    threshold: float,
    multi_label: bool,
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
                [text], embeds, labels, threshold=threshold, multi_label=multi_label
            )
            entities = outputs[0] if isinstance(outputs, list) and outputs else []
        except Exception:
            entities = model.predict_entities(
                text, labels, threshold=threshold, multi_label=multi_label
            )
    else:
        entities = model.predict_entities(
            text, labels, threshold=threshold, multi_label=multi_label
        )
    return entities, cached_labels


def handle_ner(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    model_name = str(payload.get("model") or DEFAULT_MODEL)
    text = str(payload.get("text") or "")
    labels = parse_labels(payload.get("labels"))
    threshold = payload.get("threshold", 0.05)
    chunking_strategy = str(payload.get("chunking_strategy") or "semantic")
    if chunking_strategy in ("text-tiling", "sentence"):
        chunking_strategy = "semantic"
    use_spell_correction = bool(payload.get("use_spell_correction", False))
    spell_correction_max_tokens = int(payload.get("spell_correction_max_tokens", 160))
    use_cache = bool(payload.get("use_cache", True))
    unload_model_after_inference = bool(payload.get("unload_model_after_inference", True))
    unload_chunking_after_inference = bool(payload.get("unload_chunking_after_inference", True))
    label_batch_size = int(payload.get("label_batch_size", 8))
    use_chunking = bool(payload.get("use_chunking", True))
    chunk_char_threshold = int(payload.get("chunk_char_threshold", CHUNK_CHAR_THRESHOLD))
    chunk_size_tokens = int(payload.get("chunk_size_tokens", CHUNK_SIZE_TOKENS))
    multi_label = bool(payload.get("multi_label", True))

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

    model = None
    try:
        model = get_model(model_name)

        t0 = time.perf_counter()
        entities: List[Dict] = []
        cached_labels = False
        chunks_used: int | None = None
        raw_chunks: List[Dict[str, Any]] | None = None
        text_used: str | None = None
        max_workers = int(payload.get("chunk_max_workers", CHUNK_MAX_WORKERS))
        if max_workers < 1:
            max_workers = 1
        if torch.cuda.is_available():
            max_workers = 1

        if use_chunking and len(text) > chunk_char_threshold:
            try:
                chunks = chunk_text(text, strategy=chunking_strategy, chunk_size_tokens=chunk_size_tokens)
            except Exception as e:
                return {"error": f"Chunking failed: {e!s}"}, 500
            if chunks:
                joiner = "\n\n"
                raw_chunks = []
                corrected_parts: List[str] = []
                cursor = 0
                chunk_texts: List[Tuple[int, str]] = []
                for idx, c in enumerate(chunks):
                    original_chunk = getattr(c, "text", "") or ""
                    if original_chunk.strip():
                        chunk_texts.append((idx, original_chunk))

                # 1) Correct chunks in parallel (CPU-friendly). For CUDA we force workers=1 above.
                if use_spell_correction and chunk_texts:
                    with ThreadPoolExecutor(max_workers=min(max_workers, len(chunk_texts))) as ex:
                        corrected_map = dict(
                            zip(
                                [i for i, _ in chunk_texts],
                                list(
                                    ex.map(
                                        lambda t: correct_text(
                                            t, max_tokens=spell_correction_max_tokens
                                        ),
                                        [txt for _, txt in chunk_texts],
                                    )
                                ),
                            )
                        )
                else:
                    corrected_map = {i: txt for i, txt in chunk_texts}

                # 2) Stitch corrected text to compute offsets (must be sequential)
                chunk_entries: List[Tuple[int, str, str, int, int]] = []
                for idx, original_chunk in chunk_texts:
                    corrected_chunk = corrected_map.get(idx, original_chunk)

                    if corrected_parts:
                        cursor += len(joiner)
                        corrected_parts.append(joiner)

                    start_offset = cursor
                    corrected_parts.append(corrected_chunk)
                    cursor += len(corrected_chunk)
                    end_offset = cursor
                    chunk_entries.append(
                        (idx, original_chunk, corrected_chunk, start_offset, end_offset)
                    )

                    raw_chunks.append(
                        {
                            "index": idx,
                            "start": int(start_offset),
                            "end": int(end_offset),
                            "original_text": original_chunk,
                            "corrected_text": corrected_chunk,
                        }
                    )

                # 3) Run NER per corrected chunk in parallel (CPU-friendly)
                def _infer_one(entry: Tuple[int, str, str, int, int]):
                    _idx, _orig, corrected, start_offset, _end = entry
                    ents, cached = _run_ner_on_text(
                        model,
                        corrected,
                        labels,
                        threshold,
                        multi_label,
                        use_cache,
                        model_name,
                        label_batch_size,
                    )
                    adjusted = []
                    for e in ents:
                        ent = dict(e)
                        ent["start"] = (ent.get("start") or 0) + start_offset
                        ent["end"] = (ent.get("end") or 0) + start_offset
                        adjusted.append(ent)
                    return adjusted, cached

                if chunk_entries:
                    if max_workers > 1 and len(chunk_entries) > 1:
                        with ThreadPoolExecutor(
                            max_workers=min(max_workers, len(chunk_entries))
                        ) as ex:
                            results = list(ex.map(_infer_one, chunk_entries))
                    else:
                        results = [_infer_one(e) for e in chunk_entries]

                    for adjusted, cached in results:
                        cached_labels = cached_labels or cached
                        entities.extend(adjusted)

                entities.sort(key=lambda x: (x.get("start", 0), x.get("end", 0)))
                chunks_used = len(chunks)
                text_used = "".join(corrected_parts)
            else:
                # Fallback: no chunks returned; run on full text (optionally corrected)
                text_used = (
                    correct_text(text, max_tokens=spell_correction_max_tokens)
                    if use_spell_correction
                    else text
                )
                entities, cached_labels = _run_ner_on_text(
                    model,
                    text_used,
                    labels,
                    threshold,
                    multi_label,
                    use_cache,
                    model_name,
                    label_batch_size,
                )
        else:
            text_used = (
                correct_text(text, max_tokens=spell_correction_max_tokens)
                if use_spell_correction
                else text
            )
            entities, cached_labels = _run_ner_on_text(
                model,
                text_used,
                labels,
                threshold,
                multi_label,
                use_cache,
                model_name,
                label_batch_size,
            )

        took_ms = int((time.perf_counter() - t0) * 1000)

        out: Dict[str, Any] = {
            "model": model_name,
            "entities": entities,
            "cached_labels": cached_labels,
            "took_ms": took_ms,
            "chunking_strategy": chunking_strategy,
            "use_spell_correction": use_spell_correction,
            "multi_label": multi_label,
        }
        if chunks_used is not None:
            out["chunks_used"] = chunks_used
        if raw_chunks is not None:
            out["chunks"] = raw_chunks
        if text_used is not None:
            out["text_used"] = text_used
        return out, 200
    finally:
        if unload_chunking_after_inference:
            release_chunking_resources()
        if unload_model_after_inference:
            clear_label_cache_for_model(model_name)
            release_model(model_name)
        model = None

