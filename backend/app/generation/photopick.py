"""Pick the employee photo that best FITS a post request, and vision-tag photos so it can.

When a person has several photos, a feature should use the one that suits what the user asked for — a
formal shot for a formal/announcement post, a casual/festive shot for a celebration, a confident pose for
an "on a mission" post. Each photo is vision-tagged ONCE (attire / expression / setting / framing / a short
caption) and cached; selection is then a deterministic keyword + intent score, so generation needs no extra
LLM call. The face is NEVER altered — this only chooses WHICH real photo to feature.
"""
from __future__ import annotations

import base64
import io
import json
import random
import re

from ..providers import llm

_ANALYSIS_PROMPT = (
    "You are tagging a REAL photo of ONE person for a marketing photo library. Describe ONLY what is "
    "visibly true — do NOT identify, name, or guess who the person is. Reply ONLY as JSON with these keys:\n"
    '{"attire": one of "formal","business_casual","casual","branded_tshirt","traditional","other";\n'
    ' "expression": one of "smiling","neutral","serious","confident";\n'
    ' "setting": one of "studio","office","outdoor","event","home","other";\n'
    ' "framing": one of "headshot","half_body","full_body";\n'
    ' "caption": a short factual description (<= 16 words) of clothing / pose / mood, NO name}'
)

_ATTIRE = {"formal", "business_casual", "casual", "branded_tshirt", "traditional", "other"}
_EXPR = {"smiling", "neutral", "serious", "confident"}
_SETTING = {"studio", "office", "outdoor", "event", "home", "other"}
_FRAMING = {"headshot", "half_body", "full_body"}


def _jpeg(data: bytes, side: int = 512) -> bytes:
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(io.BytesIO(data)).convert("RGB"))
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def _parse(raw: str) -> dict:
    m = re.search(r"\{.*\}", raw or "", re.S)
    try:
        d = json.loads(m.group()) if m else {}
    except Exception:
        d = {}
    if not isinstance(d, dict):
        return {}

    def pick(key, allowed):
        v = str(d.get(key, "")).strip().lower().replace("-", "_").replace(" ", "_")
        return v if v in allowed else ""

    return {
        "attire": pick("attire", _ATTIRE),
        "expression": pick("expression", _EXPR),
        "setting": pick("setting", _SETTING),
        "framing": pick("framing", _FRAMING),
        "caption": str(d.get("caption", "")).strip()[:200],
    }


async def analyze_photo_bytes(data: bytes) -> dict:
    """Vision-tag one photo. Returns {} on any failure / no provider (caller falls back to random)."""
    if not data or not llm.provider_available():
        return {}
    try:
        b64 = base64.b64encode(_jpeg(data)).decode()
        raw = await llm.vision_caption(b64, _ANALYSIS_PROMPT)
        return _parse(raw)
    except Exception:
        return {}


# --- selection scoring ----------------------------------------------------------------------------
# (request keywords) -> (preferred attire set, preferred expression set)
_INTENTS = [
    (("formal", "professional", "corporate", "announcement", "business", "executive", "official",
      "webinar", "conference", "linkedin", "hiring", "recruit", "client"),
     {"formal", "business_casual"}, {"confident", "serious", "neutral"}),
    (("mission", "confident", "bold", "driven", "champion", "strong", "leader", "leadership", "winning",
      "hustle", "achiever", "achievement", "power", "unstoppable", "grind"),
     {"formal", "business_casual", "branded_tshirt"}, {"confident", "serious"}),
    (("welcome", "onboard", "onboarding", "thank", "congrat", "happy", "smile", "warm", "joined",
      "joining", "birthday", "anniversary", "celebrate", "celebrating"),
     set(), {"smiling"}),
    (("casual", "fun", "festival", "festive", "diwali", "holi", "navratri", "eid", "pongal", "onam",
      "christmas", "party", "team", "friendly", "holiday", "fest", "outing", "culture"),
     {"casual", "branded_tshirt", "traditional"}, {"smiling", "neutral"}),
    (("sport", "sports", "cricket", "football", "match", "game", "fitness", "active", "tournament",
      "championship", "run", "marathon", "gym"),
     {"casual", "branded_tshirt"}, set()),
    (("traditional", "ethnic", "cultural", "saree", "kurta"),
     {"traditional"}, set()),
]


def _score(analysis: dict, req_tokens: set, req_lower: str) -> float:
    a = analysis or {}
    doc = " ".join(str(a.get(k, "")) for k in ("caption", "attire", "expression", "setting", "framing")).lower()
    doc_tokens = set(re.findall(r"[a-z]+", doc))
    score = 1.0 * len(req_tokens & doc_tokens)  # plain keyword overlap on the caption/tags
    for kws, attires, exprs in _INTENTS:
        if any(k in req_lower for k in kws):
            if attires and a.get("attire") in attires:
                score += 3.0
            if exprs and a.get("expression") in exprs:
                score += 2.0
    return score


def pick_index(analyses: list[dict], request_text: str) -> int:
    """Index of the photo whose tags best fit `request_text`. Random among un-decidable/empty cases so a
    person with no tags (or a vague request) still varies across posts."""
    n = len(analyses)
    if n == 0:
        return 0
    have = [i for i, a in enumerate(analyses) if a]
    req = (request_text or "").strip()
    if not req or not have:
        return random.randrange(n)
    toks = {w for w in re.findall(r"[a-z]+", req.lower()) if len(w) > 2}
    rl = req.lower()
    scored = [(_score(analyses[i], toks, rl), i) for i in range(n)]
    top = max(s for s, _ in scored)
    if top <= 0:                                   # nothing matched -> vary across the tagged photos
        return random.choice(have)
    best = [i for s, i in scored if s == top]
    return random.choice(best)
