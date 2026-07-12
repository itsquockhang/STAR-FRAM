import logging
from gliner2 import GLiNER2
from src.core.utils import get_device
from torch.utils.data import DataLoader as OrigDataLoader
from tqdm import tqdm
import gliner2.inference.engine

logger = logging.getLogger("starfarm.ner")

# Monkeypatch the DataLoader in gliner2.inference.engine to automatically wrap batches in a tqdm progress bar
class TqdmDataLoader(OrigDataLoader):
    def __iter__(self):
        # We only show progress bar if there are multiple batches to extract
        if len(self) > 1:
            return iter(tqdm(super().__iter__(), total=len(self), desc="Extracting NER batches", leave=False))
        return super().__iter__()

gliner2.inference.engine.DataLoader = TqdmDataLoader

# Module-level singleton
_model: GLiNER2 | None = None
_model_name: str | None = None

AVAILABLE_MODELS = {
    "gliner2-multi-v1": {
        "repo_id": "fastino/gliner2-multi-v1",
        "name": "GLiNER2 Multilingual (fastino/gliner2-multi-v1)"
    },
    "gliner2-base-v1": {
        "repo_id": "fastino/gliner2-base-v1",
        "name": "GLiNER2 Base English (fastino/gliner2-base-v1)"
    }
}


def load_model(model_id: str = "gliner2-multi-v1"):
    """Load the GLiNER2 model into memory. Unloads previous model if model_id changes."""
    global _model, _model_name
    if _model is not None and _model_name == model_id:
        logger.info(f"NER model {model_id} already loaded, skipping.")
        return
        
    if _model is not None:
        logger.info(f"Unloading previous NER model: {_model_name}")
        del _model
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        elif hasattr(torch, "mps") and torch.mps.is_available():
            torch.mps.empty_cache()
        _model = None
        _model_name = None

    device = get_device()
    device_type = device.type if hasattr(device, "type") else str(device)
    
    # Smart optimization settings based on device capability
    quantize = False
    compile_model = False
    
    if device_type == "cuda":
        quantize = True
    elif device_type == "mps":
        quantize = True
    else:  # cpu
        quantize = False
        
    repo_id = AVAILABLE_MODELS.get(model_id, AVAILABLE_MODELS["gliner2-multi-v1"])["repo_id"]
    logger.info(f"Loading GLiNER2 model '{repo_id}' on {device_type} (quantize={quantize}, compile={compile_model})...")
    
    _model = GLiNER2.from_pretrained(
        repo_id,
        map_location=device,
        quantize=quantize,
        compile=compile_model
    )
    _model_name = model_id
    logger.info(f"GLiNER2 model '{model_id}' loaded successfully.")


def get_model(model_id: str = "gliner2-multi-v1") -> GLiNER2:
    """Return the loaded model singleton, loading/switching if necessary."""
    global _model, _model_name
    if _model is None or _model_name != model_id:
        load_model(model_id)
    return _model


def extract_entities(text: str, labels: list[str] | dict[str, str], model_id: str = "gliner2-multi-v1") -> dict:
    """
    Run NER extraction on the given text with the specified labels.
    Uses extract_entities_long to support long document extraction.
    Returns the result dict from GLiNER2 with global spans and confidence scores.
    """
    model = get_model(model_id)
    result = model.extract_entities_long(
        text,
        labels,
        # chunk_size=384,
        # chunk_overlap=64,
        chunk_size=512,
        chunk_overlap=96,
        include_spans=True,
        include_confidence=True
    )
    return result


