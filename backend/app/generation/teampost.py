"""Branded "feature a person/team" post built around a REAL photo (exact faces — never AI-synthesized).

Cuts the person out of their actual photo (offline background removal via rembg, when available) and
places them as a hero on Talentrupt's navy designed background — a bold headline, a question, a
"Featuring <name> · <role>" badge, and the real logo (the "Man on a Mission" style). Falls back to a
clean cover-fit (no cut-out) if rembg isn't installed, so the feature never breaks. No LLM/image-API.
"""
from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from ..models import Brand
from .common import body_font, heading_font, paste_logo, public_url, storage_subdir, unique_name

W = H = 1080
RAIL_W = 16
NAVY = (0x0B, 0x35, 0x59)
NAVY2 = (0x12, 0x44, 0x6E)
RED = (0xF6, 0x40, 0x4C)
CREAM = (0xEB, 0xE9, 0xDF)
WHITE = (255, 255, 255)


def _cutout(img: Image.Image) -> Image.Image:
    """Background-removed RGBA of the subject (offline rembg). Returns the original as opaque RGBA if
    rembg isn't available, so the post still renders (cover-fit) rather than failing."""
    try:
        from rembg import remove  # heavy import; only loaded when a team post is built
        out = remove(img).convert("RGBA")
        bbox = out.getbbox()
        return out.crop(bbox) if bbox else out
    except Exception:
        return img.convert("RGBA")


def _wrap(d: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words, lines, cur = str(text or "").split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= max_w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


# Background variety: each entry is (ghost rounded-rects, dotted-arc center+start-angle). Picked by
# `variant` so repeated posts for the same person don't share an identical background.
_BACKDROPS = [
    ([(640, 120, 360, 360, 18), (560, 360, 420, 420, -12), (720, 540, 300, 300, 26)], (880, 300, -10)),
    ([(600, 60, 440, 440, -14), (520, 470, 360, 360, 16), (770, 300, 280, 280, 30)], (300, 250, 100)),
    ([(680, 200, 380, 380, 10), (560, 560, 420, 420, -20), (810, 70, 300, 300, 24)], (300, 840, 205)),
]


def _paint_backdrop(canvas: Image.Image, d: ImageDraw.ImageDraw, variant: int = 0) -> None:
    rects, (ax, ay, a0) = _BACKDROPS[variant % len(_BACKDROPS)]
    for (x, y, w, h, rot) in rects:
        g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        ImageDraw.Draw(g).rounded_rectangle([0, 0, w, h], radius=40, fill=(*NAVY2, 130))
        gr = g.rotate(rot, expand=True)
        canvas.paste(gr, (x, y), gr)
    for i in range(26):  # dotted arc
        a = math.radians(a0 + i * 7)
        px, py = int(ax + 150 * math.cos(a)), int(ay + 150 * math.sin(a))
        d.ellipse([px - 4, py - 4, px + 4, py + 4], fill=WHITE)
    d.rectangle([0, 0, RAIL_W, H], fill=RED)


def build_team_image(
    brand: Brand | None, photo_bytes: bytes, name: str, role: str = "",
    headline: str = "", question: str = "", variant: int = 0,
) -> tuple[str, str, dict]:
    """Compose a branded feature post around a real photo. `variant` rotates the background, hero scale
    and headline accent so repeats look different. Returns (path, file_name, meta) — same shape as
    images._render. Raises on an unreadable photo (caller surfaces a message; never an AI face)."""
    try:  # team photos may be HEIC (iPhone) — register the opener when available
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    photo = ImageOps.exif_transpose(Image.open(io.BytesIO(photo_bytes)).convert("RGB"))
    hero = _cutout(photo)

    canvas = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(canvas)
    _paint_backdrop(canvas, d, variant)

    # Hero on the right, anchored bottom; cap width so a wide cut-out (group/scene) can't overflow.
    target_h = int(H * (0.80, 0.78, 0.82)[variant % 3])
    scale = target_h / hero.height
    if hero.width * scale > W * 0.62:
        scale = (W * 0.62) / hero.width
    hero = hero.resize((max(1, int(hero.width * scale)), max(1, int(hero.height * scale))), Image.LANCZOS)
    try:
        hero = hero.filter(ImageFilter.SHARPEN)
    except Exception:
        pass
    canvas.paste(hero, (W - hero.width - 36, H - hero.height), hero)

    pad = 70
    head = (headline or "On a Mission!").strip()
    hlines = _wrap(d, head, heading_font(104), W - 470)[:3]
    f = heading_font(104 if max(d.textlength(ln, font=heading_font(104)) for ln in hlines) <= (W - 470) else 84)
    accent_box = (variant % 2 == 0)  # even: red box on the last line; odd: a red underline bar
    y, last_tw = 84, 0
    for idx, ln in enumerate(hlines):
        tw = d.textlength(ln, font=f)
        last_tw = tw
        if accent_box and idx == len(hlines) - 1:
            d.rectangle([pad - 8, y - 4, pad + tw + 26, y + f.size + 14], fill=RED)
            d.text((pad + 6, y + 4), ln, font=f, fill=WHITE)
        else:
            d.text((pad, y + 4), ln, font=f, fill=WHITE)
        y += int(f.size * 1.18) + 10
    if not accent_box:
        d.rectangle([pad, y - 2, pad + min(int(last_tw), W - 470), y + 12], fill=RED)
        y += 18

    if question:
        qf = body_font(34)
        y += 12
        for ln in _wrap(d, question, qf, 440):
            d.text((pad, y), ln, font=qf, fill=CREAM)
            y += 44

    # Featuring + name + role badge, bottom-left
    fy = H - 250
    d.rectangle([pad, fy - 16, pad + 120, fy - 12], fill=WHITE)
    d.text((pad, fy), "Featuring", font=body_font(32), fill=CREAM)
    namef = heading_font(58)
    d.text((pad, fy + 40), name or "the Talentrupt team", font=namef, fill=WHITE)
    if role:
        ny = fy + 40 + 72
        bf = body_font(30)
        rw = d.textlength(role, font=bf)
        bw = 24 + 16 + rw  # briefcase icon + gap + role text
        d.rounded_rectangle([pad, ny, pad + bw + 40, ny + 52], radius=26, fill=WHITE)
        ix, iy = pad + 22, ny + 16  # mini briefcase, drawn (no emoji font dependency)
        d.rounded_rectangle([ix, iy + 5, ix + 24, iy + 20], radius=3, fill=NAVY)
        d.rectangle([ix + 8, iy, ix + 16, iy + 7], outline=NAVY, width=3)
        d.text((ix + 36, ny + 11), role, font=bf, fill=NAVY)

    try:
        paste_logo(canvas, W - 116, H - 116, 74)
    except Exception:
        pass

    file_name = unique_name("tr-team", "png")
    path = storage_subdir("images") / file_name
    canvas.convert("RGB").save(str(path), "PNG")
    return str(path), file_name, {
        "url": public_url("images", file_name),
        "renderer": "team_feature_cutout",
        "size": f"{W}x{H}",
        "kind": "team",
    }
