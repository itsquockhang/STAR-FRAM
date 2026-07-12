import logging
from fastapi import APIRouter, Form, Cookie, Request, status
from fastapi.responses import RedirectResponse
from src.core.database import get_db
from src.core.auth import hash_password, verify_password, create_session, get_session, delete_session
from src.core.config import DEFAULT_SETTINGS
from src.core.templates import templates

logger = logging.getLogger("starfarm.routes.auth")

router = APIRouter()

@router.post("/login")
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

@router.post("/logout")
async def logout(session_id: str | None = Cookie(default=None)):
    if session_id:
        await delete_session(session_id)
        
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="session_id")
    return response

@router.post("/create-user")
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

@router.post("/delete-user/{username_to_delete}")
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
