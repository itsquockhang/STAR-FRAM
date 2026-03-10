import os

from flask import Flask, jsonify, request
from flask_cors import CORS

from config import DEFAULT_MODEL, SUPPORTED_MODELS
from ner_service import clear_label_cache, handle_ner
from youtube_service import fetch_transcript

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})


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


@app.post("/api/youtube/transcript")
def youtube_transcript():
    payload = request.get_json(silent=True) or {}
    url_or_id = str(payload.get("url") or payload.get("video_id") or "").strip()
    languages = payload.get("languages")
    if not url_or_id:
        return jsonify({"error": "Missing 'url' or 'video_id'"}), 400
    body, status = fetch_transcript(url_or_id, languages=languages)
    return jsonify(body), status


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
