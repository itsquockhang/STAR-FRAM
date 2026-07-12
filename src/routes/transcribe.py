import os
import re
import time
import logging
from fastapi import APIRouter, Form, Cookie, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from src.core.auth import get_session
from src.services.transcribe import get_available_devices, download_audio_from_youtube, transcribe_audio
from src.core.templates import templates

logger = logging.getLogger("starfarm.routes.transcribe")

router = APIRouter()

@router.get("/transcribe", response_class=HTMLResponse)
async def transcribe_page(
    request: Request,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=303)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(key="session_id")
        return response

    devices = get_available_devices()

    return templates.TemplateResponse(
        request=request,
        name="transcribe.html",
        context={
            "username": session["username"],
            "is_admin": session["is_admin"],
            "devices": devices,
            "active_page": "transcribe"
        }
    )


@router.post("/transcribe", response_class=HTMLResponse)
async def transcribe_post(
    request: Request,
    url: str = Form(...),
    model_size: str = Form("base"),
    device: str = Form(None),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=303)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(key="session_id")
        return response

    devices = get_available_devices()
    if not device or device not in devices:
        device = devices[0]

    context = {
        "username": session["username"],
        "is_admin": session["is_admin"],
        "devices": devices,
        "url": url,
        "model_size": model_size,
        "device": device,
        "active_page": "transcribe"
    }

    # Validate YouTube URL
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
        r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    if not re.match(youtube_regex, url):
        context["error"] = "Invalid YouTube URL format. Please provide a valid YouTube link."
        return templates.TemplateResponse(request=request, name="transcribe.html", context=context)

    # Temporary directory for audio inside the workspace
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "audio")
    audio_path = None
    start_time = time.time()
    try:
        # 1. Download audio from YouTube
        audio_path, video_title = download_audio_from_youtube(url, output_dir)
        context["video_title"] = video_title

        # 2. Transcribe using Whisper
        result = transcribe_audio(audio_path, model_size, device)
        context["transcript_text"] = result.get("text", "")
        
        elapsed_time = time.time() - start_time
        context["extract_duration"] = f"{elapsed_time:.1f}"
        context["success"] = f"Transcription completed successfully in {elapsed_time:.1f}s!"
        logger.info(f"YouTube transcription by '{session['username']}' completed successfully in {elapsed_time:.2f}s: {video_title}")
    except Exception as e:
        logger.error(f"YouTube transcription failed: {e}")
        context["error"] = f"An error occurred during transcription: {str(e)}"
    finally:
        # Clean up temporary audio file to prevent leaks
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
                logger.info(f"Cleaned up temporary audio file: {audio_path}")
            except Exception as cleanup_err:
                logger.warning(f"Failed to delete temporary audio file {audio_path}: {cleanup_err}")

    return templates.TemplateResponse(request=request, name="transcribe.html", context=context)
