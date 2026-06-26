"""Branded "feature a person/team" posts built around a REAL photo (exact faces — never AI-synthesized).

Several distinct FORMATS so the same person isn't always shown the same way:
  - spotlight : person cut out (offline rembg) as a hero on the navy designed background ("Man on a
                Mission" style).
  - magazine  : the full real photo, full-bleed, with a navy caption band (shows the real backdrop).
  - split     : the full photo on one side, a navy text panel on the other.
  - framed    : a rounded "spotlight card" — framed portrait centred on navy with name/role.
Each also has background/headline/accent variants. Falls back to a cover-fit (no cut-out) if rembg
isn't installed, so the feature never breaks. No LLM / image-API — pure PIL.
"""
from __future__ import annotations

import io
import math
import random
import re

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

STYLE_NAMES = ["spotlight", "magazine", "split", "framed"]


# --- shared helpers --------------------------------------------------------
def _cutout(img: Image.Image) -> Image.Image:
    """Background-removed RGBA of the subject (offline rembg). Returns the original as opaque RGBA if
    rembg isn't available, so the post still renders rather than failing."""
    try:
        from rembg import remove  # heavy import; only loaded when a cut-out post is built
        out = remove(img).convert("RGBA")
        bbox = out.getbbox()
        return out.crop(bbox) if bbox else out
    except Exception:
        return img.convert("RGBA")


def _cover_fit(img: Image.Image, w: int, h: int) -> Image.Image:
    """Center-crop + scale `img` to exactly fill w×h (never distort)."""
    img = img.convert("RGB")
    src_r, dst_r = img.width / img.height, w / h
    if src_r > dst_r:
        nw = max(1, int(img.height * dst_r))
        x = (img.width - nw) // 2
        img = img.crop((x, 0, x + nw, img.height))
    else:
        nh = max(1, int(img.width / dst_r))
        y = (img.height - nh) // 2
        img = img.crop((0, y, img.width, y + nh))
    return img.resize((w, h), Image.LANCZOS)


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


def split_message(message: str) -> tuple[str, str]:
    """Split a post message into a punchy (headline, subline) so a longer message is shown in full
    instead of being truncated into the headline. Splits on the first sentence break, else a
    colon/dash, else after the first few words for long messages; short messages stay all-headline.
    'Congrats Nishant! Celebrating 10+ years at Talentrupt' -> ('Congrats Nishant!', 'Celebrating 10+
    years at Talentrupt')."""
    msg = " ".join((message or "").split())
    if not msg:
        return "", ""
    m = re.search(r"[.!?]", msg)
    if m and msg[m.end():].strip():
        return msg[:m.end()].strip(), msg[m.end():].strip()
    for sep in (" — ", " - ", ": ", "—", ":"):
        if sep in msg:
            a, b = msg.split(sep, 1)
            if a.strip() and b.strip():
                return a.strip(), b.strip()
    words = msg.split()
    if len(words) > 6:
        return " ".join(words[:3]), " ".join(words[3:])
    return msg, ""


# --- team label parsing & person detection (shared so EVERY image path can refuse a fake face) ------
_ROLE_PHRASES = ["account manager", "account executive", "talent acquisition", "co founder",
                 "chief operating officer", "operations head", "team lead", "coo", "ceo", "cto", "cfo",
                 "cmo", "vp", "founder", "co-founder", "director", "manager", "lead", "head", "recruiter",
                 "sourcer", "associate", "executive", "president", "officer", "intern"]
_ROLE_ACRONYMS = {"coo", "ceo", "cto", "cfo", "cmo", "vp"}
# Tokens that must NEVER be read as "a real person is named" (company / generic / role words).
_PERSON_STOPWORDS = {"talentrupt", "team", "group", "everyone", "staff", "the", "our", "people",
                     "coo", "ceo", "cto", "cfo", "cmo", "founder", "leadership", "account", "manager"}


def parse_team_label(label: str) -> tuple[str, str]:
    """'nishant trivedi coo' -> ('Nishant Trivedi', 'COO'); 'jerry account manager' -> ('Jerry',
    'Account Manager'); 'leadership team' -> ('Leadership Team', ''). A trailing rotation number is
    dropped so '<base>-2' shots map to the same name/role."""
    toks = label.lower().split()
    while len(toks) > 1 and toks[-1].isdigit():
        toks.pop()
    base = " ".join(toks)
    if toks and toks[-1] in ("team", "group", "everyone", "staff"):
        return base.title(), ""
    for ph in sorted(_ROLE_PHRASES, key=lambda p: -len(p.split())):
        pw = ph.split()
        if len(toks) > len(pw) and toks[-len(pw):] == pw:
            role = ph.upper() if ph in _ROLE_ACRONYMS else ph.title()
            return " ".join(toks[:-len(pw)]).title() or base.title(), role
    return base.title(), ""


def detect_team_person(text: str) -> str | None:
    """If `text` names a REAL person who has a photo in the Team library, return that person's name —
    so any image path can route to their real photo instead of EVER AI-generating their face."""
    from ..knowledge import retrieve
    toks = {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2}
    if not toks:
        return None
    for it in retrieve.list_team_photos():
        name, _role = parse_team_label(it["label"])
        name_toks = {t for t in re.findall(r"[a-z0-9]+", name.lower()) if len(t) > 2} - _PERSON_STOPWORDS
        if name_toks & toks:
            return name
    return None


_GROUP_CUES = {"team", "teams", "group", "everyone", "everybody", "staff", "leadership", "leaders",
               "all", "crew", "folks", "company", "office", "department", "squad", "members",
               "colleagues", "family", "culture", "together", "people", "us", "we"}


def is_group_query(text: str) -> bool:
    """True when the request is about the team/group as a whole (so we feature a GROUP shot)."""
    return bool({t for t in re.findall(r"[a-z]+", (text or "").lower())} & _GROUP_CUES)


def group_photos() -> list:
    """Team photos that depict a GROUP (no individual role) — used so a generic 'the team' request
    rotates across real group shots instead of silently defaulting to one person."""
    from ..knowledge import retrieve
    return [p for p in retrieve.list_team_photos() if parse_team_label(p["label"])[1] == ""]


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


def _draw_headline(d, x, y, text, max_w, accent_box=True, size=104, max_lines=3) -> int:
    """Headline in heading font, auto-shrunk so the FULL text fits within max_lines — never drops
    words. Even variants box the last line red; odd variants underline. Returns the y below the block."""
    text = (text or "On a Mission!").strip()
    f = heading_font(size)
    lines = _wrap(d, text, f, max_w)
    while len(lines) > max_lines and size > 44:
        size -= 6
        f = heading_font(size)
        lines = _wrap(d, text, f, max_w)
    last_tw = 0
    for idx, ln in enumerate(lines):
        tw = d.textlength(ln, font=f)
        last_tw = tw
        if accent_box and idx == len(lines) - 1:
            d.rectangle([x - 8, y - 4, x + tw + 26, y + f.size + 14], fill=RED)
            d.text((x + 6, y + 4), ln, font=f, fill=WHITE)
        else:
            d.text((x, y + 4), ln, font=f, fill=WHITE)
        y += int(f.size * 1.18) + 10
    if not accent_box:
        d.rectangle([x, y - 2, x + min(int(last_tw), max_w), y + 12], fill=RED)
        y += 18
    return y


def _role_badge(d, x, y, role, fill=WHITE, fg=NAVY) -> None:
    bf = body_font(30)
    rw = d.textlength(role, font=bf)
    bw = 24 + 16 + rw
    d.rounded_rectangle([x, y, x + bw + 40, y + 52], radius=26, fill=fill)
    ix, iy = x + 22, y + 16  # mini briefcase, drawn (no emoji-font dependency)
    d.rounded_rectangle([ix, iy + 5, ix + 24, iy + 20], radius=3, fill=fg)
    d.rectangle([ix + 8, iy, ix + 16, iy + 7], outline=fg, width=3)
    d.text((ix + 36, y + 11), role, font=bf, fill=fg)


def _draw_featuring(d, x, y, name, role, name_size=58) -> None:
    if not name:  # no name given (e.g. "use this photo") -> just the headline + photo, no name block
        return
    d.rectangle([x, y - 16, x + 120, y - 12], fill=WHITE)
    d.text((x, y), "Featuring", font=body_font(32), fill=CREAM)
    d.text((x, y + 40), name, font=heading_font(name_size), fill=WHITE)
    if role:
        _role_badge(d, x, y + 40 + 72, role)


# --- formats ---------------------------------------------------------------
def _layout_spotlight(photo, name, role, headline, question, variant) -> Image.Image:
    canvas = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(canvas)
    _paint_backdrop(canvas, d, variant)
    hero = _cutout(photo)
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
    y = _draw_headline(d, pad, 84, headline, W - 470, accent_box=(variant % 2 == 0))
    if question:
        qf = body_font(34)
        y += 12
        for ln in _wrap(d, question, qf, 440):
            d.text((pad, y), ln, font=qf, fill=CREAM)
            y += 44
    _draw_featuring(d, pad, H - 250, name, role)
    paste_logo(canvas, W - 116, H - 116, 74)
    return canvas


def _scrim(canvas, top_frac, start_alpha) -> Image.Image:
    """Composite a bottom navy gradient onto a full-bleed photo for caption legibility."""
    grad = Image.new("L", (1, H), 0)
    y0, y1 = H * top_frac, H * (top_frac + 0.18)
    for yy in range(H):
        if yy < y0:
            a = 0
        elif yy < y1:
            a = int(start_alpha * (yy - y0) / (y1 - y0))
        else:
            a = start_alpha
        grad.putpixel((0, yy), a)
    layer = Image.new("RGBA", (W, H), (*NAVY, 255))
    layer.putalpha(grad.resize((W, H)))
    return Image.alpha_composite(canvas.convert("RGBA"), layer).convert("RGB")


def _layout_magazine(photo, name, role, headline, question, variant) -> Image.Image:
    canvas = _cover_fit(photo, W, H)
    canvas = _scrim(canvas, 0.40, 250)
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, RAIL_W, H], fill=RED)
    pad = 70
    cap = headline or "On a Mission!"
    if question:
        cap = f"{cap} {question}"
    for s in (32, 28, 25):  # shrink the caption so the whole message fits (never truncated)
        cf = body_font(s)
        cap_lines = _wrap(d, cap, cf, W - 2 * pad)
        if len(cap_lines) <= 3:
            break
    cap_lines = cap_lines[:3]
    name_y = H - 250
    cy = name_y - 20 - len(cap_lines) * (cf.size + 6)
    d.rectangle([pad, cy - 18, pad + 90, cy - 13], fill=RED)  # red tick
    for ln in cap_lines:
        d.text((pad, cy), ln, font=cf, fill=CREAM)
        cy += cf.size + 6
    if name:
        d.text((pad, name_y), name, font=heading_font(74), fill=WHITE)
        if role:
            _role_badge(d, pad, name_y + 92, role)
    paste_logo(canvas, W - 116, H - 116, 74)
    return canvas


def _layout_split(photo, name, role, headline, question, variant) -> Image.Image:
    canvas = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(canvas)
    panel_w = int(W * 0.44)
    canvas.paste(_cover_fit(photo, W - panel_w, H), (panel_w, 0))
    d.rectangle([panel_w - 8, 0, panel_w, H], fill=RED)  # seam
    d.rectangle([0, 0, RAIL_W, H], fill=RED)
    for i in range(20):  # small dotted arc accent in the panel
        a = math.radians(-20 + i * 8)
        px, py = int(panel_w * 0.5 + 90 * math.cos(a)), int(H * 0.30 + 90 * math.sin(a))
        d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=NAVY2)
    pad = 64
    y = _draw_headline(d, pad, 110, headline, panel_w - 2 * pad, accent_box=(variant % 2 == 0), size=78)
    if question:
        qf = body_font(30)
        y += 10
        for ln in _wrap(d, question, qf, panel_w - 2 * pad):
            d.text((pad, y), ln, font=qf, fill=CREAM)
            y += 40
    _draw_featuring(d, pad, H - 300, name, role, name_size=48)
    paste_logo(canvas, pad, H - 110, 60)
    return canvas


def _layout_framed(photo, name, role, headline, question, variant) -> Image.Image:
    canvas = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(canvas)
    _paint_backdrop(canvas, d, variant)
    fw, fh, fy = 580, 540, 220
    fx = (W - fw) // 2
    portrait = _cover_fit(photo, fw, fh)
    mask = Image.new("L", (fw, fh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, fw, fh], radius=44, fill=255)
    d.rounded_rectangle([fx - 8, fy - 8, fx + fw + 8, fy + fh + 8], radius=50, outline=WHITE, width=6)
    canvas.paste(portrait, (fx, fy), mask)
    # caption above the frame — combine headline + subline, shrink so the whole thing fits (≤2 lines)
    cap = headline or "Team Spotlight"
    if question:
        cap = f"{cap} {question}"
    for s in (50, 44, 38, 32):
        cf = heading_font(s)
        clines = _wrap(d, cap, cf, W - 150)
        if len(clines) <= 2:
            break
    clines = clines[:2]
    ty = 64 if len(clines) == 2 else 96
    for ln in clines:
        d.text(((W - d.textlength(ln, font=cf)) // 2, ty), ln, font=cf, fill=CREAM)
        ty += cf.size + 8
    if name:
        nf = heading_font(58)
        d.text(((W - d.textlength(name, font=nf)) // 2, fy + fh + 26), name, font=nf, fill=WHITE)
        if role:
            rf = body_font(32)
            rw = d.textlength(role, font=rf)
            ry = fy + fh + 26 + 76
            d.rounded_rectangle([(W - rw) // 2 - 30, ry, (W + rw) // 2 + 30, ry + 54], radius=27, fill=RED)
            d.text(((W - rw) // 2, ry + 12), role, font=rf, fill=WHITE)
    paste_logo(canvas, W - 116, H - 116, 74)
    return canvas


_LAYOUTS = {
    "spotlight": _layout_spotlight,
    "magazine": _layout_magazine,
    "split": _layout_split,
    "framed": _layout_framed,
}


def build_team_image(
    brand: Brand | None, photo_bytes: bytes, name: str, role: str = "",
    headline: str = "", question: str = "", variant: int = 0, style: str = "spotlight",
) -> tuple[str, str, dict]:
    """Compose a branded feature post around a real photo in one of STYLE_NAMES formats. `variant`
    rotates background/scale/accent within a format. Returns (path, file_name, meta) — same shape as
    images._render. Raises on an unreadable photo (caller surfaces a message; never an AI face)."""
    try:  # team photos may be HEIC (iPhone) — register the opener when available
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    photo = ImageOps.exif_transpose(Image.open(io.BytesIO(photo_bytes)).convert("RGB"))
    style = style if style in _LAYOUTS else "spotlight"
    canvas = _LAYOUTS[style](photo, name, role, headline, question, variant)

    file_name = unique_name("tr-team", "png")
    path = storage_subdir("images") / file_name
    canvas.convert("RGB").save(str(path), "PNG")
    return str(path), file_name, {
        "url": public_url("images", file_name),
        "renderer": f"team_{style}",
        "style": style,
        "size": f"{W}x{H}",
        "kind": "team",
    }


def render_if_person(brand, concept: str, count: int = 1):
    """If `concept` names a real Team person, render up to `count` real-photo posts and return them as
    [(path, file_name, meta)]; else None. The single chokepoint that lets ANY image path refuse to
    AI-generate a real face — used inside build_images so generate/refine/campaign all stay safe."""
    from ..knowledge import retrieve
    if not detect_team_person(concept):
        return None
    photos = retrieve.person_photos(detect_team_person(concept))
    if not photos:
        return None
    head, sub = split_message(concept or "")
    if not head:
        head = "In the Spotlight."
    out = []
    for _ in range(max(1, min(int(count or 1), 4))):
        ph = random.choice(photos)
        raw = retrieve.team_reference_bytes(ph["path"])
        if not raw:
            continue
        name, role = parse_team_label(ph["label"])
        p, fn, m = build_team_image(brand, raw, name=name, role=role, headline=head, question=sub,
                                    variant=random.randint(0, 5), style=random.choice(STYLE_NAMES))
        out.append((p, fn, {**m, "team_photo": ph["label"]}))
    return out or None
