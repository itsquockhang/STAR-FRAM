## STARFRAM Backend (Flask + GLiNER)

### Install dependencies with `uv`

```bash
cd backend
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### Run server

```bash
python app.py
```

Backend runs at `http://127.0.0.1:8000`.

### API

- `GET /health`
- `GET /api/models`
- `POST /api/ner`

Example request body:

```json
{
  "model": "knowledgator/gliner-bi-base-v2.0",
  "text": "Cristiano Ronaldo ...",
  "labels": ["person", "award", "date", "competitions", "teams"],
  "threshold": 0.05,
  "use_cache": true,
  "use_chunking": true,
  "chunk_char_threshold": 1500
}
```

Notes:
- `use_cache: true` provides a speedup for bi-encoder models (those that implement `encode_labels`).
- For `urchade/gliner_multi-v2.1` (uni-encoder), the backend automatically falls back to `predict_entities`.
- **Chunking**: When `use_chunking: true` and text length > `chunk_char_threshold` (default: 1500 chars), the backend uses [Chonkie Semantic Chunker](https://docs.chonkie.ai/oss/chunkers/semantic-chunker) with embeddings from [jinaai/jina-embeddings-v5-text-nano](https://huggingface.co/jinaai/jina-embeddings-v5-text-nano) to split long text into semantic chunks, runs NER per chunk, then merges entities back into original offsets. Configurable via env: `CHUNK_EMBEDDING_MODEL`, `CHUNK_CHAR_THRESHOLD`, `CHUNK_SIZE_TOKENS`, `CHUNK_SIMILARITY_THRESHOLD`.

Response:

```json
{
  "model": "knowledgator/gliner-bi-base-v2.0",
  "entities": [],
  "cached_labels": false,
  "took_ms": 1234,
  "chunks_used": 3
}
```

`chunks_used` is only present when chunking is used.

