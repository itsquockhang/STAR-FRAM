import os
import json
import asyncio
import logging
import httpx

logger = logging.getLogger("starfarm.translate")

TRANSLATE_API_BASE = os.getenv("TRANSLATE_API_BASE", "https://www-translate.quockhang.io.vn/v1")
DEFAULT_MODEL = "translategemma-4b-it"
TARGET_MODEL_ROOT = "ViralityLeo/vllm-translategemma-4b-it-FP8-Dynamic"

# Global circuit breaker state for Translation connection
_translate_online = True
_translate_last_checked = 0.0
_translate_offline_reason = ""


async def check_connection() -> tuple[bool, str | None, list[str]]:
    """
    Check connection to the translation server and fetch available models.
    Returns:
        (is_connected, error_message, available_model_ids)
    """
    global _translate_online, _translate_last_checked, _translate_offline_reason
    import time
    
    current_time = time.time()
    # Circuit breaker: if marked offline within last 15 seconds, fail immediately without waiting for HTTP timeout
    if not _translate_online and (current_time - _translate_last_checked < 15.0):
        return False, f"Translation server is marked offline (Circuit Breaker active. Reason: {_translate_offline_reason})", []

    url = f"{TRANSLATE_API_BASE}/models"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
            if response.status_code == 200:
                data = response.json()
                models = data.get("data", [])
                model_ids = [m.get("id") for m in models if m.get("id")]
                _translate_online = True
                _translate_last_checked = current_time
                return True, None, model_ids
            else:
                reason = f"Server returned HTTP status code {response.status_code}"
                _translate_online = False
                _translate_last_checked = current_time
                _translate_offline_reason = reason
                return False, reason, []
    except httpx.ConnectError:
        reason = "Could not resolve host or connect to the translation server. Please verify your internet connection."
        _translate_online = False
        _translate_last_checked = current_time
        _translate_offline_reason = reason
        return False, reason, []
    except httpx.TimeoutException:
        reason = "Connection to the translation server timed out."
        _translate_online = False
        _translate_last_checked = current_time
        _translate_offline_reason = reason
        return False, reason, []
    except Exception as e:
        logger.error(f"Error checking translation server status: {e}")
        reason = f"Unexpected error: {str(e)}"
        _translate_online = False
        _translate_last_checked = current_time
        _translate_offline_reason = reason
        return False, reason, []

async def translate_text(text: str, source_lang: str, target_lang: str) -> dict:
    """
    Translate text using the TranslateGemma model.
    Splits text recursively using RecursiveChunker to fit in TranslateGemma context window.
    Constructs the prompt as: <<<source>>>{source_lang}<<<target>>>{target_lang}<<<text>>>{chunk}
    """
    # 1. Determine model ID by checking available models
    is_connected, err_msg, model_ids = await check_connection()
    if not is_connected:
        raise ConnectionError(f"Translation server is unreachable. Details: {err_msg}")
    
    # Try resolving to the target root model, falling back to matching ID
    resolved_model = DEFAULT_MODEL
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(f"{TRANSLATE_API_BASE}/models")
            if response.status_code == 200:
                models = response.json().get("data", [])
                for m in models:
                    m_id = m.get("id")
                    m_root = m.get("root")
                    if m_root == TARGET_MODEL_ROOT or m_id == TARGET_MODEL_ROOT:
                        resolved_model = m_id
                        break
                    elif m_id == DEFAULT_MODEL:
                        resolved_model = m_id
    except Exception as e:
        logger.warning(f"Could not dynamically resolve model ID, using default fallback. Error: {e}")

    # Chunk the text using Chonkie's RecursiveChunker with gpt2 tokenizer standard
    from chonkie import RecursiveChunker
    # Use chunk_size=1500 tokens (very safe for max 4096 tokens)
    chunker = RecursiveChunker(tokenizer="gpt2", chunk_size=1500)
    chunks = chunker.chunk(text)
    
    translated_chunks = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for idx, chunk in enumerate(chunks):
            # Build the required prompt format
            prompt = f"<<<source>>>{source_lang}<<<target>>>{target_lang}<<<text>>>{chunk.text}"
            
            payload = {
                "model": resolved_model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            
            url = f"{TRANSLATE_API_BASE}/chat/completions"
            logger.info(f"Sending translation request for chunk {idx+1}/{len(chunks)} to {url} using model {resolved_model}")
            
            response = await client.post(url, json=payload)
            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_detail = response.json().get("error", {}).get("message", response.text)
                except Exception:
                    pass
                raise ValueError(f"Translate server error on chunk {idx+1}: {error_detail}")
                
            result = response.json()
            choices = result.get("choices", [])
            if not choices:
                raise ValueError(f"No translation output was returned for chunk {idx+1}.")
                
            translated_text = choices[0].get("message", {}).get("content", "")
            translated_chunks.append(translated_text)
            
            # Aggregate usage stats
            usage = result.get("usage", {})
            total_prompt_tokens += usage.get("prompt_tokens", 0)
            total_completion_tokens += usage.get("completion_tokens", 0)
            total_tokens += usage.get("total_tokens", 0)

    # Join the translated chunks back together
    full_translation = "\n\n".join(translated_chunks)
    
    return {
        "translated_text": full_translation,
        "model_used": resolved_model,
        "usage": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens
        }
    }


async def translate_single_chunk_non_stream(client, url, payload, idx):
    try:
        response = await client.post(url, json=payload)
        if response.status_code != 200:
            error_detail = response.text
            try:
                error_detail = response.json().get("error", {}).get("message", response.text)
            except Exception:
                pass
            return {"error": error_detail, "index": idx}
        result = response.json()
        choices = result.get("choices", [])
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        usage = result.get("usage", {})
        return {"translated_text": content, "usage": usage, "index": idx}
    except Exception as e:
        return {"error": str(e), "index": idx}


async def translate_text_stream(text: str, source_lang: str, target_lang: str, stream_limit: int = 1):
    """
    Stream translation token-by-token for the first 'stream_limit' chunks,
    while translating the remaining chunks in parallel in the background
    to optimize speed.
    """
    is_connected, err_msg, _ = await check_connection()
    if not is_connected:
        yield {"error": f"Translation server is unreachable: {err_msg}"}
        return

    resolved_model = DEFAULT_MODEL
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            response = await client.get(f"{TRANSLATE_API_BASE}/models")
            if response.status_code == 200:
                models = response.json().get("data", [])
                for m in models:
                    m_id = m.get("id")
                    m_root = m.get("root")
                    if m_root == TARGET_MODEL_ROOT or m_id == TARGET_MODEL_ROOT:
                        resolved_model = m_id
                        break
                    elif m_id == DEFAULT_MODEL:
                        resolved_model = m_id
    except Exception as e:
        logger.warning(f"Could not resolve model ID in stream, using default fallback: {e}")

    # Chunk using Chonkie
    from chonkie import RecursiveChunker
    chunker = RecursiveChunker(tokenizer="gpt2", chunk_size=1500)
    chunks = chunker.chunk(text)

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0

    # Start parallel tasks for chunks beyond the stream_limit
    tasks = []
    async with httpx.AsyncClient(timeout=60.0) as client:
        url = f"{TRANSLATE_API_BASE}/chat/completions"
        for idx in range(stream_limit, len(chunks)):
            chunk = chunks[idx]
            prompt = f"<<<source>>>{source_lang}<<<target>>>{target_lang}<<<text>>>{chunk.text}"
            payload = {
                "model": resolved_model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            }
            tasks.append(translate_single_chunk_non_stream(client, url, payload, idx))

        # Run background translation tasks concurrently
        bg_tasks = asyncio.gather(*tasks) if tasks else None

        # Process the first stream_limit chunks token-by-token
        for idx in range(min(stream_limit, len(chunks))):
            chunk = chunks[idx]
            if idx > 0:
                yield {"token": "\n\n"}

            prompt = f"<<<source>>>{source_lang}<<<target>>>{target_lang}<<<text>>>{chunk.text}"
            payload = {
                "model": resolved_model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "stream": True,
                "stream_options": {
                    "include_usage": True
                }
            }

            logger.info(f"Streaming chunk {idx+1}/{len(chunks)} using model {resolved_model}")
            try:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        yield {"error": f"Translate server returned status code {response.status_code}"}
                        return
                    
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                continue
                            try:
                                data_json = json.loads(data_str)
                                
                                # Check for usage info
                                usage = data_json.get("usage")
                                if usage:
                                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                                    total_completion_tokens += usage.get("completion_tokens", 0)
                                    total_tokens += usage.get("total_tokens", 0)
                                    continue
                                
                                choices = data_json.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    if content:
                                        yield {"token": content}
                            except Exception as parse_err:
                                logger.warning(f"Failed to parse streaming line: {parse_err}")
            except Exception as e:
                yield {"error": f"Streaming request failed: {str(e)}"}
                return

        # Once the streaming chunks are finished, wait for the parallel background tasks to complete
        if bg_tasks:
            results = await bg_tasks
            for res in results:
                if "error" in res:
                    yield {"error": f"Failed to translate chunk {res['index']+1}: {res['error']}"}
                    return
                
                yield {"token": "\n\n"}
                yield {"token": res["translated_text"]}

                # Add usage stats
                usage = res.get("usage", {})
                total_prompt_tokens += usage.get("prompt_tokens", 0)
                total_completion_tokens += usage.get("completion_tokens", 0)
                total_tokens += usage.get("total_tokens", 0)

    # Yield the final usage object
    yield {
        "model_used": resolved_model,
        "usage": {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens
        }
    }

