import logging
import re
import os
from fastapi import APIRouter, Form, Cookie, Request, HTTPException, status
from fastapi.responses import RedirectResponse
from src.core.database import get_db
from src.core.auth import get_session
from src.core.config import DEFAULT_SETTINGS
from src.core.templates import templates

logger = logging.getLogger("starfarm.routes.settings")

router = APIRouter()

async def get_conductor_model() -> str:
    import httpx
    conductor_api_base = os.getenv("CONDUCTOR_API_BASE", "https://www-conductor.quockhang.io.vn/v1")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{conductor_api_base}/models")
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and len(data["data"]) > 0:
                    model_id = data["data"][0]["id"]
                    logger.info(f"Dynamically fetched conductor model: {model_id}")
                    return model_id
    except Exception as e:
        logger.warning(f"Failed to dynamically fetch conductor model, using fallback: {e}")
    return "google/gemma-4-E2B-it-qat-w4a16-ct"


@router.get("/settings", response_class=RedirectResponse)
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

    from fastapi.responses import HTMLResponse
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

@router.post("/settings/language")
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

@router.post("/settings/labels/add")
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

@router.post("/settings/labels/edit")
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

@router.post("/settings/labels/delete/{label_name}")
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


@router.post("/settings/labels/enhance")
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
        
        conductor_api_base = os.getenv("CONDUCTOR_API_BASE", "https://www-conductor.quockhang.io.vn/v1")
        
        # Configure DSPy LM
        lm = dspy.LM(
            model=f"openai/{model_id}",
            api_base=conductor_api_base,
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
