import logging
from gliner2 import GLiNER2
from src.utils import get_device

logger = logging.getLogger("starfarm.ner")

# Module-level singleton
_model: GLiNER2 | None = None


def load_model():
    """Load the GLiNER2 model into memory. Called once at app startup."""
    global _model
    if _model is not None:
        logger.info("NER model already loaded, skipping.")
        return
    device = get_device()
    logger.info("Loading GLiNER2 model 'fastino/gliner2-multi-v1'...")
    _model = GLiNER2.from_pretrained("fastino/gliner2-multi-v1", device=device)
    logger.info("GLiNER2 model loaded successfully.")


def get_model() -> GLiNER2:
    """Return the loaded model singleton, loading it lazily if necessary."""
    global _model
    if _model is None:
        load_model()
    return _model


def extract_entities(text: str, labels: list[str]) -> dict:
    """
    Run NER extraction on the given text with the specified labels.
    Returns the raw result dict from GLiNER2.
    """
    model = get_model()
    result = model.extract_entities(text, labels)
    return result
