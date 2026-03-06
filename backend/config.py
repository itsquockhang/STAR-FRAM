import os

DEFAULT_MODEL = os.getenv("GLINER_MODEL", "knowledgator/gliner-bi-base-v2.0")
SUPPORTED_MODELS = [
    "knowledgator/gliner-bi-base-v2.0",
    "urchade/gliner_multi-v2.1",
]

# Chunking: Chonkie SemanticChunker + Jina embeddings
CHUNK_EMBEDDING_MODEL = os.getenv("CHUNK_EMBEDDING_MODEL", "jinaai/jina-embeddings-v5-text-nano")
CHUNK_CHAR_THRESHOLD = int(os.getenv("CHUNK_CHAR_THRESHOLD", "1500"))  # Only chunk when text is longer
CHUNK_SIZE_TOKENS = int(os.getenv("CHUNK_SIZE_TOKENS", "512"))
CHUNK_SIMILARITY_THRESHOLD = float(os.getenv("CHUNK_SIMILARITY_THRESHOLD", "0.7"))

