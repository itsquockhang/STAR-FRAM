import threading
from typing import Dict

from gliner import GLiNER

from config import DEFAULT_MODEL, SUPPORTED_MODELS

_models: Dict[str, GLiNER] = {}
_model_lock = threading.Lock()


def get_model(model_name: str) -> GLiNER:
  """Load or reuse a GLiNER model instance by name."""
  if model_name not in SUPPORTED_MODELS:
      # Fallback to default if someone passes a bad name here.
      model_name = DEFAULT_MODEL

  with _model_lock:
      model = _models.get(model_name)
      if model is None:
          model = GLiNER.from_pretrained(model_name)
          # _attn_implementation='flash_attention_2'
          _models[model_name] = model
      return model

