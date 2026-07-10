import os
import re
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Form, Cookie, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import escape, Markup

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("starfarm.main")

from src.database import init_db, close_db, get_db
from src.auth import hash_password, verify_password, create_session, get_session, delete_session
from src.ner import load_model as load_ner_model, extract_entities
from src.transcribe import get_available_devices, download_audio_from_youtube, transcribe_audio

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize MongoDB and Redis
    logger.info("Initializing databases...")
    await init_db()
    
    # Seeding default Admin user if db is empty or admin doesn't exist
    try:
        db = get_db()
        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "adminpassword")
        
        # Check if admin user already exists
        existing_admin = await db.users.find_one({"username": admin_username})
        if not existing_admin:
            logger.info(f"Default admin user '{admin_username}' not found. Creating default admin...")
            hashed_pw = hash_password(admin_password)
            await db.users.insert_one({
                "username": admin_username,
                "password_hash": hashed_pw,
                "is_admin": True
            })
            logger.info("Default admin user created successfully.")
        else:
            logger.info(f"Admin user '{admin_username}' already exists. Skipping seed.")
    except Exception as e:
        logger.error(f"Error seeding default admin user: {e}")

    # Pre-load NER model so first request doesn't stall
    try:
        load_ner_model()
    except Exception as e:
        logger.warning(f"NER model pre-load failed (will retry lazily): {e}")

    yield
    # Shutdown: Close DB connections
    logger.info("Closing database connections...")
    await close_db()

# Create FastAPI app
app = FastAPI(
    title="Starfarm Admin",
    description="Starfarm Login and Admin User Management Console",
    lifespan=lifespan
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")

@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request, session_id: str | None = Cookie(default=None), error: str | None = None):
    # Verify session
    if session_id:
        session = await get_session(session_id)
        if session:
            # User is already logged in, redirect to dashboard
            return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
            
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"error": error}
    )

@app.post("/login")
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    try:
        db = get_db()
        # Find user in database
        user = await db.users.find_one({"username": username})
        if user and verify_password(password, user["password_hash"]):
            # Create session in Redis
            is_admin = user.get("is_admin", False)
            token = await create_session(username, is_admin)
            
            response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
            # Set cookie with 30 minutes expiry (1800 seconds)
            response.set_cookie(
                key="session_id",
                value=token,
                httponly=True,
                max_age=1800,
                samesite="lax"
            )
            logger.info(f"User '{username}' logged in successfully.")
            return response
            
        # Authentication failed
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "Incorrect username or password."}
        )
    except Exception as e:
        logger.error(f"Error during login: {e}")
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"error": "System error. Please try again later."}
        )

@app.post("/logout")
async def logout(session_id: str | None = Cookie(default=None)):
    if session_id:
        await delete_session(session_id)
        
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session_id")
    return response

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    session_id: str | None = Cookie(default=None),
    success: str | None = None,
    error: str | None = None,
    view: str | None = None
):
    # Verify session
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        
    session = await get_session(session_id)
    if not session:
        # Invalid or expired session
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(key="session_id")
        return response
        
    username = session["username"]
    is_admin = session["is_admin"]
    
    # Determine which view to show
    # Admin defaults to 'admin', standard users always get 'apps'
    if is_admin:
        current_view = view if view in ("admin", "apps") else "admin"
    else:
        current_view = "apps"
    
    # Context dictionary
    context = {
        "username": username,
        "is_admin": is_admin,
        "view": current_view,
        "success": success,
        "error": error
    }
    
    # If admin viewing admin panel, fetch all users
    if is_admin and current_view == "admin":
        try:
            db = get_db()
            cursor = db.users.find({}, {"username": 1, "is_admin": 1})
            users = await cursor.to_list(length=100)
            context["users"] = users
        except Exception as e:
            logger.error(f"Failed to fetch users: {e}")
            context["error"] = "Failed to load user list."
            context["users"] = []
            
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context=context
    )

@app.post("/create-user")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    is_admin: str | None = Form(default=None),
    session_id: str | None = Cookie(default=None)
):
    # Check session
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        
    session = await get_session(session_id)
    if not session or not session["is_admin"]:
        # Unauthorized
        return RedirectResponse(url="/dashboard?error=You do not have permission to perform this action.", status_code=status.HTTP_303_SEE_OTHER)
        
    # Input validation
    username = username.strip()
    if len(username) < 3:
        return RedirectResponse(url="/dashboard?error=Username must be at least 3 characters long.", status_code=status.HTTP_303_SEE_OTHER)
        
    if len(password) < 6:
        return RedirectResponse(url="/dashboard?error=Password must be at least 6 characters long.", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        db = get_db()
        # Check if user already exists
        existing_user = await db.users.find_one({"username": username})
        if existing_user:
            return RedirectResponse(url="/dashboard?error=Username already exists.", status_code=status.HTTP_303_SEE_OTHER)
            
        # Hash password and insert
        hashed_pw = hash_password(password)
        new_user = {
            "username": username,
            "password_hash": hashed_pw,
            "is_admin": is_admin == "true"
        }
        await db.users.insert_one(new_user)
        logger.info(f"Admin '{session['username']}' created new user '{username}' (is_admin: {is_admin == 'true'}).")
        
        return RedirectResponse(url=f"/dashboard?success=User '{username}' created successfully.", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error creating user: {e}")
        return RedirectResponse(url="/dashboard?error=System error occurred while creating the user.", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/delete-user/{username_to_delete}")
async def delete_user(
    request: Request,
    username_to_delete: str,
    session_id: str | None = Cookie(default=None)
):
    # Check session
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        
    session = await get_session(session_id)
    if not session or not session["is_admin"]:
        return RedirectResponse(url="/dashboard?error=You do not have permission to perform this action.", status_code=status.HTTP_303_SEE_OTHER)
        
    # Prevent self-deletion
    if username_to_delete == session["username"]:
        return RedirectResponse(url="/dashboard?error=You cannot delete your own account.", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        db = get_db()
        # Delete from MongoDB
        result = await db.users.delete_one({"username": username_to_delete})
        if result.deleted_count == 0:
            return RedirectResponse(url="/dashboard?error=User not found.", status_code=status.HTTP_303_SEE_OTHER)
            
        # Invalidate deleted user's sessions in Redis using direct prefix matching
        from src.database import get_redis
        redis_client = get_redis()
        async for key in redis_client.scan_iter(f"session:{username_to_delete}:*"):
            await redis_client.delete(key)
                    
        logger.info(f"Admin '{session['username']}' deleted user '{username_to_delete}'.")
        return RedirectResponse(url=f"/dashboard?success=User '{username_to_delete}' deleted successfully.", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        return RedirectResponse(url="/dashboard?error=System error occurred while deleting the user.", status_code=status.HTTP_303_SEE_OTHER)


# ── NER Routes ──────────────────────────────────────────────────────

MAX_NER_CHARS = 100000

# Color classes matching ner.html CSS
NER_TAG_CLASSES = [
    "ner-tag-0", "ner-tag-1", "ner-tag-2", "ner-tag-3",
    "ner-tag-4", "ner-tag-5", "ner-tag-6", "ner-tag-7",
]

def build_highlighted_html(text: str, entities_by_label: dict, labels: list[str]) -> str:
    """Build HTML string with inline entity highlights using direct spans."""
    spans = []
    label_index = {label: i for i, label in enumerate(labels)}
    for label, entities in entities_by_label.items():
        idx = label_index.get(label, 0) % 8
        for entity in entities:
            if isinstance(entity, dict):
                start = entity.get("start")
                end = entity.get("end")
                matched = entity.get("text")
                if start is not None and end is not None and matched is not None:
                    spans.append((start, end, matched, label, idx))
            elif isinstance(entity, str):
                # Fallback in case a raw string is passed
                pattern = re.compile(re.escape(entity), re.IGNORECASE)
                for m in pattern.finditer(text):
                    spans.append((m.start(), m.end(), m.group(), label, idx))

    if not spans:
        return str(escape(text))

    # Sort by start position, longer spans first for overlaps
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))

    # Remove overlapping spans (keep the first/longest)
    filtered = []
    last_end = -1
    for span in spans:
        if span[0] >= last_end:
            filtered.append(span)
            last_end = span[1]

    # Build HTML
    parts = []
    cursor = 0
    for start, end, matched, label, idx in filtered:
        if start > cursor:
            parts.append(str(escape(text[cursor:start])))
        tag_class = NER_TAG_CLASSES[idx]
        parts.append(
            f'<span class="ner-entity {tag_class}">'
            f'{escape(matched)}'
            f'<span class="ner-label">{escape(label)}</span>'
            f'</span>'
        )
        cursor = end
    if cursor < len(text):
        parts.append(str(escape(text[cursor:])))

    return Markup(''.join(parts))



@app.get("/ner", response_class=HTMLResponse)
async def ner_page(
    request: Request,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(key="session_id")
        return response

    return templates.TemplateResponse(
        request=request,
        name="ner.html",
        context={
            "username": session["username"],
            "is_admin": session["is_admin"],
        }
    )


@app.post("/ner", response_class=HTMLResponse)
async def ner_extract(
    request: Request,
    text: str = Form(...),
    labels: str = Form(""),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(key="session_id")
        return response

    context = {
        "username": session["username"],
        "is_admin": session["is_admin"],
        "text": text,
        "labels_str": labels,
    }

    # Validate
    if len(text) > MAX_NER_CHARS:
        context["error"] = f"Text exceeds the maximum limit of {MAX_NER_CHARS} characters."
        return templates.TemplateResponse(request=request, name="ner.html", context=context)

    label_list = [l.strip() for l in labels.split(",") if l.strip()]
    if not label_list:
        context["error"] = "Please provide at least one entity label."
        return templates.TemplateResponse(request=request, name="ner.html", context=context)

    try:
        result = extract_entities(text, label_list)
        entities = result.get("entities", {})
        context["results"] = entities
        context["highlighted_html"] = build_highlighted_html(text, entities, label_list)
        logger.info(f"NER extraction by '{session['username']}': {len(text)} chars, {len(label_list)} labels, {sum(len(v) for v in entities.values())} entities found.")
    except Exception as e:
        logger.error(f"NER extraction failed: {e}")
        context["error"] = "An error occurred during entity extraction. Please try again."

    return templates.TemplateResponse(request=request, name="ner.html", context=context)


# ── Transcribe Routes ────────────────────────────────────────────────

@app.get("/transcribe", response_class=HTMLResponse)
async def transcribe_page(
    request: Request,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
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
        }
    )


@app.post("/transcribe", response_class=HTMLResponse)
async def transcribe_post(
    request: Request,
    url: str = Form(...),
    model_size: str = Form("base"),
    device: str = Form(None),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
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
    }

    # Validate YouTube URL
    youtube_regex = (
        r'(https?://)?(www\.)?'
        '(youtube|youtu|youtube-nocookie)\.(com|be)/'
        '(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
    )
    if not re.match(youtube_regex, url):
        context["error"] = "Invalid YouTube URL format. Please provide a valid YouTube link."
        return templates.TemplateResponse(request=request, name="transcribe.html", context=context)

    # Temporary directory for audio inside the workspace
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "audio")
    audio_path = None
    try:
        # 1. Download audio from YouTube
        audio_path, video_title = download_audio_from_youtube(url, output_dir)
        context["video_title"] = video_title

        # 2. Transcribe using Whisper
        result = transcribe_audio(audio_path, model_size, device)
        context["transcript_text"] = result.get("text", "")
        context["success"] = "Transcription completed successfully!"
        logger.info(f"YouTube transcription by '{session['username']}' completed successfully: {video_title}")
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
