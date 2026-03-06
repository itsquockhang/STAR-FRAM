import threading
from typing import Any, List

from chonkie import SemanticChunker

from config import CHUNK_EMBEDDING_MODEL, CHUNK_SIMILARITY_THRESHOLD, CHUNK_SIZE_TOKENS

_chunker: Any = None
_chunker_lock = threading.Lock()


def get_chunker() -> SemanticChunker:
    global _chunker
    if _chunker is None:
        with _chunker_lock:
            if _chunker is None:
                _chunker = SemanticChunker(
                    embedding_model=CHUNK_EMBEDDING_MODEL,
                    threshold=CHUNK_SIMILARITY_THRESHOLD,
                    chunk_size=CHUNK_SIZE_TOKENS,
                    similarity_window=3,
                )
    return _chunker


def chunk_text(text: str) -> List[Any]:
    """Split text by semantic similarity; returns chunks with .text, .start_index, .end_index."""
    if not text.strip():
        return []
    chunker = get_chunker()
    chunks = chunker.chunk(text)
    return list(chunks)

