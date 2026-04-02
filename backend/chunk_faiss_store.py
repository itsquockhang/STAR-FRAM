"""
FAISS index for saved chunk embeddings (KNN / max inner product on L2-normalized vectors ≈ cosine).

Kept in sync with SQLite: upsert when embeddings change, remove on delete or when embedding cleared.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from typing import Any, Dict, List, Tuple

import numpy as np

DB_PATH = os.getenv(
    "NER_CHUNKS_DB_PATH",
    os.path.join(os.path.dirname(__file__), "ner_chunks.sqlite3"),
)

logger = logging.getLogger(__name__)

_lock = threading.RLock()

_index: Any = None
_dim: int | None = None

FAISS_INDEX_PATH = os.getenv(
    "NER_CHUNK_FAISS_INDEX_PATH",
    os.path.join(os.path.dirname(__file__), "ner_chunks_faiss.index"),
)
FAISS_META_PATH = FAISS_INDEX_PATH + ".meta.json"


def _ensure_dir(path: str) -> None:
  d = os.path.dirname(path)
  if d and not os.path.exists(d):
    os.makedirs(d, exist_ok=True)


def _write_meta(dim: int) -> None:
  _ensure_dir(FAISS_META_PATH)
  with open(FAISS_META_PATH, "w", encoding="utf-8") as f:
    json.dump({"dim": dim}, f)


def _read_meta() -> int | None:
  if not os.path.isfile(FAISS_META_PATH):
    return None
  try:
    with open(FAISS_META_PATH, encoding="utf-8") as f:
      m = json.load(f)
    d = m.get("dim")
    return int(d) if d is not None else None
  except Exception:
    return None


def _import_faiss():
  try:
    import faiss
  except ImportError as e:
    raise RuntimeError(
      "faiss-cpu is required for chunk KNN. Install: pip install faiss-cpu",
    ) from e
  return faiss


def _new_index(dim: int):
  faiss = _import_faiss()
  base = faiss.IndexFlatIP(dim)
  return faiss.IndexIDMap2(base)


def _load_index_from_disk() -> Tuple[Any, int] | None:
  faiss = _import_faiss()
  if not os.path.isfile(FAISS_INDEX_PATH):
    return None
  dim = _read_meta()
  if dim is None:
    return None
  try:
    idx = faiss.read_index(FAISS_INDEX_PATH)
    return idx, dim
  except Exception as e:
    logger.warning("Failed to load FAISS index: %s", e)
    return None


def _save_index_to_disk(idx: Any, dim: int) -> None:
  faiss = _import_faiss()
  _ensure_dir(FAISS_INDEX_PATH)
  faiss.write_index(idx, FAISS_INDEX_PATH)
  _write_meta(dim)


def rebuild_from_sqlite() -> Dict[str, Any]:
  """Rebuild the FAISS index from all rows in chunks with non-null embedding_json."""
  global _index, _dim
  faiss = _import_faiss()
  with _lock:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
      cur = conn.cursor()
      cur.execute(
        """
        SELECT id, embedding_json, embedding_dim
        FROM chunks
        WHERE embedding_json IS NOT NULL AND TRIM(embedding_json) != ''
        ORDER BY id
        """
      )
      rows = cur.fetchall()
    finally:
      conn.close()

    if not rows:
      _index = None
      _dim = None
      if os.path.isfile(FAISS_INDEX_PATH):
        try:
          os.remove(FAISS_INDEX_PATH)
        except OSError:
          pass
      if os.path.isfile(FAISS_META_PATH):
        try:
          os.remove(FAISS_META_PATH)
        except OSError:
          pass
      return {"ok": True, "vectors": 0, "dim": None}

    first = json.loads(rows[0]["embedding_json"])
    dim = len(first) if isinstance(first, list) else int(rows[0]["embedding_dim"] or 0)
    if dim <= 0:
      return {"ok": False, "error": "Could not infer embedding dimension"}

    index = _new_index(dim)
    for r in rows:
      raw = r["embedding_json"]
      cid = int(r["id"])
      try:
        vec = json.loads(raw)
        if not isinstance(vec, list) or len(vec) != dim:
          logger.warning("Skip chunk %s: bad embedding length", cid)
          continue
      except Exception:
        continue
      x = np.array([vec], dtype=np.float32)
      faiss.normalize_L2(x)
      index.add_with_ids(x, np.array([cid], dtype=np.int64))

    _index = index
    _dim = dim
    _save_index_to_disk(index, dim)
    return {"ok": True, "vectors": index.ntotal, "dim": dim}


def ensure_loaded() -> None:
  global _index, _dim
  with _lock:
    if _index is not None:
      return
    loaded = _load_index_from_disk()
    if loaded is not None:
      _index, _dim = loaded
      return
    rebuild_from_sqlite()


def sync_chunk(chunk_id: int) -> None:
  """Upsert or remove this chunk's vector from FAISS based on current SQLite row."""
  global _index, _dim
  faiss = _import_faiss()
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  try:
    cur = conn.cursor()
    cur.execute(
      "SELECT embedding_json, embedding_dim FROM chunks WHERE id = ?",
      (chunk_id,),
    )
    row = cur.fetchone()
  finally:
    conn.close()

  if row is None:
    remove_chunk_id(chunk_id)
    return

  raw = row["embedding_json"]
  if raw is None or not str(raw).strip():
    remove_chunk_id(chunk_id)
    return

  try:
    vec = json.loads(raw)
  except Exception:
    remove_chunk_id(chunk_id)
    return

  if not isinstance(vec, list) or not vec:
    remove_chunk_id(chunk_id)
    return

  dim = len(vec)
  x = np.array([vec], dtype=np.float32)
  faiss.normalize_L2(x)

  with _lock:
    ensure_loaded_unsafe()
    if _index is None:
      _index = _new_index(dim)
      _dim = dim
    elif _dim != dim:
      logger.warning(
        "Embedding dim mismatch (index %s vs chunk %s); rebuilding FAISS from DB",
        _dim,
        dim,
      )
      rebuild_from_sqlite()
      return

    try:
      _index.remove_ids(np.array([chunk_id], dtype=np.int64))
    except Exception:
      pass
    _index.add_with_ids(x, np.array([chunk_id], dtype=np.int64))
    _save_index_to_disk(_index, _dim or dim)


def ensure_loaded_unsafe() -> None:
  """Must be called with _lock held."""
  global _index, _dim
  if _index is not None:
    return
  loaded = _load_index_from_disk()
  if loaded is not None:
    _index, _dim = loaded
    return
  # empty — created on first add in sync_chunk
  _index = None
  _dim = None


def remove_chunk_id(chunk_id: int) -> None:
  """Remove id from FAISS (e.g. after SQLite row deleted). Safe if index missing or id absent."""
  global _index, _dim
  with _lock:
    if _index is None:
      loaded = _load_index_from_disk()
      if loaded is None:
        return
      _index, _dim = loaded
    try:
      _index.remove_ids(np.array([chunk_id], dtype=np.int64))
      md = _dim if _dim is not None else _read_meta()
      if md is not None:
        _save_index_to_disk(_index, md)
    except Exception as e:
      logger.debug("FAISS remove_ids %s: %s", chunk_id, e)


def search_knn_by_text(query: str, k: int = 10) -> Tuple[Dict[str, Any], int]:
  """Embed query and return top-k chunk ids with inner product scores (cosine for normalized vectors)."""
  from chunk_embedding import embed_text

  q = embed_text(query)
  if not q:
    return {"error": "Empty query or embedding failed"}, 400
  return search_knn_by_vector(q, k)


def search_knn_by_vector(vec: List[float], k: int) -> Tuple[Dict[str, Any], int]:
  faiss = _import_faiss()
  ensure_loaded()
  with _lock:
    if _index is None or _index.ntotal == 0:
      return {"results": [], "dim": _dim}, 200
    dim = _dim
    if dim is None or len(vec) != dim:
      return {"error": f"Query dim {len(vec)} != index dim {dim}"}, 400

    xq = np.array([vec], dtype=np.float32)
    faiss.normalize_L2(xq)
    kk = min(int(k), int(_index.ntotal))
    if kk <= 0:
      return {"results": [], "dim": dim}, 200
    distances, labels = _index.search(xq, kk)
    results: List[Dict[str, Any]] = []
    for i in range(kk):
      cid = int(labels[0][i])
      if cid == -1:
        continue
      score = float(distances[0][i])
      results.append({"chunk_id": cid, "score": score})

  return {"results": results, "dim": dim}, 200
