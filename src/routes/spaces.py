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
    
    # Fetch predicates
    predicates_cursor = db.predicates.find({})
    predicates = await predicates_cursor.to_list(length=100)
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
    
    return templates.TemplateResponse(
        request=request,
        name="space_detail.html",
        context={
            "username": username,
            "is_admin": session["is_admin"],
            "doc": doc,
            "highlighted_html": highlighted_html,
            "predicates": predicates,
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


@router.post("/spaces/{doc_id}/relations/add")
async def add_relation(
    doc_id: str,
    request: Request,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db = get_db()
    try:
        data = await request.json()
        subject = data.get("subject", "").strip()
        predicate = data.get("predicate", "").strip()
        obj = data.get("object", "").strip()

        if not subject or not predicate or not obj:
            return {"success": False, "error": "Subject, predicate, and object are required."}

        # Add to document relations array
        res = await db.spaces_documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$push": {"relations": {"subject": subject, "predicate": predicate, "object": obj}}}
        )
        if res.matched_count == 0:
            return {"success": False, "error": "Document not found."}

        logger.info(f"Relation ({subject} - {predicate} - {obj}) added to document {doc_id} by user {session['username']}")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to add relation to doc {doc_id}: {e}")
        return {"success": False, "error": str(e)}


@router.post("/spaces/{doc_id}/relations/delete")
async def delete_relation(
    doc_id: str,
    request: Request,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db = get_db()
    try:
        data = await request.json()
        subject = data.get("subject", "").strip()
        predicate = data.get("predicate", "").strip()
        obj = data.get("object", "").strip()

        # Remove from document relations array
        res = await db.spaces_documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$pull": {"relations": {"subject": subject, "predicate": predicate, "object": obj}}}
        )
        if res.matched_count == 0:
            return {"success": False, "error": "Document not found."}

        logger.info(f"Relation ({subject} - {predicate} - {obj}) deleted from document {doc_id} by user {session['username']}")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete relation from doc {doc_id}: {e}")
        return {"success": False, "error": str(e)}


@router.post("/spaces/{doc_id}/relations/auto-extract")
async def auto_extract_relations(
    doc_id: str,
    session_id: str | None = Cookie(default=None)
):
    if not session_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Unauthorized")

    db = get_db()
    try:
        doc = await db.spaces_documents.find_one({"_id": ObjectId(doc_id)})
        if not doc:
            return {"success": False, "error": "Document not found."}

        # Get active language for descriptions
        user = await db.users.find_one({"username": session["username"]})
        user_settings = user.get("settings", {}) if user else {}
        lang = user_settings.get("language", "en")

        # Fetch registered predicates
        predicates_cursor = db.predicates.find({})
        predicates = await predicates_cursor.to_list(length=100)
        if not predicates:
            predicates = [
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

        labels = doc.get("labels", [])
        text = doc.get("text", "")
        model_id = doc.get("model", "gliner2-multi-v1")

        if not labels or not text:
            return {"success": True, "relations": []}

        # Load GLiNER2 model & build extraction schema
        from src.services.ner import get_model
        model = get_model(model_id)

        schema = model.create_schema()
        schema.entities(labels)

        # Build relations dictionary for GLiNER2
        relations_map = {}
        for pred in predicates:
            desc = pred.get(f"desc_{lang}") or pred.get("desc_en") or pred.get("desc_vi") or f"{pred.get('label_vi')} / {pred.get('label_en')}"
            relations_map[pred["name"]] = desc
        schema.relations(relations_map)

        # Extract
        results = model.extract(text, schema)
        relation_extraction = results.get("relation_extraction", {})

        extracted_relations = []
        for rel_name, triples in relation_extraction.items():
            # Match relation key with its label corresponding to active language
            pred_obj = next((p for p in predicates if p["name"] == rel_name), None)
            if pred_obj:
                pred_label = pred_obj.get(f"label_{lang}") or pred_obj.get("label_vi") or pred_obj.get("label_en") or rel_name
            else:
                pred_label = rel_name
            for s, o in triples:
                extracted_relations.append({
                    "subject": s.strip(),
                    "predicate": pred_label,
                    "object": o.strip()
                })

        # Save to DB, avoiding duplicate relations
        existing_relations = doc.get("relations", [])
        existing_set = {(r["subject"], r["predicate"], r["object"]) for r in existing_relations}

        new_to_add = []
        for r in extracted_relations:
            triple_tuple = (r["subject"], r["predicate"], r["object"])
            if triple_tuple not in existing_set:
                new_to_add.append(r)
                existing_set.add(triple_tuple)

        if new_to_add:
            await db.spaces_documents.update_one(
                {"_id": ObjectId(doc_id)},
                {"$push": {"relations": {"$each": new_to_add}}}
            )

        logger.info(f"GLiNER2 auto-extracted {len(new_to_add)} new relations for doc {doc_id}")
        
        # Return complete updated relations list
        updated_doc = await db.spaces_documents.find_one({"_id": ObjectId(doc_id)})
        return {"success": True, "relations": updated_doc.get("relations", [])}
    except Exception as e:
        logger.error(f"Failed to auto-extract relations for doc {doc_id}: {e}")
        return {"success": False, "error": str(e)}
