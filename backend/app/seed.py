"""Seed the single Talentrupt brand record (Talentrupt-only build)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .brand.brand_kit import brand_kit
from .models import Brand


def seed_brand(db: Session) -> None:
    if db.query(Brand).first():
        return
    brand = Brand(
        name="Talentrupt",
        tagline="RPO Done Right",
        voice=(
            "Confident, structured, proof-driven B2B voice for staffing agencies and "
            "hiring-driven companies. Process-first, transparent, and outcome-focused."
        ),
        pillars=[
            "RPO Done Right",
            "Healthcare Staffing Reliability",
            "Engineered Hiring Systems",
            "Scale Without Internal Overhead",
            "Data-Driven Hiring Decisions",
            "Source, Screen, Submit, Place",
            "Myth vs Truth: RPO",
            "Trust-Driven Recruitment",
        ],
        services=[
            "Full life-cycle recruiter",
            "Dedicated sourcer",
            "Credentialing solutions",
            "Hybrid sourcer",
            "Administrative services",
            "Vendor management services",
            "Back-office recruiting operations",
            "Healthcare staffing support",
            "Offshore RPO delivery",
        ],
        proof_points=[
            "500+ healthcare roles filled annually",
            "90% submission-to-interview alignment",
            "80% roles delivered within SLA timelines",
            "95% positive client satisfaction",
            "92% offer acceptance success rate",
        ],
        brand_kit=brand_kit(),
    )
    db.add(brand)
    db.commit()
