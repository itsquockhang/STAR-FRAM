import logging
import datetime
from bson import ObjectId
from fastapi import APIRouter, Form, Cookie, Request, HTTPException, Query, status
from fastapi.responses import RedirectResponse, HTMLResponse
from src.core.database import get_db
from src.core.auth import get_session
from src.core.utils import build_highlighted_html
from src.core.templates import templates

logger = logging.getLogger("starfarm.routes.spaces")

def clean_dspy_output(text: str) -> str:
    """Removes DSPy internal prompt/completion tags like [[ ## completed ]], [[ ## field ]], markdown block ticks, etc."""
    if not text:
        return ""
    import re
    # Remove [[ ## ... ]] and [[ ... ]] tags
    text = re.sub(r'\[\[\s*##.*?\s*\]\]', '', str(text))
    text = re.sub(r'\[\[.*?\]\]', '', text)
    # Remove markdown code blocks
    text = re.sub(r'```[a-zA-Z]*', '', text)
    text = text.replace('```', '')
    return text.strip()

import difflib

def is_similar_triple(t1: tuple, t2: tuple, threshold: float = 0.75) -> bool:
    """
    Check if two triples (s1, p1, o1) and (s2, p2, o2) are semantically similar.
    Uses difflib SequenceMatcher fuzzy similarity and substring containment checks.
    """
    s1, p1, o1 = t1
    s2, p2, o2 = t2

    def str_sim(a: str, b: str) -> float:
        if a == b:
            return 1.0
        if not a or not b:
            return 0.0
        if (len(a) >= 3 and a in b) or (len(b) >= 3 and b in a):
            return 0.95
        return difflib.SequenceMatcher(None, a, b).ratio()

    # Predicate check: exact, slug, or similarity
    p1_slug = p1.replace(" ", "_")
    p2_slug = p2.replace(" ", "_")
    pred_match = (p1 == p2) or (p1_slug == p2_slug) or (str_sim(p1, p2) >= 0.7)

    if not pred_match:
        return False

    sub_sim = str_sim(s1, s2)
    obj_sim = str_sim(o1, o2)

    return sub_sim >= threshold and obj_sim >= threshold

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


@router.post("/spaces/{doc_id}/relations/delete-all")
async def delete_all_relations(
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
        res = await db.spaces_documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$set": {"relations": []}}
        )
        if res.matched_count == 0:
            return {"success": False, "error": "Document not found."}

        logger.info(f"All relations cleared from document {doc_id} by user {session['username']}")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to delete all relations from doc {doc_id}: {e}")
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

        import json
        schema_dict = {
            "entities": labels,
            "relations": relations_map,
            "schema_internal": schema.to_dict() if hasattr(schema, "to_dict") else (schema.__dict__ if hasattr(schema, "__dict__") else str(schema))
        }
        logger.info(f"[GLiNER2 Auto-Extract Debug] Schema Input JSON:\n{json.dumps(schema_dict, indent=2, ensure_ascii=False)}")

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


@router.post("/spaces/{doc_id}/relations/suggest")
async def suggest_relations(
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

        # Use predicate label based on user active language
        pred_labels = [p.get(f"label_{lang}") or p.get("label_vi") or p.get("label_en") for p in predicates]

        import dspy
        
        class GenerateKGRelations(dspy.Signature):
            """
            Extract relationship triples (Subject - Predicate - Object) from the document text based on the allowed predicates list.
            Format output as: Subject | Predicate | Object (one triple per line).
            Only extract relationships that are explicitly mentioned in the text.
            Do not include headers, numbering, bullets, or extra text. Output only the triples.
            """
            text = dspy.InputField(desc="The document text to analyze")
            predicates = dspy.InputField(desc="Comma-separated allowed relationship predicates list")
            relations = dspy.OutputField(desc="Suggested triples in the format 'Subject | Predicate | Object', one per line")

        # Configure DSPy LM
        from src.routes.settings import get_dspy_lm, LLMConnectionError
        lm = await get_dspy_lm()

        with dspy.context(lm=lm):
            predictor = dspy.Predict(GenerateKGRelations)
            result = predictor(
                text=doc.get("text", ""),
                predicates=", ".join(pred_labels)
            )

        existing_relations = doc.get("relations", [])
        existing_triples = []
        for r in existing_relations:
            s_c = (r.get("subject") or "").lower().strip()
            p_c = (r.get("predicate") or "").lower().strip()
            o_c = (r.get("object") or "").lower().strip()
            if s_c and p_c and o_c:
                existing_triples.append((s_c, p_c, o_c))

        registered_set = set()
        for p in predicates:
            if p.get("name"): registered_set.add(p["name"].lower().replace(" ", "_"))
            if p.get("label_en"): registered_set.add(p["label_en"].lower().strip())
            if p.get("label_vi"): registered_set.add(p["label_vi"].lower().strip())

        relations_text = result.relations
        suggestions = []
        if relations_text:
            for line in relations_text.split("\n"):
                line = line.strip()
                if not line or "|" not in line:
                    continue
                parts = line.split("|")
                if len(parts) >= 3:
                    sub = parts[0].strip()
                    pred = parts[1].strip()
                    obj = parts[2].strip()
                    
                    import re
                    sub = re.sub(r'^\d+[\.\)\-\s]+', '', sub).strip()
                    pred = re.sub(r'^\d+[\.\)\-\s]+', '', pred).strip()
                    obj = re.sub(r'^\d+[\.\)\-\s]+', '', obj).strip()
                    
                    if not sub or not pred or not obj:
                        continue

                    sub_clean = sub.lower().strip()
                    pred_clean = pred.lower().strip()
                    obj_clean = obj.lower().strip()
                    target_t = (sub_clean, pred_clean, obj_clean)

                    pred_slug = pred_clean.replace(" ", "_")
                    in_settings = (pred_clean in registered_set) or (pred_slug in registered_set)
                    already_exists = any(is_similar_triple(target_t, ex_t, threshold=0.75) for ex_t in existing_triples)

                    # Prevent duplicate suggestions in output
                    if not any(s["subject"] == sub and s["predicate"] == pred and s["object"] == obj for s in suggestions):
                        suggestions.append({
                            "subject": sub,
                            "predicate": pred,
                            "object": obj,
                            "in_settings": in_settings,
                            "already_exists": already_exists
                        })

        logger.info(f"AI suggested {len(suggestions)} relations for doc {doc_id} using model '{lm.model}'")
        return {"success": True, "suggestions": suggestions}
    except LLMConnectionError as e:
        logger.error(f"Failed to suggest relations for doc {doc_id}: LLM connection error: {e}")
        return {"success": False, "error": f"LLM connection error: {e}"}
    except Exception as e:
        logger.error(f"Failed to suggest relations for doc {doc_id}: {e}")
        return {"success": False, "error": str(e)}


@router.post("/spaces/{doc_id}/prai/extract-gliner")
async def extract_prai_gliner(
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

        text = doc.get("text", "")
        model_id = doc.get("model", "gliner2-multi-v1")
        if not text:
            return {"success": False, "error": "Document contains no text."}

        from src.services.ner import extract_entities
        prai_schema = {
            "Problem": "Agricultural problems, crop diseases, pest infestations, physiological disorders, climate stresses, or weeds",
            "Practice": "Agricultural practices, farming techniques, treatments, application of pesticides/fertilizers, irrigation, or management actions",
            "Actor": "Farmers, agricultural experts, traders, scientists, or human actors",
            "Impact": "Impacts, outcomes, yield losses, environmental consequences, or growth benefits"
        }

        raw_results = extract_entities(text, prai_schema, model_id=model_id)
        entities_map = raw_results.get("entities", {})
        
        # Helper to format entity list cleanly
        def format_entities(items):
            result = []
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        text_val = item.get("text", "")
                        conf_val = item.get("confidence")
                        if text_val:
                            result.append({"text": text_val, "confidence": round(conf_val, 2) if conf_val is not None else None})
                    elif isinstance(item, str) and item.strip():
                        result.append({"text": item.strip(), "confidence": None})
            return result

        prai_results = {
            "Problem": format_entities(entities_map.get("Problem", [])),
            "Practice": format_entities(entities_map.get("Practice", [])),
            "Actor": format_entities(entities_map.get("Actor", [])),
            "Impact": format_entities(entities_map.get("Impact", []))
        }

        await db.spaces_documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$set": {"prai.gliner": prai_results}}
        )

        logger.info(f"GLiNER2 extracted PRAI items for document {doc_id}")
        return {"success": True, "prai_gliner": prai_results}
    except Exception as e:
        logger.error(f"GLiNER2 PRAI extraction failed for doc {doc_id}: {e}")
        return {"success": False, "error": str(e)}


@router.post("/spaces/{doc_id}/prai/extract-ai")
async def extract_prai_ai(
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

        text = doc.get("text", "")
        if not text:
            return {"success": False, "error": "Document contains no text."}

        import dspy
        from src.routes.settings import get_dspy_lm, LLMConnectionError

        class ExtractPRAIFramework(dspy.Signature):
            """
            Extract structured agricultural knowledge units according to the {P, R, A, I} framework based ONLY on facts in the document text:
            - P (Problem): Crop diseases, pests, weeds, climate stresses, physiological disorders (e.g. leaf yellowing, pest infestation).
            - R (Practice): Actionable practices, treatments, pesticide/fertilizer applications, techniques (e.g. pesticide spraying, pruning).
            - A (Actor): Explicit or implicit human actors, farmers, experts, institutions (e.g. farmer, agricultural scientist).
            - I (Impact): Outcomes, yield loss, crop stress, economic or environmental impacts (e.g. yield reduction, crop stress).
            
            STRICT ANTI-HALLUCINATION RULE: Rely ONLY on the document text. Never invent or hallucinate outside province names, locations, or actors not present in the text!
            Format output as clean items separated by pipes or commas.
            """
            text = dspy.InputField(desc="The document text to analyze")
            problems = dspy.OutputField(desc="List of extracted Problems (P), separated by pipes or commas")
            practices = dspy.OutputField(desc="List of extracted Practices (R), separated by pipes or commas")
            actors = dspy.OutputField(desc="List of extracted Actors (A), explicit or implicit, separated by pipes or commas")
            impacts = dspy.OutputField(desc="List of extracted Impacts (I), separated by pipes or commas")

        lm = await get_dspy_lm()
        with dspy.context(lm=lm):
            predictor = dspy.Predict(ExtractPRAIFramework)
            res = predictor(text=text)

        logger.info(f"=== [DSPy Raw Output - Extract PRAI] ===\nProblems: {getattr(res, 'problems', '')}\nPractices: {getattr(res, 'practices', '')}\nActors: {getattr(res, 'actors', '')}\nImpacts: {getattr(res, 'impacts', '')}\n=========================================")

        def parse_items(raw_str):
            if not raw_str:
                return []
            import re
            cleaned_raw = clean_dspy_output(str(raw_str))
            parts = re.split(r'[\|\n,]', cleaned_raw)
            items = []
            for p in parts:
                cleaned = re.sub(r'^\d+[\.\)\-\s]+', '', p).strip()
                cleaned = clean_dspy_output(cleaned)
                if cleaned and cleaned.lower() not in ["empty", "none", "n/a", "k/a", "implicit", "completed", "none."]:
                    if cleaned not in items:
                        items.append(cleaned)
            return items

        prai_ai = {
            "Problem": parse_items(res.problems),
            "Practice": parse_items(res.practices),
            "Actor": parse_items(res.actors),
            "Impact": parse_items(res.impacts)
        }

        await db.spaces_documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$set": {"prai.ai": prai_ai}}
        )

        logger.info(f"AI (DSPy) extracted PRAI items for document {doc_id} using model '{lm.model}'")
        return {"success": True, "prai_ai": prai_ai}
    except LLMConnectionError as e:
        logger.error(f"AI PRAI extraction failed for doc {doc_id}: LLM connection error: {e}")
        return {"success": False, "error": f"LLM connection error: {e}"}
    except Exception as e:
        logger.error(f"AI PRAI extraction failed for doc {doc_id}: {e}")
        return {"success": False, "error": str(e)}


@router.post("/spaces/{doc_id}/prai/clear")
async def clear_prai(
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
        await db.spaces_documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$unset": {"prai": ""}}
        )
        logger.info(f"PRAI extractions cleared for document {doc_id}")
        return {"success": True}
    except Exception as e:
        logger.error(f"Failed to clear PRAI for doc {doc_id}: {e}")
        return {"success": False, "error": str(e)}


def detect_text_language(text: str) -> str:
    """Detect if document text is primarily English ('en') or Vietnamese ('vi')."""
    if not text:
        return "vi"
    import re
    vi_accent_pattern = re.compile(r'[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệđìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆĐÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴ]')
    vi_matches = len(vi_accent_pattern.findall(text))
    if vi_matches >= 2:
        return "vi"
    
    words = [w.lower() for w in re.findall(r'\b[a-zA-Z]+\b', text)]
    if not words:
        return "vi"
    
    en_stop_words = {"the", "is", "and", "in", "of", "to", "for", "with", "on", "at", "by", "from", "that", "this", "are", "was", "be", "has", "have"}
    en_count = sum(1 for w in words if w in en_stop_words)
    if en_count >= 2:
        return "en"
    
    return "vi"


@router.post("/spaces/{doc_id}/prai/synthesize-sentences")
async def synthesize_prai_sentences(
    doc_id: str,
    lang: str | None = Query(default=None),
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

        text = doc.get("text", "")
        if not text:
            return {"success": False, "error": "Document contains no text."}

        # Auto-detect language if not explicitly passed
        if not lang or lang.strip().lower() not in ["vi", "en"]:
            lang = detect_text_language(text)

        relations = doc.get("relations", [])
        prai_data = doc.get("prai", {})

        import dspy
        from src.routes.settings import get_dspy_lm, LLMConnectionError

        lang_code = lang.lower().strip()
        if lang_code == "en":
            class SynthesizePRAISentencesEN(dspy.Signature):
                """
                Synthesize structured agricultural PRAI narrative sentences in English based ONLY on the provided document text, extracted PRAI entities {Problem, Practice, Actor, Impact}, and Knowledge Graph triples.
                
                CRITICAL REQUIREMENTS:
                1. STRICT FAITHFULNESS & GROUNDING: Rely ONLY on facts, entities, locations, and organizations present in the provided input text. NEVER introduce or hallucinate outside location names, province names (e.g., specific province names not in text), actors, or organizations!
                2. Output strictly 1 structured line per distinct Problem/Situation using the exact format:
                   Actor: <A> | Problem: <P> | Practice: <R> | Impact: <I> | Sentence: <Sentence text>
                3. Write fluent and natural sentences connecting A, P, R, I without repetitive rigid templates.
                4. VERBATIM RULE: The exact words specified in <A>, <P>, <R>, <I> MUST appear verbatim inside <Sentence text> so they can be highlighted accurately.
                
                Example output format:
                Actor: Rice farmers | Problem: Brown planthopper | Practice: Biological spraying | Impact: Restored crop growth | Sentence: To control brown planthopper, rice farmers applied biological spraying to achieve restored crop growth.
                """
                text = dspy.InputField(desc="Document text context")
                prai_entities = dspy.InputField(desc="Extracted PRAI entities (P, R, A, I)")
                kg_relations = dspy.InputField(desc="Knowledge Graph triples (Subject | Predicate | Object)")
                sentences = dspy.OutputField(desc="Synthesized English PRAI narrative lines connecting A, P, R, I")

            SigClass = SynthesizePRAISentencesEN
        else:
            class SynthesizePRAISentencesVI(dspy.Signature):
                """
                Synthesize structured agricultural PRAI narrative sentences in Vietnamese based ONLY on the provided document text, extracted PRAI entities {Problem, Practice, Actor, Impact}, and Knowledge Graph triples.
                
                YÊU CẦU BẮT BUỘC & CHẶT CHẼ:
                1. QUY TẮC TRÁNH ẢO GIÁC (ANTI-HALLUCINATION): TUYỆT ĐỐI CHỈ sử dụng thông tin, tác nhân, địa danh, tỉnh thành có sẵn trong văn bản bài viết. KHÔNG BAO GIỜ tự bịa thêm các tên tỉnh thành (như "tỉnh Trà Vinh"), địa danh hoặc tổ chức không có trong văn bản!
                2. Xuất chính xác 1 dòng cấu trúc cho MỖI Vấn đề (Problem) theo đúng định dạng:
                   Actor: <A> | Problem: <P> | Practice: <R> | Impact: <I> | Sentence: <Nội dung câu kịch bản>
                3. Câu kịch bản diễn đạt tự nhiên, trôi chảy và linh hoạt. Không bắt buộc theo một trật tự cố định.
                4. QUY TẮC NGUYÊN VĂN: Các từ/cụm từ chính xác được ghi ở <A>, <P>, <R>, <I> BẮT BUỘC phải xuất hiện nguyên văn (verbatim) trong <Nội dung câu kịch bản> để hệ thống tô màu chính xác cả 4 yếu tố.
                
                Example output format:
                Actor: Nông dân | Problem: Bệnh rầy nâu | Practice: Phun thuốc sinh học | Impact: Khôi phục sinh trưởng cây trồng | Sentence: Nhằm đối phó với bệnh rầy nâu, nông dân đã chủ động phun thuốc sinh học giúp khôi phục sinh trưởng cây trồng.
                """
                text = dspy.InputField(desc="Document text context")
                prai_entities = dspy.InputField(desc="Extracted PRAI entities (P, R, A, I)")
                kg_relations = dspy.InputField(desc="Knowledge Graph triples (Subject | Predicate | Object)")
                sentences = dspy.OutputField(desc="Synthesized Vietnamese PRAI narrative lines connecting A, P, R, I")

            SigClass = SynthesizePRAISentencesVI

        # Format inputs for LLM
        kg_formatted = "\n".join([f"{r.get('subject')} | {r.get('predicate')} | {r.get('object')}" for r in relations]) if relations else "None"
        
        gliner_prai = prai_data.get("gliner", {})
        ai_prai = prai_data.get("ai", {})
        
        prai_summary = []
        for k in ["Problem", "Practice", "Actor", "Impact"]:
            g_items = [i.get("text") if isinstance(i, dict) else i for i in gliner_prai.get(k, [])]
            a_items = ai_prai.get(k, [])
            combined = list(dict.fromkeys([x for x in (g_items + a_items) if x]))
            if combined:
                prai_summary.append(f"{k}s: {', '.join(combined)}")
        
        prai_input_str = "\n".join(prai_summary) if prai_summary else "None"

        lm = await get_dspy_lm()
        with dspy.context(lm=lm):
            predictor = dspy.Predict(SigClass)
            res = predictor(
                text=text,
                prai_entities=prai_input_str,
                kg_relations=kg_formatted
            )

        logger.info(f"=== [DSPy Raw Output - Synthesize Sentences ({lang_code})] ===\n{getattr(res, 'sentences', '')}\n=========================================================")

        output_text = clean_dspy_output(res.sentences or "")
        parsed_sentences = []
        
        if output_text:
            import re
            lines = output_text.split("\n")
            for line in lines:
                line = clean_dspy_output(line.strip())
                if not line or ("completed" in line.lower() and len(line) < 25):
                    continue
                
                if "|" in line and "Sentence:" in line:
                    parts = line.split("|")
                    item = {"actor": "", "problem": "", "practice": "", "impact": "", "sentence": "", "lang": lang_code}
                    for p in parts:
                        if ":" in p:
                            k, v = p.split(":", 1)
                            k = k.strip().lower()
                            v = clean_dspy_output(v.strip())
                            if "actor" in k: item["actor"] = v
                            elif "problem" in k: item["problem"] = v
                            elif "practice" in k: item["practice"] = v
                            elif "impact" in k: item["impact"] = v
                            elif "sentence" in k: item["sentence"] = v
                    if item["sentence"]:
                        item["sentence"] = clean_dspy_output(item["sentence"])
                        parsed_sentences.append(item)
                else:
                    clean_line = re.sub(r'^\d+[\.\)\-\s]+', '', line).strip()
                    clean_line = clean_dspy_output(clean_line)
                    if clean_line and len(clean_line) > 10 and not clean_line.lower().startswith("completed"):
                        parsed_sentences.append({"sentence": clean_line, "lang": lang_code})

        await db.spaces_documents.update_one(
            {"_id": ObjectId(doc_id)},
            {"$set": {"prai.sentences": parsed_sentences}}
        )

        logger.info(f"Synthesized {len(parsed_sentences)} PRAI narrative sentences ({lang_code}) for doc {doc_id}")
        return {"success": True, "sentences": parsed_sentences}
    except LLMConnectionError as e:
        logger.error(f"Failed to synthesize PRAI sentences for doc {doc_id}: LLM connection error: {e}")
        return {"success": False, "error": f"LLM connection error: {e}"}
    except Exception as e:
        logger.error(f"Failed to synthesize PRAI sentences for doc {doc_id}: {e}")
        return {"success": False, "error": str(e)}
