"""Future-campaign planner: a strategy brief + a dated content calendar.

Grounded in the brand library (incl. the ingested sales deck) via retrieve.brand_context.
"""
from __future__ import annotations

from ..knowledge import retrieve
from ..models import Brand
from ..providers import llm

FORMATS = {"post", "image", "deck", "pdf"}
WEEK_DAYS = 7


def _weeks(timeframe: str) -> int:
    """Parse '4 weeks' / '6' etc. -> int weeks (1-12)."""
    digits = "".join(ch for ch in str(timeframe) if ch.isdigit())
    try:
        w = int(digits) if digits else 4
    except ValueError:
        w = 4
    return max(1, min(w, 12))


async def interpret_intent(brand: Brand | None, messages: list[dict]) -> dict:
    """Conversational new-campaign intake. Given the chat so far, either ask ONE
    clarifying question or return a ready brief to plan.
    Returns {"action": "ask"|"plan", "message"?, "name","goal","audience","channels","timeframe"}.
    """
    if not llm.provider_available():
        last = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        return {"action": "plan", "name": last[:60] or "New Campaign", "goal": last,
                "audience": "", "sector": "", "channels": ["LinkedIn"], "timeframe": "4 weeks"}

    pillars = ", ".join(brand.pillars) if brand else ""
    sys = (
        "You are Talentrupt's campaign-planning intake assistant (offshore RPO, 'RPO Done Right'; "
        f"pillars: {pillars}). From the conversation, determine the marketing campaign the user "
        "wants to plan. You need at minimum a clear GOAL/topic. Infer audience, channels, and "
        "timeframe; DEFAULT channels=['LinkedIn'] and timeframe='4 weeks' when unspecified. "
        "Also choose the ONE primary target SECTOR for this campaign from EXACTLY this list: "
        "'IT & Software', 'Healthcare', 'Staffing & Recruiting', 'Corporate / Non-IT', "
        "'Finance & Fintech'. Pick the single best fit for the goal — do NOT default to Healthcare. "
        "Make the AUDIENCE specific to that one sector (e.g. for 'IT & Software': 'software & tech "
        "companies scaling engineering and product teams'); NEVER write a cross-sector audience like "
        "'healthcare and other industries'. "
        "Ask AT MOST ONE short clarifying question, and only if the goal/topic is genuinely unclear "
        "— otherwise proceed to plan. Return ONLY JSON: "
        '{"action":"ask"|"plan","message":"<one concise question, only if action=ask>",'
        '"name":"<short campaign name>","goal":"...","audience":"...",'
        '"sector":"<one of the five sectors above>",'
        '"channels":["LinkedIn"|"Email"|"Instagram"|"Blog"...],"timeframe":"e.g. 4 weeks"}. '
        "Prefer action='plan' as soon as you understand the goal — do not over-ask."
    )
    convo = [{"role": "system", "content": sys}]
    for m in messages[-8:]:
        if m.get("role") in ("user", "assistant"):
            convo.append({"role": m["role"], "content": str(m.get("content", ""))})
    data = await llm.chat_json(convo)
    if not isinstance(data, dict):
        return {"action": "ask", "message": "What's the goal of this campaign, and who's it for?"}
    action = data.get("action") if data.get("action") in ("ask", "plan") else None
    if action == "plan" and (data.get("goal") or data.get("name")):
        return {
            "action": "plan",
            "name": str(data.get("name") or data.get("goal") or "New Campaign")[:80],
            "goal": str(data.get("goal") or data.get("name") or ""),
            "audience": str(data.get("audience") or ""),
            "sector": str(data.get("sector") or ""),
            "channels": data.get("channels") or ["LinkedIn"],
            "timeframe": str(data.get("timeframe") or "4 weeks"),
        }
    return {"action": "ask", "message": str(data.get("message") or "Tell me the campaign's goal and audience.")}


async def plan_campaign(brand: Brand | None, brief: dict) -> dict:
    """Return {strategy, items}. items each: day_offset, channel, format, topic, hook."""
    name = brief.get("name", "Campaign")
    goal = brief.get("goal", "")
    audience = brief.get("audience", "")
    channels = brief.get("channels") or ["LinkedIn"]
    weeks = _weeks(brief.get("timeframe", "4 weeks"))
    n_items = max(3, min(weeks * 2, 16))  # ~2 posts/week, capped

    if llm.provider_available():
        pillars = ", ".join(brand.pillars) if brand else ""
        proof = "; ".join(brand.proof_points) if brand and brand.proof_points else ""
        context = await retrieve.brand_context(f"{name} {goal} {audience}", k=8)
        sys = (
            "You are a senior B2B marketing strategist for Talentrupt (offshore RPO, 'RPO Done "
            f"Right'). Brand pillars: {pillars}. Proof points (use only if real/relevant, never "
            f"invent): {proof}.\n"
            + (f"\n{context}\n\n" if context else "")
            + "Plan a forward-looking campaign. Return ONLY JSON with TWO keys:\n"
            '"strategy": {"objective","audience","key_messages":[...3-4],"pillars":[...],'
            '"kpis":[...3-5]}\n'
            f'"items": an array of EXACTLY {n_items} content-calendar items spread across {weeks} '
            f"week(s). Each item: "
            '{"day_offset": integer day from campaign start (0-based, spread evenly across the '
            f"{weeks * WEEK_DAYS} days), "
            f'"channel": one of {channels}, '
            '"format": one of "post","image","deck","pdf" (mostly "post"/"image"; occasional '
            '"deck"/"pdf" for milestones), "topic": short content topic, '
            '"hook": a scroll-stopping one-line hook for that piece}.\n'
            "Make the arc build over time (awareness -> proof -> offer -> CTA). Vary topics/formats; "
            "ground them in Talentrupt's real services, process, pricing, and proof."
        )
        usr = f"Campaign: {name}\nGoal: {goal}\nAudience: {audience}\nChannels: {channels}\nTimeframe: {weeks} weeks"
        data = await llm.chat_json(
            [{"role": "system", "content": sys}, {"role": "user", "content": usr}]
        )
        if isinstance(data, dict) and data.get("items"):
            return {
                "strategy": data.get("strategy", {}) or {},
                "items": _normalize_items(data["items"], channels, weeks)[:n_items],
            }

    # Deterministic fallback
    strategy = {
        "objective": goal or f"Grow awareness and pipeline for {name}.",
        "audience": audience or "Staffing agencies and hiring-driven companies",
        "key_messages": [
            "RPO Done Right — scale recruiting without internal overhead",
            "Proven delivery: fast, SLA-driven submissions",
            "Flexible recruiter pods that grow with you",
        ],
        "pillars": (brand.pillars[:4] if brand else []),
        "kpis": ["Impressions", "Engagement rate", "Qualified replies", "Meetings booked"],
    }
    fmts = ["post", "image", "post", "image", "deck", "pdf"]
    items = []
    for i in range(n_items):
        items.append({
            "day_offset": int(i * (weeks * WEEK_DAYS) / max(1, n_items)),
            "channel": channels[i % len(channels)],
            "format": fmts[i % len(fmts)],
            "topic": f"{name}: angle {i + 1}",
            "hook": "RPO Done Right — here's what that means for your hiring.",
        })
    return {"strategy": strategy, "items": items}


def _normalize_items(raw: list, channels: list, weeks: int) -> list[dict]:
    horizon = weeks * WEEK_DAYS
    out = []
    for it in raw or []:
        if not isinstance(it, dict):
            continue
        try:
            off = int(it.get("day_offset", 0))
        except (TypeError, ValueError):
            off = 0
        fmt = it.get("format") if it.get("format") in FORMATS else "post"
        ch = it.get("channel") if it.get("channel") in channels else (channels[0] if channels else "LinkedIn")
        out.append({
            "day_offset": max(0, min(off, horizon - 1)),
            "channel": str(ch),
            "format": fmt,
            "topic": str(it.get("topic", "") or "")[:380],
            "hook": str(it.get("hook", "") or "")[:600],
        })
    out.sort(key=lambda x: x["day_offset"])
    return out
