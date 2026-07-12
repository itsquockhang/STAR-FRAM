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


def load_model():
    """Load the GLiNER2 model into memory. Called once at app startup."""
    global _model
    if _model is not None:
        logger.info("NER model already loaded, skipping.")
        return
    device = get_device()
    device_type = device.type if hasattr(device, "type") else str(device)
    
    # Smart optimization settings based on device capability
    quantize = False
    compile_model = False
    
    if device_type == "cuda":
        quantize = True
        # compile_model = True
    elif device_type == "mps":
        quantize = True
        # compile_model = False  # torch.compile fails on MPS for GLiNER2 due to Metal shading compiler bugs
    else:  # cpu
        quantize = False  # CPU fp16 is slow or unsupported for many ops
        # compile_model = True  # compile works on CPU
        
    logger.info(f"Loading GLiNER2 model 'fastino/gliner2-multi-v1' on {device_type} (quantize={quantize}, compile={compile_model})...")
    
    _model = GLiNER2.from_pretrained(
        "fastino/gliner2-multi-v1",
        map_location=device,
        quantize=quantize,
        compile=compile_model
    )
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
    Uses extract_entities_long to support long document extraction.
    Returns the result dict from GLiNER2 with global spans and confidence scores.
    """
    model = get_model()
    result = model.extract_entities_long(
        text,
        labels,
        chunk_size=384,
        chunk_overlap=64,
        include_spans=True,
        include_confidence=True
    )
    return result


