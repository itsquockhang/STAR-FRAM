from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

from openai import OpenAI

LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL", os.getenv("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1")
).rstrip("/")
LLM_API_KEY = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "lm-studio"))
LLM_MODEL = os.getenv("LLM_MODEL", "").strip()
LLM_TIMEOUT_SECS = float(os.getenv("LLM_TIMEOUT_SECS", "120"))
LLM_TRY_EXTRAS = os.getenv("LLM_TRY_EXTRAS", "0").lower() in ("1", "true", "yes", "y")


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


def extract_agri_relations(text: str) -> Tuple[Dict[str, Any], int]:
    s = (text or "").strip()
    if not s:
        return {"error": "Missing 'text'"}, 400

    system = (
        "You are an agricultural analysis assistant. The input is a Vietnamese text snippet. "
        "Your task is to extract the causal chain in agriculture: causes (factors), problems, "
        "solutions (actions), who applies the solutions (actors), and the outcomes/results."
        "\n\nReturn ONLY VALID JSON (no markdown, no explanations) with the schema:\n"
        "{\n"
        '  "summary": "1-2 short sentences in Vietnamese describing the main relationships",\n'
        '  "factors": [\n'
        '    {"name": "...", "type": "bệnh|sâu_hại|cỏ_dại|thời_tiết|đất|khác"}\n'
        "  ],\n"
        '  "targets": [\n'
        '    {"name": "...", "type": "cây_trồng|vật_nuôi|khác"}\n'
        "  ],\n"
        '  "actors": [\n'
        '    {"name": "...", "type": "nông_dân|hợp_tác_xã|khác"}\n'
        "  ],\n"
        '  "problems": ["..."],\n'
        '  "solutions": [\n'
        '    {"name": "...", "category": "canh_tác|hoá_học|sinh_học|cơ_giới|quản_lý|khác"}\n'
        "  ],\n"
        '  "impacts": [\n'
        '    {\n'
        '      "from": "factor|solution",\n'
        '      "to": "target|problem",\n'
        '      "effect": "tăng|giảm|gây_ra|giải_quyết|không_rõ",\n'
        '      "evidence": "short Vietnamese quote from the text"\n'
        "    }\n"
        "  ],\n"
        '  "outcome": {\n'
        '    "result": "tốt_hơn|xấu_hơn|không_rõ",\n'
        '    "reason": "một câu tiếng Việt giải thích vì sao có kết quả này"\n'
        "  }\n"
        "}\n"
        "If some fields cannot be inferred, use empty arrays or 'không_rõ'."
    )

    user = {"text": s}

    try:
        content = _post_chat_completions(
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

    # Parse JSON strictly; if model returns extra text, try best-effort extraction
    parsed: Dict[str, Any] | None = None
    try:
        parsed = json.loads(content)
    except Exception:
        try:
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(content[start : end + 1])
        except Exception:
            parsed = None

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

