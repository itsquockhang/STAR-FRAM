from __future__ import annotations

import gc
import importlib
import threading
from typing import Any, Dict, Tuple

import torch

LLAMA_CPP_TRANSLATE_REPO_ID = "mradermacher/translategemma-4b-it-GGUF"
LLAMA_CPP_TRANSLATE_FILENAME = "translategemma-4b-it.IQ4_XS.gguf"
MLX_TRANSLATE_MODEL = "mlx-community/translategemma-4b-it-4bit"

_llama: Any | None = None
_mlx_model: Any | None = None
_mlx_tokenizer: Any | None = None
_model_lock = threading.Lock()


def _get_runtime_device() -> str:
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _build_llama(device: str) -> Any:
    llama_cpp = importlib.import_module("llama_cpp")
    llama_cls = getattr(llama_cpp, "Llama")

    common_kwargs = {
        "repo_id": LLAMA_CPP_TRANSLATE_REPO_ID,
        "filename": LLAMA_CPP_TRANSLATE_FILENAME,
        "verbose": True,
    }

    if device == "cuda":
        try:
            return llama_cls.from_pretrained(
                **common_kwargs,
                n_gpu_layers=-1,
            )
        except Exception:
            return llama_cls.from_pretrained(
                **common_kwargs,
                n_gpu_layers=0,
            )

    return llama_cls.from_pretrained(
        **common_kwargs,
        n_gpu_layers=0,
    )


def _get_llama(device: str) -> Any:
    global _llama
    if _llama is None:
        with _model_lock:
            if _llama is None:
                _llama = _build_llama(device)
    return _llama


def _get_mlx_model_and_tokenizer() -> Tuple[Any, Any]:
    global _mlx_model, _mlx_tokenizer
    if _mlx_model is None or _mlx_tokenizer is None:
        with _model_lock:
            if _mlx_model is None or _mlx_tokenizer is None:
                # Import lazily so Linux/Windows environments do not require MLX libs.
                mlx_lm = importlib.import_module("mlx_lm")
                load_fn = getattr(mlx_lm, "load")

                _mlx_model, _mlx_tokenizer = load_fn(MLX_TRANSLATE_MODEL)
    return _mlx_model, _mlx_tokenizer


def _release_llama() -> None:
    global _llama
    with _model_lock:
        llm = _llama
        _llama = None

    if llm is not None:
        try:
            close_fn = getattr(llm, "close", None)
            if callable(close_fn):
                close_fn()
        except Exception:
            pass

        try:
            del llm
        except Exception:
            pass


def _release_mlx_model_and_tokenizer() -> None:
    global _mlx_model, _mlx_tokenizer
    with _model_lock:
        model = _mlx_model
        tokenizer = _mlx_tokenizer
        _mlx_model = None
        _mlx_tokenizer = None

    if model is not None:
        try:
            del model
        except Exception:
            pass
    if tokenizer is not None:
        try:
            del tokenizer
        except Exception:
            pass


def _release_runtime_caches() -> None:
    try:
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()

        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
    except Exception:
        pass


def _release_translation_resources() -> None:
    _release_llama()
    _release_mlx_model_and_tokenizer()
    _release_runtime_caches()


def _build_translation_prompt(source_lang_code: str, target_lang_code: str, text: str) -> str:
    return (
        f"Translate the following text from {source_lang_code} to {target_lang_code}. "
        "Return only the translated text.\n\n"
        f"{text}"
    )


def _build_translation_message_content(
    source_lang_code: str,
    target_lang_code: str,
    text: str,
) -> list[Dict[str, Any]]:
    return [
        {
            "type": "text",
            "source_lang_code": source_lang_code,
            "target_lang_code": target_lang_code,
            "text": text,
            "image": None,
        }
    ]


def _translate_with_mlx(
    text: str,
    source_lang_code: str,
    target_lang_code: str,
    max_new_tokens: int,
) -> str:
    # Import lazily so Linux/Windows environments do not require MLX libs.
    mlx_lm = importlib.import_module("mlx_lm")
    generate_fn = getattr(mlx_lm, "generate")

    model, tokenizer = _get_mlx_model_and_tokenizer()
    prompt = _build_translation_prompt(source_lang_code, target_lang_code, text)

    if getattr(tokenizer, "chat_template", None) is not None:
        messages = [{"role": "user", "content": prompt}]
        prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True)

    response = generate_fn(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=max_new_tokens,
        verbose=False,
    )
    return str(response).strip()


def _parse_llama_output(output: Any) -> str:
    if not isinstance(output, dict):
        return ""

    choices = output.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    first = choices[0]
    if isinstance(first, dict):
        message = first.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                return content.strip()
            if isinstance(content, list) and content:
                item = content[0]
                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        return text.strip()

        text = first.get("text")
        if isinstance(text, str):
            return text.strip()

    return ""


def _translate_with_llama(
    text: str,
    source_lang_code: str,
    target_lang_code: str,
    max_new_tokens: int,
    device: str,
) -> str:
    llm = _get_llama(device)
    content = _build_translation_message_content(
        source_lang_code=source_lang_code,
        target_lang_code=target_lang_code,
        text=text,
    )
    output = llm.create_chat_completion(
        messages=[
            {
                "role": "user",
                "content": content,
            },
        ],
        max_tokens=max_new_tokens,
        temperature=0,
    )
    return _parse_llama_output(output)


def handle_translate(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    text = str(payload.get("text") or "")
    source_lang_code = str(payload.get("source_lang_code") or "").strip()
    target_lang_code = str(payload.get("target_lang_code") or "").strip()
    max_new_tokens = payload.get("max_new_tokens", 200)

    if not text.strip():
        return {"error": "Missing 'text'"}, 400
    if not source_lang_code:
        return {"error": "Missing 'source_lang_code'"}, 400
    if not target_lang_code:
        return {"error": "Missing 'target_lang_code'"}, 400

    try:
        max_new_tokens = int(max_new_tokens)
    except Exception:
        return {"error": "Invalid 'max_new_tokens'"}, 400

    max_new_tokens = max(1, min(1024, max_new_tokens))

    device = _get_runtime_device()

    try:
        if device == "mps":
            translated_text = _translate_with_mlx(
                text=text,
                source_lang_code=source_lang_code,
                target_lang_code=target_lang_code,
                max_new_tokens=max_new_tokens,
            )
            model_name = MLX_TRANSLATE_MODEL
            backend = "mlx_lm"
        else:
            translated_text = _translate_with_llama(
                text=text,
                source_lang_code=source_lang_code,
                target_lang_code=target_lang_code,
                max_new_tokens=max_new_tokens,
                device=device,
            )
            model_name = LLAMA_CPP_TRANSLATE_REPO_ID
            backend = "llama_cpp"
    except ModuleNotFoundError as e:
        return {"error": f"Translation backend missing dependency: {e!s}"}, 500
    except Exception as e:
        return {"error": f"Translation failed: {e!s}"}, 500
    finally:
        # Release model/tokenizer/pipeline after each request as requested.
        _release_translation_resources()

    if not translated_text:
        return {"error": "Translation model returned empty output"}, 502

    return (
        {
            "model": model_name,
            "model_filename": LLAMA_CPP_TRANSLATE_FILENAME if backend == "llama_cpp" else None,
            "backend": backend,
            "device": device,
            "source_lang_code": source_lang_code,
            "target_lang_code": target_lang_code,
            "translated_text": translated_text,
        },
        200,
    )
