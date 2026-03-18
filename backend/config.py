import os

DEFAULT_MODEL = os.getenv("GLINER_MODEL", "knowledgator/gliner-bi-base-v2.0")
SUPPORTED_MODELS = [
    "knowledgator/gliner-bi-base-v2.0",
    "urchade/gliner_multi-v2.1",
    "urchade/gliner_base",
    "urchade/gliner_multi",
    "urchade/gliner_medium-v2",
    "urchade/gliner_medium-v2.1",
    "knowledgator/gliner-qwen-0.5B-v1.0",
    "knowledgator/gliner-qwen-1.5B-v1.0",
]

# Qwen-based GLiNER models: use flash attention and fp16 on CUDA
GLINER_QWEN_MODELS = frozenset({
    "knowledgator/gliner-qwen-0.5B-v1.0",
    "knowledgator/gliner-qwen-1.5B-v1.0",
})
GLINER_QWEN_MAX_LENGTH = int(os.getenv("GLINER_QWEN_MAX_LENGTH", "2048"))

# Chunking: Chonkie SemanticChunker + Jina embeddings
CHUNK_EMBEDDING_MODEL = os.getenv("CHUNK_EMBEDDING_MODEL", "google/embeddinggemma-300m")
CHUNK_CHAR_THRESHOLD = int(os.getenv("CHUNK_CHAR_THRESHOLD", "155"))  # Only chunk when text is longer
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "160"))
CHUNK_SIMILARITY_THRESHOLD = float(os.getenv("CHUNK_SIMILARITY_THRESHOLD", "0.7"))

# Parallel chunk processing (best on CPU). If CUDA is available, code will auto-fallback to 1.
CHUNK_MAX_WORKERS = int(os.getenv("CHUNK_MAX_WORKERS", "4"))

