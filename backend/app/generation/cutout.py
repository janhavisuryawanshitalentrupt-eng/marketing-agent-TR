"""Optional employee-photo background removal via a hosted API.

Keeps the heavy rembg/onnxruntime off the shared 2GB droplet: when a `bg_removal_api_key` is configured
we strip the photo's background through remove.bg / Photoroom and float the person on the scene; when it
isn't (the default), the composer falls back to the designed framed card. The API removes ONLY the
background — the real face pixels are never altered. Any failure returns None so rendering never breaks.
"""
from __future__ import annotations

import logging

from ..config import settings

log = logging.getLogger("talentrupt.cutout")


def cutout_available() -> bool:
    """True when a background-removal API is configured (provider + key)."""
    return settings.bg_removal_provider in ("removebg", "photoroom") and bool(settings.bg_removal_api_key)


def remove_bg_api(img_bytes: bytes) -> bytes | None:
    """Remove the background from a photo via the configured API. Returns transparent PNG bytes, or None
    (no provider/key, missing httpx, network error, or non-image response) so the caller falls back to
    the framed-card layout."""
    if not cutout_available():
        return None
    try:
        import httpx  # bundled with the openai SDK; guard the import so a missing dep never crashes
    except Exception:
        return None
    provider, key = settings.bg_removal_provider, settings.bg_removal_api_key
    try:
        if provider == "removebg":
            r = httpx.post(
                "https://api.remove.bg/v1.0/removebg",
                headers={"X-Api-Key": key},
                files={"image_file": ("photo.png", img_bytes, "application/octet-stream")},
                data={"size": "auto", "format": "png"},
                timeout=45,
            )
        else:  # photoroom
            r = httpx.post(
                "https://sdk.photoroom.com/v1/segment",
                headers={"x-api-key": key},
                files={"image_file": ("photo.png", img_bytes, "application/octet-stream")},
                timeout=45,
            )
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
            return r.content
        log.warning("bg-removal %s failed: HTTP %s %s", provider, r.status_code, (r.text or "")[:200])
    except Exception as e:  # network / timeout / anything — fall back to the framed card
        log.warning("bg-removal %s error: %s", provider, e)
    return None
