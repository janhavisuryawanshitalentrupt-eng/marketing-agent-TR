"""Shared opportunity persistence — used by both the API endpoints and the
chat agent's prospecting tools (kept out of main.py to avoid a circular import)."""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import Opportunity
from .discover import company_linkedin_url, sanitize_contacts


def serialize_opportunity(o: Opportunity) -> dict:
    # Sanitize on READ too, so rows persisted before the anti-fabrication guard (with fake
    # /in/ profile URLs and guessed emails) never reach the UI as if they were verified.
    why = dict(o.why or {})
    company = o.company or ""
    why["contacts"] = sanitize_contacts(company, why.get("contacts"), why.get("website", ""))
    # Provider-VERIFIED contacts live in a separate field (never the sanitized `contacts`); default [].
    why["verified_contacts"] = why.get("verified_contacts") or []
    if why["contacts"]:
        why["decision_maker"] = why["contacts"][0]["role"]  # role only — no AI-guessed name
        why["decision_maker_linkedin"] = why["contacts"][0]["linkedin"]
    else:
        why["decision_maker"] = ""
        why["decision_maker_linkedin"] = ""
    why["decision_maker_email"] = ""
    return {
        "id": o.id,
        "company": o.company,
        "segment": o.segment,
        "fit_score": o.fit_score,
        "hiring_signal": o.signal,
        "pain_point": o.pain_point,
        "recommended_service": o.service,
        "status": o.status,
        "saved": bool((o.why or {}).get("saved")),
        "country": (o.why or {}).get("country", ""),
        "company_linkedin": company_linkedin_url(company),
        "why": why,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


def save_opportunity(db: Session, d: dict) -> Opportunity:
    """Upsert an opportunity by company name."""
    existing = (
        db.query(Opportunity)
        .filter(func.lower(Opportunity.company) == d["company"].strip().lower())
        .first()
    )
    why = {
        "why_fit": d.get("why_fit", ""),
        "why_now": d.get("why_now", ""),
        # Sanitize on WRITE too (not just read): blank any AI-guessed contact names/emails before
        # they ever hit the DB, so no caller can persist fabricated contacts.
        "contacts": sanitize_contacts(d["company"], d.get("contacts", []), d.get("website", "")),
        "timing": d.get("timing", {}),
        "decision_maker": d.get("decision_maker", ""),
        "decision_maker_linkedin": d.get("decision_maker_linkedin", ""),
        "decision_maker_email": d.get("decision_maker_email", ""),
        "website": d.get("website", ""),
        "country": d.get("country", ""),  # HQ country — keeps the USA-default durable on read
        "source": d.get("source", ""),
        "pain_points": d.get("pain_points", []),
    }
    o = existing or Opportunity(company=d["company"][:280], status="new")
    o.segment = d.get("segment", "")
    o.fit_score = d.get("fit_score", 0.0)
    o.signal = d.get("hiring_signal", "")
    o.pain_point = "; ".join(d.get("pain_points", []) or [])
    o.service = d.get("recommended_service", "")
    if existing:  # re-discovery rebuilds `why` — carry forward user/system state that lives only here
        prev = existing.why or {}
        why["outreach"] = prev.get("outreach")
        why["saved"] = prev.get("saved", False)  # never drop a user's ★ shortlist on a re-upsert
        why["outreach_log"] = prev.get("outreach_log")  # keep tracked sent/replied/meeting timeline
        why["verified_contacts"] = prev.get("verified_contacts")  # keep enriched verified contacts
    o.why = why
    if not existing:
        db.add(o)
    db.commit()
    db.refresh(o)
    return o
