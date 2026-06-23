"""Generate a real, grounded 'how to win this client' strategy for a campaign target client.

It is grounded in the prospect's ACTUAL hiring signal + Talentrupt's REAL capabilities/voice
(pulled from the brand library). It's advisory sales strategy — specific, not invented facts.
"""
from __future__ import annotations

from ..knowledge import retrieve
from ..providers import llm

_FIELDS = (
    'Return ONLY a JSON object with keys: '
    '"why_fit" (1-2 sentences on why this company is a strong fit for Talentrupt RPO, grounded in '
    'their hiring signal), '
    '"pain_points" (array of 3-4 specific recruiting pains THIS company likely faces), '
    '"approach" (2-3 sentences: the strategy/angle to win them — what to lead with and why it '
    'resonates), '
    '"talking_points" (array of 4-6 concrete, specific points the rep can raise, tied to '
    "Talentrupt's real capabilities), "
    '"recommended_services" (array of the Talentrupt services that fit this company), '
    '"first_touch" (a short, warm, specific opening message — email or LinkedIn — referencing '
    'their real situation; no placeholders like [name]).'
)


async def win_strategy(prospect: dict, campaign=None) -> dict:
    """Return a structured win strategy for `prospect` (a normalized discover dict)."""
    if not llm.provider_available():
        return {}
    company = prospect.get("company", "")
    context = await retrieve.brand_context(
        f"{company} {prospect.get('recommended_service', '')} RPO win strategy outreach", k=4
    )
    sys = (
        "You are Talentrupt's senior RPO sales strategist. Talentrupt is an offshore RPO that gives "
        "staffing agencies and hiring-driven companies scalable, SLA-driven recruiting and sourcing "
        "capacity (full life-cycle recruiting, dedicated sourcers, credentialing, VMS support, "
        "healthcare staffing, back-office recruiting ops). Produce a CONCRETE, SPECIFIC strategy to "
        "win THIS company as a client — grounded in their actual hiring signal and Talentrupt's REAL "
        "capabilities. No generic fluff, and do NOT invent facts, names, or numbers. " + _FIELDS
        + (f"\n\nTalentrupt voice & proof points (use naturally, only if relevant):\n{context}"
           if context else "")
    )
    usr = (
        f"Target company: {company}\n"
        f"Segment: {prospect.get('segment', '')}\n"
        f"Hiring signal: {prospect.get('hiring_signal', '')}\n"
        f"Why now: {prospect.get('why_now', '')}\n"
        f"Recommended service: {prospect.get('recommended_service', '')}\n"
        f"Known pain points: {', '.join(prospect.get('pain_points', []) or [])}\n"
        + (f"Campaign goal: {getattr(campaign, 'goal', '') or ''}\n" if campaign else "")
        + "Write the win strategy for this specific company."
    )
    data = await llm.chat_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": usr}]
    )
    return data or {}
