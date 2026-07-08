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
from . import designs
from .common import font
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


# --------------------------------------------------------------------------------------------------
# Meaningful copy bank — real marketing copy WITHOUT an LLM, so EVERY post reads as intentional (holiday
# greetings, themed recruitment lines, or a strong default). Used as the fallback when the LLM is
# unavailable AND to replace any weak/echoed headline that slips through (see `_is_weak_headline`).
# --------------------------------------------------------------------------------------------------
_HOLIDAY_COPY = {
    "diwali": ("Happy Diwali", "Wishing you light, prosperity, and new beginnings."),
    "deepavali": ("Happy Diwali", "Wishing you light, prosperity, and new beginnings."),
    "holi": ("Happy Holi", "May your year be as bright and colourful as today."),
    "navratri": ("Happy Navratri", "Nine nights of joy, energy, and new beginnings."),
    "dussehra": ("Happy Dussehra", "May good triumph and new journeys begin."),
    "dasara": ("Happy Dussehra", "May good triumph and new journeys begin."),
    "pongal": ("Happy Pongal", "A harvest of joy, health, and prosperity."),
    "onam": ("Happy Onam", "Wishing you a season of togetherness and plenty."),
    "raksha": ("Happy Raksha Bandhan", "Celebrating the bonds that keep us strong."),
    "rakhi": ("Happy Raksha Bandhan", "Celebrating the bonds that keep us strong."),
    "eid": ("Eid Mubarak", "Wishing you peace, joy, and togetherness."),
    "ramadan": ("Ramadan Mubarak", "A month of peace, reflection, and blessings."),
    "ramzan": ("Ramadan Mubarak", "A month of peace, reflection, and blessings."),
    "christmas": ("Merry Christmas", "Warm wishes for joy and togetherness this season."),
    "xmas": ("Merry Christmas", "Warm wishes for joy and togetherness this season."),
    "hanukkah": ("Happy Hanukkah", "Wishing you light and warmth this season."),
    "new year": ("Happy New Year", "Here's to new goals and great teams ahead."),
    "thanksgiving": ("Happy Thanksgiving", "Grateful for the people who make it all possible."),
    "halloween": ("Happy Halloween", "Wishing you a spook-tacular day."),
    "valentine": ("Happy Valentine's Day", "A little appreciation goes a long way."),
    "womens day": ("Happy Women's Day", "Celebrating the women who lead, build, and inspire."),
    "mens day": ("Happy Men's Day", "Here's to the men who lead with heart."),
    "mothers day": ("Happy Mother's Day", "Celebrating the strength of every mother."),
    "fathers day": ("Happy Father's Day", "Celebrating the dads who lead by example."),
    "independence day": ("Happy Independence Day", "Proud, free, and moving forward together."),
    "republic day": ("Happy Republic Day", "Celebrating unity, pride, and progress."),
    "labour day": ("Happy Labour Day", "Honouring the people behind every great result."),
    "labor day": ("Happy Labour Day", "Honouring the people behind every great result."),
    "earth day": ("Happy Earth Day", "Building a greener, better tomorrow, together."),
    "pride": ("Happy Pride", "Celebrating every identity, every story."),
    "yoga": ("International Yoga Day", "A calm mind builds a stronger team."),
    "wellness": ("Wellness First", "A healthy team is a happy, high-performing team."),
    "mindfulness": ("A Mindful Moment", "Small pauses power big performance."),
    "meditation": ("A Mindful Moment", "Small pauses power big performance."),
}

_THEME_COPY = [
    (re.compile(r"\b(nurse|nursing|healthcare|clinical|medical|hospital|patient|care\s*team)\b", re.I),
     "Healthcare Hiring, Done Right", "Connecting care teams with the talent they need to thrive.", "HEALTHCARE HIRING"),
    (re.compile(r"\b(engineer|developer|software|tech|coding|devops|cloud|\bit\b)\b", re.I),
     "Building Tech Teams That Deliver", "The right engineers, matched to your mission.", "TECH HIRING"),
    (re.compile(r"\b(data.?driven|analytics|metric|insight)\w*\b", re.I),
     "Data-Driven Hiring", "Smarter decisions, backed by real insight.", "DATA-DRIVEN HIRING"),
    (re.compile(r"\b(scal|grow|growth|expansion|hypergrowth|ramp)\w*\b", re.I),
     "Scale Your Team With Confidence", "The right people, exactly when you're ready to grow.", "TIME TO SCALE"),
    (re.compile(r"\b(leader|leadership|executive|c-suite|founder)\w*\b", re.I),
     "Leadership That Moves You Forward", "Placing the leaders who shape what's next.", "LEADERSHIP HIRING"),
    (re.compile(r"\b(diversit|inclusion|\bdei\b|belonging)\w*\b", re.I),
     "Hiring for Every Story", "Diverse teams build better outcomes.", "DIVERSITY IN HIRING"),
    (re.compile(r"\b(cultur|team|people|employee|onboard)\w*\b", re.I),
     "People First, Always", "Building teams where great work happens.", "PEOPLE FIRST"),
    (re.compile(r"\b(recruit|hir|staffing|sourc|\brpo\b|talent)\w*\b", re.I),
     "Recruitment, Done Right", "We build the teams that build your business.", "LET'S TALK HIRING"),
]

_DEFAULT_COPY = ("Recruitment, Done Right", "We build the teams that build your business.", "LET'S TALK HIRING")

# When there's no theme and no LLM headline, ROTATE across these so two generic posts never read the same
# ("Recruitment, Done Right" on every card was the #1 reason a batch looked identical). Picked at random.
_DEFAULT_COPY_BANK = [
    ("Recruitment, Done Right", "We build the teams that build your business.", "LET'S TALK HIRING"),
    ("Great Teams Start Here", "The right people, matched to your mission.", "HIRING PARTNERS"),
    ("Hire Smarter, Grow Faster", "Talent that moves your business forward.", "LET'S TALK TALENT"),
    ("Your Next Great Hire", "We find the people who make the difference.", "TALENT ON DEMAND"),
    ("Building Winning Teams", "From first brief to final offer — done right.", "RPO DONE RIGHT"),
    ("Talent That Delivers", "The people behind every great result.", "PEOPLE FIRST"),
    ("Powering Your Growth", "Scale your team with confidence.", "READY TO SCALE"),
    ("The Right People, Right Now", "Recruitment that keeps pace with you.", "LET'S TALK HIRING"),
    ("Where Great Careers Begin", "Connecting the right talent with the right teams.", "NOW HIRING"),
    ("Beyond the Resume", "We match on potential, not just paper.", "SMARTER HIRING"),
]

_WEAK_WORDS = {"on", "for", "of", "with", "to", "in", "and", "the", "a", "an", "at", "by", "about",
               "from", "as", "or", "but", "our", "your", "my", "this", "that", "it", "is", "are"}


def _meaningful_copy(concept: str) -> tuple[str, str, str]:
    """A real (headline, subline, kicker) for `concept` WITHOUT an LLM — a holiday greeting, a themed
    recruitment line, or a strong default. Never echoes the raw prompt."""
    c = (concept or "").strip()
    m = _HOLIDAY_RE.search(c)
    if m:
        key = m.group(0).lower().replace("'", "").replace("'", "").strip()
        if key in _HOLIDAY_COPY:
            h, s = _HOLIDAY_COPY[key]
            return h, s, ""
        if key in ("festival", "holiday", "seasons greetings", "season's greetings", "anniversary", "birthday"):
            return "Season's Greetings", "Wishing you joy and good things ahead.", ""
    for rx, h, s, k in _THEME_COPY:
        if rx.search(c):
            return h, s, k
    return random.choice(_DEFAULT_COPY_BANK)   # no theme -> rotate so a batch never repeats one line


def _is_weak_headline(h: str) -> bool:
    """True when a headline is a fragment / prompt-echo rather than real copy: too short, filler-only, or
    dangling on a preposition (e.g. 'On Mission', 'For The Team', 'Use A Different Style')."""
    words = re.findall(r"[A-Za-z0-9']+", h or "")
    if len(words) < 2:
        return True
    lows = [w.lower() for w in words]
    if all(w in _WEAK_WORDS or len(w) <= 2 for w in lows):
        return True
    return lows[0] in _WEAK_WORDS or lows[-1] in _WEAK_WORDS


def _good_subtext(st: str) -> bool:
    """True when a supplied subline is a genuine sentence worth printing (not a stray instruction/fragment)."""
    st = (st or "").strip()
    return len(st.split()) >= 4 and not re.search(
        r"\b(style|styles|look|looks|version|background|scene|theme|design|layout|variation|post|image|"
        r"different|warmer|brighter|colou?r|colou?rs)\b", st, re.I)


def _fallback_plan(concept: str, tagline: str, has_person: bool) -> dict:
    c = (concept or "").strip()
    observance = bool(_HOLIDAY_RE.search(c)) and not has_person
    head, sub, kicker = _meaningful_copy(c)
    v = {"template": "observance" if observance else ("hero" if has_person else "statement"),
         "headline": head, "subtext": sub, "kicker": kicker, "scene": c, "bg": "navy"}
    return _coerce(v, concept, tagline, has_person)


def _coerce(v: dict, concept: str, tagline: str, has_person: bool) -> dict:
    headline = (v.get("headline") or "").strip()
    if _is_weak_headline(headline):        # LLM off, or a prompt-echo fragment -> real curated copy
        mh, ms, mk = _meaningful_copy(concept)
        headline = mh
        v = {**v, "subtext": (v.get("subtext") or ms), "kicker": (v.get("kicker") or mk)}
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


def _canvas(prof) -> Image.Image:
    """A fresh RGBA canvas painted with the profile's background: a solid fill, a navy/cream vertical
    SPLIT (split_duotone), or subtle angular facets over a near-black base (midnight)."""
    canvas = Image.new("RGBA", (W, H), (*prof.bg, 255))
    if prof.key == "split_duotone":
        ImageDraw.Draw(canvas).rectangle([int(W * 0.46), 0, W, H], fill=(*prof.bg_alt, 255))
    elif prof.motif == "facets":
        shades = [prof.bg_alt, (min(255, prof.bg_alt[0] + 6), min(255, prof.bg_alt[1] + 8), min(255, prof.bg_alt[2] + 10)),
                  prof.bg_alt, prof.bg]
        _faceted_bg(canvas, shades)
    return canvas


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


def _alpha_center_x(cut: Image.Image) -> int:
    """Horizontal centre-of-mass of the subject's alpha — so a width crop keeps the person (face), not a desk."""
    import numpy as np
    cols = (np.asarray(cut.split()[-1]) > 64).sum(axis=0)
    tot = int(cols.sum())
    if tot <= 0:
        return cut.width // 2
    return int((cols * np.arange(cut.width)).sum() / tot)


# Person occupies the right side; the left column (PAD..PAD+HERO_TEXT_W) is reserved for the headline.
HERO_TEXT_W = 420
_PERSON_MAX_W = W - (PAD + HERO_TEXT_W) - 32   # keep the person clear of the headline column


def _place_person_cutout(canvas: Image.Image, cut: Image.Image, side: str = "right") -> int:
    """Size the cut-out person aspect-aware + bottom anchor (no backdrop) on the chosen `side`. Returns
    the person's LEFT x so the caller can keep text clear. Seated/upper-body/standing all read as a hero."""
    bbox = cut.getbbox()          # tighten to the real subject (defensive)
    if bbox:
        cut = cut.crop(bbox)
    ar = cut.height / max(1, cut.width)
    target_h = int(H * (0.94 if ar >= 1.7 else 0.86 if ar >= 1.15 else 0.72))
    scale = target_h / cut.height
    pw, ph = max(1, int(cut.width * scale)), target_h
    if pw > _PERSON_MAX_W:        # too wide -> CROP around the person's centre (keep the face), don't shrink
        crop_w = max(1, int(_PERSON_MAX_W / scale))
        cx = _alpha_center_x(cut)
        x0 = max(0, min(cut.width - crop_w, cx - crop_w // 2))
        cut = cut.crop((x0, 0, x0 + crop_w, cut.height))
        pw = _PERSON_MAX_W
    p = cut.resize((pw, ph), Image.LANCZOS)
    x = 24 if side == "left" else W - pw - 24   # bottom anchored on the chosen side
    y = H - ph
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([x + int(pw * 0.16), H - 40, x + int(pw * 0.84), H - 8], fill=(0, 0, 0, 95))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(13)))
    canvas.alpha_composite(p, (x, y))
    return x


def _float_cutout(canvas: Image.Image, cut: Image.Image, disc: tuple, side: str = "right") -> None:
    """A cleanly cut-out person, prominent + bottom anchored on a soft brand backdrop disc (`disc` colour)."""
    box = [520, 11, 1686, 1177] if side == "right" else [W - 1686, 11, W - 520, 1177]
    ImageDraw.Draw(canvas, "RGBA").ellipse(box, fill=(*disc, 240))
    _place_person_cutout(canvas, cut, side=side)


def _photo_panel(canvas: Image.Image, person_rgb: Image.Image, disc: tuple, side: str = "right",
                 keyline: tuple = WHITE) -> None:
    """No clean cut-out possible (prod default) -> a clean rounded PHOTO PANEL on the chosen side: the
    person's real photo cover-fit into a rounded card (their own background clipped to the shape), a brand
    accent disc behind it, a soft drop shadow and a keyline. Reads as intentional design, never a broken
    cut-out — and the person is fully framed, never half-off."""
    pw, ph = int(W * 0.44), int(H * 0.80)
    px = 34 if side == "left" else W - pw - 34
    py = (H - ph) // 2
    d = ImageDraw.Draw(canvas, "RGBA")
    d.ellipse([px - 46, py - 26, px + pw + 34, py + ph + 26], fill=(*disc, 235))        # accent behind
    sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([px + 6, py + 12, px + pw + 6, py + ph + 12], radius=40,
                                         fill=(11, 34, 58, 95))
    canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)))
    canvas.alpha_composite(_rounded(_cover_fit(person_rgb, pw, ph), 40), (px, py))
    ImageDraw.Draw(canvas).rounded_rectangle([px - 4, py - 4, px + pw + 4, py + ph + 4], radius=44,
                                             outline=(*keyline, 255), width=6)


def _hero_person(canvas: Image.Image, person_rgb: Image.Image, prof) -> None:
    """Place the featured person on `prof.hero_photo_side`: a floating cut-out (when the background can be
    removed), else a clean framed photo panel. The real face + clothes are untouched and fully in frame."""
    side = getattr(prof, "hero_photo_side", "right")
    disc = prof.disc_col
    keyline = prof.accent2 if prof.dark else prof.accent
    try:
        cut, ok = _clean_cutout(person_rgb)
        if ok and cut is not None:
            _float_cutout(canvas, cut, disc, side=side)
        else:
            _photo_panel(canvas, person_rgb, disc, side=side, keyline=keyline)
    except Exception as e:
        log.warning("chatpost hero person failed: %s", e)
        try:
            _photo_panel(canvas, person_rgb, disc, side=side, keyline=keyline)
        except Exception:
            pass


# --------------------------------------------------------------------------------------------------
# "MAN ON A MISSION" spotlight template (reproduces Talentrupt's own reference post)
# --------------------------------------------------------------------------------------------------
_MISSION_Q = "What does success look like when you're building for the long term?"

# Curated reflective questions for the 'Man on a Mission' spotlight — real, meaningful copy so the
# post never echoes the user's raw instruction (e.g. "Use A Different Style"). Seeded per person so
# it's stable, and offset by the backdrop variant so a "different style" edit rotates it too.
_MISSION_QUESTIONS = [
    "What does building something that lasts really take?",
    "What does it take to lead when it matters most?",
    "What drives the people who shape what's next?",
    "What does success look like when you're building for the long term?",
    "How do you turn a bold vision into everyday progress?",
    "What keeps a great team moving toward a big goal?",
    "What does showing up with purpose look like every day?",
]


def _mission_question(name: str, variant: int = 0) -> str:
    seed = sum(ord(c) for c in (name or "")) + int(variant or 0)
    return _MISSION_QUESTIONS[seed % len(_MISSION_QUESTIONS)]


# 'Man on a Mission' backdrop palettes. All are DARK so the fixed light text (red lead, white/cream
# copy, light-blue script name, white role pill) stays legible on every one. Index 0 is the original
# navy. A conversational edit ("different background", "warmer", "brighter") swaps to another index —
# same person, same layout, visibly different backdrop. See `mission_variant`.
_MISSION_BGS = [
    # 0 — navy (original)
    {"base": (0x0B, 0x35, 0x59), "facets": [(0x10, 0x40, 0x68), (0x0A, 0x2E, 0x50), (0x13, 0x49, 0x74), (0x0C, 0x38, 0x5E)]},
    # 1 — warm espresso / plum ("warmer")
    {"base": (0x3A, 0x24, 0x2E), "facets": [(0x4E, 0x30, 0x3A), (0x30, 0x1E, 0x28), (0x5A, 0x39, 0x3F), (0x42, 0x2A, 0x33)]},
    # 2 — bright royal azure ("brighter")
    {"base": (0x12, 0x4E, 0x86), "facets": [(0x1B, 0x5E, 0x9E), (0x0F, 0x45, 0x78), (0x24, 0x6C, 0xB0), (0x17, 0x57, 0x92)]},
    # 3 — deep maroon
    {"base": (0x4C, 0x18, 0x22), "facets": [(0x60, 0x22, 0x2E), (0x3C, 0x12, 0x1B), (0x70, 0x2C, 0x38), (0x54, 0x1D, 0x27)]},
    # 4 — deep teal
    {"base": (0x0C, 0x3A, 0x38), "facets": [(0x12, 0x4A, 0x47), (0x0A, 0x30, 0x2F), (0x18, 0x56, 0x52), (0x0E, 0x40, 0x3D)]},
    # 5 — indigo
    {"base": (0x24, 0x1E, 0x4A), "facets": [(0x2E, 0x27, 0x5E), (0x1C, 0x18, 0x3C), (0x38, 0x30, 0x70), (0x28, 0x22, 0x52)]},
]
MISSION_BG_COUNT = len(_MISSION_BGS)


def mission_variant(instruction: str, prev: int = 0) -> int:
    """Pick a Mission backdrop index from a conversational edit. Colour/tone words map to a matching
    palette; a generic 'different background' rotates to the next one so it always visibly changes."""
    t = (instruction or "").lower()
    warm = any(w in t for w in ("warm", "cozy", "cosy"))
    bright = any(w in t for w in ("bright", "light", "vivid", "vibrant", "lighter"))
    if bright:                       # 'warmer and brighter' -> bright wins (a clearer visible change)
        return 2
    if warm:
        return 1
    if any(w in t for w in ("maroon", "crimson", "burgundy")) or "red bg" in t or "red background" in t:
        return 3
    if any(w in t for w in ("teal", "green", "emerald")):
        return 4
    if any(w in t for w in ("purple", "indigo", "violet")):
        return 5
    if "navy" in t or "blue" in t:
        return 0 if prev != 0 else 2
    return (prev + 1) % MISSION_BG_COUNT     # generic 'change the background' -> next in rotation


def _faceted_bg(canvas: Image.Image, facets: list) -> None:
    """Subtle angular panels over the base — the 'Man on a Mission' faceted backdrop (palette-driven)."""
    d = ImageDraw.Draw(canvas, "RGBA")
    polys = [
        [(0.52, 0.0), (1.0, 0.0), (1.0, 0.34), (0.66, 0.16)],
        [(0.60, 0.02), (0.98, 0.0), (0.86, 0.40), (0.66, 0.30)],
        [(0.48, 0.10), (0.72, 0.0), (0.70, 0.30), (0.50, 0.26)],
        [(0.74, 0.30), (1.0, 0.20), (1.0, 0.62), (0.80, 0.52)],
    ]
    for i, poly in enumerate(polys):
        d.polygon([(int(px * W), int(py * H)) for px, py in poly], fill=(*facets[i % len(facets)], 80))


def _dashed_arc(canvas: Image.Image, color: tuple) -> None:
    """A decorative dashed curve sweeping from the top-right down toward the person, with an arrowhead."""
    d = ImageDraw.Draw(canvas, "RGBA")
    cx, cy, r = int(W * 0.64), int(H * -0.02), int(W * 0.32)
    pts = [(cx + int(r * math.cos(math.radians(deg))), cy + int(r * math.sin(math.radians(deg))))
           for deg in range(30, 128, 4)]
    for i in range(0, len(pts) - 1, 2):        # dashed
        d.line([pts[i], pts[i + 1]], fill=(*color, 225), width=4)
    if len(pts) >= 3:                          # small arrowhead at the end (pointing toward the person)
        (ex, ey), (bx, by) = pts[-1], pts[-3]
        ang = math.atan2(ey - by, ex - bx)
        for da in (math.radians(150), math.radians(-150)):
            d.line([(ex, ey), (ex + int(20 * math.cos(ang + da)), ey + int(20 * math.sin(ang + da)))],
                   fill=(*color, 225), width=4)


def _briefcase(d: ImageDraw.ImageDraw, x: int, y: int, color: tuple) -> None:
    d.rounded_rectangle([x, y + 6, x + 26, y + 26], radius=3, outline=color, width=3)
    d.rectangle([x + 8, y, x + 18, y + 8], outline=color, width=3)     # handle
    d.line([(x, y + 15), (x + 26, y + 15)], fill=color, width=3)


def _render_mission(plan: dict, person_rgb: Image.Image) -> Image.Image:
    """Talentrupt's 'Man on a Mission' spotlight: three-part headline (LEAD / on a / Mission!), a reflective
    question, 'Featuring <Name>' in script, a role pill, dashed-arc accents — and the real person seated
    prominently bottom-right on a faceted navy backdrop."""
    bg = _MISSION_BGS[int(plan.get("bg_variant", 0)) % MISSION_BG_COUNT]
    canvas = Image.new("RGBA", (W, H), (*bg["base"], 255))
    _faceted_bg(canvas, bg["facets"])
    _dashed_arc(canvas, WHITE)
    try:                                       # the real person, under the left-hand text
        cut, ok = _clean_cutout(person_rgb)
        if ok and cut is not None:
            _place_person_cutout(canvas, cut)
        else:
            _photo_panel(canvas, person_rgb, RED)
    except Exception as e:
        log.warning("mission person failed: %s", e)
    _wordmark(canvas, dark_bg=True)
    d = ImageDraw.Draw(canvas)
    TW, x = 400, PAD
    # three-part headline
    d.text((x, 146), plan.get("lead", "Man"), font=heading_font(122), fill=RED)
    d.text((x + 8, 288), "on a", font=script_font(78), fill=WHITE)
    kw = plan.get("mission_word", "Mission!")
    kf = heading_font(100)
    kww = d.textlength(kw, font=kf)
    d.rectangle([x - 6, 394, int(x + kww + 30), 502], fill=(*RED, 255))
    d.text((x + 12, 384), kw, font=kf, fill=WHITE)
    # reflective question
    y = 532
    for ln in _wrap(d, (plan.get("subtext") or _MISSION_Q), body_font(30), TW)[:4]:
        d.text((x, y), ln, font=body_font(30), fill=CREAM)
        y += 40
    y += 24
    d.text((x, y), "Featuring", font=script_font(38), fill=CREAM)
    y += 50
    d.text((x, y), (plan.get("person_name") or "").strip(), font=script_font(64), fill=(0x9E, 0xC6, 0xEC))
    y += 84
    role = (plan.get("person_role") or "").strip().upper()
    if role:
        # Auto-fit: shrink the font so the WHOLE role fits the pill (never a mid-word cut like "SPECILA").
        MAX_PILL_W = 470          # keep the pill clear of the person on the right
        size = 28
        rf = heading_font(size)
        while size > 15 and d.textlength(role, font=rf) + 96 > MAX_PILL_W:
            size -= 1
            rf = heading_font(size)
        rt = role
        if d.textlength(rt, font=rf) + 96 > MAX_PILL_W:   # still too long at min size -> trim on a word
            while rt and d.textlength(rt + "…", font=rf) + 96 > MAX_PILL_W:
                rt = rt.rsplit(" ", 1)[0] if " " in rt.strip() else rt[:-1]
            rt = rt.rstrip() + "…"
        rw = d.textlength(rt, font=rf)
        d.rounded_rectangle([x, y, int(x + rw + 96), y + 58], radius=29, fill=(*WHITE, 255))
        _briefcase(d, x + 24, y + 15, RED)
        d.text((x + 64, y + (58 - size) // 2 - 2), rt, font=rf, fill=NAVY)
    d.line([(PAD, H - 66), (PAD + 210, H - 66)], fill=(*WHITE, 255), width=3)
    return canvas.convert("RGB")


# --------------------------------------------------------------------------------------------------
# Brand chrome (drawn crisply by the app)
# --------------------------------------------------------------------------------------------------
def _wordmark(canvas: Image.Image, dark_bg: bool, align: str = "left", x: int = PAD) -> None:
    col = WHITE if dark_bg else NAVY
    if align == "center":
        if not paste_wordmark(canvas, PAD, 60, W - 2 * PAD, 56, dark_bg=dark_bg, align="center"):
            d = ImageDraw.Draw(canvas)
            f = heading_font(40)
            d.text(((W - d.textlength("TALENTRUPT", font=f)) / 2, 66), "TALENTRUPT", font=f, fill=col)
        return
    if not paste_wordmark(canvas, x, 60, 300, 56, dark_bg=dark_bg, align="left"):
        ImageDraw.Draw(canvas).text((x, 66), "TALENTRUPT", font=heading_font(40), fill=col)


def _kicker(canvas: Image.Image, x: int, y: int, text: str, prof, center: bool = False) -> int:
    """The eyebrow above the headline, styled per profile: pill | band | rule | plain. Returns y below it."""
    if not text:
        return y
    d = ImageDraw.Draw(canvas)
    style = prof.kicker_style
    if style == "plain":                         # letterspaced caps, no chrome (soft_neutral)
        f = heading_font(24)
        t = " ".join((text.upper()[:26]))
        tw = d.textlength(t, font=f)
        tx = (W - tw) / 2 if center else x
        d.text((tx, y), t, font=f, fill=(*prof.accent, 255))
        return int(y + 46)
    if style == "rule":                          # small-caps over a thin accent2 rule (editorial)
        f = heading_font(24)
        t = " ".join((text.upper()[:26]))
        tw = d.textlength(t, font=f)
        tx = (W - tw) / 2 if center else x
        d.text((tx, y), t, font=f, fill=(*prof.accent, 255))
        rx0 = (W - tw) / 2 if center else x
        d.rectangle([rx0, y + 40, rx0 + tw, y + 42], fill=(*prof.accent2, 255))
        return int(y + 66)
    # pill (default) or band (square-corner)
    f = heading_font(26)
    t = text.upper()[:26]
    tw = d.textlength(t, font=f)
    bx = (W - (tw + 44)) / 2 if center else x
    radius = 25 if style == "pill" else 4
    d.rounded_rectangle([bx, y, bx + tw + 44, y + 50], radius=radius, fill=(*prof.accent, 255))
    d.text((bx + 22, y + 10), t, font=f, fill=(*prof.on_accent, 255))
    return y + 68


def _headline(canvas: Image.Image, text: str, red_word: str, x: int, y: int, max_w: int,
              size: int, prof, max_lines: int = 4, center: bool = False) -> int:
    """Headline wrapped to max_w in the profile's head family, with any `red_word` flipped to the accent.
    Centered when `center` (soft_neutral). Returns the y below the block."""
    d = ImageDraw.Draw(canvas)
    size = max(20, int(size * getattr(prof, "head_scale", 1.0)))
    f = font(prof.head_family, size)
    # Shrink until the LONGEST single word fits the column — wide display faces (Archivo/Playfair) must
    # never break a word mid-way ("Healthcar/e"). Words still wrap normally; only the size adapts.
    words_all = [w for w in re.split(r"\s+", text) if w]
    while size > 30 and max((d.textlength(w, font=f) for w in words_all), default=0) > max_w:
        size -= 4
        f = font(prof.head_family, size)
    base = prof.ink
    red_tokens = {re.sub(r"[^a-z0-9]", "", w.lower()) for w in (red_word or "").split() if w}
    lines = _wrap(d, text, f, max_w)[:max_lines]
    lh = int(size * 1.12)
    for ln in lines:
        lw = d.textlength(ln, font=f)
        cx = (W - lw) / 2 if center else x
        for word in ln.split():
            key = re.sub(r"[^a-z0-9]", "", word.lower())
            col = prof.accent if (key and key in red_tokens) else base
            d.text((cx, y), word, font=f, fill=col)
            cx += d.textlength(word + " ", font=f)
        y += lh
    return y


def _divider(canvas: Image.Image, x: int, y: int, prof, center: bool = False) -> int:
    """Divider under the headline, styled per profile: bar | dots | double_rule | none."""
    d = ImageDraw.Draw(canvas)
    col = prof.divider_col
    style = prof.divider
    if style == "none":
        return y + 8
    if style == "dots":
        cx = W / 2 if center else x + 24
        for i in range(3):
            px = cx + (i - (1 if center else 0)) * 34
            d.ellipse([px - 8, y - 4, px + 8, y + 12], fill=(*col, 255))
        return y + 30
    if style == "double_rule":
        x0 = x
        d.rectangle([x0, y, x0 + 150, y + 2], fill=(*col, 255))
        d.rectangle([x0, y + 8, x0 + 150, y + 10], fill=(*col, 255))
        return y + 34
    bx = (W - 96) / 2 if center else x           # bar
    d.rectangle([bx, y, bx + 96, y + 8], fill=(*col, 255))
    return y + 30


def _stat_cards(canvas: Image.Image, stats: list[dict], x: int, y: int, total_w: int, prof) -> None:
    """A row of up to 3 rounded stat cards with a big value + a small label, colours from the profile."""
    n = len(stats)
    if not n:
        return
    gap = 22
    cw = (total_w - gap * (n - 1)) // n
    ch = 190
    # Alternate the profile's card fill with its accent for rhythm (both are legibility-checked).
    cols = [prof.card_bg, prof.accent, prof.card_bg]
    d = ImageDraw.Draw(canvas)
    for i, s in enumerate(stats[:3]):
        cx = x + i * (cw + gap)
        fill = cols[i % 3]
        on = prof.on_accent if fill == prof.accent else prof.card_ink
        sh = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([cx + 3, y + 6, cx + cw + 3, y + ch + 6], radius=26,
                                             fill=(11, 34, 58, 60))
        canvas.alpha_composite(sh.filter(ImageFilter.GaussianBlur(8)))
        d = ImageDraw.Draw(canvas)
        d.rounded_rectangle([cx, y, cx + cw, y + ch], radius=26, fill=(*fill, 255))
        val = str(s["value"])[:8]
        vf = font(prof.head_family, 76)
        while d.textlength(val, font=vf) > cw - 40 and vf.size > 34:
            vf = font(prof.head_family, vf.size - 6)
        d.text((cx + (cw - d.textlength(val, font=vf)) / 2, y + 30), val, font=vf, fill=(*on, 255))
        lab = str(s["label"]).upper()[:22]
        lf = body_font(24)
        for j, ln in enumerate(_wrap(d, lab, lf, cw - 36)[:2]):
            d.text((cx + (cw - d.textlength(ln, font=lf)) / 2, y + 122 + j * 30), ln, font=lf,
                   fill=(*on, 220))


def _cta_button(canvas: Image.Image, x: int, y: int, text: str, prof) -> None:
    if not text:
        return
    d = ImageDraw.Draw(canvas)
    f = heading_font(26)
    t = text.upper()[:22]
    tw = d.textlength(t, font=f)
    col = prof.ink
    d.rounded_rectangle([x, y, x + tw + 96, y + 58], radius=29, outline=(*col, 255), width=3)
    d.text((x + 28, y + 14), t, font=f, fill=col)
    ax = x + tw + 54
    d.line([(ax, y + 29), (ax + 22, y + 29)], fill=(*prof.accent, 255), width=4)
    d.line([(ax + 14, y + 21), (ax + 22, y + 29), (ax + 14, y + 37)], fill=(*prof.accent, 255), width=4, joint="curve")


def _footer(canvas: Image.Image, prof, align: str = "left") -> None:
    """An accent-circle globe + website (Talentrupt's footer signature), profile-coloured. `align` puts it
    bottom-left (default) or bottom-right (so it clears a hero photo placed on the left)."""
    d = ImageDraw.Draw(canvas)
    cy = H - 66
    r = 20
    url = "www.talentrupt.com"
    uf = body_font(28)
    block_w = 2 * r + 16 + int(d.textlength(url, font=uf))
    x0 = (W - PAD - block_w) if align == "right" else PAD
    d.ellipse([x0, cy - r, x0 + 2 * r, cy + r], fill=(*prof.accent, 255))
    gx0, gy0 = x0 + 6, cy - 14
    d.ellipse([gx0, gy0, gx0 + 28, gy0 + 28], outline=(*prof.on_accent, 255), width=2)
    d.line([(gx0 + 14, gy0), (gx0 + 14, gy0 + 28)], fill=(*prof.on_accent, 255), width=2)
    d.line([(gx0, gy0 + 14), (gx0 + 28, gy0 + 14)], fill=(*prof.on_accent, 255), width=2)
    d.text((x0 + 2 * r + 16, cy - 17), url, font=uf, fill=prof.ink)


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


def _arcs(canvas: Image.Image, cx: int, cy: int, color: tuple) -> None:
    """Concentric quarter-circle strokes radiating from a corner (split_duotone signature)."""
    d = ImageDraw.Draw(canvas, "RGBA")
    for i, r in enumerate((150, 230, 310)):
        d.arc([cx - r, cy - r, cx + r, cy + r], start=180, end=270, fill=(*color, 200 - i * 30), width=6)


def _hairline_frame(canvas: Image.Image, color: tuple, corner: tuple) -> None:
    """A thin inset frame with a small solid square on the top-left corner (editorial signature)."""
    d = ImageDraw.Draw(canvas, "RGBA")
    m = 30
    d.rectangle([m, m, W - m, H - m], outline=(*color, 150), width=1)
    d.rectangle([m, m, m + 26, m + 26], fill=(*corner, 255))


def _accents(canvas: Image.Image, prof, seed: int) -> None:
    """Decorative motif for the poster templates, dispatched on the profile's signature."""
    accent, accent2 = prof.accent, prof.accent2
    motif = prof.motif
    if motif == "arcs":
        _arcs(canvas, int(W * 0.62), H + 20, accent)
        _dot_grid(canvas, PAD, H - 200, 4, 3, 24, 5, accent2)
    elif motif == "hairline_frame":
        _hairline_frame(canvas, accent2, accent)
    elif motif == "facets":                       # facets already painted on the bg -> add a faint grid
        _dot_grid(canvas, W - 200, 150, 4, 4, 26, 5, accent2)
        _dot_grid(canvas, PAD, H - 210, 5, 3, 26, 5, accent)
    elif motif == "dot_grid":
        _dot_grid(canvas, W - 210, 150, 4, 4, 28, 6, accent2)
        _dot_grid(canvas, PAD, H - 210, 5, 3, 26, 5, accent)
    else:                                         # diag_circle (classic) — the original signature
        kind = seed % 3
        if kind == 0:
            _diag_circle(canvas, W - 120, 150, 96, accent)
            _dot_grid(canvas, PAD, H - 210, 5, 4, 26, 5, accent2)
        elif kind == 1:
            _diag_circle(canvas, W - 130, H - 150, 104, accent2)
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


def _render(plan: dict, bg_img: Image.Image | None, person: Image.Image | None, prof) -> Image.Image:
    tmpl = plan["template"]

    if tmpl == "mission" and person is not None:
        return _render_mission(plan, person)      # mission keeps its own 6-backdrop variant system

    if tmpl == "hero" and person is not None:
        HW = HERO_TEXT_W
        side = prof.hero_photo_side
        tx = (W - PAD - HW) if side == "left" else PAD    # text column opposite the photo
        canvas = _canvas(prof)
        _hero_person(canvas, person, prof)
        _wordmark(canvas, dark_bg=prof.dark, x=(tx if side == "left" else PAD))
        y = 210
        y = _kicker(canvas, tx, y, plan["kicker"], prof)
        y = _headline(canvas, plan["headline"], plan["red_word"], tx, y, HW, 72, prof, max_lines=5)
        y = _divider(canvas, tx, y + 16, prof)
        d = ImageDraw.Draw(canvas)
        for ln in _wrap(d, plan["subtext"], body_font(30), HW)[:3]:
            d.text((tx, y), ln, font=body_font(30), fill=prof.sub)
            y += 42
        if plan["cta"]:
            _cta_button(canvas, tx, y + 20, plan["cta"], prof)
        _footer(canvas, prof, align="right" if side == "left" else "left")
        return canvas.convert("RGB")

    if tmpl == "observance":
        # A photo scene is the star; the profile only restyles the chrome (type/kicker/divider colours).
        scene = bg_img if bg_img is not None else _canvas(prof)
        canvas = _scrim_left(scene, True)
        _wordmark(canvas, dark_bg=True, align="center")
        y = 250
        d = ImageDraw.Draw(canvas)
        if plan["kicker"]:
            y = _kicker(canvas, PAD, y, plan["kicker"], prof, center=True)
        y = _headline(canvas, plan["headline"], plan["red_word"], PAD, y, W - 2 * PAD, 96, prof,
                      max_lines=3, center=True)
        y = _divider(canvas, PAD, y + 16, prof, center=True)
        for ln in _wrap(d, plan["subtext"], body_font(32), W - 2 * PAD)[:3]:
            d.text(((W - d.textlength(ln, font=body_font(32))) / 2, y), ln, font=body_font(32), fill=CREAM)
            y += 44
        _footer(canvas, prof)
        return canvas.convert("RGB")

    # statement / stat (no person)
    center = prof.align == "center"
    canvas = _canvas(prof)
    _accents(canvas, prof, hash(plan["headline"]) & 7)
    _wordmark(canvas, dark_bg=prof.dark, align="center" if center else "left")
    y = 210
    y = _kicker(canvas, PAD, y, plan["kicker"], prof, center=center)
    y = _headline(canvas, plan["headline"], plan["red_word"], PAD, y, W - 2 * PAD, 92, prof,
                  max_lines=4, center=center)
    y = _divider(canvas, PAD, y + 16, prof, center=center)
    d = ImageDraw.Draw(canvas)
    for ln in _wrap(d, plan["subtext"], body_font(32), W - 2 * PAD)[:3]:
        lx = (W - d.textlength(ln, font=body_font(32))) / 2 if center else PAD
        d.text((lx, y), ln, font=body_font(32), fill=prof.sub)
        y += 46
    if plan["template"] == "stat" and plan["stats"]:
        _stat_cards(canvas, plan["stats"], PAD, max(y + 30, 620), W - 2 * PAD, prof)
    _footer(canvas, prof)
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
        "bg_variant": int(plan.get("bg_variant", 0)),
        "profile": plan.get("profile", designs.DEFAULT_PROFILE),
        "profile_name": plan.get("profile_name", ""),
    }


# --------------------------------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------------------------------
async def build_chat_post(brand: Brand | None, concept: str, count: int = 1, style: str | None = None,
                          person_photo: bytes | None = None, person_name: str = "",
                          headline: str = "", subtext: str = "", person_role: str = "",
                          bg_variant: int | None = None,
                          profile: str | None = None, owner: str = ""
                          ) -> list[tuple[str, str, dict]]:
    """Render `count` Talentrupt-brand Chat posts for `concept`. If `person_photo` is given, the real
    person is composited AS-IS. A person request mentioning 'mission' uses the 'Man on a Mission' spotlight
    template; otherwise a hero. When `headline` is supplied the copy is used verbatim (no LLM planning).

    A DESIGN PROFILE (palette + typography + layout + motif) is auto-rotated per owner (never repeats the
    last used) so consecutive posts look designed, not stamped; `profile` forces a specific one (refine)."""
    count = max(1, min(count, 3))
    person = _prep_person(person_photo) if person_photo else None
    tagline = (brand.tagline if brand and brand.tagline else "RPO Done Right")
    if headline.strip():   # explicit copy (person feature) -> one post, no LLM planning
        cl = (headline + " " + (concept or "")).lower()
        if person is not None and "mission" in cl:
            lead = "Woman" if re.search(r"\bwom[ae]n\b", cl) else "Man"
            # The question is CURATED meaningful copy — never the user's raw instruction. Only honour a
            # caller-supplied subtext when it's a genuine sentence (has spaces, no styling/deliverable words).
            st = (subtext or "").strip()
            good_sub = (len(st.split()) >= 4 and not re.search(
                r"\b(style|styles|look|version|background|scene|theme|design|layout|variation|post|image|"
                r"different|warmer|brighter|colou?r|colou?rs)\b", st, re.I))
            question = st if good_sub else _mission_question(person_name, int(bg_variant or 0))
            plans = [{"template": "mission", "lead": lead, "mission_word": "Mission!", "bg": "navy",
                      "bg_variant": int(bg_variant or 0) % MISSION_BG_COUNT,
                      "person_name": person_name, "person_role": person_role, "subtext": question}]
        else:
            kicker = (person_name.strip().upper()[:26] if person_name else "")
            # Edit path passes a variant -> alternate navy/cream deterministically so 'change the
            # background' visibly flips; first generation (variant None) stays random for variety.
            hero_bg = (["navy", "cream"][int(bg_variant) % 2] if bg_variant is not None
                       else random.choice(["navy", "cream"]))
            # A real subline, never a stray instruction fragment. Pass the full concept so `_coerce` /
            # `_meaningful_copy` can theme-detect and replace a weak/echoed headline with real copy.
            hero_sub = subtext if _good_subtext(subtext) else _meaningful_copy(concept or headline)[1]
            plans = [_coerce({"template": "hero", "headline": headline, "subtext": hero_sub, "kicker": kicker,
                              "bg": hero_bg}, (concept or headline), tagline, has_person=person is not None)]
    else:
        plans = await _plan(brand, concept, count, has_person=person is not None)
    # Resolve the design profile: an explicit key (refine "different style") wins; otherwise auto-rotate
    # per owner. With multiple variations, give each a FRESH profile so the batch itself looks varied.
    base_prof = designs.resolve_profile(profile) or designs.pick_profile(owner, "post")
    out: list[tuple[str, str, dict]] = []
    for idx, p in enumerate(plans):
        prof = base_prof if (idx == 0 or profile) else designs.pick_profile(owner, "post")
        p["profile"] = prof.key
        p["profile_name"] = prof.name
        try:
            bg = await _ai_scene(p["scene"]) if (p["template"] == "observance") else None
            canvas = _render(p, bg, person, prof)
            out.append(_save(canvas, p))
        except Exception as e:
            log.warning("chatpost render failed: %s", e)
            continue
    return out
