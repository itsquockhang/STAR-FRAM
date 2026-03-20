import re
import threading
from types import SimpleNamespace
from typing import Any, List, Tuple

import torch
from chonkie import SemanticChunker, TokenChunker
from tokenizers import Tokenizer
from underthesea import lang_detect, sent_tokenize as vi_sent_tokenize

from config import (
    CHUNK_EMBEDDING_MODEL,
    CHUNK_SIMILARITY_THRESHOLD,
    CHUNK_SIZE_TOKENS,
)

_semantic_chunkers: dict[int, Any] = {}
_token_chunkers: dict[int, Any] = {}
_chunker_lock = threading.Lock()
_nltk_punkt_ready = False

_PARA_SPLIT = re.compile(r"\n\s*\n")
_WS_COLLAPSE = re.compile(r"\s+")


def _clamp_chunk_size_tokens(chunk_size_tokens: int | None) -> int:
    size = int(chunk_size_tokens or CHUNK_SIZE_TOKENS)
    return max(16, size)


def _ensure_nltk_punkt() -> None:
    global _nltk_punkt_ready
    if _nltk_punkt_ready:
        return
    with _chunker_lock:
        if _nltk_punkt_ready:
            return
        import nltk

        try:
            nltk.data.find("tokenizers/punkt")
        except LookupError:
            nltk.download("punkt", quiet=True)
        _nltk_punkt_ready = True


def _tokenize_paragraph(lang: str, para: str) -> List[str]:
    try:
        if lang == "vi":
            raw = vi_sent_tokenize(para)
        else:
            from nltk.tokenize import sent_tokenize as nltk_sent_tokenize

            raw = nltk_sent_tokenize(para)
    except Exception:
        raw = [para]
    return [s.strip() for s in raw if s and s.strip()]


def _split_sentences(text: str) -> List[str]:
    if not text or not text.strip():
        return []

    _ensure_nltk_punkt()

    out: List[str] = []
    for para in _PARA_SPLIT.split(text):
        para = para.strip()
        if not para:
            continue
        try:
            lang = lang_detect(para)
        except Exception:
            lang = ""
        out.extend(_tokenize_paragraph(lang, para))
    return out


def _find_sentence_index(text: str, sent: str, cursor: int) -> int | None:
    idx = text.find(sent, cursor)
    if idx != -1:
        return idx
    norm = _WS_COLLAPSE.sub(" ", sent).strip()
    window = text[cursor:]
    flat = _WS_COLLAPSE.sub(" ", window)
    m = re.search(re.escape(norm), flat)
    if m is None:
        return None
    return cursor + m.start()


def _locate_sentence_spans(text: str, sentences: List[str]) -> Tuple[List[str], List[Tuple[int, int]]]:
    found: List[str] = []
    spans: List[Tuple[int, int]] = []
    cursor = 0

    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue

        idx = _find_sentence_index(text, sent, cursor)
        if idx is None:
            continue

        start = idx
        end = idx + len(sent)
        if spans and start < spans[-1][1]:
            idx2 = _find_sentence_index(text, sent, spans[-1][1])
            if idx2 is None:
                continue
            start = idx2
            end = idx2 + len(sent)

        found.append(sent)
        spans.append((start, end))
        cursor = end

    return found, spans


def _sentence_chunks(text: str) -> List[Any]:
    sentences = _split_sentences(text)
    if not sentences:
        return []

    _, spans = _locate_sentence_spans(text, sentences)
    if not spans:
        return [SimpleNamespace(text=text, start_index=0, end_index=len(text))]

    return [
        SimpleNamespace(text=text[start:end], start_index=start, end_index=end)
        for start, end in spans
    ]


def _clear_torch_memory() -> None:
    try:
        import gc

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
    except Exception:
        pass


def release_chunking_resources() -> None:
    with _chunker_lock:
        semantic_chunkers = list(_semantic_chunkers.values())
        token_chunkers = list(_token_chunkers.values())
        _semantic_chunkers.clear()
        _token_chunkers.clear()

    try:
        del semantic_chunkers
        del token_chunkers
    except Exception:
        pass

    _clear_torch_memory()


def get_semantic_chunker(chunk_size_tokens: int | None = None) -> SemanticChunker:
    size = _clamp_chunk_size_tokens(chunk_size_tokens)
    with _chunker_lock:
        ch = _semantic_chunkers.get(size)
        if ch is None:
            ch = SemanticChunker(
                embedding_model=CHUNK_EMBEDDING_MODEL,
                threshold=CHUNK_SIMILARITY_THRESHOLD,
                chunk_size=size,
                similarity_window=3,
            )
            _semantic_chunkers[size] = ch
    return ch


def get_token_chunker(chunk_size_tokens: int | None = None) -> TokenChunker:
    size = _clamp_chunk_size_tokens(chunk_size_tokens)
    with _chunker_lock:
        ch = _token_chunkers.get(size)
        if ch is None:
            ch = TokenChunker(
                tokenizer=Tokenizer.from_pretrained("google/embeddinggemma-300m"),
                chunk_size=size,
                chunk_overlap=20,
            )
            _token_chunkers[size] = ch
    return ch


def chunk_text(text: str, strategy: str = "semantic", *, chunk_size_tokens: int | None = None) -> List[Any]:
    if not text.strip():
        return []

    if strategy == "token":
        return list(get_token_chunker(chunk_size_tokens).chunk(text))
    if strategy == "sentence":
        return _sentence_chunks(text)
    return list(get_semantic_chunker(chunk_size_tokens).chunk(text))
