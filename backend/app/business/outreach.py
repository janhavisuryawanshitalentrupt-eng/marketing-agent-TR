"""Generate personalized outreach for an opportunity, grounded in Talentrupt's voice."""
from __future__ import annotations

from ..knowledge import retrieve
from ..models import Opportunity
from ..providers import llm


async def generate_outreach(opp: Opportunity) -> dict:
    why = opp.why or {}
    signal = opp.signal or why.get("hiring_signal", "")
    context = await retrieve.brand_context(f"{opp.company} {opp.service} outreach RPO", k=3)

    if llm.provider_available():
        sys = (
            "You are Talentrupt's senior business-development copywriter. Talentrupt is an "
            "offshore RPO that gives staffing agencies and hiring-driven companies scalable "
            "recruiting/sourcing capacity. Write warm, specific, non-spammy B2B outreach that "
            "references the prospect's real hiring signal. Return ONLY JSON with: "
            "email_subject, email_body, linkedin_message (<= 300 chars), "
            "followups (array of 2 objects {day, message}), talking_points (array of 3-4 strings)."
            + (f"\n\nTalentrupt voice/patterns:\n{context}" if context else "")
        )
        usr = (
            f"Prospect: {opp.company}\nSegment: {opp.segment}\nHiring signal: {signal}\n"
            f"Why now: {why.get('why_now','')}\nRecommended service: {opp.service}\n"
            f"Decision-maker: {why.get('decision_maker','')}\n"
            "Write the outreach for that decision-maker."
        )
        data = await llm.chat_json(
            [{"role": "system", "content": sys}, {"role": "user", "content": usr}]
        )
        if data:
            return data

    # Deterministic fallback
    return {
        "email_subject": f"Helping {opp.company} scale hiring without the overhead",
        "email_body": (
            f"Hi {{name}},\n\nI noticed {opp.company} {signal or 'is actively hiring'}. "
            "Scaling recruiting fast often means scaling overhead — Talentrupt gives you "
            "dedicated offshore sourcing and full life-cycle recruiting capacity, engineered "
            "for SLA delivery and submission quality.\n\nWorth a quick conversation?\n\n— Talentrupt"
        ),
        "linkedin_message": (
            f"Hi {{name}} — saw {opp.company} is hiring. Talentrupt adds dedicated RPO "
            "recruiting capacity without internal overhead. Open to a quick chat?"
        ),
        "followups": [
            {"day": 3, "message": "Following up — happy to share how we scale recruiting capacity quickly."},
            {"day": 7, "message": "Last note — even a pilot pod can ease your current hiring load."},
        ],
        "talking_points": [
            "Dedicated sourcing capacity, no internal overhead",
            "SLA-driven delivery and submission quality",
            "Flexible, scalable recruiter pods",
        ],
    }
