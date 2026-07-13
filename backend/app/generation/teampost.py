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
               "spotlight_series", "welcome", "anniversary", "grid", "quote"]
SERIES_STYLES = ["spotlight_series", "welcome", "anniversary", "quote"]  # skin-aware renderers (take a Skin)


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
        # Background reference = the TOP-LEFT + TOP-RIGHT CORNERS (the wall beside the head), NOT the full top
        # strip: a subject with tall hair / head reaching the top makes the full strip non-uniform, which used
        # to wrongly bail (→ the raw white-wall photo shipped). The corners are almost always the plain wall.
        # It must be LIGHT and fairly UNIFORM (a plain studio wall), else we bail.
        cw = max(12, w // 7)
        corners = np.concatenate([arr[:s, :cw].reshape(-1, 3), arr[:s, -cw:].reshape(-1, 3)])
        bg = np.median(corners, axis=0)
        if float(bg.mean()) < 116 or float(corners.std(0).mean()) > 30:
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
        # NEAR-EDGE ONLY: the cast SHADOW and leftover LIGHT WALL live right at the person's OUTLINE; the deep
        # interior (the CHEST) is the shirt. Restrict the neutral/wall strip to pixels NEAR the border-connected
        # background so a bright printed SHIRT LOGO / TEXT (also neutral + bright) deep on the chest is NEVER
        # punched into holes — those holes used to show the scene through as green/grey DOTS on the shirt text.
        near_bg = np.asarray(
            Image.fromarray((is_bg.astype(np.uint8) * 255), "L").filter(ImageFilter.MaxFilter(19))) > 127
        # Remove the person's cast SHADOW and any leftover LIGHT WALL the flood-fill couldn't reach (the exact
        # "white shadow" patch behind a shoulder). Both are NEUTRAL (low-saturation) greys/whites; skin is WARM
        # (bigger channel spread) and hair/dark clothes are dark, so gating on low saturation + not-too-dark
        # strips the wall & shadow without eating the person. (A LIGHT-coloured shirt is the one exception —
        # use the remove.bg key for those.)
        neutral = near_bg & (~is_bg) & ((mx - mn) < 22) & (bright > 74)
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
        # Any BRIGHT NEUTRAL patch still opaque is LEFTOVER LIGHT WALL (e.g. a wall region enclosed behind a
        # shoulder that the hole-fill wrongly re-filled — the "cream shadow" behind the person). It is NOT skin
        # (warm, bigger channel spread), hair or dark clothes, so strip it. The despeckle below closes the tiny
        # true holes (eye-whites) this also clears.
        # Only near the person's OUTLINE (near_bg) — so bright SHIRT TEXT deep on the chest is protected.
        wall2 = near_bg & (alpha > 127) & ((mx - mn) < 26) & (bright > 150)
        if 0.0 < float(wall2.mean()) < 0.22:  # safety: never nuke a genuinely pale subject
            alpha = np.where(wall2, 0, alpha).astype(np.uint8)
        # SOLIDIFY the interior: re-close every hole the neutral / wall2 gates punched INSIDE the body (a bright
        # watch, a specular highlight, a light tattoo). Otherwise a bright background — e.g. a green football
        # pitch — shows through them as coloured SPECKLES on the person (the "green dots on the hand"). Flood the
        # true background inward from the border corners; any 0-pixel NOT reached is enclosed by the subject ->
        # force it opaque. Fully see-through gaps that open to the frame edge (an arm-on-hip triangle) stay cut,
        # which is correct.
        try:
            fill = Image.fromarray(((alpha > 127).astype(np.uint8) * 255), "L").convert("RGB")
            farr = np.asarray(fill)
            for cx, cy in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)):
                if float(farr[cy, cx].mean()) < 128:            # a genuine background corner
                    ImageDraw.floodfill(fill, (cx, cy), (3, 5, 7), thresh=20)
            outside = np.all(np.asarray(fill) == np.array((3, 5, 7)), axis=-1)
            if 0.05 < float(outside.mean()) < 0.95:             # sane bg/fg split -> trust it
                alpha = np.where(outside, 0, 255).astype(np.uint8)
        except Exception:
            pass
        # Despeckle + CLOSE pinholes (a MaxFilter dilate then a MinFilter erode = morphological close) so tiny
        # holes the keyer punched INSIDE the face/skin — which otherwise show the busy background through as
        # coloured DOTS on the person — are filled, then a light median + feather. The close preserves the
        # silhouette size while killing pinholes; the medians clean the fringe.
        a = (Image.fromarray(alpha, "L").filter(ImageFilter.MedianFilter(7))
             .filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.MinFilter(3))
             .filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(1.2)))
        # QUALITY GATE — only ship a cut-out that's actually CLEAN. A clean silhouette is a solid blob with a
        # smooth edge and almost no bright-neutral WALL left inside it (measured clean cut ≈ 0.9% roughness,
        # 0.1% leftover wall). A messy free-key (jagged edge / leftover 'cream shadow') scores far higher — bail
        # so the caller uses the CLEAN framed/split design instead of shipping a rough cut-out.
        a_np = np.asarray(a)
        op = a_np > 127
        area = int(op.sum())
        if area < 1:
            return None
        peri = int(np.abs(np.diff(op.astype(np.int16), axis=0)).sum()
                   + np.abs(np.diff(op.astype(np.int16), axis=1)).sum())
        roughness = peri / area * 100.0
        # Measure leftover WALL only NEAR the edge (near_bg). Deep-interior bright-neutral pixels are the
        # printed SHIRT TEXT / logo (which we now deliberately KEEP) — counting those as "wall" wrongly failed
        # the gate and dumped the person onto a plain split-poster background instead of the themed scene.
        wall_left = float((op & near_bg & ((mx - mn) < 26) & (bright > 150)).mean())
        if roughness > 2.4 or wall_left > 0.02:
            return None
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
        img = ImageEnhance.Color(img).enhance(1.03)          # a touch more life — kept low so it doesn't
        img = ImageEnhance.Contrast(img).enhance(1.05)       # amplify chroma noise into coloured speckles
        img = ImageEnhance.Sharpness(img).enhance(1.12)
        # a MODERATE unsharp mask: enough to keep printed text/logos legible, but gentle enough that it does
        # NOT halo/garble the already-soft text on a real (out-of-focus, wrinkled) t-shirt. threshold=5 keeps
        # smooth skin clean so it does NOT sharpen sensor/JPEG noise into coloured dots on the face.
        img = img.filter(ImageFilter.UnsharpMask(radius=1.1, percent=55, threshold=5))
    except Exception:
        pass
    return img


def _wrap(d: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    def _hard(word: str) -> list[str]:
        # A single word wider than the box is character-split so no returned line ever overflows (a long
        # concatenated name / URL used to run off the edge and over the photo).
        if d.textlength(word, font=font) <= max_w:
            return [word]
        out, cur = [], ""
        for ch in word:
            if not cur or d.textlength(cur + ch, font=font) <= max_w:
                cur += ch
            else:
                out.append(cur)
                cur = ch
        if cur:
            out.append(cur)
        return out

    lines, cur = [], ""
    for w in str(text or "").split():
        for piece in _hard(w):
            t = (cur + " " + piece).strip()
            if not cur or d.textlength(t, font=font) <= max_w:
                cur = t
            else:
                lines.append(cur)
                cur = piece
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


def _layout_quote(photo, name, role, headline, question, variant, skin):
    """Testimonial card: the person's FULL saying rendered VERBATIM and AUTO-FIT (wraps + shrinks to fit
    the whole quote — never truncated), with a big quotation mark, a rounded REAL-photo portrait and a
    '— Name, Role' attribution. Handles a short punchy line or a long multi-sentence quote alike."""
    sk = skin
    canvas = Image.new("RGB", (W, H), sk.bg)
    d = ImageDraw.Draw(canvas)
    _pro_scene(canvas, d, sk, variant)  # subtle on-brand accents
    pad = 100

    quote = (headline or question or "").strip().strip('"“”‘’ ').strip() or "In their own words."

    # Big opening quotation mark in the accent colour.
    d.text((pad - 14, 18), "“", font=heading_font(210), fill=sk.accent)

    # --- Attribution (bottom): rounded real-photo portrait + name + role ---
    port = 132
    ax, ay = pad, H - 108 - port
    try:
        p = _enhance_photo(_cover_fit(photo, port, port))
        mask = Image.new("L", (port, port), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, port, port], fill=255)
        canvas.paste(p, (ax, ay), mask)
        d.ellipse([ax - 3, ay - 3, ax + port + 3, ay + port + 3], outline=sk.accent, width=4)
    except Exception:
        pass
    nx = ax + port + 26
    d.text((nx, ay + 34), f"— {name}", font=heading_font(40), fill=sk.name)
    if role:
        d.text((nx, ay + 86), role, font=body_font(26), fill=sk.sub)

    # --- Quote text: auto-fit into the area between the quote mark and the attribution (never truncated) ---
    long = len(quote) > 120
    font_fn = body_font if long else heading_font
    text_top, text_bottom = 236, ay - 36
    max_w, max_h = W - 2 * pad, (ay - 36) - 236
    size = 52 if long else 78
    f = font_fn(size)
    lines = _wrap(d, quote, f, max_w)
    lh = int(size * 1.3)
    while (len(lines) * lh > max_h) and size > 20:
        size -= 3
        f = font_fn(size)
        lines = _wrap(d, quote, f, max_w)
        lh = int(size * 1.3)
    y = text_top + max(0, (max_h - len(lines) * lh) // 2)  # vertically centre the block
    for ln in lines:
        d.text((pad, y), ln, font=f, fill=sk.text)
        y += lh

    paste_wordmark(canvas, W - 250, H - 58, 200, 40, dark_bg=sk.wm_dark)
    return canvas


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
    "quote": _layout_quote,
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
    photo.thumbnail((1800, 1800), Image.LANCZOS)  # cap working size (full-res uploads OOM the 2GB droplet)
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
    # NOTE: deliberately do NOT feed the literal headline/message into the prompt — gpt-image tends to RENDER
    # it as ghost text in the background despite "NO text". We only steer the SETTING.
    if theme:
        # THEME -> a REALISTIC PHOTOGRAPHIC location (a real football stadium/pitch), so the real cut-out
        # person composited on top looks genuinely photographed there — NOT an abstract corporate graphic.
        return (
            f'A realistic, photorealistic, cinematic BACKGROUND PHOTOGRAPH of the real location for this theme: '
            f'"{theme[:160]}" — shown in its NATURAL, TRUE colours (a football/soccer theme -> a real GREEN '
            "grass pitch inside a floodlit STADIUM at dusk/night, softly-blurred crowd in the stands, bright "
            "stadium floodlights and gentle lens flare, shallow depth of field; cricket -> a green field with a "
            "tan pitch strip; a festival -> its real lights and decor). Shot like a real professional "
            "photograph — rich saturated colour, natural lighting, real atmosphere and depth. ABSOLUTELY NO "
            "people, NO person, NO faces, NO text, NO words, NO letters, NO numbers, NO logos, NO signage. Keep "
            "the RIGHT side a touch clearer for a standing person and the LEFT calmer/darker for a caption. "
            "Square 1:1 composition."
        )
    scene = _SCENE_TYPES[variant % len(_SCENE_TYPES)]
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
    "PRESERVE THEIR CLOTHING EXACTLY as in the reference photo — keep the same garment, colour and especially "
    "any TEXT, wording, letters or logo printed on it EXACTLY as written; do NOT change, re-letter, restyle, "
    "remove or garble the shirt text unless explicitly instructed. "
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
    # NOTE: deliberately do NOT feed the literal headline/message into the edit prompt — gpt-image renders it
    # as GHOST TEXT in the scene despite "NO text". The branded caption is overlaid separately afterwards.
    theme = (theme or "").strip()
    if theme:
        setting = (
            f'FULLY IMMERSED INSIDE the real environment of this CAMPAIGN THEME: "{theme[:200]}", as an EPIC, '
            "CINEMATIC premium SPORTS-POSTER photograph — NOT a plain studio backdrop and NOT a flat white "
            "wall (e.g. a football campaign -> standing powerfully mid-field on the floodlit GREEN pitch inside "
            "a packed roaring STADIUM at night, a huge blurred crowd, bright stadium floodlights and lens "
            "flares behind them, glowing embers/sparks in the air, dramatic high-contrast rim lighting; a "
            "Diwali campaign -> among glowing diyas, fireworks and rich festive decor). Big depth, atmosphere, "
            "energy and drama; theatrical back/rim lighting that separates them from the background. A powerful, "
            "confident HERO stance (e.g. arms crossed, chin up) that commands the frame"
        )
        wardrobe = (
            "WARDROBE: KEEP the person's EXACT clothing from the reference photo — the same garment, colour and "
            "any text, wording or logo printed on it, reproduced EXACTLY as written. Do NOT swap it for a jersey "
            "or a different outfit, and do NOT change, re-letter, restyle or garble the shirt text. "
        )
        kind = "immersive themed campaign"
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
        f"Re-pose, re-light and re-stage them for the best look: place them {setting}. "
        + wardrobe +
        "SEAMLESS INTEGRATION: they must look GENUINELY PHOTOGRAPHED at that location, fully part of the scene — "
        "match the environment's perspective and camera angle, cast realistic contact + directional SHADOWS, "
        "add subtle reflections/bounce light and matching depth of field, and colour-grade the subject to the "
        "scene's light and palette. Blend foreground and background PERFECTLY — absolutely NO cut-out edges, NO "
        "pasted or sticker look, NO halo. Preserve their natural skin tones, facial features, clothing details "
        "and body proportions. Photorealistic, highly detailed, cinematic and visually premium. "
        "COMPOSITION: a clean 1:1 square; compose the person on the RIGHT with their head in the upper-right; "
        "keep the LEFT ~40% as calm, softly-lit, uncluttered negative space for a caption. Crisp focus, "
        "flattering light. Absolutely NO text, NO words, NO letters, NO logos, NO watermarks anywhere."
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


def _place_editorial_person(canvas, skin, hero, layout, photo_bg=True, fit=""):
    """Composite the REAL cut-out cleanly (NO fake white glow): a tight feathered edge, a colour-grade that
    only tone-matches a PHOTO plate (never a flat colour block), a grounded contact shadow + a soft cast
    shadow, and a WHISPER of rim so it reads as designed, not pasted. `layout` 1=hero-right, 2=big-crop
    (bleeds off top), 3=hero-left. Returns the TIGHT person bbox (shadows excluded so text clamping is honest)."""
    import numpy as np
    from PIL import ImageChops, ImageEnhance
    warm = skin.key in ("light", "cream", "photo")
    # HALF-BODY vs FULL-BODY: sample the bottom 10% of the cut-out. A head-to-torso crop fills that band with
    # body — its bottom edge IS the shirt/chest, so any TEXT printed there lands at the frame edge; a full body
    # tapers to narrow feet or empty. The ratio is scale-invariant, so measure it on the input alpha.
    try:
        _b = np.asarray(hero.split()[-1])[int(hero.height * 0.90):, :]
        half_body = _b.size > 0 and float((_b > 40).mean()) > 0.42
    except Exception:
        half_body = False
    # FIT nudge (from a conversational edit, e.g. "make her smaller / fit properly / bigger"): scale the
    # subject down or up so the user can dial the composition without re-shooting.
    fit = (fit or "").lower()
    fit_mul = (0.86 if fit in ("smaller", "fit", "shrink", "reduce", "smaller person")
               else 1.12 if fit in ("bigger", "larger", "zoom", "grow") else 1.0)
    # STAGE 0 — size + position. A half-body crop is a touch smaller and LIFTED (never top-bleed, on ANY
    # template) so the shirt — and its printed text — clears the frame edge and the dark bottom scrim; a full
    # body stays prominent + floor-anchored (layout 2 = a deliberate dramatic top-bleed crop).
    if half_body:
        # a torso crop: contained (narrower cap) + inset from the edge (bigger pad) so it never jams into /
        # bleeds off the SIDE, and GROUNDED at the bottom (below) — not floating. Sized a touch larger so a
        # printed SHIRT LOGO / text reads clearly.
        target_h, cap, right_pad = int(H * 0.84 * fit_mul), (W * 0.54 if layout == 3 else W * 0.56), 54
    elif layout == 2:
        target_h, cap, right_pad = int(H * 0.98 * fit_mul), W * 0.60, 16
    elif layout == 3:
        target_h, cap, right_pad = int(H * 0.90 * fit_mul), W * 0.56, 24
    else:
        target_h, cap, right_pad = int(H * 0.90 * fit_mul), W * 0.58, 24
    scale = target_h / hero.height
    if hero.width * scale > cap:
        scale = cap / hero.width
    hero = hero.resize((max(1, int(hero.width * scale)), max(1, int(hero.height * scale))), Image.LANCZOS)
    a = hero.split()[-1]
    hx = (46 if half_body else 24) if layout == 3 else (W - hero.width - right_pad)
    if half_body:
        # grounded: let the torso bottom bleed a touch OFF the frame — no floating gap, and no hard cut line.
        # The subject is sized so the chest (and its printed text) still sits comfortably mid-frame.
        hy = H - hero.height + int(H * 0.03)
    elif layout == 2:
        hy = -int(hero.height * 0.04)
    else:
        hy = H - hero.height                     # floor-anchor a full body
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
    # STAGE 1b — GREEN DESPILL: the subject has no genuine green (warm skin, navy shirt, dark hair), so any
    # green-DOMINANT pixel is spill / fringe from a green background (a pitch) bleeding onto a soft edge. Pull
    # the green channel down to just above max(R,B) so it never tints or green-fringes the person. Only applied
    # over a photo background; strongly-green-only so it can't grey a legitimately navy/skin subject.
    if photo_bg:
        try:
            hr = np.asarray(hero.convert("RGB")).astype(np.float32)
            rb = np.maximum(hr[..., 0], hr[..., 2])
            over = hr[..., 1] > rb + 18
            hr[..., 1] = np.where(over, rb + 10, hr[..., 1])
            despilled = Image.fromarray(np.clip(hr, 0, 255).astype("uint8"), "RGB").convert("RGBA")
            despilled.putalpha(a)
            hero = despilled
        except Exception:
            pass
    # STAGE 2 — feather + a 1px erode (kills the 'sticker' edge)
    a = a.filter(ImageFilter.GaussianBlur(0.6)).filter(ImageFilter.MinFilter(3))
    hero.putalpha(a)
    # STAGE 3 — a SUBTLE contact shadow, ONLY a soft pool at the feet of a floor-anchored FULL body (grounds
    # them so they don't float). We deliberately DROP the big offset CAST shadow: an offset silhouette read as
    # an ugly grey BOX behind the person (worse when the free key-out left a strip of studio wall). No shadow
    # is cleaner than a bad one — the user asked for a clean, shadow-free subject.
    if layout != 2 and not half_body:
        sil = Image.new("RGBA", hero.size, (0, 0, 0, 0))
        sil.paste((0, 0, 0, 90), (0, 0), a)
        ground = sil.resize((hero.width, max(1, int(hero.height * 0.06))), Image.LANCZOS)
        gl = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        gl.paste(ground, (hx + 18, H - int(hero.height * 0.04)))
        blurred = gl.filter(ImageFilter.GaussianBlur(30))
        canvas.paste(blurred, (0, 0), blurred)
    # STAGE 5 — the person (no offset cast shadow: it made an ugly grey box behind the subject)
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
        if kicker:                                    # intent eyebrow (ANNOUNCEMENT / SAVE THE DATE …)
            d.text((pad, 446), kicker, font=heading_font(24), fill=skin.accent)
            boxes.append((pad, 446, pad + hl_w, 476))
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


def _panel_theme_prompt(theme: str) -> str:
    """A REALISTIC themed photo for the poster panel (no people, no text) so the split poster looks like the
    real thing — e.g. football -> a lush GREEN pitch, white lines, a real ball, a goal net, floodlit stadium."""
    return (
        f'A realistic, vivid, cinematic VERTICAL poster-panel photo BACKGROUND for this theme: "{theme[:170]}". '
        "Show the theme's real setting and objects in their NATURAL, TRUE colours: a football/soccer theme -> a "
        "lush GREEN grass pitch with crisp white line markings, a real black-and-white football on the grass, a "
        "goal with a net, a floodlit stadium; cricket -> a green field with a tan pitch strip; a festival -> its "
        "real lights and decor. Photorealistic, rich saturated colour, natural lighting, shallow depth of field. "
        "Keep ONLY the TOP third quieter/darker (open sky, shadow or dusk) so a white headline stays readable "
        "over it; the rest shows the scene in full colour. ABSOLUTELY NO people, NO faces, NO text, NO words, NO "
        "letters, NO numbers, NO logos, NO signage. Tall vertical composition."
    )


# Dark panel colour schemes (all dark so the white caption + red keyword box stay legible). Rotating these +
# the panel SIDE + the seam + the accent makes every no-cut-out poster look genuinely different.
_SPLIT_SCHEMES = [(0x0B, 0x35, 0x59), (0x0A, 0x24, 0x3E), (0x12, 0x2E, 0x38),
                  (0x10, 0x2A, 0x4E), (0x14, 0x22, 0x3A), (0x0C, 0x33, 0x3B)]


async def _bold_split_poster(photo, variant, theme=""):
    """No clean cut-out -> a BOLD magazine SPLIT poster instead of a plain photo: a designed panel (holding the
    oversized caption) beside a tight PORTRAIT CROP of the real photo. Keeps the person's EXACT face (just a
    crop — nothing redrawn), and every graphic sits in a SAFE zone so it never covers the subject or text.
    DESIGN VARIES with `variant`: the panel SIDE flips (mirror), the colour scheme, seam style and accent all
    rotate — so consecutive generations look different. When a `theme` is set the panel background is a THEMED
    graphic (football/cricket/festival, no people/text). Returns (canvas, person_box, layout)."""
    from ..providers import llm
    import numpy as np
    v = int(variant)
    scheme = _SPLIT_SCHEMES[v % len(_SPLIT_SCHEMES)]
    panel_left = (v % 2 == 0)                       # alternate the side the panel/text sits on (big visual flip)
    panel_w = int(W * (0.42 + 0.02 * (v % 3)))      # slight width variety
    photo_w = W - panel_w
    px = 0 if panel_left else W - panel_w           # panel x-origin
    fx = panel_w if panel_left else 0               # photo x-origin
    seam_x = panel_w if panel_left else photo_w     # where panel meets photo
    canvas = Image.new("RGB", (W, H), scheme)
    # PHOTO SIDE: a clean CUT-OUT of the person (transparent -> NO white studio wall) floated on a dark brand
    # gradient when the cut is clean; otherwise the raw photo crop (still fine, just keeps their own bg).
    hero = _cutout(photo)
    clean_cut = hero.mode == "RGBA" and int(np.asarray(hero.split()[-1]).min()) < 245
    if clean_cut:
        g = np.linspace(1.14, 0.72, H)[:, None, None]                     # dark brand gradient backdrop
        pbg = Image.fromarray(np.clip(np.broadcast_to(np.array(scheme, float), (H, photo_w, 3)) * g, 0, 255)
                              .astype("uint8"), "RGB").convert("RGBA")
        sc = (H * 0.99) / hero.height                                     # fill the height, anchored bottom
        hw, hh = max(1, int(hero.width * sc)), max(1, int(hero.height * sc))
        hero2 = hero.resize((hw, hh), Image.LANCZOS)
        ox, oy = (photo_w - hw) // 2, H - hh
        # soft grounding shadow so the cut-out doesn't look pasted
        sh = Image.new("RGBA", (photo_w, H), (0, 0, 0, 0))
        sha = hero2.split()[-1].point(lambda v: int(v * 0.5))
        sh.paste((0, 0, 0, 255), (ox + 10, oy + 16), sha)
        pbg = Image.alpha_composite(pbg, sh.filter(ImageFilter.GaussianBlur(14)))
        pbg.alpha_composite(hero2, (ox, oy))
        canvas.paste(pbg.convert("RGB"), (fx, 0))
    else:
        pic = _cover_fit(photo, photo_w, H)
        arr = np.clip((np.asarray(pic.convert("RGB")).astype(np.float32) - 128) * 1.10 + 128, 0, 255)
        canvas.paste(Image.fromarray(arr.astype("uint8"), "RGB"), (fx, 0))
        es = Image.new("RGBA", (photo_w, H), (0, 0, 0, 0))               # soft seam scrim (photo-crop case only)
        ed = ImageDraw.Draw(es)
        for i in range(90):
            a = int(150 * (1 - i / 90))
            ed.line([((i if panel_left else photo_w - 1 - i), 0), ((i if panel_left else photo_w - 1 - i), H)], fill=(*scheme, a))
        canvas.paste(es, (fx, 0), es)
    # PANEL: a THEMED graphic when a theme is set + provider up, else a flat scheme gradient.
    themed, panel = False, None
    if (theme or "").strip() and llm.image_provider_available():
        try:
            # the split-poster PANEL is a small auxiliary graphic (behind the caption) -> lighter gpt-image-1;
            # the MAIN featured scene stays on gpt-image-2.
            data = await llm.generate_image_bytes(_panel_theme_prompt(theme), size="1024x1024",
                                                  quality="medium", model="gpt-image-1")
            if data:
                panel = _cover_fit(Image.open(io.BytesIO(data)).convert("RGB"), panel_w, H)
                pa = np.asarray(panel.convert("RGB")).astype(np.float32)
                ys = np.linspace(0, 1, H)[:, None, None]
                # Darken ONLY the top ~third (behind the headline) and fade to ~0 below, with a NEAR-BLACK
                # (not navy) scrim — so the scene keeps its true colour (a football pitch stays GREEN).
                al = np.clip(0.90 - ys * 1.5, 0.0, 0.9)
                panel = Image.fromarray((pa * (1 - al) + np.array((10, 15, 24), float) * al).astype("uint8"), "RGB")
                themed = True
        except Exception:
            panel = None
    if panel is None:
        ramp = np.linspace(1.08, 0.80, H)[:, None, None]
        panel = Image.fromarray(
            np.clip(np.broadcast_to(np.array(scheme, float), (H, panel_w, 3)) * ramp, 0, 255).astype("uint8"), "RGB")
    canvas.paste(panel, (px, 0))
    # SEAM (style rotates) + one ACCENT in the panel's safe mid zone (skipped on a themed panel to stay clean).
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    seam = v % 3
    if seam == 0:      # angled ribbon
        pts = ([(seam_x - 30, 0), (seam_x + 34, 0), (seam_x - 30, H), (seam_x - 94, H)] if panel_left
               else [(seam_x + 30, 0), (seam_x - 34, 0), (seam_x + 30, H), (seam_x + 94, H)])
        od.polygon(pts, fill=(*RED, 255))
    elif seam == 1:    # straight bold bar
        od.rectangle([seam_x - 14, 0, seam_x + 14, H], fill=(*RED, 255))
    else:              # thin double rule
        for dx in (-10, 12):
            od.rectangle([seam_x + dx - 3, 0, seam_x + dx + 3, H], fill=(*RED, 255))
    if not themed:
        ax = (70 if panel_left else px + 60)         # accent x inside the panel (safe, below headline)
        ay = int(H * 0.52)
        acc = v % 4
        if acc == 0:
            od.ellipse([ax, ay, ax + 200, ay + 200], outline=(*RED, 170), width=14)
        elif acc == 1:
            _accent_dot_grid(od, ax, ay, 4, 4, gap=30, r=6, fill=(*RED, 220))
        elif acc == 2:
            _accent_chevrons(od, ax, ay, n=3, size=40, gap=26, color=(*RED, 230), width=9)
        else:
            _accent_squiggle(od, ax, ay, panel_w - 150, amp=10, color=(*RED, 230), width=7)
    canvas = Image.alpha_composite(canvas.convert("RGBA"), ov).convert("RGB")
    person_box = (panel_w + 40, 0, W, H) if panel_left else (0, 0, photo_w - 40, H)
    return canvas, person_box, (1 if panel_left else 3)


async def _build_editorial_banner(brand, photo, name, role, headline, question, variant, keyword, theme="",
                                  require_cutout=False, eyebrow="", fit=""):
    """Keep the person AS-IS (their exact real photo — never regenerated) and change only the BACKGROUND:
    cut the real person out and composite them onto a REALISTIC themed background photo (a real stadium/pitch),
    graded + grounded so they sit in the scene. If there's no theme / no clean cut-out, fall back to the bold
    SPLIT poster (person cut-out beside a themed panel). `eyebrow` (optional intent label) drives the small
    kicker line above the headline. Returns (path, fname, meta), or None."""
    import numpy as np
    from ..providers import llm
    skin = SKINS["photo"]
    template = int(variant) % 6
    layout = (template % 3) + 1
    # EYEBROW: an explicit INTENT label (ANNOUNCEMENT / SAVE THE DATE / CELEBRATING …) wins, so the post reads
    # as what it IS. A personal feature (has an on-image name) keeps the rotating team kicker; a role-model /
    # campaign banner (no name) NEVER says 'IN THE SPOTLIGHT' — that makes an event look like a success story.
    if (eyebrow or "").strip():
        kicker = eyebrow.strip().upper()[:26]
    elif name:
        kicker = _EDITORIAL_KICKERS[template % len(_EDITORIAL_KICKERS)]
    else:
        kicker = "TALENTRUPT PRESENTS"
    canvas = person_box = None
    if (theme or "").strip() and llm.image_provider_available():
        hero = _cutout(photo)                                  # the REAL person, exact — only the bg changes
        cut_ok = False
        if hero.mode == "RGBA" and hero.width >= 160 and hero.height >= 240:
            al = np.asarray(hero.split()[-1])
            cut_ok = int(al.min()) < 245 and 0.30 <= float((al > 127).mean()) <= 0.97
        if cut_ok:
            try:
                data = await llm.generate_image_bytes(_scene_prompt(headline, question, variant, theme),
                                                      size="1024x1024", quality="medium")
                bg = _cover_fit(Image.open(io.BytesIO(data)).convert("RGB"), W, H) if data else None
            except Exception:
                bg = None
            if bg is not None:                                 # realistic themed scene + the real person on top
                canvas = _editorial_scrim(bg, layout, blur=2.0, strength=0.82, reach=0.5)
                person_box = _place_editorial_person(canvas, skin, hero, layout, photo_bg=True, fit=fit)
    if canvas is None:                                          # no theme / no clean cut -> split poster
        canvas, person_box, layout = await _bold_split_poster(photo, variant, theme)
    canvas = _apply_grain(canvas, variant, 4.0)
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, RAIL_W, H], fill=skin.accent)
    boxes = _draw_editorial_text(canvas, d, skin, name, role, headline, question, keyword, layout, person_box,
                                 kicker)
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
                         keyword="", theme="", prefer="", eyebrow="", fit=""):
    """Featured-employee banner. HARD RULE: the face is ALWAYS the person's REAL uploaded photo — NEVER an
    AI-generated face. `theme` drives the scene; pass name="" to omit the on-image name label. Priority:
      • FACESWAP key set -> an immersive AI scene with the person's EXACT REAL face swapped on
        (`_build_faceswap_banner`). Best: immersive scene + real face.
      • Otherwise (DEFAULT) -> the REAL cut-out person composited onto the themed scene
        (`_build_editorial_banner`, require_cutout) — their actual photo, face + clothes untouched.
      • No clean cut-out -> a clean framed/split design of the real photo (still the REAL face).
    The gpt-image edit path (`_build_ai_portrait_banner`) makes an AI face and is DELIBERATELY NOT used except
    inside faceswap (where the real face is swapped back on). Any failure -> a deterministic template."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except Exception:
        pass
    try:
        _src = ImageOps.exif_transpose(Image.open(io.BytesIO(photo_bytes)).convert("RGB"))
        # Cap the working size BEFORE the numpy cut-out/enhance: uploads are 5000px+ (~60MB RGB arrays) and
        # processing them full-res on the 2GB droplet spikes memory → OOM-kill → a 502. The output is 1080px,
        # so 1800px is ample for a crisp crop/cut-out.
        _src.thumbnail((1800, 1800), Image.LANCZOS)
        photo = _enhance_photo(_src)
    except Exception:
        return build_team_image(brand, photo_bytes, name, role, headline, question, variant,
                                style="spotlight_series", skin=random.choice(DETERMINISTIC_SKINS))
    try:
        from . import faceswap
        result = None
        # KEEP THE PERSON AS-IS (their exact real photo — never regenerated) and just CHANGE THE BACKGROUND:
        # cut the real person out and place them onto a REALISTIC themed background (a real stadium/pitch).
        if faceswap.faceswap_available():       # (opt-in) seamless AI scene + EXACT real face swapped on
            result = await _build_faceswap_banner(brand, photo, name, role, headline, question, variant, keyword, theme)
        if result is None:                      # DEFAULT: real cut-out person (as-is) on a realistic themed bg
            result = await _build_editorial_banner(brand, photo, name, role, headline, question, variant,
                                                   keyword, theme, eyebrow=eyebrow, fit=fit)
        if result is not None:
            try:                                # stamp the design inputs so a later REFINE can reuse them
                result[2]["variant"] = int(variant)
                if (eyebrow or "").strip():
                    result[2]["eyebrow"] = eyebrow
            except Exception:
                pass
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
