"""Branded social post built around a REAL team photo (exact faces — never AI-synthesized).

Pure, offline PIL: cover-fit the ACTUAL photo into the top of a 1200x1200 on-brand canvas, then drop a
navy headline band with the message + the real logo. Used by the generate_team_image tool when the
user asks to feature a specific Talentrupt person or group. No LLM / image-API calls.
"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw

from ..models import Brand
from .common import body_font, heading_font, paste_logo, public_url, storage_subdir, unique_name

W = H = 1200
BAND_H = 300            # navy text band at the bottom
RAIL_W = 24             # red signature rail down the left edge
SEAM_H = 140            # navy gradient blending the photo bottom into the band
NAVY = (0x0B, 0x35, 0x59)
RED = (0xF6, 0x40, 0x4C)
CREAM = (0xEB, 0xE9, 0xDF)
WHITE = (255, 255, 255)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = str(text or "").split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _cover_fit(img: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """Scale + center-crop to EXACTLY fill box_w x box_h without stretching, so faces stay undistorted
    (works for tall portraits and wide group shots alike)."""
    iw, ih = img.size
    scale = max(box_w / iw, box_h / ih)
    nw, nh = max(box_w, round(iw * scale)), max(box_h, round(ih * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - box_w) // 2, (nh - box_h) // 2
    return img.crop((left, top, left + box_w, top + box_h))


def build_team_image(
    brand: Brand | None, photo_bytes: bytes, headline: str, subhead: str | None = None
) -> tuple[str, str, dict]:
    """Composite a real team photo into an on-brand post. Returns (path, file_name, meta) — same shape
    as images._render. Raises on an unreadable photo (the caller surfaces a friendly message rather
    than ever falling back to an AI-generated face)."""
    photo = Image.open(io.BytesIO(photo_bytes)).convert("RGB")

    canvas = Image.new("RGB", (W, H), NAVY)
    photo_h = H - BAND_H
    canvas.paste(_cover_fit(photo, W, photo_h), (0, 0))

    # Soft navy gradient rising from the band into the photo bottom (no hard seam, headline always reads).
    ramp = Image.new("L", (1, SEAM_H), 0)
    for y in range(SEAM_H):
        ramp.putpixel((0, y), int(255 * (y / max(1, SEAM_H - 1))))
    canvas.paste(Image.new("RGB", (W, SEAM_H), NAVY), (0, photo_h - SEAM_H), ramp.resize((W, SEAM_H)))

    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, RAIL_W, H], fill=RED)  # brand rail

    # Headline — auto-shrink so it fits <=3 lines inside the band, leaving room for the logo (right) and
    # the subhead/underline (below).
    pad_l, pad_r = 84, 120
    max_w = W - pad_l - pad_r
    text = headline or (brand.tagline if brand and brand.tagline else "Meet the Talentrupt team")
    size = 64
    while size > 30:
        font = heading_font(size)
        lines = _wrap(d, text, font, max_w)
        if len(lines) <= 3 and len(lines) * int(size * 1.18) <= BAND_H - 130:
            break
        size -= 6
    font = heading_font(size)
    lines = _wrap(d, text, font, max_w)[:3]
    line_h = int(size * 1.18)

    y = photo_h + 44
    for ln in lines:
        d.text((pad_l, y), ln, font=font, fill=WHITE)
        y += line_h
    d.rectangle([pad_l, y + 8, pad_l + 88, y + 15], fill=RED)  # underline tick
    sub = subhead or (brand.tagline if brand and brand.tagline else "RPO Done Right")
    if sub:
        d.text((pad_l, y + 28), sub, font=body_font(30), fill=CREAM)

    logo_s = 92
    paste_logo(canvas, W - logo_s - 60, H - logo_s - 56, logo_s)  # real logo, band bottom-right

    file_name = unique_name("tr-team", "png")
    path = storage_subdir("images") / file_name
    canvas.save(str(path), "PNG")
    return str(path), file_name, {
        "url": public_url("images", file_name),
        "renderer": "team_photo_composite",
        "size": f"{W}x{H}",
        "kind": "team",
    }
