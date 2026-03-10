import threading
from types import SimpleNamespace
from typing import Any, List

from chonkie import SemanticChunker, TokenChunker
from underthesea import sent_tokenize
from tokenizers import Tokenizer

from config import CHUNK_EMBEDDING_MODEL, CHUNK_SIMILARITY_THRESHOLD, CHUNK_SIZE_TOKENS

_semantic_chunker: Any = None
_token_chunker: Any = None
_chunker_lock = threading.Lock()


def get_semantic_chunker() -> SemanticChunker:
    global _semantic_chunker
    if _semantic_chunker is None:
        with _chunker_lock:
            if _semantic_chunker is None:
                _semantic_chunker = SemanticChunker(
                    embedding_model=CHUNK_EMBEDDING_MODEL,
                    threshold=CHUNK_SIMILARITY_THRESHOLD,
                    chunk_size=CHUNK_SIZE_TOKENS,
                    similarity_window=3,
                )
    return _semantic_chunker


def get_token_chunker() -> TokenChunker:
    global _token_chunker
    if _token_chunker is None:
        with _chunker_lock:
            if _token_chunker is None:
                custom_tokenizer = Tokenizer.from_pretrained("google/embeddinggemma-300m")
                _token_chunker = TokenChunker(
                    tokenizer=custom_tokenizer,
                    chunk_size=CHUNK_SIZE_TOKENS,
                    chunk_overlap=20,
                )
    return _token_chunker


def _sentence_chunks(text: str) -> List[Any]:
    """
    Build chunks by Vietnamese sentence using underthesea.sent_tokenize.
    Each chunk has .text, .start_index, .end_index like Chonkie chunks.
    """
    sentences = sent_tokenize(text)
    chunks: List[Any] = []
    cursor = 0
    for sent in sentences:
        if not sent:
            continue
        idx = text.find(sent, cursor)
        if idx == -1:
            # Fallback: skip if we cannot locate
            continue
        start = idx
        end = idx + len(sent)
        cursor = end
        chunks.append(SimpleNamespace(text=sent, start_index=start, end_index=end))
    return chunks


def chunk_text(text: str, strategy: str = "semantic") -> List[Any]:
    """
    Split text into chunks.

    - strategy == "semantic": use SemanticChunker (default)
    - strategy == "token": use TokenChunker (fixed-size token chunks)
    - strategy == "sentence": use underthesea.sent_tokenize for sentence-based chunks
    """
    if not text.strip():
        return []

    if strategy == "token":
        chunker = get_token_chunker()
        chunks = chunker.chunk(text)
        return list(chunks)
    if strategy == "sentence":
        return _sentence_chunks(text)

    chunker = get_semantic_chunker()
    chunks = chunker.chunk(text)
    return list(chunks)

