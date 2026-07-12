import json
import time
import logging
from fastapi import APIRouter, Form, Cookie, Request, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from src.core.auth import get_session
from src.services.translate import check_connection as check_translate_connection, translate_text, translate_text_stream
from src.core.templates import templates

logger = logging.getLogger("starfarm.routes.translate")

router = APIRouter()

@router.get("/translate", response_class=HTMLResponse)
async def translate_page(
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
            "active_page": "translate"
        }
    )


@router.post("/translate", response_class=HTMLResponse)
async def translate_post(
    request: Request,
    text: str = Form(...),
    source_lang: str = Form("en"),
    target_lang: str = Form("vi"),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=303)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=303)
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
        "active_page": "translate"
    }

    if not is_connected:
        context["error"] = f"Cannot translate: Translation server is offline. {err_msg}"
        return templates.TemplateResponse(request=request, name="translate.html", context=context)

    # Input validation
    text = text.strip()
    if not text:
        context["error"] = "Please provide text to translate."
        return templates.TemplateResponse(request=request, name="translate.html", context=context)

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


@router.post("/translate/stream")
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

    async def event_generator():
        try:
            async for event in translate_text_stream(text, source_lang, target_lang):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Streaming translation exception: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
