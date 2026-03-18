from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterable, List, Tuple

DB_PATH = os.getenv(
    "NER_CHUNKS_DB_PATH",
    os.path.join(os.path.dirname(__file__), "ner_chunks.sqlite3"),
)


def _utc_now() -> str:
  return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _ensure_dir(path: str) -> None:
  directory = os.path.dirname(path)
  if directory and not os.path.exists(directory):
    os.makedirs(directory, exist_ok=True)


def _normalize_classification_tags(value: Any) -> List[str]:
  raw_items: List[Any] = []
  if isinstance(value, list):
    raw_items = value
  elif isinstance(value, str):
    v = value.strip()
    if not v:
      return []
    try:
      parsed = json.loads(v)
      if isinstance(parsed, list):
        raw_items = parsed
      else:
        raw_items = [s.strip() for s in v.split(",")]
    except Exception:
      raw_items = [s.strip() for s in v.split(",")]

  out: List[str] = []
  seen: set[str] = set()
  for item in raw_items:
    tag = str(item or "").strip()
    if not tag or tag in seen:
      continue
    seen.add(tag)
    out.append(tag)
  return out


def _serialize_classification_tags(tags: Iterable[str]) -> str:
  return json.dumps(list(tags), ensure_ascii=False)


def _normalize_rating(value: Any) -> str | None:
  if value is None:
    return None
  rating = str(value).strip()
  return rating or None


@contextmanager
def get_conn():
  _ensure_dir(DB_PATH)
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  try:
    yield conn
    conn.commit()
  finally:
    conn.close()


def init_db() -> None:
  with get_conn() as conn:
    cur = conn.cursor()
    cur.execute(
      """
      CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doc_title TEXT,
        model TEXT,
        text_used TEXT,
        chunk_index INTEGER,
        start INTEGER,
        end INTEGER,
        original_text TEXT,
        corrected_text TEXT,
        is_starred INTEGER DEFAULT 0,
        status TEXT DEFAULT 'new',
        classification_tags TEXT DEFAULT '[]',
        rating TEXT,
        created_at TEXT,
        updated_at TEXT
      )
      """
    )
    cur.execute(
      """
      CREATE TABLE IF NOT EXISTS entities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chunk_id INTEGER NOT NULL,
        label TEXT,
        text TEXT,
        score REAL,
        start INTEGER,
        end INTEGER,
        FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
      )
      """
    )

    # Lightweight migration for existing databases.
    cur.execute("PRAGMA table_info(chunks)")
    existing_cols = {str(r["name"]) for r in cur.fetchall()}
    if "classification_tags" not in existing_cols:
      cur.execute("ALTER TABLE chunks ADD COLUMN classification_tags TEXT DEFAULT '[]'")
    if "rating" not in existing_cols:
      cur.execute("ALTER TABLE chunks ADD COLUMN rating TEXT")


def save_chunks_with_entities(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
  text_used = str(payload.get("text_used") or "")
  if not text_used:
    return {"error": "Missing 'text_used'"}, 400

  raw_chunks = payload.get("chunks") or []
  entities = payload.get("entities") or []

  if not isinstance(raw_chunks, list) or not raw_chunks:
    return {"error": "Missing 'chunks' (non-empty array)"}, 400

  model = payload.get("model")
  labels = payload.get("labels") or []
  if isinstance(labels, list):
    labels_str = ",".join(str(l) for l in labels)
  else:
    labels_str = str(labels)

  doc_title = payload.get("doc_title") or None
  default_classification_tags = _normalize_classification_tags(payload.get("classification_tags"))
  default_rating = _normalize_rating(payload.get("rating"))
  now = _utc_now()

  # Pre-normalize entities
  norm_entities: List[Dict[str, Any]] = []
  if isinstance(entities, list):
    for e in entities:
      if not isinstance(e, dict):
        continue
      norm_entities.append(
        {
          "text": str(e.get("text") or ""),
          "label": str(e.get("label") or ""),
          "score": float(e["score"]) if isinstance(e.get("score"), (int, float)) else None,
          "start": int(e["start"]) if isinstance(e.get("start"), (int, float)) else None,
          "end": int(e["end"]) if isinstance(e.get("end"), (int, float)) else None,
        }
      )

  created_ids: List[int] = []

  with get_conn() as conn:
    cur = conn.cursor()

    for c in raw_chunks:
      if not isinstance(c, dict):
        continue
      start = int(c.get("start") or 0)
      end = int(c.get("end") or start)
      chunk_index = int(c.get("index") or 0)
      original_text = c.get("original_text")
      corrected_text = c.get("corrected_text") or text_used[start:end]
      classification_tags = _normalize_classification_tags(
        c.get("classification_tags", default_classification_tags)
      )
      rating = _normalize_rating(c.get("rating", default_rating))

      cur.execute(
        """
        INSERT INTO chunks (
          doc_title, model, text_used, chunk_index,
          start, end, original_text, corrected_text,
          is_starred, status, classification_tags, rating, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 'new', ?, ?, ?, ?)
        """,
        (
          doc_title,
          model,
          text_used,
          chunk_index,
          start,
          end,
          original_text,
          corrected_text,
          _serialize_classification_tags(classification_tags),
          rating,
          now,
          now,
        ),
      )
      chunk_id = int(cur.lastrowid)
      created_ids.append(chunk_id)

      # Attach entities that fall inside this chunk span
      for e in norm_entities:
        es = e.get("start")
        ee = e.get("end")
        if es is None or ee is None:
          continue
        if es >= start and ee <= end:
          cur.execute(
            """
            INSERT INTO entities (
              chunk_id, label, text, score, start, end
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
              chunk_id,
              e["label"],
              e["text"],
              e["score"],
              es - start,
              ee - start,
            ),
          )

  return {"chunk_ids": created_ids}, 200


def list_chunks() -> Tuple[Dict[str, Any], int]:
  with get_conn() as conn:
    cur = conn.cursor()
    cur.execute(
      """
      SELECT
        id,
        doc_title,
        model,
        chunk_index,
        start,
        end,
        corrected_text,
        is_starred,
        status,
        classification_tags,
        rating,
        created_at,
        updated_at
      FROM chunks
      ORDER BY created_at DESC, id DESC
      """
    )
    rows = [dict(r) for r in cur.fetchall()]

  for row in rows:
    row["classification_tags"] = _normalize_classification_tags(row.get("classification_tags"))
    row["rating"] = _normalize_rating(row.get("rating"))
  return {"items": rows}, 200


def get_chunk_detail(chunk_id: int) -> Tuple[Dict[str, Any], int]:
  with get_conn() as conn:
    cur = conn.cursor()
    cur.execute("SELECT * FROM chunks WHERE id = ?", (chunk_id,))
    row = cur.fetchone()
    if row is None:
      return {"error": "Chunk not found"}, 404
    chunk = dict(row)
    chunk["classification_tags"] = _normalize_classification_tags(chunk.get("classification_tags"))
    chunk["rating"] = _normalize_rating(chunk.get("rating"))

    cur.execute(
      """
      SELECT id, label, text, score, start, end
      FROM entities
      WHERE chunk_id = ?
      ORDER BY start, end, id
      """,
      (chunk_id,),
    )
    ents = [dict(r) for r in cur.fetchall()]

  chunk["entities"] = ents
  return chunk, 200


def update_chunk(chunk_id: int, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
  allowed_fields = {
    "doc_title",
    "corrected_text",
    "is_starred",
    "status",
    "classification_tags",
    "rating",
  }
  sets: List[str] = []
  params: List[Any] = []

  for key, value in data.items():
    if key not in allowed_fields:
      continue
    sets.append(f"{key} = ?")
    if key == "is_starred":
      params.append(1 if bool(value) else 0)
    elif key == "classification_tags":
      params.append(_serialize_classification_tags(_normalize_classification_tags(value)))
    elif key == "rating":
      params.append(_normalize_rating(value))
    else:
      params.append(value)

  if not sets:
    return {"error": "No updatable fields provided"}, 400

  sets.append("updated_at = ?")
  params.append(_utc_now())
  params.append(chunk_id)

  with get_conn() as conn:
    cur = conn.cursor()
    cur.execute(f"UPDATE chunks SET {', '.join(sets)} WHERE id = ?", params)
    if cur.rowcount == 0:
      return {"error": "Chunk not found"}, 404

  return get_chunk_detail(chunk_id)


def delete_chunk(chunk_id: int) -> Tuple[Dict[str, Any], int]:
  with get_conn() as conn:
    cur = conn.cursor()
    cur.execute("DELETE FROM chunks WHERE id = ?", (chunk_id,))
    if cur.rowcount == 0:
      return {"error": "Chunk not found"}, 404
  return {"ok": True}, 200


def add_entity(chunk_id: int, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
  label = str(data.get("label") or "").strip()
  text = str(data.get("text") or "").strip()
  if not label or not text:
    return {"error": "Missing 'label' or 'text'"}, 400

  score = data.get("score")
  start = data.get("start")
  end = data.get("end")

  with get_conn() as conn:
    cur = conn.cursor()
    cur.execute("SELECT id FROM chunks WHERE id = ?", (chunk_id,))
    if cur.fetchone() is None:
      return {"error": "Chunk not found"}, 404

    cur.execute(
      """
      INSERT INTO entities (chunk_id, label, text, score, start, end)
      VALUES (?, ?, ?, ?, ?, ?)
      """,
      (
        chunk_id,
        label,
        text,
        float(score) if isinstance(score, (int, float)) else None,
        int(start) if isinstance(start, (int, float)) else None,
        int(end) if isinstance(end, (int, float)) else None,
      ),
    )
    ent_id = int(cur.lastrowid)

  return {"id": ent_id}, 200


def update_entity(entity_id: int, data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
  allowed_fields = {"label", "text", "score", "start", "end"}
  sets: List[str] = []
  params: List[Any] = []

  for key, value in data.items():
    if key not in allowed_fields:
      continue
    sets.append(f"{key} = ?")
    if key in ("start", "end") and isinstance(value, (int, float)):
      params.append(int(value))
    elif key == "score" and isinstance(value, (int, float)):
      params.append(float(value))
    else:
      params.append(value)

  if not sets:
    return {"error": "No updatable fields provided"}, 400

  params.append(entity_id)

  with get_conn() as conn:
    cur = conn.cursor()
    cur.execute(f"UPDATE entities SET {', '.join(sets)} WHERE id = ?", params)
    if cur.rowcount == 0:
      return {"error": "Entity not found"}, 404

  return {"ok": True}, 200


def delete_entity(entity_id: int) -> Tuple[Dict[str, Any], int]:
  with get_conn() as conn:
    cur = conn.cursor()
    cur.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
    if cur.rowcount == 0:
      return {"error": "Entity not found"}, 404
  return {"ok": True}, 200

