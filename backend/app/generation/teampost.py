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
import logging
import math
import random
import re
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from ..models import Brand
from . import cutout
from .common import body_font, heading_font, paste_wordmark, public_url, script_font, storage_subdir, unique_name

log = logging.getLogger("talentrupt.teampost")

W = H = 1080
RAIL_W = 16
NAVY = (0x0B, 0x35, 0x59)
NAVY2 = (0x12, 0x44, 0x6E)
RED = (0xF6, 0x40, 0x4C)
CREAM = (0xEB, 0xE9, 0xDF)
WHITE = (255, 255, 255)
INK = (0x14, 0x22, 0x3A)      # near-navy ink for text on light skins
SUBINK = (0x46, 0x56, 0x6E)   # muted navy for sublines on light skins


# --- Brand "skins": full on-brand palette treatments so output isn't navy-every-time ----------------
@dataclass(frozen=True)
class Skin:
    key: str
    bg: tuple            # background fill (the "photo" skin paints its own scene)
    text: tuple          # headline text colour
    sub: tuple           # subline / body text colour
    accent: tuple        # keyword box, rails, arrows (RED; NAVY on the red skin)
    on_accent: tuple     # text drawn ON the accent box
    name: tuple          # featured-name colour
    frame: tuple         # photo-card frame colour
    wm_dark: bool        # True -> white wordmark (dark bg); False -> navy wordmark (light bg)
    shade: tuple         # subtle geometric-accent shade for the background
    is_photo: bool = False


SKINS = {
    "light": Skin("light", (0xF7, 0xF5, 0xEF), NAVY, SUBINK, RED, WHITE, NAVY, NAVY, False, (0xE3, 0xDF, 0xD2)),
    "cream": Skin("cream", CREAM, NAVY, SUBINK, RED, WHITE, NAVY, NAVY, False, (0xDD, 0xD8, 0xC8)),
    "red": Skin("red", RED, WHITE, CREAM, NAVY, WHITE, WHITE, WHITE, True, (0xD2, 0x2A, 0x35)),
    "navy": Skin("navy", NAVY, WHITE, CREAM, RED, WHITE, WHITE, CREAM, True, NAVY2),
    "photo": Skin("photo", NAVY, WHITE, CREAM, RED, WHITE, WHITE, CREAM, True, NAVY2, is_photo=True),
}
DETERMINISTIC_SKINS = ["light", "cream", "navy", "red"]
ALL_SKINS = DETERMINISTIC_SKINS + ["photo"]
_SKIN_ROT: dict[str, int] = {}


def pick_skin(owner: str = "", include_photo: bool = True) -> str:
    """Rotate through the skins with no immediate repeat, so consecutive posts for an owner differ
    (light / cream / navy / red / photographic) instead of navy-every-time."""
    pool = ALL_SKINS if include_photo else DETERMINISTIC_SKINS
    i = _SKIN_ROT.get(owner, -1) + 1
    _SKIN_ROT[owner] = i
    return pool[i % len(pool)]


def resolve_skin(key: str) -> Skin:
    return SKINS.get((key or "").lower(), SKINS["navy"])


STYLE_NAMES = ["spotlight", "magazine", "split", "framed",
               "spotlight_series", "welcome", "anniversary", "grid"]
SERIES_STYLES = ["spotlight_series", "welcome", "anniversary"]  # skin-aware renderers (take a Skin)


# --- shared helpers --------------------------------------------------------
def _key_plain_bg(img: Image.Image):
    """Remove a PLAIN, uniform, light studio background using numpy + PIL flood-fill (NO external deps, so it
    works on the droplet without rembg or a bg-removal key) — the Talentrupt team photos are studio shots on
    a plain wall, so this yields a clean cut-out for free. Flood-filling the background from the BORDER keeps
    any light clothing that's enclosed by the person (no holes). Returns a trimmed RGBA subject, or None when
    the background isn't a uniform light plain (caller falls back). Only the background is removed — the
    face/subject pixels are untouched."""
    import numpy as np
    try:
        rgb = img.convert("RGB")
        w, h = rgb.size
        if w < 64 or h < 64:
            return None
        arr = np.asarray(rgb).astype(np.float32)
        s = max(16, min(w, h) // 18)
        # Background reference = the TOP strip: for a head-and-shoulders portrait the area above the head is
        # almost always the plain wall, even when the person fills the frame and touches the side/bottom
        # borders. The strip must be LIGHT and fairly UNIFORM (a plain studio wall), else we bail.
        top = arr[:s, :].reshape(-1, 3)
        bg = np.median(top, axis=0)
        if float(bg.mean()) < 118 or float(top.std(0).mean()) > 26:
            return None
        from PIL import ImageDraw
        work = rgb.copy()
        sentinel = (0, 254, 1)
        # Seed the flood-fill ONLY from border points that actually match the wall colour (never from a
        # person-coloured border), so it fills the true background and never bleeds into the subject.
        candidates = [(2, 2), (w - 3, 2), (w // 2, 2), (w // 4, 2), (3 * w // 4, 2),
                      (2, h // 10), (w - 3, h // 10), (2, h // 3), (w - 3, h // 3), (2, h - 3), (w - 3, h - 3)]
        seeded = 0
        for (x, y) in candidates:
            if float(np.linalg.norm(arr[y, x] - bg)) < 45:
                try:
                    ImageDraw.floodfill(work, (x, y), sentinel, thresh=46)
                    seeded += 1
                except Exception:
                    pass
        if seeded == 0:
            return None
        warr = np.asarray(work)
        is_bg = np.all(warr == np.array(sentinel, dtype=warr.dtype), axis=-1)      # border-connected background
        # Also remove the person's soft CAST SHADOW on the wall: neutral (low-saturation), mid-light greys —
        # which the flood-fill can't reach. These are NOT the (warm) skin, the (saturated navy) clothes or the
        # (dark) hair, so gating on low saturation + mid brightness targets the shadow without eating the person.
        mx = arr.max(-1)
        mn = arr.min(-1)
        bright = arr.mean(-1)
        # Remove the person's cast SHADOW and any leftover LIGHT WALL the flood-fill couldn't reach (the exact
        # "white shadow" patch behind a shoulder). Both are NEUTRAL (low-saturation) greys/whites; skin is WARM
        # (bigger channel spread) and hair/dark clothes are dark, so gating on low saturation + not-too-dark
        # strips the wall & shadow without eating the person. (A LIGHT-coloured shirt is the one exception —
        # use the remove.bg key for those.)
        neutral = (~is_bg) & ((mx - mn) < 22) & (bright > 74)
        is_bg = is_bg | neutral
        frac = float(is_bg.mean())
        if frac < 0.10 or frac > 0.92:  # no real subject, or nearly everything keyed -> bail
            return None
        alpha = np.where(is_bg, 0, 255).astype(np.uint8)
        # Keep ONLY the person's connected blob (drop a disconnected wall-shadow blob the flood-fill missed):
        # flood-fill the foreground from the centre line; anything not connected to the subject is discarded.
        fgimg = Image.fromarray(alpha, "L").convert("RGB")
        for cy in (0.45, 0.35, 0.55, 0.28):
            sx, sy = w // 2, int(h * cy)
            if 0 <= sy < alpha.shape[0] and alpha[sy, sx] > 127:
                try:
                    ImageDraw.floodfill(fgimg, (sx, sy), (0, 254, 1), thresh=12)
                except Exception:
                    pass
                comp = np.all(np.asarray(fgimg) == np.array((0, 254, 1)), axis=-1)
                if float(comp.mean()) > 0.05:  # a real subject blob -> keep only it
                    alpha = np.where(comp, 255, 0).astype(np.uint8)
                break
        # Fill small ENCLOSED holes the neutral gate opened inside the person (eye-whites, printed shirt text):
        # flood the true background from a top corner; anything NOT reached from it is the person -> opaque.
        try:
            inv = Image.fromarray(alpha, "L").convert("RGB")
            ImageDraw.floodfill(inv, (0, 0), (7, 8, 9), thresh=40)
            reached = np.all(np.asarray(inv) == np.array((7, 8, 9)), axis=-1)
            if float(reached.mean()) > 0.03:  # the corner really was background
                alpha = np.where(reached, 0, 255).astype(np.uint8)
        except Exception:
            pass
        # Despeckle, then ERODE 1px (MinFilter) to cut the light background fringe that causes a 'pasted'
        # halo on a real photo, then a tight feather.
        a = (Image.fromarray(alpha, "L").filter(ImageFilter.MedianFilter(5))
             .filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(1.0)))
        out = rgb.convert("RGBA")
        out.putalpha(a)
        bbox = out.getbbox()
        return out.crop(bbox) if bbox else out
    except Exception:
        return None


def _cutout(img: Image.Image) -> Image.Image:
    """Background-removed RGBA of the subject. Order: hosted API (when a key is set — keeps rembg off the
    droplet) → offline rembg (dev) → plain-studio-background keying (numpy, no deps → works on the droplet
    for the team's studio headshots) → opaque RGBA (caller uses a non-framed full-photo fallback). The face
    is never altered."""
    try:  # hosted API (remove.bg / Photoroom) — no-op unless bg_removal_api_key is set
        import io as _io
        api = cutout.remove_bg_api(img_to_png_bytes(img)) if cutout.cutout_available() else None
        if api:
            out = Image.open(_io.BytesIO(api)).convert("RGBA")
            bbox = out.getbbox()
            return out.crop(bbox) if bbox else out
    except Exception:
        pass
    try:
        from rembg import remove  # heavy import; only loaded when a cut-out post is built
        out = remove(img).convert("RGBA")
        bbox = out.getbbox()
        return out.crop(bbox) if bbox else out
    except Exception:
        pass
    keyed = _key_plain_bg(img)  # free studio-background removal on the droplet (numpy + flood-fill)
    if keyed is not None:
        return keyed
    return img.convert("RGBA")


def img_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


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


def _enhance_photo(img: Image.Image) -> Image.Image:
    """Tasteful auto-cleanup so a casual phone photo reads more professional — even lighting, cleaner
    colour, a touch of sharpness. Pixel-level only; the person's IDENTITY / face is never changed."""
    try:
        img = img.convert("RGB")
        img = ImageOps.autocontrast(img, cutoff=1)          # even out exposure
        img = ImageEnhance.Brightness(img).enhance(1.03)
        img = ImageEnhance.Color(img).enhance(1.06)          # a little more life in the colour
        img = ImageEnhance.Contrast(img).enhance(1.05)
        img = ImageEnhance.Sharpness(img).enhance(1.18)      # crisper without looking processed
    except Exception:
        pass
    return img


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
    # Shrink until the text fits max_lines AND no single line overflows the width — a long word like
    # "Talentrupt" can't wrap, so without the width check it spills past max_w onto the photo.
    while (len(lines) > max_lines or any(d.textlength(ln, font=f) > max_w for ln in lines)) and size > 34:
        size -= 5
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


def _fit_font(d, text, font_fn, size, max_w, floor=26):
    """Return `font_fn(size)` shrunk until `text` fits `max_w` (so a long name/role/tagline can't spill
    past the text column onto the photo)."""
    f = font_fn(size)
    while d.textlength(text, font=f) > max_w and size > floor:
        size -= 3
        f = font_fn(size)
    return f


def _role_badge(d, x, y, role, fill=WHITE, fg=NAVY, max_w=None) -> None:
    fs = 30
    bf = body_font(fs)
    if max_w:  # shrink so a long role ("Talent Discovery Specialist") stays within the text column
        while (24 + 16 + d.textlength(role, font=bf) + 40) > max_w and fs > 18:
            fs -= 2
            bf = body_font(fs)
    rw = d.textlength(role, font=bf)
    bw = 24 + 16 + rw
    d.rounded_rectangle([x, y, x + bw + 40, y + 52], radius=26, fill=fill)
    ix, iy = x + 22, y + 16  # mini briefcase, drawn (no emoji-font dependency)
    d.rounded_rectangle([ix, iy + 5, ix + 24, iy + 20], radius=3, fill=fg)
    d.rectangle([ix + 8, iy, ix + 16, iy + 7], outline=fg, width=3)
    d.text((ix + 36, y + (52 - fs) // 2 - 2), role, font=bf, fill=fg)


def _draw_featuring(d, x, y, name, role, name_size=58) -> None:
    if not name:  # no name given (e.g. "use this photo") -> just the headline + photo, no name block
        return
    d.rectangle([x, y - 16, x + 120, y - 12], fill=WHITE)
    d.text((x, y), "Featuring", font=body_font(32), fill=CREAM)
    d.text((x, y + 40), name, font=heading_font(name_size), fill=WHITE)
    if role:
        _role_badge(d, x, y + 40 + 72, role)


# --- advanced primitives (keyword box, script, accents, safe placement, overlap guard) -------------
def _draw_headline_highlight(d, x, y, text, max_w, skin, keyword="", size=104, max_lines=3):
    """Headline in the skin's text colour with a filled accent box hugging ONE keyword (default: the
    last word) — the reference 'red-box a word' look. Auto-shrinks so a long word can't spill onto the
    photo. Returns (y_below, bbox)."""
    text = (text or "On a Mission!").strip()
    f = heading_font(size)
    lines = _wrap(d, text, f, max_w)
    while (len(lines) > max_lines or any(d.textlength(ln, font=f) > max_w for ln in lines)) and size > 34:
        size -= 5
        f = heading_font(size)
        lines = _wrap(d, text, f, max_w)
    kw = re.sub(r"[^\w]", "", keyword or "").lower()
    if not kw:
        words_all = [w for w in re.split(r"\s+", text) if w]
        kw = re.sub(r"[^\w]", "", words_all[-1]).lower() if words_all else ""
    target = None
    for li, ln in enumerate(lines):
        for wi, wd in enumerate(ln.split(" ")):
            if kw and re.sub(r"[^\w]", "", wd).lower() == kw:
                target = (li, wi)
                break
        if target:
            break
    lh = int(f.size * 1.18) + 10
    top, maxx = y, x
    space = d.textlength(" ", font=f)
    for li, ln in enumerate(lines):
        wx = x
        for wi, wd in enumerate(ln.split(" ")):
            ww = d.textlength(wd, font=f)
            if target == (li, wi):
                d.rounded_rectangle([wx - 8, y - 2, min(x + max_w, wx + ww + 10), y + f.size + 12],
                                    radius=9, fill=skin.accent)
                d.text((wx, y + 3), wd, font=f, fill=skin.on_accent)
            else:
                d.text((wx, y + 3), wd, font=f, fill=skin.text)
            wx += ww + space
        maxx = max(maxx, wx - space)
        y += lh
    if target is None:  # keyword didn't survive wrapping -> underline the block in the accent colour
        d.rectangle([x, y - 4, min(x + max_w, int(maxx)), y + 8], fill=skin.accent)
        y += 16
    return y, (x - 10, top - 4, int(maxx) + 12, y)


def _draw_featuring_script(d, x, y, name, role, skin, name_size=52, max_w=None) -> tuple:
    """'Featuring [Name]' — the name in the handwritten script font + a role badge, both width-clamped to
    `max_w` so they stay in the text column (never over the photo). Returns its bbox."""
    if not name:
        return (x, y, x, y)
    d.text((x, y), "Featuring", font=body_font(26), fill=skin.sub)
    sf = _fit_font(d, name, script_font, int(name_size * 1.12), max_w or 9999, floor=34)
    ny = y + 28
    d.text((x, ny), name, font=sf, fill=skin.name)
    by = d.textbbox((x, ny), name, font=sf)[3] + 4
    if role:
        _role_badge(d, x, by, role, fill=skin.accent, fg=skin.on_accent, max_w=max_w)
        by += 56
    return (x - 4, y - 4, x + (max_w or 300) + 6, by)  # bbox right clamped to the text column


# decorative accents — callers place them ONLY in reserved zones (never over the photo or text).
def _accent_dot_grid(d, x, y, cols, rows, gap=26, r=4, fill=NAVY2):
    for i in range(cols):
        for j in range(rows):
            cx, cy = x + i * gap, y + j * gap
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


def _accent_arc(d, cx, cy, radius=150, start=0, n=26, step=7, r=4, fill=WHITE):
    for i in range(n):
        a = math.radians(start + i * step)
        px, py = int(cx + radius * math.cos(a)), int(cy + radius * math.sin(a))
        d.ellipse([px - r, py - r, px + r, py + r], fill=fill)


def _accent_chevrons(d, x, y, n=3, size=22, gap=14, color=RED, width=6):
    for i in range(n):
        ox = x + i * gap
        d.line([(ox, y), (ox + size * 0.62, y + size * 0.5), (ox, y + size)], fill=color, width=width, joint="curve")


def _accent_starburst(d, cx, cy, r_out=70, r_in=30, points=12, color=RED):
    pts = []
    for i in range(points * 2):
        rr = r_out if i % 2 == 0 else r_in
        a = math.radians(i * 180.0 / points)
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    d.polygon(pts, fill=color)


def _accent_arrow(d, x0, y0, x1, y1, color=RED, width=7, curve=0.28):
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    cxp, cyp = mx - dy * curve, my + dx * curve
    pts = [((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cxp + t * t * x1,
            (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cyp + t * t * y1) for t in [i / 24 for i in range(25)]]
    d.line(pts, fill=color, width=width, joint="curve")
    ax, ay = pts[-1]
    bx, by = pts[-4]
    ang = math.atan2(ay - by, ax - bx)
    for da in (math.radians(150), math.radians(-150)):
        d.line([(ax, ay), (ax + 22 * math.cos(ang + da), ay + 22 * math.sin(ang + da))], fill=color, width=width)


def _accent_squiggle(d, x, y, w, amp=8, color=RED, width=5):
    pts = [(x + i, y + amp * math.sin(i / 22.0)) for i in range(0, int(w) + 1, 6)]
    d.line(pts, fill=color, width=width, joint="curve")


_CONFETTI = [RED, NAVY, (0xF5, 0xC0, 0x42), (0xFF, 0x7A, 0x52), (0x2A, 0x6E, 0xD6), CREAM]


def _confetti(d, x0, y0, x1, y1, n, seed) -> None:
    """Scatter small celebratory shapes (tilted ticker-tape, dots, ribbons) in a zone. Callers pass the
    top / right band so it never covers the text column."""
    rnd = random.Random(int(seed) * 7 + 13)
    for _ in range(n):
        x, y = rnd.randint(int(x0), int(x1)), rnd.randint(int(y0), int(y1))
        col = rnd.choice(_CONFETTI)
        k = rnd.randint(0, 2)
        if k == 0:  # tilted ticker-tape rectangle
            w, h = rnd.randint(8, 16), rnd.randint(4, 7)
            a = math.radians(rnd.randint(0, 180))
            ca, sa = math.cos(a), math.sin(a)
            pts = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]
            d.polygon([(x + px * ca - py * sa, y + px * sa + py * ca) for px, py in pts], fill=col)
        elif k == 1:  # dot
            s = rnd.randint(4, 8)
            d.ellipse([x, y, x + s, y + s], fill=col)
        else:  # short ribbon
            d.line([(x, y), (x + rnd.randint(8, 16), y + rnd.randint(-6, 8))], fill=col, width=3)


def _pro_scene(canvas, d, skin, variant) -> None:
    """Premium backdrop for a featured person: the signature rail + a scatter of confetti in the top-right
    band + a small dot cluster. The navy 'halo' behind the person is drawn in _place_person (it needs the
    person's exact position). Drawn BEFORE the person so they sit on top."""
    d.rectangle([0, 0, RAIL_W, H], fill=skin.accent)
    _confetti(d, W * 0.36, 34, W - 28, H * 0.34, 26, variant)
    _accent_dot_grid(d, 84, 132, 4, 3, gap=22, r=4, fill=skin.shade)


def _intersect(a, b, margin=0):
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + margin <= bx0 or bx1 + margin <= ax0 or ay1 + margin <= by0 or by1 + margin <= ay0)


def _ensure_clear(label, *boxes) -> bool:
    """Verify the given bounding boxes are mutually disjoint — the "nothing overrides" guarantee. The
    layout math keeps text left of the photo and the wordmark in a reserved margin; this logs a warning
    if that's ever violated so a regression can't ship silently."""
    bs = [b for b in boxes if b]
    for i in range(len(bs)):
        for j in range(i + 1, len(bs)):
            if _intersect(bs[i], bs[j]):
                log.warning("OVERLAP in %s: %s vs %s", label, bs[i], bs[j])
                return False
    return True


def _place_person(canvas, d, skin, photo, hero, target_h_frac=0.82, max_w_frac=0.55, right_pad=30, backdrop=False):
    """Float the cut-out person on the RIGHT (real cut-out) or a premium rounded framed card (fallback).
    Returns (person_left, person_box) so callers clamp all text to the LEFT of person_left. The width cap
    (<=0.55 W) guarantees person_left stays >= ~456, so the clamped headline (min 340) can never reach it.
    `backdrop` draws a navy 'halo' circle behind the cut-out person (sized to them → never reaches text)."""
    # A real cut-out has transparency AND covers a decent part of the frame. A tiny bbox means the
    # remover only caught a fragment (e.g. just the head) — upscaling that looks bad, so fall back to
    # the clean framed photo instead. (remove.bg on prod yields full, clean cut-outs.)
    cut_ok = (hero.mode == "RGBA" and hero.getextrema()[3][0] < 245
              and hero.width >= photo.width * 0.42 and hero.height >= photo.height * 0.45)
    if cut_ok:
        target_h = int(H * target_h_frac)
        scale = target_h / hero.height
        if hero.width * scale > W * max_w_frac:
            scale = (W * max_w_frac) / hero.width
        hero = hero.resize((max(1, int(hero.width * scale)), max(1, int(hero.height * scale))), Image.LANCZOS)
        try:
            hero = hero.filter(ImageFilter.SHARPEN)
        except Exception:
            pass
        hx, hy = W - hero.width - right_pad, H - hero.height
        if backdrop:  # navy halo behind the person (upper body); radius stays right of the text column
            r = int(hero.width * 0.46)
            ccx, ccy = hx + hero.width // 2, hy + int(hero.height * 0.30)
            halo = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
            ImageDraw.Draw(halo).ellipse([ccx - r, ccy - r, ccx + r, ccy + r],
                                         fill=(*(NAVY2 if skin.key == "navy" else NAVY), 255))
            canvas.paste(halo, (0, 0), halo)
        shadow = Image.new("RGBA", hero.size, (0, 0, 0, 0))
        shadow.paste((0, 0, 0, 150), (0, 0), hero.split()[-1])
        shadow = shadow.filter(ImageFilter.GaussianBlur(20))
        canvas.paste(shadow, (hx + 14, hy + 10), shadow)
        canvas.paste(hero, (hx, hy), hero)
        return hx, (hx, hy, hx + hero.width, hy + hero.height)
    # framed-card fallback (skin-aware double frame + red corner tab so it reads as an editorial card)
    fw, fh = int(W * 0.50), int(H * 0.72)
    fx, fy = W - fw - 54, (H - fh) // 2 + 24
    card = _cover_fit(photo, fw, fh)
    try:
        card = card.filter(ImageFilter.UnsharpMask(radius=1.4, percent=90, threshold=3))
    except Exception:
        pass
    rad = 42
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([fx - 4, fy - 4, fx + fw + 4, fy + fh + 4], radius=rad + 6, fill=(0, 0, 0, 130))
    sh = sh.filter(ImageFilter.GaussianBlur(24))
    canvas.paste(sh, (0, 0), sh)
    mask = Image.new("L", (fw, fh), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, fw, fh], radius=rad, fill=255)
    canvas.paste(card, (fx, fy), mask)
    d.rounded_rectangle([fx - 6, fy - 6, fx + fw + 6, fy + fh + 6], radius=rad + 6, outline=skin.frame, width=6)
    d.rounded_rectangle([fx - 12, fy - 12, fx + fw + 12, fy + fh + 12], radius=rad + 10, outline=skin.accent, width=3)
    d.rounded_rectangle([fx + fw - 40, fy - 16, fx + fw + 16, fy + 26], radius=10, fill=skin.accent)
    return fx, (fx - 12, fy - 12, fx + fw + 12, fy + fh + 12)


def _paint_scene_bg(canvas, d, skin, variant) -> None:
    """Fill the background for a skin + tasteful accents kept OUT of the text/photo zones."""
    d.rectangle([0, 0, RAIL_W, H], fill=skin.accent)  # signature left rail
    if skin.key in ("navy", "red"):
        rects, (ax, ay, a0) = _BACKDROPS[variant % len(_BACKDROPS)]
        for (x, y, w, h, rot) in rects:  # geometric shapes on the right — the person covers most
            g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            ImageDraw.Draw(g).rounded_rectangle([0, 0, w, h], radius=40, fill=(*skin.shade, 150))
            gr = g.rotate(rot, expand=True)
            canvas.paste(gr, (x, y), gr)
        _accent_arc(d, ax, ay, 150, a0, 26, 7, 4, WHITE)
    else:  # light / cream: a subtle dot cluster in the top-right corner (above/behind the person)
        _accent_dot_grid(d, W - 150, 44, 5, 4, gap=24, r=4, fill=skin.shade)


def _extract_years(text: str) -> str:
    """The anniversary number — e.g. '7' from '7 years', '7 strong years', 'celebrating 7 years'. Only
    when the text is actually about an anniversary (mentions year(s)/anniversary)."""
    t = (text or "").lower()
    if not re.search(r"\byears?\b|\byrs?\b|anniversar", t):
        return ""
    m = re.search(r"\b(\d{1,2})\b", t)
    return m.group(1) if m else ""


def detect_series(text: str) -> str:
    """Pick the reference series from the message: anniversary / welcome / grid / spotlight_series."""
    t = (text or "").lower()
    if _extract_years(t) or "anniversary" in t or "workversary" in t or "work-versary" in t:
        return "anniversary"
    if any(w in t for w in ("welcome", "welcoming", "joining", "joins", "joined", "new hire", "onboard", "onboarding")):
        return "welcome"
    if any(w in t for w in ("team", "everyone", "group", "all of us", "one year strong", "the crew", "the squad")):
        return "grid"
    return "spotlight_series"


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
    paste_wordmark(canvas, 70, H - 64, 240, 46, dark_bg=True)  # wordmark in the clean bottom margin
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
    paste_wordmark(canvas, 70, H - 64, 240, 46, dark_bg=True)  # on the dark scrim, bottom-left
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
    paste_wordmark(canvas, pad, H - 64, 230, 46, dark_bg=True)  # on the navy panel, bottom-left
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
    paste_wordmark(canvas, 0, H - 64, W, 46, dark_bg=True, align="center")  # centered in the bottom margin
    return canvas


# --- skin-aware series formats (the reference "employee feature" looks, on a rotating skin) ---------
_TAGLINES = [
    "Let's build the future, together!",
    "Here's to what's next!",
    "Making great things happen.",
    "Onward and upward!",
    "Ready to make an impact!",
]


def _layout_spotlight_series(photo, name, role, headline, question, variant, skin, keyword="", kicker=""):
    """Premium featured-person post: the ENHANCED real cut-out floating on a navy halo with confetti,
    wordmark leading top-left, a red-box keyword headline, a script tagline, and 'Featuring [Name]' +
    role badge — on the given skin. (Casual photo -> clean, professional post; face never changed.)"""
    photo = _enhance_photo(photo)
    canvas = Image.new("RGB", (W, H), skin.bg)
    d = ImageDraw.Draw(canvas)
    _pro_scene(canvas, d, skin, variant)
    hero = _cutout(photo)
    person_left, person_box = _place_person(canvas, d, skin, photo, hero, backdrop=True)
    pad = 70
    hl_w = max(340, person_left - pad - 30)
    paste_wordmark(canvas, pad, 52, 230, 40, dark_bg=skin.wm_dark)  # wordmark leads, top-left
    y = 128
    if kicker:
        d.text((pad, y), kicker.upper(), font=heading_font(26), fill=skin.accent)
        y += 44
    y, head_box = _draw_headline_highlight(d, pad, y, headline, hl_w, skin, keyword=keyword)
    sub_box = None
    if question:
        qf = body_font(32)
        sy = y + 12
        for ln in _wrap(d, question, qf, hl_w)[: max(1, ((H - 420) - (y + 12)) // 42)]:
            d.text((pad, sy), ln, font=qf, fill=skin.sub)
            sy += 42
        sub_box = (pad, y + 12, pad + hl_w, sy)
        y = sy
    tag = _TAGLINES[variant % len(_TAGLINES)]  # script tagline, width-clamped to the text column
    d.text((pad, y + 18), tag, font=_fit_font(d, tag, script_font, 48, hl_w, 28), fill=skin.accent)
    feat_box = _draw_featuring_script(d, pad, H - 250, name, role, skin, max_w=hl_w)
    _ensure_clear("spotlight_series/" + skin.key, person_box, head_box, sub_box, feat_box)
    return canvas


def _layout_welcome(photo, name, role, headline, question, variant, skin):
    first = name.split()[0] if name else "Aboard"
    return _layout_spotlight_series(photo, name, role, headline or f"Welcome, {first}!", question, variant,
                                    skin, keyword="Welcome", kicker="New to the team")


def _layout_anniversary(photo, name, role, headline, question, variant, skin):
    """'X Strong Years': giant script number, name + role, a short story/quote — the ENHANCED real cut-out
    floating on a navy halo with confetti. Face never changed."""
    photo = _enhance_photo(photo)
    canvas = Image.new("RGB", (W, H), skin.bg)
    d = ImageDraw.Draw(canvas)
    _pro_scene(canvas, d, skin, variant)
    hero = _cutout(photo)
    person_left, person_box = _place_person(canvas, d, skin, photo, hero, backdrop=True)
    pad = 70
    hl_w = max(340, person_left - pad - 30)
    paste_wordmark(canvas, pad, 52, 230, 40, dark_bg=skin.wm_dark)
    yrs = _extract_years(f"{headline} {question}")
    big = script_font(190)
    label = yrs if yrs else "Strong"
    d.text((pad, 104), label, font=big, fill=skin.accent)
    nb = d.textbbox((pad, 104), label, font=big)
    y = nb[3] - 4
    hf = heading_font(54)
    for ln in _wrap(d, "STRONG YEARS" if yrs else "YEARS STRONG", hf, hl_w):
        d.text((pad, y), ln, font=hf, fill=skin.text)
        y += 64
    y += 6
    _accent_squiggle(d, pad, y, min(hl_w, 300), color=skin.accent)
    y += 28
    if name:
        d.text((pad, y), name, font=_fit_font(d, name, heading_font, 52, hl_w, 34), fill=skin.name)
        y += 66
        if role:
            _role_badge(d, pad, y, role, fill=skin.accent, fg=skin.on_accent, max_w=hl_w)
            y += 62
    if question:
        qf = body_font(30)
        sy = y + 6
        for ln in _wrap(d, question, qf, hl_w)[: max(1, ((H - 90) - sy) // 40)]:
            d.text((pad, sy), ln, font=qf, fill=skin.sub)
            sy += 40
        y = sy
    _ensure_clear("anniversary/" + skin.key, person_box, (pad - 4, 52, pad + hl_w, min(y, H - 66)))
    return canvas


def build_team_grid(brand, photos: list[bytes], labels: list[tuple[str, str]],
                    headline: str = "", skin=None, variant: int = 0) -> tuple[str, str, dict]:
    """'One Year Strong': a rounded-card grid of multiple employees, each with a name strip. No cut-out
    needed (crowd of framed cards) → safe on prod today. Rendered on a skin."""
    sk = skin if isinstance(skin, Skin) else resolve_skin(skin or "navy")
    photos = photos[:9] or [b""]
    n = len(photos)
    cols = 1 if n == 1 else (2 if n <= 4 else 3)
    rows = math.ceil(n / cols)
    canvas = Image.new("RGB", (W, H), sk.bg)
    d = ImageDraw.Draw(canvas)
    _paint_scene_bg(canvas, d, sk, variant)
    pad = 60
    _draw_headline_highlight(d, pad, 56, headline or "One Year Strong", W - 2 * pad, sk, size=72, max_lines=2)
    top, bottom, g, strip = 210, H - 108, 26, 52
    cw = (W - 2 * pad - (cols - 1) * g) // cols
    ch = (bottom - top - (rows - 1) * g) // rows
    for idx, pb in enumerate(photos):
        r, c = divmod(idx, cols)
        cx, cy = pad + c * (cw + g), top + r * (ch + g)
        try:
            img = ImageOps.exif_transpose(Image.open(io.BytesIO(pb)).convert("RGB"))
        except Exception:
            continue
        ph = _cover_fit(img, cw, ch - strip)
        mask = Image.new("L", (cw, ch - strip), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw, ch - strip], radius=26, fill=255)
        canvas.paste(ph, (cx, cy), mask)
        d.rounded_rectangle([cx - 3, cy - 3, cx + cw + 3, cy + ch - strip + 3], radius=29, outline=sk.frame, width=3)
        nm = labels[idx][0] if idx < len(labels) else ""
        if nm:
            nf = heading_font(30)
            tw = d.textlength(nm, font=nf)
            d.text((cx + (cw - tw) // 2, cy + ch - strip + 12), nm, font=nf, fill=sk.name)
    paste_wordmark(canvas, 0, H - 58, W, 40, dark_bg=sk.wm_dark, align="center")
    file_name = unique_name("tr-team", "png")
    path = storage_subdir("images") / file_name
    canvas.convert("RGB").save(str(path), "PNG")
    return str(path), file_name, {
        "url": public_url("images", file_name), "renderer": "team_grid", "style": "grid",
        "skin": sk.key, "size": f"{W}x{H}", "kind": "team",
    }


_LAYOUTS = {
    "spotlight": _layout_spotlight,
    "magazine": _layout_magazine,
    "split": _layout_split,
    "framed": _layout_framed,
}
_SERIES = {
    "spotlight_series": _layout_spotlight_series,
    "welcome": _layout_welcome,
    "anniversary": _layout_anniversary,
}


def build_team_image(
    brand: Brand | None, photo_bytes: bytes, name: str, role: str = "",
    headline: str = "", question: str = "", variant: int = 0, style: str = "spotlight",
    skin: str = "navy",
) -> tuple[str, str, dict]:
    """Compose a branded feature post around a real photo. Legacy styles (spotlight/magazine/split/framed)
    are navy; the SERIES styles (spotlight_series/welcome/anniversary) render on the given `skin`, so the
    same person isn't always shown navy. Returns (path, file_name, meta). Never an AI face."""
    try:  # team photos may be HEIC (iPhone) — register the opener when available
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    photo = ImageOps.exif_transpose(Image.open(io.BytesIO(photo_bytes)).convert("RGB"))
    sk = resolve_skin(skin)
    if style in _SERIES:
        canvas = _SERIES[style](photo, name, role, headline, question, variant, sk)
        skin_key = sk.key
    else:
        style = style if style in _LAYOUTS else "spotlight"
        canvas = _LAYOUTS[style](photo, name, role, headline, question, variant)
        skin_key = "navy"

    file_name = unique_name("tr-team", "png")
    path = storage_subdir("images") / file_name
    canvas.convert("RGB").save(str(path), "PNG")
    return str(path), file_name, {
        "url": public_url("images", file_name),
        "renderer": f"team_{style}",
        "style": style,
        "skin": skin_key,
        "size": f"{W}x{H}",
        "kind": "team",
    }


# --- AI-scene format: gpt-image-1 makes the BACKGROUND, the REAL cut-out person goes on top ----------
# Deliberately span DIFFERENT dominant tones (light / warm / red / navy / office) so the photo skin
# doesn't come out navy every time.
_SCENE_TYPES = [
    "a bright, airy, minimal studio backdrop in soft off-white and warm cream with gentle coral-red "
    "geometric accents and soft shadows, clean and premium, plenty of light",
    "a warm congratulatory backdrop: soft golden bokeh, a smooth gradient from warm cream to soft gold, "
    "tasteful sparkle and gentle light rays, light and uplifting, magazine-cover feel",
    "a bold coral-red-forward abstract scene with deep navy accents and soft rounded geometric shapes, "
    "confident and energetic, dynamic depth",
    "a premium modern office environment, bright and aspirational, floor-to-ceiling windows with soft "
    "city bokeh, clean editorial composition, warm daylight, mostly light tones",
    "a bold abstract brand backdrop: deep navy with dynamic flowing coral-red ribbons and soft rounded "
    "geometric shapes, energetic and celebratory, depth and a soft glow",
    "a contemporary tech-forward abstract scene: a cool gradient with subtle glowing connected-dot "
    "network lines and coral accents, sleek and professional, soft depth",
]


def _scene_prompt(headline: str, question: str, variant: int, theme: str = "") -> str:
    theme = (theme or "").strip()
    # A campaign brief DRIVES the backdrop subject/setting (e.g. football -> a stadium/pitch); with no theme
    # we rotate a generic on-brand mood. Either way it's a PEOPLE-FREE background (the person is composited on).
    scene = (f'a setting that clearly reflects this campaign theme — "{theme[:160]}" — its real-world '
             "location, objects and atmosphere (but with NO people in it)" if theme
             else _SCENE_TYPES[variant % len(_SCENE_TYPES)])
    # NOTE: deliberately do NOT feed the literal headline/message into the prompt — gpt-image tends to
    # RENDER it as ghost text in the background despite "NO text". We only steer the SETTING + on-brand MOOD.
    return (
        f"A richly designed, premium social-media BACKGROUND graphic for a corporate post: {scene}. "
        "Warm, professional, celebratory on-brand mood (welcome, teamwork, growth, a milestone), tasteful. "
        "Talentrupt brand palette: deep navy #0B3559, coral red #F6404C, warm cream #EBE9DF — use "
        "them tastefully and VARY the dominant tone per the scene above (do NOT make it uniformly dark "
        "navy). High-end editorial and cinematic, polished — NOT a plain flat colour. ABSOLUTELY NO "
        "people, NO person, NO faces, NO text, NO words, NO letters, NO numbers, NO logos, NO signage. Keep "
        "the RIGHT side and the BOTTOM-LEFT relatively clean so a person photo (right) and a caption (left) "
        "sit cleanly on top. Square 1:1 composition."
    )


def _ai_scrim(canvas: Image.Image) -> Image.Image:
    """Navy gradient over the AI scene — strong on the left + bottom (for text), clear upper-right."""
    import numpy as np
    w, h = canvas.size
    xs = np.linspace(0, 1, w)[None, :]
    ys = np.linspace(0, 1, h)[:, None]
    left = np.clip(1.0 - xs / 0.55, 0, 1)
    bottom = np.clip((ys - 0.5) / 0.5, 0, 1)
    a = np.clip(left * 0.9 + bottom * 0.8, 0, 0.96)
    alpha = Image.fromarray((a * 255).astype("uint8"), "L")
    layer = Image.new("RGBA", (w, h), (*NAVY, 255))
    layer.putalpha(alpha)
    return Image.alpha_composite(canvas.convert("RGBA"), layer).convert("RGB")


# CANONICAL identity directive — the user's standing rule for EVERY image path that edits/re-renders a real
# person's face (saved verbatim in docs/IMAGE-GENERATION.md and the assistant's memory). Any new face-editing
# prompt MUST prepend this so identity is never altered — only pose/lighting/surroundings change.
STRICT_FACE_DIRECTIVE = (
    "STRICT FACIAL CONSISTENCY MODE: treat the provided reference photo as the single source of truth for "
    "the face and prioritise its facial features for this and all subsequent generation. Maintain the "
    "subject's identity accurately — preserve their bone structure, face shape and proportions, jawline, "
    "cheekbones, nose, lips, eyes and eye spacing, eyebrows, skin tone and complexion, hair and hairstyle, "
    "facial hair, age and gender EXACTLY. Only adapt the POSE, LIGHTING and SURROUNDINGS. Do NOT alter their "
    "facial structure in any way — do NOT slim, reshape, age, de-age, smooth or beautify the face, and do NOT "
    "replace them with a different face. The result must be unmistakably the SAME individual, instantly "
    "recognisable as the person in the reference photo. "
)


# --- AI PORTRAIT: feed the REAL photo into gpt-image-1's edit endpoint so the SAME person is re-posed /
# re-lit / re-dressed into a VARIED premium scene (identity locked). This is the "best AI picture using the
# employee's photo" path — every look is different, so posts stop looking identical. Rotating art-directions
# span DIFFERENT settings, poses, wardrobe and dominant tones (never navy-every-time).
_PORTRAIT_LOOKS = [
    "in a bright, modern open-plan office with soft daylight from floor-to-ceiling windows and gentle city "
    "bokeh behind them; a relaxed, confident three-quarter stance",
    "against a clean off-white studio seamless backdrop with soft, even, flattering studio light; a warm, "
    "professional head-and-shoulders pose looking to camera",
    "in a warm, editorial golden-hour setting with soft bokeh and gentle light rays; an easy, self-assured "
    "pose with arms lightly crossed",
    "against a bold on-brand abstract backdrop of deep navy with flowing coral-red geometric shapes and a "
    "soft rim light; a strong, direct, empowered pose",
    "on a contemporary rooftop with a softly blurred city skyline and bright aspirational daylight; standing "
    "tall and forward-looking",
    "in a minimal cream-and-coral geometric set with a single soft shadow; a calm, approachable, slightly "
    "leaning pose",
    "in a sleek, tech-forward space with a cool gradient and subtle glowing connected-dot network lines and "
    "coral accents; a dynamic, modern pose",
    "in a collaborative co-working space with warm natural light and soft depth behind; an approachable, "
    "genuine expression",
]


def _portrait_prompt(headline: str, question: str, variant: int, theme: str = "") -> str:
    """Art-direct one identity-locked portrait edit. `variant` rotates the look so consecutive posts for the
    same person differ. The person is composed RIGHT so the deterministic caption/wordmark sit clean LEFT.
    `theme` (a campaign brief/topic) DRIVES the surroundings + wardrobe when set — so a Football campaign puts
    them on a pitch in kit, a Diwali campaign in festive decor, etc. (only pose/lighting/surroundings change;
    the face is still locked). When there's no theme it falls back to a rotating premium corporate look."""
    msg = " ".join(x for x in (headline, question) if x).strip()
    celebrate = (f' The post celebrates: "{msg[:100]}" — let the mood echo it tastefully.' if msg else "")
    theme = (theme or "").strip()
    if theme:
        setting = (
            f'in an environment that clearly and literally reflects this CAMPAIGN THEME: "{theme[:200]}". '
            "Build the backdrop, location, props and activity around THAT theme so the scene is unmistakably "
            "on-topic (e.g. a football campaign -> on a real football pitch / stadium with a ball; a Diwali "
            "campaign -> warm festive lights, diyas and decor; a wellness campaign -> a calm bright studio). "
            "Give them a natural, confident pose that suits the theme"
        )
        wardrobe = (
            "WARDROBE: dress them appropriately FOR THE CAMPAIGN THEME above — sporty kit, festive, smart-"
            "casual or formal exactly as the theme demands — NOT a default business blazer unless the theme "
            "itself is corporate. "
        )
        kind = "themed campaign"
    else:
        setting = _PORTRAIT_LOOKS[variant % len(_PORTRAIT_LOOKS)]
        wardrobe = (
            "WARDROBE: dress them in a sharp, well-fitted business BLAZER — a navy or charcoal suit jacket over "
            "a crisp collared shirt (an optional tie), executive and polished, like a premium corporate headshot "
            "(do NOT leave them in a plain t-shirt or casual wear). "
        )
        kind = "corporate"
    return (
        f"Restyle the SAME person from the provided photo into a premium, photorealistic {kind} "
        "social-media portrait. "
        + STRICT_FACE_DIRECTIVE +
        "EXACTLY ONE PERSON: render only this single individual — do NOT add, invent, duplicate or "
        "hallucinate any other people or extra faces. If the source shows more than one person or is a "
        "graphic/screenshot, focus on the SINGLE main subject only. "
        f"Re-pose, re-light and re-stage them for the best look: place them {setting}.{celebrate} "
        + wardrobe +
        "COMPOSITION: a clean 1:1 square; compose the person on the RIGHT with their head in the upper-right; "
        "keep the LEFT ~40% as calm, softly-lit, uncluttered negative space for a caption. Talentrupt brand "
        "palette — deep navy #0B3559, coral red #F6404C, warm cream #EBE9DF — used tastefully, and VARY the "
        "dominant tone per the setting above (do NOT make it uniformly dark navy). Crisp focus, flattering "
        "light, high-end editorial quality. Absolutely NO text, NO words, NO letters, NO logos, NO watermarks."
    )


async def _ai_portrait_canvas(photo: Image.Image, headline: str, question: str, variant: int, theme: str = ""):
    """Re-render the SAME person (identity-locked) into a varied premium scene via the image-EDIT endpoint.
    `theme` (a campaign brief) steers the surroundings/wardrobe to match the campaign. Returns a 1080 RGB
    canvas with the person baked in, or None on failure/moderation refusal so the caller falls back to the
    safe real cut-out composite."""
    from ..providers import llm
    try:
        src = photo.copy()
        src.thumbnail((1024, 1024), Image.LANCZOS)  # ample detail for the face; keeps the upload snappy
        data = await llm.generate_image_edit(
            _portrait_prompt(headline, question, variant, theme), [img_to_png_bytes(src)],
            size="1024x1024", input_fidelity="high", mime="image/png",
            quality="medium",  # identity is held by input_fidelity, not quality — medium ~halves latency
        )
        if not data:
            return None
        canvas = _cover_fit(Image.open(io.BytesIO(data)).convert("RGB"), W, H)
        try:
            canvas = canvas.filter(ImageFilter.UnsharpMask(radius=2, percent=120, threshold=2))
        except Exception:
            pass
        return canvas
    except Exception:
        return None


# --- PORTRAIT iPHONE-FRAME banner (designed by the senior graphics team) ---------------------------
# The employee's identity-locked professional portrait sits inside a clean phone mockup on the RIGHT; the
# branded caption lives in a reserved LEFT column with a 64px gutter — provably non-overlapping. The device
# reads as a real phone on every skin (titanium rail + charcoal bezel), while the bg/text/accent rotate.
_PHONE_WEAR = [
    "dressed in a sharp, well-fitted navy business blazer over a crisp white shirt (executive, polished)",
    "dressed in a tailored charcoal blazer over a clean shirt with a subtle tie (sharp and professional)",
    "dressed in a sharp navy blazer over a crisp shirt, confident corporate-headshot styling",
    "dressed in a well-fitted dark blazer over a clean collared shirt, premium executive look",
]


def _phone_portrait_prompt(variant: int) -> str:
    """Identity-locked CENTERED vertical portrait prompt for the phone screen — clean cream studio backdrop,
    generous headroom so the rounded crop + dynamic island never clip the face. Always a sharp blazer."""
    wear = _PHONE_WEAR[variant % len(_PHONE_WEAR)]
    return (
        "Restyle the SAME person from the provided photo into a premium, photorealistic, VERTICAL PORTRAIT "
        "for a phone screen. "
        + STRICT_FACE_DIRECTIVE +
        "EXACTLY ONE PERSON — do NOT add, invent or duplicate any "
        "other person or extra faces. Compose a CENTERED head-and-shoulders to upper-chest portrait, subject "
        "dead-centre horizontally, facing camera with a calm, confident, approachable expression, shoulders "
        "squared, head in the upper third with generous even headroom and clean side margins so a "
        "rounded-corner crop will not clip the face or ears. Background: a smooth, uncluttered seamless studio "
        "backdrop in soft warm off-white / light cream with a single gentle soft shadow and a faint coral-red "
        "rim glow (Talentrupt palette: deep navy #0B3559, coral red #F6404C, warm cream #EBE9DF) — NO props, "
        "NO furniture, NO patterns, NO windows. Soft, even, flattering studio key light, gentle catchlights, "
        f"crisp focus on the eyes, natural skin. {wear}. Tall vertical portrait composition. Absolutely NO "
        "text, NO words, NO letters, NO logos, NO watermarks, NO borders, NO phone frame or UI — just the "
        "person on the clean backdrop."
    )


async def _phone_portrait_img(photo: Image.Image, variant: int):
    """Identity-locked portrait for the phone screen via the image-EDIT endpoint (tall 1024x1536, falling
    back to 1024x1024). Returns a PIL RGB image or None (caller uses the enhanced real photo instead)."""
    from ..providers import llm
    src = photo.copy()
    src.thumbnail((1024, 1024), Image.LANCZOS)
    png = img_to_png_bytes(src)
    for size in ("1024x1536", "1024x1024"):
        try:
            data = await llm.generate_image_edit(
                _phone_portrait_prompt(variant), [png], size=size, input_fidelity="high", mime="image/png")
            if data:
                return Image.open(io.BytesIO(data)).convert("RGB")
        except Exception:
            continue
    return None


# Device palette — a phone is a dark metallic object, so these stay CONSTANT on every skin (only the bg,
# text, accent chip and keyword box recolor per skin) so it always reads as a real iPhone.
_CHASSIS = (0xC9, 0xCE, 0xD6)   # titanium rail
_BEZEL_DK = (0x0E, 0x14, 0x20)  # charcoal bezel


def _place_person_phone(canvas, d, skin, portrait):
    """Draw the premium PORTRAIT iPhone mockup (right, vertically ~centred) holding `portrait`, and return
    (person_left, person_box) so all caption text clamps to the LEFT. Geometry per the senior-graphics-team
    FINAL spec; alpha effects (shadow, glass rim) are composited on RGBA layers so their opacity is honoured."""
    # soft drop shadow (down-right) BEFORE the device
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([630, 160, 1058, 1050], radius=72, fill=(0, 0, 0, 150))
    canvas.paste(sh.filter(ImageFilter.GaussianBlur(30)), (0, 0), sh.filter(ImageFilter.GaussianBlur(30)))
    # titanium chassis + charcoal bezel
    d.rounded_rectangle([612, 134, 1040, 1024], radius=72, fill=_CHASSIS)
    d.rounded_rectangle([620, 142, 1032, 1016], radius=64, fill=_BEZEL_DK)
    # the portrait fills the screen aperture (rounded so no square corners peek past the bezel)
    card = _cover_fit(portrait, 396, 858)
    try:
        card = card.filter(ImageFilter.UnsharpMask(radius=1.4, percent=90, threshold=3))
    except Exception:
        pass
    mask = Image.new("L", (396, 858), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, 396, 858], radius=56, fill=255)
    canvas.paste(card, (628, 150), mask)
    # polished glass + metal rim highlights (need alpha -> RGBA overlay)
    ov = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    od.rounded_rectangle([630, 152, 1022, 1006], radius=54, outline=(255, 255, 255, 60), width=2)
    od.rounded_rectangle([610, 132, 1042, 1026], radius=74, outline=(255, 255, 255, 70), width=2)
    canvas.paste(ov, (0, 0), ov)
    # dynamic island + camera speck (always dark, reads as a real cut-out)
    d.rounded_rectangle([780, 178, 872, 200], radius=11, fill=INK)
    d.ellipse([858, 186, 866, 194], fill=(0x24, 0x34, 0x4E))
    # subtle side buttons (chassis darkened), hugging the device edges
    btn = tuple(int(c * 0.7) for c in _CHASSIS)
    d.rounded_rectangle([1040, 360, 1045, 456], radius=3, fill=btn)
    d.rounded_rectangle([607, 300, 612, 364], radius=3, fill=btn)
    d.rounded_rectangle([607, 380, 612, 444], radius=3, fill=btn)
    # on-brand corner chip on the top bezel band (never over the screen or the text)
    d.rounded_rectangle([962, 142, 1032, 162], radius=10, fill=skin.accent)
    return 612, (605, 130, 1046, 1028)


async def _build_phone_banner(brand, photo, name, role, headline, question, variant, keyword):
    """DESIGN A — a clean PORTRAIT iPhone frame holding the employee's REAL photo (face NEVER changed),
    caption on the reserved LEFT (64px gutter, verified by `_ensure_clear`). The DESIGN varies — a random
    skin (bg / colours / accents) each time — but the person is the untouched real photo."""
    skin = resolve_skin(random.choice(DETERMINISTIC_SKINS))
    portrait = photo  # the REAL photo — face is never AI-regenerated
    canvas = Image.new("RGB", (W, H), skin.bg)
    d = ImageDraw.Draw(canvas)
    _paint_scene_bg(canvas, d, skin, variant)                     # rail + subtle accents (kept off the frame)
    person_left, person_box = _place_person_phone(canvas, d, skin, portrait)
    pad, hl_w = 70, 478                                            # 64px gutter to the device at x=612
    wm_box = (pad, 132, pad + 230, 176)
    try:
        paste_wordmark(canvas, pad, 132, 230, 44, dark_bg=skin.wm_dark)
    except Exception:
        wm_box = None
    y, head_box = _draw_headline_highlight(d, pad, 232, headline or "In the Spotlight.", hl_w, skin,
                                           keyword=keyword, size=96, max_lines=3)
    sub_box = None
    if question:
        qf = body_font(30)
        sy = y + 16
        for ln in _wrap(d, question, qf, hl_w)[: max(1, (724 - sy) // 40)]:
            d.text((pad, sy), ln, font=qf, fill=skin.sub)
            sy += 40
        sub_box = (pad, y + 16, pad + hl_w, sy)
    feat_box = _draw_featuring_script(d, pad, H - 250, name, role, skin, max_w=hl_w)
    _ensure_clear("phone_" + skin.key, person_box, head_box, sub_box, feat_box, wm_box)
    file_name = unique_name("tr-team", "png")
    path = storage_subdir("images") / file_name
    canvas.convert("RGB").save(str(path), "PNG")
    return str(path), file_name, {
        "url": public_url("images", file_name), "renderer": "team_phone_portrait",
        "style": "ai", "skin": skin.key, "size": f"{W}x{H}", "kind": "team", "design": "phone",
    }


async def _build_scene_banner(brand, photo, name, role, headline, question, variant, keyword):
    """DESIGN B — the REAL person on a VARIED AI-generated BACKGROUND: gpt-image makes the SCENE only (no
    people), then the person's REAL photo goes on top (a clean cut-out when background-removal is enabled,
    else a premium framed card) — the FACE is NEVER changed. This is "change the background, keep the face".
    Returns (path, fname, meta), or None if the AI background is unavailable (caller uses Design A)."""
    from ..providers import llm
    if not llm.image_provider_available():
        return None
    bg = None
    try:
        data = await llm.generate_image_bytes(_scene_prompt(headline, question, variant), size="1024x1024")
        if data:
            bg = _cover_fit(Image.open(io.BytesIO(data)).convert("RGB"), W, H)
            try:  # crisp up any soft/hazy background
                bg = bg.filter(ImageFilter.UnsharpMask(radius=2, percent=130, threshold=2))
            except Exception:
                pass
    except Exception:
        bg = None
    if bg is None:
        return None
    skin = SKINS["photo"]
    hero = _cutout(photo)                 # REAL person (bg-removed cut-out, or opaque -> framed card)
    canvas = _ai_scrim(bg)
    d = ImageDraw.Draw(canvas)
    person_left, person_box = _place_person(canvas, d, skin, photo, hero)  # composites the REAL photo
    d.rectangle([0, 0, RAIL_W, H], fill=skin.accent)
    pad = 70
    hl_w = max(340, person_left - pad - 30)
    y, head_box = _draw_headline_highlight(d, pad, 92, headline or "On a Mission!", hl_w, skin, keyword=keyword)
    sub_box = None
    if question:
        qf = body_font(34)
        sy = y + 10
        for ln in _wrap(d, question, qf, hl_w)[: max(1, ((H - 290) - (y + 10)) // 44)]:
            d.text((pad, sy), ln, font=qf, fill=skin.sub)
            sy += 44
        sub_box = (pad, y + 10, pad + hl_w, sy)
    feat_box = _draw_featuring_script(d, pad, H - 250, name, role, skin, max_w=hl_w)
    try:
        paste_wordmark(canvas, pad, H - 60, 240, 44, dark_bg=True)
    except Exception:
        pass
    _ensure_clear("ai_scene", person_box, head_box, sub_box, feat_box)
    file_name = unique_name("tr-team", "png")
    path = storage_subdir("images") / file_name
    canvas.convert("RGB").save(str(path), "PNG")
    return str(path), file_name, {
        "url": public_url("images", file_name), "renderer": "team_ai_scene",
        "style": "ai", "skin": "photo", "size": f"{W}x{H}", "kind": "team", "design": "scene",
    }


def _overlay_ai_scene(scene, name, role, headline, question, keyword, renderer):
    """Shared finish for the full-AI-portrait designs: scrim the AI scene (person baked in on the RIGHT), add
    the branded caption + wordmark on the reserved LEFT, verify no overlaps, save. Returns (path,fname,meta)."""
    skin = SKINS["photo"]
    canvas = _ai_scrim(scene)
    d = ImageDraw.Draw(canvas)
    person_left = int(W * 0.50)
    person_box = (person_left, 0, W, H)
    d.rectangle([0, 0, RAIL_W, H], fill=skin.accent)
    pad = 70
    hl_w = max(340, person_left - pad - 30)
    y, head_box = _draw_headline_highlight(d, pad, 92, headline or "On a Mission!", hl_w, skin, keyword=keyword)
    sub_box = None
    if question:
        qf = body_font(34)
        sy = y + 10
        for ln in _wrap(d, question, qf, hl_w)[: max(1, ((H - 290) - (y + 10)) // 44)]:
            d.text((pad, sy), ln, font=qf, fill=skin.sub)
            sy += 44
        sub_box = (pad, y + 10, pad + hl_w, sy)
    feat_box = _draw_featuring_script(d, pad, H - 250, name, role, skin, max_w=hl_w)
    try:
        paste_wordmark(canvas, pad, H - 60, 240, 44, dark_bg=True)
    except Exception:
        pass
    _ensure_clear(renderer, person_box, head_box, sub_box, feat_box)
    file_name = unique_name("tr-team", "png")
    path = storage_subdir("images") / file_name
    canvas.convert("RGB").save(str(path), "PNG")
    return str(path), file_name, {
        "url": public_url("images", file_name), "renderer": renderer,
        "style": "ai", "skin": "photo", "size": f"{W}x{H}", "kind": "team",
        "design": renderer.replace("team_ai_", ""),
    }


async def _build_ai_portrait_banner(brand, photo, name, role, headline, question, variant, keyword, theme=""):
    """DEFAULT AI look (STRICT FACIAL CONSISTENCY) — gpt-image-1's image-EDIT endpoint with
    input_fidelity='high' re-poses/re-lights/re-stages the SAME person into a polished portrait (blazer + a
    VARIED environment: office / studio / golden-hour / bold-brand / rooftop / …, 8 looks) while preserving
    their facial features from the reference photo. This is the strongest identity lock the image API offers,
    but it is still an AI regeneration — for a pixel-exact real face, add a FACESWAP key (used first when set).
    Returns (path, fname, meta), or None if the provider is unavailable / the edit is refused."""
    from ..providers import llm
    if not llm.image_provider_available():
        return None
    scene = await _ai_portrait_canvas(photo, headline, question, variant, theme)
    if scene is None:
        return None
    return _overlay_ai_scene(scene, name, role, headline, question, keyword, "team_ai_portrait")


async def _build_faceswap_banner(brand, photo, name, role, headline, question, variant, keyword, theme=""):
    """FACE-SWAP upgrade (only when a FACESWAP key is set) — the SAME polished AI portrait, but with the
    person's EXACT real face swapped on (body/clothes/background AI, FACE real). Returns (path,fname,meta),
    or None if the provider/key/swap is unavailable (caller uses the plain AI portrait)."""
    from ..providers import llm
    from . import faceswap
    if not (llm.image_provider_available() and faceswap.faceswap_available()):
        return None
    edited = await _ai_portrait_canvas(photo, headline, question, variant, theme)
    if edited is None:
        return None
    swapped = await faceswap.swap_face(img_to_png_bytes(edited), img_to_png_bytes(photo))  # real face onto it
    if swapped is None:
        return None
    try:
        scene = _cover_fit(Image.open(io.BytesIO(swapped)).convert("RGB"), W, H)
    except Exception:
        return None
    return _overlay_ai_scene(scene, name, role, headline, question, keyword, "team_ai_faceswap")


# --- EDITORIAL composite (senior-graphics-team design): the REAL cut-out is GRADED, GROUNDED and RIM-LIT so
# it reads as PHOTOGRAPHED INTO the scene, not pasted on a card. No frame, no border, no tab. 3 dynamic
# layouts rotate. The FACE is never AI-changed — only the design around the person. ------------------------
def _apply_grain(canvas, variant, strength=4.2):
    """A whisper of shared film grain over subject + plate — the single biggest 'one image, not a paste' cue."""
    import numpy as np
    try:
        g = np.random.default_rng(int(variant) + 7).normal(0, strength, (H, W, 1))
        out = np.clip(np.asarray(canvas.convert("RGB")).astype(np.float32) + g, 0, 255).astype("uint8")
        return Image.fromarray(out, "RGB")
    except Exception:
        return canvas.convert("RGB")


def _editorial_scrim(bg, layout, blur=2.4, strength=0.86, reach=0.55):
    """A navy gradient scrim on the TEXT side (+ bottom) for legibility. A PHOTO plate is gently blurred for
    depth; a flat GRAPHIC plate isn't (blur=0) so the design stays crisp — and a NARROW `reach` keeps the
    scrim behind the text only, so the bold graphic still shows. Layout 3 mirrors to the RIGHT."""
    import numpy as np
    base = bg.convert("RGB")
    if blur:
        try:
            base = base.filter(ImageFilter.GaussianBlur(blur))
        except Exception:
            pass
    w, h = base.size
    xs = np.linspace(0, 1, w)[None, :]
    ys = np.linspace(0, 1, h)[:, None]
    side = np.clip((xs - (1 - reach)) / reach, 0, 1) if layout == 3 else np.clip(1.0 - xs / reach, 0, 1)
    bottom = np.clip((ys - 0.62) / 0.38, 0, 1)
    a = np.clip(side * strength + bottom * (strength * 0.5), 0, 0.93)
    layer = Image.new("RGBA", (w, h), (*NAVY, 255))
    layer.putalpha(Image.fromarray((a * 255).astype("uint8"), "L"))
    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")


def _place_editorial_person(canvas, skin, hero, layout, photo_bg=True):
    """Composite the REAL cut-out cleanly (NO fake white glow): a tight feathered edge, a colour-grade that
    only tone-matches a PHOTO plate (never a flat colour block), a grounded contact shadow + a soft cast
    shadow, and a WHISPER of rim so it reads as designed, not pasted. `layout` 1=hero-right, 2=big-crop
    (bleeds off top), 3=hero-left. Returns the TIGHT person bbox (shadows excluded so text clamping is honest)."""
    import numpy as np
    from PIL import ImageChops, ImageEnhance
    warm = skin.key in ("light", "cream", "photo")
    # STAGE 0 — prominent size + floor-anchored position
    if layout == 2:
        target_h, cap, right_pad = int(H * 0.98), W * 0.60, 16
    elif layout == 3:
        target_h, cap, right_pad = int(H * 0.90), W * 0.56, 24
    else:
        target_h, cap, right_pad = int(H * 0.90), W * 0.58, 24
    scale = target_h / hero.height
    if hero.width * scale > cap:
        scale = cap / hero.width
    hero = hero.resize((max(1, int(hero.width * scale)), max(1, int(hero.height * scale))), Image.LANCZOS)
    a = hero.split()[-1]
    hx = 24 if layout == 3 else (W - hero.width - right_pad)
    hy = -int(hero.height * 0.04) if layout == 2 else (H - hero.height)
    # STAGE 1 — colour-grade. Only tone-MATCH toward a real PHOTO plate (on a flat colour block that would
    # tint the person the block's colour). Always a gentle polish.
    try:
        hrgb = np.asarray(hero.convert("RGB")).astype(np.float32)
        if photo_bg:
            box = (max(0, hx), max(0, hy), min(W, hx + hero.width), min(H, hy + int(hero.height * 0.55)))
            tgt = np.asarray(canvas.convert("RGB").crop(box)).reshape(-1, 3).mean(0)
            af = np.asarray(a).reshape(-1) > 10
            mean = hrgb.reshape(-1, 3)[af].mean(0)
            hrgb = np.clip(hrgb + np.clip((tgt - mean) * 0.15, -12, 12), 0, 255)
        graded = Image.fromarray(np.clip(hrgb, 0, 255).astype("uint8"), "RGB")
        graded = ImageEnhance.Color(graded).enhance(1.04)
        graded = ImageEnhance.Contrast(graded).enhance(1.05)
        hero = graded.convert("RGBA")
        hero.putalpha(a)
    except Exception:
        pass
    # STAGE 2 — feather + a 1px erode (kills the 'sticker' edge)
    a = a.filter(ImageFilter.GaussianBlur(0.6)).filter(ImageFilter.MinFilter(3))
    hero.putalpha(a)
    # STAGE 3 — contact shadow pooling at the feet (skip for the top-bleed crop)
    if layout != 2:
        sil = Image.new("RGBA", hero.size, (0, 0, 0, 0))
        sil.paste((0, 0, 0, 165), (0, 0), a)
        ground = sil.resize((hero.width, max(1, int(hero.height * 0.10))), Image.LANCZOS)
        gl = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        gl.paste(ground, (hx + 18, H - int(hero.height * 0.06)))
        blurred = gl.filter(ImageFilter.GaussianBlur(26))
        canvas.paste(blurred, (0, 0), blurred)
    # STAGE 4 — soft cast shadow (navy-tinted, offset to the light side) BEFORE the person
    sh = Image.new("RGBA", hero.size, (0, 0, 0, 0))
    sh.paste((6, 12, 26, 105), (0, 0), a)
    sh = sh.filter(ImageFilter.GaussianBlur(24))
    off = (max(RAIL_W, hx - 20), hy + 16) if layout == 3 else (hx + 20, hy + 16)
    canvas.paste(sh, off, sh)
    # STAGE 5 — the person
    canvas.paste(hero, (hx, hy), hero)
    # STAGE 6 — a WHISPER of directional rim (subtle; never a glowing sticker outline)
    try:
        rim_mask = ImageChops.subtract(a, a.filter(ImageFilter.MinFilter(7)))
        rm = ImageChops.multiply(a, rim_mask).point(lambda v: min(v, 42)).filter(ImageFilter.GaussianBlur(1.4))
        gy = np.linspace(1, 0, hero.height)[:, None]
        gx = (np.linspace(0, 1, hero.width) if layout == 3 else np.linspace(1, 0, hero.width))[None, :]
        rm = Image.fromarray((np.asarray(rm).astype(np.float32) * np.clip(gy * gx, 0, 1)).astype("uint8"), "L")
        rim = Image.new("RGBA", hero.size, (255, 250, 244, 0))
        rim.putalpha(rm)
        canvas.paste(rim, (hx, hy), rim)
    except Exception:
        pass
    return (hx, max(0, hy), hx + hero.width, H)


def _draw_editorial_text(canvas, d, skin, name, role, headline, question, keyword, layout, person_box,
                         kicker="TEAM // SPOTLIGHT"):
    """Draw the editorial caption for a layout and return the text bounding boxes (for `_ensure_clear`).
    Text lives entirely in the reserved column opposite the subject. `kicker` (may be empty) rotates."""
    pad = 70
    boxes = []
    if layout == 3:                                   # subject LEFT -> text RIGHT
        tx, tw = 664, 376
        try:
            paste_wordmark(canvas, tx, 46, 300, 42, dark_bg=skin.wm_dark); boxes.append((tx, 46, tx + 300, 90))
        except Exception:
            pass
        if kicker:
            d.text((tx, 120), kicker, font=heading_font(24), fill=skin.accent); boxes.append((tx, 120, tx + 300, 150))
        y, hb = _draw_headline_highlight(d, tx, 168, headline or "On a Mission!", tw, skin, keyword=keyword, size=96, max_lines=4)
        boxes.append(hb)
        if question:
            qf = body_font(30); sy = y + 14
            for ln in _wrap(d, question, qf, tw)[: max(1, (700 - (y + 14)) // 42)]:
                d.text((tx, sy), ln, font=qf, fill=skin.sub); sy += 42
            boxes.append((tx, y + 14, tx + tw, sy))
        boxes.append(_draw_featuring_script(d, tx, H - 250, name, role, skin, max_w=tw))
    elif layout == 2:                                 # subject RIGHT (top-bleed) -> text LEFT, featuring high
        hl_w = max(320, person_box[0] - pad - 50)
        boxes.append(_draw_featuring_script(d, pad, 322, name, role, skin, max_w=hl_w))
        y, hb = _draw_headline_highlight(d, pad, 492, headline or "On a Mission!", hl_w, skin, keyword=keyword, size=104, max_lines=3)
        boxes.append(hb)
        if question:
            qf = body_font(30); sy = y + 12
            for ln in _wrap(d, question, qf, hl_w)[: max(1, (760 - (y + 12)) // 42)]:
                d.text((pad, sy), ln, font=qf, fill=skin.sub); sy += 42
            boxes.append((pad, y + 12, pad + hl_w, sy))
        try:
            paste_wordmark(canvas, pad, H - 70, 230, 42, dark_bg=skin.wm_dark); boxes.append((pad, H - 72, pad + 230, H - 24))
        except Exception:
            pass
    else:                                             # LAYOUT 1 masthead hero-right (default)
        hl_w = max(320, person_box[0] - pad - 50)
        try:
            paste_wordmark(canvas, pad, 46, 250, 42, dark_bg=skin.wm_dark); boxes.append((pad, 46, pad + 250, 88))
        except Exception:
            pass
        if kicker:
            d.text((pad, 120), kicker, font=heading_font(24), fill=skin.accent); boxes.append((pad, 120, pad + 300, 150))
        y, hb = _draw_headline_highlight(d, pad, 168, headline or "On a Mission!", hl_w, skin, keyword=keyword, size=112, max_lines=3)
        boxes.append(hb)
        if question:
            qf = body_font(32); sy = y + 14
            for ln in _wrap(d, question, qf, hl_w)[: max(1, (700 - (y + 14)) // 42)]:
                d.text((pad, sy), ln, font=qf, fill=skin.sub); sy += 42
            boxes.append((pad, y + 14, pad + hl_w, sy))
        boxes.append(_draw_featuring_script(d, pad, 830, name, role, skin, max_w=hl_w))
    return boxes


def _finish_editorial(canvas, renderer):
    file_name = unique_name("tr-team", "png")
    path = storage_subdir("images") / file_name
    canvas.convert("RGB").save(str(path), "PNG")
    return str(path), file_name, {
        "url": public_url("images", file_name), "renderer": renderer,
        "style": "ai", "skin": "photo", "size": f"{W}x{H}", "kind": "team", "design": "editorial",
    }


async def _build_editorial_banner(brand, photo, name, role, headline, question, variant, keyword, theme=""):
    """PREMIUM EDITORIAL composite — the REAL cut-out person integrated into a gpt-image editorial scene
    (graded/grounded/rim-lit, NO frame), with a rotating dynamic layout. The FACE is never changed. `theme`
    (a campaign brief) steers the photographic backdrop to match the campaign. Returns (path, fname, meta),
    or None on failure."""
    from ..providers import llm
    skin = SKINS["photo"]
    template = int(variant) % 6          # 6 distinct designs (0-4 = bold graphic, 5 = photographic scene)
    layout = (template % 3) + 1          # person position rotates too
    text_left = layout != 3
    kicker = _EDITORIAL_KICKERS[template % len(_EDITORIAL_KICKERS)]
    # background: mostly a BOLD graphic poster (instant + looks designed, not a fake composite); occasionally
    # a gpt-image photographic scene for depth.
    # With a campaign THEME set, always use a photographic themed backdrop (so the scene matches the campaign)
    # rather than a flat brand-graphic plate.
    photo_bg = (template == 5 or bool((theme or "").strip())) and llm.image_provider_available()
    bg = None
    if photo_bg:
        try:
            data = await llm.generate_image_bytes(_scene_prompt(headline, question, variant, theme), size="1024x1024")
            if data:
                bg = _cover_fit(Image.open(io.BytesIO(data)).convert("RGB"), W, H)
        except Exception:
            bg = None
    if bg is None:                       # graphic poster (also the offline / provider-down path)
        photo_bg = False
        bg = _graphic_editorial_bg(template, text_left)
    canvas = _editorial_scrim(bg, layout, blur=2.4 if photo_bg else 0,
                              strength=0.86 if photo_bg else 0.82, reach=0.55 if photo_bg else 0.40)
    hero = _cutout(photo)
    cut_ok = (hero.mode == "RGBA" and hero.getextrema()[3][0] < 245
              and hero.width >= photo.width * 0.42 and hero.height >= photo.height * 0.45)
    if cut_ok:
        person_box = _place_editorial_person(canvas, skin, hero, layout, photo_bg=photo_bg)
    else:  # FRAMELESS fallback (no clean cut-out): full-bleed photo, heavy scrim, NO card
        full = _cover_fit(photo, W, H)
        canvas = _editorial_scrim(full, 1, blur=2.4, strength=0.9)
        person_box = (int(W * 0.5), 0, W, H)
        layout, kicker = 1, "TEAM // SPOTLIGHT"
    canvas = _apply_grain(canvas, variant, 3.0 if not photo_bg else 4.0)
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, RAIL_W, H], fill=skin.accent)
    boxes = _draw_editorial_text(canvas, d, skin, name, role, headline, question, keyword, layout, person_box, kicker)
    _ensure_clear("editorial_L%d" % layout, person_box, *boxes)
    return _finish_editorial(canvas, "team_editorial")


def _lin_grad(c1, c2, vertical=True):
    import numpy as np
    a = np.array(c1, float)
    b = np.array(c2, float)
    t = (np.linspace(0, 1, H)[:, None, None] if vertical else np.linspace(0, 1, W)[None, :, None])
    arr = np.broadcast_to((a * (1 - t) + b * t).astype("uint8"), (H, W, 3)).copy()
    return Image.fromarray(arr, "RGB")


# Distinct BOLD flat-graphic plates — a cut-out person on one of these reads as an INTENTIONAL editorial
# poster (designed, not a fake photo composite), and they're instant (no gpt-image call). The bold shapes
# sit on the PERSON side (which the cut-out covers); the caption side is darkened by the scrim. Rotating
# these + the layout + the kicker makes every post look different.
def _graphic_editorial_bg(template, text_left):
    t = int(template) % 6
    pcx = int(W * 0.72) if text_left else int(W * 0.28)     # centre of the person side
    if t == 0:                                              # deep navy gradient (clean, classic)
        return _lin_grad((0x0B, 0x35, 0x59), (0x15, 0x4A, 0x77))
    if t == 1:                                              # BOLD coral base + navy disc behind the person
        c = Image.new("RGB", (W, H), (0xF6, 0x40, 0x4C))
        ImageDraw.Draw(c, "RGBA").ellipse([pcx - 430, -150, pcx + 430, 910], fill=(0x0B, 0x35, 0x59, 255))
        return c
    if t == 2:                                              # warm cream -> gold, coral ring behind the person
        c = _lin_grad((0xEF, 0xEC, 0xE1), (0xF3, 0xD9, 0xAA))
        ImageDraw.Draw(c, "RGBA").ellipse([pcx - 350, 70, pcx + 350, 790], outline=(0xF6, 0x40, 0x4C, 170), width=12)
        return c
    if t == 3:                                              # navy + big coral disc behind the person
        c = _lin_grad((0x0A, 0x2C, 0x4A), (0x0B, 0x35, 0x59))
        ImageDraw.Draw(c, "RGBA").ellipse([pcx - 410, -110, pcx + 410, 870], fill=(0xF6, 0x40, 0x4C, 235))
        return c
    if t == 4:                                              # cream base + a big navy ARC sweeping in
        c = Image.new("RGB", (W, H), (0xEB, 0xE9, 0xDF))
        d = ImageDraw.Draw(c, "RGBA")
        if text_left:
            d.pieslice([pcx - 560, -340, pcx + 560, 800], 90, 270, fill=(0x0B, 0x35, 0x59, 255))
        else:
            d.pieslice([pcx - 560, -340, pcx + 560, 800], 270, 450, fill=(0x0B, 0x35, 0x59, 255))
        return c
    # t == 5: bold DIAGONAL split — coral field, navy wedge on the caption side
    c = Image.new("RGB", (W, H), (0xF6, 0x40, 0x4C))
    d = ImageDraw.Draw(c, "RGBA")
    if text_left:
        d.polygon([(0, 0), (int(W * 0.66), 0), (int(W * 0.40), H), (0, H)], fill=(0x0B, 0x35, 0x59, 255))
    else:
        d.polygon([(W, 0), (int(W * 0.34), 0), (int(W * 0.60), H), (W, H)], fill=(0x0B, 0x35, 0x59, 255))
    return c


# Rotating kicker labels (some templates drop it) so the eyebrow line isn't always identical.
_EDITORIAL_KICKERS = ["TEAM // SPOTLIGHT", "MEET THE TEAM", "TALENTRUPT PEOPLE", "IN THE SPOTLIGHT",
                      "OUR PEOPLE", ""]


async def build_ai_scene(brand, photo_bytes, name="", role="", headline="", question="", variant=0,
                         keyword="", theme=""):
    """Featured-employee banner that keeps the person's EXACT real face. `theme` (a campaign brief) drives the
    scene/background so the person is placed in the campaign's world; pass name="" to omit the on-image name
    label (e.g. campaign images). Priority — strongest identity first:
      • FACESWAP key set -> a full AI scene (person genuinely IN the themed environment) with the person's
        EXACT real face swapped on (`_build_faceswap_banner`). Best of both: immersive scene + real face.
      • Otherwise (DEFAULT) -> a PREMIUM EDITORIAL composite of the REAL cut-out person on a themed background
        (`_build_editorial_banner`). The face + clothing are literally their photo — never redrawn — so the
        identity is exact and there's no hallucinated text on their shirt.
    NOTE: we deliberately do NOT use gpt-image's image-EDIT path by default — even at input_fidelity=high it
    REGENERATES the face (it drifts) and hallucinates garbage text on clothing. It's only used *inside*
    faceswap, where the real face is then swapped back on. Any failure -> a deterministic template."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    try:
        photo = _enhance_photo(ImageOps.exif_transpose(Image.open(io.BytesIO(photo_bytes)).convert("RGB")))
    except Exception:
        return build_team_image(brand, photo_bytes, name, role, headline, question, variant,
                                style="spotlight_series", skin=random.choice(DETERMINISTIC_SKINS))
    try:
        from . import faceswap
        result = None
        if faceswap.faceswap_available():   # immersive AI scene + EXACT real face (opt-in key, strongest)
            result = await _build_faceswap_banner(brand, photo, name, role, headline, question, variant, keyword, theme)
        if result is None:                  # DEFAULT: real cut-out composite — face + clothes are exactly theirs
            result = await _build_editorial_banner(brand, photo, name, role, headline, question, variant, keyword, theme)
        if result is not None:
            return result
    except Exception:
        pass
    return build_team_image(brand, photo_bytes, name, role, headline, question, variant,
                            style="spotlight_series", skin=random.choice(DETERMINISTIC_SKINS))


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
