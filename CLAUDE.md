# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Package manager is `uv` (dependencies declared in `pyproject.toml`, locked in `uv.lock`).

```bash
# Install dependencies
uv sync

# Local dev (starts Mongo+Redis in Docker, then runs uvicorn with --reload on 127.0.0.1:8000)
./serve.sh

# Production (starts Mongo+Redis+Qdrant in Docker, runs uvicorn with multiple workers on 0.0.0.0:8000)
./run_prod.sh          # WORKERS env var controls worker count (default 4)

# Full Docker stack (app + qdrant + mongodb + redis, all containerized)
./run_docker.sh
docker compose logs -f app

# Run the app directly without the bootstrap scripts (requires Mongo/Redis already reachable)
uv run uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

There is no configured test suite, linter, or formatter in this repo (no `tests/` directory, no pytest/ruff config). ffmpeg must be installed on the host for the transcription feature to work locally (the bootstrap scripts check for it and fail fast if missing).

Model-serving helper scripts (for the external LLM/translation backends this app talks to) live in `scripts/serve_gemma4b.sh` and `scripts/serve_translategemma4b.sh` — these run the actual LLM servers this app calls over HTTP; they are not part of the app process itself.

## Environment

Configuration is via `.env` (loaded with `python-dotenv` in `main.py`). Key variables:

- `MONGO_URI`, `REDIS_HOST`/`REDIS_PORT` — datastore connections (`src/core/database.py`)
- `QDRANT_HOST`/`QDRANT_PORT`/`QDRANT_GRPC_PORT`/`QDRANT_PREFER_GRPC` — vector DB (`src/services/qdrant.py`)
- `CONDUCTOR_API_BASE` — OpenAI-compatible LLM endpoint used for all DSPy-based generation features (default `https://www-conductor.quockhang.io.vn/v1`)
- `TRANSLATE_API_BASE` — OpenAI-compatible endpoint for the TranslateGemma model (default `https://www-translate.quockhang.io.vn/v1`)
- `ADMIN_USERNAME`/`ADMIN_PASSWORD` — seeded on first boot if no admin user exists
- `SECRET_KEY` — JWT signing key for sessions (defaults to an insecure dev value — must be overridden in production)
- `HF_TOKEN`, `DEEPSEEK_API_KEY`, `NVIDIA_API_KEY`, `OPENROUTER_API_KEY` — provider keys for optional model backends

## Architecture

Starfarm is a FastAPI server-rendered (Jinja2, no SPA/JS framework) admin console for building an agricultural knowledge graph from unstructured text. There is no separate frontend build step — templates in `src/templates/` are rendered directly by FastAPI routes, styled via `src/static/style.css` per the design language in `DESIGN.md`.

**Entry point (`main.py`)**: constructs the `FastAPI` app, runs `lifespan` startup logic (init Mongo/Redis, seed the default admin user, backfill `DEFAULT_SETTINGS` onto any user missing them or running an old settings shape, pre-load the NER model), and wires up the routers from `src/routes/`. `/` (login) and `/dashboard` are defined directly in `main.py`; every other page/action lives in a router module.

**Layering**: `src/routes/*` (HTTP handlers, session/auth checks, Jinja2 `TemplateResponse` rendering) → `src/services/*` (stateless business logic: model inference, HTTP calls to external LLM servers, vector DB client) → `src/core/*` (cross-cutting: db connections, auth/session primitives, shared config/templates/utils). Routes talk to Mongo/Redis directly via `get_db()`/`get_redis()` rather than through a repository layer.

**Auth**: `src/core/auth.py` issues a JWT (HS256) on login, storing a mirror record in Redis keyed `session:{username}:{jti}` with a TTL; `get_session()` requires both a valid signature *and* a live Redis key, so `delete_session()` (logout) revokes instantly by deleting the Redis key regardless of JWT expiry. The `session_id` cookie carries the JWT. There is no framework-level auth dependency — every route handler manually reads the `session_id` cookie and calls `get_session()`, then checks `session["is_admin"]` for admin-only routes (`/settings`).

**User settings / entity schema (`src/core/config.py`, `src/routes/settings.py`)**: each user document in Mongo has a `settings` sub-document with `language` (`en`/`vi`) and `labels` (the NER entity schema: name + bilingual `desc_en`/`desc_vi`, optionally cached `queries_en`/`queries_vi` RAG queries). `DEFAULT_SETTINGS` in `config.py` is the agricultural entity schema (crop, disease, pest, pesticide, fertilizer, variety, symptom, pathogen, season, person, organization, location, date, quantity) and is what gets seeded/backfilled for users. Relationship predicates (for the knowledge graph, e.g. `cultivated_in`, `affected_by`) are stored separately in `db.predicates` (not per-user) and lazily seeded with defaults the first time any route reads an empty collection — this default-predicate list is currently duplicated inline across `settings.py` and `spaces.py` rather than shared from one place.

**NER (`src/services/ner.py`, `src/routes/ner.py`)**: wraps `GLiNER2` (fastino) as a module-level singleton (`_model`/`_model_name`), auto-selecting device via `get_device()` (CUDA > MPS > CPU) and quantizing on GPU/MPS but not CPU. `load_model()` swaps/unloads the model if a different `model_id` is requested. `extract_entities()` uses `extract_entities_long` (chunked, with spans + confidence) so it works on long documents. Two models are registered in `AVAILABLE_MODELS` (multilingual vs. English-only). A monkeypatch replaces GLiNER2's internal DataLoader with a tqdm-wrapped version purely for progress logging.

**LLM generation via DSPy (`src/routes/settings.py`)**: all "AI suggest/generate" features (label definitions, predicate definitions, RAG query enhancement, KG relation suggestions in `spaces.py`) go through `get_dspy_lm()`, which resolves a `dspy.LM` pointed at `CONDUCTOR_API_BASE` using the OpenAI-compatible `openai/<model_id>` provider prefix. `get_conductor_model()` implements a **circuit breaker**: if the Conductor server was marked offline within the last 15s, it raises `LLMConnectionError` immediately instead of waiting for an HTTP timeout; on success it also opportunistically caches the currently-served model id. `src/services/translate.py` implements the same circuit-breaker pattern independently for `TRANSLATE_API_BASE` (module-level `_translate_online`/`_translate_last_checked`/`_translate_offline_reason` globals) — the two circuit breakers are not shared/unified.

**Translation (`src/services/translate.py`)**: chunks input with Chonkie's `RecursiveChunker` (gpt2 tokenizer, 1500-token chunks) to stay under the TranslateGemma context window, then calls the OpenAI-compatible `/chat/completions` endpoint with a custom prompt format `<<<source>>>{lang}<<<target>>>{lang}<<<text>>>{chunk}`. `translate_text_stream()` streams the first `stream_limit` chunks token-by-token via SSE while translating the remaining chunks concurrently in the background with `asyncio.gather`, then flushes them in order once streaming finishes.

**Transcription (`src/services/transcribe.py`, `src/routes/transcribe.py`)**: downloads audio from a validated YouTube URL via `yt-dlp` into `src/data/audio/`, transcribes with faster-whisper/mlx-whisper depending on platform, and always deletes the temporary audio file in a `finally` block after the request completes (no persistent audio storage).

**Spaces / Knowledge Graph (`src/routes/spaces.py`)**: "Spaces" documents (`db.spaces_documents`) are saved NER extraction results (title, text, entities, labels, model) that a user can revisit to build a relationship graph on top of the previously extracted entities. Relations are stored as a `relations` array of `{subject, predicate, object}` triples embedded directly in the document (no separate edges collection). Two ways to populate relations: `auto-extract` runs GLiNER2's relation-extraction schema (`model.create_schema().relations(...)`) directly against the registered predicates; `suggest` instead prompts the Conductor LLM (via DSPy) for candidate triples as a text format (`Subject | Predicate | Object` per line) that the user must review/accept — these are two distinct extraction strategies living side by side. Only a document's author can delete it; there is no admin override for space document deletion (unlike labels/predicates, which are settings/admin-only).

**Entity highlighting (`src/core/utils.py`)**: `build_highlighted_html()` is shared between the NER page and the Spaces detail page — it takes raw text plus a `{label: [entities]}` dict, resolves overlapping spans (keeping the longest at each start position), and wraps matches in `<span>` tags colored by a fixed palette of 8 CSS classes (`NER_TAG_CLASSES`) cycled by label index.

**Extraction from URLs (`src/services/extractor.py`)**: uses `trafilatura` to fetch and extract both markdown and plain-text content plus metadata from an arbitrary URL, feeding the same downstream NER/Spaces pipeline.

**Qdrant (`src/services/qdrant.py`)**: a thin `QdrantService` wrapper (collections, upsert, vector search) — present in the codebase but not yet wired into any route; likely intended as the retrieval backend for the cached bilingual RAG queries generated in `settings.py`.
