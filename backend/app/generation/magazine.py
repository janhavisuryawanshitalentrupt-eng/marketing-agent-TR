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
import math

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
    _cutout,
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


def _is_festive(theme: str) -> bool:
    t = (theme or "").lower()
    return any(k in t for k in _FESTIVE)


def _motif_band(canvas: Image.Image, prof, theme: str, y: int) -> None:
    """The top-of-page decorative garland. A FESTIVE theme always keeps its festoon + festive palette (so
    Diwali/Christmas issues are unchanged); otherwise the garland is tinted to the PROFILE's own colours so
    each design's inner pages read as a set. Light accent2 (cream/white) falls back to navy so dots stay
    visible on the light page."""
    d = ImageDraw.Draw(canvas)
    if _is_festive(theme):
        _festoon(d, y, _festive_palette(theme))
        return
    second = prof.accent2 if sum(prof.accent2) < 620 else NAVY   # keep dots visible on a light page
    _festoon(d, y, [prof.accent, second, NAVY, prof.accent])


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
def _cover_split_panel(issue: dict, prof) -> Image.Image:
    """A full-height champion photo on the RIGHT ~54%; a dark left column holds a stacked masthead, the
    champion's name (script), stat chips, and the headline. A magazine-cover look, not a poster."""
    cover = issue.get("cover", {}) or {}
    canvas = Image.new("RGBA", (MW, MH), (*NAVY, 255))
    split = int(MW * 0.46)
    photo = cover.get("photo")
    if photo:
        try:
            src = _cover_fit(_open_photo(photo), MW - split, MH)
            canvas.alpha_composite(src.convert("RGBA"), (split, 0))
        except Exception as e:
            log.warning("magazine split cover photo failed: %s", e)
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, split, MH], fill=(*NAVY, 255))       # solid left column over any bleed
    d.rectangle([split - 6, 0, split, MH], fill=(*prof.accent, 255))
    # stacked masthead
    if not paste_wordmark(canvas, 54, 92, split - 108, 52, dark_bg=True, align="left"):
        d.text((54, 92), "TALENTRUPT", font=font(prof.head_family, 44), fill=WHITE)
    d.text((54, 168), "TIMES", font=font(prof.head_family, 34), fill=prof.accent)
    ed = (issue.get("edition") or "").strip()
    if ed:
        d.text((54, 226), ed.upper()[:24], font=body_font(22), fill=CREAM)
    d.line([(54, 268), (split - 54, 268)], fill=(*prof.accent, 255), width=3)
    name = (cover.get("name") or "").strip()
    nf = script_font(76)
    ny = 300
    for ln in _wrap(d, name, nf, split - 84)[:2]:
        d.text((54, ny), ln, font=nf, fill=WHITE)
        ny += 86
    stats = [s for s in (cover.get("stats") or []) if (s or {}).get("label")][:3]
    sy = ny + 62
    for s in stats:
        _stat_chip(canvas, 54, sy, s.get("label", ""), s.get("value", ""))
        sy += 132
    hl = (cover.get("headline") or "In the Spotlight").strip()
    hf = font(prof.head_family, 50)
    hy = max(sy + 30, MH - 260)
    for ln in _wrap(d, hl, hf, split - 90)[:3]:
        d.text((54, hy), ln, font=hf, fill=WHITE)
        hy += 58
    return canvas.convert("RGB")


def _cover_band_bottom(issue: dict, prof) -> Image.Image:
    """A loud poster cover: an oversized DISPLAY headline top-left, a framed champion photo lower-right, and
    a deep bottom band with the name + tagline. Distinct from the calm framed layout."""
    cover = issue.get("cover", {}) or {}
    canvas = Image.new("RGBA", (MW, MH), (*prof.bg, 255))
    d = ImageDraw.Draw(canvas)
    _rail(canvas, prof)
    if not paste_wordmark(canvas, 54, 70, 260, 46, dark_bg=prof.dark, align="left"):
        d.text((54, 74), "TALENTRUPT", font=font(prof.head_family, 40), fill=prof.ink)
    hl = (cover.get("headline") or "Champions of the Month").strip()
    hf = font("display", 92)
    words = [w for w in hl.split()]
    while hf.size > 48 and max((d.textlength(w, font=hf) for w in words), default=0) > MW - 108:
        hf = font("display", hf.size - 6)
    hy = 190
    for ln in _wrap(d, hl, hf, MW - 108)[:3]:
        d.text((54, hy), ln, font=hf, fill=prof.ink)
        hy += int(hf.size * 1.06)
    # framed photo lower-right
    photo = cover.get("photo")
    if photo:
        try:
            fw, fh = 470, 620
            fx, fy = MW - fw - 44, MH - fh - 320
            src = _cover_fit(_open_photo(photo), fw, fh)
            sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(sh).rounded_rectangle([fx + 8, fy + 12, fx + fw + 8, fy + fh + 12], radius=40,
                                                 fill=(0, 0, 0, 90))
            canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
            canvas.alpha_composite(_rounded(src, 40), (fx, fy))
            ImageDraw.Draw(canvas).rounded_rectangle([fx - 4, fy - 4, fx + fw + 4, fy + fh + 4], radius=44,
                                                     outline=(*prof.on_accent, 255), width=6)
        except Exception as e:
            log.warning("magazine band cover photo failed: %s", e)
    # bottom band: name + tagline
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, MH - 250, MW, MH], fill=(*NAVY, 255))
    d.rectangle([0, MH - 250, RAIL, MH], fill=(*prof.accent, 255))
    name = (cover.get("name") or "").strip()
    if name:
        d.text((54, MH - 226), name, font=script_font(76), fill=WHITE)
    tag = (cover.get("tagline") or "").strip()
    if tag:
        _para(d, 54, MH - 120, tag, body_font(28), CREAM, MW - 108, 38, max_lines=2)
    return canvas.convert("RGB")


def _grain(canvas: Image.Image, strength: int = 9) -> None:
    """A subtle paper-grain overlay — the print/editorial texture the reference magazines have."""
    try:
        import numpy as np
        n = np.random.RandomState(_seed("grain")).randint(0, 255, (MH, MW), dtype="uint8")
        noise = Image.fromarray(n, "L").convert("RGBA")
        noise.putalpha(strength)
        canvas.alpha_composite(noise)
    except Exception:
        pass


def _person_cutout_layer(photo, target_h: int):
    """A background-removed, height-fitted person layer + True when the cut-out really worked (prod: hosted
    remove.bg; dev: numpy studio keyer). Returns (None, False) so the caller frames the photo instead."""
    try:
        import numpy as np
        cut = _cutout(_open_photo(photo))
        if cut.mode != "RGBA":
            return None, False
        al = np.asarray(cut.split()[-1])
        ok = int(al.min()) < 245 and 0.12 <= float((al > 127).mean()) <= 0.92
        if not ok:
            return None, False
        bbox = cut.getbbox()
        cut = cut.crop(bbox) if bbox else cut
        scale = target_h / cut.height
        return cut.resize((max(1, int(cut.width * scale)), target_h), Image.LANCZOS), True
    except Exception:
        return None, False


def _big_stat(canvas: Image.Image, x: int, y: int, value: str, label: str, color: tuple,
              align: str = "left", max_w: int = 300) -> None:
    """A reference-style stat callout: a BIG coloured number with a bold label beneath (not a small pill)."""
    d = ImageDraw.Draw(canvas)
    vf = font("display", 66)
    val = str(value)[:8]
    while d.textlength(val, font=vf) > max_w and vf.size > 34:
        vf = font("display", vf.size - 6)
    lf = heading_font(26)
    vx = (x - d.textlength(val, font=vf)) if align == "right" else x
    d.text((vx, y), val, font=vf, fill=(*color, 255))
    ly = y + vf.size + 6
    for i, ln in enumerate(_wrap(d, str(label).upper(), lf, max_w)[:2]):
        lx = (x - d.textlength(ln, font=lf)) if align == "right" else x
        d.text((lx, ly + i * 30), ln, font=lf, fill=(*NAVY, 255))


def _cover_spotlight(issue: dict, prof) -> Image.Image:
    """The signature TR-magazine cover, learned from the real reference issues: a compact newspaper masthead,
    a HUGE display TITLE, the champion CUT-OUT overlapping it, big stat numbers flanking them, a 'Top
    Performer' eyebrow + name + blurb in a bottom band, over a lightly grained page."""
    cover = issue.get("cover", {}) or {}
    canvas = Image.new("RGBA", (MW, MH), (*prof.page_bg, 255))
    _grain(canvas)
    d = ImageDraw.Draw(canvas)
    # 1) compact newspaper masthead
    ed = (issue.get("edition") or "").strip()
    d.text((44, 60), "SPECIAL EDITION", font=font("serif", 26), fill=NAVY)
    if ed:
        d.text((MW - 44 - d.textlength(ed.upper()[:20], font=body_font(24)), 66), ed.upper()[:20],
               font=body_font(24), fill=SUBINK)
    mf = font("serif", 78)
    tw = d.textlength("TALENTRUPT", font=mf)
    tmw = d.textlength(" TIMES", font=mf)
    mx = (MW - tw - tmw) / 2
    d.text((mx, 100), "TALENTRUPT", font=mf, fill=NAVY)
    d.text((mx + tw, 100), " TIMES", font=mf, fill=prof.accent)
    d.line([(44, 196), (MW - 44, 196)], fill=(*NAVY, 255), width=4)
    d.line([(44, 204), (MW - 44, 204)], fill=(*NAVY, 255), width=2)
    # 2) HUGE display title (the cover headline), the person will overlap its lower half
    title = (cover.get("headline") or "Best Performer").strip().upper()
    title_family = "serif" if prof.head_family == "serif" else "display"   # elegant serif for editorial profiles
    tf = font(title_family, 150)
    words = title.split()
    while tf.size > 70 and max((d.textlength(w, font=tf) for w in words), default=0) > MW - 80:
        tf = font(title_family, tf.size - 8)
    tlines = _wrap(d, title, tf, MW - 80)[:3]
    if len(tlines) >= 3:                       # a long title -> a touch smaller so 3 lines sit above the person
        tf = font(title_family, int(tf.size * 0.82))
        tlines = _wrap(d, title, tf, MW - 80)[:3]
    ty = 232 if len(tlines) >= 3 else 236
    for ln in tlines:
        d.text(((MW - d.textlength(ln, font=tf)) / 2, ty), ln, font=tf, fill=(*prof.accent, 255))
        ty += int(tf.size * 0.96)
    # 3) champion — cut-out overlapping the title, else a clean framed portrait
    photo = cover.get("photo")
    person_bottom = MH - 250
    if photo:
        layer, ok = _person_cutout_layer(photo, target_h=int(MH * 0.62))
        if ok and layer is not None:
            px = (MW - layer.width) // 2
            sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(sh).ellipse([px + int(layer.width * 0.12), person_bottom - 44,
                                        px + int(layer.width * 0.88), person_bottom - 6], fill=(0, 0, 0, 70))
            canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(14)))
            canvas.alpha_composite(layer, (px, person_bottom - layer.height))
        else:
            try:
                fw, fh = 420, 560
                fx, fy = (MW - fw) // 2, person_bottom - fh
                canvas.alpha_composite(_rounded(_cover_fit(_open_photo(photo), fw, fh), 28), (fx, fy))
                ImageDraw.Draw(canvas).rounded_rectangle([fx - 4, fy - 4, fx + fw + 4, fy + fh + 4],
                                                         radius=32, outline=(*prof.accent, 255), width=6)
            except Exception as e:
                log.warning("spotlight cover photo failed: %s", e)
    # 4) big stat callouts flanking the champion (up to 3 per side)
    stats = [s for s in (cover.get("stats") or []) if (s or {}).get("label") and (s or {}).get("value")][:6]
    left, right = stats[0::2][:3], stats[1::2][:3]
    for i, s in enumerate(left):
        _big_stat(canvas, 54, 560 + i * 172, s.get("value", ""), s.get("label", ""), prof.accent,
                  align="left", max_w=260)
    for i, s in enumerate(right):
        _big_stat(canvas, MW - 54, 560 + i * 172, s.get("value", ""), s.get("label", ""), prof.accent,
                  align="right", max_w=260)
    # 5) bottom band: Top-Performer eyebrow + name + blurb
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, MH - 250, MW, MH], fill=(*NAVY, 255))
    d.rectangle([0, MH - 250, RAIL, MH], fill=(*prof.accent, 255))
    eb = "TOP PERFORMER"
    ef2 = heading_font(24)
    ew = d.textlength(eb, font=ef2)
    d.rounded_rectangle([44, MH - 232, 44 + ew + 36, MH - 190], radius=21, fill=(*prof.accent, 255))
    d.text((62, MH - 226), eb, font=ef2, fill=WHITE)
    name = (cover.get("name") or "").strip()
    if name:
        d.text((44, MH - 178), name, font=font("display", 58), fill=WHITE)
    blurb = (cover.get("tagline") or cover.get("blurb") or "").strip()
    if blurb:
        _para(d, 44, MH - 104, blurb, body_font(24), CREAM, MW - 88, 32, max_lines=2)
    return canvas.convert("RGB")


def _render_cover(issue: dict) -> Image.Image:
    prof = _mprof(issue)
    if prof.cover_style == "split_panel":
        return _cover_split_panel(issue, prof)
    if prof.cover_style == "band_bottom":
        return _cover_band_bottom(issue, prof)
    if prof.cover_style in ("framed_right", "framed_left"):
        return _cover_spotlight(issue, prof)   # the reference-style magazine cover (default)
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
    """The editor's note — a bold colored masthead block with a big display title, then a justified body on
    the grained page and a script sign-off (the reference editorial look)."""
    prof = _mprof(issue)
    theme = (issue.get("theme") or "").strip()
    canvas = Image.new("RGBA", (MW, MH), (*prof.page_bg, 255))
    _grain(canvas, 7)
    d = ImageDraw.Draw(canvas)
    # colored masthead block with eyebrow + big display title
    block_h = 452
    d.rectangle([0, 0, MW, block_h], fill=(*NAVY, 255))
    d.rectangle([0, 0, RAIL, block_h], fill=(*prof.accent, 255))
    d.text((60, 92), "FROM THE EDITOR'S DESK", font=heading_font(28), fill=(*prof.accent, 255))
    title = (f"Happy {theme.title()}!" if theme else "A Note From The Desk")
    tfam = "serif" if prof.head_family == "serif" else "display"
    tf = font(tfam, 96)
    words = title.split()
    while tf.size > 52 and max((d.textlength(w, font=tf) for w in words), default=0) > MW - 120:
        tf = font(tfam, tf.size - 8)
    ty = 156
    for ln in _wrap(d, title, tf, MW - 120)[:3]:
        d.text((60, ty), ln, font=tf, fill=WHITE)
        ty += int(tf.size * 0.98)
    # justified-measure body on the light lower page
    _para(d, 72, block_h + 60, editorial or "", body_font(30), INK, MW - 144, 48, max_lines=15)
    d.text((72, MH - 156), "— The Talentrupt Team", font=script_font(50), fill=(*prof.accent, 255))
    try:
        paste_wordmark(canvas, MW - 258, MH - 64, 200, 34, dark_bg=False, align="left")
    except Exception:
        pass
    return canvas.convert("RGB")


def _outline(canvas: Image.Image, layer: Image.Image, x: int, y: int, color: tuple, w: int = 5) -> None:
    """A coloured 'sticker' edge around a cut-out person (the reference outline) — the silhouette pasted at
    8 offsets behind the real person."""
    try:
        sil = Image.new("RGBA", layer.size, (*color, 255))
        sil.putalpha(layer.split()[-1])
        for dx, dy in ((-w, 0), (w, 0), (0, -w), (0, w), (-w, -w), (w, w), (-w, w), (w, -w)):
            canvas.alpha_composite(sil, (x + dx, y + dy))
    except Exception:
        pass


def _hand_arrow(canvas: Image.Image, p0, p1, color: tuple, bend: int = 60) -> None:
    """A small hand-drawn curved arrow (quadratic bezier + arrowhead) — the reference doodle that points
    from the name toward the person."""
    d = ImageDraw.Draw(canvas, "RGBA")
    cx, cy = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2 - bend
    pts = []
    for k in range(21):
        t = k / 20
        pts.append(((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * cx + t ** 2 * p1[0],
                    (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * cy + t ** 2 * p1[1]))
    for i in range(len(pts) - 1):
        d.line([pts[i], pts[i + 1]], fill=(*color, 255), width=4)
    (ex, ey), (bx, by) = pts[-1], pts[-3]
    ang = math.atan2(ey - by, ex - bx)
    for da in (math.radians(148), math.radians(-148)):
        d.line([(ex, ey), (ex + 18 * math.cos(ang + da), ey + 18 * math.sin(ang + da))],
               fill=(*color, 255), width=4)


def _spotlight_card(canvas: Image.Image, y0: int, entry: dict, prof, flip: bool) -> None:
    """One teammate spotlight (reference 'Shining Star' style): a CUT-OUT person with an accent outline on
    an alternating side, a big name, big inline stat numbers, and a blurb — no boxy card."""
    d = ImageDraw.Draw(canvas)
    H = 560
    person_left = flip
    photo = entry.get("photo")
    pw = 0
    if photo:
        layer, ok = _person_cutout_layer(photo, target_h=440)
        if ok and layer is not None:
            pw = layer.width
            px = 54 if person_left else (MW - 54 - pw)
            py = y0 + H - layer.height
            _outline(canvas, layer, px, py, prof.accent, w=5)
            canvas.alpha_composite(layer, (px, py))
        else:
            fw, fh = 300, 384
            pw = fw
            px = 54 if person_left else (MW - 54 - fw)
            py = y0 + (H - fh) // 2
            try:
                canvas.alpha_composite(_rounded(_cover_fit(_open_photo(photo), fw, fh), 24), (px, py))
                ImageDraw.Draw(canvas).rounded_rectangle([px - 4, py - 4, px + fw + 4, py + fh + 4],
                                                         radius=28, outline=(*prof.accent, 255), width=6)
            except Exception:
                pw = 0
    pw = pw or 300
    # text column OPPOSITE the person
    if person_left:
        tx = 54 + pw + 54
        tw = MW - 54 - tx
    else:
        tx = 54
        tw = (MW - 54 - pw - 54) - tx
    tw = max(240, tw)
    d = ImageDraw.Draw(canvas)
    ty = y0 + 26
    name = (entry.get("name") or "Teammate").strip()
    nf = font("display", 46)
    d.text((tx, ty), _ellipsize(d, name, nf, tw), font=nf, fill=(*prof.accent, 255))
    ty += 64
    meta = " · ".join([m for m in ((entry.get("role") or "").strip(), (entry.get("office") or "").strip()) if m])
    if meta:
        d.text((tx, ty), _ellipsize(d, meta, body_font(24), tw), font=body_font(24), fill=NAVY)
        ty += 46
    for s in [s for s in (entry.get("stats") or []) if (s or {}).get("label") and (s or {}).get("value")][:3]:
        vf = font("display", 44)
        v = str(s["value"])[:6]
        d.text((tx, ty), v, font=vf, fill=(*prof.accent, 255))
        d.text((tx + d.textlength(v, font=vf) + 16, ty + 12),
               _ellipsize(d, str(s["label"]).upper(), heading_font(24), tw - 120), font=heading_font(24), fill=NAVY)
        ty += 58
    blurb = (entry.get("blurb") or "").strip()
    if blurb:
        _para(d, tx, ty + 6, blurb, body_font(23), SUBINK, tw, 32, max_lines=4)
    # a small doodle arrow pointing from the text toward the person
    try:
        if person_left:
            _hand_arrow(canvas, (tx - 14, y0 + 70), (54 + pw + 12, y0 + 150), prof.accent, bend=44)
        else:
            _hand_arrow(canvas, (tx + min(tw, 250) + 14, y0 + 70), (MW - 54 - pw - 12, y0 + 150),
                        prof.accent, bend=44)
    except Exception:
        pass


def _render_spotlights(issue: dict, entries: list[dict]) -> list[Image.Image]:
    prof = _mprof(issue)
    pages: list[Image.Image] = []
    per_page = 2
    for i in range(0, len(entries), per_page):
        chunk = entries[i:i + per_page]
        canvas = Image.new("RGBA", (MW, MH), (*prof.page_bg, 255))
        _grain(canvas, 7)
        d = ImageDraw.Draw(canvas)
        _rail(canvas, prof)
        # editorial header: 'SHINING STARS' (display accent) + 'of the month' (script navy)
        hf = font("display", 58)
        d.text((60, 118), "SHINING STARS", font=hf, fill=(*prof.accent, 255))
        d.text((64, 190), "of the month", font=script_font(52), fill=NAVY)
        d.line([(60, 268), (360, 268)], fill=(*prof.accent, 255), width=5)
        y0 = 312
        for j, entry in enumerate(chunk):
            _spotlight_card(canvas, y0, entry, prof, flip=(j % 2 == 1))
            y0 += 588
        try:                                   # wordmark opposite the last person (which alternates sides)
            last_left = ((len(chunk) - 1) % 2 == 1)
            wx = (MW - 260) if last_left else 60
            paste_wordmark(canvas, wx, MH - 62, 200, 34, dark_bg=False, align="left")
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
    canvas = Image.new("RGBA", (MW, MH), (*prof.page_bg, 255))
    _grain(canvas, 7)
    d = ImageDraw.Draw(canvas)
    _rail(canvas, prof)
    d.text((60, 118), "AWARD OF THE MONTH", font=heading_font(28), fill=prof.accent)
    title = (award.get("title") or "Champions").strip().upper()
    tfam = "serif" if prof.head_family == "serif" else "display"
    tf = font(tfam, 78)
    words = title.split()
    while tf.size > 46 and max((d.textlength(w, font=tf) for w in words), default=0) > MW - 120:
        tf = font(tfam, tf.size - 6)
    ty = 158
    for ln in _wrap(d, title, tf, MW - 120)[:2]:
        d.text((60, ty), ln, font=tf, fill=(*prof.accent, 255))
        ty += int(tf.size * 0.98)
    d.line([(60, ty + 6), (330, ty + 6)], fill=(*NAVY, 255), width=5)
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
        # name (a small red banner) + BIG display value on the right
        d = ImageDraw.Draw(canvas)
        tx, tw = 452, (MW - 90) - 452
        nm = _ellipsize(d, w.get("name") or "Teammate", heading_font(40), tw - 40)
        nw = d.textlength(nm, font=heading_font(40))
        d.rounded_rectangle([tx, y0 + 58, tx + nw + 40, y0 + 116], radius=12, fill=(*prof.accent, 255))
        d.text((tx + 20, y0 + 68), nm, font=heading_font(40), fill=WHITE)
        vf = font("display", 100)
        d.text((tx, y0 + 138), _ellipsize(d, str(w.get("value") or ""), vf, tw), font=vf,
               fill=(*NAVY, 255))
        if caption:
            d.text((tx, y0 + 262), caption.upper(), font=heading_font(26), fill=prof.accent)
        y0 += card_h + gap
    try:
        paste_wordmark(canvas, 60, MH - 60, 200, 36, dark_bg=False, align="left")
    except Exception:
        pass
    return canvas.convert("RGB")


def _render_category_champions(issue: dict, cat_awards: list[dict]) -> Image.Image:
    """A single page with three columns (LI / Non-Tech / Tech), each a compact top-3 leaderboard."""
    prof = _mprof(issue)
    canvas = Image.new("RGBA", (MW, MH), (*prof.page_bg, 255))
    _grain(canvas, 7)
    d = ImageDraw.Draw(canvas)
    _rail(canvas, prof)
    d.text((60, 118), "CATEGORY CHAMPIONS", font=heading_font(28), fill=prof.accent)
    tfam = "serif" if prof.head_family == "serif" else "display"
    d.text((60, 158), "TOP OF THEIR FIELD", font=font(tfam, 72), fill=(*prof.accent, 255))
    d.line([(60, 254), (330, 254)], fill=(*NAVY, 255), width=5)

    cols = cat_awards[:3]
    left, right = 44, MW - 44
    gap = 20
    colw = (right - left - gap * (len(cols) - 1)) // max(1, len(cols))
    y0, col_h = 322, 700
    for i, aw in enumerate(cols):
        x = left + i * (colw + gap)
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle([x, y0, x + colw, y0 + col_h], radius=26, fill=(*WHITE, 255))
        # header band — the category name only (strip any "Categories — " prefix), clipped to the column
        raw = (aw.get("title") or "").strip()
        for sep in ("—", "–", ":", " - "):
            if sep in raw:
                raw = raw.split(sep)[-1].strip()
                break
        d.rounded_rectangle([x, y0, x + colw, y0 + 72], radius=26, fill=(*NAVY, 255))
        d.rectangle([x, y0 + 40, x + colw, y0 + 72], fill=(*NAVY, 255))
        lf = heading_font(36)
        label = _ellipsize(d, raw or "Category", lf, colw - 28)
        lw = d.textlength(label, font=lf)
        d.text((x + (colw - lw) / 2, y0 + 18), label, font=lf, fill=WHITE)
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
    _grain(canvas, 8)
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, RAIL, MH], fill=(*prof.accent, 255))
    try:
        _confetti(d, RAIL, 80, MW, 260, 26, _seed("close"))
        _confetti(d, RAIL, MH - 300, MW, MH - 80, 26, _seed("close2"))
    except Exception:
        pass
    thanks = "THANK YOU"
    tf = font("display", 120)
    d.text(((MW - d.textlength(thanks, font=tf)) / 2, MH // 2 - 320), thanks, font=tf, fill=(*prof.accent, 255))
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
