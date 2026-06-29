"""Social/marketing post generation."""
from __future__ import annotations

from ..knowledge import retrieve
from ..models import Brand, Campaign
from ..providers import llm


async def generate_posts(
    brand: Brand | None,
    campaign: Campaign | None,
    count: int = 3,
    platform: str = "Social",
    angle: str = "",
) -> list[dict]:
    """Return a list of post dicts: platform, content_type, hook, caption, cta,
    hashtags (list), visual_concept."""
    count = max(1, min(count, 8))

    if llm.provider_available():
        pillars = ", ".join(brand.pillars) if brand else ""
        ctx = ""
        if campaign:
            ctx = (
                f"Campaign: {campaign.name}. Goal: {campaign.goal}. "
                f"Audience: {campaign.audience}. Pillar: {campaign.pillar}. "
            )
        query = " ".join(filter(None, [angle, platform, campaign.pillar if campaign else "", campaign.name if campaign else ""]))
        context = await retrieve.brand_context(query)
        sys = (
            "You are Talentrupt's senior B2B copywriter (offshore RPO, 'RPO Done Right'). "
            f"Brand pillars: {pillars}. "
            + (f"\n\n{context}\n\n" if context else "")
            + "Return ONLY a JSON object with key 'posts' = array. Each post has: "
            "platform, content_type, hook, caption, cta, hashtags (array of strings), "
            "visual_concept. Make hooks scroll-stopping, captions tight and proof-driven, "
            "CTAs specific. No fluff, no emojis-as-bullets."
        )
        plat_line = (
            "platform-agnostic SOCIAL MEDIA posts (work on any network — do not name or tailor to a "
            "specific platform; set each post's \"platform\" field to \"Social\")"
            if platform.lower() in ("social", "social media", "")
            else f"{platform} posts"
        )
        usr = (
            f"{ctx}Write {count} {plat_line}"
            + (f" with this angle: {angle}." if angle else ".")
        )
        data = await llm.chat_json(
            [{"role": "system", "content": sys}, {"role": "user", "content": usr}]
        )
        raw = data.get("posts") if isinstance(data, dict) else None
        posts = [p for p in (raw or []) if isinstance(p, dict)]  # ignore non-object items
        if posts:
            return posts[:count]

    # Deterministic fallback
    base = angle or (campaign.pillar if campaign else "RPO Done Right")
    out = []
    for i in range(count):
        out.append(
            {
                "platform": platform,
                "content_type": "Educational post",
                "hook": f"{base}: the part most staffing teams get wrong.",
                "caption": (
                    "Scaling recruiting shouldn't mean scaling overhead. Talentrupt's "
                    "structured offshore RPO adds dedicated sourcing and full life-cycle "
                    "recruiting capacity — engineered for SLA delivery and submission quality."
                ),
                "cta": "See how Talentrupt scales your hiring — book a call.",
                "hashtags": ["#RPO", "#Staffing", "#Recruiting", "#TalentAcquisition"],
                "visual_concept": "Navy proof-card with red rail and a single standout metric.",
            }
        )
    return out
