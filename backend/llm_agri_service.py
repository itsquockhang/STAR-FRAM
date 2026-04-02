from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)

LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL", os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1")
).rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "lm-studio"))
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_TIMEOUT_SECS = float(os.getenv("LLM_TIMEOUT_SECS", "120"))
LLM_TRY_EXTRAS = os.getenv("LLM_TRY_EXTRAS", "0").lower() in ("1", "true", "yes", "y")

# Agri relations: structured output (OpenAI json_schema / json_object). Fallback if unsupported.
LLM_AGRI_STRUCTURED = os.getenv("LLM_AGRI_STRUCTURED", "0").lower() in ("1", "true", "yes", "y")
# OpenAI strict JSON schema; many local servers need false or skip schema entirely.
LLM_AGRI_JSON_STRICT = os.getenv("LLM_AGRI_JSON_STRICT", "0").lower() in ("1", "true", "yes", "y")


def _agri_json_schema_definition() -> Dict[str, Any]:
  """JSON Schema for agri relations (OpenAI structured outputs / compatible APIs)."""
  factor_item = {
      "type": "object",
      "properties": {
          "name": {"type": "string"},
          "type": {
              "type": "string",
              "enum": ["disease", "pest", "weed", "weather", "soil", "other"],
          },
      },
      "required": ["name", "type"],
      "additionalProperties": False,
  }
  target_item = {
      "type": "object",
      "properties": {
          "name": {"type": "string"},
          "type": {"type": "string", "enum": ["crop", "livestock", "other"]},
      },
      "required": ["name", "type"],
      "additionalProperties": False,
  }
  actor_item = {
      "type": "object",
      "properties": {
          "name": {"type": "string"},
          "type": {"type": "string", "enum": ["farmer", "cooperative", "other"]},
      },
      "required": ["name", "type"],
      "additionalProperties": False,
  }
  problem_item = {
      "type": "object",
      "properties": {
          "name": {"type": "string"},
          "type": {
              "type": "string",
              "enum": [
                  "disease",
                  "pest",
                  "weed",
                  "weather",
                  "soil",
                  "management",
                  "economic",
                  "social",
                  "other",
              ],
          },
      },
      "required": ["name", "type"],
      "additionalProperties": False,
  }
  solution_item = {
      "type": "object",
      "properties": {
          "name": {"type": "string"},
          "category": {
              "type": "string",
              "enum": [
                  "cultivation",
                  "chemical",
                  "biological",
                  "mechanical",
                  "management",
                  "other",
              ],
          },
      },
      "required": ["name", "category"],
      "additionalProperties": False,
  }
  impact_item = {
      "type": "object",
      "properties": {
          "from": {"type": "string"},
          "to": {"type": "string"},
          "effect": {
              "type": "string",
              "enum": ["increase", "decrease", "cause", "resolve", "unclear"],
          },
          "evidence": {"type": "string"},
      },
      "required": ["from", "to", "effect", "evidence"],
      "additionalProperties": False,
  }
  outcome = {
      "type": "object",
      "properties": {
          "result": {"type": "string", "enum": ["better", "worse", "unclear"]},
          "reason": {"type": "string"},
      },
      "required": ["result", "reason"],
      "additionalProperties": False,
  }
  return {
      "type": "object",
      "properties": {
          "summary": {"type": "string"},
          "factors": {"type": "array", "items": factor_item},
          "targets": {"type": "array", "items": target_item},
          "actors": {"type": "array", "items": actor_item},
          "problems": {"type": "array", "items": problem_item},
          "solutions": {"type": "array", "items": solution_item},
          "impacts": {"type": "array", "items": impact_item},
          "outcome": outcome,
      },
      "required": [
          "summary",
          "factors",
          "targets",
          "actors",
          "problems",
          "solutions",
          "impacts",
          "outcome",
      ],
      "additionalProperties": False,
  }


def _agri_response_format_json_schema() -> Dict[str, Any]:
  body: Dict[str, Any] = {
      "name": "agri_relations_analysis",
      "schema": _agri_json_schema_definition(),
  }
  if LLM_AGRI_JSON_STRICT:
      body["strict"] = True
  return {"type": "json_schema", "json_schema": body}


OCR_PROMPT = (
    "Perform OCR on this image. Output the full transcription as valid Markdown only.\n\n"
    "Rules:\n"
    "- Use Markdown structure: headings (# / ##), bullet or numbered lists, blockquotes where appropriate.\n"
    "- Tables: use GitHub-flavored Markdown pipe tables (| col | col |) when the layout is tabular.\n"
    "- Preserve reading order (top to bottom, columns left to right). Keep line breaks meaningful.\n"
    "- Bold (**text**) or italics (*text*) only when emphasis is clear from the document.\n"
    "- Do not wrap the answer in a markdown code fence. Do not add preambles or commentary—output only the Markdown body."
)


def _unwrap_markdown_code_fence(text: str) -> str:
    """If the model wraps the whole reply in ``` or ```markdown, strip the outer fence."""
    t = (text or "").strip()
    if not t.startswith("```"):
        return t
    lines = t.split("\n")
    if len(lines) < 2:
        return t
    inner = lines[1:]
    if inner and inner[-1].strip() == "```":
        inner = inner[:-1]
    return "\n".join(inner).strip()


def _parse_agri_llm_json(content: str) -> Optional[Dict[str, Any]]:
    """
    Parse the agri-relations JSON from LLM output.

    Handles: markdown ```json fences, prose before/after the object, JSON returned as a
    quoted string (double-encoded), and finding the first complete {...} via JSONDecoder.
    """
    s = (content or "").strip()
    if not s:
        return None
    if s.startswith("\ufeff"):
        s = s.lstrip("\ufeff")

    # Unwrap one or two layers of ``` / ```json fences
    for _ in range(3):
        if not s.startswith("```"):
            break
        s = _unwrap_markdown_code_fence(s)

    # Drop common preambles: keep from first '{' (model sometimes adds "Here is the JSON:")
    brace0 = s.find("{")
    if brace0 > 0:
        s = s[brace0:]

    dec = json.JSONDecoder()

    def _loads(v: str) -> Any:
        return json.loads(v)

    # 1) Parse whole buffer: object, or JSON string that contains JSON (common LLM mistake)
    try:
        obj = _loads(s)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, str):
            t = obj.strip()
            for _ in range(4):
                if not t.startswith("{"):
                    break
                try:
                    inner = _loads(t)
                    if isinstance(inner, dict):
                        return inner
                    if isinstance(inner, str):
                        t = inner.strip()
                        continue
                    break
                except Exception:
                    break
    except Exception:
        pass

    # 2) First complete {...} via JSONDecoder (ignores trailing prose; correct brace matching)
    tries = 0
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        tries += 1
        if tries > 200:
            break
        try:
            obj, _end = dec.raw_decode(s, i)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue

    # 3) Legacy: substring between first '{' and last '}' (may fail on braces in strings)
    try:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            obj = _loads(s[start : end + 1])
            if isinstance(obj, dict):
                return obj
    except Exception:
        pass

    return None


def _normalize_base_url(base_url: str) -> str:
    u = (base_url or "").rstrip("/")
    if not u.endswith("/v1"):
        u = f"{u}/v1"
    return u


def _resolve_model_id(client: OpenAI) -> str:
    if LLM_MODEL:
        return LLM_MODEL
    models = client.models.list()
    if getattr(models, "data", None):
        return models.data[0].id
    return "Qwen/Qwen3.5-0.8B"


def _post_chat_completions(messages: List[Dict[str, Any]]) -> str:
    client = OpenAI(
        api_key=LLM_API_KEY,
        base_url=_normalize_base_url(LLM_BASE_URL),
        timeout=LLM_TIMEOUT_SECS,
    )
    model_id = _resolve_model_id(client)

    def _call(with_extras: bool) -> str:
        kwargs: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.4,
            "top_p": 0.95,
        }

        # Optional knobs (often rejected by LM Studio / transformers serve)
        if with_extras:
            kwargs["presence_penalty"] = 0.0
            kwargs["extra_body"] = {"top_k": 20, "do_sample": True}

        resp = client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()

    if LLM_TRY_EXTRAS:
        try:
            return _call(with_extras=True)
        except Exception:
            return _call(with_extras=False)
    return _call(with_extras=False)


def _post_chat_completions_agri(messages: List[Dict[str, Any]]) -> str:
    """
    Chat completion for agri relations. Prefer OpenAI-style structured output (json_schema),
    then json_object, then plain text (legacy).
    """
    client = OpenAI(
        api_key=LLM_API_KEY,
        base_url=_normalize_base_url(LLM_BASE_URL),
        timeout=LLM_TIMEOUT_SECS,
    )
    model_id = _resolve_model_id(client)

    def _call_one(response_format: Optional[Dict[str, Any]]) -> str:
        kwargs: Dict[str, Any] = {
            "model": model_id,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.4,
            "top_p": 0.95,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format

        def _invoke(kw: Dict[str, Any]) -> str:
            resp = client.chat.completions.create(**kw)
            return (resp.choices[0].message.content or "").strip()

        if LLM_TRY_EXTRAS:
            try:
                kw2 = dict(kwargs)
                kw2["presence_penalty"] = 0.0
                kw2["extra_body"] = {"top_k": 20, "do_sample": True}
                return _invoke(kw2)
            except Exception:
                return _invoke(kwargs)
        return _invoke(kwargs)

    if not LLM_AGRI_STRUCTURED:
        return _call_one(response_format=None)

    attempts: List[Tuple[str, Optional[Dict[str, Any]]]] = [
        ("json_schema", _agri_response_format_json_schema()),
        ("json_object", {"type": "json_object"}),
        ("plain", None),
    ]
    last_err: Optional[Exception] = None
    for label, rf in attempts:
        try:
            return _call_one(response_format=rf)
        except Exception as e:
            last_err = e
            logger.info(
                "Agri LLM response_format=%s failed: %s — trying next fallback",
                label,
                e,
            )
            continue
    if last_err:
        raise last_err
    return ""


def ocr_image_base64(image_base64: str, mime: str = "image/jpeg") -> str:
    """
    Send a single image (base64) to the LLM for OCR.
    Returns extracted content as Markdown (headings, lists, pipe tables, etc.).
    Uses the same LLM_BASE_URL / LLM_MODEL as agri relations.
    """
    if not image_base64:
        return ""
    url = f"data:{mime};base64,{image_base64}"
    content: List[Dict[str, Any]] = [
        {"type": "image_url", "image_url": {"url": url}},
        {"type": "text", "text": OCR_PROMPT},
    ]
    messages = [{"role": "user", "content": content}]
    client = OpenAI(
        api_key=LLM_API_KEY,
        base_url=_normalize_base_url(LLM_BASE_URL),
        timeout=LLM_TIMEOUT_SECS,
    )
    model_id = _resolve_model_id(client)
    kwargs: Dict[str, Any] = {
        "model": model_id,
        "messages": messages,
        "max_tokens": 4096,
        "temperature": 0,
    }
    resp = client.chat.completions.create(**kwargs)
    raw = (resp.choices[0].message.content or "").strip()
    return _unwrap_markdown_code_fence(raw)


def extract_agri_relations(text: str) -> Tuple[Dict[str, Any], int]:
    s = (text or "").strip()
    if not s:
        return {"error": "Missing 'text'"}, 400

    if LLM_AGRI_STRUCTURED:
        system = (
            "You are an agricultural analysis assistant. The user message is JSON with a single field "
            '"text" containing text to analyze.\n\n'
            "Extract the causal chain in agriculture: factors, targets, actors, problems, solutions, impacts, outcome.\n\n"
            "IMPORTANT: Write summary, reasons, evidence, and free-text fields in the SAME LANGUAGE as the input text "
            "(English if the input is English, Vietnamese if Vietnamese).\n\n"
            "If something cannot be inferred, use empty arrays where allowed, or the enum value 'unclear' / 'other' as appropriate."
        )
    else:
        system = (
            "You are an agricultural analysis assistant. Analyze the input text and extract the causal chain in agriculture: "
            "causes (factors), problems, solutions (actions), actors, and outcomes.\n\n"
            "IMPORTANT: Respond in the SAME LANGUAGE as the input text (English if input is English, Vietnamese if input is Vietnamese).\n\n"
            "Return ONLY VALID JSON (no markdown, no explanations) with this schema:\n"
            "{\n"
            '  "summary": "1-2 sentences describing the main relationships",\n'
            '  "factors": [\n'
            '    {"name": "...", "type": "disease|pest|weed|weather|soil|other"}\n'
            "  ],\n"
            '  "targets": [\n'
            '    {"name": "...", "type": "crop|livestock|other"}\n'
            "  ],\n"
            '  "actors": [\n'
            '    {"name": "...", "type": "farmer|cooperative|other"}\n'
            "  ],\n"
            '  "problems": [{"name": "...", "type": "..."}],\n'
            '  "solutions": [\n'
            '    {"name": "...", "category": "cultivation|chemical|biological|mechanical|management|other"}\n'
            "  ],\n"
            '  "impacts": [\n'
            '    {\n'
            '      "from": "factor|solution",\n'
            '      "to": "target|problem",\n'
            '      "effect": "increase|decrease|cause|resolve|unclear",\n'
            '      "evidence": "relevant quote from the text"\n'
            "    }\n"
            "  ],\n"
            '  "outcome": {\n'
            '    "result": "better|worse|unclear",\n'
            '    "reason": "explanation based on the text"\n'
            "  }\n"
            "}\n"
            "If fields cannot be inferred, use empty arrays or 'unclear'."
        )

    user = {"text": s}

    try:
        content = _post_chat_completions_agri(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ]
        )
    except Exception as e:
        return {
            "error": f"LLM request failed: {e!s}",
            "llm_base_url": _normalize_base_url(LLM_BASE_URL),
            "llm_model": LLM_MODEL or "(auto)",
        }, 502

    parsed = _parse_agri_llm_json(content)

    if parsed is None:
        return {
            "error": "LLM returned non-JSON content (temporary).",
            "raw": content[:4000],
            "llm_base_url": LLM_BASE_URL,
            "llm_model": LLM_MODEL,
        }, 502

    return {
        "analysis": parsed,
        "llm_base_url": LLM_BASE_URL,
        "llm_model": LLM_MODEL,
    }, 200

