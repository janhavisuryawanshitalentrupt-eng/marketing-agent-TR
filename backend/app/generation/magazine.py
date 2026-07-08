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

from . import designs
from .common import (
    body_font,
    font,
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
SILVER = (0xB4, 0xBC, 0xC6)
BRONZE = (0xCD, 0x7F, 0x32)
MEDALS = [GOLD, SILVER, BRONZE]     # 1st / 2nd / 3rd place accent colours

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


# ---- design PROFILE skin -------------------------------------------------------------------------
# A magazine picks a DesignProfile (auto-rotated per owner, never repeats the last) so consecutive issues
# look designed, not stamped. The profile only restyles the CHROME — page fill, spine, decorative accent
# colour, masthead/title TYPE, cover photo side. All DATA (award ranks, medal colours, stat values, real
# photos, the festive garland palette on holiday themes) is untouched.
def _mprof(issue: dict):
    return (issue or {}).get("_prof") or designs.PROFILES[designs.DEFAULT_PROFILE]


def _rail(canvas: Image.Image, prof) -> None:
    """The page spine per profile: a red/navy left bar, a thin navy bar, top+bottom rules, or none."""
    d = ImageDraw.Draw(canvas)
    style = prof.rail
    if style == "none":
        return
    if style == "top_bottom_rules":
        d.rectangle([0, 0, MW, 6], fill=(*prof.accent, 255))
        d.rectangle([0, MH - 6, MW, MH], fill=(*prof.accent, 255))
        return
    if style == "thin_navy":
        d.rectangle([0, 0, 7, MH], fill=(*NAVY, 255))
        return
    col = NAVY if style == "left_navy" else prof.accent   # left_red -> the profile accent
    d.rectangle([0, 0, RAIL, MH], fill=(*col, 255))


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


def _masthead(canvas: Image.Image, edition: str, prof=None) -> None:
    prof = prof or designs.PROFILES[designs.DEFAULT_PROFILE]
    d = ImageDraw.Draw(canvas)
    tf = font(prof.head_family, 84)
    title = "TALENTRUPT"
    tw = d.textlength(title, font=tf)
    tx = (MW - tw) // 2
    d.text((tx, 66), title, font=tf, fill=NAVY)
    sf = font(prof.head_family, 38)
    stw = d.textlength("TIMES", font=sf)
    d.text((tx + tw - stw, 150), "TIMES", font=sf, fill=prof.accent)
    ef = body_font(24)
    if edition:
        # Below the masthead (a wide display masthead would otherwise collide with a top-left edition).
        d.text((40, 182), edition.upper()[:26], font=ef, fill=SUBINK)
    d.line([(40, 214), (MW - 40, 214)], fill=(*prof.accent, 255), width=4)


# ---- page renderers ------------------------------------------------------------------------------
def _render_cover(issue: dict) -> Image.Image:
    prof = _mprof(issue)
    palette = _festive_palette(issue.get("theme", ""))
    canvas = Image.new("RGBA", (MW, MH), (*prof.page_bg, 255))
    d = ImageDraw.Draw(canvas)
    _rail(canvas, prof)
    # festive confetti in reserved zones (top band + left gutter), theme-tinted
    try:
        _confetti(d, RAIL, 0, MW, 60, 22, _seed(issue.get("title", "")))
    except Exception:
        pass
    _masthead(canvas, issue.get("edition", ""), prof)

    cover = issue.get("cover", {}) or {}
    # 1) champion photo — a clean framed PORTRAIT, on the side the profile prefers (framed_left flips it so a
    # run of issues varies). A framed crop always shows the real face (a headshot rarely cuts out cleanly).
    photo_left = prof.cover_style == "framed_left"
    text_x = (MW - 490) if photo_left else 46          # name/stats column opposite the photo
    photo = cover.get("photo")
    if photo:
        try:
            src = _open_photo(photo)
            fw, fh, fy, r = 500, 900, 300, 46
            fx = 24 if photo_left else MW - 524
            sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(sh).rounded_rectangle([fx + 8, fy + 14, fx + fw + 8, fy + fh + 14], radius=r,
                                                 fill=(11, 34, 58, 95))
            canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(18)))
            canvas.alpha_composite(_rounded(_cover_fit(src, fw, fh), r), (fx, fy))
            ImageDraw.Draw(canvas).rounded_rectangle([fx - 5, fy - 5, fx + fw + 5, fy + fh + 5],
                                                     radius=r + 5, outline=(*WHITE, 255), width=8)
        except Exception as e:
            log.warning("magazine cover photo failed: %s", e)

    # 2) champion name (script) upper, in the text column
    d = ImageDraw.Draw(canvas)
    name = (cover.get("name") or "").strip()
    if name:
        nf = script_font(104)
        ny = 288
        for ln in _wrap(d, name, nf, int(MW * 0.44))[:2]:
            d.text((text_x, ny), ln, font=nf, fill=prof.accent)
            ny += 96

    # 3) stat callouts down the text column (centred, laid out by measured width)
    stats = [s for s in (cover.get("stats") or []) if (s or {}).get("label")][:6]
    col_cx = (MW - 245) if photo_left else int(MW * 0.22)
    sy = 560
    for s in stats:
        cw, _ch = _chip_size(s.get("label", ""), s.get("value", ""))
        _stat_chip(canvas, int(col_cx - cw / 2), sy, s.get("label", ""), s.get("value", ""))
        sy += 150

    # 4) headline + tagline in a navy bottom band
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 1256, MW, MH], fill=(*NAVY, 255))
    d.rectangle([0, 1256, RAIL, MH], fill=(*prof.accent, 255))
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
    prof = _mprof(issue)
    palette = _festive_palette(issue.get("theme", ""))
    canvas = Image.new("RGBA", (MW, MH), (*prof.page_bg, 255))
    d = ImageDraw.Draw(canvas)
    _rail(canvas, prof)
    _festoon(d, 96, palette)
    theme = (issue.get("theme") or "").strip()
    kicker = "EDITOR'S NOTE"
    d.text((60, 190), kicker, font=heading_font(26), fill=prof.accent)
    title = (f"Happy {theme.title()}!" if theme else "A Note From The Desk")
    tf = font(prof.head_family, 72)
    ty = 234
    for ln in _wrap(d, title, tf, MW - 120)[:2]:
        d.text((60, ty), ln, font=tf, fill=NAVY)
        ty += 78
    d.line([(60, ty + 8), (300, ty + 8)], fill=(*prof.accent, 255), width=5)
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


def _spotlight_card(canvas: Image.Image, y0: int, entry: dict, palette: list[tuple], flip: bool,
                    _accent: tuple = RED) -> None:
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
        d.text((tx, ty), _ellipsize(d, meta, mf, tw), font=mf, fill=_accent)
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
    prof = _mprof(issue)
    palette = _festive_palette(issue.get("theme", ""))
    tf = font(prof.head_family, 58)
    pages: list[Image.Image] = []
    per_page = 2
    for i in range(0, len(entries), per_page):
        chunk = entries[i:i + per_page]
        canvas = Image.new("RGBA", (MW, MH), (*prof.page_bg, 255))
        d = ImageDraw.Draw(canvas)
        _rail(canvas, prof)
        _festoon(d, 90, palette)
        d.text((60, 150), "TEAM SPOTLIGHT", font=heading_font(30), fill=prof.accent)
        d.text((60, 192), "Champions of the Month", font=tf, fill=NAVY)
        d.line([(60, 270), (360, 270)], fill=(*prof.accent, 255), width=5)
        y0 = 320
        for j, entry in enumerate(chunk):
            _spotlight_card(canvas, y0, entry, palette, flip=(j % 2 == 1), _accent=prof.accent)
            y0 += 560
        try:
            paste_wordmark(canvas, 60, MH - 64, 200, 36, dark_bg=False, align="left")
        except Exception:
            pass
        pages.append(canvas.convert("RGB"))
    return pages


def _medal_circle(canvas: Image.Image, cx: int, cy: int, r: int, rank: int) -> None:
    """A coloured rank medallion (gold/silver/bronze) with the place number centred inside."""
    d = ImageDraw.Draw(canvas)
    col = MEDALS[(rank - 1) % len(MEDALS)]
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*col, 255), outline=(*WHITE, 255), width=max(3, r // 14))
    f = heading_font(int(r * 1.15))
    num = str(rank)
    tw = d.textlength(num, font=f)
    d.text((cx - tw / 2, cy - r * 0.72), num, font=f, fill=NAVY)


def _photo_or_initials(canvas: Image.Image, cx: int, cy: int, size: int, entry: dict) -> None:
    """Centre a circular real photo at (cx, cy); fall back to initials on a cream disc."""
    d = ImageDraw.Draw(canvas)
    photo = entry.get("photo")
    av = _circle_photo(photo, size) if photo else None
    x0, y0 = int(cx - size / 2), int(cy - size / 2)
    if av is not None:
        canvas.alpha_composite(av, (x0, y0))
        return
    d.ellipse([x0, y0, x0 + size, y0 + size], fill=(*CREAM, 255), outline=(*NAVY, 60), width=3)
    initials = "".join(w[0] for w in (entry.get("name") or "T R").split()[:2]).upper()
    f = heading_font(int(size * 0.42))
    iw = d.textlength(initials, font=f)
    d.text((cx - iw / 2, cy - size * 0.26), initials, font=f, fill=NAVY)


_UNIT_CAPTION = {"margin": "Total margin", "placements": "Placements",
                 "efficiency": "Per placement", "category": "Margin"}


def _render_award_podium(issue: dict, award: dict) -> Image.Image:
    """A full page for one headline award: kicker + title + a 3-place leaderboard of real people."""
    prof = _mprof(issue)
    palette = _festive_palette(issue.get("theme", ""))
    canvas = Image.new("RGBA", (MW, MH), (*prof.page_bg, 255))
    d = ImageDraw.Draw(canvas)
    _rail(canvas, prof)
    _festoon(d, 92, palette)
    d.text((60, 150), "AWARD OF THE MONTH", font=heading_font(28), fill=prof.accent)
    title = (award.get("title") or "Champions").strip()
    tf = font(prof.head_family, 62)
    ty = 194
    for ln in _wrap(d, title, tf, MW - 130)[:2]:
        d.text((60, ty), ln, font=tf, fill=NAVY)
        ty += 70
    d.line([(60, ty + 6), (330, ty + 6)], fill=(*prof.accent, 255), width=5)
    caption = _UNIT_CAPTION.get(award.get("unit", ""), "")

    winners = [w for w in (award.get("winners") or []) if (w or {}).get("name")][:3]
    y0 = max(ty + 44, 372)
    card_h, gap = 336, 22
    for w in winners:
        rank = int(w.get("rank") or 1)
        d = ImageDraw.Draw(canvas)
        # card + soft shadow
        sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([48, y0 + 8, MW - 40, y0 + card_h + 8], radius=32,
                                             fill=(11, 34, 58, 55))
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(9)))
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle([44, y0, MW - 44, y0 + card_h], radius=32, fill=(*WHITE, 255))
        # left medal accent bar
        d.rounded_rectangle([44, y0, 74, y0 + card_h], radius=32, fill=(*MEDALS[(rank - 1) % 3], 255))
        d.rectangle([60, y0, 74, y0 + card_h], fill=(*MEDALS[(rank - 1) % 3], 255))
        cy = y0 + card_h // 2
        _medal_circle(canvas, 150, y0 + 74, 52, rank)
        _photo_or_initials(canvas, 300, cy, 208, w)
        # name + value on the right
        d = ImageDraw.Draw(canvas)
        tx, tw = 452, (MW - 90) - 452
        d.text((tx, y0 + 68), _ellipsize(d, w.get("name") or "Teammate", heading_font(52), tw),
               font=heading_font(52), fill=NAVY)
        vf = heading_font(96)
        d.text((tx, y0 + 132), _ellipsize(d, str(w.get("value") or ""), vf, tw), font=vf,
               fill=(*NAVY, 255))
        if caption:
            d.text((tx, y0 + 250), caption.upper(), font=body_font(28), fill=prof.accent)
        y0 += card_h + gap
    try:
        paste_wordmark(canvas, 60, MH - 60, 200, 36, dark_bg=False, align="left")
    except Exception:
        pass
    return canvas.convert("RGB")


def _render_category_champions(issue: dict, cat_awards: list[dict]) -> Image.Image:
    """A single page with three columns (LI / Non-Tech / Tech), each a compact top-3 leaderboard."""
    prof = _mprof(issue)
    palette = _festive_palette(issue.get("theme", ""))
    canvas = Image.new("RGBA", (MW, MH), (*prof.page_bg, 255))
    d = ImageDraw.Draw(canvas)
    _rail(canvas, prof)
    _festoon(d, 92, palette)
    d.text((60, 150), "CATEGORY CHAMPIONS", font=heading_font(28), fill=prof.accent)
    d.text((60, 194), "Top of Their Field", font=font(prof.head_family, 62), fill=NAVY)
    d.line([(60, 268), (330, 268)], fill=(*prof.accent, 255), width=5)

    cols = cat_awards[:3]
    left, right = 44, MW - 44
    gap = 20
    colw = (right - left - gap * (len(cols) - 1)) // max(1, len(cols))
    y0, col_h = 322, 700
    for i, aw in enumerate(cols):
        x = left + i * (colw + gap)
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle([x, y0, x + colw, y0 + col_h], radius=26, fill=(*WHITE, 255))
        # header band
        label = (aw.get("title") or "").split("—")[-1].strip() or "Category"
        d.rounded_rectangle([x, y0, x + colw, y0 + 72], radius=26, fill=(*NAVY, 255))
        d.rectangle([x, y0 + 40, x + colw, y0 + 72], fill=(*NAVY, 255))
        lf = heading_font(38)
        lw = d.textlength(label, font=lf)
        d.text((x + (colw - lw) / 2, y0 + 16), label, font=lf, fill=WHITE)
        winners = [w for w in (aw.get("winners") or []) if (w or {}).get("name")][:3]
        # #1 gets a photo
        cy = y0 + 190
        if winners:
            _photo_or_initials(canvas, x + colw // 2, cy, 150, winners[0])
        d = ImageDraw.Draw(canvas)
        ry = y0 + 296
        for w in winners:
            rank = int(w.get("rank") or 1)
            _medal_circle(canvas, x + 42, ry + 30, 26, rank)
            d = ImageDraw.Draw(canvas)
            nm = _ellipsize(d, w.get("name") or "", heading_font(30), colw - 96)
            d.text((x + 82, ry + 8), nm, font=heading_font(30), fill=NAVY)
            d.text((x + 82, ry + 46), str(w.get("value") or ""), font=heading_font(38),
                   fill=(*MEDALS[(rank - 1) % 3], 255))
            ry += 118
    try:
        paste_wordmark(canvas, 60, MH - 60, 200, 36, dark_bg=False, align="left")
    except Exception:
        pass
    return canvas.convert("RGB")


def _render_closing(issue: dict) -> Image.Image:
    prof = _mprof(issue)
    palette = _festive_palette(issue.get("theme", ""))
    # Closing stays a dark, celebratory page; midnight goes near-black, others navy.
    close_bg = prof.bg if prof.key == "midnight" else NAVY
    canvas = Image.new("RGBA", (MW, MH), (*close_bg, 255))
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, RAIL, MH], fill=(*prof.accent, 255))
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
async def build_magazine(brand, issue: dict, profile: str | None = None,
                         owner: str = "") -> tuple[str, str, dict]:
    """Render the whole issue to a multi-page PDF and return (path, file_name, meta).

    A DESIGN PROFILE (palette + typography + spine + cover side) is auto-rotated per owner so consecutive
    issues look designed, not stamped; `profile` forces a specific one. Only the CHROME changes — award
    ranks, medal colours, stat values, real photos and the festive garland are untouched.

    `issue` shape (photos already resolved to bytes by the caller):
      {title, edition, theme, editorial,
       cover: {name, role, photo: bytes|None, headline, tagline, stats: [{label, value}]},
       spotlights: [{name, role, office, blurb, photo: bytes|None, stats: [...]}]}
    """
    title = (issue.get("title") or "Talentrupt Times").strip()
    theme = (issue.get("theme") or "").strip()
    prof = designs.resolve_profile(profile) or designs.pick_profile(owner, "magazine")
    issue["_prof"] = prof                         # read by every _render_* via _mprof(issue)
    editorial = (issue.get("editorial") or "").strip() or await _write_editorial(brand, theme, title)

    pages: list[Image.Image] = []
    pages.append(_render_cover(issue))
    pages.append(_render_editorial(issue, editorial))
    # Award podium pages (award-report format only): a full page per headline award, then a single
    # combined page for the per-category champions.
    awards = [a for a in (issue.get("awards") or []) if (a or {}).get("winners")]
    for aw in awards:
        if aw.get("unit") != "category":
            pages.append(_render_award_podium(issue, aw))
    cat_awards = [a for a in awards if a.get("unit") == "category"]
    if cat_awards:
        pages.append(_render_category_champions(issue, cat_awards))
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
        "profile": prof.key,
        "profile_name": prof.name,
    }
    return str(path), file_name, meta
