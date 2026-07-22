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

class LLMConnectionError(RuntimeError):
    pass


# Global circuit breaker state for LLM connection
_llm_online = True
_llm_last_checked = 0.0
_llm_offline_reason = ""


async def get_conductor_model() -> str:
    global _llm_online, _llm_last_checked, _llm_offline_reason
    import time
    
    current_time = time.time()
    # Circuit breaker: if marked offline within last 15 seconds, fail immediately without waiting for HTTP timeout
    if not _llm_online and (current_time - _llm_last_checked < 15.0):
        raise LLMConnectionError(f"Server LLM is offline. (Circuit Breaker active. Reason: {_llm_offline_reason})")

    import httpx
    conductor_api_base = os.getenv("CONDUCTOR_API_BASE", "https://www-conductor.quockhang.io.vn/v1")
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{conductor_api_base}/models", timeout=2.0)
            if resp.status_code == 200:
                data = resp.json()
                if "data" in data and len(data["data"]) > 0:
                    model_id = data["data"][0]["id"]
                    logger.info(f"Dynamically fetched conductor model: {model_id}")
                    _llm_online = True
                    _llm_last_checked = current_time
                    return model_id
            
            reason = f"Status code {resp.status_code}"
            _llm_online = False
            _llm_last_checked = current_time
            _llm_offline_reason = reason
            raise LLMConnectionError(f"Server LLM returned status code {resp.status_code}. Please check server logs.")
    except LLMConnectionError as e:
        raise e
    except (httpx.ConnectError, httpx.ConnectTimeout, httpx.RequestError) as e:
        logger.error(f"Conductor server is unreachable: {e}")
        _llm_online = False
        _llm_last_checked = current_time
        _llm_offline_reason = "Connection failed/Timeout"
        raise LLMConnectionError("Server LLM is offline or unreachable. Please verify serve.sh is running.")
    except Exception as e:
        logger.warning(f"Failed to dynamically fetch conductor model, using fallback: {e}")
    return "google/gemma-4-E2B-it-qat-w4a16-ct"


async def get_dspy_lm():
    import dspy
    model_id = await get_conductor_model()
    conductor_api_base = os.getenv("CONDUCTOR_API_BASE", "https://www-conductor.quockhang.io.vn/v1")
    return dspy.LM(
        model=f"openai/{model_id}",
        api_base=conductor_api_base,
        api_key="dummy",
        # Config parameters tuned for google/gemma-4-E2B-it-qat-w4a16-ct
        temperature=1.0,
        top_p=0.95,
        top_k=64
    )


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

    # Fetch predicates from db.predicates
    predicates_cursor = db.predicates.find({})
    predicates = await predicates_cursor.to_list(length=100)
    
    # Seed default agricultural predicates if empty
    if not predicates:
        default_preds = [
            {
                "name": "cultivated_in", 
                "label_en": "is grown in", 
                "label_vi": "được trồng ở", 
                "desc_en": "Which crop is grown in which region/location", 
                "desc_vi": "Cây trồng nào được trồng ở vùng miền/vị trí nào"
            },
            {
                "name": "affected_by", 
                "label_en": "is affected by", 
                "label_vi": "bị bệnh", 
                "desc_en": "Which crop is affected by which disease", 
                "desc_vi": "Cây trồng nào bị mắc bệnh hại gì"
            },
            {
                "name": "has_yield", 
                "label_en": "has yield", 
                "label_vi": "có năng suất", 
                "desc_en": "The average or peak yield of a crop", 
                "desc_vi": "Năng suất trung bình hoặc tối đa của cây trồng"
            },
            {
                "name": "grown_in_season", 
                "label_en": "is grown in season", 
                "label_vi": "trồng vào mùa", 
                "desc_en": "Which season or time of year the crop is grown", 
                "desc_vi": "Mùa vụ gieo trồng của cây trong năm"
            },
            {
                "name": "solution_for", 
                "label_en": "is remedy/solution for", 
                "label_vi": "giải pháp cho", 
                "desc_en": "Remedy or control solution for a crop disease", 
                "desc_vi": "Giải pháp phòng trừ hoặc chữa trị cho bệnh hại cây trồng"
            }
        ]
        await db.predicates.insert_many(default_preds)
        predicates = default_preds

    predicates = sorted(predicates, key=lambda x: x["name"])

    from fastapi.responses import HTMLResponse
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "username": username,
            "is_admin": session["is_admin"],
            "settings": sorted_settings,
            "predicates": predicates,
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
            Generate diverse and effective search queries for a search engine in a Retrieval-Augmented Generation (RAG) system.
            Generate exactly 5 queries in Vietnamese (queries_vi) and 5 queries in English (queries_en).
            The queries must be designed to retrieve documents relevant to the entity label and its definitions.
            """
            label_name = dspy.InputField(desc="The name of the entity label")
            definition_en = dspy.InputField(desc="The definition of the entity label in English")
            definition_vi = dspy.InputField(desc="The definition of the entity label in Vietnamese")
            queries_vi = dspy.OutputField(desc="Exactly 5 Vietnamese search queries, numbered 1 to 5, one per line")
            queries_en = dspy.OutputField(desc="Exactly 5 English search queries, numbered 1 to 5, one per line")
            
        data = await request.json()
        name = data.get("name", "")
        desc_en = data.get("desc_en", "")
        desc_vi = data.get("desc_vi", "")
        force_regen = data.get("force_regen", False)
        
        if not name:
            return {"success": False, "error": "Label name is required."}
            
        username = session["username"]
        db = get_db()
        
        # Check cache if not forcing regeneration
        if not force_regen:
            user = await db.users.find_one({"username": username})
            if user:
                labels = user.get("settings", {}).get("labels", [])
                for l in labels:
                    if l.get("name") == name:
                        cached_vi = l.get("queries_vi")
                        cached_en = l.get("queries_en")
                        if cached_vi and cached_en and len(cached_vi) == 5 and len(cached_en) == 5:
                            logger.info(f"Returning cached enhanced queries for label '{name}'")
                            return {
                                "success": True, 
                                "queries_vi": cached_vi, 
                                "queries_en": cached_en, 
                                "cached": True
                            }
            
        # Configure DSPy LM
        lm = await get_dspy_lm()
        
        with dspy.context(lm=lm):
            predictor = dspy.Predict(GenerateRAGQueries)
            result = predictor(
                label_name=name,
                definition_en=desc_en,
                definition_vi=desc_vi
            )
            
        queries_vi_text = result.queries_vi
        queries_en_text = result.queries_en
        
        import re
        
        def parse_queries(text, default_query):
            parsed = []
            if text:
                for line in text.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    # Remove leading numbers/bullets like "1.", "- ", "2) " or "1. "
                    cleaned = re.sub(r'^[\d\-\*\.\)\s]+', '', line).strip()
                    if cleaned:
                        parsed.append(cleaned)
            parsed = parsed[:5]
            while len(parsed) < 5:
                parsed.append(default_query)
            return parsed
            
        queries_vi = parse_queries(queries_vi_text, f"Truy vấn tài liệu liên quan đến nhãn {name}")
        queries_en = parse_queries(queries_en_text, f"Retrieve documents related to label {name}")
        
        # Save generated queries to label document inside users collection
        await db.users.update_one(
            {"username": username, "settings.labels.name": name},
            {
                "$set": {
                    "settings.labels.$.queries_vi": queries_vi,
                    "settings.labels.$.queries_en": queries_en
                }
            }
        )
            
        logger.info(f"Bilingual query enhancement completed and saved for label '{name}' using model '{lm.model}'")
        return {
            "success": True, 
            "queries_vi": queries_vi, 
            "queries_en": queries_en,
            "cached": False
        }
    except Exception as e:
        logger.error(f"Query enhancement failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/settings/labels/suggest-definition")
async def suggest_label_definition(
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
        
        class GenerateLabelDefinition(dspy.Signature):
            """
            Generate a brief and accurate definition/description for a given entity label key name.
            Generate exactly one brief definition in English (definition_en) and one in Vietnamese (definition_vi).
            Each description must be a single concise sentence.
            """
            label_name = dspy.InputField(desc="The name/key of the entity label, e.g. 'crop_disease' or 'fertilizer'")
            definition_en = dspy.OutputField(desc="A brief one-sentence English description of what this entity is")
            definition_vi = dspy.OutputField(desc="Một mô tả ngắn gọn một câu bằng Tiếng Việt về thực thể này")
            
        data = await request.json()
        name = data.get("name", "")
        if not name:
            return {"success": False, "error": "Label name is required."}
            
        # Configure DSPy LM
        lm = await get_dspy_lm()
        
        with dspy.context(lm=lm):
            predictor = dspy.Predict(GenerateLabelDefinition)
            result = predictor(label_name=name)
            
        desc_en = result.definition_en.strip() if result.definition_en else ""
        desc_vi = result.definition_vi.strip() if result.definition_vi else ""
        
        logger.info(f"Label definition generated for '{name}' using model '{lm.model}'")
        return {"success": True, "desc_en": desc_en, "desc_vi": desc_vi}
    except Exception as e:
        logger.error(f"Label definition generation failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/settings/predicates/add")
async def add_predicate(
    name: str = Form(...),
    label_en: str = Form(...),
    label_vi: str = Form(...),
    desc_en: str = Form(""),
    desc_vi: str = Form(""),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session or not session.get("is_admin"):
        return RedirectResponse(url="/dashboard?error=Unauthorized action.", status_code=status.HTTP_303_SEE_OTHER)

    import datetime
    name = name.strip().lower().replace(" ", "_")
    db = get_db()
    
    # Check if predicate already exists
    existing = await db.predicates.find_one({"name": name})
    if existing:
        return RedirectResponse(url="/settings?error=Predicate name already exists.", status_code=status.HTTP_303_SEE_OTHER)
        
    new_pred = {
        "name": name,
        "label_en": label_en.strip(),
        "label_vi": label_vi.strip(),
        "desc_en": desc_en.strip(),
        "desc_vi": desc_vi.strip(),
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }
    await db.predicates.insert_one(new_pred)
    logger.info(f"Predicate '{name}' added successfully by admin '{session['username']}'.")
    return RedirectResponse(url="/settings?success=Predicate added successfully.", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/predicates/delete/{name}")
async def delete_predicate(
    name: str,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    session = await get_session(session_id)
    if not session or not session.get("is_admin"):
        return RedirectResponse(url="/dashboard?error=Unauthorized action.", status_code=status.HTTP_303_SEE_OTHER)

    db = get_db()
    result = await db.predicates.delete_one({"name": name})
    if result.deleted_count == 0:
        return RedirectResponse(url="/settings?error=Predicate not found.", status_code=status.HTTP_303_SEE_OTHER)
        
    logger.info(f"Predicate '{name}' deleted successfully by admin '{session['username']}'.")
    return RedirectResponse(url="/settings?success=Predicate deleted successfully.", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/settings/predicates/suggest")
async def suggest_predicate_definitions(
    request: Request,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return {"success": False, "error": "Unauthorized"}
    session = await get_session(session_id)
    if not session or not session.get("is_admin"):
        return {"success": False, "error": "Unauthorized"}

    try:
        import dspy
        
        class GeneratePredicateDefinition(dspy.Signature):
            """
            Generate bilingual labels and descriptions for a relationship predicate key name in an agricultural knowledge graph context.
            Example input:
              predicate_name: 'cultivated_in'
            Example output:
              label_en: 'is grown in'
              label_vi: 'được trồng ở'
              desc_en: 'Which crop is grown in which region/location'
              desc_vi: 'Cây trồng nào được trồng ở vùng miền/vị trí nào'
            """
            predicate_name = dspy.InputField(desc="The name/key of the relationship predicate, e.g. 'cultivated_in' or 'affected_by'")
            label_en = dspy.OutputField(desc="A brief English label, e.g. 'is grown in'")
            label_vi = dspy.OutputField(desc="Một nhãn tiếng Việt ngắn gọn, ví dụ: 'được trồng ở'")
            desc_en = dspy.OutputField(desc="A brief one-sentence English description of the relation")
            desc_vi = dspy.OutputField(desc="Một mô tả ngắn gọn một câu bằng tiếng Việt về mối quan hệ")

        data = await request.json()
        name = data.get("name", "")
        if not name:
            return {"success": False, "error": "Predicate name is required."}

        # Configure DSPy LM
        lm = await get_dspy_lm()
        
        with dspy.context(lm=lm):
            predictor = dspy.Predict(GeneratePredicateDefinition)
            result = predictor(predicate_name=name)

        logger.info(f"Predicate definitions suggested for '{name}' using model '{lm.model}'")
        return {
            "success": True,
            "label_en": result.label_en.strip() if result.label_en else "",
            "label_vi": result.label_vi.strip() if result.label_vi else "",
            "desc_en": result.desc_en.strip() if result.desc_en else "",
            "desc_vi": result.desc_vi.strip() if result.desc_vi else ""
        }
    except Exception as e:
        logger.error(f"Predicate suggestion generation failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/settings/predicates/add_auto")
async def add_auto_predicate(
    request: Request,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return {"success": False, "error": "Unauthorized"}
    session = await get_session(session_id)
    if not session:
        return {"success": False, "error": "Unauthorized"}

    try:
        data = await request.json()
        raw_pred = data.get("predicate", "").strip()
        if not raw_pred:
            return {"success": False, "error": "Predicate is required."}

        import re, datetime
        # Slugify predicate for key name
        name = re.sub(r'[^a-z0-9_]', '', raw_pred.lower().replace(" ", "_")).strip("_")
        if not name:
            name = f"pred_{int(datetime.datetime.now().timestamp())}"

        db = get_db()
        pattern = re.compile(f"^{re.escape(raw_pred)}$", re.IGNORECASE)
        existing = await db.predicates.find_one({
            "$or": [
                {"name": name},
                {"label_en": pattern},
                {"label_vi": pattern}
            ]
        })

        if existing:
            return {
                "success": True,
                "already_exists": True,
                "message": f"Predicate '{existing.get('label_vi') or existing['name']}' already exists in settings.",
                "predicate": existing["name"]
            }

        # Generate definitions using LLM (DSPy)
        import dspy
        
        class GeneratePredicateDefinition(dspy.Signature):
            """
            Generate bilingual labels and descriptions for a relationship predicate key name in an agricultural knowledge graph context.
            """
            predicate_name = dspy.InputField(desc="The name/key of the relationship predicate")
            label_en = dspy.OutputField(desc="A brief English label")
            label_vi = dspy.OutputField(desc="Một nhãn tiếng Việt ngắn gọn")
            desc_en = dspy.OutputField(desc="A brief one-sentence English description of the relation")
            desc_vi = dspy.OutputField(desc="Một mô tả ngắn gọn một câu bằng tiếng Việt về mối quan hệ")

        lm = await get_dspy_lm()
        with dspy.context(lm=lm):
            predictor = dspy.Predict(GeneratePredicateDefinition)
            result = predictor(predicate_name=raw_pred)

        label_en = result.label_en.strip() if result.label_en else raw_pred
        label_vi = result.label_vi.strip() if result.label_vi else raw_pred
        desc_en = result.desc_en.strip() if result.desc_en else f"Relationship '{raw_pred}'"
        desc_vi = result.desc_vi.strip() if result.desc_vi else f"Mối quan hệ '{raw_pred}'"

        new_pred = {
            "name": name,
            "label_en": label_en,
            "label_vi": label_vi,
            "desc_en": desc_en,
            "desc_vi": desc_vi,
            "created_at": datetime.datetime.now(datetime.timezone.utc)
        }
        await db.predicates.insert_one(new_pred)
        logger.info(f"Predicate '{name}' auto-added by '{session['username']}' using model '{lm.model}'")

        return {
            "success": True,
            "already_exists": False,
            "message": f"Predicate '{raw_pred}' successfully added to settings.",
            "predicate": new_pred
        }
    except LLMConnectionError as e:
        logger.error(f"Auto-add predicate failed due to LLM connection error: {e}")
        return {"success": False, "error": f"LLM connection error: {e}"}
    except Exception as e:
        logger.error(f"Auto-add predicate failed: {e}")
        return {"success": False, "error": str(e)}

