import logging
from fastapi import APIRouter, Form, Cookie, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from src.core.auth import get_session
from src.services.extractor import extract_url_content
from src.core.templates import templates

logger = logging.getLogger("starfarm.routes.extract")

router = APIRouter()

@router.get("/extract", response_class=HTMLResponse)
async def extract_page(
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

    return templates.TemplateResponse(
        request=request,
        name="extract.html",
        context={
            "username": session["username"],
            "is_admin": session["is_admin"],
            "active_page": "extract"
        }
    )


@router.post("/extract", response_class=HTMLResponse)
async def extract_post(
    request: Request,
    url: str = Form(...),
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        return RedirectResponse(url="/", status_code=303)
    session = await get_session(session_id)
    if not session:
        response = RedirectResponse(url="/", status_code=303)
        response.delete_cookie(key="session_id")
        return response

    context = {
        "username": session["username"],
        "is_admin": session["is_admin"],
        "url": url,
        "active_page": "extract"
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
