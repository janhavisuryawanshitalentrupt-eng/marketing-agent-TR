"""LLM provider adapter — provider-pluggable, streaming-first.

Phase 1 supports:
  * ``openai``  -> OpenAI-compatible chat completions (streaming) via httpx.
  * ``none``    -> deterministic streamed fallback so the app runs with no key.

Phase 2 will add tool-calling on top of ``chat_complete``.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import AsyncIterator

import httpx

from ..config import settings

log = logging.getLogger("talentrupt")

# Transient provider statuses worth a quick retry (rate limit + upstream/gateway hiccups).
_RETRY_STATUSES = {429, 500, 502, 503, 504}


async def _post_json(
    url: str, headers: dict, payload: dict, timeout: float = 120, attempts: int = 3
) -> dict:
    """POST a chat-completions request and return the parsed body, retrying briefly on TRANSIENT
    provider failures (timeouts, connection drops, 429/5xx). Non-transient errors (e.g. 400/401)
    raise immediately. Re-raises the last error if every attempt fails — so callers' own
    try/except still governs the user-facing outcome."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, headers=headers, json=payload)
            if resp.status_code in _RETRY_STATUSES and i < attempts - 1:
                log.info("provider %s (attempt %d/%d) — retrying", resp.status_code, i + 1, attempts)
                await asyncio.sleep(0.6 * (i + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.TimeoutException, httpx.TransportError) as e:
            last = e
            if i < attempts - 1:
                log.info("provider transport error (attempt %d/%d): %s — retrying", i + 1, attempts, e)
                await asyncio.sleep(0.6 * (i + 1))
                continue
            raise
    if last:
        raise last
    raise RuntimeError("provider returned no response")


def provider_available() -> bool:
    return settings.llm_provider == "openai" and bool(settings.openai_api_key)


def image_provider_available() -> bool:
    return settings.image_provider == "openai" and bool(settings.openai_api_key)


async def generate_image_bytes(
    prompt: str, size: str | None = None, quality: str | None = None
) -> bytes:
    """Generate an image with gpt-image-1 and return raw PNG bytes."""
    url = f"{settings.openai_base_url.rstrip('/')}/images/generations"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openai_image_model,
        "prompt": prompt,
        "n": 1,
        "size": size or settings.openai_image_size,
        "quality": quality or settings.openai_image_quality,
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        b64 = resp.json()["data"][0]["b64_json"]
    return base64.b64decode(b64)


async def generate_image_edit(
    prompt: str, references: list[bytes], size: str | None = None, quality: str | None = None
) -> bytes:
    """Generate an image with gpt-image-1 guided by reference images (style transfer
    from real past posts). Returns raw PNG bytes."""
    url = f"{settings.openai_base_url.rstrip('/')}/images/edits"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    files = [
        ("image[]", (f"ref{i}.jpg", data, "image/jpeg"))
        for i, data in enumerate(references)
    ]
    form = {
        "model": settings.openai_image_model,
        "prompt": prompt,
        "size": size or settings.openai_image_size,
        "quality": quality or settings.openai_image_quality,
    }
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(url, headers=headers, data=form, files=files)
        resp.raise_for_status()
        b64 = resp.json()["data"][0]["b64_json"]
    return base64.b64decode(b64)


async def stream_chat(messages: list[dict], temperature: float = 0.6) -> AsyncIterator[str]:
    """Yield assistant text deltas for the given chat messages."""
    if provider_available():
        async for delta in _stream_openai(messages, temperature):
            yield delta
    else:
        async for delta in _stream_fallback(messages):
            yield delta


async def _stream_openai(messages: list[dict], temperature: float) -> AsyncIterator[str]:
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0]["delta"].get("content")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue


async def chat_with_tools(
    messages: list[dict], tools: list[dict], temperature: float = 0.5
) -> dict:
    """Non-streaming completion with tool-calling. Returns the assistant message
    dict: {role, content, tool_calls?}. Caller is responsible for executing any
    tool calls and looping. Requires an available provider."""
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": temperature,
        "tools": tools,
        "tool_choice": "auto",
    }
    data = await _post_json(url, headers, payload)
    return data["choices"][0]["message"]


def _extract_json(text: str):
    """Lenient JSON extraction from model text (handles fences / prose around it)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text
        text = text.replace("json", "", 1).strip("` \n")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_c, close_c in (("[", "]"), ("{", "}")):
        i, j = text.find(open_c), text.rfind(close_c)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(text[i : j + 1])
            except json.JSONDecodeError:
                continue
    return None


async def web_search_text(prompt: str) -> str:
    """Live web-grounded query using the search-enabled model. Returns the RAW model text
    (prose + citations). Search-preview models ignore response_format, so callers that need
    JSON should structure this text with a second chat_json() pass."""
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openai_search_model,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""


async def web_search_json(prompt: str):
    """Live web-grounded query that returns parsed JSON (list/dict) or None."""
    return _extract_json(await web_search_text(prompt))


async def chat_json(messages: list[dict], temperature: float = 0.6) -> dict:
    """Non-streaming completion that returns parsed JSON. The prompt must ask
    for a JSON object. Requires an available provider."""
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openai_model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    data = await _post_json(url, headers, payload)
    content = data["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}


async def embed(texts: list[str]) -> list[list[float]]:
    """Return embedding vectors for the given texts. Requires a provider."""
    if not texts:
        return []
    url = f"{settings.openai_base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {"model": settings.openai_embedding_model, "input": texts}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()["data"]
    return [d["embedding"] for d in data]


async def vision_caption(image_b64: str, prompt: str) -> str:
    """Caption an image (base64 JPEG/PNG) with the vision-capable chat model."""
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.openai_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }
        ],
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"] or ""


async def _stream_fallback(messages: list[dict]) -> AsyncIterator[str]:
    """No-key deterministic response. Honest about being a local fallback."""
    user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    text = (
        "Talentrupt AI is running in local mode (no AI provider key configured yet).\n\n"
        f'You asked: "{user.strip()}"\n\n'
        "Once an OpenAI key is set in backend/.env (LLM_PROVIDER=openai), I will plan "
        "campaigns, write on-brand posts, design visuals, and build ready-to-present decks "
        "from a single request."
    )
    for word in text.split(" "):
        yield word + " "
