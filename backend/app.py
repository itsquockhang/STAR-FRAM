import os

from flask import Flask, jsonify, request
from flask_cors import CORS

from config import DEFAULT_MODEL, SUPPORTED_MODELS
from ner_service import clear_label_cache, handle_ner

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


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
