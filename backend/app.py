import os

from flask import Flask, jsonify, request
from flask_cors import CORS

from config import DEFAULT_MODEL, SUPPORTED_MODELS
from document_service import extract_text_from_upload
from pdf_service import extract_text_from_pdf
from llm_agri_service import extract_agri_relations
from ner_service import clear_label_cache, handle_ner
from translation_service import handle_translate
from web_service import extract_web_text
from whisperx_service import transcribe_youtube_with_whisperx
from youtube_service import fetch_transcript
from chunk_db import (
    add_entity,
    delete_chunk,
    delete_entity,
    get_chunk_detail,
    init_db,
    list_chunks,
    save_chunks_with_entities,
    update_chunk,
    update_entity,
)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

# Ensure SQLite DB/tables exist for chunk storage.
init_db()


@app.get("/health")
def health():
    return jsonify({"ok": True})


@app.get("/api/models")
def models():
    return jsonify({"default": DEFAULT_MODEL, "supported": SUPPORTED_MODELS})


@app.post("/api/cache/clear")
def clear_cache():
    clear_label_cache()
    return jsonify({"ok": True})


@app.post("/api/ner")
def ner():
    payload = request.get_json(silent=True) or {}
    body, status = handle_ner(payload)
    return jsonify(body), status


@app.post("/api/ner/chunks/save")
def ner_chunks_save():
    payload = request.get_json(silent=True) or {}
    body, status = save_chunks_with_entities(payload)
    return jsonify(body), status


@app.get("/api/ner/chunks")
def ner_chunks_list():
    body, status = list_chunks()
    return jsonify(body), status


@app.get("/api/ner/chunks/<int:chunk_id>")
def ner_chunk_detail(chunk_id: int):
    body, status = get_chunk_detail(chunk_id)
    return jsonify(body), status


@app.patch("/api/ner/chunks/<int:chunk_id>")
def ner_chunk_update(chunk_id: int):
    payload = request.get_json(silent=True) or {}
    body, status = update_chunk(chunk_id, payload)
    return jsonify(body), status


@app.delete("/api/ner/chunks/<int:chunk_id>")
def ner_chunk_delete(chunk_id: int):
    body, status = delete_chunk(chunk_id)
    return jsonify(body), status


@app.post("/api/ner/chunks/<int:chunk_id>/entities")
def ner_chunk_add_entity(chunk_id: int):
    payload = request.get_json(silent=True) or {}
    body, status = add_entity(chunk_id, payload)
    return jsonify(body), status


@app.patch("/api/ner/entities/<int:entity_id>")
def ner_entity_update(entity_id: int):
    payload = request.get_json(silent=True) or {}
    body, status = update_entity(entity_id, payload)
    return jsonify(body), status


@app.delete("/api/ner/entities/<int:entity_id>")
def ner_entity_delete(entity_id: int):
    body, status = delete_entity(entity_id)
    return jsonify(body), status


@app.post("/api/translate")
def translate():
    payload = request.get_json(silent=True) or {}
    body, status = handle_translate(payload)
    return jsonify(body), status


@app.post("/api/youtube/transcript")
def youtube_transcript():
    payload = request.get_json(silent=True) or {}
    url_or_id = str(payload.get("url") or payload.get("video_id") or "").strip()
    languages = payload.get("languages")
    if not url_or_id:
        return jsonify({"error": "Missing 'url' or 'video_id'"}), 400
    body, status = fetch_transcript(url_or_id, languages=languages)
    return jsonify(body), status


@app.post("/api/doc/extract")
def doc_extract():
    if "file" not in request.files:
        return jsonify({"error": "Missing file upload field 'file'"}), 400

    f = request.files["file"]
    filename = f.filename or ""
    data = f.read() or b""
    body, status = extract_text_from_upload(filename, data)
    return jsonify(body), status


@app.post("/api/pdf/extract")
def pdf_extract():
    if "file" not in request.files:
        return jsonify({"error": "Missing file upload field 'file'"}), 400

    f = request.files["file"]
    filename = f.filename or ""
    data = f.read() or b""
    if not filename.lower().endswith(".pdf"):
        return jsonify({"error": "File must be a PDF (.pdf)"}), 400
    body, status = extract_text_from_pdf(data, filename)
    return jsonify(body), status


@app.post("/api/web/extract")
def web_extract():
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url") or "").strip()
    body, status = extract_web_text(url)
    return jsonify(body), status


@app.post("/api/llm/agri-relations")
def llm_agri_relations():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text") or "")
    body, status = extract_agri_relations(text)
    return jsonify(body), status


@app.post("/api/youtube/whisperx")
def youtube_whisperx():
    payload = request.get_json(silent=True) or {}
    url = str(payload.get("url") or "").strip()
    language = payload.get("language")
    model_name = payload.get("model")
    body, status = transcribe_youtube_with_whisperx(url, language=language, model_name=model_name)
    return jsonify(body), status


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
