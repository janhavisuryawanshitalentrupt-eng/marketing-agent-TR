"""Tool registry for the marketing agent.

Each tool has (1) an OpenAI function schema exposed to the model and (2) an
executor that runs a generation engine, persists assets, and returns a result
the model can read plus serialized asset cards for the client.

Executors are plain functions so both the LLM loop and the deterministic
fallback path can call them.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..business import analyze as bd_analyze
from ..business import discover as bd_discover
from ..business import outreach as bd_outreach
from ..business.store import save_opportunity, serialize_opportunity
from ..generation import decks, images, pdf, posts, refine as gen_refine, strategy, teampost
from ..knowledge import retrieve
from ..models import Asset, Brand, CalendarTask, Campaign, CampaignProspect, Employee, Opportunity
from ..providers import llm


# --- Serialization --------------------------------------------------------
def serialize_asset(a: Asset) -> dict:
    return {
        "id": a.id,
        "campaign_id": a.campaign_id,
        "type": a.type,
        "title": a.title,
        "body": a.body,
        "file_url": a.file_url,
        "meta": a.meta,
    }


def _save_asset(db: Session, campaign_id: int | None, type_: str, title: str,
                body: dict, file_path: str | None = None, file_url: str | None = None,
                meta: dict | None = None, owner: str = "admin") -> Asset:
    a = Asset(
        campaign_id=campaign_id, owner=owner, type=type_, title=title[:380], body=body,
        file_path=file_path, file_url=file_url, meta=meta or {},
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


QUICK_CONTENT = "Quick Content"


async def _ensure_campaign(db: Session, state: dict, brand: Brand | None, hint: str) -> Campaign:
    """Return the active campaign. One-off generations (no planned campaign in this
    turn) go into a single shared 'Quick Content' folder instead of spawning a new
    named folder per request."""
    owner = state.get("owner", "admin")
    if state.get("campaign_id"):
        c = db.get(Campaign, state["campaign_id"])
        if c:
            return c
    # Scope the shared "Quick Content" folder by owner so the two accounts never pool into one.
    c = db.query(Campaign).filter(Campaign.name == QUICK_CONTENT, Campaign.owner == owner).first()
    if not c:
        c = Campaign(name=QUICK_CONTENT, owner=owner, goal="One-off generated assets", audience="", pillar="")
        db.add(c)
        db.commit()
        db.refresh(c)
    state["campaign_id"] = c.id
    return c


# --- Executors ------------------------------------------------------------
async def exec_create_campaign(db, state, brand, args) -> dict:
    name = args.get("name", "Untitled Campaign")
    brief = {
        "name": name,
        "goal": args.get("goal", ""),
        "audience": args.get("audience", ""),
        "pillar": args.get("pillar", ""),
    }
    owner = state.get("owner", "admin")
    strat = await strategy.generate_strategy(brand, brief)
    # Reuse an existing same-named campaign instead of creating a duplicate folder — but only the
    # caller's own, so it can't adopt the other account's campaign.
    existing = (
        db.query(Campaign)
        .filter(func.lower(Campaign.name) == name.strip().lower(), Campaign.owner == owner)
        .first()
    )
    if existing:
        existing.goal = brief["goal"] or existing.goal
        existing.audience = brief["audience"] or existing.audience
        existing.pillar = brief["pillar"] or existing.pillar
        existing.kpis = strat.get("kpis", []) or existing.kpis
        existing.strategy = strat
        db.commit()
        c = existing
    else:
        c = Campaign(
            name=name[:280], owner=owner, goal=brief["goal"], audience=brief["audience"],
            pillar=brief["pillar"], channels=args.get("channels", []) or [],
            timeline=args.get("timeline", ""), kpis=strat.get("kpis", []),
            strategy=strat, status="active",
        )
        db.add(c)
        db.commit()
        db.refresh(c)
    state["campaign_id"] = c.id

    card = {
        "id": c.id, "type": "campaign", "title": c.name, "campaign_id": c.id,
        "body": {
            "objective": strat.get("objective", ""),
            "key_message": strat.get("key_message", ""),
            "audience": strat.get("audience", ""),
        },
        "file_url": None, "meta": {},
    }
    return {
        "summary": f"Created campaign '{name}' with a full strategy package.",
        "assets": [card],
    }


async def exec_generate_posts(db, state, brand, args) -> dict:
    c = await _ensure_campaign(db, state, brand, args.get("angle") or "Quick Content")
    platform = args.get("platform") or "Social"
    items = await posts.generate_posts(
        brand, c, count=args.get("count", 3), platform=platform, angle=args.get("angle", ""),
    )
    saved = []
    for p in items:
        a = _save_asset(
            db, c.id, "post", p.get("hook", "Post"),
            body=p, meta={"platform": p.get("platform") or platform},
            owner=state.get("owner", "admin"),
        )
        saved.append(serialize_asset(a))
    label = "social media" if platform.lower().startswith("social") else platform
    return {"summary": f"Wrote {len(saved)} {label} post" + ("s" if len(saved) != 1 else "") + ".",
            "assets": saved}


async def exec_generate_image(db, state, brand, args) -> dict:
    concept = args.get("concept", "")
    # HARD GUARD (defense-in-depth): NEVER AI-generate a real team member's face. If the concept names
    # someone in the Team library, route to the REAL-photo composer no matter what the model chose —
    # the prompt also says so, but this guarantees it even when the model ignores the prompt. (A second
    # identical guard lives inside images.build_images so refine/campaign paths are covered too.)
    person = teampost.detect_team_person(concept)
    if person:
        return await exec_team_image(db, state, brand,
                                     {"person": person, "message": concept, "count": args.get("count")})
    # Offer variations to pick from. Clamp to 1-3 as a hard cost ceiling regardless of the model's ask.
    try:
        count = max(1, min(int(args.get("count", 1) or 1), 3))
    except (TypeError, ValueError):
        count = 1
    rendered = await images.build_images(brand, None, concept, count=count, style=args.get("style"),
                                         brief=state.get("campaign_brief", ""))
    saved = []
    for path, fname, meta in rendered:
        a = _save_asset(
            db, state.get("campaign_id"), "image", concept or "Campaign visual",
            body={"concept": concept, "layout": meta.get("layout")},
            file_path=path, file_url=meta["url"], meta=meta,
            owner=state.get("owner", "admin"),
        )
        saved.append(serialize_asset(a))
    if not saved:  # generation returned nothing (e.g. provider error) — don't claim success
        return {"summary": "Image generation didn't return anything this time — please try again.", "assets": []}
    n = len(saved)
    summary = (f"Generated {n} on-brand image variations to choose from." if n > 1
               else "Generated an on-brand image.")
    return {"summary": summary, "assets": saved}


def _variation_count(args) -> int:
    """User-chosen number of variations, clamped 1-3 (hard cost ceiling)."""
    try:
        return max(1, min(int(args.get("count", 1) or 1), 3))
    except (TypeError, ValueError):
        return 1


# Document styling vocabulary — single source of truth shared by the schemas and the builders.
DOC_TONE = ["executive", "professional", "conversational", "persuasive", "data-driven"]
DOC_DEPTH = ["concise", "standard", "in-depth"]
DOC_THEME = ["minimal", "editorial", "bold", "data-driven"]
_DEPTH_SLIDES = {"concise": 5, "standard": 8, "in-depth": 12}


def _doc_style(args) -> dict:
    """Extract the optional document-tailoring params, validated against the enums. Returns ONLY the
    keys the user actually supplied, so old topic-only calls pass nothing extra and builders use defaults."""
    out: dict = {}
    if (aud := str(args.get("audience") or "").strip()):
        out["audience"] = aud[:200]
    if (tone := str(args.get("tone") or "").strip().lower()) in DOC_TONE:
        out["tone"] = tone
    if (depth := str(args.get("depth") or "").strip().lower()) in DOC_DEPTH:
        out["depth"] = depth
    if (theme := str(args.get("design_theme") or "").strip().lower()) in DOC_THEME:
        out["design_theme"] = theme
    return out


async def exec_build_deck(db, state, brand, args) -> dict:
    topic = args.get("topic") or "Talentrupt RPO"
    style = _doc_style(args)
    # Explicit slide count wins; else derive from depth; else default 6.
    slides = args.get("slides") or _DEPTH_SLIDES.get(style.get("depth", ""), 6)
    count = _variation_count(args)
    saved = []
    brief = state.get("campaign_brief", "")
    for _ in range(count):  # each build re-plans the outline -> distinct variations
        path, fname, meta = await decks.build_deck(brand, None, topic, slides=slides, brief=brief, **style)
        a = _save_asset(db, state.get("campaign_id"), "deck", topic, body={"topic": topic, **style},
                        file_path=path, file_url=meta["url"], meta=meta,
                        owner=state.get("owner", "admin"))
        saved.append(serialize_asset(a))
    if not saved:
        return {"summary": "Couldn't build the presentation this time — please try again.", "assets": []}
    n = len(saved)
    summary = (f"Built {n} presentation variations to choose from."
               if n > 1 else f"Built a {saved[0].get('meta', {}).get('slides', slides)}-slide presentation.")
    return {"summary": summary, "assets": saved}


async def exec_build_pdf(db, state, brand, args) -> dict:
    kind = args.get("kind", "report")
    topic = (args.get("topic") or "").strip()
    style = _doc_style(args)
    count = _variation_count(args)
    brief = state.get("campaign_brief", "")
    saved = []
    for _ in range(count):
        # Write tailored, brand-grounded content for the topic (None -> template fallback in build_pdf).
        outline = await pdf.generate_pdf_outline(brand, topic, kind, brief=brief, **style) if (topic or brief) else None
        path, fname, meta = pdf.build_pdf(brand, None, kind=kind, topic=topic, outline=outline, brief=brief, **style)
        title = (topic or f"Talentrupt — {kind}")[:120]
        a = _save_asset(db, state.get("campaign_id"), "pdf", title, body={"kind": kind, "topic": topic, **style},
                        file_path=path, file_url=meta["url"], meta=meta,
                        owner=state.get("owner", "admin"))
        saved.append(serialize_asset(a))
    if not saved:
        return {"summary": "Couldn't build the document this time — please try again.", "assets": []}
    n = len(saved)
    summary = (f"Created {n} {kind} PDF variations to choose from" + (f" on “{topic}”." if topic else ".")
               if n > 1 else f"Created a {kind} PDF" + (f" on “{topic}”." if topic else "."))
    return {"summary": summary, "assets": saved}


async def exec_search_brand_knowledge(db, state, brand, args) -> dict:
    hits = await retrieve.search(args.get("query", ""), k=args.get("k", 6))
    if not hits:
        return {"summary": "No matching items found in the Talentrupt source library yet.", "assets": []}
    lines = [f"- ({h['folder']}) {' '.join(h['text'].split())[:300]}" for h in hits]
    return {"summary": "Talentrupt source-library matches:\n" + "\n".join(lines), "assets": []}


def _contact_label(c: dict) -> str:
    return " / ".join(x for x in [c.get("name"), c.get("role")] if x)


async def exec_discover_prospects(db, state, brand, args) -> dict:
    """Find real hiring companies as Talentrupt prospects; score + save them to Business Dev."""
    filters: dict = {}
    for key in ("industry", "company_size", "location", "title", "signal", "keywords"):
        val = args.get(key)
        if val:
            filters[key] = str(val)
    try:
        count = max(1, min(int(args.get("count", 6) or 6), 12))
    except (TypeError, ValueError):
        count = 6
    items = await bd_discover.discover(
        None, str(args.get("query", "") or ""), count=count, filters=filters or None
    )
    if not items:
        return {"summary": "No matching companies surfaced right now — try broadening the criteria.",
                "assets": []}
    saved = [save_opportunity(db, it, owner=state.get("owner", "admin")) for it in items]
    lines = []
    for o in saved:
        w = o.why or {}
        contacts = w.get("contacts") or []
        who = _contact_label(contacts[0]) if contacts else "decision-maker TBD"
        timing = (w.get("timing") or {}).get("label") or ""
        lines.append(
            f"- {o.company} — fit {int(o.fit_score)} ({o.segment}). "
            f"Signal: {(o.signal or '').strip()[:140]}. Key contact: {who}."
            + (f" Timing: {timing}." if timing else "")
        )
    summary = (
        f"Found and saved {len(saved)} prospect(s) to the Business Dev tab:\n" + "\n".join(lines)
        + "\nFull decision-maker lists (LinkedIn + email), timing and outreach drafts are in Business Dev."
    )
    return {"summary": summary, "assets": []}


async def exec_analyze_company(db, state, brand, args) -> dict:
    """Analyze one named company as a Talentrupt prospect; save it to Business Dev."""
    company = (args.get("company") or "").strip()
    if not company:
        return {"summary": "No company name was provided to analyze.", "assets": []}
    d = await bd_analyze.analyze_company(company, str(args.get("website", "") or ""))
    if not d:
        return {"summary": f"Couldn't analyze {company} right now.", "assets": []}
    o = save_opportunity(db, d, owner=state.get("owner", "admin"))
    w = o.why or {}
    contacts = w.get("contacts") or []
    timing = w.get("timing") or {}
    who = "; ".join(_contact_label(c) for c in contacts[:4] if _contact_label(c)) or "TBD"
    summary = (
        f"{o.company} — fit {int(o.fit_score)} ({o.segment}). "
        f"Signal: {(o.signal or '').strip()[:200]}. "
        f"Why now: {(w.get('why_now') or '')[:200]}. "
        f"Timing: {timing.get('label', '')} — {(timing.get('reason') or '')[:160]}. "
        f"Decision-makers: {who}. Saved to Business Dev for outreach."
    )
    return {"summary": summary, "assets": []}


# --- READ tools: let chat answer questions about what's ALREADY in the app -------------
async def exec_list_prospects(db, state, brand, args) -> dict:
    """READ the prospects in Business Dev. Always reports EXACT counts: the TOTAL prospect count and
    the ★ saved/shortlisted subset — so chat never conflates 'all prospects' with 'saved'."""
    all_rows = (db.query(Opportunity).filter(Opportunity.owner == state.get("owner", "admin"))
                .order_by(Opportunity.fit_score.desc()).all())
    total_all = len(all_rows)
    saved_all = sum(1 for o in all_rows if (o.why or {}).get("saved"))
    rows = all_rows
    status = (args.get("status") or "").strip().lower()
    if status in ("new", "contacted", "replied", "meeting"):
        rows = [o for o in rows if (o.status or "") == status]
    saved_only = bool(args.get("saved_only"))
    if saved_only:
        rows = [o for o in rows if (o.why or {}).get("saved")]
    term = (args.get("query") or "").strip().lower()
    if term:
        rows = [o for o in rows if term in f"{o.company} {o.segment} {o.signal}".lower()]
    matched = len(rows)
    try:
        limit = max(1, min(int(args.get("limit", 50) or 50), 200))
    except (TypeError, ValueError):
        limit = 50
    shown = rows[:limit]
    if total_all == 0:
        return {"summary": "There are 0 prospects in Business Dev yet — use Find prospects "
                "(or ask me to find some) to add them.", "assets": []}
    # State both exact numbers up front so the model answers count questions correctly and never guesses.
    counts = f"Business Dev has {total_all} prospect(s) total; {saved_all} are ★ saved/shortlisted."
    if not shown:
        return {"summary": counts + " None match that filter.", "assets": []}
    lines = [
        f"- {o.company} — fit {int(o.fit_score or 0)} ({o.segment or 'n/a'}); status {o.status}"
        + (" ★saved" if (o.why or {}).get("saved") else "")
        for o in shown
    ]
    if saved_only:
        head = f"{counts}\nThe {matched} ★ saved/shortlisted prospect(s):"
    elif status or term:
        head = f"{counts}\n{matched} match your filter (showing {len(shown)}):"
    else:
        head = f"{counts} Showing {len(shown)}:"
    return {"summary": head + "\n" + "\n".join(lines), "assets": []}


async def exec_list_campaigns(db, state, brand, args) -> dict:
    """READ this account's campaigns, split by TYPE so counts are never conflated:
    INTERNAL = promote Talentrupt (a content folder, no target clients); EXTERNAL = client-targeting
    (a sector + scored target clients). Owner-scoped, and archived campaigns are excluded. Pass
    type='internal'/'external' to answer 'how many internal/external campaigns', or name=... for one
    campaign's target clients."""
    owner = state.get("owner", "admin")
    rows = (db.query(Campaign)
            .filter(Campaign.owner == owner, Campaign.status != "archived")
            .order_by(Campaign.id.desc()).all())
    if not rows:
        return {"summary": "No campaigns have been created yet.", "assets": []}

    # One campaign's clients, looked up by name.
    term = (args.get("name") or "").strip().lower()
    if term:
        match = next((c for c in rows if term in (c.name or "").lower()), None)
        if match:
            if (match.type or "external") == "internal":
                return {"summary": f"'{match.name}' is an INTERNAL (promote-Talentrupt) campaign — a "
                        "content folder, so it has no target clients.", "assets": []}
            sector = (match.strategy or {}).get("sector") or "auto-detected"
            clients = (db.query(CampaignProspect)
                       .filter(CampaignProspect.campaign_id == match.id, CampaignProspect.status == "active")
                       .order_by(CampaignProspect.fit_score.desc()).all())
            cl = [f"- {cp.company} — fit {int(cp.fit_score or 0)}" for cp in clients] or ["- (no active clients yet)"]
            return {"summary": f"'{match.name}' (EXTERNAL) [sector: {sector}] — {len(clients)} active "
                    f"target client(s):\n" + "\n".join(cl), "assets": []}

    internal = [c for c in rows if (c.type or "external") == "internal"]
    external = [c for c in rows if (c.type or "external") != "internal"]

    def _ext_line(c) -> str:
        sector = (c.strategy or {}).get("sector") or ""
        n = (db.query(CampaignProspect)
             .filter(CampaignProspect.campaign_id == c.id, CampaignProspect.status == "active").count())
        return f"- {c.name}" + (f" [{sector}]" if sector else "") + f" — {n} target client(s)"

    want = (args.get("type") or "").strip().lower()
    if want == "internal":
        body = "\n".join(f"- {c.name}" for c in internal) or "(none)"
        return {"summary": f"{len(internal)} INTERNAL (promote-Talentrupt) campaign(s):\n{body}", "assets": []}
    if want == "external":
        body = "\n".join(_ext_line(c) for c in external) or "(none)"
        return {"summary": f"{len(external)} EXTERNAL (client-targeting) campaign(s):\n{body}", "assets": []}

    parts = [f"{len(rows)} campaign(s) total: {len(internal)} INTERNAL (promote Talentrupt) and "
             f"{len(external)} EXTERNAL (client-targeting)."]
    if internal:
        parts.append("INTERNAL:\n" + "\n".join(f"- {c.name}" for c in internal))
    if external:
        parts.append("EXTERNAL:\n" + "\n".join(_ext_line(c) for c in external))
    return {"summary": "\n\n".join(parts), "assets": []}


async def exec_list_assets(db, state, brand, args) -> dict:
    """READ the generated assets (images, decks, PDFs, posts) from Create / past generations."""
    q = db.query(Asset).filter(Asset.owner == state.get("owner", "admin"))  # this account's assets only
    t = (args.get("type") or "").strip().lower()
    if t in ("image", "deck", "pdf", "post"):
        q = q.filter(Asset.type == t)
    rows = q.order_by(Asset.id.desc()).all()
    total = len(rows)
    try:
        limit = max(1, min(int(args.get("limit", 30) or 30), 100))
    except (TypeError, ValueError):
        limit = 30
    shown = rows[:limit]
    if not shown:
        return {"summary": "No generated assets yet — create images, decks, or PDFs in Create (or ask me).",
                "assets": []}
    lines = [f"- [{a.type}] {a.title}" for a in shown]
    head = f"{total} generated asset(s)" + (f" (showing {len(shown)})" if total > len(shown) else "") + ":"
    return {"summary": head + "\n" + "\n".join(lines), "assets": []}


async def exec_list_tasks(db, state, brand, args) -> dict:
    """READ the follow-up reminders in the Tasks tab — grouped overdue / today / upcoming."""
    rows = (db.query(CalendarTask).filter(CalendarTask.owner == state.get("owner", "admin"))
            .order_by(CalendarTask.due_at).all())
    status = (args.get("status") or "").strip().lower()
    if status in ("pending", "done", "snoozed"):
        rows = [t for t in rows if (t.status or "") == status]
    opp_ids = {t.opportunity_id for t in rows if t.opportunity_id}
    companies = (
        {o.id: o.company for o in db.query(Opportunity).filter(Opportunity.id.in_(opp_ids)).all()}
        if opp_ids else {}
    )
    now = datetime.now(timezone.utc)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_today = start_today + timedelta(days=1)
    buckets: dict[str, list[str]] = {"Overdue": [], "Today": [], "Upcoming": [], "Done": []}
    for t in rows:
        co = companies.get(t.opportunity_id)
        label = t.title + (f" — {co}" if co else "")
        due = t.due_at
        if due and due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if (t.status or "") == "done":
            buckets["Done"].append(label)
        elif due and due < start_today:
            buckets["Overdue"].append(f"{label} (was due {due.date()})")
        elif due and due < end_today:
            buckets["Today"].append(label)
        else:
            buckets["Upcoming"].append(label + (f" (due {due.date()})" if due else ""))
    open_n = sum(len(buckets[k]) for k in ("Overdue", "Today", "Upcoming"))
    if open_n == 0 and not buckets["Done"]:
        return {"summary": "No follow-up tasks in the Tasks tab right now.", "assets": []}
    parts = []
    for k in ("Overdue", "Today", "Upcoming"):
        if buckets[k]:
            parts.append(f"{k} ({len(buckets[k])}):\n" + "\n".join(f"  - {x}" for x in buckets[k][:15]))
    head = (f"{open_n} open follow-up task(s)"
            + (f", {len(buckets['Done'])} done" if buckets["Done"] else "") + " in the Tasks tab:")
    return {"summary": head + "\n" + "\n\n".join(parts), "assets": []}


async def exec_get_analytics(db, state, brand, args) -> dict:
    """READ the Analytics rollup (pipeline / outreach / campaigns / content / tasks). Read-only;
    mirrors the /api/analytics/summary KPI definitions so chat and the dashboard agree."""
    _owner = state.get("owner", "admin")
    opps = db.query(Opportunity).filter(Opportunity.owner == _owner).all()
    by_status = {"new": 0, "contacted": 0, "replied": 0, "meeting": 0}
    saved = sent = replied = 0
    for o in opps:
        by_status[o.status if o.status in by_status else "new"] += 1
        why = o.why or {}
        if why.get("saved"):
            saved += 1
        log = why.get("outreach_log") or {}
        if log.get("sent_at") or o.status in ("contacted", "replied", "meeting"):
            sent += 1
        if log.get("replied_at") or o.status in ("replied", "meeting"):
            replied += 1
    campaigns = db.query(Campaign).filter(Campaign.owner == _owner).all()
    planning = sum(1 for c in campaigns if c.status == "planning")
    active_clients = (db.query(CampaignProspect)
                      .join(Campaign, CampaignProspect.campaign_id == Campaign.id)
                      .filter(CampaignProspect.status == "active", Campaign.owner == _owner).count())
    assets_by_type: dict[str, int] = {}
    for (t,) in db.query(Asset.type).filter(Asset.owner == _owner).all():
        assets_by_type[t] = assets_by_type.get(t, 0) + 1
    now = datetime.now(timezone.utc)
    overdue = due_soon = pending = 0
    for tk in db.query(CalendarTask).filter(CalendarTask.status == "pending", CalendarTask.owner == _owner).all():
        pending += 1
        if tk.due_at:
            due = tk.due_at if tk.due_at.tzinfo else tk.due_at.replace(tzinfo=timezone.utc)
            if due < now:
                overdue += 1
            elif due <= now + timedelta(days=7):
                due_soon += 1
    content = ", ".join(f"{v} {k}{'s' if v != 1 else ''}" for k, v in sorted(assets_by_type.items())) or "none yet"
    summary = (
        "Talentrupt analytics snapshot:\n"
        f"- Pipeline: {len(opps)} prospects — {by_status['new']} new, {by_status['contacted']} contacted, "
        f"{by_status['replied']} replied, {by_status['meeting']} meeting; {saved} saved/shortlisted.\n"
        f"- Outreach: {sent} contacted/sent, {replied} replied.\n"
        f"- Campaigns: {len(campaigns)} total ({planning} in planning), {active_clients} active target clients.\n"
        f"- Content generated: {content}.\n"
        f"- Tasks: {pending} open ({overdue} overdue, {due_soon} due within 7 days)."
    )
    return {"summary": summary, "assets": []}


# --- ACTION tools: let chat DO things (mirrors the Business Dev / Tasks / Create endpoints) -------
_PIPELINE_ORDER = ["new", "contacted", "replied", "meeting"]  # mirrors main.py


def _find_opp(db, name: str, owner: str = "admin") -> Opportunity | None:
    """Resolve a saved prospect by company name (exact first, then a contains match) — own account only."""
    name = (name or "").strip().lower()
    if not name:
        return None
    rows = db.query(Opportunity).filter(Opportunity.owner == owner).all()
    return (
        next((o for o in rows if (o.company or "").strip().lower() == name), None)
        or next((o for o in rows if name in (o.company or "").lower()), None)
    )


async def exec_draft_outreach(db, state, brand, args) -> dict:
    """Generate + save outreach for a saved prospect and schedule follow-ups (mirrors POST .../outreach)."""
    target = args.get("company", "")
    o = _find_opp(db, target, state.get("owner", "admin"))
    if not o:
        return {"summary": f"No saved prospect matches \"{target}\". Find or analyze it first, then I can draft outreach.", "assets": []}
    outreach = await bd_outreach.generate_outreach(o)
    why = dict(o.why or {})
    why["outreach"] = outreach
    o.why = why
    if o.status == "new":
        o.status = "contacted"
    db.commit()
    n_fu = 0
    for fu in outreach.get("followups", [])[:2]:
        try:
            days = int(fu.get("day", 3))
        except (TypeError, ValueError):
            days = 3
        db.add(CalendarTask(
            opportunity_id=o.id, owner=state.get("owner", "admin"),
            title=f"Follow up with {o.company}", kind="followup",
            due_at=datetime.now(timezone.utc) + timedelta(days=days),
            payload={"message": fu.get("message", "")},
        ))
        n_fu += 1
    db.commit()
    summary = (
        f"Drafted outreach for {o.company} (saved to Business Dev; status now {o.status}; "
        f"{n_fu} follow-up reminder(s) scheduled — track-only, nothing was sent).\n\n"
        f"SUBJECT: {outreach.get('email_subject','')}\n\n"
        f"EMAIL:\n{outreach.get('email_body','')}\n\n"
        f"LINKEDIN:\n{outreach.get('linkedin_message','')}"
    )
    return {"summary": summary, "assets": []}


async def exec_update_pipeline(db, state, brand, args) -> dict:
    """Record outreach activity + advance pipeline forward-only (mirrors POST .../track). Track-only."""
    target = args.get("company", "")
    o = _find_opp(db, target, state.get("owner", "admin"))
    if not o:
        return {"summary": f"No saved prospect matches \"{target}\".", "assets": []}
    field = {"sent": "sent_at", "contacted": "sent_at", "replied": "replied_at",
             "meeting": "meeting_at"}.get((args.get("event") or "").strip().lower())
    if not field:
        return {"summary": "Tell me what happened: sent, replied, or meeting.", "assets": []}
    why = dict(o.why or {})
    log = dict(why.get("outreach_log") or {})
    history = list(log.get("history") or [])
    now_iso = datetime.now(timezone.utc).isoformat()
    if args.get("channel"):
        log["channel"] = str(args["channel"]).strip()
    if args.get("notes"):
        log["notes"] = str(args["notes"]).strip()
    log[field] = now_iso
    stage = {"sent_at": "contacted", "replied_at": "replied", "meeting_at": "meeting"}[field]
    history.append({"event": field[:-3], "at": now_iso, "channel": log.get("channel", "")})
    cur = o.status if o.status in _PIPELINE_ORDER else "new"
    if _PIPELINE_ORDER.index(stage) > _PIPELINE_ORDER.index(cur):
        o.status = stage
    log["history"] = history
    why["outreach_log"] = log
    o.why = why
    db.commit()
    db.refresh(o)
    return {"summary": f"Logged outreach for {o.company}. Pipeline status: {o.status} (track-only — no email sent).", "assets": []}


async def exec_manage_task(db, state, brand, args) -> dict:
    """Complete or snooze a follow-up task, found by its linked company or title (mirrors PATCH /tasks)."""
    hint = (args.get("company") or args.get("task") or "").strip().lower()
    if not hint:
        return {"summary": "Which follow-up? Name the company (or task) it's for.", "assets": []}
    rows = (db.query(CalendarTask)
            .filter(CalendarTask.status != "done", CalendarTask.owner == state.get("owner", "admin"))
            .order_by(CalendarTask.due_at).all())
    opp_ids = {t.opportunity_id for t in rows if t.opportunity_id}
    companies = (
        {o.id: (o.company or "").lower() for o in db.query(Opportunity).filter(Opportunity.id.in_(opp_ids)).all()}
        if opp_ids else {}
    )
    target = next((t for t in rows if hint in (t.title or "").lower()
                   or hint in companies.get(t.opportunity_id, "")), None)
    if not target:
        return {"summary": f"No open follow-up matches \"{hint}\".", "assets": []}
    pay = dict(target.payload or {})
    if (args.get("action") or "").strip().lower() == "snooze":
        try:
            days = max(1, int(args.get("snooze_days", 3) or 3))
        except (TypeError, ValueError):
            days = 3
        target.due_at = datetime.now(timezone.utc) + timedelta(days=days)
        target.status = "pending"
        pay["snoozed_until"] = target.due_at.isoformat()
        msg = f"Snoozed “{target.title}” for {days} day(s) — now due {target.due_at.date()}."
    else:
        target.status = "done"
        pay["completed_at"] = datetime.now(timezone.utc).isoformat()
        msg = f"Marked “{target.title}” as done."
    target.payload = pay
    db.commit()
    return {"summary": msg, "assets": []}


async def exec_regenerate_asset(db, state, brand, args) -> dict:
    """Regenerate/refine a prior asset, saved as a NEW version (mirrors POST /assets/{id}/regenerate)."""
    a = None
    if args.get("asset_id"):
        try:
            a = db.get(Asset, int(args["asset_id"]))
        except (TypeError, ValueError):
            a = None
    if not a:
        title = (args.get("title") or "").strip().lower()
        if title:
            a = next((x for x in db.query(Asset).order_by(Asset.id.desc()).all()
                      if title in (x.title or "").lower()), None)
    if not a:
        return {"summary": "Tell me which asset to regenerate (its title or id) — I couldn't match one.", "assets": []}
    new = await gen_refine.regenerate_asset(db, a.id, (args.get("instruction") or "").strip(), False)
    if not new:
        return {"summary": f"Couldn't regenerate “{a.title}”.", "assets": []}
    return {"summary": f"Regenerated a new version of “{a.title}” ([{new.type}]) — saved to Create.",
            "assets": [serialize_asset(new)]}


async def exec_animate_asset(db, state, brand, args) -> dict:
    """Animate a finished image/team post into a short MOTION clip — a cinematic zoom/pan over the REAL
    rendered image. The face is NEVER changed (it's the actual post, just animated). Saves a new asset."""
    from ..generation import animate
    a = None
    if args.get("asset_id"):
        try:
            a = db.get(Asset, int(args["asset_id"]))
        except (TypeError, ValueError):
            a = None
    if not a:
        title = (args.get("asset") or args.get("title") or "").strip().lower()
        if title:
            a = next((x for x in db.query(Asset).order_by(Asset.id.desc()).all()
                      if x.type == "image" and title in (x.title or "").lower()), None)
    if not a:  # default to the most recent still image
        a = db.query(Asset).filter(Asset.type == "image").order_by(Asset.id.desc()).first()
    if not a or a.type != "image" or not a.file_path:
        return {"summary": "Tell me which post to animate — I couldn't find a still image to use.",
                "assets": []}
    try:
        path, fname, meta = animate.build_motion(a.file_path)
    except Exception:
        return {"summary": "Couldn't animate that image this time — please try again.", "assets": []}
    new_type = "video" if meta.get("format") == "mp4" else "image"  # gif animates in an <img>
    body = {**(a.body or {}), "animated_from": a.id, "kind": (a.body or {}).get("kind", "")}
    na = _save_asset(db, a.campaign_id or state.get("campaign_id"), new_type, f"{a.title} (animated)"[:380],
                     body=body, file_path=path, file_url=meta["url"], meta={**meta, "parent_id": a.id},
                     owner=getattr(a, "owner", None) or state.get("owner", "admin"))
    return {"summary": f"Animated “{a.title}” into a {meta.get('format', 'clip').upper()} motion post — "
            "a cinematic zoom over the real photo; the face is unchanged.", "assets": [serialize_asset(na)]}


_FEATURE_HEADLINES = ["On a Mission!", "Built to Lead.", "Driven to Deliver.", "Making it Happen!",
                      "In the Spotlight."]


async def _build_one(brand, raw, name, role, headline, subline, style):
    """Render one featured-person post. style 'ai' -> gpt-image-1 background + real cut-out (async);
    otherwise the deterministic navy template. Both keep the REAL face."""
    if style == "ai":
        return await teampost.build_ai_scene(brand, raw, name=name, role=role, headline=headline,
                                             question=subline, variant=random.randint(0, 5))
    return teampost.build_team_image(brand, raw, name=name, role=role, headline=headline,
                                     question=subline, variant=random.randint(0, 5), style=style)


_INSTRUCTION_RE = re.compile(
    r"^\s*(?:please\s+|can\s+you\s+|could\s+you\s+|i\s+(?:want|need|would\s+like)(?:\s+you)?(?:\s+to)?\s+|let'?s\s+|kindly\s+)*"
    r"(?:create|make|generate|build|design|draft|produce|render|do|give\s+me|show\s+me|prepare|put\s+together)\s+"
    r"(?:me\s+)?(?:an?\s+|the\s+|some\s+|a\s+few\s+)?"
    r"(?:image|images|post|posts|visual|visuals|graphic|graphics|picture|photo|creative|design|banner|poster)?s?\s*"
    r"(?:of|for|about|featuring|showing|with|on|that\s+says|saying|to)?\s*",
    re.I,
)


def _clean_headline(message: str, name: str = "") -> str:
    """Turn a raw user request into a clean post headline: drop the person's name and any leading
    'create an image of / make a post about …' instruction phrasing, so the literal prompt is never
    printed as the headline. Returns '' if nothing meaningful remains (caller uses a default headline)."""
    m = (message or "").strip()
    if name:
        m = re.sub(r"\b" + re.escape(name) + r"\b", " ", m, flags=re.I)
    prev = None
    while prev != m:  # peel repeated leading instruction phrases ("create an image of …")
        prev = m
        m = _INSTRUCTION_RE.sub("", m, count=1).strip()
    m = re.sub(r"^(?:of|for|about|featuring|with|on|the)\s+", "", m, flags=re.I)  # leftover preposition
    return re.sub(r"\s+", " ", m).strip(" -,:;.")


async def _polish_headline(message: str) -> str:
    """Rewrite a rough phrase into a SHORT, punchy marketing headline via the LLM — so a deterministic
    @mention (which bypasses the agent) still gets a real headline, not the user's literal words. Best
    effort: returns the input unchanged on any error or when no AI provider is configured."""
    msg = (message or "").strip()
    if not msg or not llm.provider_available():
        return msg
    try:
        out = await llm.chat_json([
            {"role": "system", "content":
             "You write short marketing post headlines for Talentrupt, an RPO (recruitment process "
             "outsourcing) firm. Rewrite the user's rough phrase into ONE punchy headline of 2-5 words, "
             "Title Case, no end punctuation, no quotes — keep their intent. Reply ONLY as JSON: "
             "{\"headline\": \"...\"}."},
            {"role": "user", "content": msg},
        ], temperature=0.5)
        head = ((out or {}).get("headline") or "").strip().strip('"').strip()
        return head[:60] if head else msg
    except Exception:
        return msg


def _find_employee(db, owner: str, query: str):
    """Resolve a Folders employee for `owner` by name — case-insensitive, fuzzy (exact first, then name
    contained-in-query or query-contained-in-name, longest name wins). Returns the Employee or None. The
    single matcher so a person in the Folders photo library is found no matter which tool the agent uses."""
    q = (query or "").strip().lstrip("@").strip().lower()
    if not q:
        return None
    rows = db.query(Employee).filter(Employee.owner == owner).all()
    return (next((e for e in rows if (e.name or "").lower() == q), None)
            or next((e for e in sorted(rows, key=lambda x: -len(x.name or ""))
                     if e.name and ((e.name or "").lower() in q or q in (e.name or "").lower())), None))


async def exec_team_image(db, state, brand, args) -> dict:
    """Feature a REAL Talentrupt person/group: composite their ACTUAL photo into a branded post. Never
    AI-generates a face. Looks in the Folders photo library FIRST (a named employee there), then the
    brand library's legacy Team/ folder; if no photo matches, lists the options."""
    person = (args.get("person") or "").strip()
    message = (args.get("message") or "").strip()
    # Folders photo library is the primary source for a NAMED person now: if `person` is an employee
    # there, feature their stored photo (delegates to feature_employee). Fixes the "no team photos for X
    # in the library" reply when X was actually uploaded to Folders. Brand-library Team/ is the fallback.
    if person:
        _emp = _find_employee(db, state.get("owner", "admin"), person)
        if _emp:
            return await exec_feature_employee(db, state, brand,
                                               {"name": _emp.name, "message": message, "style": (args.get("style") or "")})
    options = retrieve.list_team_photos()
    if not options:
        return {"summary": "There are no team photos on file yet, so I can't feature a real person — and "
                "I won't invent a face. Add the photos to a 'Team/' folder inside the brand library "
                "(named descriptively, e.g. Team/nishant-trivedi-coo.jpg), then re-run the knowledge "
                "import.", "assets": []}
    # Route the request WITHOUT ever silently defaulting to one individual:
    #  - a real named person we have -> their photos;
    #  - a generic 'team'/group request (or a bare message) -> rotate real GROUP shots;
    #  - a name we DON'T have -> ask who (don't substitute someone else).
    query = person or message
    specific = teampost.detect_team_person(query)
    if specific:
        photos = retrieve.person_photos(specific)
    elif person and not teampost.is_group_query(person):
        photos = []
    else:
        photos = teampost.group_photos()
    if not photos:
        labels = ", ".join(sorted({o["label"] for o in options}))
        miss = person or message
        return {"summary": (f"I couldn't match “{miss}” to a team photo. " if miss else
                            "I don't have a group photo on file yet to feature the team. ")
                + f"Available team photos: {labels}. Who should I feature? (I only use the real photos "
                "on file — I never invent a face.)", "assets": []}
    # Decide how many posts and in which FORMAT(s). A specific style honors it; otherwise rotate
    # distinct formats so posts don't all look alike (and count>1 returns options to choose from).
    n = max(1, min(int(args.get("count") or 1), 4))
    style_arg = (args.get("style") or "").strip().lower()
    # A crowd shouldn't be cut out — group posts use the full-photo formats; individuals rotate all.
    if style_arg in teampost.STYLE_NAMES or style_arg == "ai":
        styles = [style_arg] * n
    elif not specific:  # group request -> full real-photo formats (don't cut a crowd onto an AI bg)
        pool = ["magazine", "split"]
        styles = random.sample(pool, k=min(n, len(pool)))
        while len(styles) < n:
            styles.append(random.choice(pool))
    else:  # a named individual, no explicit style -> default to the designed AI scene (rich background)
        styles = ["ai"] * n

    # Strip any "create an image of …" instruction phrasing, then split into headline + supporting subline.
    clean_msg = _clean_headline(message, person)
    msg_head, msg_sub = teampost.split_message(clean_msg) if clean_msg else ("", "")
    assets, used, name, role = [], [], "", ""
    for i in range(n):
        photo = random.choice(photos)  # rotate across this person's real shots
        raw = retrieve.team_reference_bytes(photo["path"])
        if not raw:
            continue
        name, role = teampost.parse_team_label(photo["label"])
        if clean_msg:
            headline, subline = msg_head, msg_sub
        else:
            headline, subline = random.choice(_FEATURE_HEADLINES), ""
        try:
            path, fname, meta = await _build_one(brand, raw, name, role, headline, subline, styles[i])
        except Exception:
            continue
        meta = {**meta, "team_photo": photo["label"]}
        title = f"{name}" + (f" — {role}" if role else "")
        a = _save_asset(db, state.get("campaign_id"), "image", title[:380],
                        body={"person": name, "role": role, "headline": headline, "subline": subline,
                              "kind": "team", "style": styles[i]},
                        file_path=path, file_url=meta["url"], meta=meta,
                        owner=state.get("owner", "admin"))
        assets.append(serialize_asset(a))
        used.append(styles[i])

    if not assets:
        return {"summary": "Couldn't build the team post this time — please try again.", "assets": []}
    fmts = ", ".join(dict.fromkeys(used))
    note = (f" in {len(assets)} different formats ({fmts}) — pick your favourite"
            if len(assets) > 1 else f" ({fmts} format)")
    tip = "" if len(photos) > 1 else \
        " · add more photos of them (same name, e.g. \"…-2.jpg\") for even more variety"
    return {"summary": f"Created {len(assets)} post(s) featuring {name}" + (f" ({role})" if role else "")
            + " — real photos" + note + tip + ".", "assets": assets}


async def exec_feature_uploaded_person(db, state, brand, args) -> dict:
    """Feature a person from a photo the user JUST ATTACHED, using the name/role they gave — composites
    their REAL uploaded photo into the brand template. NEVER changes or AI-generates the face. The app
    doesn't need to 'know' the person: the photo + name come from the user this turn."""
    imgs = (state or {}).get("attachments") or []
    if not imgs:
        return {"summary": "Attach the person's photo first (the 📎 button next to the message box), then "
                "tell me their name (and the message) — I'll build the post from that exact photo and "
                "never change the face.", "assets": []}
    raw = None
    for img in reversed(imgs):  # most-recent usable image
        try:
            with open(img["path"], "rb") as f:
                raw = f.read()
            break
        except Exception:
            continue
    if not raw:
        return {"summary": "I couldn't read the attached photo — please re-attach it and try again.",
                "assets": []}
    name = (args.get("name") or "").strip()
    role = (args.get("role") or "").strip()
    message = (args.get("message") or "").strip()
    head, sub = teampost.split_message(message) if message else (random.choice(_FEATURE_HEADLINES), "")
    n = max(1, min(int(args.get("count") or 1), 4))
    style_arg = (args.get("style") or "").strip().lower()
    if style_arg in teampost.STYLE_NAMES or style_arg == "ai":
        styles = [style_arg] * n
    else:
        styles = ["ai"] * n  # default uploaded-person posts to the designed AI scene
    assets, used = [], []
    for i in range(n):
        try:
            path, fname, meta = await _build_one(brand, raw, name, role, head, sub, styles[i])
        except Exception:
            continue
        meta = {**meta, "uploaded": True}
        title = (name or "Featured") + (f" — {role}" if role else "")
        a = _save_asset(db, state.get("campaign_id"), "image", title[:380],
                        body={"person": name, "role": role, "headline": head, "subline": sub,
                              "kind": "team", "style": styles[i], "uploaded": True},
                        file_path=path, file_url=meta["url"], meta=meta,
                        owner=state.get("owner", "admin"))
        assets.append(serialize_asset(a))
        used.append(styles[i])
    if not assets:
        return {"summary": "Couldn't build the post from that photo — please try again.", "assets": []}
    who = name or "the person in your photo"
    note = (f" in {len(assets)} formats ({', '.join(dict.fromkeys(used))}) to choose from"
            if len(assets) > 1 else "")
    return {"summary": f"Created a post featuring {who}" + (f" ({role})" if role else "")
            + " from your uploaded photo — real face, unchanged" + note + ".", "assets": assets}


async def exec_feature_employee(db, state, brand, args) -> dict:
    """Feature a Talentrupt EMPLOYEE from the Folders photo library by NAME: looks up the employee for
    THIS account, composites their REAL stored photo into the brand template. NEVER AI-generates the
    face. Called when the user @mentions a team member (e.g. '@Nishant ...') or asks to feature one."""
    owner = state.get("owner", "admin")
    name_q = (args.get("name") or "").strip().lstrip("@").strip()
    if not name_q:
        return {"summary": "Tell me which team member to feature — type @ in the box to pick one from "
                "your Folders.", "assets": []}
    rows = db.query(Employee).filter(Employee.owner == owner).all()
    ql = name_q.lower()
    match = (next((e for e in rows if e.name.lower() == ql), None)
             or next((e for e in rows if ql in e.name.lower()), None)
             or next((e for e in rows if e.name.lower() in ql), None))
    if not match:
        avail = ", ".join(e.name for e in rows[:8]) if rows else "no employees yet"
        return {"summary": f'I couldn\'t find "{name_q}" in your Folders. Add them in the Folders section '
                f"first (upload their photo). You have: {avail}.", "assets": []}
    try:
        with open(match.photo_path, "rb") as f:
            raw = f.read()
    except Exception:
        return {"summary": f"I couldn't read {match.name}'s photo — please re-upload it in Folders.",
                "assets": []}
    message = await _polish_headline(_clean_headline((args.get("message") or "").strip(), match.name))
    head, sub = teampost.split_message(message) if message else (random.choice(_FEATURE_HEADLINES), "")
    style_arg = (args.get("style") or "").strip().lower()
    if style_arg in ("ai", "scene"):
        style = "ai"  # AI background + real cut-out (best with rembg installed)
    elif style_arg in teampost.STYLE_NAMES:
        style = style_arg
    else:
        style = random.choice(["magazine", "split", "framed"])  # real-photo templates (no AI face, no rembg)
    try:
        path, fname, meta = await _build_one(brand, raw, match.name, match.role, head, sub, style)
    except Exception:
        return {"summary": "Couldn't build the post — please try again.", "assets": []}
    title = match.name + (f" — {match.role}" if match.role else "")
    a = _save_asset(db, state.get("campaign_id"), "image", title[:380],
                    body={"person": match.name, "role": match.role, "headline": head, "subline": sub,
                          "kind": "team", "style": style, "employee_id": match.id},
                    file_path=path, file_url=meta["url"], meta={**meta, "employee_id": match.id},
                    owner=owner)
    return {"summary": f"Created a post featuring {match.name}"
            + (f" ({match.role})" if match.role else "")
            + " using their real photo from Folders — face unchanged.", "assets": [serialize_asset(a)]}


EXECUTORS = {
    "create_campaign": exec_create_campaign,
    "generate_posts": exec_generate_posts,
    "generate_image": exec_generate_image,
    "generate_team_image": exec_team_image,
    "feature_uploaded_person": exec_feature_uploaded_person,
    "feature_employee": exec_feature_employee,
    "build_deck": exec_build_deck,
    "build_pdf": exec_build_pdf,
    "search_brand_knowledge": exec_search_brand_knowledge,
    "discover_prospects": exec_discover_prospects,
    "analyze_company": exec_analyze_company,
    "list_prospects": exec_list_prospects,
    "list_campaigns": exec_list_campaigns,
    "list_assets": exec_list_assets,
    "list_tasks": exec_list_tasks,
    "get_analytics": exec_get_analytics,
    "draft_outreach": exec_draft_outreach,
    "update_pipeline": exec_update_pipeline,
    "manage_task": exec_manage_task,
    "regenerate_asset": exec_regenerate_asset,
    "animate_asset": exec_animate_asset,
}

# Mode-specific tool sets:
#   chat   -> the all-access assistant: search knowledge, find/analyze prospects, AND generate
#             visuals/decks/PDFs (it also writes all text content directly in its reply)
#   create -> visual/document generation only
CHAT_TOOL_NAMES = [
    "search_brand_knowledge",
    "discover_prospects",
    "analyze_company",
    "list_prospects",
    "list_campaigns",
    "list_assets",
    "list_tasks",
    "get_analytics",
    "draft_outreach",
    "update_pipeline",
    "manage_task",
    "regenerate_asset",
    "animate_asset",
    "create_campaign",
    "generate_posts",
    "generate_image",
    "generate_team_image",
    "feature_uploaded_person",
    "feature_employee",
    "build_deck",
    "build_pdf",
]
CREATE_TOOL_NAMES = ["generate_image", "generate_team_image", "feature_uploaded_person", "feature_employee",
                     "build_deck", "build_pdf", "regenerate_asset", "animate_asset"]
# Internal-campaign content studio: write posts + build every visual/document into the folder.
CAMPAIGN_TOOL_NAMES = ["generate_posts", "generate_image", "generate_team_image",
                       "feature_uploaded_person", "feature_employee", "build_deck", "build_pdf",
                       "regenerate_asset", "animate_asset"]


def tools_for(mode: str) -> tuple[dict, list]:
    names = {"create": CREATE_TOOL_NAMES, "campaign": CAMPAIGN_TOOL_NAMES}.get(mode, CHAT_TOOL_NAMES)
    execs = {n: EXECUTORS[n] for n in names}
    schemas = [s for s in TOOL_SCHEMAS if s["function"]["name"] in names]
    return execs, schemas

# Friendly status labels shown to the user while a tool runs.
STATUS_LABELS = {
    "create_campaign": "Planning the campaign strategy",
    "generate_posts": "Writing on-brand posts",
    "generate_image": "Designing a campaign visual",
    "generate_team_image": "Featuring the team",
    "feature_uploaded_person": "Featuring your photo",
    "feature_employee": "Featuring your team member",
    "build_deck": "Designing presentation slides",
    "build_pdf": "Preparing the document",
    "search_brand_knowledge": "Reviewing past Talentrupt work",
    "discover_prospects": "Searching for matching companies",
    "analyze_company": "Analyzing the company",
    "list_prospects": "Looking up saved companies",
    "list_campaigns": "Reviewing your campaigns",
    "list_assets": "Looking up generated assets",
    "list_tasks": "Checking your follow-up tasks",
    "get_analytics": "Pulling the analytics rollup",
    "draft_outreach": "Writing outreach",
    "update_pipeline": "Updating the pipeline",
    "manage_task": "Updating your tasks",
    "regenerate_asset": "Regenerating the asset",
    "animate_asset": "Animating the post",
}


# --- OpenAI function schemas ---------------------------------------------
def _fn(name, description, properties, required=None):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


TOOL_SCHEMAS = [
    _fn("create_campaign",
        "Create a marketing campaign with a full strategy package. Call this first "
        "when the user wants a campaign or multiple assets that belong together.",
        {
            "name": {"type": "string", "description": "Concise, professional campaign name"},
            "goal": {"type": "string"},
            "audience": {"type": "string"},
            "pillar": {"type": "string", "description": "Messaging pillar/theme"},
            "channels": {"type": "array", "items": {"type": "string"}},
            "timeline": {"type": "string"},
        },
        ["name"]),
    _fn("generate_posts",
        "Write social/marketing post COPY (caption + hashtags + CTA). Attaches to the current "
        "campaign. This is the text/caption only — for a visual use generate_image.",
        {
            "count": {"type": "integer", "description": "How many posts (1-8)"},
            "platform": {"type": "string", "enum": ["Social", "LinkedIn", "Instagram", "Email", "Blog"],
                         "description": "Default 'Social' = a platform-agnostic post (works anywhere). "
                                        "Only set a specific network if the user names one."},
            "angle": {"type": "string", "description": "Theme/angle for the posts"},
        },
        ["count"]),
    _fn("generate_image",
        "Render on-brand image(s) (PNG) for the requested concept.",
        {
            "concept": {"type": "string", "description": "The topic/visual message — be specific to the request"},
            "count": {"type": "integer",
                      "description": "How many distinct variations to render (1-3). Defaults to 1; only set "
                                     "higher when you intend to offer the user multiple options to choose from."},
            "style": {"type": "string",
                      "enum": ["photographic", "editorial_collage", "infographic", "ui_mockup", "typographic", "decorative"],
                      "description": "Optional — set ONLY when the user explicitly chose a visual style; otherwise omit and the art director picks the best fit."},
        },
        ["concept"]),
    _fn("generate_team_image",
        "Create an on-brand post that features a REAL Talentrupt team member or group using their ACTUAL "
        "photo (exact faces) composited into the brand template — NOT an AI-generated face. Use this "
        "whenever the user asks to feature/showcase a specific named person, the founder, the leadership "
        "team, or 'the team'. The photo must already exist in the brand library's Team/ folder; if none "
        "matches, the tool returns the available options to relay — NEVER use generate_image for a real "
        "person and never invent a face.",
        {
            "person": {"type": "string",
                       "description": "Who to feature, as the user said it (e.g. 'the founder', 'Rushikesh', 'the leadership team', 'the whole team')."},
            "message": {"type": "string",
                        "description": "The headline/message for the post (e.g. 'Meet our founder'). Used as the post headline."},
            "style": {"type": "string", "enum": ["spotlight", "magazine", "split", "framed", "ai"],
                      "description": "Optional post FORMAT. Set ONLY when the user picked one: spotlight = "
                                     "person cut out on a designed background; magazine = full real photo + "
                                     "caption band; split = photo beside a text panel; framed = centered "
                                     "spotlight card; ai = real person cut out onto an AI-GENERATED scene "
                                     "(gpt-image-1 makes the background, the real face/body is unchanged) — "
                                     "use when the user asks for an 'AI image / AI background / AI scene'. "
                                     "Omit to rotate the template formats so posts don't all look alike."},
            "count": {"type": "integer",
                      "description": "How many posts to make (1-4). Use 2-4 when the user wants OPTIONS to "
                                     "choose from — each comes back in a different format. Defaults to 1."},
        },
        ["person"]),
    _fn("feature_uploaded_person",
        "Build an on-brand post around a photo the user JUST ATTACHED this turn (an employee's photo), "
        "using the name/role the user gave. Use this whenever the user attaches a PERSON'S photo and "
        "wants a post featuring them (welcome, anniversary, spotlight, congrats). It composites their "
        "REAL attached photo into the brand template and NEVER changes or AI-generates the face — the "
        "app does NOT need to already know the person. Prefer this over generate_image whenever a person "
        "photo is attached. (If the attachment is a style/content reference, not a person to feature, use "
        "generate_image instead.)",
        {
            "name": {"type": "string", "description": "The person's name — exactly as the user gave it, or "
                     "inferred from the conversation context (e.g. a person just discussed). Omit only if "
                     "truly unknown; the post then shows just the photo + message."},
            "role": {"type": "string", "description": "Their role/title if mentioned (e.g. 'Senior Recruiter')."},
            "message": {"type": "string", "description": "The post message/headline (e.g. 'Welcome to the team!', "
                        "'Congrats on 5 years!'). Shown as the headline + subline."},
            "style": {"type": "string", "enum": ["spotlight", "magazine", "split", "framed", "ai"],
                      "description": "Optional format; 'ai' = real face/body cut onto an AI-generated "
                                     "background (use when the user wants an AI image/scene). Omit to rotate."},
            "count": {"type": "integer", "description": "How many posts (1-4); omit for 1."},
        },
        []),
    _fn("feature_employee",
        "Feature a Talentrupt EMPLOYEE from the Folders photo library in a branded post, using their REAL "
        "stored photo (never an AI face). Call this whenever the user @MENTIONS a team member (e.g. "
        "'@Nishant Trivedi welcoming our new clients') or asks to feature/spotlight a specific employee "
        "by name. The employee's photo is already saved in the app's Folders, so you do NOT need an "
        "attachment — pass the name exactly as mentioned and the tool looks them up. Prefer this over "
        "generate_image/feature_uploaded_person when the user references a person by an @mention or by a "
        "name that's in their Folders.",
        {
            "name": {"type": "string", "description": "The employee's name, exactly as @mentioned (e.g. 'Nishant Trivedi'). The leading @ is optional."},
            "message": {"type": "string", "description": "What the post should say / be about (e.g. 'welcoming our newest clients'). Used as the headline + subline."},
            "style": {"type": "string", "enum": ["magazine", "split", "framed", "spotlight", "scene"],
                      "description": "Optional FORMAT. magazine/split/framed/spotlight = the real photo in a branded layout (default, rotates). 'scene' = the person on an AI-generated background — only when the user explicitly asks for an AI scene/background."},
        },
        ["name"]),
    _fn("build_deck",
        "Build a ready-to-present, designed PowerPoint (.pptx) in Talentrupt's deck style. Pass the "
        "audience/tone/depth gathered from the user so the deck is tailored, not generic.",
        {
            "topic": {"type": "string"},
            "slides": {"type": "integer", "description": "Slide count (3-12). Omit to derive from depth."},
            "audience": {"type": "string", "description": "Optional — who the deck is for (e.g. 'healthcare CHROs'); set only when the user indicated it."},
            "tone": {"type": "string", "enum": DOC_TONE,
                     "description": "Optional — the voice/formality the user asked for; omit if unspecified."},
            "depth": {"type": "string", "enum": DOC_DEPTH,
                      "description": "Optional — how deep: concise (~5 slides), standard (~8), in-depth (~12)."},
            "design_theme": {"type": "string", "enum": DOC_THEME,
                             "description": "Optional visual theme; derive from tone (executive→minimal, persuasive→bold, data-driven→data-driven, else editorial). Never invent statistics to suit a theme."},
            "count": {"type": "integer",
                      "description": "How many distinct deck variations to build (1-3). Defaults to 1; only "
                                     "set higher when the user wants multiple options to choose from."},
        },
        ["topic"]),
    _fn("build_pdf",
        "Build a designed PDF document (report, proposal, or one-pager) on a specific topic, with "
        "tailored, brand-grounded content. Pass the audience/tone/depth gathered from the user.",
        {
            "kind": {"type": "string", "enum": ["report", "proposal", "one-pager"],
                     "description": "proposal = client pitch; one-pager = quick leave-behind; report = analysis/briefing."},
            "topic": {"type": "string", "description": "What the document is about — be specific to the request"},
            "audience": {"type": "string", "description": "Optional — who reads it; set only when the user indicated it."},
            "tone": {"type": "string", "enum": DOC_TONE,
                     "description": "Optional — the voice/formality the user asked for; omit if unspecified."},
            "depth": {"type": "string", "enum": DOC_DEPTH,
                      "description": "Optional — concise (one-pager feel), standard, or in-depth."},
            "design_theme": {"type": "string", "enum": DOC_THEME,
                             "description": "Optional visual theme; derive from tone (executive→minimal, persuasive→bold, data-driven→data-driven, else editorial). Never invent statistics to suit a theme."},
            "count": {"type": "integer",
                      "description": "How many distinct document variations to build (1-3). Defaults to 1; only "
                                     "set higher when the user wants multiple options to choose from."},
        },
        ["topic"]),
    _fn("search_brand_knowledge",
        "Search Talentrupt's own past work (posts, magazines, pitch decks, brand guide) "
        "for reference patterns. Use when the user asks what Talentrupt has done before, "
        "or to ground an answer in real past content.",
        {
            "query": {"type": "string", "description": "What to look for"},
            "k": {"type": "integer", "description": "How many results (default 6)"},
        },
        ["query"]),
    _fn("discover_prospects",
        "Find REAL companies that are currently hiring and are strong outbound prospects for "
        "Talentrupt's offshore RPO. Call this whenever the user asks you to find / search / source "
        "prospects, leads, clients, or companies (e.g. 'find a staffing company ready for RPO "
        "support', 'get me healthcare companies hiring at volume'). Results are scored and saved "
        "to the Business Dev tab so the user can act on them.",
        {
            "query": {"type": "string", "description": "Free-text description of the target, e.g. 'US healthcare staffing agencies scaling up'"},
            "industry": {"type": "string"},
            "company_size": {"type": "string", "description": "Employee range, e.g. '1-500'"},
            "location": {"type": "string", "description": "Geography to target. Defaults to the United States — only set this if the user explicitly targets another country."},
            "title": {"type": "string", "description": "Decision-maker title to prioritize"},
            "signal": {"type": "string", "description": "Hiring trigger, e.g. 'Hiring at volume', 'Newly funded', 'Overloaded recruiting team'"},
            "count": {"type": "integer", "description": "How many companies (1-12, default 6)"},
        },
        []),
    _fn("analyze_company",
        "Analyze ONE specific named company as a Talentrupt prospect — fit score, hiring signal, "
        "decision-makers, and whether NOW is a good time to reach out. Saved to Business Dev.",
        {
            "company": {"type": "string", "description": "Company name"},
            "website": {"type": "string", "description": "Website if known"},
        },
        ["company"]),
    _fn("list_prospects",
        "READ the prospects in the Business Dev tab (companies found/analyzed so far). It ALWAYS "
        "reports two exact numbers: the TOTAL prospect count and the ★ saved/shortlisted subset — use "
        "those numbers verbatim, never estimate. Use this whenever the user asks to SEE, LIST, COUNT, "
        "FILTER, or LOOK UP companies/prospects — e.g. 'how many prospects do we have' (the total), "
        "'how many are saved/shortlisted' (set saved_only=true — that's the ★ subset), 'list my saved "
        "companies', or 'what's the status of <company>'. Does NOT find new companies (that's "
        "discover_prospects). NOTE: 'saved'/'shortlisted'/'starred' = the ★ subset; 'prospects'/"
        "'companies' (unqualified) = ALL of them.",
        {
            "status": {"type": "string", "enum": ["new", "contacted", "replied", "meeting"], "description": "Filter by pipeline status"},
            "saved_only": {"type": "boolean", "description": "true = only the ★ saved/shortlisted prospects (a subset of the total)"},
            "query": {"type": "string", "description": "Filter by company name / segment / signal substring"},
            "limit": {"type": "integer", "description": "Max to list (default 50)"},
        },
        []),
    _fn("list_campaigns",
        "READ this account's campaigns, split by TYPE. INTERNAL = promote Talentrupt (content folder, "
        "no clients); EXTERNAL = client-targeting (sector + target clients). ALWAYS pass `type` when the "
        "user asks specifically about internal OR external campaigns, so the count isn't conflated. Pass "
        "`name` for one campaign's target clients. Report the tool's numbers verbatim — never guess.",
        {
            "type": {"type": "string", "enum": ["internal", "external"],
                     "description": "Limit to internal (promote-Talentrupt) or external (client-targeting) campaigns"},
            "name": {"type": "string", "description": "A campaign name (substring) to list that campaign's target clients"},
        },
        []),
    _fn("list_assets",
        "READ the assets already generated (images, decks, PDFs, posts) in Create / past generations. "
        "Use when the user asks what they've generated/created so far, or to list a type of asset.",
        {
            "type": {"type": "string", "enum": ["image", "deck", "pdf", "post"], "description": "Filter by asset type"},
            "limit": {"type": "integer", "description": "Max to list (default 30)"},
        },
        []),
    _fn("list_tasks",
        "READ the follow-up reminders in the Tasks tab (overdue / today / upcoming, each with its "
        "linked company). Use when the user asks what follow-ups, reminders, or to-dos they have, "
        "what's due, what's overdue, or to review the Tasks tab.",
        {
            "status": {"type": "string", "enum": ["pending", "done", "snoozed"], "description": "Filter by task status"},
        },
        []),
    _fn("get_analytics",
        "READ the Analytics dashboard rollup: pipeline funnel by stage, prospects saved, outreach "
        "sent/replied, campaigns, generated content by type, and tasks due. Use for questions like "
        "'how's my pipeline', 'how many meetings do we have', 'what do my analytics look like', or a "
        "status update / summary of the business.",
        {},
        []),
    _fn("draft_outreach",
        "Write ready-to-use outreach (email subject + body, a LinkedIn message, and 2 follow-up "
        "reminders) for a saved prospect, grounded in their hiring signal; saves it to Business Dev and "
        "schedules the follow-up tasks. Track-only — it NEVER sends. Use when the user asks you to "
        "draft/write outreach, an intro email, or a LinkedIn message for a company.",
        {"company": {"type": "string", "description": "The prospect company (must already be saved in Business Dev)"}},
        ["company"]),
    _fn("update_pipeline",
        "Log outreach activity for a saved prospect and advance its pipeline stage "
        "(new->contacted->replied->meeting). Track-only — it records that contact happened, it never "
        "sends anything. Use when the user says they emailed/messaged a prospect, got a reply, or "
        "booked a meeting.",
        {
            "company": {"type": "string", "description": "The prospect company name"},
            "event": {"type": "string", "enum": ["sent", "replied", "meeting"], "description": "What happened"},
            "channel": {"type": "string", "description": "Optional channel, e.g. email or LinkedIn"},
            "notes": {"type": "string", "description": "Optional note"},
        },
        ["company", "event"]),
    _fn("manage_task",
        "Complete or snooze a follow-up reminder in the Tasks tab, identified by the company it's "
        "linked to (or its title). Use when the user says a follow-up is done/handled, or wants to "
        "push one out.",
        {
            "company": {"type": "string", "description": "Company (or task title) the follow-up is for"},
            "action": {"type": "string", "enum": ["done", "snooze"], "description": "Complete or snooze it"},
            "snooze_days": {"type": "integer", "description": "Days to snooze (default 3) when action=snooze"},
        },
        ["company", "action"]),
    _fn("regenerate_asset",
        "Regenerate or refine a previously generated image/deck/PDF with an optional instruction (e.g. "
        "'make the deck punchier', 'new variation'). Saves a NEW version; the original is kept. Use "
        "when the user asks to redo, refine, tweak, or make another version of something already made.",
        {
            "asset_id": {"type": "integer", "description": "The asset id, if known"},
            "title": {"type": "string", "description": "Or match by the asset's title/topic"},
            "instruction": {"type": "string", "description": "Optional change to apply"},
        },
        []),
    _fn("animate_asset",
        "Turn a finished image / team post into a short MOTION clip — a premium cinematic zoom-and-pan "
        "over the REAL rendered image. The person's face is NEVER changed (it's the actual post, just "
        "animated). Use when the user asks to animate a post, add motion, or make a video/reel of it.",
        {
            "asset": {"type": "string", "description": "Which post to animate — the title/topic you "
                      "named for it. Omit to animate the most recent image."},
        },
        []),
]
