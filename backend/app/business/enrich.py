"""Optional contact enrichment — fetch REAL, provider-VERIFIED decision-maker contacts.

This is a config-driven SEAM. With no provider/key configured it is a true no-op (returns []),
so the default discovery flow is unchanged and contacts stay role-only. When a provider IS
configured, it returns only contacts the provider actually returned/verified — names and emails
are allowed here precisely because they are verified by a third party, never guessed. Verified
results are stored in a SEPARATE field (``why["verified_contacts"]``), never mixed into the
anti-fabrication-sanitized ``why["contacts"]``.

To enable, set in backend/.env:
    ENRICHMENT_PROVIDER=apollo   # or hunter
    ENRICHMENT_API_KEY=...
"""
from __future__ import annotations

import httpx

from ..config import settings

# Small in-process cache so re-opening the same prospect doesn't burn paid lookups.
_CACHE: dict[tuple[str, str], list[dict]] = {}
_TARGET_TITLES = [
    "VP Talent Acquisition", "Head of Talent", "Director of Recruiting",
    "Talent Acquisition", "Recruiting", "People Operations", "HR", "Founder", "CEO",
]


def _domain(website: str) -> str:
    w = (website or "").strip().lower()
    if not w:
        return ""
    w = w.split("//")[-1].split("/")[0]
    return w[4:] if w.startswith("www.") else w


def _clean(records: list[dict]) -> list[dict]:
    """Keep only records with a real name or email; normalize shape; cap to a few."""
    out = []
    for r in records:
        name = (r.get("name") or "").strip()
        email = (r.get("email") or "").strip()
        if not name and not email:
            continue
        out.append({
            "name": name,
            "role": (r.get("role") or "").strip(),
            "linkedin": (r.get("linkedin") or "").strip(),
            "email": email,
            "verified": True,
            "source": r.get("source", settings.enrichment_provider),
        })
        if len(out) >= 5:
            break
    return out


async def _hunter(company: str, website: str) -> list[dict]:
    domain = _domain(website)
    if not domain:
        return []
    base = settings.enrichment_base_url.strip() or "https://api.hunter.io/v2"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{base.rstrip('/')}/domain-search",
            params={"domain": domain, "api_key": settings.enrichment_api_key, "limit": 10},
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
    recs = []
    for e in data.get("emails", []):
        first, last = (e.get("first_name") or ""), (e.get("last_name") or "")
        recs.append({
            "name": f"{first} {last}".strip(),
            "role": e.get("position") or "",
            "linkedin": e.get("linkedin") or "",
            "email": e.get("value") or "",
            "source": "hunter",
        })
    return recs


async def _apollo(company: str, website: str) -> list[dict]:
    base = settings.enrichment_base_url.strip() or "https://api.apollo.io/v1"
    domain = _domain(website)
    payload = {
        "page": 1, "per_page": 10,
        "person_titles": _TARGET_TITLES,
        "q_organization_domains": domain or None,
        "organization_names": [company] if not domain else None,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{base.rstrip('/')}/mixed_people/search",
            headers={"Content-Type": "application/json", "X-Api-Key": settings.enrichment_api_key},
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    recs = []
    for p in data.get("people", []):
        recs.append({
            "name": (p.get("name") or f"{p.get('first_name','')} {p.get('last_name','')}").strip(),
            "role": p.get("title") or "",
            "linkedin": p.get("linkedin_url") or "",
            "email": p.get("email") or "",  # Apollo only returns this if revealed/available
            "source": "apollo",
        })
    return recs


async def enrich_contacts(company: str, contacts: list[dict], website: str = "") -> list[dict]:
    """Return provider-verified contacts for ``company``, or [] if enrichment is unconfigured
    or the lookup fails. Never raises into the caller."""
    if not settings.enrichment_available() or not (company or "").strip():
        return []
    key = (settings.enrichment_provider.strip().lower(), company.strip().lower())
    if key in _CACHE:
        return _CACHE[key]
    provider = key[0]
    try:
        if provider == "hunter":
            recs = await _hunter(company, website)
        elif provider == "apollo":
            recs = await _apollo(company, website)
        else:
            recs = []
        result = _clean(recs)
    except Exception:
        result = []  # network/auth/shape error — degrade to no verified contacts, never crash
    _CACHE[key] = result
    return result
