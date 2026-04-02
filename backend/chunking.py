import threading
from typing import Any, List

import torch
from chonkie import RecursiveChunker, SemanticChunker, TokenChunker
from tokenizers import Tokenizer

from config import (
    CHUNK_EMBEDDING_MODEL,
    CHUNK_SIMILARITY_THRESHOLD,
    CHUNK_SIZE_TOKENS,
)

_semantic_chunkers: dict[int, Any] = {}
_token_chunkers: dict[int, Any] = {}
_recursive_chunkers: dict[int, Any] = {}
_chunker_lock = threading.Lock()


def _clamp_chunk_size_tokens(chunk_size_tokens: int | None) -> int:
    size = int(chunk_size_tokens or CHUNK_SIZE_TOKENS)
    return max(16, size)


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
        recursive_chunkers = list(_recursive_chunkers.values())
        _semantic_chunkers.clear()
        _token_chunkers.clear()
        _recursive_chunkers.clear()

    try:
        del semantic_chunkers
        del token_chunkers
        del recursive_chunkers
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


def get_recursive_chunker(chunk_size_tokens: int | None = None) -> RecursiveChunker:
    size = _clamp_chunk_size_tokens(chunk_size_tokens)
    with _chunker_lock:
        ch = _recursive_chunkers.get(size)
        if ch is None:
            ch = RecursiveChunker(
                tokenizer=Tokenizer.from_pretrained("google/embeddinggemma-300m"),
                chunk_size=size,
            )
            _recursive_chunkers[size] = ch
    return ch


def chunk_text(text: str, strategy: str = "semantic", *, chunk_size_tokens: int | None = None) -> List[Any]:
    if not text.strip():
        return []

    if strategy == "token":
        return list(get_token_chunker(chunk_size_tokens).chunk(text))
    if strategy == "recursive":
        return list(get_recursive_chunker(chunk_size_tokens).chunk(text))
    return list(get_semantic_chunker(chunk_size_tokens).chunk(text))
