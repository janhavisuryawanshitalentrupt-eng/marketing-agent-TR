"""Create-section intake.

Like a real designer taking a brief, the Create agent gathers intent through a SHORT, friendly
back-and-forth: it asks a few focused questions ONE at a time — each as a normal chat bubble with
tappable quick-pick chips — then generates. The brief is FORMAT-AWARE: an image asks about look/style,
a deck or PDF asks about purpose/audience/tone/length (document questions, not image ones). A specific
request, a "your call", or clear impatience generates straight away; the intake is capped so it never
interrogates endlessly.

Gated to mode=='create' by the orchestrator; Chat never asks.
"""
from __future__ import annotations

from ..models import Brand
from ..providers import llm

# How many questions the brief may ask before it must generate/answer (documents get one more axis).
_MAX_QUESTIONS = {"image": 3, "deck": 4, "pdf": 4}

# Keyword cues for the intended output format (newest user message wins on a conflict).
_DECK_KW = ("deck", "slide", "slides", "presentation", "present", "ppt", "pptx", "pitch", "keynote")
_PDF_KW = ("pdf", "report", "proposal", "one-pager", "one pager", "onepager", "white paper",
           "whitepaper", "document", "write-up", "writeup", "brochure")
_IMAGE_KW = ("image", "photo", "picture", "post", "graphic", "banner", "visual", "poster", "ad",
             "illustration", "thumbnail", "cover image")

# Fallback quick-picks per format, used only if the model returns none.
_FALLBACK_CHIPS = {
    "image": ["Polished photo", "Bold editorial collage", "Clean infographic", "Surprise me — your call"],
    "deck": ["Executive & concise", "Data-driven", "Story-led", "Surprise me — your call"],
    "pdf": ["Formal & detailed", "Punchy one-pager", "Persuasive proposal", "Surprise me — your call"],
}

# Format-specific brief categories injected into the classifier prompt.
_CATEGORIES = {
    "image": (
        "  1. Goal / message — what should it achieve or say?\n"
        "  2. Look / style — photographic, bold editorial collage, infographic, clean & minimal, illustration…\n"
        "  3. Audience — who is it for (healthcare, IT, staffing, finance, corporate…)?\n"
        "  4. How many options — 1, 2 or 3.\n"
    ),
    "deck": (
        "  1. Purpose / core message — what should this PRESENTATION achieve or land?\n"
        "  2. Audience — who's in the room (e.g. healthcare CHRO, staffing-agency owner, finance exec)?\n"
        "  3. Tone / formality — executive & concise, conversational, persuasive/sales-led, or data-driven?\n"
        "  4. Length — roughly how many slides (~5 short, ~8 standard, ~12 deep)?\n"
    ),
    "pdf": (
        "  1. Purpose / core message — what should this DOCUMENT achieve or land?\n"
        "  2. Audience — who reads it (e.g. healthcare CHRO, staffing-agency owner, finance exec)?\n"
        "  3. Tone / formality — formal report, persuasive proposal, or punchy one-pager voice?\n"
        "  4. Depth / length — a quick one-pager, a standard doc, or an in-depth write-up?\n"
    ),
}

_FORMAT_ANCHOR = {
    "image": "The user wants an IMAGE. Ask about its look/style, message and audience — visual questions.",
    "deck": ("The user wants a PRESENTATION (.pptx). Ask DOCUMENT questions — purpose, audience, tone, "
             "how many slides. Do NOT ask image 'look/style' questions like photographic vs collage."),
    "pdf": ("The user wants a PDF DOCUMENT. Ask DOCUMENT questions — purpose, audience, tone, depth/length. "
            "Do NOT ask image 'look/style' questions like photographic vs collage."),
}


_FORMAT_KW = {"deck": _DECK_KW, "pdf": _PDF_KW, "image": _IMAGE_KW}


def _detect_format(messages: list[dict]) -> str:
    """Infer the intended output format. The most RECENT user message that names a format wins (so a
    mid-conversation pivot re-targets). Within a single message a fixed deck>pdf>image priority breaks
    ties — it picks A format, not necessarily the last-named one, which is fine since this only chooses
    which brief questions to ask (the model still generates the right format via CREATE_GUIDANCE)."""
    users = [str(m.get("content", "")).lower() for m in messages if m.get("role") == "user"]
    for text in reversed(users):
        if any(k in text for k in _DECK_KW):
            return "deck"
        if any(k in text for k in _PDF_KW):
            return "pdf"
        if any(k in text for k in _IMAGE_KW):
            return "image"
    return "image"


async def interpret_create_intent(brand: Brand | None, messages: list[dict]) -> dict:
    """Triage the latest Create turn. Returns one of:
      {action:'ask', message:str, chips:[str]} — gather the next part of the brief, conversationally
      {action:'generate'}                       — enough is known / 'your call' / capped: just make it
      {action:'answer'}                         — a question or feedback
    Defaults to 'generate' on any uncertainty so generation is never blocked."""
    convo = [{"role": m["role"], "content": str(m.get("content", ""))}
             for m in messages if m.get("role") in ("user", "assistant")][-10:]

    fmt = _detect_format(convo)

    # Soft cap on the brief: once a few questions have been asked, the agent may still ANSWER a question
    # or GENERATE, but must not keep asking. Count questions only SINCE the current format was last named,
    # so a mid-conversation pivot (e.g. deck -> image) gets a fresh budget instead of inheriting the prior
    # format's count. (Counting assistant "?" turns is a heuristic — an answered question may also contain
    # "?", which only makes the cap kick in a touch sooner.)
    anchor = 0
    for i, m in enumerate(convo):
        if m["role"] == "user" and any(k in m["content"].lower() for k in _FORMAT_KW[fmt]):
            anchor = i
    asked = sum(1 for m in convo[anchor:] if m["role"] == "assistant" and "?" in m["content"])
    capped = asked >= _MAX_QUESTIONS.get(fmt, 3)

    sys = (
        "You are Talentrupt's creative director in the Create studio (it makes images, decks and PDFs). "
        "Like a real designer, you take a SHORT creative brief through a friendly back-and-forth — asking "
        "a few focused questions, ONE at a time, before you create. Read the LATEST user message and pick "
        "exactly ONE action.\n\n"
        f"{_FORMAT_ANCHOR[fmt]}\n"
        "Brief CATEGORIES to cover (roughly this priority):\n"
        f"{_CATEGORIES[fmt]}\n"
        "- 'ask': it's a NEW/ongoing asset request and you still don't know an IMPORTANT category. Ask "
        "about the single most important MISSING one as a warm, ONE-sentence question, and give 3-5 "
        "'chips' — short tappable quick-pick answers (1-4 words) tailored to THAT category and their "
        "topic, always including an easygoing 'Surprise me' / 'Your call' chip. NEVER repeat a question "
        "already asked; build on what they've said. Aim to learn 2-3 categories before creating.\n"
        "- 'generate': you know enough to make something well-tailored, OR the latest message ANSWERS "
        "your question / names a direction / requests a tweak or refine, OR the user said 'your call' / "
        "'you decide' / 'surprise me' / 'just make it'. If the request already names the TOPIC plus at "
        "least TWO specifics (e.g. audience, tone, length, format or style), you know enough — GENERATE, "
        "don't ask. Don't keep asking once you can act.\n"
        "- 'answer': the latest message is NOT a request to create or change an asset — it's a QUESTION "
        "(what can you do, why a choice, what a term means, how many I can get…), a greeting, thanks, or a "
        "general comment. The studio will reply conversationally.\n\n"
        "Examples: 'make me a post'→ask. 'photographic, for healthcare'→generate. 'a deck on RPO'→ask. "
        "'just do your thing'→generate. 'make the logo bigger'→generate. 'what styles can you do?'→answer. "
        "'thanks, perfect!'→answer. 'hi'→answer.\n\n"
        'Return ONLY JSON: {"action":"ask"|"generate"|"answer","message":"...","chips":["...","..."]}.'
    )
    if capped:
        sys += ("\n\nNOTE: You have already asked several questions in this conversation — do NOT choose "
                "'ask' again. Choose 'generate' (an asset request or an answer to act on) or 'answer' (a "
                "question or comment).")
    try:
        data = await llm.chat_json([{"role": "system", "content": sys}] + convo, temperature=0.5)
    except Exception:
        return {"action": "generate"}
    action = data.get("action") if data.get("action") in ("ask", "generate", "answer") else "generate"
    if action == "ask" and capped:  # safety: never keep asking past the cap
        action = "generate"
    if action != "ask":
        return {"action": action}
    message = str(data.get("message") or "").strip()[:400]
    if not message:  # nothing to say -> don't get stuck asking; just generate
        return {"action": "generate"}
    chips = [str(c).strip()[:40] for c in (data.get("chips") or []) if str(c).strip()][:5]
    return {"action": "ask", "message": message, "chips": chips or _FALLBACK_CHIPS[fmt]}
