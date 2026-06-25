"""Talentrupt PDF builder (report / proposal / one-pager) via reportlab.

Designed, not plain: a canvas-painted cover/hero, page chrome (logo + footer + page number), section
dividers, proof-point METRIC CARDS (rendered ONLY from real brand.proof_points — the anti-fabrication
gate), callout boxes, optional two-column bodies, and a closing CTA panel. The document is tailored by
the gathered brief (audience / tone / depth) and the visual theme (design_theme); the structure differs
by `kind`.

Two content paths:
- topic-driven (Create / Chat): an LLM writes a tailored, brand-grounded outline via
  ``generate_pdf_outline`` so each document is specific to the request — not a repeated template.
- campaign-driven (campaign milestones): renders the campaign's structured strategy with the same chrome.

All dynamic text is XML-escaped because reportlab's Paragraph parses an XML-ish subset.
"""
from __future__ import annotations

import re
from datetime import date
from xml.sax.saxutils import escape as _xml_escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image as RLImage,
    KeepInFrame,
    KeepTogether,
    ListFlowable,
    ListItem,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from ..knowledge import retrieve
from ..models import Brand, Campaign
from ..providers import llm
from .common import logo_path, public_url, storage_subdir, unique_name

NAVY = colors.HexColor("#0B3559")
RED = colors.HexColor("#F6404C")
CREAM = colors.HexColor("#EBE9DF")
INK = colors.HexColor("#222222")
HAIRLINE = colors.HexColor("#D9D7CE")

KIND_LABELS = {
    "proposal": "Campaign Proposal",
    "one-pager": "Service One-Pager",
    "report": "Executive Report",
}

# design_theme → visual accents. Navy/red/cream + logo are ALWAYS on-brand; the theme only re-weights
# the accent colour, rule weight, card fill/text and title scale so documents vary without going off-brand.
PDF_THEMES = {
    "editorial": {"accent": RED, "rule": 2.0, "card_fill": CREAM, "card_text": NAVY, "title": 32},
    "minimal": {"accent": NAVY, "rule": 0.9, "card_fill": colors.HexColor("#F4F3EE"), "card_text": NAVY, "title": 30},
    "bold": {"accent": RED, "rule": 4.0, "card_fill": NAVY, "card_text": CREAM, "title": 38},
    "data-driven": {"accent": RED, "rule": 2.0, "card_fill": CREAM, "card_text": NAVY, "title": 30},
}


def _theme(name: str) -> dict:
    return PDF_THEMES.get((name or "").strip().lower(), PDF_THEMES["editorial"])


def _esc(text) -> str:
    """reportlab Paragraph parses an XML-ish subset; escape dynamic text so &, <, > are safe."""
    return _xml_escape(str(text if text is not None else ""))


def _styles(theme: dict, tone: str = "") -> dict:
    ss = getSampleStyleSheet()
    body_leading = {"executive": 16, "data-driven": 13.5, "conversational": 16.5}.get(tone, 15)
    title_size = theme["title"] + (2 if tone == "executive" else 0)
    ct = theme["card_text"]
    return {
        "title": ParagraphStyle("trTitle", parent=ss["Title"], textColor=NAVY, fontSize=title_size,
                                 leading=title_size + 4, spaceAfter=4),
        "kicker": ParagraphStyle("trKick", parent=ss["Normal"], textColor=theme["accent"],
                                 fontName="Helvetica-Bold", fontSize=9, leading=12, spaceAfter=2),
        "sub": ParagraphStyle("trSub", parent=ss["Normal"], textColor=theme["accent"], fontSize=12, spaceAfter=12),
        "h2": ParagraphStyle("trH2", parent=ss["Heading2"], textColor=NAVY, fontName="Helvetica-Bold",
                             fontSize=15, spaceBefore=14, spaceAfter=2),
        "body": ParagraphStyle("trBody", parent=ss["Normal"], textColor=INK, fontSize=10.5,
                               leading=body_leading, alignment=TA_LEFT, spaceAfter=6),
        "card_num": ParagraphStyle("trCardNum", parent=ss["Normal"], textColor=ct,
                                   fontName="Helvetica-Bold", fontSize=22, leading=24),
        "card_label": ParagraphStyle("trCardLbl", parent=ss["Normal"], textColor=ct, fontSize=9.5, leading=12),
        "callout": ParagraphStyle("trCallout", parent=ss["Normal"], textColor=NAVY,
                                  fontName="Helvetica-Oblique", fontSize=13, leading=18),
        "cta_h": ParagraphStyle("trCtaH", parent=ss["Normal"], textColor=CREAM, fontName="Helvetica-Bold",
                                fontSize=18, leading=22),
        "cta_sub": ParagraphStyle("trCtaSub", parent=ss["Normal"], textColor=CREAM, fontSize=11,
                                  leading=15, spaceBefore=2),
    }


# --- Anti-fabrication metric gate -----------------------------------------
def _split_proof_point(p: str) -> tuple[str, str]:
    """Split a proof point into (number, label). Returns ('', label) when there's no leading number,
    so cards only ever render REAL figures. e.g. '90% submission-to-interview alignment' -> ('90%', ...)."""
    raw = " ".join(str(p or "").split())
    m = re.match(r"[~<>$€£]?\d[\d,.]*\s*(?:%|\+|x|×|k|m|b|bn|hrs?|days?|hours?)*\+?", raw, re.I)
    if m and m.group().strip():
        return m.group().strip(), raw[m.end():].strip(" .,:;–—-")
    return "", raw


def _pick_metrics(outline: dict, brand: Brand | None) -> list[tuple[str, str]]:
    """Select up to 3 metric cards. ONLY real brand.proof_points qualify: any LLM-named metric must be an
    EXACT member of the list, else it's dropped; if the model named none, fall back to the real proofs."""
    proofs = list(brand.proof_points) if brand and brand.proof_points else []
    chosen: list[str] = []
    for m in (outline.get("metrics") or []):
        if isinstance(m, str) and m in proofs and m not in chosen:
            chosen.append(m)
    if not chosen:
        chosen = proofs[:3]
    cards: list[tuple[str, str]] = []
    for p in chosen:
        num, label = _split_proof_point(p)
        if num:  # only entries with a real number become a card
            cards.append((num, label or p))
    return cards[:3]


# --- Flowable components ---------------------------------------------------
# Each builder returns a LIST of flowables. `_emit` wraps them in KeepTogether for multi-page docs (so a
# block never splits across pages) but appends them flat for the one-pager, which is wrapped in a single
# KeepInFrame (KeepInFrame cannot contain KeepTogether — it raises at draw time).
def _emit(flow: list, parts: list, keep: bool):
    parts = [p for p in parts if p is not None]
    if not parts:
        return
    if keep:
        flow.append(KeepTogether(parts))
    else:
        flow.extend(parts)


def _divider_parts(st: dict, theme: dict, heading: str, kicker: str = "") -> list:
    block = []
    if kicker:
        block.append(Paragraph(_esc(kicker.upper()), st["kicker"]))
    block.append(Paragraph(_esc(heading), st["h2"]))
    block.append(HRFlowable(width=120, thickness=theme["rule"], color=theme["accent"],
                            spaceBefore=2, spaceAfter=6, hAlign="LEFT"))
    return block


def _bullets(bullets: list, st: dict, theme: dict):
    items = [ListItem(Paragraph(_esc(b), st["body"]), leftIndent=10) for b in bullets if str(b).strip()]
    return ListFlowable(items, bulletType="bullet", bulletColor=theme["accent"]) if items else Spacer(0, 0)


def _two_col(bullets: list, st: dict, bw: float) -> list:
    pts = [b for b in bullets if str(b).strip()]
    mid = (len(pts) + 1) // 2
    gap = 18
    cw = (bw - gap) / 2

    def cell(items):
        return Paragraph("<br/>".join("• " + _esc(b) for b in items), st["body"]) if items else Spacer(0, 0)

    t = Table([[cell(pts[:mid]), cell(pts[mid:])]], colWidths=[cw, cw])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (0, 0), (0, 0), gap),
        ("LEFTPADDING", (1, 0), (1, 0), gap), ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [Spacer(1, 2), t, Spacer(1, 8)]


def _one_card(num: str, label: str, cw: float, st: dict, theme: dict):
    t = Table([[Paragraph(_esc(num), st["card_num"])], [Paragraph(_esc(label), st["card_label"])]],
              colWidths=[cw])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), theme["card_fill"]),
        ("LINEABOVE", (0, 0), (-1, 0), max(2.0, theme["rule"]), theme["accent"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 12), ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 0), ("BOTTOMPADDING", (0, 1), (-1, 1), 14),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


def _metric_cards(cards: list, st: dict, theme: dict, bw: float) -> list:
    if not cards:
        return []
    n = len(cards)
    gap = 12
    cw = (bw - gap * (n - 1)) / n
    row, widths = [], []
    for i, (num, label) in enumerate(cards):
        if i:
            row.append(Spacer(0, 0))
            widths.append(gap)
        row.append(_one_card(num, label, cw, st, theme))
        widths.append(cw)
    outer = Table([row], colWidths=widths)
    outer.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return [Spacer(1, 6), outer, Spacer(1, 14)]


def _callout(text: str, st: dict, theme: dict, bw: float) -> list:
    t = Table([[Paragraph(_esc(text), st["callout"])]], colWidths=[bw])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), CREAM),
        ("LINEBEFORE", (0, 0), (0, -1), 4, theme["accent"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 16), ("RIGHTPADDING", (0, 0), (-1, -1), 16),
        ("TOPPADDING", (0, 0), (-1, -1), 12), ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))
    return [Spacer(1, 6), t, Spacer(1, 12)]


def _cta_panel(headline: str, subtext: str, st: dict, theme: dict, bw: float) -> list:
    rows = [[Paragraph(_esc(headline), st["cta_h"])]]
    if subtext:
        rows.append([Paragraph(_esc(subtext), st["cta_sub"])])
    t = Table(rows, colWidths=[bw])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("LINEABOVE", (0, 0), (-1, 0), 4, theme["accent"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 20), ("RIGHTPADDING", (0, 0), (-1, -1), 20),
        ("TOPPADDING", (0, 0), (0, 0), 18), ("BOTTOMPADDING", (0, -1), (-1, -1), 18),
    ]))
    return [Spacer(1, 16), t]


def _masthead(st: dict, theme: dict, title: str, subtitle: str, kicker: str, bw: float) -> list:
    """Top-of-page banner used when there is no separate cover (one-pager / campaign docs)."""
    out: list = []
    try:
        out.append(RLImage(str(logo_path()), width=0.5 * inch, height=0.5 * inch))
    except Exception:
        pass
    if kicker:
        out.append(Paragraph(_esc(kicker.upper()), st["kicker"]))
    out.append(Paragraph(_esc(title), st["title"]))
    if subtitle:
        out.append(Paragraph(_esc(subtitle), st["sub"]))
    out.append(HRFlowable(width="100%", thickness=theme["rule"], color=theme["accent"], spaceBefore=4, spaceAfter=10))
    return out


# --- Canvas page chrome (painted per page via onPage callbacks) -----------
def _wrap_canvas_text(canvas, text: str, font: str, size: float, max_w: float) -> list:
    words = str(text or "").split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if canvas.stringWidth(trial, font, size) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _paint_cover(canvas, doc):
    c = canvas
    W, H = letter
    th = doc._theme
    cov = getattr(doc, "_cover", {})
    c.saveState()
    try:
        c.setFillColor(NAVY)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setFillColor(th["accent"])
        c.rect(0, 0, 0.18 * inch, H, fill=1, stroke=0)  # accent spine
        try:
            c.drawImage(str(logo_path()), 0.9 * inch, H - 1.7 * inch, width=0.7 * inch, height=0.7 * inch, mask="auto")
        except Exception:
            pass
        c.setFillColor(CREAM)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(1.75 * inch, H - 1.38 * inch, "TALENTRUPT")
        c.setFillColor(th["accent"])
        c.setFont("Helvetica-Bold", 11)
        c.drawString(0.9 * inch, H - 3.0 * inch, (cov.get("kicker") or "").upper()[:60])
        title_lines = _wrap_canvas_text(c, cov.get("title", ""), "Helvetica-Bold", 30, W - 1.9 * inch)
        y = H - 3.45 * inch
        c.setFillColor(colors.white)
        for ln in title_lines[:5]:
            c.setFont("Helvetica-Bold", 30)
            c.drawString(0.9 * inch, y, ln)
            y -= 36
        c.setFillColor(th["accent"])
        c.rect(0.92 * inch, y - 2, 2.0 * inch, 4, fill=1, stroke=0)
        if cov.get("subtitle"):
            c.setFillColor(CREAM)
            yy = y - 26
            for ln in _wrap_canvas_text(c, cov["subtitle"], "Helvetica", 13, W - 1.9 * inch)[:3]:
                c.setFont("Helvetica", 13)
                c.drawString(0.92 * inch, yy, ln)
                yy -= 17
        c.setFillColor(CREAM)
        c.setFont("Helvetica", 9)
        c.drawString(0.92 * inch, 0.7 * inch, f"{cov.get('date', '')}   ·   RPO Done Right")
    except Exception:
        pass
    c.restoreState()


def _paint_body_chrome(canvas, doc):
    c = canvas
    W, H = letter
    th = doc._theme
    c.saveState()
    try:
        c.setStrokeColor(th["accent"])
        c.setLineWidth(2)
        c.line(0.9 * inch, H - 0.62 * inch, W - 0.9 * inch, H - 0.62 * inch)
        try:
            c.drawImage(str(logo_path()), 0.9 * inch, H - 0.56 * inch, width=0.28 * inch, height=0.28 * inch, mask="auto")
        except Exception:
            pass
        c.setFillColor(NAVY)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(1.28 * inch, H - 0.47 * inch, "TALENTRUPT")
        c.setStrokeColor(HAIRLINE)
        c.setLineWidth(0.5)
        c.line(0.9 * inch, 0.62 * inch, W - 0.9 * inch, 0.62 * inch)
        c.setFillColor(NAVY)
        c.setFont("Helvetica", 8)
        c.drawString(0.9 * inch, 0.46 * inch, "Talentrupt · RPO Done Right")
        c.drawRightString(W - 0.9 * inch, 0.46 * inch, str(c.getPageNumber()))
    except Exception:
        pass
    c.restoreState()


# --- Outline (LLM) --------------------------------------------------------
_PDF_TONE_VOICE = {
    "executive": "boardroom-level: concise, confident, lead with the outcome",
    "professional": "polished, credible US B2B (the default)",
    "conversational": "direct and warm — address the reader as 'you'",
    "persuasive": "sales-forward — build toward a strong close and a clear ask",
    "data-driven": "tight and evidence-led — foreground the single most relevant REAL proof point",
}


def _pdf_directives(audience: str, tone: str) -> str:
    lines = []
    if audience:
        lines.append(f"Write for this reader: {audience}. Frame the problem, examples and CTA for them.")
    if tone and tone in _PDF_TONE_VOICE:
        lines.append(f"Voice/tone: {_PDF_TONE_VOICE[tone]}.")
    return ("\nBRIEF DIRECTIVES:\n- " + "\n- ".join(lines) + "\n") if lines else ""


async def generate_pdf_outline(brand: Brand | None, topic: str, kind: str, *,
                               audience: str = "", tone: str = "", depth: str = "",
                               design_theme: str = "editorial") -> dict | None:
    """LLM-write a tailored, brand-grounded outline. Returns a dict with title/subtitle/kicker/metrics/
    callout/sections/cta, or ``None`` when no provider is available / nothing usable (caller falls back)."""
    if not llm.provider_available() or not (topic or "").strip():
        return None
    pillars = ", ".join(brand.pillars) if brand and brand.pillars else ""
    proofs_list = list(brand.proof_points) if brand and brand.proof_points else []
    proof = "; ".join(proofs_list)
    services = ", ".join(brand.services) if brand and brand.services else ""
    context = await retrieve.brand_context(topic, k=6)
    sec_target = {"concise": "3-4", "standard": "4-6", "in-depth": "6-7"}.get(depth, "4-6")
    kind_guide = {
        "proposal": ("a persuasive CLIENT PROPOSAL: the prospect's situation/problem, Talentrupt's "
                     "tailored solution, scope of work, the proof it works, and a clear next step."),
        "one-pager": ("a crisp ONE-PAGE service overview: what it is, who it's for, how it works, the "
                      "proof, and a call to action — short and scannable."),
        "report": ("an EXECUTIVE BRIEFING / REPORT: the context, the key insight, Talentrupt's approach, "
                   "the evidence, and a recommendation."),
    }.get(kind, "an executive document.")
    sys = (
        "You are Talentrupt's senior marketing writer (offshore RPO selling into the US market, "
        f"'RPO Done Right'). Brand pillars: {pillars}. Services: {services}. "
        f"Proof points — the ONLY real numbers you may ever state: {proof}.\n"
        "ANTI-FABRICATION (critical): do NOT state ANY percentage, multiple, count or dollar figure "
        "ANYWHERE (title, subtitle, headings, bodies, bullets, callout, cta) UNLESS it is copied EXACTLY "
        f"from this list: {proof or 'none'}. Otherwise describe benefits QUALITATIVELY (write 'faster "
        "time-to-fill', NEVER '40% faster'). Inventing a number is a serious error.\n"
        + (f"\n{context}\n\n" if context else "")
        + _pdf_directives(audience, tone)
        + f"Write {kind_guide} Reference the reader/client and topic by name where natural, and weave in "
        "real Talentrupt services so it reads tailored, not boilerplate.\n"
        'Return ONLY JSON: {"title": str, "subtitle": str, "kicker": str (2-4 word eyebrow), '
        '"metrics": [str], "callout": str (one punchy key insight or client-outcome line), '
        '"sections": [{"heading": str, "body": str, "bullets": [str], "layout": "single"|"two_column"}], '
        '"cta": {"headline": str, "subtext": str}} '
        f"with {sec_target} sections. Each section: a 'heading', a 'body' of 2-4 SUBSTANTIVE sentences "
        "written SPECIFICALLY for this topic (no generic filler, no repeating a claim), and OPTIONAL "
        "'bullets' (2-4 concrete points); set 'layout' to 'two_column' only for a short parallel list "
        "(e.g. pros/cons, do/don't). For 'metrics', include ONLY proof points copied VERBATIM from this "
        f"exact list (omit entirely if none apply, NEVER alter a number): {proof or 'none available'}. "
        "Open with the reader's problem/context, keep everything specific, and make 'cta' a concrete "
        "next step. Professional US B2B tone."
    )
    usr = f"Document type: {kind}. Topic / brief: {topic}"
    try:
        data = await llm.chat_json(
            [{"role": "system", "content": sys}, {"role": "user", "content": usr}], temperature=0.7
        )
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    secs = data.get("sections")
    if not isinstance(secs, list) or not secs:
        return None
    clean = []
    for s in secs:
        if not isinstance(s, dict):
            continue
        heading = str(s.get("heading", "") or "").strip()
        body = str(s.get("body", "") or "").strip()
        bullets = [str(b).strip() for b in (s.get("bullets") or [])
                   if isinstance(b, (str, int, float)) and str(b).strip()]
        layout = "two_column" if str(s.get("layout", "")).strip() == "two_column" else "single"
        if heading and (body or bullets):
            clean.append({"heading": heading, "body": body, "bullets": bullets[:5], "layout": layout})
    if not clean:
        return None
    # Anti-fab: keep only metrics that are EXACT members of the real proof-point list.
    metrics = [m for m in (data.get("metrics") or []) if isinstance(m, str) and m in proofs_list]
    cta = data.get("cta") if isinstance(data.get("cta"), dict) else {}
    return {
        "title": (str(data.get("title") or topic).strip() or topic)[:200],
        "subtitle": str(data.get("subtitle") or "").strip()[:300],
        "kicker": str(data.get("kicker") or "").strip()[:60],
        "metrics": metrics,
        "callout": str(data.get("callout") or "").strip()[:400],
        "sections": clean[:7],
        "cta": {"headline": str(cta.get("headline") or "").strip()[:120],
                "subtext": str(cta.get("subtext") or "").strip()[:200]},
    }


# --- Body assembly --------------------------------------------------------
def _render_outline(outline: dict, kind: str, brand: Brand | None, st: dict, theme: dict, bw: float,
                    with_masthead: bool, title: str, kind_label: str) -> list:
    keep = kind != "one-pager"  # one-pager is wrapped in one KeepInFrame (no nested KeepTogether)
    flow: list = []
    if with_masthead:
        flow += _masthead(st, theme, title, outline.get("subtitle") or kind_label,
                          outline.get("kicker") or kind_label, bw)
    cards = _pick_metrics(outline, brand)
    secs = outline.get("sections") or []
    proof_forward = kind in ("one-pager", "proposal")
    placed_cards = False
    if proof_forward and cards:  # leave-behinds / pitches lead with the proof
        _emit(flow, _metric_cards(cards, st, theme, bw), keep)
        placed_cards = True
    for i, sec in enumerate(secs):
        block = _divider_parts(st, theme, sec.get("heading", ""))
        if sec.get("body"):
            block.append(Paragraph(_esc(sec["body"]), st["body"]))
        bullets = sec.get("bullets") or []
        if sec.get("layout") == "two_column" and len(bullets) >= 2:
            block += _two_col(bullets, st, bw)
        elif bullets:
            block.append(_bullets(bullets, st, theme))
        _emit(flow, block, keep)
        if not placed_cards and cards and i == 0:  # reports drop evidence after the opening section
            _emit(flow, _metric_cards(cards, st, theme, bw), keep)
            placed_cards = True
    if outline.get("callout"):
        _emit(flow, _callout(outline["callout"], st, theme, bw), keep)
    cta = outline.get("cta") or {}
    _emit(flow, _cta_panel(cta.get("headline") or "Let's build your hiring engine.",
                           cta.get("subtext") or "Partner with Talentrupt — RPO Done Right.", st, theme, bw), keep)
    return flow


def _render_campaign(campaign: Campaign | None, brand: Brand | None, topic: str, st: dict, theme: dict,
                     bw: float, kind_label: str, title: str) -> list:
    flow: list = []
    flow += _masthead(st, theme, title, kind_label, kind_label, bw)
    strat = (campaign.strategy if campaign and campaign.strategy else {}) or {}

    def sec(h, content):
        if isinstance(content, list):
            items = [c for c in content if str(c).strip()]
            if not items:
                return
            _emit(flow, _divider_parts(st, theme, h) + [_bullets(items, st, theme)], True)
        else:
            if not str(content).strip():
                return
            _emit(flow, _divider_parts(st, theme, h) + [Paragraph(_esc(content), st["body"])], True)

    if strat:
        sec("Objective", strat.get("objective", campaign.goal if campaign else ""))
        sec("Audience & Persona", [strat.get("audience", ""), strat.get("persona", "")])
        if strat.get("pain_points"):
            sec("Pain Points", strat["pain_points"])
        sec("Positioning", strat.get("positioning", ""))
        sec("Key Message", strat.get("key_message", ""))
        if strat.get("content_strategy"):
            sec("Content Strategy", strat["content_strategy"])
        if strat.get("channel_strategy"):
            sec("Channel Strategy", strat["channel_strategy"])
        if strat.get("kpis"):
            sec("KPIs", strat["kpis"])
        if strat.get("recommendations"):
            sec("Recommendations", strat["recommendations"])
    else:
        sec("Overview", topic or (campaign.goal if campaign else "Talentrupt RPO campaign."))
        sec("Services", brand.services if brand else ["Offshore RPO delivery"])
    _emit(flow, _metric_cards(_pick_metrics({}, brand), st, theme, bw), True)
    _emit(flow, _cta_panel("Let's scale your hiring.", "Partner with Talentrupt — RPO Done Right.",
                           st, theme, bw), True)
    return flow


def build_pdf(
    brand: Brand | None,
    campaign: Campaign | None,
    kind: str = "report",
    topic: str = "",
    outline: dict | None = None,
    *,
    audience: str = "",
    tone: str = "",
    depth: str = "",
    design_theme: str = "editorial",
) -> tuple[str, str, dict]:
    theme = _theme(design_theme)
    st = _styles(theme, tone)
    kind_label = KIND_LABELS.get(kind, "Executive Report")

    file_name = unique_name("tr-doc", "pdf")
    path = storage_subdir("pdfs") / file_name

    W, H = letter
    LM = RM = 0.9 * inch
    TOP, BOT = 0.95 * inch, 0.8 * inch
    bw = W - LM - RM
    doc = BaseDocTemplate(str(path), pagesize=letter, leftMargin=LM, rightMargin=RM,
                          topMargin=TOP, bottomMargin=BOT, title=(topic or kind_label))
    doc._theme = theme

    has_outline = bool(outline and outline.get("sections"))
    has_cover = has_outline and kind != "one-pager"  # one-pagers stay a single dense page

    title = (outline.get("title") if outline else "") or topic or (campaign.name if campaign else "Talentrupt")
    doc._cover = {
        "title": title,
        "kicker": (outline.get("kicker") if outline else "") or kind_label,
        "subtitle": (outline.get("subtitle") if outline else "") or "RPO Done Right",
        "date": date.today().strftime("%B %Y"),
    }

    cover_frame = Frame(0, 0, W, H, id="cover", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    body_frame = Frame(LM, BOT, bw, H - TOP - BOT, id="body")
    templates = []
    if has_cover:
        templates.append(PageTemplate(id="cover", frames=[cover_frame], onPage=_paint_cover))
    templates.append(PageTemplate(id="body", frames=[body_frame], onPage=_paint_body_chrome))
    doc.addPageTemplates(templates)

    flow: list = []
    if has_cover:
        flow += [Spacer(1, 1), NextPageTemplate("body"), PageBreak()]

    if has_outline:
        body = _render_outline(outline, kind, brand, st, theme, bw,
                               with_masthead=not has_cover, title=title, kind_label=kind_label)
    else:
        body = _render_campaign(campaign, brand, topic, st, theme, bw, kind_label, title)

    if kind == "one-pager":
        flow.append(KeepInFrame(bw, H - TOP - BOT, body, mode="shrink"))
    else:
        flow += body

    doc.build(flow)
    return str(path), file_name, {
        "kind": kind, "topic": topic, "theme": (design_theme or "editorial"),
        "url": public_url("pdfs", file_name), "ai_written": has_outline,
    }
