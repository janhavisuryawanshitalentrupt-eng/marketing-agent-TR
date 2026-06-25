"""Create-section intake.

When a NEW Create request is vague about the look, the agent replies like a person — a warm,
one-or-two-sentence question about how they want it designed — and offers a few tappable quick-pick
chips the user can click instead of typing. A specific request, a "your call", or a refine generates
straight away. The reply (typed or tapped) is just a normal chat turn the generation loop acts on.

Gated to mode=='create' by the orchestrator; Chat never asks.
"""
from __future__ import annotations

from ..models import Brand
from ..providers import llm

# Sensible fallback quick-picks if the model returns none.
_FALLBACK_CHIPS = ["Polished photo", "Bold editorial collage", "Clean infographic", "Surprise me — your call"]


async def interpret_create_intent(brand: Brand | None, messages: list[dict]) -> dict:
    """Triage the latest Create turn. Returns one of:
      {action:'ask', message:str, chips:[str]} — vague new request: ask conversationally + quick-picks
      {action:'generate'}                       — specific / 'your call' / answering / a refine: just make it
      {action:'answer'}                         — a question or feedback
    Defaults to 'generate' on any uncertainty so generation is never blocked."""
    convo = [{"role": m["role"], "content": str(m.get("content", ""))}
             for m in messages if m.get("role") in ("user", "assistant")][-8:]
    sys = (
        "You are Talentrupt's creative director in the Create studio (it makes images, decks and PDFs). "
        "Decide ONE action for the LATEST user message:\n"
        "- 'ask': a NEW asset request that is VAGUE about the look (e.g. 'make an image for our "
        "marketing', 'design a post', 'create something for LinkedIn'). Reply like a real person: write "
        "a warm, upbeat ONE-or-two-sentence 'message' asking how they'd like it to look / what to "
        "emphasise, and give 3-5 'chips' — short tappable quick-pick answers (1-4 words each) tailored "
        "to their topic that they can click instead of typing. Always include one easygoing "
        "'Surprise me' style chip. Vary your wording every time; never sound like a scripted form.\n"
        "- 'generate': the request already says enough to act on; OR the user said 'your call' / "
        "'you decide' / 'surprise me' / 'just make it'; OR the latest message ANSWERS a question you "
        "just asked, names a look/style/direction, or refines a previous asset. When in doubt between "
        "ask and generate after the user has already said something concrete, choose 'generate'.\n"
        "- 'answer': it is a question or feedback, not an asset request.\n"
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
