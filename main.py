import os
from dotenv import load_dotenv
load_dotenv()
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

from src.core.database import init_db, close_db, get_db
from src.core.auth import hash_password, verify_password, create_session, get_session, delete_session
from src.services.ner import load_model as load_ner_model, extract_entities, AVAILABLE_MODELS
from src.services.transcribe import get_available_devices, download_audio_from_youtube, transcribe_audio
from src.services.extractor import extract_url_content
from src.services.translate import check_connection as check_translate_connection, translate_text

DEFAULT_SETTINGS = {
    "language": "en",
    "labels": [
        {
            "name": "crop",
            "desc_en": "Types of crops, agricultural plants, or grains",
            "desc_vi": "Các loại cây trồng, cây nông nghiệp hoặc ngũ cốc"
        },
        {
            "name": "disease",
            "desc_en": "Plant or crop diseases caused by pathogens",
            "desc_vi": "Bệnh hại cây trồng hoặc cây nông nghiệp do tác nhân gây bệnh"
        },
        {
            "name": "pest",
            "desc_en": "Agricultural pests, insects, or rodents affecting crops",
            "desc_vi": "Sâu bệnh, côn trùng hại hoặc động vật gặm nhấm ảnh hưởng đến cây trồng"
        },
        {
            "name": "pesticide",
            "desc_en": "Chemical or biological substances used to destroy pests",
            "desc_vi": "Chất hóa học hoặc sinh học dùng để tiêu diệt sâu hại"
        },
        {
            "name": "fertilizer",
            "desc_en": "Chemical or natural substances added to soil to increase fertility",
            "desc_vi": "Chất hóa học hoặc tự nhiên bổ sung vào đất để tăng độ phì nhiêu"
        },
        {
            "name": "variety",
            "desc_en": "Specific varieties or cultivars of agricultural crops",
            "desc_vi": "Các giống cây trồng hoặc giống cây nông nghiệp cụ thể"
        },
        {
            "name": "symptom",
            "desc_en": "Visible signs of plant diseases or nutrient deficiencies",
            "desc_vi": "Các dấu hiệu nhìn thấy được của bệnh cây hoặc thiếu hụt chất dinh dưỡng"
        },
        {
            "name": "pathogen",
            "desc_en": "Microorganisms like fungi, bacteria, or viruses causing diseases",
            "desc_vi": "Vi sinh vật như nấm, vi khuẩn hoặc vi-rút gây bệnh"
        },
        {
            "name": "season",
            "desc_en": "Agricultural seasons, weather periods, or farming cycles",
            "desc_vi": "Các vụ mùa nông nghiệp, thời kỳ thời tiết hoặc chu kỳ trồng trọt"
        },
        {
            "name": "person",
            "desc_en": "Names of people, individuals, or figures",
            "desc_vi": "Tên người, cá nhân hoặc nhân vật"
        },
        {
            "name": "organization",
            "desc_en": "Names of companies, agencies, institutions, or groups",
            "desc_vi": "Tên công ty, cơ quan, tổ chức hoặc hội nhóm"
        },
        {
            "name": "location",
            "desc_en": "Geographical places, areas, regions, or coordinates",
            "desc_vi": "Địa điểm địa lý, khu vực, vùng miền hoặc tọa độ"
        },
        {
            "name": "date",
            "desc_en": "Dates, years, specific days, or time durations",
            "desc_vi": "Ngày tháng, năm, ngày cụ thể hoặc thời lượng thời gian"
        },
        {
            "name": "quantity",
            "desc_en": "Numerical amounts, measurements, weights, or volumes",
            "desc_vi": "Số lượng bằng số, phép đo, trọng lượng hoặc thể tích"
        }
    ]
}

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
                "is_admin": True,
                "settings": DEFAULT_SETTINGS
            })
            logger.info("Default admin user created successfully.")
        else:
            logger.info(f"Admin user '{admin_username}' already exists. Skipping seed.")

        # Ensure all existing users have the default settings seeded/updated if they don't have settings or have old settings
        update_result = await db.users.update_many(
            {"$or": [
                {"settings": {"$exists": False}},
                {"settings.labels.name": "contract_party"}
            ]},
            {"$set": {"settings": DEFAULT_SETTINGS}}
        )
        if update_result.modified_count > 0:
            logger.info(f"Seeded/Updated default settings for {update_result.modified_count} users.")
    except Exception as e:
        logger.error(f"Error seeding default admin user/settings: {e}")

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
            "is_admin": is_admin == "true",
            "settings": DEFAULT_SETTINGS
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
        from src.core.database import get_redis
        redis_client = get_redis()
        async for key in redis_client.scan_iter(f"session:{username_to_delete}:*"):
            await redis_client.delete(key)
                    
        logger.info(f"Admin '{session['username']}' deleted user '{username_to_delete}'.")
        return RedirectResponse(url=f"/dashboard?success=User '{username_to_delete}' deleted successfully.", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        return RedirectResponse(url="/dashboard?error=System error occurred while deleting the user.", status_code=status.HTTP_303_SEE_OTHER)


# ── Settings Routes ──────────────────────────────────────────────────

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    session_id: str | None = Cookie(default=None),
    success: str | None = None,
    error: str | None = None
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session or not session.get("is_admin"):
        return RedirectResponse(url="/dashboard?error=You do not have permission to access Settings.", status_code=status.HTTP_303_SEE_OTHER)

    username = session["username"]
    db = get_db()
    user = await db.users.find_one({"username": username})
    user_settings = user.get("settings", DEFAULT_SETTINGS) if user else DEFAULT_SETTINGS
    
    # Sort labels alphabetically by name
    sorted_settings = {
        "language": user_settings.get("language", "en"),
        "labels": sorted(user_settings.get("labels", []), key=lambda x: x["name"])
    }

    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "username": username,
            "is_admin": session["is_admin"],
            "settings": sorted_settings,
            "active_page": "settings",
            "success": success,
            "error": error
        }
    )

@app.post("/settings/language")
async def update_language(
    language: str = Form(...),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session or not session.get("is_admin"):
        return RedirectResponse(url="/dashboard?error=Unauthorized action.", status_code=status.HTTP_303_SEE_OTHER)

    if language not in ("en", "vi"):
        return RedirectResponse(url="/settings?error=Invalid language selected.", status_code=status.HTTP_303_SEE_OTHER)

    username = session["username"]
    db = get_db()
    await db.users.update_one(
        {"username": username},
        {"$set": {"settings.language": language}}
    )
    logger.info(f"User '{username}' updated definition language to '{language}'.")
    return RedirectResponse(url="/settings?success=Language preference updated successfully.", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/settings/labels/add")
async def add_label(
    name: str = Form(...),
    desc_en: str = Form(""),
    desc_vi: str = Form(""),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session or not session.get("is_admin"):
        return RedirectResponse(url="/dashboard?error=Unauthorized action.", status_code=status.HTTP_303_SEE_OTHER)

    # Validate label name: lowercase, alphanumeric and underscores, no spaces
    name = name.strip().lower()
    if not re.match(r"^[a-z0-9_]+$", name) or len(name) < 2:
        return RedirectResponse(url="/settings?error=Label name must be alphanumeric with underscores, and at least 2 characters long.", status_code=status.HTTP_303_SEE_OTHER)

    username = session["username"]
    db = get_db()
    user = await db.users.find_one({"username": username})
    user_settings = user.get("settings", DEFAULT_SETTINGS)
    labels = user_settings.get("labels", [])

    # Check duplicate
    if any(l["name"] == name for l in labels):
        return RedirectResponse(url=f"/settings?error=Label '{name}' already exists.", status_code=status.HTTP_303_SEE_OTHER)

    new_label = {
        "name": name,
        "desc_en": desc_en.strip(),
        "desc_vi": desc_vi.strip()
    }
    
    await db.users.update_one(
        {"username": username},
        {"$push": {"settings.labels": new_label}}
    )
    logger.info(f"User '{username}' added new custom label '{name}'.")
    return RedirectResponse(url=f"/settings?success=Label '{name}' added successfully.", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/settings/labels/edit")
async def edit_label(
    name: str = Form(...),
    desc_en: str = Form(""),
    desc_vi: str = Form(""),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session or not session.get("is_admin"):
        return RedirectResponse(url="/dashboard?error=Unauthorized action.", status_code=status.HTTP_303_SEE_OTHER)

    name = name.strip().lower()
    username = session["username"]
    db = get_db()
    
    # Update matching label using array filter
    result = await db.users.update_one(
        {"username": username, "settings.labels.name": name},
        {
            "$set": {
                "settings.labels.$.desc_en": desc_en.strip(),
                "settings.labels.$.desc_vi": desc_vi.strip()
            }
        }
    )
    
    if result.matched_count == 0:
        return RedirectResponse(url=f"/settings?error=Label '{name}' not found.", status_code=status.HTTP_303_SEE_OTHER)

    logger.info(f"User '{username}' updated definitions for label '{name}'.")
    return RedirectResponse(url=f"/settings?success=Label '{name}' updated successfully.", status_code=status.HTTP_303_SEE_OTHER)

@app.post("/settings/labels/delete/{label_name}")
async def delete_label(
    label_name: str,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session or not session.get("is_admin"):
        return RedirectResponse(url="/dashboard?error=Unauthorized action.", status_code=status.HTTP_303_SEE_OTHER)

    username = session["username"]
    db = get_db()
    
    result = await db.users.update_one(
        {"username": username},
        {"$pull": {"settings.labels": {"name": label_name}}}
    )
    
    if result.modified_count == 0:
        return RedirectResponse(url=f"/settings?error=Label '{label_name}' not found or could not be deleted.", status_code=status.HTTP_303_SEE_OTHER)

    logger.info(f"User '{username}' deleted label '{label_name}'.")
    return RedirectResponse(url=f"/settings?success=Label '{label_name}' deleted successfully.", status_code=status.HTTP_303_SEE_OTHER)


async def get_conductor_model() -> str:
    import httpx
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://www-conductor.quockhang.io.vn/v1/models")
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and len(data["data"]) > 0:
                    model_id = data["data"][0]["id"]
                    logger.info(f"Dynamically fetched conductor model: {model_id}")
                    return model_id
    except Exception as e:
        logger.warning(f"Failed to dynamically fetch conductor model, using fallback: {e}")
    return "google/gemma-4-E2B-it-qat-w4a16-ct"


@app.post("/settings/labels/enhance")
async def enhance_label_queries(
    request: Request,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    try:
        import dspy
        
        class GenerateRAGQueries(dspy.Signature):
            """
            Generate exactly 5 diverse and effective search queries (in Vietnamese) for a search engine in a Retrieval-Augmented Generation (RAG) system.
            The queries must be designed to retrieve documents relevant to the entity label and its definitions.
            Return ONLY the numbered list of 5 queries.
            """
            label_name = dspy.InputField(desc="The name of the entity label")
            definition_en = dspy.InputField(desc="The definition of the entity label in English")
            definition_vi = dspy.InputField(desc="The definition of the entity label in Vietnamese")
            queries = dspy.OutputField(desc="Exactly 5 search queries, numbered 1 to 5, one per line")
            
        data = await request.json()
        name = data.get("name", "")
        desc_en = data.get("desc_en", "")
        desc_vi = data.get("desc_vi", "")
        
        if not name:
            return {"success": False, "error": "Label name is required."}
            
        model_id = await get_conductor_model()
        
        # Configure DSPy LM
        lm = dspy.LM(
            model=f"openai/{model_id}",
            api_base="https://www-conductor.quockhang.io.vn/v1",
            api_key="dummy"
        )
        
        with dspy.context(lm=lm):
            predictor = dspy.Predict(GenerateRAGQueries)
            result = predictor(
                label_name=name,
                definition_en=desc_en,
                definition_vi=desc_vi
            )
            
        queries_text = result.queries
        
        import re
        queries = []
        for line in queries_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Remove leading numbers/bullets like "1.", "- ", "2) " or "1. "
            cleaned = re.sub(r'^[\d\-\*\.\)\s]+', '', line).strip()
            if cleaned:
                queries.append(cleaned)
                
        # Slice to 5 and ensure fallback if fewer
        queries = queries[:5]
        while len(queries) < 5:
            queries.append(f"Truy vấn tài liệu liên quan đến nhãn {name}")
            
        logger.info(f"Query enhancement completed for label '{name}' using model '{model_id}'")
        return {"success": True, "queries": queries}
    except Exception as e:
        logger.error(f"Query enhancement failed: {e}")
        return {"success": False, "error": str(e)}


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

    username = session["username"]
    db = get_db()
    user = await db.users.find_one({"username": username})
    user_settings = user.get("settings", DEFAULT_SETTINGS) if user else DEFAULT_SETTINGS
    
    user_labels = sorted(user_settings.get("labels", []), key=lambda x: x["name"])
    labels_str = ",".join(l["name"] for l in user_labels)

    from src.services.ner import _model_name
    current_model = _model_name or "gliner2-multi-v1"

    return templates.TemplateResponse(
        request=request,
        name="ner.html",
        context={
            "username": username,
            "is_admin": session["is_admin"],
            "models": AVAILABLE_MODELS,
            "selected_model": current_model,
            "user_labels": user_labels,
            "labels_str": labels_str,
        }
    )


@app.post("/ner", response_class=HTMLResponse)
async def ner_extract(
    request: Request,
    text: str = Form(...),
    labels: str = Form(""),
    model: str = Form("gliner2-multi-v1"),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(key="session_id")
        return response

    username = session["username"]
    db = get_db()
    user = await db.users.find_one({"username": username})
    user_settings = user.get("settings", DEFAULT_SETTINGS) if user else DEFAULT_SETTINGS
    user_labels = sorted(user_settings.get("labels", []), key=lambda x: x["name"])
    lang = user_settings.get("language", "en")

    context = {
        "username": username,
        "is_admin": session["is_admin"],
        "text": text,
        "labels_str": labels,
        "user_labels": user_labels,
        "models": AVAILABLE_MODELS,
        "selected_model": model,
    }

    # Validate
    if len(text) > MAX_NER_CHARS:
        context["error"] = f"Text exceeds the maximum limit of {MAX_NER_CHARS} characters."
        return templates.TemplateResponse(request=request, name="ner.html", context=context)

    label_list = [l.strip() for l in labels.split(",") if l.strip()]
    if not label_list:
        context["error"] = "Please provide at least one entity label."
        return templates.TemplateResponse(request=request, name="ner.html", context=context)

    # Map label to bilingual description
    desc_field = f"desc_{lang}"
    label_desc_map = {}
    for l in user_labels:
        # Fallback between desc_en and desc_vi if one is empty
        desc = l.get(desc_field) or l.get("desc_en") or l.get("desc_vi") or l["name"]
        label_desc_map[l["name"]] = desc

    # Construct definitions dictionary
    labels_dict = {}
    for l in label_list:
        # If custom definition exists, use it. Otherwise, use label name itself.
        labels_dict[l] = label_desc_map.get(l, l)

    try:
        result = extract_entities(text, labels_dict, model)
        entities = result.get("entities", {})
        context["results"] = entities
        context["highlighted_html"] = build_highlighted_html(text, entities, label_list)
        logger.info(f"NER extraction by '{username}' using '{model}': {len(text)} chars, {len(label_list)} labels, {sum(len(v) for v in entities.values())} entities found.")
    except Exception as e:
        logger.error(f"NER extraction failed: {e}")
        context["error"] = f"An error occurred during entity extraction: {str(e)}"

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
    import time
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


# ── Extract Routes ───────────────────────────────────────────────────

@app.get("/extract", response_class=HTMLResponse)
async def extract_page(
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
        name="extract.html",
        context={
            "username": session["username"],
            "is_admin": session["is_admin"],
        }
    )


@app.post("/extract", response_class=HTMLResponse)
async def extract_post(
    request: Request,
    url: str = Form(...),
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
        "url": url,
    }

    try:
        result = extract_url_content(url)
        context["markdown"] = result.get("markdown", "")
        context["text"] = result.get("text", "")
        context["metadata"] = result.get("metadata", {})
        context["success"] = "Content extracted successfully!"
        logger.info(f"URL extraction by '{session['username']}' completed successfully: {url}")
    except Exception as e:
        logger.error(f"URL extraction failed: {e}")
        context["error"] = f"Extraction failed: {str(e)}"

    return templates.TemplateResponse(request=request, name="extract.html", context=context)


# ── Translate Routes ─────────────────────────────────────────────────

@app.get("/translate", response_class=HTMLResponse)
async def translate_page(
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

    is_connected, err_msg, _ = await check_translate_connection()
    default_text = (
        "ST25 rice, celebrated as one of the world's best rice varieties, was developed in Vietnam by "
        "agricultural engineer Ho Quang Cua and his team. Characterized by its long grains, distinct pineapple "
        "fragrance, and exceptionally soft texture when cooked, this high-yield, pest-resistant cultivar "
        "marks a milestone in Vietnam's premium agricultural export market."
    )
    return templates.TemplateResponse(
        request=request,
        name="translate.html",
        context={
            "username": session["username"],
            "is_admin": session["is_admin"],
            "is_connected": is_connected,
            "connection_error": err_msg,
            "text": default_text,
        }
    )


@app.post("/translate", response_class=HTMLResponse)
async def translate_post(
    request: Request,
    text: str = Form(...),
    source_lang: str = Form("en"),
    target_lang: str = Form("vi"),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(key="session_id")
        return response

    is_connected, err_msg, _ = await check_translate_connection()
    context = {
        "username": session["username"],
        "is_admin": session["is_admin"],
        "is_connected": is_connected,
        "connection_error": err_msg,
        "text": text,
        "source_lang": source_lang,
        "target_lang": target_lang,
    }

    if not is_connected:
        context["error"] = f"Cannot translate: Translation server is offline. {err_msg}"
        return templates.TemplateResponse(request=request, name="translate.html", context=context)

    # Input validation
    text = text.strip()
    if not text:
        context["error"] = "Please provide text to translate."
        return templates.TemplateResponse(request=request, name="translate.html", context=context)

    import time
    start_time = time.time()
    try:
        result = await translate_text(text, source_lang, target_lang)
        elapsed_time = time.time() - start_time
        
        context["translated_text"] = result.get("translated_text", "")
        context["model_used"] = result.get("model_used", "")
        context["usage"] = result.get("usage", {})
        context["duration"] = f"{elapsed_time:.2f}"
        context["success"] = "Translation completed successfully!"
        logger.info(f"Translation by '{session['username']}' completed successfully in {elapsed_time:.2f}s using {result.get('model_used')}.")
    except Exception as e:
        logger.error(f"Translation failed: {e}")
        context["error"] = f"Translation failed: {str(e)}"

    return templates.TemplateResponse(request=request, name="translate.html", context=context)


@app.post("/translate/stream")
async def translate_stream(
    text: str = Form(...),
    source_lang: str = Form("en"),
    target_lang: str = Form("vi"),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    import json
    from src.services.translate import translate_text_stream

    async def event_generator():
        try:
            async for event in translate_text_stream(text, source_lang, target_lang):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Streaming translation exception: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    from fastapi.responses import StreamingResponse
    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Spaces Routes ───────────────────────────────────────────────────

@app.post("/spaces/save")
async def save_to_spaces(
    request: Request,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        data = await request.json()
        title = data.get("title", "").strip()
        text = data.get("text", "").strip()
        entities = data.get("entities", {})
        labels = data.get("labels", [])
        model = data.get("model", "gliner2-multi-v1")
        
        if not title:
            return {"success": False, "error": "Title is required."}
        if not text:
            return {"success": False, "error": "Text is required."}
            
        db = get_db()
        import datetime
        doc = {
            "title": title,
            "text": text,
            "entities": entities,
            "labels": labels,
            "model": model,
            "author": session["username"],
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
        await db.spaces_documents.insert_one(doc)
        logger.info(f"Document '{title}' saved to Spaces by user '{session['username']}'.")
        return {"success": True, "message": "Document saved successfully to Spaces."}
    except Exception as e:
        logger.error(f"Failed to save document to Spaces: {e}")
        return {"success": False, "error": f"Failed to save document: {str(e)}"}


@app.get("/spaces", response_class=HTMLResponse)
async def spaces_list_page(
    request: Request,
    q: str | None = None,
    session_id: str | None = Cookie(default=None),
    success: str | None = None,
    error: str | None = None
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(key="session_id")
        return response

    username = session["username"]
    db = get_db()
    
    # Query documents
    query = {}
    if q:
        # Search by title or text case-insensitive
        query = {
            "$or": [
                {"title": {"$regex": q, "$options": "i"}},
                {"text": {"$regex": q, "$options": "i"}}
            ]
        }
    
    cursor = db.spaces_documents.find(query).sort("created_at", -1)
    documents = await cursor.to_list(length=200)
    
    return templates.TemplateResponse(
        request=request,
        name="spaces.html",
        context={
            "username": username,
            "is_admin": session["is_admin"],
            "documents": documents,
            "q": q or "",
            "success": success,
            "error": error,
            "active_page": "spaces"
        }
    )


@app.get("/spaces/{doc_id}", response_class=HTMLResponse)
async def space_document_detail(
    request: Request,
    doc_id: str,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(key="session_id")
        return response

    username = session["username"]
    db = get_db()
    
    from bson import ObjectId
    try:
        doc = await db.spaces_documents.find_one({"_id": ObjectId(doc_id)})
    except Exception:
        return RedirectResponse(url="/spaces?error=Invalid document ID.", status_code=status.HTTP_303_SEE_OTHER)
        
    if not doc:
        return RedirectResponse(url="/spaces?error=Document not found.", status_code=status.HTTP_303_SEE_OTHER)
        
    # Render highlighted HTML using existing build_highlighted_html logic
    labels = doc.get("labels", [])
    entities = doc.get("entities", {})
    text = doc.get("text", "")
    
    highlighted_html = build_highlighted_html(text, entities, labels)
    
    return templates.TemplateResponse(
        request=request,
        name="space_detail.html",
        context={
            "username": username,
            "is_admin": session["is_admin"],
            "doc": doc,
            "highlighted_html": highlighted_html,
            "active_page": "spaces"
        }
    )


@app.post("/spaces/{doc_id}/delete")
async def delete_space_document(
    doc_id: str,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
        response.delete_cookie(key="session_id")
        return response

    username = session["username"]
    db = get_db()
    
    from bson import ObjectId
    try:
        doc = await db.spaces_documents.find_one({"_id": ObjectId(doc_id)})
    except Exception:
        return RedirectResponse(url="/spaces?error=Invalid document ID.", status_code=status.HTTP_303_SEE_OTHER)
        
    if not doc:
        return RedirectResponse(url="/spaces?error=Document not found.", status_code=status.HTTP_303_SEE_OTHER)
        
    # Authorization check: only author can delete
    if doc.get("author") != username:
        return RedirectResponse(url=f"/spaces?error=You do not have permission to delete this document.", status_code=status.HTTP_303_SEE_OTHER)
        
    try:
        await db.spaces_documents.delete_one({"_id": ObjectId(doc_id)})
        logger.info(f"Document '{doc.get('title')}' (ID: {doc_id}) deleted by author '{username}'.")
        return RedirectResponse(url=f"/spaces?success=Document '{doc.get('title')}' deleted successfully.", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        logger.error(f"Failed to delete document {doc_id}: {e}")
        return RedirectResponse(url=f"/spaces?error=Failed to delete document: {str(e)}", status_code=status.HTTP_303_SEE_OTHER)
