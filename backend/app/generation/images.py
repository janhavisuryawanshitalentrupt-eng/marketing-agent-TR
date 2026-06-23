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
STYLES = {"photographic", "decorative", "infographic", "ui_mockup", "typographic"}
RICH_STYLES = {"photographic", "decorative", "ui_mockup"}


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
async def _plan(brand: Brand | None, concept: str, count: int, context: str = "") -> list[dict]:
    proof = ", ".join(brand.proof_points) if brand and brand.proof_points else ""
    if llm.provider_available():
        sys = (
            "You are an art director for Talentrupt (offshore RPO, 'RPO Done Right'; "
            "navy/red/cream brand). Return ONLY JSON: {\"variations\": [...]} with EXACTLY "
            f"{count} variation(s). Each variation object:\n"
            '- "layout": one of "metric","statement","steps","comparison"\n'
            '- "style": one of "photographic" (a real-world photo hero), "decorative" (graphic '
            'shapes/illustration), "infographic" (icons/diagram), "ui_mockup" (an app/screen '
            'mockup), "typographic" (bold type poster)\n'
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
            "specific topic — be visually inventive. Do NOT default to a 'hand holding a card/phone' "
            "image or a cream card with a navy heading; vary scenes, framing, and layout. Match the "
            "topic; NEVER force healthcare/recruiting metrics onto unrelated topics (holidays, "
            "culture); do NOT invent statistics.\n"
            + (f"Real Talentrupt proof points (use only if relevant): {proof}\n" if proof else "")
            + (f"\n{context}\n" if context else "")
        )
        usr = f"Topic/concept: {concept}\nProduce {count} variation(s)."
        data = await llm.chat_json(
            [{"role": "system", "content": sys}, {"role": "user", "content": usr}]
        )
        variations = data.get("variations") if isinstance(data, dict) else None
        if variations:
            return [_coerce(v, concept, brand) for v in variations[:count]]

    # Fallback: a clean statement card (no fabricated/healthcare metric).
    return [
        _coerce(
            {"layout": "statement", "bg": "navy" if i % 2 == 0 else "cream",
             "headline": concept, "subtext": brand.tagline if brand else "RPO Done Right"},
            concept, brand,
        )
        for i in range(count)
    ]


def _coerce(v: dict, concept: str, brand: Brand | None) -> dict:
    layout = v.get("layout") if v.get("layout") in LAYOUTS else "statement"
    return {
        "layout": layout,
        "style": v.get("style") if v.get("style") in STYLES else "infographic",
        "composition": v.get("composition", ""),
        "bg": "cream" if v.get("bg") == "cream" else "navy",
        "headline": (v.get("headline") or concept or "RPO Done Right").strip(),
        "subtext": (v.get("subtext") or (brand.tagline if brand else "RPO Done Right")).strip(),
        "metric": v.get("metric") if layout == "metric" else None,
        "metric_label": v.get("metric_label") if layout == "metric" else None,
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
    "photographic": "A bright, real-world PHOTOGRAPH as the hero — pick a scene that genuinely fits "
    "the topic (e.g. a diverse team collaborating, a recruiter at a laptop, a candidate interview, "
    "a confident professional, an abstract modern workplace). Do NOT use a hand holding a card/phone. "
    "Integrate the headline tastefully over or beside the photo.",
    "decorative": "A bold graphic/illustration composition using brand shapes — navy line/wave "
    "motifs, a coral-red starburst, geometric blocks — arranged in a fresh, original way.",
    "infographic": "A structured infographic — icons, a clear diagram or simple chart, strong hierarchy.",
    "ui_mockup": "A sleek app/screen or dashboard mockup relevant to the topic as the focal element.",
    "typographic": "A bold typographic poster — oversized expressive headline, minimal supporting elements.",
}
_COMPOSITION_DIRECTION = {
    "full_bleed_photo": "full-bleed imagery with the text overlaid",
    "split_panel": "a split layout (image on one side, text on the other)",
    "centered_type": "centered, type-led with generous whitespace",
    "grid": "a clean grid of elements",
    "cards": "a small number of rounded cards",
    "collage": "an editorial collage of a few elements",
}


def _openai_prompt(plan: dict, concept: str, context: str, has_refs: bool) -> str:
    metric_line = f'Feature this statistic prominently: "{plan["metric"]}" ({plan.get("metric_label") or ""}).' if plan.get("metric") else ""
    extra = "Steps to show: " + "; ".join(plan["points"]) + "." if (plan["layout"] == "steps" and plan.get("points")) else ""
    comp = _COMPOSITION_DIRECTION.get(plan.get("composition", ""), _LAYOUT_DIRECTION.get(plan["layout"], _LAYOUT_DIRECTION["statement"]))
    ref_line = (
        "Attached image(s) are Talentrupt's OWN past posts — use them ONLY to match the brand "
        "palette, type treatment, and finish. Create an ORIGINAL composition that is clearly "
        "DIFFERENT from them; do NOT copy their layout, scene, or text.\n"
        if has_refs else ""
    )
    return (
        "A polished, premium SQUARE (1:1) social-media marketing graphic for Talentrupt, an "
        "offshore RPO (recruitment process outsourcing) company; tagline 'RPO Done Right'.\n\n"
        + ref_line
        + "BRAND SYSTEM — follow precisely:\n"
        "- Colors: deep navy #0B3559, coral red #F6404C (accent), warm cream #EBE9DF, white.\n"
        "- Typography: bold modern geometric sans-serif headings, strong hierarchy.\n"
        "- CRITICAL: do NOT render the word 'Talentrupt', the tagline 'RPO Done Right', or ANY company "
        "name, wordmark, logo, monogram, or 'TR' mark ANYWHERE in the image — the official logo is "
        "overlaid afterward. Keep the BOTTOM-RIGHT corner empty and uncluttered for it. Premium B2B, "
        "magazine-quality finish.\n\n"
        f"VISUAL STYLE: {_STYLE_DIRECTION.get(plan.get('style', 'infographic'), _STYLE_DIRECTION['infographic'])}\n"
        f"COMPOSITION: {comp}\n"
        f'The ONLY text rendered in the image is the headline (spell EXACTLY): "{plan["headline"]}"'
        " plus the short supporting line / stat below. NO brand name, NO extra labels or captions.\n"
        f"Supporting line: {plan.get('subtext','')}\n{metric_line}\n{extra}\n"
        f"Topic: {concept}\n\n"
        + (f"Brand voice/themes to echo:\n{context}\n" if context else "")
        + "\nOutput one finished, high-end 1:1 graphic with crisp, correctly-spelled text."
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
    plan: dict, concept: str, context: str, refs: list[bytes]
) -> tuple[str, str, dict] | None:
    prompt = _openai_prompt(plan, concept, context, bool(refs))
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
    brand: Brand | None, campaign: Campaign | None, concept: str, count: int = 1
) -> list[tuple[str, str, dict]]:
    count = max(1, min(count, 4))
    context = await retrieve.brand_context(concept, k=3)
    plans = await _plan(brand, concept, count, context)

    use_openai = llm.image_provider_available()
    results: list[tuple[str, str, dict]] = []

    if use_openai:
        # References only help the rich styles; they flatten clean infographic/typographic.
        needs_refs = any(p.get("style") in RICH_STYLES for p in plans)
        refs = _load_references(await retrieve.image_references(concept, n=3)) if needs_refs else []

        async def one(p: dict):
            use_refs = refs if p.get("style") in RICH_STYLES else []
            res = await _openai_image(p, concept, context, use_refs)
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
