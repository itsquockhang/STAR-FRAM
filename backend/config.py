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

GLINER_QWEN_MODELS = frozenset({
    "knowledgator/gliner-qwen-0.5B-v1.0",
    "knowledgator/gliner-qwen-1.5B-v1.0",
})
GLINER_QWEN_MAX_LENGTH = int(os.getenv("GLINER_QWEN_MAX_LENGTH", "2048"))

CHUNK_EMBEDDING_MODEL = os.getenv("CHUNK_EMBEDDING_MODEL", "google/embeddinggemma-300m")
CHUNK_CHAR_THRESHOLD = int(os.getenv("CHUNK_CHAR_THRESHOLD", "128"))
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "128"))
CHUNK_SIMILARITY_THRESHOLD = float(os.getenv("CHUNK_SIMILARITY_THRESHOLD", "0.7"))

CHUNK_MAX_WORKERS = int(os.getenv("CHUNK_MAX_WORKERS", "4"))

# Sentence-transformers model for persisted chunk embeddings (Saved chunks DB).
SAVED_CHUNK_EMBEDDING_MODEL = os.getenv(
    "SAVED_CHUNK_EMBEDDING_MODEL",
    "microsoft/harrier-oss-v1-270m",
)

