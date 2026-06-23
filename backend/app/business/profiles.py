"""Ideal-customer (ICP) target profiles for Talentrupt outbound.

Both ends of the RPO model: staffing agencies that get overloaded, and companies
hiring directly at volume.
"""
from __future__ import annotations

PROFILES = [
    {
        "key": "overloaded_staffing",
        "label": "Overloaded staffing agencies",
        "description": "Staffing/recruiting agencies with more open requisitions than "
        "internal recruiter capacity — prime to offload sourcing/full-desk work to Talentrupt.",
    },
    {
        "key": "volume_tech_hiring",
        "label": "Companies hiring devs at volume",
        "description": "Companies with many open software/engineering roles (e.g. 20+ "
        "developer openings) who need scalable sourcing without internal overhead.",
    },
    {
        "key": "healthcare_staffing",
        "label": "Healthcare systems & staffing",
        "description": "Healthcare providers and healthcare staffing firms hiring clinicians/"
        "allied roles needing credentialing-aware sourcing and SLA delivery.",
    },
    {
        "key": "high_growth_funded",
        "label": "High-growth / newly funded",
        "description": "Recently funded or fast-scaling companies ramping headcount quickly "
        "who lack recruiting capacity.",
    },
    {
        "key": "it_staffing_sourcers",
        "label": "IT staffing firms needing sourcers",
        "description": "IT/technical staffing firms that need dedicated offshore sourcers to "
        "keep submission pipelines full.",
    },
]


def get_profile(key: str) -> dict | None:
    return next((p for p in PROFILES if p["key"] == key), None)
