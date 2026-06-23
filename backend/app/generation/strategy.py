"""Campaign strategy package generation."""
from __future__ import annotations

from ..knowledge import retrieve
from ..models import Brand
from ..providers import llm


async def generate_strategy(brand: Brand | None, brief: dict) -> dict:
    """Return a structured campaign strategy package."""
    name = brief.get("name", "Untitled Campaign")
    goal = brief.get("goal", "")
    audience = brief.get("audience", "")
    pillar = brief.get("pillar", "")

    if llm.provider_available():
        pillars = ", ".join(brand.pillars) if brand else ""
        services = ", ".join(brand.services) if brand else ""
        context = await retrieve.brand_context(f"{name} {pillar} {goal}")
        sys = (
            "You are a C-level marketing strategist for Talentrupt, an offshore RPO firm "
            "(tagline 'RPO Done Right'). Return ONLY a JSON object for a campaign strategy. "
            f"Brand pillars: {pillars}. Services: {services}. "
            + (f"\n\n{context}\n\n" if context else " ")
            + "Keys: objective (string), audience (string), persona (string), "
            "pain_points (array of strings), positioning (string), key_message (string), "
            "content_strategy (array of strings), channel_strategy (array of strings), "
            "posting_schedule (array of strings), kpis (array of strings), "
            "creative_direction (string), reasoning (string), recommendations (array of strings)."
        )
        usr = (
            f"Campaign: {name}\nGoal: {goal}\nAudience: {audience}\nPillar: {pillar}\n"
            "Produce a sharp, execution-ready B2B RPO strategy."
        )
        data = await llm.chat_json(
            [{"role": "system", "content": sys}, {"role": "user", "content": usr}]
        )
        if data:
            return data

    # Deterministic fallback
    return {
        "objective": goal or f"Grow awareness and pipeline for {name}.",
        "audience": audience or "Staffing agencies and hiring-driven companies",
        "persona": "Talent acquisition leaders and staffing agency owners",
        "pain_points": [
            "Recruiting capacity can't scale with demand",
            "High cost of internal recruiting overhead",
            "Inconsistent submission quality and SLA misses",
        ],
        "positioning": "Talentrupt delivers structured offshore RPO that scales recruiting without internal overhead.",
        "key_message": pillar or "RPO Done Right — engineered hiring systems that deliver.",
        "content_strategy": [
            "Process-first education posts",
            "Proof/metric cards",
            "Myth vs Truth: RPO format",
        ],
        "channel_strategy": ["LinkedIn (primary)", "Email outreach", "Instagram (culture)"],
        "posting_schedule": ["Week 1: 2 posts", "Week 2: 2 posts", "Week 3: 1 post + recap"],
        "kpis": ["Impressions", "Engagement rate", "Qualified replies", "Meetings booked"],
        "creative_direction": "Navy/red/cream system, TR lockup, infographic and proof-card layouts.",
        "reasoning": "Built from Talentrupt's proven content pillars and RPO positioning.",
        "recommendations": [
            "Lead with a strong proof point",
            "Group posts into a sequenced narrative",
            "Close every post with a specific CTA",
        ],
    }
