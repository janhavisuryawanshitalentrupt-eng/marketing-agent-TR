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


# The model that produced the most recent image — surfaced in asset meta so we can see which model
# actually ran (the configured one, or the gpt-image-1 fallback when the configured model is rejected).
LAST_IMAGE_MODEL: str = settings.openai_image_model
# Trips to True once the /images/edits endpoint proves unavailable on this account (so we stop paying the
# doomed-attempt latency on every subsequent employee image); resets on any successful edit.
_EDITS_DISABLED: bool = False


def _image_models(primary: str | None = None) -> list[str]:
    """The image model to use, with gpt-image-1 appended as a SAFE fallback when it differs — so an
    unavailable/experimental model name can never break generation (it falls back). `primary` overrides the
    configured model for a single call — e.g. routing a SMALL / auxiliary image (a poster panel, a deck
    cover) to the lighter gpt-image-1, while the MAIN featured image keeps the configured gpt-image-2."""
    first = (primary or settings.openai_image_model).strip() or settings.openai_image_model
    models = [first]
    if first != "gpt-image-1":
        models.append("gpt-image-1")
    return models


async def generate_image_bytes(
    prompt: str, size: str | None = None, quality: str | None = None, model: str | None = None
) -> bytes:
    """Generate an image and return raw PNG bytes. The MAIN image uses the configured model (gpt-image-2),
    falling back to gpt-image-1 only if that model is rejected. Pass model='gpt-image-1' for a SMALL /
    auxiliary image (a panel graphic, a deck cover) to use the lighter model deliberately."""
    global LAST_IMAGE_MODEL
    url = f"{settings.openai_base_url.rstrip('/')}/images/generations"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    last_err: Exception | None = None
    for m in _image_models(model):
        payload = {
            "model": m,
            "prompt": prompt,
            "n": 1,
            "size": size or settings.openai_image_size,
            "quality": quality or settings.openai_image_quality,
        }
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                b64 = resp.json()["data"][0]["b64_json"]
            LAST_IMAGE_MODEL = m
            return base64.b64decode(b64)
        except Exception as e:  # invalid/unavailable model, rate limit, etc. -> try the fallback
            last_err = e
            logging.getLogger(__name__).warning("image model %s failed: %s", m, e)
    raise last_err  # type: ignore[misc]


async def generate_image_edit(
    prompt: str, references: list[bytes], size: str | None = None, quality: str | None = None,
    input_fidelity: str | None = None, mime: str = "image/jpeg",
) -> bytes:
    """Generate an image guided by reference images. Two uses:
      - STYLE TRANSFER from real past posts (default: lossy JPEG refs, no fidelity lock).
      - IDENTITY-PRESERVING person edit — pass mime='image/png' + input_fidelity='high' so gpt-image-1
        keeps the SAME person's face/features while it repose/reframes/re-lights them (the employee AI
        portrait path). input_fidelity is a gpt-image-1 param; if a model rejects it the loop falls back.
    Tries the configured model, falling back to gpt-image-1 if that model is rejected. Returns PNG bytes."""
    global LAST_IMAGE_MODEL, _EDITS_DISABLED
    # If a prior call proved this account/endpoint can't do /images/edits (e.g. only gpt-image-2 is
    # available, which 400s on edits), stop wasting ~10-15s per image re-attempting the doomed call — fail
    # fast so the caller falls straight back to the real-cutout composite. Resets on any later success.
    if _EDITS_DISABLED:
        raise RuntimeError("image-edit endpoint disabled after a prior unsupported-endpoint failure")
    url = f"{settings.openai_base_url.rstrip('/')}/images/edits"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    ext = "png" if "png" in mime else "jpg"
    files = [
        ("image[]", (f"ref{i}.{ext}", data, mime))
        for i, data in enumerate(references)
    ]
    last_err: Exception | None = None
    unsupported = False  # a 4xx that means "this endpoint/model can't edit" (vs a transient 5xx/network error)
    # /images/edits is a gpt-image-1 capability today — gpt-image-2 currently 400s on the edit endpoint —
    # so try the known edit-capable model FIRST. Otherwise (when gpt-image-2 is the configured model) every
    # edit wastes a failed call before falling back. Any other configured model stays in the list after it,
    # in case a future model gains edit support.
    edit_models = ["gpt-image-1"] + [m for m in _image_models() if m != "gpt-image-1"]
    for model in edit_models:
        form = {
            "model": model,
            "prompt": prompt,
            "size": size or settings.openai_image_size,
            "quality": quality or settings.openai_image_quality,
        }
        if input_fidelity:  # preserve faces/logos when editing a real photo (gpt-image-1)
            form["input_fidelity"] = input_fidelity
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                resp = await client.post(url, headers=headers, data=form, files=files)
                resp.raise_for_status()
                b64 = resp.json()["data"][0]["b64_json"]
            LAST_IMAGE_MODEL = model
            _EDITS_DISABLED = False  # it works here — clear any earlier suspicion
            return base64.b64decode(b64)
        except Exception as e:
            last_err = e
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status in (400, 403, 404):  # model/endpoint not available for edits on this account
                unsupported = True
            logging.getLogger(__name__).warning("image-edit model %s failed: %s", model, e)
    if unsupported:  # every edit-capable model rejected the endpoint -> don't keep trying on later images
        _EDITS_DISABLED = True
        logging.getLogger(__name__).warning("disabling image-edit endpoint for this process (unsupported here)")
    raise last_err  # type: ignore[misc]


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


async def probe(model: str | None = None) -> dict:
    """Make a TINY real chat call and report exactly what the provider says — so we can tell whether a
    failing chat is out-of-credits (429 insufficient_quota), rate-limited (429 rate_limit_exceeded), a bad
    key (401), a bad model (404), etc. No retries (we want the raw first response). Never raises."""
    if not provider_available():
        return {"ok": False, "reason": "no_provider", "detail": "No OpenAI key / provider configured."}
    url = f"{settings.openai_base_url.rstrip('/')}/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
    payload = {"model": model or settings.openai_model,
               "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=headers, json=payload)
    except Exception as e:
        return {"ok": False, "reason": "network", "detail": str(e)[:300]}
    if resp.status_code == 200:
        return {"ok": True, "model": payload["model"]}
    # Pull the provider's error type/code/message out of the body when present.
    err_type = err_code = err_msg = ""
    try:
        err = (resp.json() or {}).get("error", {})
        err_type, err_code, err_msg = err.get("type", ""), err.get("code", ""), err.get("message", "")
    except Exception:
        err_msg = resp.text[:300]
    reason = {401: "bad_key", 404: "bad_model"}.get(resp.status_code, "")
    if resp.status_code == 429:
        reason = "out_of_credits" if "insufficient_quota" in f"{err_type}{err_code}" else "rate_limited"
    return {"ok": False, "status": resp.status_code, "reason": reason or f"http_{resp.status_code}",
            "error_type": err_type, "error_code": err_code, "detail": err_msg[:300], "model": payload["model"]}


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
