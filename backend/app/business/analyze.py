"""Analyze a specific company (manual intake) as a Talentrupt prospect."""
from __future__ import annotations

from ..providers import llm
from .discover import _FIELDS, _TALENTRUPT, _normalize


async def analyze_company(company: str, website: str = "") -> dict | None:
    site = f" (website: {website})" if website else ""
    prompt = (
        f"{_TALENTRUPT}\n\n"
        "Talentrupt sells into the US market: US-based companies are the default ICP, and a "
        "company's US hiring footprint is part of the fit (a firm with no US presence is a weaker "
        "fit). Include the company's HQ country in the `country` field.\n"
        f"Analyze the company '{company}'{site} as an outbound prospect for Talentrupt, "
        "using recent real web information about their hiring activity where possible.\n"
        "Pay special attention to TIMING: judge whether NOW is a good moment to reach out "
        "(e.g. active hiring surge, fresh funding, expansion, leadership change = reach now; "
        "hiring freeze, recent layoffs, just signed an RPO = hold/monitor) and explain why.\n"
        "FIT SCORE: rate realistic fit for Talentrupt offshore RPO on 0–100 — be honest, not "
        "generous. A household-name mega-cap that runs its own recruiting in-house is a WEAK fit "
        "(score low); an overloaded mid-market or staffing firm hiring at volume is a STRONG fit. "
        "Reserve 85+ for a clearly exceptional fit.\n"
        "Return ONLY a JSON OBJECT (not an array) with these keys for this one company. "
        + _FIELDS.replace("Each item:", "Keys:")
        + " Do not fabricate specifics; if hiring activity is unknown, say so in hiring_signal."
    )
    def _one(data):
        # The search model often wraps a single company in a one-element array — unwrap it
        # rather than discarding the web-grounded result.
        if isinstance(data, list) and data and isinstance(data[0], dict):
            data = data[0]
        return data if isinstance(data, dict) else None

    try:
        data = _one(await llm.web_search_json(prompt))
        if data is not None:
            data.setdefault("company", company)
            res = _normalize([data], source="web_research")
            if res:
                return res[0]
    except Exception:
        pass

    if llm.provider_available():
        data = _one(await llm.chat_json([
            {"role": "system", "content": "Return ONLY a JSON object for the company analysis "
             "with the requested keys. Base on general knowledge; flag as unverified."},
            {"role": "user", "content": prompt},
        ]))
        if data is not None:
            data.setdefault("company", company)
            res = _normalize([data], source="ai_suggested")
            if res:
                return res[0]
    return None
