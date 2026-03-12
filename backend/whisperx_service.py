from __future__ import annotations

import os
import shutil
import tempfile
import time
from typing import Any, Dict, Tuple
from urllib.parse import parse_qs, urlparse

import torch
import whisperx
from yt_dlp import YoutubeDL

# TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD=true
os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "true"


def _extract_video_id_from_url(url: str) -> str:
    """
    Best-effort extraction of YouTube video id from URL (for logging/filenames only).
    """
    try:
        parsed = urlparse(url)
        if parsed.hostname in ("youtu.be", "www.youtu.be"):
            vid = (parsed.path or "").lstrip("/")
            if vid:
                return vid
        if parsed.query:
            q = parse_qs(parsed.query)
            v = q.get("v")
            if v and v[0]:
                return v[0]
    except Exception:
        pass
    return ""


def _download_audio_to_temp(url: str) -> Tuple[str, str]:
    """
    Download YouTube audio stream to a temporary file using yt-dlp.
    Returns (local file path, video_id_if_available).
    """
    tmp_dir = tempfile.mkdtemp(prefix="yt-audio-")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmp_dir, "%(id)s.%(ext)s"),
        "quiet": True,
        "noprogress": True,
    }

    # yt-dlp now requires an external JS runtime for some YouTube clients.
    # Auto-detect common runtimes and pass them explicitly.
    js_runtime_bins = {
        "deno": ("deno",),
        "node": ("node", "nodejs"),
        "quickjs": ("qjs", "quickjs"),
        "bun": ("bun",),
    }
    js_runtimes: Dict[str, Dict[str, str]] = {}
    for runtime, bins in js_runtime_bins.items():
        for bin_name in bins:
            path = shutil.which(bin_name)
            if path:
                js_runtimes[runtime] = {"path": path}
                break
    if js_runtimes:
        ydl_opts["js_runtimes"] = js_runtimes

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)
    vid = str(info.get("id") or "").strip()
    if not vid:
        vid = _extract_video_id_from_url(url)
    return filepath, vid


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

    if torch.cuda.is_available():
        device = "cuda"
    elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        # Apple Silicon (Metal Performance Shaders)
        device = "mps"
    else:
        device = "cpu"

    # Only used for WhisperX (CUDA/CPU). MLX handles precision internally on MPS.
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
        audio_path, video_id = _download_audio_to_temp(url)
        print(f"Audio path: {audio_path}")
    except Exception as e:
        return {"error": f"Failed to download audio: {e!s}"}, 502

    try:
        if device == "mps":
            # Use mlx_whisper on Apple Silicon (Metal / MLX backend)
            # Import lazily so non-Apple environments do not require MLX shared libs.
            import mlx_whisper

            mlx_result = mlx_whisper.transcribe(
                audio_path,
                path_or_hf_repo="mlx-community/whisper-medium-mlx-8bit",
                word_timestamps=True,
                verbose=True,
            )
            result: Dict[str, Any] = {
                "segments": mlx_result.get("segments") or [],
                "language": mlx_result.get("language"),
            }
        else:
            # Fallback to WhisperX (CUDA / CPU)
            model = whisperx.load_model(model_id, device, compute_type=compute_type)
            audio = whisperx.load_audio(audio_path)
            result = model.transcribe(
                audio,
                batch_size=16,
                language=language,
                verbose=True,
            )
    except Exception as e:
        return {"error": f"WhisperX/MLX transcription failed: {e!s}"}, 500
    finally:
        # Try to free GPU/CPU memory for WhisperX path
        if "model" in locals():
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
        "video_id": video_id or None,
    }
    return out, 200

