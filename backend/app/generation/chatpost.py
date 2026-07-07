"""CHAT-ONLY Talentrupt post engine — reproduces the brand's own social-post design language.

Scoped to the CHAT surface (never campaign or magazine). The APP draws every text / brand element
crisply with Pillow (wordmark, headline with ONE red keyword, kicker pill, stat cards, footer, corner
accents); gpt-image-2 supplies ONLY the background imagery for photographic/observance posts. A real
person (optional) is composited AS-IS from their actual photo — faces are never AI-generated.

Design language distilled from Talentrupt's own posts:
  • deep navy #0B3559, coral red #F6404C, warm cream #EBE9DF, white
  • wordmark at the top; bold heavy headline with exactly one word flipped to coral red
  • red pill kicker, "•••" divider, stat cards (navy/red/white), red-circle footer (website/contact)
  • tasteful corner accents only: a diagonal-line filled circle, a dotted grid, a small red burst
"""
from __future__ import annotations

import io
import logging
import math
import random
import re

from PIL import Image, ImageDraw, ImageFilter

from ..models import Brand
from .common import (
    body_font,
    heading_font,
    paste_wordmark,
    public_url,
    script_font,
    storage_subdir,
    unique_name,
)
from .teampost import CREAM, NAVY, NAVY2, RED, WHITE, _cover_fit, _cutout, _enhance_photo, _wrap

log = logging.getLogger("talentrupt.chatpost")

W = H = 1080
PAD = 84
INK = (0x14, 0x22, 0x3A)        # near-navy body ink on light backgrounds
SUBINK = (0x51, 0x60, 0x74)     # muted grey-navy subline on light
CARD_NAVY = NAVY
CARD_RED = RED

_TEMPLATES = ("statement", "stat", "hero", "observance")


# --------------------------------------------------------------------------------------------------
# Content planning (LLM, grounded in the concept; never fabricates numbers)
# --------------------------------------------------------------------------------------------------
async def _plan(brand: Brand | None, concept: str, count: int, has_person: bool) -> list[dict]:
    from ..providers import llm
    tagline = (brand.tagline if brand and brand.tagline else "RPO Done Right")
    if llm.provider_available():
        sys = (
            "You are the in-house art director for TALENTRUPT (an offshore RPO / recruitment firm; tagline "
            "'RPO Done Right'; brand palette deep navy, coral red, cream). Plan a single-image SOCIAL POST "
            "for the topic below, in Talentrupt's own house style. Return ONLY JSON: {\"variations\":[...]} "
            f"with EXACTLY {count} item(s). Each item:\n"
            '- "template": one of "statement" (bold headline poster), "stat" (headline + 2-3 stat cards), '
            '"observance" (a holiday / awareness-day / wellness / seasonal greeting over a themed photo). '
            + ("Since a REAL PERSON is featured, ALWAYS use \"hero\".\n" if has_person else
               'Use "stat" ONLY when the TOPIC itself supplies real numbers; never invent numbers.\n')
            + '- "headline": <= 8 words, punchy, matches the topic\n'
            '- "red_word": ONE word (or short 2-word phrase) taken verbatim FROM the headline, to flip coral '
            "red — the most important word\n"
            '- "subtext": one supporting line, <= 14 words\n'
            '- "kicker": <= 4 words for a small pill above the headline (e.g. "LET\'S TALK HIRING", "TIME TO '
            'REFRESH"), or ""\n'
            '- "stats": [] normally; for template "stat" up to 3 {"value","label"} — value COPIED VERBATIM '
            "from a number in the topic; NEVER invented. If the topic has no real numbers, use [].\n"
            '- "scene": for "observance" a short vivid description of the themed BACKGROUND photo (e.g. "a '
            'calm misty forest at sunrise", "warm diwali diyas and marigold"); else ""\n'
            '- "bg": "navy" or "cream" (the poster background for non-photo templates)\n'
            '- "cta": short call-to-action for the footer button, or ""\n'
            "RULES: On-topic and literal. NEVER fabricate a statistic. Holidays / wellness / awareness days "
            "take 'observance' with NO stat. Keep it classy and confident."
        )
        usr = f"Topic: {concept}\nProduce {count} distinct variation(s)."
        try:
            data = await llm.chat_json([{"role": "system", "content": sys},
                                        {"role": "user", "content": usr}])
            vs = data.get("variations") if isinstance(data, dict) else None
            if vs:
                return [_coerce(v, concept, tagline, has_person) for v in vs[:count]]
        except Exception:
            pass
    # Deterministic fallback (LLM unavailable / rate-limited): still produce a clean, on-brand plan — a
    # trimmed punchy headline, observance detected by keyword, and NO fabricated stats.
    return [_fallback_plan(concept, tagline, has_person) for _ in range(count)]


_HOLIDAY_RE = re.compile(
    r"\b(diwali|deepavali|holi|navratri|dussehra|dasara|pongal|onam|raksha|rakhi|eid|ramadan|ramzan|"
    r"christmas|xmas|hanukkah|new year|thanksgiving|halloween|valentine|women'?s day|men'?s day|"
    r"mother'?s day|father'?s day|independence day|republic day|labou?r day|earth day|pride|festival|"
    r"holiday|yoga|wellness|mindfulness|meditation|anniversary|birthday|season'?s greetings)\b", re.I)


def _fallback_plan(concept: str, tagline: str, has_person: bool) -> dict:
    c = (concept or "").strip()
    m = _HOLIDAY_RE.search(c)
    observance = bool(m) and not has_person
    head = re.split(r"[.!?\n]", c)[0].strip() or c or "RPO Done Right"
    words = head.split()
    if len(words) > 9:
        head = " ".join(words[:9])
    v = {"template": "observance" if observance else ("hero" if has_person else "statement"),
         "headline": head, "subtext": tagline, "scene": c, "bg": "navy"}
    if observance:
        v["red_word"] = m.group(0)
    return _coerce(v, concept, tagline, has_person)


def _coerce(v: dict, concept: str, tagline: str, has_person: bool) -> dict:
    headline = (v.get("headline") or concept or "RPO Done Right").strip()
    tmpl = v.get("template") if v.get("template") in _TEMPLATES else "statement"
    if has_person:
        tmpl = "hero"
    stats = []
    if tmpl == "stat":
        for s in (v.get("stats") or [])[:3]:
            val = str((s or {}).get("value", "")).strip()
            lab = str((s or {}).get("label", "")).strip()
            if val and lab:
                stats.append({"value": val[:8], "label": lab[:22]})
        if not stats:
            tmpl = "statement"          # no real numbers -> don't fake a stat card
    red_word = (v.get("red_word") or "").strip()
    if red_word and red_word.lower() not in headline.lower():
        red_word = ""                    # only highlight a word that is actually in the headline
    if not red_word:                     # default: the longest headline word (never the brand name)
        words = [w for w in re.findall(r"[A-Za-z0-9']+", headline)
                 if len(w) > 2 and w.lower() not in ("talentrupt", "rpo")]
        red_word = max(words, key=len) if words else ""
    return {
        "template": tmpl,
        "headline": headline,
        "red_word": red_word,
        "subtext": (v.get("subtext") or tagline).strip(),
        "kicker": (v.get("kicker") or "").strip()[:26],
        "stats": stats,
        "scene": (v.get("scene") or concept).strip(),
        "bg": "cream" if v.get("bg") == "cream" else ("navy" if v.get("bg") == "navy" else random.choice(["navy", "cream"])),
        "cta": (v.get("cta") or "").strip()[:22],
    }


# --------------------------------------------------------------------------------------------------
# Backgrounds
# --------------------------------------------------------------------------------------------------
def _solid(bg: str) -> Image.Image:
    return Image.new("RGB", (W, H), CREAM if bg == "cream" else NAVY)


async def _ai_scene(scene: str) -> Image.Image | None:
    """A photographic themed background for observance posts (no text, reserved zones). None on failure."""
    from ..providers import llm
    if not llm.image_provider_available() or not scene:
        return None
    prompt = (
        f"A premium, photorealistic, cinematic BACKGROUND photograph for a corporate social post about: "
        f"{scene[:180]}. Shown in natural true colour, bright and high-contrast, real atmosphere and depth. "
        "ABSOLUTELY NO people, NO faces, NO text, NO words, NO letters, NO numbers, NO logos, NO signage. "
        "Keep the TOP area and the LOWER-CENTER calm and unobtrusive so a wordmark (top) and a headline "
        "(centered) sit cleanly on top. Square 1:1 composition."
    )
    try:
        data = await llm.generate_image_bytes(prompt, size="1024x1024", quality="medium")
        return _cover_fit(Image.open(io.BytesIO(data)).convert("RGB"), W, H) if data else None
    except Exception:
        return None


# --------------------------------------------------------------------------------------------------
# Person compositing (real photo, AS-IS — face + clothes never altered)
# --------------------------------------------------------------------------------------------------
def _prep_person(photo_bytes: bytes) -> Image.Image | None:
    """Enhanced RGB of the person's REAL photo (identity untouched). The cut-out itself is attempted
    later, at compose time, so we can fall back cleanly when a background can't be removed."""
    try:
        from PIL import ImageOps
        src = ImageOps.exif_transpose(Image.open(io.BytesIO(photo_bytes)).convert("RGB"))
        src.thumbnail((1800, 1800), Image.LANCZOS)
        return _enhance_photo(src)
    except Exception as e:
        log.warning("chatpost person prep failed: %s", e)
        return None


def _rounded(img: Image.Image, radius: int) -> Image.Image:
    img = img.convert("RGBA")
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def _clean_cutout(person_rgb: Image.Image):
    """Try to cut the person out. Returns (rgba, ok) — ok is True ONLY when the background was really
    removed (the alpha has genuine transparency and a sane subject coverage). On prod with no
    bg-removal key + a shadowed studio wall the free keyer bails, so ok is False and we frame instead."""
    import numpy as np
    try:
        cut = _cutout(person_rgb)
    except Exception:
        return None, False
    ok = False
    if cut.mode == "RGBA" and cut.width >= 120 and cut.height >= 180:
        al = np.asarray(cut.split()[-1])
        # a REAL cut-out has genuine transparency AND a person-sized subject; a near-opaque/messy key
        # (coverage > ~0.9) is treated as "not cut out" so it falls back to the clean framed panel.
        ok = int(al.min()) < 245 and 0.20 <= float((al > 127).mean()) <= 0.90
    return cut, ok


def _hero_disc(canvas: Image.Image, bg: str) -> None:
    """The bold brand shape behind a cleanly cut-out person (navy field -> coral disc; cream -> navy)."""
    pcx = int(W * 0.86)
    d = ImageDraw.Draw(canvas, "RGBA")
    if bg == "cream":
        d.ellipse([pcx - 330, 90, pcx + 420, 1140], fill=(*NAVY, 255))
    else:
        d.ellipse([pcx - 320, 120, pcx + 430, 1150], fill=(*RED, 245))


def _float_cutout(canvas: Image.Image, cut: Image.Image, bg: str) -> None:
    """A cleanly cut-out person floating on the brand disc — sized so the WHOLE body stays in frame."""
    _hero_disc(canvas, bg)
    region_left = int(W * 0.50)
    max_w, max_h = W - region_left - 24, int(H * 0.82)
    scale = min(max_h / cut.height, max_w / cut.width)          # fit BOTH axes -> never clipped / half-off
    pw, ph = max(1, int(cut.width * scale)), max(1, int(cut.height * scale))
    p = cut.resize((pw, ph), Image.LANCZOS)
    x = region_left + (max_w - pw) // 2 + 12
    y = H - ph
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([x + int(pw * 0.14), H - 38, x + int(pw * 0.86), H - 8], fill=(0, 0, 0, 80))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(11)))
    canvas.alpha_composite(p, (x, y))


def _photo_panel(canvas: Image.Image, person_rgb: Image.Image, bg: str) -> None:
    """No clean cut-out possible (prod default) -> a clean rounded PHOTO PANEL on the right: the person's
    real photo cover-fit into a rounded card (their own background clipped to the shape), a brand accent
    disc behind it, a soft drop shadow and a white keyline. Reads as intentional design, never a broken
    cut-out — and the person is fully framed, never half-off."""
    pw, ph = int(W * 0.44), int(H * 0.80)
    px, py = W - pw - 34, (H - ph) // 2
    d = ImageDraw.Draw(canvas, "RGBA")
    acc = RED if bg != "cream" else NAVY
    d.ellipse([px - 46, py - 26, px + pw + 34, py + ph + 26], fill=(*acc, 235))        # accent behind
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([px + 6, py + 12, px + pw + 6, py + ph + 12], radius=40,
                                         fill=(11, 34, 58, 95))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
    canvas.alpha_composite(_rounded(_cover_fit(person_rgb, pw, ph), 40), (px, py))
    ImageDraw.Draw(canvas).rounded_rectangle([px - 4, py - 4, px + pw + 4, py + ph + 4], radius=44,
                                             outline=(*WHITE, 255), width=6)


def _hero_person(canvas: Image.Image, person_rgb: Image.Image, bg: str) -> None:
    """Place the featured person on the right: a floating cut-out (when the background can be removed),
    else a clean framed photo panel. Either way the real face + clothes are untouched and fully in frame."""
    try:
        cut, ok = _clean_cutout(person_rgb)
        if ok and cut is not None:
            _float_cutout(canvas, cut, bg)
        else:
            _photo_panel(canvas, person_rgb, bg)
    except Exception as e:
        log.warning("chatpost hero person failed: %s", e)
        try:
            _photo_panel(canvas, person_rgb, bg)
        except Exception:
            pass


# --------------------------------------------------------------------------------------------------
# Brand chrome (drawn crisply by the app)
# --------------------------------------------------------------------------------------------------
def _wordmark(canvas: Image.Image, dark_bg: bool, align: str = "left") -> None:
    col = WHITE if dark_bg else NAVY
    if align == "center":
        if not paste_wordmark(canvas, PAD, 60, W - 2 * PAD, 56, dark_bg=dark_bg, align="center"):
            d = ImageDraw.Draw(canvas)
            f = heading_font(40)
            d.text(((W - d.textlength("TALENTRUPT", font=f)) / 2, 66), "TALENTRUPT", font=f, fill=col)
        return
    if not paste_wordmark(canvas, PAD, 60, 300, 56, dark_bg=dark_bg, align="left"):
        ImageDraw.Draw(canvas).text((PAD, 66), "TALENTRUPT", font=heading_font(40), fill=col)


def _kicker(canvas: Image.Image, x: int, y: int, text: str) -> int:
    """A coral rounded pill with white uppercase text. Returns the y below it."""
    if not text:
        return y
    d = ImageDraw.Draw(canvas)
    f = heading_font(26)
    t = text.upper()[:26]
    tw = d.textlength(t, font=f)
    d.rounded_rectangle([x, y, x + tw + 44, y + 50], radius=25, fill=(*RED, 255))
    d.text((x + 22, y + 10), t, font=f, fill=WHITE)
    return y + 68


def _headline(canvas: Image.Image, text: str, red_word: str, x: int, y: int, max_w: int,
              size: int, base: tuple, max_lines: int = 4) -> int:
    """Bold headline wrapped to max_w, with any word matching `red_word` flipped to coral red."""
    d = ImageDraw.Draw(canvas)
    f = heading_font(size)
    red_tokens = {re.sub(r"[^a-z0-9]", "", w.lower()) for w in (red_word or "").split() if w}
    lines = _wrap(d, text, f, max_w)[:max_lines]
    lh = int(size * 1.08)
    for ln in lines:
        cx = x
        for word in ln.split():
            key = re.sub(r"[^a-z0-9]", "", word.lower())
            col = RED if (key and key in red_tokens) else base
            d.text((cx, y), word, font=f, fill=col)
            cx += d.textlength(word + " ", font=f)
        y += lh
    return y


def _divider(canvas: Image.Image, x: int, y: int, dark_bg: bool) -> int:
    d = ImageDraw.Draw(canvas)
    d.rectangle([x, y, x + 96, y + 8], fill=(*RED, 255))
    return y + 30


def _stat_cards(canvas: Image.Image, stats: list[dict], x: int, y: int, total_w: int, dark_bg: bool) -> None:
    """A row of up to 3 rounded stat cards (navy / red / navy…) with a big value + a small label."""
    n = len(stats)
    if not n:
        return
    gap = 22
    cw = (total_w - gap * (n - 1)) // n
    ch = 190
    cols = [CARD_NAVY, CARD_RED, CARD_NAVY]
    if dark_bg:
        cols = [CARD_RED, WHITE, CARD_RED]
    d = ImageDraw.Draw(canvas)
    for i, s in enumerate(stats[:3]):
        cx = x + i * (cw + gap)
        fill = cols[i % 3]
        on = WHITE if fill != WHITE else NAVY
        # shadow + card
        sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([cx + 3, y + 6, cx + cw + 3, y + ch + 6], radius=26,
                                             fill=(11, 34, 58, 60))
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle([cx, y, cx + cw, y + ch], radius=26, fill=(*fill, 255))
        val = str(s["value"])[:8]
        vf = heading_font(76)
        while d.textlength(val, font=vf) > cw - 40 and vf.size > 34:
            vf = heading_font(vf.size - 6)
        d.text((cx + (cw - d.textlength(val, font=vf)) / 2, y + 30), val, font=vf, fill=(*on, 255))
        lab = str(s["label"]).upper()[:22]
        lf = body_font(24)
        for j, ln in enumerate(_wrap(d, lab, lf, cw - 36)[:2]):
            d.text((cx + (cw - d.textlength(ln, font=lf)) / 2, y + 122 + j * 30), ln, font=lf,
                   fill=(*on, 220))


def _cta_button(canvas: Image.Image, x: int, y: int, text: str, dark_bg: bool) -> None:
    if not text:
        return
    d = ImageDraw.Draw(canvas)
    f = heading_font(26)
    t = text.upper()[:22]
    tw = d.textlength(t, font=f)
    col = WHITE if dark_bg else NAVY
    d.rounded_rectangle([x, y, x + tw + 96, y + 58], radius=29, outline=(*col, 255), width=3)
    d.text((x + 28, y + 14), t, font=f, fill=col)
    # little arrow
    ax = x + tw + 54
    d.line([(ax, y + 29), (ax + 22, y + 29)], fill=(*RED, 255), width=4)
    d.line([(ax + 14, y + 21), (ax + 22, y + 29), (ax + 14, y + 37)], fill=(*RED, 255), width=4, joint="curve")


def _footer(canvas: Image.Image, dark_bg: bool) -> None:
    """A red-circle globe + website, bottom-left (Talentrupt's footer signature)."""
    d = ImageDraw.Draw(canvas)
    cy = H - 66
    r = 20
    d.ellipse([PAD, cy - r, PAD + 2 * r, cy + r], fill=(*RED, 255))
    # simple globe glyph
    gx0, gy0 = PAD + 6, cy - 14
    d.ellipse([gx0, gy0, gx0 + 28, gy0 + 28], outline=(*WHITE, 255), width=2)
    d.line([(gx0 + 14, gy0), (gx0 + 14, gy0 + 28)], fill=(*WHITE, 255), width=2)
    d.line([(gx0, gy0 + 14), (gx0 + 28, gy0 + 14)], fill=(*WHITE, 255), width=2)
    d.text((PAD + 2 * r + 16, cy - 17), "www.talentrupt.com", font=body_font(28),
           fill=WHITE if dark_bg else NAVY)


# --- corner accents (tasteful, sparse) ------------------------------------------------------------
def _diag_circle(canvas: Image.Image, cx: int, cy: int, r: int, color: tuple) -> None:
    """A circle filled with diagonal hatch lines — Talentrupt's signature corner accent."""
    layer = Image.new("RGBA", (2 * r, 2 * r), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    for off in range(-2 * r, 2 * r, 14):
        ld.line([(off, 0), (off + 2 * r, 2 * r)], fill=(*color, 210), width=4)
    mask = Image.new("L", (2 * r, 2 * r), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, 2 * r - 1, 2 * r - 1], fill=255)
    layer.putalpha(Image.composite(layer.split()[-1], Image.new("L", layer.size, 0), mask))
    canvas.alpha_composite(layer, (cx - r, cy - r))


def _dot_grid(canvas: Image.Image, x: int, y: int, cols: int, rows: int, gap: int, r: int, color: tuple) -> None:
    d = ImageDraw.Draw(canvas)
    for i in range(cols):
        for j in range(rows):
            px, py = x + i * gap, y + j * gap
            d.ellipse([px - r, py - r, px + r, py + r], fill=(*color, 210))


def _accents(canvas: Image.Image, dark_bg: bool, seed: int) -> None:
    accent = RED
    faint = (WHITE if dark_bg else NAVY)
    kind = seed % 3
    if kind == 0:
        _diag_circle(canvas, W - 120, 150, 96, accent)
        _dot_grid(canvas, PAD, H - 210, 5, 4, 26, 5, faint)
    elif kind == 1:
        _diag_circle(canvas, W - 130, H - 150, 104, faint)
        _dot_grid(canvas, W - 200, 150, 4, 4, 26, 5, accent)
    else:
        _dot_grid(canvas, PAD, H - 210, 6, 3, 24, 5, accent)


# --------------------------------------------------------------------------------------------------
# Templates
# --------------------------------------------------------------------------------------------------
def _scrim_left(canvas: Image.Image, dark: bool) -> Image.Image:
    """Darken the left/top for headline legibility over a photo (observance)."""
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(ov)
    base = (0x0B, 0x35, 0x59)
    for yy in range(H):
        a = int(150 * max(0, 1 - yy / (H * 0.7)))
        dd.line([(0, yy), (W, yy)], fill=(*base, a))
    out = canvas.convert("RGBA")
    out.alpha_composite(ov)
    return out


def _render(plan: dict, bg_img: Image.Image | None, person: Image.Image | None) -> Image.Image:
    tmpl = plan["template"]
    dark = plan["bg"] != "cream"
    base = WHITE if dark else NAVY

    if tmpl == "hero" and person is not None:
        HW = 420                                           # left text column width — clears the person panel
        canvas = _solid(plan["bg"]).convert("RGBA")
        _hero_person(canvas, person, plan["bg"])
        _wordmark(canvas, dark_bg=dark)
        y = 210
        y = _kicker(canvas, PAD, y, plan["kicker"])
        y = _headline(canvas, plan["headline"], plan["red_word"], PAD, y, HW, 72, base, max_lines=5)
        y = _divider(canvas, PAD, y + 16, dark)
        d = ImageDraw.Draw(canvas)
        for ln in _wrap(d, plan["subtext"], body_font(30), HW)[:3]:
            d.text((PAD, y), ln, font=body_font(30), fill=(WHITE if dark else SUBINK))
            y += 42
        if plan["cta"]:
            _cta_button(canvas, PAD, y + 20, plan["cta"], dark)
        _footer(canvas, dark_bg=dark)
        return canvas.convert("RGB")

    if tmpl == "observance":
        scene = bg_img if bg_img is not None else _solid(plan["bg"])
        canvas = _scrim_left(scene, dark)
        _wordmark(canvas, dark_bg=True, align="center")
        y = 250
        d = ImageDraw.Draw(canvas)
        if plan["kicker"]:
            y = _kicker(canvas, PAD, y, plan["kicker"])
        y = _headline(canvas, plan["headline"], plan["red_word"], PAD, y, W - 2 * PAD, 96, WHITE, max_lines=3)
        y = _divider(canvas, PAD, y + 16, True)
        for ln in _wrap(d, plan["subtext"], body_font(32), W - 2 * PAD)[:3]:
            d.text((PAD, y), ln, font=body_font(32), fill=CREAM)
            y += 44
        _footer(canvas, dark_bg=True)
        return canvas.convert("RGB")

    # statement / stat (no person)
    canvas = _solid(plan["bg"]).convert("RGBA")
    _accents(canvas, dark, hash(plan["headline"]) & 7)
    _wordmark(canvas, dark_bg=dark)
    y = 210
    y = _kicker(canvas, PAD, y, plan["kicker"])
    y = _headline(canvas, plan["headline"], plan["red_word"], PAD, y, W - 2 * PAD, 92, base, max_lines=4)
    y = _divider(canvas, PAD, y + 16, dark)
    d = ImageDraw.Draw(canvas)
    for ln in _wrap(d, plan["subtext"], body_font(32), W - 2 * PAD)[:3]:
        d.text((PAD, y), ln, font=body_font(32), fill=(CREAM if dark else SUBINK))
        y += 46
    if plan["template"] == "stat" and plan["stats"]:
        _stat_cards(canvas, plan["stats"], PAD, max(y + 30, 620), W - 2 * PAD, dark)
    _footer(canvas, dark_bg=dark)
    return canvas.convert("RGB")


def _save(canvas: Image.Image, plan: dict) -> tuple[str, str, dict]:
    fname = unique_name("tr-chatpost", "png")
    sub = storage_subdir("images")
    sub.mkdir(parents=True, exist_ok=True)
    path = sub / fname
    canvas.save(str(path), "PNG")
    return str(path), fname, {
        "url": public_url("images", fname), "renderer": "chat_talentrupt",
        "template": plan["template"], "size": f"{W}x{H}",
    }


# --------------------------------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------------------------------
async def build_chat_post(brand: Brand | None, concept: str, count: int = 1, style: str | None = None,
                          person_photo: bytes | None = None, person_name: str = "",
                          headline: str = "", subtext: str = "") -> list[tuple[str, str, dict]]:
    """Render `count` Talentrupt-brand Chat posts for `concept`. If `person_photo` is given, the real
    person is composited AS-IS into a hero layout. When `headline` is supplied (a person feature with
    user-given copy), that copy is used verbatim instead of LLM planning. Returns [(path, file_name, meta)]."""
    count = max(1, min(count, 3))
    person = _prep_person(person_photo) if person_photo else None
    tagline = (brand.tagline if brand and brand.tagline else "RPO Done Right")
    if headline.strip():   # explicit copy (person feature) -> one hero, no LLM planning
        kicker = (person_name.strip().upper()[:26] if person_name else "")
        plans = [_coerce({"template": "hero", "headline": headline, "subtext": subtext, "kicker": kicker,
                          "bg": random.choice(["navy", "cream"])}, headline, tagline, has_person=person is not None)]
    else:
        plans = await _plan(brand, concept, count, has_person=person is not None)
    out: list[tuple[str, str, dict]] = []
    for p in plans:
        try:
            bg = await _ai_scene(p["scene"]) if (p["template"] == "observance") else None
            canvas = _render(p, bg, person)
            out.append(_save(canvas, p))
        except Exception as e:
            log.warning("chatpost render failed: %s", e)
            continue
    return out
