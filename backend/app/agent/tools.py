"""Tool registry for the marketing agent.

Each tool has (1) an OpenAI function schema exposed to the model and (2) an
executor that runs a generation engine, persists assets, and returns a result
the model can read plus serialized asset cards for the client.

Executors are plain functions so both the LLM loop and the deterministic
fallback path can call them.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..business import analyze as bd_analyze
from ..business import discover as bd_discover
from ..business.store import save_opportunity
from ..generation import decks, images, pdf, posts, strategy
from ..knowledge import retrieve
from ..models import Asset, Brand, Campaign, CampaignProspect, Opportunity


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
                meta: dict | None = None) -> Asset:
    a = Asset(
        campaign_id=campaign_id, type=type_, title=title[:380], body=body,
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
    if state.get("campaign_id"):
        c = db.get(Campaign, state["campaign_id"])
        if c:
            return c
    c = db.query(Campaign).filter(Campaign.name == QUICK_CONTENT).first()
    if not c:
        c = Campaign(name=QUICK_CONTENT, goal="One-off generated assets", audience="", pillar="")
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
    strat = await strategy.generate_strategy(brand, brief)
    # Reuse an existing same-named campaign instead of creating a duplicate folder.
    existing = (
        db.query(Campaign)
        .filter(func.lower(Campaign.name) == name.strip().lower())
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
            name=name[:280], goal=brief["goal"], audience=brief["audience"],
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
    items = await posts.generate_posts(
        brand, c, count=args.get("count", 3),
        platform=args.get("platform", "LinkedIn"), angle=args.get("angle", ""),
    )
    saved = []
    for p in items:
        a = _save_asset(
            db, c.id, "post", p.get("hook", "Post"),
            body=p, meta={"platform": p.get("platform", "LinkedIn")},
        )
        saved.append(serialize_asset(a))
    return {"summary": f"Wrote {len(saved)} {args.get('platform', 'LinkedIn')} posts.", "assets": saved}


async def exec_generate_image(db, state, brand, args) -> dict:
    concept = args.get("concept", "")
    # Single image per request for now.
    rendered = await images.build_images(brand, None, concept, count=1)
    saved = []
    for path, fname, meta in rendered:
        a = _save_asset(
            db, None, "image", concept or "Campaign visual",
            body={"concept": concept, "layout": meta.get("layout")},
            file_path=path, file_url=meta["url"], meta=meta,
        )
        saved.append(serialize_asset(a))
    return {"summary": "Generated an on-brand image.", "assets": saved}


async def exec_build_deck(db, state, brand, args) -> dict:
    topic = args.get("topic") or "Talentrupt RPO"
    path, fname, meta = await decks.build_deck(
        brand, None, topic, slides=args.get("slides", 6)
    )
    a = _save_asset(
        db, None, "deck", topic,
        body={"topic": topic}, file_path=path,
        file_url=meta["url"], meta=meta,
    )
    return {"summary": f"Built a {meta['slides']}-slide presentation.", "assets": [serialize_asset(a)]}


async def exec_build_pdf(db, state, brand, args) -> dict:
    kind = args.get("kind", "report")
    topic = (args.get("topic") or "").strip()
    # Write tailored, brand-grounded content for the topic (None -> template fallback in build_pdf).
    outline = await pdf.generate_pdf_outline(brand, topic, kind) if topic else None
    path, fname, meta = pdf.build_pdf(brand, None, kind=kind, topic=topic, outline=outline)
    title = (topic or f"Talentrupt — {kind}")[:120]
    a = _save_asset(
        db, None, "pdf", title,
        body={"kind": kind, "topic": topic}, file_path=path,
        file_url=meta["url"], meta=meta,
    )
    return {
        "summary": f"Created a {kind} PDF" + (f" on “{topic}”." if topic else "."),
        "assets": [serialize_asset(a)],
    }


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
    saved = [save_opportunity(db, it) for it in items]
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
    o = save_opportunity(db, d)
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
    """READ the companies already saved in Business Dev (the prospects found/analyzed so far)."""
    rows = db.query(Opportunity).order_by(Opportunity.fit_score.desc()).all()
    status = (args.get("status") or "").strip().lower()
    if status in ("new", "contacted", "replied", "meeting"):
        rows = [o for o in rows if (o.status or "") == status]
    if args.get("saved_only"):
        rows = [o for o in rows if (o.why or {}).get("saved")]
    term = (args.get("query") or "").strip().lower()
    if term:
        rows = [o for o in rows if term in f"{o.company} {o.segment} {o.signal}".lower()]
    total = len(rows)
    try:
        limit = max(1, min(int(args.get("limit", 50) or 50), 200))
    except (TypeError, ValueError):
        limit = 50
    shown = rows[:limit]
    if not shown:
        return {"summary": "No matching companies are saved in Business Dev yet — use Find prospects "
                "(or ask me to find some) to add them.", "assets": []}
    lines = [
        f"- {o.company} — fit {int(o.fit_score or 0)} ({o.segment or 'n/a'}); status {o.status}"
        + (" ★saved" if (o.why or {}).get("saved") else "")
        for o in shown
    ]
    head = (f"{total} compan{'y' if total == 1 else 'ies'} saved in Business Dev"
            + (f" (showing top {len(shown)})" if total > len(shown) else "") + ":")
    return {"summary": head + "\n" + "\n".join(lines), "assets": []}


async def exec_list_campaigns(db, state, brand, args) -> dict:
    """READ the planned campaigns + their target-client counts (or one campaign's clients)."""
    camps = (
        db.query(Campaign).filter(Campaign.status == "planning")
        .order_by(Campaign.id.desc()).all()
    )
    if not camps:
        return {"summary": "No campaigns have been planned yet.", "assets": []}
    term = (args.get("name") or "").strip().lower()
    if term:
        match = next((c for c in camps if term in (c.name or "").lower()), None)
        if match:
            sector = (match.strategy or {}).get("sector") or "auto-detected"
            clients = (
                db.query(CampaignProspect)
                .filter(CampaignProspect.campaign_id == match.id, CampaignProspect.status == "active")
                .order_by(CampaignProspect.fit_score.desc()).all()
            )
            cl = [f"- {cp.company} — fit {int(cp.fit_score or 0)}" for cp in clients] or ["- (no active clients yet)"]
            return {"summary": f"Campaign '{match.name}' [sector: {sector}] — {len(clients)} active "
                    f"target client(s):\n" + "\n".join(cl), "assets": []}
    lines = []
    for c in camps:
        sector = (c.strategy or {}).get("sector") or ""
        n = (
            db.query(CampaignProspect)
            .filter(CampaignProspect.campaign_id == c.id, CampaignProspect.status == "active").count()
        )
        lines.append(f"- {c.name}" + (f" [{sector}]" if sector else "") + f" — {n} target client(s)")
    return {"summary": f"{len(camps)} campaign(s):\n" + "\n".join(lines), "assets": []}


async def exec_list_assets(db, state, brand, args) -> dict:
    """READ the generated assets (images, decks, PDFs, posts) from Create / past generations."""
    q = db.query(Asset)
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


EXECUTORS = {
    "create_campaign": exec_create_campaign,
    "generate_posts": exec_generate_posts,
    "generate_image": exec_generate_image,
    "build_deck": exec_build_deck,
    "build_pdf": exec_build_pdf,
    "search_brand_knowledge": exec_search_brand_knowledge,
    "discover_prospects": exec_discover_prospects,
    "analyze_company": exec_analyze_company,
    "list_prospects": exec_list_prospects,
    "list_campaigns": exec_list_campaigns,
    "list_assets": exec_list_assets,
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
    "create_campaign",
    "generate_posts",
    "generate_image",
    "build_deck",
    "build_pdf",
]
CREATE_TOOL_NAMES = ["generate_image", "build_deck", "build_pdf"]


def tools_for(mode: str) -> tuple[dict, list]:
    names = CREATE_TOOL_NAMES if mode == "create" else CHAT_TOOL_NAMES
    execs = {n: EXECUTORS[n] for n in names}
    schemas = [s for s in TOOL_SCHEMAS if s["function"]["name"] in names]
    return execs, schemas

# Friendly status labels shown to the user while a tool runs.
STATUS_LABELS = {
    "create_campaign": "Planning the campaign strategy",
    "generate_posts": "Writing on-brand posts",
    "generate_image": "Designing a campaign visual",
    "build_deck": "Designing presentation slides",
    "build_pdf": "Preparing the document",
    "search_brand_knowledge": "Reviewing past Talentrupt work",
    "discover_prospects": "Searching for matching companies",
    "analyze_company": "Analyzing the company",
    "list_prospects": "Looking up saved companies",
    "list_campaigns": "Reviewing your campaigns",
    "list_assets": "Looking up generated assets",
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
        "Generate social/marketing posts (LinkedIn, Instagram, email). Attaches to the "
        "current campaign.",
        {
            "count": {"type": "integer", "description": "How many posts (1-8)"},
            "platform": {"type": "string", "enum": ["LinkedIn", "Instagram", "Email", "Blog"]},
            "angle": {"type": "string", "description": "Theme/angle for the posts"},
        },
        ["count"]),
    _fn("generate_image",
        "Render one on-brand image (PNG) for the requested concept.",
        {
            "concept": {"type": "string", "description": "The topic/visual message — be specific to the request"},
        },
        ["concept"]),
    _fn("build_deck",
        "Build a ready-to-present PowerPoint (.pptx) in Talentrupt's deck style.",
        {
            "topic": {"type": "string"},
            "slides": {"type": "integer", "description": "Slide count (3-12)"},
        },
        ["topic"]),
    _fn("build_pdf",
        "Build a PDF document (campaign report, proposal, or one-pager) on a specific topic, "
        "with tailored content grounded in Talentrupt's brand.",
        {
            "kind": {"type": "string", "enum": ["report", "proposal", "one-pager"]},
            "topic": {"type": "string", "description": "What the document is about — be specific to the request"},
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
        "READ the companies ALREADY saved in the Business Dev tab (prospects found/analyzed so far). "
        "Use this whenever the user asks to SEE, LIST, COUNT, FILTER, or LOOK UP existing / saved / "
        "generated companies or prospects — e.g. 'list all the companies generated so far', 'how many "
        "prospects do we have', 'show my saved companies', 'what's the status of <company>'. This does "
        "NOT find new companies (that's discover_prospects).",
        {
            "status": {"type": "string", "enum": ["new", "contacted", "replied", "meeting"], "description": "Filter by pipeline status"},
            "saved_only": {"type": "boolean", "description": "Only the starred/shortlisted prospects"},
            "query": {"type": "string", "description": "Filter by company name / segment / signal substring"},
            "limit": {"type": "integer", "description": "Max to list (default 50)"},
        },
        []),
    _fn("list_campaigns",
        "READ the planned campaigns and their target-client counts. Use when the user asks what "
        "campaigns exist, or to see/count the target clients of a campaign (pass `name` for one "
        "campaign's clients).",
        {
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
]
