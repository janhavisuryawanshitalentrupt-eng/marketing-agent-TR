"""Create-section intake.

Like a real designer taking a brief, the Create agent gathers intent through a SHORT, friendly
back-and-forth: it asks a few focused questions ONE at a time — across categories (goal/message,
format, look, audience, how many) — each as a normal chat bubble with tappable quick-pick chips, then
generates. A specific request, a "your call", or clear impatience generates straight away; the intake
is capped so it never interrogates endlessly.

Gated to mode=='create' by the orchestrator; Chat never asks.
"""
from __future__ import annotations

from ..models import Brand
from ..providers import llm

# Cap the back-and-forth: once this many questions have been asked, just generate.
_MAX_QUESTIONS = 3
# Sensible fallback quick-picks if the model returns none.
_FALLBACK_CHIPS = ["Polished photo", "Bold editorial collage", "Clean infographic", "Surprise me — your call"]


async def interpret_create_intent(brand: Brand | None, messages: list[dict]) -> dict:
    """Triage the latest Create turn. Returns one of:
      {action:'ask', message:str, chips:[str]} — gather the next part of the brief, conversationally
      {action:'generate'}                       — enough is known / 'your call' / capped: just make it
      {action:'answer'}                         — a question or feedback
    Defaults to 'generate' on any uncertainty so generation is never blocked."""
    convo = [{"role": m["role"], "content": str(m.get("content", ""))}
             for m in messages if m.get("role") in ("user", "assistant")][-10:]

    # Safety cap: if the agent has already asked a few questions, stop and generate (no extra LLM call).
    asked = sum(1 for m in convo if m["role"] == "assistant" and "?" in m["content"])
    if asked >= _MAX_QUESTIONS:
        return {"action": "generate"}

    sys = (
        "You are Talentrupt's creative director in the Create studio (it makes images, decks and PDFs). "
        "Like a real designer, you take a SHORT creative brief through a friendly back-and-forth — asking "
        "a few focused questions, ONE at a time, before you create. Decide ONE action for the LATEST "
        "user message.\n\n"
        "Brief CATEGORIES to cover (roughly this priority):\n"
        "  1. Goal / message — what should it achieve or say?\n"
        "  2. Format — image, deck (.pptx) or PDF (assume an image if they implied a visual/post).\n"
        "  3. Look / style — photographic, bold editorial collage, infographic, clean & minimal, illustration…\n"
        "  4. Audience — who is it for (healthcare, IT, staffing, finance, corporate…)?\n"
        "  5. How many options — 1, 2 or 3.\n\n"
        "- 'ask': you still don't know an IMPORTANT category. Ask about the single most important MISSING "
        "one as a warm, ONE-sentence question, and give 3-5 'chips' — short tappable quick-pick answers "
        "(1-4 words) tailored to THAT category and their topic, always including an easygoing 'Surprise "
        "me' / 'Your call' chip. NEVER repeat a question already asked in this conversation; build on "
        "what they've said. Aim to learn 2-3 categories before creating — don't stop after just one.\n"
        "- 'generate': you now know enough to make something well-tailored (at least the goal AND the "
        "look, ideally the audience too), OR the user said 'your call' / 'you decide' / 'surprise me' / "
        "'just make it' / seems impatient. Don't keep asking once you can act well.\n"
        "- 'answer': it's a question or feedback, not an asset request.\n\n"
        'Return ONLY JSON: {"action":"ask"|"generate"|"answer","message":"...","chips":["...","..."]}.'
    )
    try:
        data = await llm.chat_json([{"role": "system", "content": sys}] + convo, temperature=0.6)
    except Exception:
        return {"action": "generate"}
    action = data.get("action") if data.get("action") in ("ask", "generate", "answer") else "generate"
    if action != "ask":
        return {"action": action}
    message = str(data.get("message") or "").strip()[:400]
    if not message:  # nothing to say -> don't get stuck asking; just generate
        return {"action": "generate"}
    chips = [str(c).strip()[:40] for c in (data.get("chips") or []) if str(c).strip()][:5]
    return {"action": "ask", "message": message, "chips": chips or _FALLBACK_CHIPS}
