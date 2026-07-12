import os
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("starfarm.main")

from fastapi import FastAPI, Cookie, Request, status
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.core.database import init_db, close_db, get_db
from src.core.auth import hash_password, get_session
from src.core.config import DEFAULT_SETTINGS
from src.core.templates import templates
from src.services.ner import load_model as load_ner_model

# Import modular routers
from src.routes.auth import router as auth_router
from src.routes.settings import router as settings_router
from src.routes.ner import router as ner_router
from src.routes.transcribe import router as transcribe_router
from src.routes.extract import router as extract_router
from src.routes.translate import router as translate_router
from src.routes.spaces import router as spaces_router

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

# Mount static files
app.mount("/static", StaticFiles(directory="src/static"), name="static")

# Include sub-routers
app.include_router(auth_router)
app.include_router(settings_router)
app.include_router(ner_router)
app.include_router(transcribe_router)
app.include_router(extract_router)
app.include_router(translate_router)
app.include_router(spaces_router)


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
        "error": error,
        "active_page": "dashboard"
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
