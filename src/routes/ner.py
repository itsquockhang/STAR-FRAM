import logging
from fastapi import APIRouter, Form, Cookie, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from src.core.database import get_db
from src.core.auth import get_session
from src.core.config import DEFAULT_SETTINGS
from src.core.utils import build_highlighted_html
from src.services.ner import extract_entities, AVAILABLE_MODELS
from src.core.templates import templates

logger = logging.getLogger("starfarm.routes.ner")

router = APIRouter()

MAX_NER_CHARS = 100000

@router.get("/ner", response_class=HTMLResponse)
async def ner_page(
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
            "active_page": "ner"
        }
    )


@router.post("/ner", response_class=HTMLResponse)
async def ner_extract(
    request: Request,
    text: str = Form(...),
    labels: str = Form(""),
    model: str = Form("gliner2-multi-v1"),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=303)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=303)
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
        "active_page": "ner"
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
        desc = l.get(desc_field) or l.get("desc_en") or l.get("desc_vi") or l["name"]
        label_desc_map[l["name"]] = desc

    # Construct definitions dictionary
    labels_dict = {}
    for l in label_list:
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
