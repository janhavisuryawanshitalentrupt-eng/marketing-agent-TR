"""Animate a finished still post into a short, premium MOTION clip — a slow cinematic zoom/pan
("Ken Burns") over the REAL rendered image.

The face is NEVER altered: this is pure camera motion over the actual post (the real photo), so the
person's likeness is byte-for-byte the one we already composited — no AI, no re-synthesis. Encodes an
MP4 (h.264, broadly compatible) when imageio-ffmpeg is available, falling back to an animated GIF so the
feature still works offline. A true image-to-video provider (Runway/Kling/etc., which adds subtle head
motion while preserving identity) can later be plugged into _provider_motion() behind a config flag.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from .common import public_url, storage_subdir, unique_name


def _ease(t: float) -> float:
    """Smootherstep easing for a gentle start/stop."""
    return t * t * t * (t * (t * 6 - 15) + 10)


def _kenburns_frames(img: Image.Image, n: int, zoom: float) -> list[Image.Image]:
    W, H = img.size
    pan_x, pan_y = W * 0.045, -H * 0.03  # subtle diagonal drift
    frames = []
    for i in range(n):
        e = _ease(i / (n - 1)) if n > 1 else 0.0
        scale = 1.0 + zoom * e
        cw, ch = W / scale, H / scale
        cx = W / 2 + pan_x * (e - 0.5) * 2
        cy = H / 2 + pan_y * (e - 0.5) * 2
        left = min(max(cx - cw / 2, 0), W - cw)
        top = min(max(cy - ch / 2, 0), H - ch)
        crop = img.crop((round(left), round(top), round(left + cw), round(top + ch)))
        frames.append(crop.resize((W, H), Image.LANCZOS))
    return frames


def build_motion(image_path: str, duration: float = 3.2, fps: int = 24, zoom: float = 0.14):
    """Render a Ken-Burns motion clip from a still image. Returns (path, file_name, meta). MP4 when an
    encoder is present, else an animated GIF. Never changes the image's content — only the framing."""
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    if W % 2:  # h.264/yuv420p needs even dimensions
        img = img.crop((0, 0, W - 1, H))
        W -= 1
    if H % 2:
        img = img.crop((0, 0, W, H - 1))
        H -= 1
    n = max(2, int(duration * fps))
    frames = _kenburns_frames(img, n, zoom)

    try:
        import imageio.v2 as imageio
        file_name = unique_name("tr-motion", "mp4")
        path = storage_subdir("images") / file_name
        writer = imageio.get_writer(
            str(path), fps=fps, codec="libx264", quality=8,
            macro_block_size=1, pixelformat="yuv420p",  # broad browser/social compatibility
        )
        for f in frames:
            writer.append_data(np.asarray(f))
        writer.close()
        fmt = "mp4"
    except Exception:
        file_name = unique_name("tr-motion", "gif")
        path = storage_subdir("images") / file_name
        light = [f.resize((W // 2, H // 2), Image.LANCZOS) for f in frames[::2]]
        light[0].save(str(path), save_all=True, append_images=light[1:],
                      duration=int(2000 / fps), loop=0, optimize=True)
        fmt = "gif"

    return str(path), file_name, {
        "url": public_url("images", file_name),
        "format": fmt,
        "renderer": "motion_kenburns",
        "kind": "video",
        "size": f"{W}x{H}",
        "duration": round(duration, 1),
    }
