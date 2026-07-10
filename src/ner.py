import logging
from gliner2 import GLiNER2
from src.utils import get_device

logger = logging.getLogger("starfarm.ner")

# Custom implementation of extract_entities_long to support long document extraction.
def _extract_entities_long(
    self: GLiNER2,
    long_text: str,
    labels: list[str],
    chunk_size: int = 384,
    chunk_overlap: int = 64,
    include_spans: bool = True,
    include_confidence: bool = True,
    threshold: float = 0.5,
    **kwargs
) -> dict:
    """
    Extract entities from a long document by breaking it into chunks,
    running predictions, remapping spans globally, and deduplicating overlaps.
    """
    tokenizer = self.processor.tokenizer
    tokens = tokenizer(long_text, return_offsets_mapping=True, add_special_tokens=False)
    input_ids = tokens["input_ids"]
    offsets = tokens["offset_mapping"]
    num_tokens = len(input_ids)
    if num_tokens == 0:
        return {"entities": {}}

    chunks = []
    start_idx = 0
    step = chunk_size - chunk_overlap
    if step <= 0:
        step = chunk_size // 2
        if step <= 0:
            step = 1

    while start_idx < num_tokens:
        end_idx = min(start_idx + chunk_size, num_tokens)
        chunk_start_char = offsets[start_idx][0]
        chunk_end_char = offsets[end_idx - 1][1]
        chunk_text = long_text[chunk_start_char:chunk_end_char]
        
        chunks.append({
            "text": chunk_text,
            "char_offset": chunk_start_char
        })
        
        if end_idx == num_tokens:
            break
        start_idx += step

    from tqdm import tqdm

    chunk_texts = [c["text"] for c in chunks]
    batch_size = kwargs.pop("batch_size", 8)
    
    batch_results = []
    # Process chunks in batches with tqdm progress bar
    for i in tqdm(range(0, len(chunk_texts), batch_size), desc="Extracting NER chunks"):
        batch = chunk_texts[i:i + batch_size]
        batch_res = self.batch_extract_entities(
            batch,
            labels,
            batch_size=batch_size,
            threshold=threshold,
            format_results=True,
            include_confidence=include_confidence,
            include_spans=include_spans,
            **kwargs
        )
        batch_results.extend(batch_res)

    all_entities = {}
    for chunk, res in zip(chunks, batch_results):
        char_offset = chunk["char_offset"]
        chunk_entities = res.get("entities", {})
        
        for label, entities in chunk_entities.items():
            if label not in all_entities:
                all_entities[label] = []
            for ent in entities:
                if include_spans:
                    global_start = ent["start"] + char_offset
                    global_end = ent["end"] + char_offset
                    reconstructed = {
                        "text": ent["text"],
                        "start": global_start,
                        "end": global_end
                    }
                    if include_confidence:
                        reconstructed["confidence"] = ent.get("confidence", 1.0)
                    all_entities[label].append(reconstructed)
                else:
                    if include_confidence:
                        all_entities[label].append(ent)
                    else:
                        all_entities[label].append(ent)

    if include_spans:
        for label in all_entities:
            ents = all_entities[label]
            if include_confidence:
                ents.sort(key=lambda x: (x["start"], -x["confidence"]))
            else:
                ents.sort(key=lambda x: (x["start"], -(x["end"] - x["start"])))
            merged = []
            for ent in ents:
                duplicate = False
                for existing in merged:
                    if existing["start"] == ent["start"] and existing["end"] == ent["end"]:
                        duplicate = True
                        break
                    # Deduplicate overlapping entities of same label
                    overlap_len = min(existing["end"], ent["end"]) - max(existing["start"], ent["start"])
                    if overlap_len > 0:
                        duplicate = True
                        break
                if not duplicate:
                    merged.append(ent)
            all_entities[label] = merged
    else:
        for label in all_entities:
            ents = all_entities[label]
            seen = set()
            deduped = []
            for ent in ents:
                key = ent["text"] if include_confidence else ent
                if key not in seen:
                    seen.add(key)
                    deduped.append(ent)
            all_entities[label] = deduped

    return {"entities": all_entities}

# Attach function to the GLiNER2 class
GLiNER2.extract_entities_long = _extract_entities_long

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
        compile_model = True
    elif device_type == "mps":
        quantize = True
        compile_model = False  # torch.compile fails on MPS for GLiNER2 due to Metal shading compiler bugs
    else:  # cpu
        quantize = False  # CPU fp16 is slow or unsupported for many ops
        compile_model = True  # compile works on CPU
        
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

