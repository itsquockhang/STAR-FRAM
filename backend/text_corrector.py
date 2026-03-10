import threading
import json
from typing import Tuple

import torch
from huggingface_hub import hf_hub_download
from tokenizers import Tokenizer
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, PreTrainedTokenizerFast
from underthesea import text_normalize

MODEL_PATH = "protonx-models/protonx-legal-tc"

_lock = threading.Lock()
_tokenizer = None
_model = None
_device = None


def _get_model_and_tokenizer() -> Tuple[AutoTokenizer, AutoModelForSeq2SeqLM, torch.device]:
    global _tokenizer, _model, _device
    if _tokenizer is None or _model is None or _device is None:
        with _lock:
            if _tokenizer is None or _model is None or _device is None:
                try:
                    tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH)
                except Exception:
                    # Work around some repos with tokenizer.json that breaks AutoTokenizer
                    tok_path = hf_hub_download(MODEL_PATH, filename="tokenizer.json")
                    tokenizer_obj = Tokenizer.from_file(tok_path)
                    tokenizer = PreTrainedTokenizerFast(tokenizer_object=tokenizer_obj)

                    try:
                        stm_path = hf_hub_download(MODEL_PATH, filename="special_tokens_map.json")
                        with open(stm_path, "r", encoding="utf-8") as f:
                            stm = json.load(f)
                        # Common T5 tokens: <pad>, </s>, <unk>
                        for k, v in stm.items():
                            if k == "pad_token":
                                tokenizer.pad_token = v
                            elif k == "eos_token":
                                tokenizer.eos_token = v
                            elif k == "unk_token":
                                tokenizer.unk_token = v
                            elif k == "bos_token":
                                tokenizer.bos_token = v
                    except Exception:
                        pass

                model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_PATH)
                device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                model.to(device)
                model.eval()
                _tokenizer = tokenizer
                _model = model
                _device = device
    return _tokenizer, _model, _device


def correct_text(
    text: str,
    *,
    max_tokens: int = 160,
    num_beams: int = 10,
) -> str:
    """
    Spelling correction / text cleanup using protonx-models/protonx-legal-tc.
    Returns corrected text (best beam).
    """
    s = (text or "").strip()
    if not s:
        return ""

    # Normalize Vietnamese text before spelling correction model
    try:
        s = text_normalize(s)
    except Exception:
        pass

    tokenizer, model, device = _get_model_and_tokenizer()

    inputs = tokenizer(
        s,
        return_tensors="pt",
        truncation=True,
        max_length=max_tokens,
    ).to(device)

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            num_beams=num_beams,
            num_return_sequences=1,
            max_new_tokens=max_tokens,
            early_stopping=True,
        )

    decoded = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return decoded.strip()

