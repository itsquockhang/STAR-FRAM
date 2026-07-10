import os
import uuid
import json
import datetime
import bcrypt
import jwt
from src.database import get_redis

SECRET_KEY = os.getenv("SECRET_KEY", "starfarm-super-secret-key-123456")
ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

async def create_session(username: str, is_admin: bool, ttl: int = 1800) -> str:
    """Create a signed JWT session, store the tracking record in Redis, and return token."""
    jti = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.timezone.utc)
    
    payload = {
        "sub": username,
        "is_admin": is_admin,
        "jti": jti,
        "iat": now,
        "exp": now + datetime.timedelta(seconds=ttl)
    }
    
    # Generate signed JWT
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    
    # Map the session in Redis to enable instant revocation (logouts/deletions)
    redis_client = get_redis()
    key = f"session:{username}:{jti}"
    session_data = {
        "username": username,
        "is_admin": "true" if is_admin else "false",
        "jti": jti
    }
    await redis_client.set(key, json.dumps(session_data), ex=ttl)
    return token

async def get_session(token: str) -> dict | None:
    """Decode, verify signature and expiration of the JWT, and check active Redis state."""
    if not token:
        return None
    try:
        # Decode and verify signature & expiry
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        jti = payload.get("jti")
        if not username or not jti:
            return None
            
        # Verify that this session has not been revoked in Redis (e.g. via Logout/Deletion)
        redis_client = get_redis()
        key = f"session:{username}:{jti}"
        data = await redis_client.get(key)
        if not data:
            return None
            
        session_data = json.loads(data)
        session_data["is_admin"] = session_data.get("is_admin") == "true"
        return session_data
    except (jwt.PyJWTError, Exception):
        return None

async def delete_session(token: str):
    """Revoke session instantly by deleting its key from Redis."""
    if not token:
        return
    try:
        # Decode without verification checks if it's already expired, to fetch the identifier
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_signature": True})
        username = payload.get("sub")
        jti = payload.get("jti")
        if username and jti:
            redis_client = get_redis()
            key = f"session:{username}:{jti}"
            await redis_client.delete(key)
    except jwt.PyJWTError:
        # If token is corrupted or signature validation fails, ignore
        pass
