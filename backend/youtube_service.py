"""YouTube transcript fetching via youtube-transcript-api."""

import re
from typing import Any, Dict, Tuple

from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url_or_id: str) -> str | None:
    """Extract YouTube video ID from URL or return as-is if already an ID."""
    s = (url_or_id or "").strip()
    if not s:
        return None
    # https://www.youtube.com/watch?v=VIDEO_ID
    m = re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", s)
    if m:
        return m.group(1)
    # https://youtu.be/VIDEO_ID
    m = re.match(r"(?:https?://)?(?:www\.)?youtu\.be/([a-zA-Z0-9_-]{11})", s)
    if m:
        return m.group(1)
    # https://www.youtube.com/embed/VIDEO_ID
    m = re.search(r"/embed/([a-zA-Z0-9_-]{11})", s)
    if m:
        return m.group(1)
    # Assume it's already a video ID (11 chars)
    if re.match(r"^[a-zA-Z0-9_-]{11}$", s):
        return s
    return None


def fetch_transcript(url_or_id: str, languages: list[str] | None = None) -> Tuple[Dict[str, Any], int]:
    """
    Fetch transcript for a YouTube video.
    Returns (body, status). body has 'text', 'video_id', 'language', etc. or 'error'.
    """
    video_id = extract_video_id(url_or_id)
    if not video_id:
        return {"error": "Invalid YouTube URL or video ID"}, 400

    try:
        ytt = YouTubeTranscriptApi()
        fetched = ytt.fetch(video_id, languages=languages or ["en", "vi"])
    except Exception as e:
        err_name = type(e).__name__
        if "NoTranscript" in err_name or "TranscriptsDisabled" in err_name:
            msg = "No transcript available for this video. The video may not have captions enabled."
        elif "VideoUnavailable" in err_name or "VideoNotFound" in err_name:
            msg = "Video is unavailable or does not exist."
        else:
            msg = f"Failed to fetch transcript: {e!s}"
        return {"error": msg, "video_id": video_id}, 404

    if not fetched:
        return {
            "error": "No transcript available for this video.",
            "video_id": video_id,
        }, 404

    # FetchedTranscript is iterable over FetchedTranscriptSnippet (text, start, duration)
    snippets = list(fetched)
    text = "\n".join(s.text for s in snippets).strip()
    language = getattr(fetched, "language", "") or getattr(fetched, "language_code", "")

    return {
        "text": text,
        "video_id": video_id,
        "language": language,
        "snippet_count": len(snippets),
    }, 200
