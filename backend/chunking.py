import threading
from types import SimpleNamespace
from typing import Any, List

import numpy as np
import torch
from chonkie import SemanticChunker, TokenChunker
from sentence_transformers import SentenceTransformer
from tokenizers import Tokenizer
from underthesea import sent_tokenize

from config import CHUNK_EMBEDDING_MODEL, CHUNK_SIMILARITY_THRESHOLD, CHUNK_SIZE_TOKENS

_semantic_chunker: Any = None
_token_chunker: Any = None
_text_tiling_embedder: Any = None
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


def get_text_tiling_embedder() -> SentenceTransformer:
    """
    Lazy-load a SentenceTransformer used for Text Tiling based chunking.
    By default we reuse CHUNK_EMBEDDING_MODEL which is set to embeddinggemma-300m.
    """
    global _text_tiling_embedder
    if _text_tiling_embedder is None:
        with _chunker_lock:
            if _text_tiling_embedder is None:
                if torch.cuda.is_available():
                    device = "cuda"
                elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
                    device = "mps"
                else:
                    device = "cpu"

                _text_tiling_embedder = SentenceTransformer(
                    CHUNK_EMBEDDING_MODEL,
                    device=device,
                )
    return _text_tiling_embedder


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


def _text_tiling_chunks(text: str, k: int = 3, std_factor: float = 0.5) -> List[Any]:
    """
    Text Tiling style chunking using sentence embeddings from embeddinggemma-300m.

    - Split text into sentences (Vietnamese-friendly via underthesea.sent_tokenize)
    - Compute sentence embeddings
    - Compute cosine similarity between left/right windows of size k
    - Place boundaries at low-similarity valleys using a mean-std heuristic
    """
    sentences = sent_tokenize(text)
    if not sentences:
        return []
    if len(sentences) == 1:
        return [SimpleNamespace(text=text, start_index=0, end_index=len(text))]

    # Locate each sentence span in the original text
    spans: List[tuple[int, int]] = []
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
        spans.append((start, end))

    if not spans:
        return [SimpleNamespace(text=text, start_index=0, end_index=len(text))]

    # Trim sentences list to those we actually found spans for
    if len(spans) != len(sentences):
        valid_count = min(len(spans), len(sentences))
        sentences = sentences[:valid_count]
        spans = spans[:valid_count]

    # print("Text Tiling: Encoding sentences...")
    # https://github.com/saeedabc/llm-text-tiling/blob/main/llm_tet.py
    embedder = get_text_tiling_embedder()
    # Shape: (num_sentences, dim)
    sent_embs = embedder.encode(sentences, batch_size=32, convert_to_numpy=True)
    if isinstance(sent_embs, list):
        sent_embs = np.asarray(sent_embs)

    n = sent_embs.shape[0]
    if n <= 1:
        s0, e0 = spans[0]
        return [SimpleNamespace(text=text[s0:e0], start_index=s0, end_index=e0)]

    # Compute cosine similarities between left and right context windows
    sims: List[float] = []
    for i in range(n - 1):
        l_start = max(0, i - k + 1)
        l_end = i + 1
        r_start = i + 1
        r_end = min(n, i + 1 + k)
        l_ctx = sent_embs[l_start:l_end]
        r_ctx = sent_embs[r_start:r_end]
        if l_ctx.size == 0 or r_ctx.size == 0:
            sims.append(1.0)
            continue
        l_vec = l_ctx.mean(axis=0)
        r_vec = r_ctx.mean(axis=0)
        denom = (np.linalg.norm(l_vec) * np.linalg.norm(r_vec)) or 1e-8
        sim = float(np.dot(l_vec, r_vec) / denom)
        sims.append(sim)

    sims_arr = np.asarray(sims, dtype=float)
    mu = float(sims_arr.mean()) if sims_arr.size else 0.0
    sigma = float(sims_arr.std()) if sims_arr.size else 0.0
    threshold = mu - std_factor * sigma

    # Choose boundaries where similarity dips below threshold
    boundary_idxs: List[int] = []
    for i, sim in enumerate(sims):
        if sim < threshold:
            # Optional local-minima check: ensure it's a valley
            left_ok = i == 0 or sim <= sims[i - 1]
            right_ok = i == len(sims) - 1 or sim <= sims[i + 1]
            if left_ok and right_ok:
                boundary_idxs.append(i)

    # If no boundaries found, just return single chunk
    if not boundary_idxs:
        s0, e0 = spans[0][0], spans[-1][1]
        return [SimpleNamespace(text=text[s0:e0], start_index=s0, end_index=e0)]

    chunks: List[Any] = []
    start_sent_idx = 0
    for b in boundary_idxs:
        end_sent_idx = b  # boundary is between b and b+1 → chunk ends at sentence b
        s_start = spans[start_sent_idx][0]
        s_end = spans[end_sent_idx][1]
        chunks.append(SimpleNamespace(text=text[s_start:s_end], start_index=s_start, end_index=s_end))
        start_sent_idx = end_sent_idx + 1

    # Last chunk
    if start_sent_idx < len(spans):
        s_start = spans[start_sent_idx][0]
        s_end = spans[-1][1]
        chunks.append(SimpleNamespace(text=text[s_start:s_end], start_index=s_start, end_index=s_end))

    return chunks


def chunk_text(text: str, strategy: str = "semantic") -> List[Any]:
    """
    Split text into chunks.

    - strategy == "semantic": use SemanticChunker (default)
    - strategy == "token": use TokenChunker (fixed-size token chunks)
    - strategy == "sentence": use underthesea.sent_tokenize for sentence-based chunks
    - strategy == "text-tiling": Text Tiling style chunking with embeddinggemma-300m
    """
    if not text.strip():
        return []

    if strategy == "token":
        chunker = get_token_chunker()
        chunks = chunker.chunk(text)
        return list(chunks)
    if strategy == "sentence":
        return _sentence_chunks(text)
    if strategy == "text-tiling":
        return _text_tiling_chunks(text)

    chunker = get_semantic_chunker()
    chunks = chunker.chunk(text)
    return list(chunks)

