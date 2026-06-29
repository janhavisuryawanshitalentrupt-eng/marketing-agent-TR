"""Talentrupt-branded campaign image compositor (deterministic render, AI-planned content).

Content (headline, layout, optional metric, steps, comparison) is planned by the LLM
from the *actual topic* — so a data-driven or holiday post never inherits a healthcare
metric. Multiple distinct variations can be produced in one call. Rendering stays
deterministic in the brand system (navy/red/cream, TR lockup, red rail).
"""
from __future__ import annotations

import asyncio
import io
import re
import zipfile

from PIL import Image, ImageDraw

from ..brand.brand_kit import CREAM, NAVY, RED, WHITE
from ..config import settings
from ..knowledge import retrieve
from ..models import Brand, Campaign
from ..providers import llm
from .common import (
    body_font,
    composite_logo_bytes,
    heading_font,
    hex_to_rgb,
    paste_logo,
    public_url,
    storage_subdir,
    unique_name,
)

W = H = 1200
NAVY_RGB = hex_to_rgb(NAVY)
RED_RGB = hex_to_rgb(RED)
CREAM_RGB = hex_to_rgb(CREAM)
WHITE_RGB = hex_to_rgb(WHITE)

LAYOUTS = {"metric", "statement", "steps", "comparison"}
STYLES = {"photographic", "decorative", "infographic", "ui_mockup", "typographic", "editorial_collage"}
RICH_STYLES = {"photographic", "decorative", "ui_mockup", "infographic", "editorial_collage"}
# Diverse style rotation used to spread MULTIPLE variations across genuinely different looks (so 3
# "options" aren't three near-identical collages). Ordered most-distinct-first.
_VARIETY = ["photographic", "infographic", "editorial_collage", "typographic", "decorative", "ui_mockup"]


def _wrap(draw, text, font, max_width):
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# --- Content planning -----------------------------------------------------
async def _plan(brand: Brand | None, concept: str, count: int, context: str = "",
                force_style: str | None = None, brief: str = "") -> list[dict]:
    proof = ", ".join(brand.proof_points) if brand and brand.proof_points else ""
    # Per-variation style: an explicit user choice applies to all; for MULTIPLE options with no chosen
    # style, spread DISTINCT styles so the variations look genuinely different (not the same archetype);
    # a single image (count==1, no choice) lets the planner pick the best fit (None).
    if force_style in STYLES:
        assigned = [force_style] * count
    elif count > 1:
        assigned = [_VARIETY[i % len(_VARIETY)] for i in range(count)]
    else:
        assigned = [None]
    if llm.provider_available():
        ident = (
            (
                "You are an art director for a TALENTRUPT INTERNAL CAMPAIGN. Talentrupt's brand look is "
                "navy/red/cream, modern and premium. THIS content is for the campaign brief below — the "
                "headline, subtext, subject and visual MUST be about THAT theme. Do NOT use 'RPO Done "
                "Right', recruiting / offshore-staffing copy, or any recruiting metric UNLESS the brief "
                f"is itself about recruiting.\nCAMPAIGN BRIEF (authoritative topic): {brief[:700]}\n\n"
            )
            if brief else
            "You are an art director for Talentrupt (offshore RPO, 'RPO Done Right'; navy/red/cream brand). "
        )
        sys = (
            ident
            + "Return ONLY JSON: {\"variations\": [...]} with EXACTLY "
            f"{count} variation(s). Each variation object:\n"
            '- "layout": one of "metric","statement","steps","comparison"\n'
            '- "style": one of "photographic" (a cinematic real-world photo hero), '
            '"editorial_collage" (a cut-out-subject magazine collage on textured cream paper), '
            '"decorative" (flat-vector illustration with brand shapes), "infographic" (navy hero '
            'silhouette + a stat-card row), "ui_mockup" (a browser/app screen holding stat cards), '
            '"typographic" (atmospheric photo + elegant condensed type)\n'
            '- "composition": one of "full_bleed_photo","split_panel","centered_type","grid",'
            '"cards","collage" — the overall arrangement\n'
            '- "bg": "navy" or "cream"\n'
            '- "headline": <= 10 words, punchy, matches the topic\n'
            '- "subtext": one short supporting line (<= 14 words)\n'
            '- "metric": a number/percent string for layout "metric" ONLY, and ONLY if a real '
            "proven Talentrupt number genuinely fits the topic; otherwise null\n"
            '- "metric_label": short label for that metric, else null\n'
            '- "points": array of 3-4 short strings for layout "steps", else []\n'
            '- "left"/"right": {"label","text"} for layout "comparison", else null\n'
            '- "cta": short call to action\n'
            "ART-DIRECTION RULES: Choose the style AND composition that genuinely best fit THIS "
            "specific topic — be visually inventive and vary scenes, framing, and layout. Talentrupt's "
            "quality bar is FIVE distinct archetypes; map the topic to the one that fits:\n"
            "1. ATMOSPHERIC PHOTO HERO — for calm, premium, emotionally resonant topics (a value, a "
            "relationship, a milestone, a holiday, a reflective statement): style 'photographic' with "
            "composition 'full_bleed_photo'. A cinematic real-world photo, subtle navy/cream/coral "
            "grade, wide calm negative space for the headline.\n"
            "2. ATMOSPHERIC PHOTO + ELEGANT TYPE — for poetic/atmospheric one-line ideas: style "
            "'typographic' with 'full_bleed_photo' or 'centered_type'. Full-bleed evocative scene + "
            "ELEGANT THIN CONDENSED ALL-CAPS headline (one word oversized), NOT bold geometric sans.\n"
            "3. CUT-OUT-SUBJECT COLLAGE — for people/editorial topics (recruiter truths, myths, "
            "day-in-the-life, candidate experience, hiring tips, culture, 'things they don't tell "
            "you'): style 'editorial_collage' with composition 'collage'. One cut-out person on "
            "textured cream paper, ringed by floating topic objects/icons, coral arc/squiggle/"
            "dotted-grid accents, NAVY headline carrying exactly ONE coral word + a navy subtext pill.\n"
            "4. STAT-CARD INFOGRAPHIC — for data/proof topics: style 'infographic' with 'cards' (or "
            "'grid'). A big navy flat-vector silhouette hero + a row of 2-3 navy/coral STAT CARDS (big "
            "number + short label) on white/cream, optional slim coral proof banner.\n"
            "5. ILLUSTRATION + BROWSER-MOCKUP DATA — for product/process/pipeline data: style "
            "'ui_mockup' with 'split_panel' or 'cards'. A realistic browser-window or app screen "
            "holding that same row of stat cards.\n"
            "Use 'decorative' for object- or concept-led illustrated collages with NO single human "
            "subject. Keep accent motifs SPARSE (corners and behind the subject) — they are accents, "
            "never a full-color background wash. PREFER a striking photographic, atmospheric, or "
            "editorial hero for most topics (they read most premium and on-brand). METRIC GATING: use "
            "the 'infographic'/'ui_mockup' stat-card archetypes (and ANY metric) ONLY for topics "
            "genuinely about Talentrupt's data/proof/performance; the metric MUST be copied VERBATIM "
            "from Talentrupt's supplied proof points — NEVER an industry, market, or topical statistic "
            "(e.g. a sector's projected growth %), and NEVER a number you estimate. For culture, "
            "holiday, wellness, values, seasonal, or motivational topics, choose 'photographic', "
            "'typographic', or 'editorial_collage' and set metric/metric_label to null — do NOT attach "
            "any statistic. If no real Talentrupt number genuinely fits, set metric/metric_label to "
            "null and render any screen/cards with believable but NON-numeric UI instead. NEVER invent "
            "or estimate a statistic to fill a card. Do NOT default to a 'hand holding a card/phone' "
            "image or a plain cream card with a navy heading. Match the topic; NEVER force healthcare/"
            "recruiting metrics onto unrelated topics (holidays, culture); do NOT invent statistics.\n"
            + (f"Real Talentrupt proof points (use only if relevant): {proof}\n" if (proof and not brief) else "")
            + (f"\n{context}\n" if context else "")
        )
        diversity = ""
        if count > 1 and force_style in STYLES:
            diversity = (f"\nProduce EXACTLY {count} variations ALL in the '{force_style}' style, but each "
                         "a DISTINCT concept — different scene, subject, framing, layout and bg. They must "
                         "look like different options, never the same image reworded.")
        elif count > 1:
            spread = "; ".join(f"variation {i + 1} = {s}" for i, s in enumerate(assigned))
            diversity = (f"\nProduce EXACTLY {count} variations that are VISUALLY DISTINCT from each other. "
                         f"Use these styles IN ORDER: {spread}. Give each a different scene, composition, "
                         "framing and bg, and write its content to suit its style. They must look like "
                         "genuinely different options to choose from — NOT the same image reworded.")
        usr = (
            (f"Campaign theme (what every variation must be about): {brief[:700]}\n" if brief else "")
            + f"Topic/concept: {concept}\nProduce {count} variation(s).{diversity}"
        )
        try:
            data = await llm.chat_json(
                [{"role": "system", "content": sys}, {"role": "user", "content": usr}]
            )
            variations = data.get("variations") if isinstance(data, dict) else None
            if variations:
                vs = variations[:count]
                # Force each variation to its assigned style so the spread is GUARANTEED (the model
                # otherwise tends to collapse multiple options into one favored archetype).
                return [_coerce(v, concept, brand, force_style=assigned[i]) for i, v in enumerate(vs)]
        except Exception:
            pass  # transient provider/parse error -> degrade to the deterministic fallback below

    # Fallback: distinct styles + alternating bg so multiple options still differ (no fabricated metric).
    # Brief-aware fallback: a campaign image must never fall back to the RPO tagline.
    fb_sub = "" if brief else (brand.tagline if brand else "RPO Done Right")
    return [
        _coerce(
            {"layout": "statement", "bg": "navy" if i % 2 == 0 else "cream",
             "headline": concept, "subtext": fb_sub},
            concept, brand, force_style=assigned[i],
        )
        for i in range(count)
    ]


def _metric_is_real(metric, brand: Brand | None) -> bool:
    """Anti-fabrication backstop: a rendered statistic must echo a REAL Talentrupt proof point.
    The planner is instructed to only use real numbers, but this guarantees it deterministically —
    any number not present in the brand's proof points (e.g. an industry/market stat) is rejected.
    Matches on WHOLE numbers (separators normalized) so a fabricated '5%' can't slip through just
    because '5' is a substring of '500'/'95'."""
    proof = " ".join(brand.proof_points) if brand and brand.proof_points else ""
    if not proof:
        return False
    def _nums(s: str) -> set[str]:
        # whole numeric tokens, commas stripped so '1,000' and '1000' compare equal
        return {t.replace(",", "") for t in re.findall(r"\d[\d,]*", str(s or ""))}
    cand = _nums(metric)
    return bool(cand) and bool(cand & _nums(proof))


_NONCOMMERCIAL_RE = re.compile(
    r"\b(yoga|diwali|deepavali|holi|navratri|dussehra|dasara|raksha|rakhi|eid|ramadan|ramzan|"
    r"christmas|xmas|hanukkah|kwanzaa|new year|thanksgiving|halloween|valentine|women'?s day|"
    r"men'?s day|mother'?s day|father'?s day|independence day|republic day|labou?r day|"
    r"veterans? day|earth day|pride month|festival|holiday|season'?s greetings|wellness|"
    r"mindfulness|meditation|gratitude|celebrat|anniversary|birthday|condolence|tribute)\b",
    re.I,
)


def _is_noncommercial_topic(concept: str) -> bool:
    """Culture/holiday/wellness/seasonal posts must never carry a recruiting stat — they take an
    atmospheric/editorial treatment (like Talentrupt's real yoga/holiday posts), not a stat card."""
    return bool(_NONCOMMERCIAL_RE.search(concept or ""))


def _coerce(v: dict, concept: str, brand: Brand | None, force_style: str | None = None) -> dict:
    layout = v.get("layout") if v.get("layout") in LAYOUTS else "statement"
    # An explicit, valid user-chosen style wins; else use the planner's pick (default photographic).
    style = force_style if force_style in STYLES else (v.get("style") if v.get("style") in STYLES else "photographic")
    metric = v.get("metric") if layout == "metric" else None
    metric_label = v.get("metric_label") if layout == "metric" else None
    # Never render a number that isn't a real Talentrupt proof point — drop it and fall back to a
    # clean statement layout (mirrors the app-wide no-fabrication contract).
    if metric and not _metric_is_real(metric, brand):
        metric, metric_label, layout = None, None, "statement"
    # Culture/holiday/wellness topics: never a stat card; route a data style to an atmospheric poster.
    if _is_noncommercial_topic(concept):
        metric = metric_label = None
        if layout == "metric":
            layout = "statement"
        if style in ("infographic", "ui_mockup"):
            style = "typographic"
    return {
        "layout": layout,
        "style": style,
        "composition": v.get("composition", ""),
        "bg": "cream" if v.get("bg") == "cream" else "navy",
        "headline": (v.get("headline") or concept or "RPO Done Right").strip(),
        "subtext": (v.get("subtext") or (brand.tagline if brand else "RPO Done Right")).strip(),
        "metric": metric,
        "metric_label": metric_label,
        "points": (v.get("points") or [])[:4] if layout == "steps" else [],
        "left": v.get("left") if layout == "comparison" else None,
        "right": v.get("right") if layout == "comparison" else None,
        "cta": (v.get("cta") or "See Talentrupt in action  →").strip(),
    }


# --- Rendering ------------------------------------------------------------
def _palette(bg: str):
    if bg == "cream":
        return CREAM_RGB, NAVY_RGB, NAVY_RGB, CREAM_RGB  # bg, primary, card, card_text
    return NAVY_RGB, WHITE_RGB, CREAM_RGB, NAVY_RGB


def _lockup(img, d, bg: str, primary):
    # Real brand logo tile (navy TR in a red square); drawn badge only as a fallback.
    if not paste_logo(img, 80, 72, 100):
        badge = CREAM_RGB if bg == "navy" else NAVY_RGB
        d.rounded_rectangle([80, 78, 172, 170], radius=18, fill=badge)
        d.text((102, 92), "TR", font=heading_font(50), fill=RED_RGB)
    d.text((196, 90), "TALENTRUPT", font=heading_font(28), fill=primary)
    d.text((198, 126), "RPO Done Right", font=body_font(20), fill=primary)


def _render(content: dict) -> tuple[str, str, dict]:
    bg, primary, card, card_text = _palette(content["bg"])
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 24, H], fill=RED_RGB)
    _lockup(img, d, content["bg"], primary)

    layout = content["layout"]
    if layout == "steps":
        _render_steps(d, content, primary, card, card_text)
    elif layout == "comparison":
        _render_comparison(d, content, primary, card, card_text)
    elif layout == "metric" and content.get("metric"):
        _render_metric(d, content, primary, card, card_text)
    else:
        _render_statement(d, content, primary)

    # CTA footer
    d.text((84, H - 96), content["cta"], font=heading_font(32), fill=primary)

    file_name = unique_name("tr-image", "png")
    path = storage_subdir("images") / file_name
    img.save(path, "PNG")
    return str(path), file_name, {
        "url": public_url("images", file_name), "layout": layout,
        "renderer": "brand_compositor", "size": f"{W}x{H}",
    }


def _headline(d, text, primary, top=270, size=72, max_lines=4):
    f = heading_font(size)
    lines = _wrap(d, text, f, W - 200)[:max_lines]
    y = top
    for ln in lines:
        d.text((84, y), ln, font=f, fill=primary)
        y += int(size * 1.18)
    d.rectangle([86, y + 8, 320, y + 20], fill=RED_RGB)
    return y + 40


def _render_statement(d, c, primary):
    y = _headline(d, c["headline"], primary, top=300, size=84, max_lines=4)
    for ln in _wrap(d, c["subtext"], body_font(36), W - 220)[:3]:
        d.text((86, y), ln, font=body_font(36), fill=primary)
        y += 50


def _render_metric(d, c, primary, card, card_text):
    _headline(d, c["headline"], primary, top=250, size=64, max_lines=3)
    top = 770
    d.rounded_rectangle([80, top, W - 80, H - 150], radius=28, fill=card)
    # The model sometimes puts a whole phrase in `metric`; show just the headline number and
    # shrink it to fit the column before the label — so it never overflows or collides.
    metric = " ".join(str(c.get("metric", "") or "").split())
    m = re.match(r"[~<>$€£]?\d[\d,.]*\s*(?:%|\+|x|×|k|m|b|bn|hrs?|days?|hours?)*\+?", metric, re.I)
    if m and m.group().strip():
        metric = m.group().strip()
    size = 104
    while size > 40 and d.textlength(metric, font=heading_font(size)) > 320:
        size -= 8
    d.text((116, top + 36), metric, font=heading_font(size), fill=RED_RGB)
    label = c.get("metric_label") or c["subtext"]
    for i, ln in enumerate(_wrap(d, label, body_font(34), W - 470)[:3]):
        d.text((460, top + 70 + i * 44), ln, font=body_font(34), fill=card_text)


def _render_steps(d, c, primary, card, card_text):
    _headline(d, c["headline"], primary, top=250, size=58, max_lines=2)
    points = c["points"] or [c["subtext"]]
    y = 520
    gap = min(150, int((H - 180 - y) / max(1, len(points))))
    for i, p in enumerate(points[:4], 1):
        d.rounded_rectangle([80, y, W - 80, y + gap - 18], radius=20, fill=card)
        d.ellipse([104, y + 22, 104 + 56, y + 22 + 56], fill=RED_RGB)
        d.text((118, y + 28), str(i), font=heading_font(40), fill=WHITE_RGB)
        for j, ln in enumerate(_wrap(d, p, body_font(30), W - 320)[:2]):
            d.text((196, y + 26 + j * 38), ln, font=body_font(30), fill=card_text)
        y += gap


def _render_comparison(d, c, primary, card, card_text):
    _headline(d, c["headline"], primary, top=250, size=56, max_lines=2)
    left = c.get("left") or {"label": "Myth", "text": c["subtext"]}
    right = c.get("right") or {"label": "Truth", "text": c["cta"]}
    top, bot = 500, H - 150
    mid = W // 2
    # Left panel
    d.rounded_rectangle([80, top, mid - 14, bot], radius=22, fill=card)
    d.text((110, top + 28), str(left.get("label", "")), font=heading_font(40), fill=RED_RGB)
    for j, ln in enumerate(_wrap(d, left.get("text", ""), body_font(28), mid - 200)[:6]):
        d.text((110, top + 100 + j * 40), ln, font=body_font(28), fill=card_text)
    # Right panel
    d.rounded_rectangle([mid + 14, top, W - 80, bot], radius=22, fill=card)
    d.text((mid + 44, top + 28), str(right.get("label", "")), font=heading_font(40), fill=RED_RGB)
    for j, ln in enumerate(_wrap(d, right.get("text", ""), body_font(28), mid - 200)[:6]):
        d.text((mid + 44, top + 100 + j * 40), ln, font=body_font(28), fill=card_text)


# --- gpt-image-1 (rich, illustrative, reference-grounded) -----------------
_LAYOUT_DIRECTION = {
    "metric": "Make ONE large statistic the hero element with a short supporting label.",
    "steps": "A numbered step/process infographic (3-4 steps) with simple icons or badges.",
    "comparison": "A two-column comparison layout (e.g. left vs right, myth vs truth).",
    "statement": "The headline is the hero; minimal supporting elements.",
}
_STYLE_DIRECTION = {
    "photographic": "A full-bleed, magazine-grade PHOTOGRAPH as the hero — choose ONE quietly "
    "cinematic real-world moment that genuinely fits the topic (e.g. two diverse hands meeting in a "
    "warm handshake on a soft neutral studio backdrop; a candidate and recruiter mid-conversation; a "
    "single confident professional by a sunlit window; a diverse team collaborating). Shoot it like an "
    "editorial cover: shallow depth of field, soft directional natural light, and generous CALM "
    "NEGATIVE SPACE on one side or the top for the headline. Apply a SUBTLE brand color grade — "
    "deep-navy cool in the shadows, faint warm-cream highlights, with at most one small coral-red "
    "accent occurring naturally in the scene (a lanyard, sticky note, sleeve) rather than a flat color "
    "wash. Do NOT use a hand holding a card/phone. Integrate the headline tastefully over the calm "
    "negative space, never crowding the subject; one small coral arc or squiggle accent in a corner is "
    "optional, kept minimal so the photo leads.",
    "editorial_collage": "A magazine-style EDITORIAL COLLAGE on a textured warm-cream (#EBE9DF) paper "
    "background with subtle grain/fiber tooth. A single full-color CUT-OUT photo of one real, relatable "
    "professional (clean cut-out edge with a faint paper drop-shadow; arms crossed, mid-laugh, or "
    "gesturing) anchors the frame, RINGED by 6-10 neatly floating everyday work objects and app-style "
    "icon tiles relevant to the topic (laptop, headphones, smartphone, notebook, coffee tumbler, "
    "glasses, a document with a small coral check or red error badge), each at varied sizes/angles "
    "casting a soft shadow like scattered stickers. BEHIND and around the subject, hand-drawn CORAL-RED "
    "(#F6404C) accent motifs — concentric line arcs/half-circles, a loose squiggle, an 8-point "
    "starburst, a small dotted grid — tucked into corners as sparse accents, never a full color wash. "
    "Bold modern geometric NAVY (#0B3559) headline with exactly ONE word flipped to coral red, plus a "
    "solid navy rounded subtext PILL holding a single white line. Confident negative space, crisp "
    "focus, premium B2B finish.",
    "decorative": "A bold flat-vector ILLUSTRATION composition on textured cream (or navy) 'paper' — a "
    "navy/coral/cream scene that dramatizes the topic (people at desks, a spinning globe, flying "
    "envelopes, oversized props) or a hero object built from clean vector shapes. Anchor it with the "
    "signature accent motifs done large and confident: a coral-red 8-POINT STARBURST behind the focal "
    "point, hand-drawn navy SQUIGGLES, concentric line ARCS/half-circles, geometric blocks, and a "
    "DOTTED GRID drifting into a corner — scattered as ACCENTS, never a flat single-color wash. Use for "
    "object- or concept-led compositions with no single human subject. Layered, editorial, asymmetric, "
    "strong navy/coral/cream hierarchy with generous whitespace and a tactile finish.",
    "infographic": "A clean structured infographic on CRISP WHITE (or warm cream) with magazine-strength "
    "hierarchy. Build it around ONE flat-vector NAVY silhouette HERO illustration (a large object or "
    "scene that literally embodies the topic) with tiny coral-red and cream accent figures or props "
    "woven in. Below or beside the hero, place a single ROW OF 2-3 rounded STAT CARDS in deep navy and "
    "coral red, each holding one BIG number (only if a real one is supplied) plus a short label. "
    "Optional slim coral banner strip for a one-line proof statement. Scatter signature motifs sparingly "
    "in the margins — a coral 8-point starburst, a squiggle, a dotted grid, a half-circle line arc. "
    "Render ONLY numbers explicitly provided; invent NO statistics — if none fit, use non-numeric "
    "labels. Strong grid, generous whitespace, every element tack-sharp.",
    "ui_mockup": "A sleek, front-facing BROWSER-WINDOW or app mockup as the focal element on a textured "
    "off-white/cream or soft navy backdrop. Draw realistic window chrome (rounded top bar, three "
    "traffic-light dots, a simple address/tab bar) framing a clean recruiting-relevant dashboard. INSIDE "
    "the window, when real numbers are supplied, show a tidy horizontal ROW of 2-3 rounded STAT CARDS in "
    "navy + coral red, each a big number over a short label (e.g. candidates sourced, CVs delivered, in "
    "pipeline). Keep it flat-on or tilt subtly in 3/4 perspective, casting a soft drop shadow so it "
    "reads as a solid premium object. Surround it with light brand motifs — a coral starburst, a navy "
    "squiggle, scattered dots. If NO real metric is provided, fill the screen with believable UI "
    "(charts, lists, avatars) bearing NO fabricated numerals. Crisp, pixel-clean edges.",
    "typographic": "An ATMOSPHERIC PHOTO + TYPE poster: a full-bleed evocative photograph or painterly "
    "atmospheric scene that fits the topic (misty forest at dawn, a calm horizon, soft city light, a "
    "quiet textured landscape) carrying the whole frame, with one elegant THIN CONDENSED ALL-CAPS "
    "headline laid over it — one key word oversized as the focal type, the rest in a tight refined "
    "hierarchy. Let a hero silhouette or single subject sit low in the frame with a gentle warm golden "
    "glow; keep wide tranquil negative space (sky, mist, fog) above for the type and a short two-line "
    "caption at the very bottom. Grade subtly toward navy shadows and cream-warm light with at most one "
    "whisper of coral; no flat wash, no clutter. Tack-sharp, premium, contemplative.",
}
_COMPOSITION_DIRECTION = {
    "full_bleed_photo": "a full-bleed photographic/atmospheric hero filling the frame edge-to-edge, "
    "with the headline set over a deliberately calm zone of negative space (open sky, soft wall, "
    "blurred background); the subject sits off-center so the type never collides with it, and the "
    "bottom-right corner stays empty",
    "split_panel": "a split layout — a cut-out subject, photo, flat-vector illustration, or "
    "browser-window mockup on one side; the headline and a solid navy subtext pill (plus stat cards if "
    "real numbers exist) on the other — divided cleanly with optional coral accents along the seam",
    "centered_type": "a type-led poster with an oversized elegant thin condensed all-caps headline "
    "centered over generous tranquil whitespace or a quiet atmospheric photo backdrop; one word may "
    "dominate as the focal point, a short caption anchored low, refined restrained hierarchy throughout",
    "grid": "a clean grid of elements or icon tiles with strong alignment and even gutters; promote one "
    "tile or stat as the visual anchor",
    "cards": "a clean horizontal row of 2-3 solid, fully-opaque rounded navy/coral STAT CARDS, each a "
    "big number above a short label, with generous spacing and aligned baselines, set off by one or two "
    "coral accent motifs — populated ONLY with real supplied numbers",
    "collage": "an editorial cut-out collage on textured cream paper — a single cut-out subject (a "
    "person, or a hero object) ringed by a handful of neatly floating topic-relevant objects/icon tiles "
    "at varied sizes and angles, each with a soft shadow, plus sparse coral arc/squiggle/starburst/"
    "dotted-grid accents in the corners and behind the subject; navy headline with one coral word "
    "beside a solid navy subtext pill, with deliberate negative space",
}


def _openai_prompt(plan: dict, concept: str, context: str, has_refs: bool, brief: str = "") -> str:
    metric_line = f'Feature this statistic prominently: "{plan["metric"]}" ({plan.get("metric_label") or ""}).' if plan.get("metric") else ""
    extra = "Steps to show: " + "; ".join(plan["points"]) + "." if (plan["layout"] == "steps" and plan.get("points")) else ""
    comp = _COMPOSITION_DIRECTION.get(plan.get("composition", ""), _LAYOUT_DIRECTION.get(plan["layout"], _LAYOUT_DIRECTION["statement"]))
    ref_line = (
        "Attached image(s) are Talentrupt's OWN past posts. Study them closely to ABSORB the brand's "
        "craft — its warm-cream paper texture, the subtle navy/cream/coral color grading, the "
        "hand-drawn coral accent motifs (arcs, squiggles, starbursts, dotted grids), the elegant type "
        "treatments (bold geometric navy with one coral word, or elegant thin condensed all-caps), the "
        "cut-out-subject finish, and the overall compositional RICHNESS and polish (layered depth, "
        "confident motif placement, calm negative space, magazine-grade hierarchy). MATCH that level of "
        "craft and brand feel and quality bar. But create a fully ORIGINAL composition with a DIFFERENT "
        "subject, scene, object set, layout, and text; do NOT copy, trace, or echo their arrangement, "
        "framing, props, or wording. Reach their finish, invent your own picture.\n"
        if has_refs else ""
    )
    if brief:
        subject_line = (
            "A polished, premium SQUARE (1:1) social-media marketing graphic for a TALENTRUPT INTERNAL "
            "CAMPAIGN. THE SUBJECT of this graphic is the campaign described below — depict ONLY that. "
            "It is NOT about RPO / recruitment / offshore staffing, and must NOT show the tagline 'RPO "
            "Done Right' or any recruiting copy, metrics, or messaging UNLESS the campaign brief itself "
            "is about recruiting. Stay strictly on the campaign's theme.\n"
            f"CAMPAIGN BRIEF (authoritative — the image MUST be about this): {brief[:700]}\n\n"
        )
    else:
        subject_line = (
            "A polished, premium SQUARE (1:1) social-media marketing graphic for Talentrupt, an "
            "offshore RPO (recruitment process outsourcing) company; tagline 'RPO Done Right'.\n\n"
        )
    return (
        subject_line
        + ref_line
        + "BRAND SYSTEM — follow precisely:\n"
        "- Colors: deep navy #0B3559, coral red #F6404C (accent), warm cream #EBE9DF, white.\n"
        "- Typography: bold modern geometric sans-serif headings, strong hierarchy.\n"
        "- BRAND MOTIFS: Where it suits the style, weave in Talentrupt's signature ACCENT MOTIFS in "
        "coral red (and sometimes navy) — a hand-drawn 8-POINT STARBURST behind or beside the focal "
        "element, loose hand-drawn SQUIGGLES, a faint DOTTED GRID, and CONCENTRIC LINE ARCS / "
        "half-circles drifting into the corners — over a textured warm-cream 'paper' background for "
        "collage, decorative, and infographic posts; for cut-out-subject collages give the single "
        "cut-out person a clean edge with a faint paper drop-shadow, surround them with neatly floating "
        "work objects/icon tiles at varied sizes each casting a soft shadow, and set the headline in "
        "bold geometric navy with exactly ONE word in coral red beside a solid navy rounded subtext "
        "pill. For data graphics, render stat figures as solid, fully-opaque rounded navy and coral-red "
        "CARDS, each one big number above a short label, aligned in a clean row. These motifs are "
        "SPARSE accents only (corners and behind the subject) and must NEVER become a flat full-color "
        "wash; for full-bleed photographic and atmospheric posters keep them minimal or absent so the "
        "photo and type stay clean.\n"
        "- CRITICAL: do NOT render the word 'Talentrupt', the tagline 'RPO Done Right', or ANY company "
        "name, wordmark, logo, monogram, or 'TR' mark ANYWHERE in the image — the official logo is "
        "overlaid afterward. Keep the BOTTOM-RIGHT corner (about the last 20% of the width AND height) "
        "COMPLETELY EMPTY — no headline, subtext, stat cards, numbers, subject or graphics there. Place "
        "any stat cards or text along the bottom-LEFT or center so nothing reaches the bottom-right "
        "corner. Premium B2B, magazine-quality finish.\n\n"
        f"VISUAL STYLE: {_STYLE_DIRECTION.get(plan.get('style', 'photographic'), _STYLE_DIRECTION['photographic'])}\n"
        f"COMPOSITION: {comp}\n"
        f'The ONLY text rendered in the image is the headline (spell EXACTLY): "{plan["headline"]}"'
        " plus the short supporting line / stat below. NO brand name, NO extra labels or captions.\n"
        f"Supporting line: {plan.get('subtext','')}\n{metric_line}\n{extra}\n"
        f"Topic: {concept}\n\n"
        + (f"Brand voice/themes to echo:\n{context}\n" if context else "")
        + "\nRENDER QUALITY: tack-sharp focus, high detail, crisp edges; professional editorial/studio "
        "photography quality; vivid yet brand-accurate color with strong contrast and clean lighting. "
        "Any panel or card behind text must be SOLID and fully opaque (never translucent). STRICTLY "
        "AVOID: blur, soft focus, low contrast, faded/washed-out tones, muddy gradients, haze, or noise.\n"
        + "Output one finished, high-end, photorealistic 1:1 graphic with crisp, correctly-spelled text."
    )


def _downscale_jpeg(data: bytes, max_side: int = 1024) -> bytes:
    im = Image.open(io.BytesIO(data))
    if im.mode != "RGB":
        im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=82)
    return buf.getvalue()


def _load_references(paths: list[str]) -> list[bytes]:
    if not paths:
        return []
    out = []
    try:
        zf = zipfile.ZipFile(settings.knowledge_zip_path)
    except Exception:
        return []
    for p in paths:
        try:
            out.append(_downscale_jpeg(zf.read(p)))
        except Exception:
            continue
    return out


async def _openai_image(
    plan: dict, concept: str, context: str, refs: list[bytes], brief: str = ""
) -> tuple[str, str, dict] | None:
    prompt = _openai_prompt(plan, concept, context, bool(refs), brief=brief)
    try:
        if refs:
            data = await llm.generate_image_edit(prompt, refs)
        else:
            data = await llm.generate_image_bytes(prompt)
    except Exception:
        return None
    data = composite_logo_bytes(data)  # stamp the real Talentrupt logo so it's always present & correct
    file_name = unique_name("tr-image", "png")
    path = storage_subdir("images") / file_name
    with open(path, "wb") as f:
        f.write(data)
    return str(path), file_name, {
        "url": public_url("images", file_name), "layout": plan["layout"],
        "style": plan.get("style"), "renderer": "openai_gpt_image_ref" if refs else "openai_gpt_image",
        "size": settings.openai_image_size,
    }


# --- Public API -----------------------------------------------------------
async def build_images(
    brand: Brand | None, campaign: Campaign | None, concept: str, count: int = 1,
    style: str | None = None, brief: str = "",
) -> list[tuple[str, str, dict]]:
    # HARD FACE GUARD (single chokepoint for every image path — generate/refine/campaign): if the
    # concept names a real Talentrupt person, render their REAL photo and NEVER reach gpt-image-1.
    from . import teampost
    guarded = teampost.render_if_person(brand, concept, count)
    if guarded is not None:
        return guarded
    count = max(1, min(count, 4))
    brief = (brief or "").strip()
    # CAMPAIGN images must be grounded in the campaign BRIEF — NOT Talentrupt's generic RPO corpus.
    # retrieve.brand_context/image_references pull from one shared RPO/holiday past-post library, so
    # for a non-RPO campaign (cricket, football) they bleed "RPO Done Right" taglines and cross-topic
    # imagery (cricket bats, an Independence-Day team shot) into the picture. With a brief present we
    # ground in the brief and skip that retrieval entirely; the brand look still comes from the prompt.
    context = "" if brief else await retrieve.brand_context(concept, k=3)
    # `style`, when set (e.g. an explicit Create-intake choice), forces the visual style.
    plans = await _plan(brand, concept, count, context, force_style=style, brief=brief)

    use_openai = llm.image_provider_available()
    results: list[tuple[str, str, dict]] = []

    if use_openai:
        # References only help the rich styles; they flatten clean infographic/typographic. NEVER attach
        # past-post images for a campaign image (they leak off-theme/RPO subjects).
        needs_refs = any(p.get("style") in RICH_STYLES for p in plans)
        refs = [] if brief else (_load_references(await retrieve.image_references(concept, n=3)) if needs_refs else [])

        async def one(p: dict):
            use_refs = refs if p.get("style") in RICH_STYLES else []
            res = await _openai_image(p, concept, context, use_refs, brief=brief)
            if res is None:  # API failed -> compositor fallback (never fake)
                try:
                    return _render(p)
                except Exception:
                    return None
            return res

        results = [r for r in await asyncio.gather(*[one(p) for p in plans]) if r]
    else:
        for p in plans:
            try:
                results.append(_render(p))
            except Exception:
                continue
    return results
