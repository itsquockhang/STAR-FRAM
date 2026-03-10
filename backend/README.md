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
- `POST /api/youtube/transcript`

Example request body:

```json
{
  "model": "knowledgator/gliner-bi-base-v2.0",
  "text": "Cristiano Ronaldo ...",
  "labels": ["person", "award", "date", "competitions", "teams"],
  "threshold": 0.05,
  "use_cache": true,
  "use_chunking": true,
  "chunking_strategy": "token",
  "use_spell_correction": false,
  "spell_correction_max_tokens": 160,
  "chunk_max_workers": 4,
  "chunk_char_threshold": 1500
}
```

Notes:
- `use_cache: true` provides a speedup for bi-encoder models (those that implement `encode_labels`).
- For `urchade/gliner_multi-v2.1` (uni-encoder), the backend automatically falls back to `predict_entities`.
- **Chunking**: When `use_chunking: true` and text length > `chunk_char_threshold`, the backend splits text into chunks, runs NER per chunk, then merges entities back into the returned `text_used` offsets.
  - **Strategies** (`chunking_strategy`):
    - `semantic`: [Chonkie SemanticChunker](https://docs.chonkie.ai/oss/chunkers/semantic-chunker)
    - `token`: [Chonkie TokenChunker](https://docs.chonkie.ai/oss/chunkers/token-chunker)
    - `sentence`: Vietnamese sentence splitting via `underthesea.sent_tokenize`
  - **Config** (env):
    - `CHUNK_EMBEDDING_MODEL`, `CHUNK_SIMILARITY_THRESHOLD` (semantic only)
    - `CHUNK_CHAR_THRESHOLD`, `CHUNK_SIZE_TOKENS`
    - `CHUNK_MAX_WORKERS` (parallel chunk processing; auto-falls back to 1 worker when CUDA is available)
- **Spelling correction (optional)**: When `use_spell_correction: true`, each chunk is normalized with `underthesea.text_normalize()` then corrected with `protonx-models/protonx-legal-tc`. NER is executed on corrected text. Use `spell_correction_max_tokens` to control truncation / generation length.

Response:

```json
{
  "model": "knowledgator/gliner-bi-base-v2.0",
  "text_used": "....",
  "entities": [],
  "cached_labels": false,
  "took_ms": 1234,
  "chunks_used": 3,
  "chunking_strategy": "token",
  "use_spell_correction": false,
  "chunks": [
    {
      "index": 0,
      "start": 0,
      "end": 120,
      "original_text": "...",
      "corrected_text": "..."
    }
  ]
}
```

`chunks_used` and `chunks` are only present when chunking is used.

### YouTube Transcript API

`POST /api/youtube/transcript`

Request body:

```json
{
  "url": "https://www.youtube.com/watch?v=RcX_GuQnB6s",
  "languages": ["vi", "en"]
}
```

Response (success):

```json
{
  "text": "...",
  "video_id": "RcX_GuQnB6s",
  "language": "vi",
  "snippet_count": 123
}
```

If transcript is unavailable/disabled, the endpoint returns a 404 with a clear `error` message.

