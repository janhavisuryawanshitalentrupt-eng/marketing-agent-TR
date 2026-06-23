"""Discover companies with live hiring signals via web-research, score fit for Talentrupt."""
from __future__ import annotations

import re
from urllib.parse import quote

from ..config import settings
from ..providers import llm
from .profiles import get_profile

# --- Reliable, non-fabricated LinkedIn link (or none) ----------------------
# An AI cannot know a person's real profile URL, and LinkedIn's OWN keyword people-search is
# NOT scoped to an employer — "<role> <company>" surfaces unrelated people (the wrong-person
# bug). Instead we build a search-engine X-ray scoped to LinkedIn profiles with the company
# EXACT-QUOTED, and we SUPPRESS the link entirely when the company/role isn't specific enough
# to land on the right person. Bing is the default (less consent/CAPTCHA friction than Google
# on shared office IPs). It never fabricates — it opens a results page of real indexed profiles.
_CORP_SUFFIXES = {
    "inc", "llc", "corp", "ltd", "co", "company", "group", "solutions", "partners", "global",
    "technologies", "technology", "services", "staffing", "recruiting", "recruitment",
    "consulting", "agency", "associates", "holdings", "international", "systems", "enterprises",
    "corporation", "incorporated", "the", "and", "of",
}
# Single-token names that flood LinkedIn with unrelated people (common words + common surnames).
_COMMON_TOKENS = {
    "apex", "summit", "pinnacle", "vertex", "bridge", "catalyst", "stivers", "premier", "vision",
    "core", "elite", "prime", "peak", "horizon", "spectrum", "synergy", "nexus", "fusion", "unity",
    "alliance", "advantage", "select", "preferred", "first", "national", "american", "united",
    "general", "quality", "professional", "corporate", "executive", "strategic", "dynamic",
    "innovative", "creative", "modern", "legacy", "liberty", "freedom", "capital", "century",
    "metro", "valley", "river", "lake", "north", "south", "east", "west", "central", "pacific",
    "atlantic", "smith", "brown", "wolf", "stone", "clark", "wright", "king", "hill", "cole",
    "grant", "reed", "james", "miller", "davis", "jones", "taylor", "anderson", "thomas",
    "jackson", "white", "harris", "martin", "thompson", "garcia", "lewis", "young", "allen",
}
_GENERIC_ROLES = {
    "decision maker", "decision-maker", "owner", "manager", "management", "leadership", "hr",
    "team", "staff", "employee", "contact", "executive", "leader", "head", "founder",
}


def _company_is_distinctive(company: str) -> bool:
    """Will an EXACT-QUOTED X-ray of this company name mostly hit the RIGHT company? A strong
    token (uncommon and >=4 chars) makes it specific; a multi-word name whose tokens don't
    collide with a common word/surname is fine too (e.g. "CCI Staffing"); but a bare common
    word / surname / short acronym ("Stivers", "Apex", "Smith Group") is NOT and is suppressed."""
    all_toks = re.findall(r"[a-z0-9]+", (company or "").lower())
    distinctive = [t for t in all_toks if t not in _CORP_SUFFIXES]
    strong = [t for t in distinctive if t not in _COMMON_TOKENS and len(t) >= 4]
    if strong:
        return True
    if len(all_toks) >= 2 and distinctive and all(t not in _COMMON_TOKENS for t in distinctive):
        return True  # short acronym etc., but the exact-quoted multi-word phrase is specific
    return False


def _role_is_specific(role: str) -> bool:
    r = (role or "").strip().lower()
    return bool(r) and r not in _GENERIC_ROLES


_STRIP_SUFFIXES = {
    "staffing", "recruiting", "recruitment", "agency", "services", "solutions", "consulting",
    "inc", "llc", "corp", "ltd", "co", "company", "incorporated", "corporation", "group",
    "holdings", "international", "enterprises", "labs", "studios", "industries", "ventures",
}


def _search_phrase(company: str) -> str:
    """The phrase to exact-quote in the X-ray. Trim trailing generic suffixes ONLY while a
    multi-word (>=2 token) name remains, so name variants still match — e.g. "Judge Group
    Staffing" -> "Judge Group" matches profiles that say "The Judge Group". Single-word names
    are left intact (their full name is what appears in profiles)."""
    core = company.split()
    while len(core) > 2 and core[-1].strip(".,").lower() in _STRIP_SUFFIXES:
        core.pop()
    return " ".join(core)


def _linkedin_search_url(company: str, role: str, website: str = "") -> str:
    """A LinkedIn-NATIVE people search (lands the rep directly on LinkedIn, where they pick the
    profile) scoped to the company + role, or "" to SUPPRESS the link when it can't be reliable:
    a generic role, or an ambiguous company name (bare common word / surname / short acronym)
    that would surface the WRONG people. The company is exact-quoted to scope to that employer.
    `website` is accepted for a future verified-company-page tier; the gate doesn't depend on it."""
    company = (company or "").strip()
    role = (role or "").strip()
    if not _role_is_specific(role):
        return ""
    if not _company_is_distinctive(company):
        return ""  # e.g. "Stivers" (surname), "Apex" (common word), "Smith Group"
    role_kw = f'"{role}"' if " " in role else role  # phrase-quote multi-word titles to cut noise
    keywords = f'"{_search_phrase(company)}" {role_kw}'
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote(keywords)


def company_linkedin_url(company: str) -> str:
    """A reliable LinkedIn reference to the COMPANY itself (LinkedIn company search), available for
    EVERY prospect. Company search is far less noisy than people search, so the rep lands on the
    company and can open its People tab from there. Returns "" only when there's no company name."""
    company = (company or "").strip()
    if not company:
        return ""
    return "https://www.linkedin.com/search/results/companies/?keywords=" + quote(company)

_FIELDS = (
    'Each item: "company" (name), "website" (url or ""), '
    '"segment" (the company\'s specific industry as free text, e.g. "Healthcare Staffing Agency"), '
    '"sector" (classify the company into EXACTLY ONE of these labels — copy it verbatim: '
    '"IT & Software" (software/SaaS/cloud/platform/tech-product/IT-services companies), '
    '"Healthcare" (hospitals, health systems, clinical/medical orgs), '
    '"Staffing & Recruiting" (staffing/recruiting/talent agencies), '
    '"Finance & Fintech" (banks, fintech, financial-services, insurance, investment), '
    '"Corporate / Non-IT" (ONLY non-tech, non-finance, non-health, non-staffing employers — e.g. '
    'manufacturing, retail, CPG, logistics, hospitality, construction, energy, education). '
    'If a company sells software or is a SaaS/fintech, it is NOT "Corporate / Non-IT" — use IT or '
    'Finance. Pick the single best fit for what the company PRIMARILY is), '
    '"country" (the company\'s HEADQUARTERS country — be honest; if it is based outside the US '
    '(e.g. India, Kuwait, UK), put that country, do NOT default to "United States"), '
    '"hiring_signal" (what/how many roles + where seen), "why_now", '
    '"fit_score" (0-100 integer), "recommended_service", '
    '"contacts" (array of 3-5 SENIOR decision-makers who would actually own a recruiting/RPO '
    'buying decision at THIS specific company — use the REAL job titles that fit THIS company: '
    'the founder/CEO or owner; the senior-most talent/recruiting/HR leader by whatever title they '
    'actually use there (e.g. Head of Recruiting, VP Talent, CHRO, Director of HR, Recruiting '
    'Manager); and 1-2 relevant operations/delivery/finance leaders. TAILOR and VARY the titles to '
    'the company and its size — do NOT return the same generic CEO/COO/CFO/VP-Talent-Acquisition '
    'set every time. No one below Director/Manager. Each object: {"name" (real name if reasonably '
    'known, else ""), "role" (the fitting title), "linkedin" (real LinkedIn PROFILE url if known, '
    'else ""), "email" (best-effort email if reasonably known, else ""; do NOT fabricate)}), '
    '"timing" (object {"reach_now": true|false, "label": one of "Reach now"|"Monitor"|"Hold", '
    '"reason": one short sentence on whether NOW is a good moment to reach out and why}), '
    '"why_fit" (one sentence), "pain_points" (array of short strings).'
)

_TALENTRUPT = (
    "Talentrupt is an offshore RPO (recruitment process outsourcing) firm — it provides "
    "dedicated recruiting/sourcing capacity to (a) staffing agencies that are overloaded "
    "with requisitions and (b) companies hiring at volume that lack internal recruiter "
    "capacity. Services: full life-cycle recruiting, dedicated sourcers, credentialing, "
    "VMS support, healthcare staffing, back-office recruiting ops."
)

# Keep results realistic — a small offshore RPO sells to mid-market & staffing firms, not FAANG.
_ICP_GUARDRAILS = (
    "TARGETING RULES: EXCLUDE household-name mega-caps and Fortune-100 giants (e.g. Google, "
    "Microsoft, Amazon/AWS, Apple, Meta, Oracle, SAP, IBM, Salesforce, Netflix) — they do NOT buy "
    "offshore RPO. Focus on MID-MARKET companies (~50–5,000 employees) and STAFFING/RECRUITING "
    "agencies that are OVERLOADED with requisitions or LACK internal recruiting capacity — where "
    "Talentrupt could realistically win the business.\n"
)
_SCORE_RUBRIC = (
    "FIT SCORE: rate realistic fit for Talentrupt offshore RPO on 0–100 and SPREAD the scores — "
    "reserve 85+ ONLY for an exceptional, clearly-overloaded mid-market or staffing prospect; put "
    "most between 45 and 80; use lower scores for weaker fits. Do NOT cluster scores near one value.\n"
)


def _normalize_role(role: str) -> str:
    """Light, conservative title cleanup so e.g. 'VP, Talent Acquisition' and 'VP Talent
    Acquisition' dedupe to one and read cleanly. Drops parentheticals + stray punctuation only —
    no aggressive rewriting that could mangle a real title."""
    r = re.sub(r"\s*\([^)]*\)", "", str(role or ""))  # drop parentheticals
    r = r.replace(",", " ")
    r = re.sub(r"\s+", " ", r).strip(" ,-–—|/")
    return r


def sanitize_contacts(company: str, contacts: list | None, website: str = "") -> list[dict]:
    """No fake data, ever. An LLM cannot know real people, so we do NOT show AI-guessed NAMES:
    we keep only the ROLE, blank emails, and attach a LinkedIn link ONLY when it can be made
    RELIABLE (see _linkedin_search_url) — otherwise the link is suppressed ("") so the UI shows
    the role alone rather than a search that lands on the wrong person. Idempotent — applied on
    WRITE and READ, so legacy rows with fabricated names/profile-URLs/emails are neutralized too."""
    company = str(company or "").strip()
    out, seen = [], set()
    for c in (contacts or [])[:8]:
        if not isinstance(c, dict):
            continue
        role = _normalize_role(c.get("role", ""))[:120]
        if not role:
            continue  # without a role there is nothing REAL to show (the name is a guess)
        key = role.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "name": "",  # never surface an AI-guessed name
            "role": role,
            "linkedin": _linkedin_search_url(company, role, website),  # "" => link suppressed
            "email": "",
        })
        if len(out) >= 6:
            break
    return out


def _norm_contacts(it: dict) -> list[dict]:
    company = str(it.get("company", "") or "").strip()
    website = str(it.get("website", "") or "").strip()
    out = sanitize_contacts(company, it.get("contacts"), website)
    # Back-compat: build a single contact from the old flat fields if no array.
    if not out and (it.get("decision_maker") or it.get("decision_maker_linkedin")):
        out = sanitize_contacts(
            company, [{"name": "", "role": str(it.get("decision_maker", "") or "")}], website
        )
    return out


def _norm_timing(it: dict) -> dict:
    raw = it.get("timing") if isinstance(it.get("timing"), dict) else {}
    label = str(raw.get("label", "") or "").strip().title()
    if label not in ("Reach Now", "Monitor", "Hold"):
        label = "Reach Now" if raw.get("reach_now") else "Monitor"
    label = {"Reach Now": "Reach now"}.get(label, label)
    return {
        "reach_now": label == "Reach now",  # derive from the final label so the two never disagree
        "label": label,
        "reason": str(raw.get("reason", "") or "").strip()[:300],
    }


_SECTORS = (
    "IT & Software", "Healthcare", "Staffing & Recruiting",
    "Finance & Fintech", "Corporate / Non-IT",
)


_US_TOKENS = {
    "us", "usa", "u.s.", "u.s.a.", "u.s", "united states",
    "united states of america", "america", "united states (usa)",
}


def _norm_country(raw) -> str:
    """Normalize a company HQ country; collapse US variants to 'United States' (else cleaned/"")."""
    c = str(raw or "").strip()
    if not c:
        return ""
    low = c.lower().strip(". ")
    if low in {t.strip(". ") for t in _US_TOKENS} or "united states" in low:
        return "United States"
    return c[:60]


def _is_us_location(loc: str) -> bool:
    """True when an explicit location filter clearly denotes the US (so we can drop non-US)."""
    low = (loc or "").strip().lower()
    if not low:
        return False
    # Regional "...america" phrases are explicitly NON-US — never treat them as US (bias only, no drop).
    if any(p in low for p in ("south america", "latin america", "central america", "north america")):
        return False
    if low in _US_TOKENS:
        return True
    if any(t in low for t in ("united states", "u.s.a", "u.s.", " usa", "usa ")):
        return True
    return low == "america"  # bare "America" reads as the USA colloquially


def _country_is_us_or_unknown(country: str) -> bool:
    """Purity gate for the USA default: keep US companies and ambiguous ones; drop clearly non-US."""
    c = _norm_country(country)
    return c == "" or c == "United States"


def _norm_sector(raw) -> str:
    """Snap the LLM's per-company sector to one of the five canonical labels (else "")."""
    low = str(raw or "").strip().lower()
    if not low:
        return ""
    for sec in _SECTORS:
        if low == sec.lower():
            return sec
    # tolerate minor wording drift
    if "health" in low or "clinical" in low or "medical" in low:
        return "Healthcare"
    if "staffing" in low or "recruit" in low:
        return "Staffing & Recruiting"
    if "fintech" in low or "financ" in low or "bank" in low:
        return "Finance & Fintech"
    if "software" in low or "saas" in low or "technology" in low or low.startswith("it"):
        return "IT & Software"
    if "corporate" in low or "non-it" in low or "non it" in low:
        return "Corporate / Non-IT"
    return ""


def _normalize(items: list, source: str, require_website: bool = False) -> list[dict]:
    out = []
    for it in items or []:
        if not isinstance(it, dict) or not it.get("company"):
            continue
        # Fabrication-reduction heuristic (NOT validation): an un-grounded AI-recalled company
        # with no official website is the most likely to be invented — drop it. The company name
        # is still unverified by design (the UI labels ai_suggested results "verify").
        if require_website and not str(it.get("website", "") or "").strip():
            continue
        try:
            score = float(it.get("fit_score", 0))
        except (TypeError, ValueError):
            # Recover a number from "85%", "85/100", "85 (high)" rather than zeroing the lead.
            m = re.search(r"\d+(?:\.\d+)?", str(it.get("fit_score", "")))
            score = float(m.group()) if m else 0.0
        contacts = _norm_contacts(it)
        primary = contacts[0] if contacts else {}
        dm = ", ".join(x for x in [primary.get("name"), primary.get("role")] if x)
        out.append({
            "company": str(it.get("company", ""))[:280],
            "website": str(it.get("website", "") or ""),
            "segment": str(it.get("segment", "") or ""),
            "sector": _norm_sector(it.get("sector")),
            "country": _norm_country(it.get("country")),
            "hiring_signal": str(it.get("hiring_signal", "") or ""),
            "why_now": str(it.get("why_now", "") or ""),
            "fit_score": max(0.0, min(score, 100.0)),
            "recommended_service": str(it.get("recommended_service", "") or ""),
            "contacts": contacts,
            "timing": _norm_timing(it),
            # back-compat single-contact fields (used by outreach + older UI)
            "decision_maker": dm or str(it.get("decision_maker", "") or ""),
            "decision_maker_linkedin": primary.get("linkedin", ""),
            "decision_maker_email": primary.get("email", ""),
            "why_fit": str(it.get("why_fit", "") or ""),
            "pain_points": [str(p) for p in (it.get("pain_points") or [])][:5],
            "source": source,
        })
    out.sort(key=lambda x: x["fit_score"], reverse=True)
    return out


def _filters_clause(f: dict | None) -> str:
    if not f:
        return ""
    parts = []
    if f.get("industry"):
        parts.append(f"Industry: {f['industry']}.")
    if f.get("company_size"):
        parts.append(f"Company size: {f['company_size']} employees.")
    if f.get("location"):
        parts.append(f"Location/geography: {f['location']}.")
    if f.get("title"):
        parts.append(f"Prioritize companies where the target buyer holds a title like '{f['title']}'.")
    if f.get("signal"):
        parts.append(f"Hiring trigger/signal: prioritize companies that are {f['signal']}.")
    if f.get("keywords"):
        parts.append(f"Keywords/focus: {f['keywords']}.")
    return ("ONLY include companies matching these filters — " + " ".join(parts) + "\n") if parts else ""


async def discover(
    profile_key: str | None, query: str, count: int = 8,
    filters: dict | None = None, exclude: list[str] | None = None,
) -> list[dict]:
    count = max(1, min(count, 12))
    profile = get_profile(profile_key) if profile_key else None
    target = profile["description"] if profile else (query or "companies hiring at volume")
    extra = f" Additional focus: {query}." if (query and profile) else ""

    # The whole app targets the US by default: if no location was given, scope to the US and
    # drop clearly non-US results. An explicit non-US location is respected (no US drop).
    filters = dict(filters or {})
    explicit_loc = (filters.get("location") or "").strip()
    us_only = (not explicit_loc) or _is_us_location(explicit_loc)
    if not explicit_loc:
        filters["location"] = settings.default_location

    def _finalize(items: list, source: str, require_website: bool = False) -> list[dict]:
        out = _normalize(items or [], source=source, require_website=require_website)
        if us_only:
            out = [it for it in out if _country_is_us_or_unknown(it.get("country"))]
        return out

    prompt = (
        f"{_TALENTRUPT}\n\n"
        "PRIORITIZE LINKEDIN as your primary research source — LinkedIn company pages, LinkedIn job "
        "posts, and LinkedIn people are the most trusted signals; corroborate with the open web.\n"
        f"List {count} SPECIFIC, real companies (name each one) that currently appear to be ACTIVELY "
        f"HIRING and are strong outbound prospects for Talentrupt — aim for the full {count}.\n"
        f"Target profile: {target}.{extra}\n"
        + _filters_clause(filters)
        + _ICP_GUARDRAILS
        + _SCORE_RUBRIC
        + (("Do NOT include any of these already-known companies (find DIFFERENT ones): "
            + ", ".join(str(x) for x in exclude[:40]) + ".\n") if exclude else "")
        + "Prefer companies with a concrete, recent hiring signal (LinkedIn job postings, hiring "
        "announcements, funding-driven ramp). Do not invent companies or fabricate numbers.\n"
        f"Return ONLY a JSON array. {_FIELDS}"
    )

    # 1) Live web RESEARCH (grounded, trustworthy). The search model returns prose + citations,
    #    so we structure its findings into JSON with a second call that may use ONLY the companies
    #    it actually named — keeping results web-grounded rather than invented.
    research = ""
    try:
        research = await llm.web_search_text(prompt)
    except Exception:
        research = ""
    if research.strip() and llm.provider_available():
        try:
            data = await llm.chat_json([
                {"role": "system", "content":
                    "From the user's web-research notes below, extract the companies into JSON. "
                    "Return ONLY a JSON object {\"companies\": [...]}. Use ONLY companies EXPLICITLY "
                    "named in the notes — do NOT add, invent, or substitute any others. If the notes "
                    "name no companies, return an empty array. " + _FIELDS},
                {"role": "user", "content": research[:14000]},
            ])
            items = (data or {}).get("companies")
        except Exception:
            items = None
        result = _finalize(items, source="web_research")
        if result:
            return result

    # 3) Constrained general-knowledge fallback — REAL companies ONLY (never invented), each
    #    corroborated by its official website. If nothing qualifies we return [] (honest empty)
    #    rather than present fabricated leads.
    if llm.provider_available():
        try:
            data = await llm.chat_json([
                {"role": "system", "content":
                    "Return ONLY a JSON object with key 'companies' = array. " + _FIELDS +
                    " CRITICAL: only include REAL companies that genuinely exist and that you are "
                    "confident about — do NOT invent, guess, or approximate company names. It is far "
                    "better to return FEWER real companies (even an empty array) than to fabricate. "
                    "Include each company's real official website. These are leads to VERIFY."},
                {"role": "user", "content": prompt},
            ])
        except Exception:
            return []  # honest-empty rather than a 500, consistent with the web-search steps
        items = (data or {}).get("companies")
        return _finalize(items, source="ai_suggested", require_website=True)
    return []
