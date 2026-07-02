"""Optional employee face-swap via a hosted API (keeps the person's EXACT real face on an AI portrait).

The problem: an image-to-image AI edit that gives the polished "blazer + scene" look REPAINTS the whole
person — including the face — so the featured employee ends up looking like someone else. The fix: generate
the AI portrait with gpt-image, then SWAP the person's real face onto it. Face detection / swapping needs
heavy libraries (insightface / onnxruntime) that we deliberately keep OFF the shared 2GB droplet, so we do
the swap through a hosted API instead.

Gated by `faceswap_provider` + `faceswap_api_key` (see config.py). When unset (the default) this is a no-op
and the composer keeps the plain real photo (exact face, real clothes). Any failure returns None so
rendering never breaks. Only the FACE is taken from the real photo; the body/clothes/background stay AI.
"""
from __future__ import annotations

import asyncio
import base64
import logging

from ..config import settings

log = logging.getLogger("talentrupt.faceswap")


def faceswap_available() -> bool:
    """True when a hosted face-swap API is configured (provider + key)."""
    return settings.faceswap_available()


def _data_uri(img_bytes: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(img_bytes).decode()


async def swap_face(target_png: bytes, source_png: bytes) -> bytes | None:
    """Put the REAL face (from `source_png`, the employee's actual photo) onto the AI portrait
    (`target_png`). Returns PNG/JPEG bytes, or None (no provider/key, missing httpx, network/model error) so
    the caller falls back to the plain real-photo composite. The body/clothes/background stay from the AI
    portrait; only the FACE comes from the real photo."""
    if not faceswap_available():
        return None
    provider = settings.faceswap_provider.strip().lower()
    if provider == "replicate":
        return await _replicate_swap(target_png, source_png)
    log.warning("faceswap provider %r not supported", provider)
    return None


async def _replicate_swap(target_png: bytes, source_png: bytes) -> bytes | None:
    """Run a Replicate face-swap model. Uses the model's LATEST version via
    POST /v1/models/{owner}/{name}/predictions with `Prefer: wait` (synchronous), then polls if needed.
    Input keys are configurable (faceswap_target_key / faceswap_source_key) to match the chosen model."""
    try:
        import httpx  # bundled with the openai SDK
    except Exception:
        return None
    key = settings.faceswap_api_key.strip()
    model = settings.faceswap_model.strip()
    tkey = settings.faceswap_target_key.strip() or "input_image"
    skey = settings.faceswap_source_key.strip() or "swap_image"
    payload = {"input": {tkey: _data_uri(target_png), skey: _data_uri(source_png)}}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": "wait"}
    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"https://api.replicate.com/v1/models/{model}/predictions", headers=headers, json=payload
            )
            if r.status_code not in (200, 201):
                log.warning("faceswap replicate create failed: HTTP %s %s", r.status_code, (r.text or "")[:200])
                return None
            data = r.json()
            output = await _await_output(c, data, key)
            if not output:
                return None
            url = output[-1] if isinstance(output, list) else output  # last output = the result image
            if not isinstance(url, str):
                return None
            img = await c.get(url, timeout=60)
            if img.status_code == 200 and img.headers.get("content-type", "").startswith("image"):
                return img.content
            log.warning("faceswap replicate output fetch failed: HTTP %s", img.status_code)
    except Exception as e:  # network / timeout / anything -> fall back to the real-photo composite
        log.warning("faceswap replicate error: %s", e)
    return None


async def _await_output(c, data: dict, key: str):
    """Return the prediction `output` once it succeeds. `Prefer: wait` usually returns it already; otherwise
    poll the get-url for up to ~60s."""
    status = data.get("status")
    get_url = (data.get("urls") or {}).get("get")
    for _ in range(30):
        if status == "succeeded":
            return data.get("output")
        if status in ("failed", "canceled"):
            log.warning("faceswap replicate %s: %s", status, str(data.get("error"))[:200])
            return None
        if not get_url:
            return None
        await asyncio.sleep(2)
        rr = await c.get(get_url, headers={"Authorization": f"Bearer {key}"}, timeout=30)
        if rr.status_code != 200:
            return None
        data = rr.json()
        status = data.get("status")
    log.warning("faceswap replicate timed out waiting for the swap")
    return None
