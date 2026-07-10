import os
import logging
import torch
import yt_dlp

logger = logging.getLogger("starfarm.transcribe")

MLX_MODEL_MAPPING = {
    "tiny": "mlx-community/whisper-tiny",
    "base": "mlx-community/whisper-base",
    "small": "mlx-community/whisper-small",
    "medium": "mlx-community/whisper-medium",
    "large-v3": "mlx-community/whisper-large-v3",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo"
}


def get_available_devices() -> list[str]:
    """
    Returns the list of available execution devices on the current host.
    Ordered by priority (best accelerator first).
    """
    devices = []
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        devices.append("mps")
    if torch.cuda.is_available():
        devices.append("cuda")
    devices.append("cpu")
    return devices


def download_audio_from_youtube(url: str, output_dir: str) -> tuple[str, str]:
    """
    Download audio from a YouTube URL and convert it to .m4a format.
    Returns: (audio_file_path, video_title)
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # We want a unique template to prevent collisions
    out_template = os.path.join(output_dir, "%(id)s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': out_template,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
            'preferredquality': '192',
        }],
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android', 'ios']
            }
        }
    }
    
    logger.info(f"Downloading audio from YouTube URL: {url}")
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info["id"]
        video_title = info.get("title", "YouTube Video")
        
        # After conversion, the file will be .m4a
        audio_path = os.path.join(output_dir, f"{video_id}.m4a")
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Expected audio file not found at {audio_path}")
            
        logger.info(f"Audio downloaded successfully: {audio_path} (Title: {video_title})")
        return audio_path, video_title


def transcribe_audio(audio_path: str, model_size: str, device: str) -> dict:
    """
    Transcribe the audio file using either mlx_whisper (for Apple Silicon MPS) or standard openai-whisper.
    Returns the transcription result dictionary (containing 'text' and optionally segments).
    """
    logger.info(f"Starting transcription on device '{device}' using model size '{model_size}' for: {audio_path}")
    
    if device == "mps":
        try:
            import mlx_whisper
            repo_name = MLX_MODEL_MAPPING.get(model_size, f"mlx-community/whisper-{model_size}")
            logger.info(f"Using Apple MLX-Whisper with model repository: {repo_name}")
            result = mlx_whisper.transcribe(
                audio_path,
                path_or_hf_repo=repo_name,
                verbose=False
            )
            return result
        except ImportError:
            logger.warning("mlx_whisper is not installed. Falling back to faster-whisper on CPU.")
            device = "cpu"
            
    # Fallback to faster-whisper (for CPU, CUDA, or if mlx-whisper is missing on MPS)
    from faster_whisper import WhisperModel
    
    # Select optimal compute type
    if device == "cuda":
        compute_type = "float16"
    else:
        compute_type = "int8"  # int8 is extremely fast on CPU
        
    logger.info(f"Using faster-whisper with device: {device} (compute_type: {compute_type})")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    segments, info = model.transcribe(audio_path, beam_size=5)
    
    # Reconstruct text by joining segments
    text = "".join([segment.text for segment in segments])
    return {"text": text}
