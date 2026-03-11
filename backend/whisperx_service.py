from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, Tuple

import torch
import whisperx
from yt_dlp import YoutubeDL
import time

# TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=true
os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "true"

def _download_audio_to_temp(url: str) -> str:
    """
    Download YouTube audio stream to a temporary .m4a file using yt-dlp.
    Returns the local file path.
    """
    tmp_dir = tempfile.mkdtemp(prefix="yt-audio-")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmp_dir, "%(id)s.%(ext)s"),
        "quiet": True,
        "noprogress": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)
    return filepath


def transcribe_youtube_with_whisperx(
    url: str,
    language: str | None = None,
    model_name: str | None = None,
) -> Tuple[Dict[str, Any], int]:
    """
    Fallback transcription using WhisperX when YouTube does not provide captions.

    - Downloads audio with yt-dlp
    - Runs WhisperX large-v2
    - Returns plain text transcript and basic metadata
    """
    url = (url or "").strip()
    if not url:
        return {"error": "Missing 'url'"}, 400

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    # Allow only a known set of WhisperX models, default to "tiny"
    allowed_models = {
        "tiny",
        "tiny.en",
        "base",
        "base.en",
        "small",
        "small.en",
        "medium",
        "medium.en",
        "large-v1",
        "large-v2",
        "large-v3",
        "large",
        "distil-large-v2",
        "distil-medium.en",
        "distil-small.en",
        "distil-large-v3",
        "distil-large-v3.5",
        "large-v3-turbo",
        "turbo",
    }
    model_id = (model_name or "").strip().lower() or "tiny"
    if model_id not in allowed_models:
        model_id = "tiny"

    started_at = time.time()

    try:
        audio_path = _download_audio_to_temp(url)
        print(f"Audio path: {audio_path}")
    except Exception as e:
        return {"error": f"Failed to download audio: {e!s}"}, 502

    try:
        model = whisperx.load_model(model_id, device, compute_type=compute_type)
        audio = whisperx.load_audio(audio_path)
        result = model.transcribe(
            audio,
            batch_size=16,
            language=language,
        )
    except Exception as e:
        return {"error": f"WhisperX transcription failed: {e!s}"}, 500
    finally:
        # Try to free GPU/CPU memory
        try:
            del model  # type: ignore[name-defined]
        except Exception:
            pass
        try:
            import gc

            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    elapsed = time.time() - started_at

    segments = result.get("segments") or []
    if not segments:
        return {"error": "WhisperX produced no segments."}, 500

    # Concatenate segment texts into a single transcript
    text_parts = [str(s.get("text") or "").strip() for s in segments]
    text = "\n".join(t for t in text_parts if t).strip()

    if not text:
        return {"error": "WhisperX produced empty transcript."}, 500

    out = {
        "text": text,
        "language": result.get("language"),
        "segment_count": len(segments),
        "source": "whisperx",
        "elapsed_seconds": elapsed,
        "model": model_id,
    }
    return out, 200

