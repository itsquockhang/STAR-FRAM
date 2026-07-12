import logging
import torch

logger = logging.getLogger("starfarm.utils")


def get_device() -> torch.device:
    """Detect the best available compute device: CUDA > MPS > CPU."""
    if torch.cuda.is_available():
        device = torch.device("cuda")
        logger.info(f"Using CUDA device: {torch.cuda.get_device_name(0)}")
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device = torch.device("mps")
        logger.info("Using Apple MPS (Metal Performance Shaders) device.")
    else:
        device = torch.device("cpu")
        logger.info("Using CPU device.")
    return device


# Color classes matching ner.html CSS
NER_TAG_CLASSES = [
    "ner-tag-0", "ner-tag-1", "ner-tag-2", "ner-tag-3",
    "ner-tag-4", "ner-tag-5", "ner-tag-6", "ner-tag-7",
]

def build_highlighted_html(text: str, entities_by_label: dict, labels: list[str]) -> str:
    """Build HTML string with inline entity highlights using direct spans."""
    import re
    from markupsafe import escape, Markup
    
    spans = []
    label_index = {label: i for i, label in enumerate(labels)}
    for label, entities in entities_by_label.items():
        idx = label_index.get(label, 0) % 8
        for entity in entities:
            if isinstance(entity, dict):
                start = entity.get("start")
                end = entity.get("end")
                matched = entity.get("text")
                if start is not None and end is not None and matched is not None:
                    spans.append((start, end, matched, label, idx))
            elif isinstance(entity, str):
                # Fallback in case a raw string is passed
                pattern = re.compile(re.escape(entity), re.IGNORECASE)
                for m in pattern.finditer(text):
                    spans.append((m.start(), m.end(), m.group(), label, idx))

    if not spans:
        return str(escape(text))

    # Sort by start position, longer spans first for overlaps
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))

    # Remove overlapping spans (keep the first/longest)
    filtered = []
    last_end = -1
    for span in spans:
        if span[0] >= last_end:
            filtered.append(span)
            last_end = span[1]

    # Build HTML
    parts = []
    cursor = 0
    for start, end, matched, label, idx in filtered:
        if start > cursor:
            parts.append(str(escape(text[cursor:start])))
        tag_class = NER_TAG_CLASSES[idx]
        parts.append(
            f'<span class="ner-entity {tag_class}">'
            f'{escape(matched)}'
            f'<span class="ner-label">{escape(label)}</span>'
            f'</span>'
        )
        cursor = end
    if cursor < len(text):
        parts.append(str(escape(text[cursor:])))

    return Markup(''.join(parts))

