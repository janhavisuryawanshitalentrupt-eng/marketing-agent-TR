"""Create-section structured intake.

When a Create request is vague, the agent shows a categorized creative BRIEF (chips + Other) instead
of asking free-text questions. This module:
  - interpret_create_intent(): triage a turn -> show a form / generate now / just answer.
  - build_form()/_categories(): the (mostly static) brief the frontend renders.
  - parse_brief_line() + brief_system_note(): turn a submitted "[brief] k=v; ..." line into a
    deterministic instruction the generation loop follows (so generation never re-surveys the user).

Gated to mode=='create' by the orchestrator; Chat never produces a form.
"""
from __future__ import annotations

from ..models import Brand
from ..providers import llm

# Design chips map to the REAL image style enum (generation/images.STYLES). Values must stay valid.
_DESIGN_OPTIONS = [
    {"label": "Photographic", "value": "photographic"},
    {"label": "Editorial collage", "value": "editorial_collage"},
    {"label": "Bold infographic", "value": "infographic"},
    {"label": "App / dashboard", "value": "ui_mockup"},
    {"label": "Bold type", "value": "typographic"},
    {"label": "Illustration", "value": "decorative"},
]


def _categories() -> list[dict]:
    """The creative-brief categories. Multi-select where the user benefits (requirement, audience)."""
    return [
        {"key": "format", "label": "Format", "select": "single", "allow_other": False, "options": [
            {"label": "Image", "value": "image"},
            {"label": "Deck (.pptx)", "value": "deck"},
            {"label": "PDF document", "value": "pdf"}]},
        {"key": "requirement", "label": "What should it do?", "select": "multi", "allow_other": True, "options": [
            {"label": "Showcase reliability", "value": "showcase reliability"},
            {"label": "Highlight a proven stat", "value": "highlight a proven stat"},
            {"label": "Tell a success story", "value": "tell a success story"},
            {"label": "Explain the offering", "value": "explain the offering"},
            {"label": "Drive a clear CTA", "value": "drive a clear call to action"}]},
        {"key": "design", "label": "Design / look (images)", "select": "single", "allow_other": True,
         "options": _DESIGN_OPTIONS},
        {"key": "goal", "label": "Goal", "select": "single", "allow_other": True, "options": [
            {"label": "Reach / awareness", "value": "reach and awareness"},
            {"label": "Engagement", "value": "engagement"},
            {"label": "Leads & meetings", "value": "leads and meetings"},
            {"label": "Brand credibility", "value": "brand credibility"},
            {"label": "Recruiting / employer brand", "value": "recruiting / employer brand"}]},
        {"key": "audience", "label": "Audience", "select": "multi", "allow_other": True, "options": [
            {"label": "Healthcare", "value": "healthcare"},
            {"label": "IT & Software", "value": "IT & software"},
            {"label": "Staffing agencies", "value": "staffing agencies"},
            {"label": "Finance & Fintech", "value": "finance & fintech"},
            {"label": "Corporate", "value": "corporate"}]},
        {"key": "count", "label": "How many options", "select": "single", "allow_other": False, "options": [
            {"label": "1", "value": "1"}, {"label": "2", "value": "2"}, {"label": "3", "value": "3"}]},
    ]


def build_form(topic: str) -> dict:
    return {"title": "Quick creative brief", "topic": (topic or "").strip()[:200], "categories": _categories()}


async def interpret_create_intent(brand: Brand | None, messages: list[dict]) -> dict:
    """Triage the latest Create turn. Returns {action:'form'|'generate'|'answer', form?, intro?}.
    Defaults to 'generate' on any uncertainty so generation is never blocked."""
    convo = [{"role": m["role"], "content": str(m.get("content", ""))}
             for m in messages if m.get("role") in ("user", "assistant")][-8:]
    last_user = next((m["content"] for m in reversed(convo) if m["role"] == "user"), "")
    sys = (
        "You triage requests in Talentrupt's Create studio (it produces images, decks, and PDFs). "
        "Choose ONE action for the LATEST user message:\n"
        "- 'form': a NEW asset request that is VAGUE/underspecified (e.g. 'make an image for our "
        "marketing', 'create something for LinkedIn', 'design a post') — the user should fill a short "
        "creative brief first.\n"
        "- 'generate': the request is already specific enough to act on, OR the user said 'your call' / "
        "'you decide' / 'surprise me' / 'just make it', OR it is a refine/iterate of a previous asset.\n"
        "- 'answer': it is a question or feedback, not an asset request.\n"
        "Also extract 'topic' (the subject in a few words) and a warm, upbeat one-line 'intro' to show "
        "above the brief. Return ONLY JSON: "
        '{"action":"form"|"generate"|"answer","topic":"...","intro":"..."}.'
    )
    try:
        data = await llm.chat_json([{"role": "system", "content": sys}] + convo, temperature=0.3)
    except Exception:
        return {"action": "generate"}
    action = data.get("action") if data.get("action") in ("form", "generate", "answer") else "generate"
    if action != "form":
        return {"action": action}
    topic = str(data.get("topic") or last_user or "").strip()[:200]
    intro = str(data.get("intro") or "Love it — give me a few quick details and I'll create it 👇").strip()[:240]
    return {"action": "form", "intro": intro, "form": build_form(topic)}


def parse_brief_line(line: str) -> dict:
    """Parse '[brief] format=image; requirement=a,b; topic=...; other=...' -> {key: [values]}."""
    body = (line or "").strip()
    if body.lower().startswith("[brief]"):
        body = body[len("[brief]"):]
    out: dict[str, list[str]] = {}
    for part in body.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        key = k.strip().lower()
        vals = [x.strip() for x in v.split(",") if x.strip()]
        if key and vals:
            out[key] = vals
    return out


_LABELS = {"format": "Format", "requirement": "Requirements", "design": "Design", "goal": "Goal",
           "audience": "Audience", "count": "Options", "topic": "Topic", "other": "Notes"}


def brief_system_note(parsed: dict) -> str:
    """A deterministic instruction injected into the system prompt so the loop generates from the
    submitted brief and does NOT ask anything else."""
    if not parsed:
        return ""
    lines = [f"- {_LABELS.get(k, k.title())}: {', '.join(parsed[k])}"
             for k in ("format", "topic", "requirement", "design", "goal", "audience", "count", "other")
             if parsed.get(k)]
    fmt = (parsed.get("format") or ["image"])[0].lower()
    tool = {"image": "generate_image", "deck": "build_deck", "pdf": "build_pdf"}.get(fmt, "generate_image")
    return (
        "The user submitted this creative brief via the form. GENERATE NOW — do NOT ask any more "
        "questions and do NOT show another brief.\n" + "\n".join(lines) + "\n"
        f"Call the {tool} tool. Fold the requirements, goal, audience, topic and notes into the "
        "concept/topic text so the asset reflects them. For an IMAGE: set count to the Options number "
        "(1-3) and set the optional style to the Design value when it's one of the valid styles; for a "
        "PDF pick kind = 'proposal' if the goal is leads/sales, 'one-pager' for a quick overview, else "
        "'report'; decks/PDFs ignore Design. Use ONLY real Talentrupt proof points — never invent numbers."
    )
