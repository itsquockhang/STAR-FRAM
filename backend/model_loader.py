import threading
from typing import Dict

import torch
from gliner import GLiNER

from config import (
    DEFAULT_MODEL,
    GLINER_QWEN_MAX_LENGTH,
    GLINER_QWEN_MODELS,
    SUPPORTED_MODELS,
)

_models: Dict[str, GLiNER] = {}
_model_lock = threading.Lock()


def get_model(model_name: str) -> GLiNER:
    """Load or reuse a GLiNER model instance by name."""
    if model_name not in SUPPORTED_MODELS:
        model_name = DEFAULT_MODEL

    with _model_lock:
        model = _models.get(model_name)
        if model is not None:
            return model

        if model_name in GLINER_QWEN_MODELS:
            try:
                model = GLiNER.from_pretrained(
                    model_name,
                    _attn_implementation="flash_attention_2",
                    max_length=GLINER_QWEN_MAX_LENGTH,
                )
                if torch.cuda.is_available():
                    model = model.to("cuda", dtype=torch.float16)
            except Exception:
                # Fallback without flash attention if unavailable (e.g. CPU or no flash_attn)
                model = GLiNER.from_pretrained(
                    model_name,
                    max_length=GLINER_QWEN_MAX_LENGTH,
                )
                if torch.cuda.is_available():
                    model = model.to("cuda", dtype=torch.float16)
        else:
            model = GLiNER.from_pretrained(model_name)

        _models[model_name] = model
        return model

