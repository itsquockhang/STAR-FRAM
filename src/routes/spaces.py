import logging
import datetime
from bson import ObjectId
from fastapi import APIRouter, Form, Cookie, Request, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from src.core.database import get_db
from src.core.auth import get_session
from src.core.utils import build_highlighted_html
from src.core.templates import templates

logger = logging.getLogger("starfarm.routes.spaces")

router = APIRouter()

@router.post("/spaces/save")
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


@router.get("/spaces", response_class=HTMLResponse)
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


@router.get("/spaces/{doc_id}", response_class=HTMLResponse)
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


@router.post("/spaces/{doc_id}/delete")
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
