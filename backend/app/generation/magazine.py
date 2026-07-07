"""Multi-page MAGAZINE generator — a branded, festive internal magazine (à la "Talentrupt Times").

Each PAGE is rendered as a full-page PIL image (portrait, 1080×1528) with the same brand fonts, colours and
REAL employee photos the rest of the app uses (faces are NEVER AI-generated — `_cutout` keeps the real photo).
The pages are then combined into ONE multi-page PDF via Pillow's `save_all=True`.

Pages produced:
  1. COVER      — the month's champion (real cut-out) on a festive backdrop + big stat callouts + headline.
  2. EDITORIAL  — a warm editor's note (LLM-written, grounded in the theme; falls back to a default).
  3. SPOTLIGHTS — one card per featured teammate (circular real photo + office + stat chips + blurb), 2/page.
  4. CLOSING    — a simple branded thank-you page.

The generator is defensive: any single photo / LLM failure degrades gracefully, never crashes the build.
The caller (the /api/magazine endpoint) resolves employee ids → (name, role, photo bytes); this module never
touches the database.
"""
from __future__ import annotations

import hashlib
import io
import logging

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .common import (
    body_font,
    heading_font,
    paste_wordmark,
    public_url,
    script_font,
    storage_subdir,
    unique_name,
)
from .teampost import (
    CREAM,
    NAVY,
    RED,
    WHITE,
    _confetti,
    _cover_fit,
    _enhance_photo,
    _wrap,
)

log = logging.getLogger("talentrupt")

MW, MH = 1080, 1528          # portrait page (≈ A4 ratio)
RAIL = 14
INK = (0x14, 0x22, 0x3A)     # near-navy body text on light
SUBINK = (0x55, 0x63, 0x74)  # muted grey
GOLD = (0xF5, 0xC0, 0x42)
ORANGE = (0xFF, 0x7A, 0x52)
GREEN = (0x1E, 0x7A, 0x46)

# Festive accent palettes keyed by occasion word in the theme; brand palette is the default.
_FESTIVE = {
    "diwali": [GOLD, ORANGE, RED, (0xE0, 0x5A, 0x2B)],
    "deepavali": [GOLD, ORANGE, RED, (0xE0, 0x5A, 0x2B)],
    "christmas": [RED, GREEN, GOLD, (0x2A, 0x6E, 0xD6)],
    "holi": [RED, (0x2A, 0x6E, 0xD6), GOLD, GREEN],
    "new year": [GOLD, RED, NAVY, (0x2A, 0x6E, 0xD6)],
    "eid": [GREEN, GOLD, (0x2A, 0x6E, 0xD6), CREAM],
}


def _festive_palette(theme: str) -> list[tuple]:
    t = (theme or "").lower()
    for key, pal in _FESTIVE.items():
        if key in t:
            return pal
    return [RED, GOLD, NAVY, ORANGE]


def _seed(text: str) -> int:
    # stable across process runs (builtin hash() is salted per-process) so the festive layout is deterministic
    return int(hashlib.md5((text or "tr").encode("utf-8")).hexdigest()[:8], 16)


def _ellipsize(d: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    """Truncate `text` with an ellipsis so it fits on ONE line within max_w px."""
    text = str(text or "")
    if d.textlength(text, font=font) <= max_w:
        return text
    out = ""
    for ch in text:
        if d.textlength(out + ch + "…", font=font) <= max_w:
            out += ch
        else:
            break
    return (out + "…") if out else "…"


# ---- photo helpers -------------------------------------------------------------------------------
def _open_photo(photo_bytes: bytes) -> Image.Image:
    """Open + orient + enhance an employee photo. HEIC-safe. Raises on truly unreadable bytes."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    src = ImageOps.exif_transpose(Image.open(io.BytesIO(photo_bytes)).convert("RGB"))
    src.thumbnail((1600, 1600), Image.LANCZOS)   # cap size (OOM safety on the small droplet)
    return _enhance_photo(src)


def _circle_photo(photo_bytes: bytes, size: int) -> Image.Image | None:
    """A circular, cover-fitted real-photo avatar with a subtle ring. None on failure."""
    try:
        src = _cover_fit(_open_photo(photo_bytes), size, size)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
        out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        out.paste(src, (0, 0), mask)
        ring = ImageDraw.Draw(out)
        ring.ellipse([1, 1, size - 2, size - 2], outline=(*WHITE, 255), width=max(4, size // 60))
        return out
    except Exception as e:
        log.warning("magazine circle photo failed: %s", e)
        return None


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    """Round the corners of an RGB/RGBA image (returns RGBA)."""
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


# ---- drawing helpers -----------------------------------------------------------------------------
def _para(d: ImageDraw.ImageDraw, x: int, y: int, text: str, font, fill, max_w: int,
          line_h: int, max_lines: int = 8) -> int:
    """Draw wrapped body text (splitting on blank lines into paragraphs); return the y below."""
    for block in (text or "").split("\n"):
        block = block.strip()
        if not block:
            y += line_h // 2
            continue
        for ln in _wrap(d, block, font, max_w):
            if max_lines <= 0:
                return y
            d.text((x, y), ln, font=font, fill=fill)
            y += line_h
            max_lines -= 1
    return y


_CHIP_H = 122
_MEASURE = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def _chip_size(label: str, value: str) -> tuple[int, int]:
    """The (width, height) a stat chip will occupy — so callers can lay chips out without overflow."""
    vw = _MEASURE.textlength(str(value)[:7], font=heading_font(54))
    lw = _MEASURE.textlength(str(label).upper()[:16], font=body_font(22))
    return int(max(vw, lw, 120) + 52), _CHIP_H


def _stat_chip(canvas: Image.Image, x_left: int, cy: int, label: str, value: str, accent=RED) -> int:
    """A white, soft-shadowed pill (big VALUE + small red LABEL) with its LEFT edge at x_left, vertically
    centred at cy. Returns the chip WIDTH so a row/column of chips can be laid out cleanly."""
    d = ImageDraw.Draw(canvas)
    val, lab = str(value)[:7], str(label).upper()[:16]
    vf, lf = heading_font(54), body_font(22)
    vw, lw = d.textlength(val, font=vf), d.textlength(lab, font=lf)
    w, h = int(max(vw, lw, 120) + 52), _CHIP_H
    x0, y0 = int(x_left), int(cy - h / 2)
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([x0 + 4, y0 + 7, x0 + w + 4, y0 + h + 7], radius=26,
                                         fill=(11, 34, 58, 70))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(7)))
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle([x0, y0, x0 + w, y0 + h], radius=26, fill=(*WHITE, 255))
    d.text((x0 + (w - lw) / 2, y0 + 18), lab, font=lf, fill=accent)
    d.text((x0 + (w - vw) / 2, y0 + 46), val, font=vf, fill=NAVY)
    return w


def _festoon(d: ImageDraw.ImageDraw, y: int, palette: list[tuple]) -> None:
    """A simple festive garland: a row of hanging dots across the page top."""
    n = 22
    gap = MW // n
    for i in range(n + 1):
        x = i * gap
        col = palette[i % len(palette)]
        r = 12 if i % 2 == 0 else 8
        d.line([(x, 0), (x, y - r - 4)], fill=(*NAVY, 60), width=1)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*col, 255))


def _masthead(canvas: Image.Image, edition: str, month_hint: str = "") -> None:
    d = ImageDraw.Draw(canvas)
    tf = heading_font(84)
    title = "TALENTRUPT"
    tw = d.textlength(title, font=tf)
    tx = (MW - tw) // 2
    d.text((tx, 66), title, font=tf, fill=NAVY)
    sf = heading_font(38)
    stw = d.textlength("TIMES", font=sf)
    d.text((tx + tw - stw, 150), "TIMES", font=sf, fill=RED)
    ef = body_font(24)
    if edition:
        d.text((40, 74), edition.upper()[:26], font=ef, fill=SUBINK)
    d.line([(40, 214), (MW - 40, 214)], fill=(*RED, 255), width=4)


# ---- page renderers ------------------------------------------------------------------------------
def _render_cover(issue: dict) -> Image.Image:
    palette = _festive_palette(issue.get("theme", ""))
    canvas = Image.new("RGBA", (MW, MH), (*CREAM, 255))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, RAIL, MH], fill=(*RED, 255))
    # festive confetti in reserved zones (top band + left gutter), theme-tinted
    try:
        _confetti(d, RAIL, 0, MW, 60, 22, _seed(issue.get("title", "")))
    except Exception:
        pass
    _masthead(canvas, issue.get("edition", ""))

    cover = issue.get("cover", {}) or {}
    # 1) champion photo on the RIGHT — a clean framed PORTRAIT. (A headshot rarely cuts out cleanly on the
    # free keyer, and a bad cut-out rendered as an empty blob; a framed crop always shows the real face.)
    photo = cover.get("photo")
    if photo:
        try:
            src = _open_photo(photo)
            fw, fh, fx, fy, r = 500, 900, MW - 524, 300, 46
            sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(sh).rounded_rectangle([fx + 8, fy + 14, fx + fw + 8, fy + fh + 14], radius=r,
                                                 fill=(11, 34, 58, 95))
            canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
            canvas.alpha_composite(_rounded(_cover_fit(src, fw, fh), r), (fx, fy))
            ImageDraw.Draw(canvas).rounded_rectangle([fx - 5, fy - 5, fx + fw + 5, fy + fh + 5],
                                                     radius=r + 5, outline=(*WHITE, 255), width=8)
        except Exception as e:
            log.warning("magazine cover photo failed: %s", e)

    # 2) champion name (script) upper-left
    d = ImageDraw.Draw(canvas)
    name = (cover.get("name") or "").strip()
    if name:
        nf = script_font(104)
        ny = 288
        for ln in _wrap(d, name, nf, int(MW * 0.44))[:2]:
            d.text((46, ny), ln, font=nf, fill=RED)
            ny += 96

    # 3) stat callouts down the LEFT column (centred at x=0.22·MW, laid out by measured width)
    stats = [s for s in (cover.get("stats") or []) if (s or {}).get("label")][:6]
    sy = 560
    for s in stats:
        cw, _ch = _chip_size(s.get("label", ""), s.get("value", ""))
        _stat_chip(canvas, int(MW * 0.22 - cw / 2), sy, s.get("label", ""), s.get("value", ""))
        sy += 150

    # 4) headline + tagline in a navy bottom band
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 1256, MW, MH], fill=(*NAVY, 255))
    d.rectangle([0, 1256, RAIL, MH], fill=(*RED, 255))
    hl = (cover.get("headline") or "In the Spotlight").strip()
    hf = heading_font(58)
    hy = 1292
    for ln in _wrap(d, hl, hf, MW - 92)[:2]:
        d.text((46, hy), ln, font=hf, fill=WHITE)
        hy += 66
    tag = (cover.get("tagline") or "").strip()
    if tag:
        _para(d, 46, hy + 8, tag, body_font(28), CREAM, MW - 92, 40, max_lines=3)
    try:
        paste_wordmark(canvas, MW - 250, MH - 62, 210, 40, dark_bg=True, align="right")
    except Exception:
        pass
    return canvas.convert("RGB")


def _render_editorial(issue: dict, editorial: str) -> Image.Image:
    palette = _festive_palette(issue.get("theme", ""))
    canvas = Image.new("RGBA", (MW, MH), (*CREAM, 255))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, RAIL, MH], fill=(*RED, 255))
    _festoon(d, 96, palette)
    theme = (issue.get("theme") or "").strip()
    kicker = "EDITOR'S NOTE"
    d.text((60, 190), kicker, font=heading_font(26), fill=RED)
    title = (f"Happy {theme.title()}!" if theme else "A Note From The Desk")
    ty = 234
    for ln in _wrap(d, title, heading_font(72), MW - 120)[:2]:
        d.text((60, ty), ln, font=heading_font(72), fill=NAVY)
        ty += 78
    d.line([(60, ty + 8), (300, ty + 8)], fill=(*RED, 255), width=5)
    _para(d, 60, ty + 44, editorial or "", body_font(30), INK, MW - 130, 46, max_lines=20)
    # festive footer accents + wordmark
    try:
        _confetti(d, RAIL, MH - 150, MW, MH - 60, 16, _seed(title))
    except Exception:
        pass
    try:
        paste_wordmark(canvas, 60, MH - 70, 220, 40, dark_bg=False, align="left")
    except Exception:
        pass
    return canvas.convert("RGB")


def _spotlight_card(canvas: Image.Image, y0: int, entry: dict, palette: list[tuple], flip: bool) -> None:
    """One teammate spotlight inside a white rounded card starting at y0 (card height ~510)."""
    card_h = 512
    pad = 44
    d = ImageDraw.Draw(canvas)
    d.rounded_rectangle([pad, y0, MW - pad, y0 + card_h], radius=34, fill=(*WHITE, 255))
    # circular photo on one side
    size = 300
    photo = entry.get("photo")
    av = _circle_photo(photo, size) if photo else None
    cx = (MW - pad - 40 - size) if flip else (pad + 40)
    cy = y0 + (card_h - size) // 2
    if av is not None:
        canvas.alpha_composite(av, (cx, cy))
    else:
        d.ellipse([cx, cy, cx + size, cy + size], fill=(*CREAM, 255), outline=(*NAVY, 60), width=3)
        initials = "".join(w[0] for w in (entry.get("name") or "T R").split()[:2]).upper()
        f = heading_font(96)
        iw = d.textlength(initials, font=f)
        d.text((cx + (size - iw) / 2, cy + size / 2 - 60), initials, font=f, fill=NAVY)

    # text column sits OPPOSITE the photo and never runs under it
    if flip:
        tx = pad + 60
        tw = (MW - pad - 40 - size - 40) - tx
    else:
        tx = pad + 60 + size + 40
        tw = (MW - pad - 40) - tx
    tw = max(200, tw)
    ty = y0 + 42
    name = (entry.get("name") or "").strip() or "Teammate"
    nf = heading_font(50)
    d.text((tx, ty), _ellipsize(d, name, nf, tw), font=nf, fill=NAVY)
    ty += 62
    office = (entry.get("office") or "").strip()
    role = (entry.get("role") or "").strip()
    meta = " · ".join([m for m in (role, office) if m])
    if meta:
        mf = body_font(26)
        d.text((tx, ty), _ellipsize(d, meta, mf, tw), font=mf, fill=RED)
        ty += 44
    # stat chips row — laid out by MEASURED width, stopping before the text column's right edge
    stats = [s for s in (entry.get("stats") or []) if (s or {}).get("label")][:3]
    if stats:
        cx, right = tx, tx + tw
        placed = False
        for s in stats:
            cw, _ch = _chip_size(s.get("label", ""), s.get("value", ""))
            if cx > tx and cx + cw > right:
                break
            _stat_chip(canvas, cx, ty + 62, s.get("label", ""), s.get("value", ""))
            cx += cw + 16
            placed = True
        if placed:
            ty += 138
    d = ImageDraw.Draw(canvas)
    blurb = (entry.get("blurb") or "").strip()
    if blurb:
        _para(d, tx, ty + 6, blurb, body_font(25), SUBINK, tw, 36, max_lines=4)


def _render_spotlights(issue: dict, entries: list[dict]) -> list[Image.Image]:
    palette = _festive_palette(issue.get("theme", ""))
    pages: list[Image.Image] = []
    per_page = 2
    for i in range(0, len(entries), per_page):
        chunk = entries[i:i + per_page]
        canvas = Image.new("RGBA", (MW, MH), (*CREAM, 255))
        d = ImageDraw.Draw(canvas)
        d.rectangle([0, 0, RAIL, MH], fill=(*RED, 255))
        _festoon(d, 90, palette)
        d.text((60, 150), "TEAM SPOTLIGHT", font=heading_font(30), fill=RED)
        d.text((60, 192), "Champions of the Month", font=heading_font(58), fill=NAVY)
        d.line([(60, 270), (360, 270)], fill=(*RED, 255), width=5)
        y0 = 320
        for j, entry in enumerate(chunk):
            _spotlight_card(canvas, y0, entry, palette, flip=(j % 2 == 1))
            y0 += 560
        try:
            paste_wordmark(canvas, 60, MH - 64, 200, 36, dark_bg=False, align="left")
        except Exception:
            pass
        pages.append(canvas.convert("RGB"))
    return pages


def _render_closing(issue: dict) -> Image.Image:
    palette = _festive_palette(issue.get("theme", ""))
    canvas = Image.new("RGBA", (MW, MH), (*NAVY, 255))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, RAIL, MH], fill=(*RED, 255))
    try:
        _confetti(d, RAIL, 80, MW, 260, 26, _seed("close"))
        _confetti(d, RAIL, MH - 300, MW, MH - 80, 26, _seed("close2"))
    except Exception:
        pass
    msg = "Here's to another\nremarkable month."
    yf = script_font(96)
    ty = MH // 2 - 150
    for ln in msg.split("\n"):
        w = d.textlength(ln, font=yf)
        d.text(((MW - w) / 2, ty), ln, font=yf, fill=WHITE)
        ty += 108
    sub = "Thank you, team. — Talentrupt"
    sf = body_font(30)
    w = d.textlength(sub, font=sf)
    d.text(((MW - w) / 2, ty + 20), sub, font=sf, fill=CREAM)
    try:
        paste_wordmark(canvas, (MW - 260) // 2, MH - 170, 260, 46, dark_bg=True, align="center")
    except Exception:
        pass
    return canvas.convert("RGB")


# ---- editorial copy (LLM, best-effort) -----------------------------------------------------------
def _default_editorial(theme: str) -> str:
    t = (theme or "").strip()
    occ = f"this {t.title()} season" if t else "this month"
    return (
        f"As we celebrate {occ}, we're reminded that beyond targets and pipelines, we're a team that grows "
        "together. Every submission, every offer, and every start is a shared win.\n\n"
        "Thank you for the energy, the collaboration, and the heart you bring each day. Here's to carrying "
        "this momentum forward — brighter, bolder, and together."
    )


async def _write_editorial(brand, theme: str, title: str) -> str:
    from ..providers import llm
    if not llm.provider_available():
        return _default_editorial(theme)
    try:
        out = await llm.chat_json([
            {"role": "system", "content":
             "You are the editor of Talentrupt's internal TEAM magazine (Talentrupt is an RPO / recruitment "
             "firm). Write a warm, uplifting EDITORIAL note for this month's issue — exactly 2 short "
             "paragraphs, about 70-95 words total, celebrating the team, the occasion, and momentum. No "
             "headings, no bullet points, no emojis, no hashtags. Separate the two paragraphs with a blank "
             "line. Reply ONLY as JSON: {\"editorial\": \"...\"}."},
            {"role": "user", "content":
             f"Magazine: {title}. Occasion / theme: {theme or 'a productive month'}."},
        ], temperature=0.7)
        txt = ((out or {}).get("editorial") or "").strip()
        return txt or _default_editorial(theme)
    except Exception:
        return _default_editorial(theme)


# ---- public entry point --------------------------------------------------------------------------
async def build_magazine(brand, issue: dict) -> tuple[str, str, dict]:
    """Render the whole issue to a multi-page PDF and return (path, file_name, meta).

    `issue` shape (photos already resolved to bytes by the caller):
      {title, edition, theme, editorial,
       cover: {name, role, photo: bytes|None, headline, tagline, stats: [{label, value}]},
       spotlights: [{name, role, office, blurb, photo: bytes|None, stats: [...]}]}
    """
    title = (issue.get("title") or "Talentrupt Times").strip()
    theme = (issue.get("theme") or "").strip()
    editorial = (issue.get("editorial") or "").strip() or await _write_editorial(brand, theme, title)

    pages: list[Image.Image] = []
    pages.append(_render_cover(issue))
    pages.append(_render_editorial(issue, editorial))
    spotlights = [s for s in (issue.get("spotlights") or []) if (s or {}).get("name")]
    if spotlights:
        pages.extend(_render_spotlights(issue, spotlights))
    pages.append(_render_closing(issue))

    file_name = unique_name("tr-magazine", "pdf")
    sub = storage_subdir("pdfs")
    sub.mkdir(parents=True, exist_ok=True)
    path = sub / file_name
    pages[0].save(str(path), "PDF", save_all=True, append_images=pages[1:], resolution=150.0)

    meta = {
        "url": public_url("pdfs", file_name),
        "format": "pdf",
        "kind": "magazine",
        "pages": len(pages),
        "title": title,
        "edition": issue.get("edition", ""),
        "theme": theme,
    }
    return str(path), file_name, meta
