"""Parse an uploaded EMPLOYEE ROSTER (CSV / .xlsx) and turn it into a magazine `issue` spec.

The user uploads a spreadsheet with a Name column + metric columns (Submissions, Interviews, Offers, Starts,
Productivity, …). We: (1) fuzzy-detect the name / office / numeric-metric columns, (2) rank everyone by a
performance score (a chosen column, or a weighted composite that favours outcomes), (3) feature the top
performer as the COVER champion and the next N as SPOTLIGHTS, with their real stats + auto-written copy.

Photos are NOT resolved here — the endpoint matches each featured name to a Folders employee (owner-scoped).
Pure + defensive: bad cells are skipped, never crash the build.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re

_NAME_EXACT = {"name", "employeename", "fullname", "employee", "person", "teammember", "candidate"}
_OFFICE_HINTS = ("office", "location", "branch", "city", "base", "region", "site")
_HEADLINES = ["Spark of Brilliance", "Setting the Pace", "Leading the Charge", "Raising the Bar",
              "Champion of the Month", "Driven to Deliver"]
_FEATURE_CAP = 24


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (h or "").lower())


def _num(v) -> float | None:
    """Best-effort numeric parse: '1,234', '95%', '4.0' -> float; text / inf / nan / overflow -> None.
    (float() accepts 'inf'/'nan'/'1e400', so a NON-FINITE result is treated as text, never crashes _fmt.)"""
    if v is None:
        return None
    s = str(v).strip().replace(",", "").replace("%", "")
    if not s:
        return None
    f = None
    try:
        f = float(s)
    except ValueError:
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        if m:
            try:
                f = float(m.group())
            except ValueError:
                f = None
    return f if (f is not None and math.isfinite(f)) else None


def _numeric_frac(vals) -> float:
    non = [v for v in vals if str(v).strip()]
    return (sum(1 for v in non if _num(v) is not None) / len(non)) if non else 0.0


def _text_frac(vals) -> float:
    non = [v for v in vals if str(v).strip()]
    return (sum(1 for v in non if _num(v) is None) / len(non)) if non else 0.0


def _fmt(v) -> str:
    n = _num(v)
    s = str(v).strip()
    if n is None or not math.isfinite(n):   # non-numeric / inf / nan -> show the raw text (never int(inf))
        return s[:12]
    whole = str(int(n)) if n == int(n) else f"{n:g}"
    return whole + "%" if "%" in s else whole


# ---- parsing ------------------------------------------------------------------------------------
def parse_roster(filename: str, data: bytes) -> list[dict]:
    """Return a list of row dicts {header: cell}. Handles .xlsx (openpyxl) and CSV/TSV (stdlib)."""
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")):
        return _parse_xlsx(data)
    return _parse_csv(data)


def _rows_to_dicts(header: list, rows: list[list]) -> list[dict]:
    # Coerce EVERY header cell to str first — an .xlsx header row can hold ints (a year like 2024), floats or
    # datetimes, and (h or "").strip() would then raise AttributeError on the non-string.
    header = [(str(h).strip() if h is not None else "") for h in header]
    # de-dupe blank/duplicate headers so keys stay unique
    seen: dict[str, int] = {}
    keys: list[str] = []
    for i, h in enumerate(header):
        key = h or f"col{i + 1}"
        if key in seen:
            seen[key] += 1
            key = f"{key} ({seen[key]})"
        else:
            seen[key] = 0
        keys.append(key)
    out = []
    for r in rows:
        out.append({keys[i]: (str(r[i]).strip() if i < len(r) and r[i] is not None else "")
                    for i in range(len(keys))})
    return out


def _parse_csv(data: bytes) -> list[dict]:
    text = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except Exception:
            continue
    if text is None:
        text = data.decode("utf-8", "replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except Exception:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [r for r in reader if any((c or "").strip() for c in r)]
    if not rows:
        return []
    return _rows_to_dicts(rows[0], rows[1:])


def _parse_xlsx(data: bytes) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        ws = wb.active
        rows = [r for r in ws.iter_rows(values_only=True)
                if r is not None and any(c is not None and str(c).strip() for c in r)]
    finally:
        wb.close()
    if not rows:
        return []
    return _rows_to_dicts(list(rows[0]), [list(r) for r in rows[1:]])


# ---- column detection + scoring -----------------------------------------------------------------
def _detect_columns(rows: list[dict]):
    headers = list(rows[0].keys()) if rows else []
    name_col = next((h for h in headers if _norm(h) in _NAME_EXACT), None)
    if not name_col:
        name_col = next((h for h in headers if "name" in _norm(h)), None)
    if not name_col:  # fallback: the first mostly-text column
        name_col = next((h for h in headers if _text_frac([r.get(h, "") for r in rows]) > 0.6), None)
    office_col = next((h for h in headers
                       if h != name_col and any(k in _norm(h) for k in _OFFICE_HINTS)), None)
    metric_cols = [h for h in headers
                   if h and h not in (name_col, office_col)
                   and _numeric_frac([r.get(h, "") for r in rows]) >= 0.5]
    return name_col, office_col, metric_cols


def _weight(h: str) -> float:
    n = _norm(h)
    if any(k in n for k in ("start", "join", "placement", "onboard", "hire")):
        return 5.0
    if "offer" in n:
        return 4.0
    if "interview" in n:
        return 1.5
    if any(k in n for k in ("productivity", "score", "rating", "points", "efficiency")):
        return 2.0
    if any(k in n for k in ("submission", "sub", "cv", "profile", "sourced")):
        return 0.3
    return 1.0


def _score(row: dict, metric_cols: list[str], rank_by: str) -> float:
    if rank_by:
        for h in metric_cols:
            if _norm(h) == _norm(rank_by):
                v = _num(row.get(h))
                return v if v is not None else -1.0
    total = 0.0
    for h in metric_cols:
        v = _num(row.get(h))
        if v is not None:
            total += v * _weight(h)
    return total


# ---- copy templates -----------------------------------------------------------------------------
def _champion_copy(first: str, stats: list[dict]) -> tuple[str, str]:
    hl = _HEADLINES[int(hashlib.md5((first or "x").encode("utf-8")).hexdigest()[:6], 16) % len(_HEADLINES)]
    if len(stats) >= 2:
        tg = (f"With {stats[0]['value']} {stats[0]['label'].lower()} and {stats[1]['value']} "
              f"{stats[1]['label'].lower()}, {first} set a new benchmark this month.")
    elif stats:
        tg = f"With {stats[0]['value']} {stats[0]['label'].lower()}, {first} led the way this month."
    else:
        tg = f"{first} delivered standout results this month."
    return hl, tg


def _spotlight_blurb(first: str, stats: list[dict]) -> str:
    if stats:
        top = ", ".join(f"{s['value']} {s['label'].lower()}" for s in stats[:2])
        return (f"{first} continues to set the benchmark — {top} this month reflect real consistency and "
                "quality delivery.")
    return f"{first} delivered consistent, quality results — a standout month for the team."


# ---- public: roster -> issue --------------------------------------------------------------------
def build_issue(rows: list[dict], *, theme: str = "", title: str = "Talentrupt Times", edition: str = "",
                editorial: str = "", feature_count: int = 0, rank_by: str = ""):
    """Analyse the roster and return (issue_dict_without_photos, featured_names, columns_info).

    Raises ValueError('no_name_column' | 'no_rows') for a caller-friendly 400.
    """
    rows = [r for r in rows if any((str(v) or "").strip() for v in r.values())]
    if not rows:
        raise ValueError("no_rows")
    name_col, office_col, metric_cols = _detect_columns(rows)
    if not name_col:
        raise ValueError("no_name_column")
    people = [r for r in rows if (r.get(name_col) or "").strip()]
    if not people:
        raise ValueError("no_rows")

    ranked = sorted(people, key=lambda r: _score(r, metric_cols, rank_by), reverse=True)
    limit = min(feature_count, _FEATURE_CAP) if feature_count and feature_count > 0 else _FEATURE_CAP
    ranked = ranked[:limit]

    def stats_for(r: dict, n: int) -> list[dict]:
        out = []
        for h in metric_cols:
            if len(out) >= n:
                break
            v = r.get(h, "")
            if str(v).strip():
                out.append({"label": h, "value": _fmt(v)})
        return out

    champ = ranked[0]
    cname = (champ.get(name_col) or "").strip()
    cfirst = cname.split()[0] if cname else "Our champion"
    cstats = stats_for(champ, 6)
    headline, tagline = _champion_copy(cfirst, cstats)

    issue: dict = {
        "title": (title or "Talentrupt Times").strip(),
        "edition": edition.strip(),
        "theme": theme.strip(),
        "editorial": editorial.strip(),
        "cover": {"name": cname, "role": "", "headline": headline, "tagline": tagline, "stats": cstats},
        "spotlights": [],
    }
    for r in ranked[1:]:
        nm = (r.get(name_col) or "").strip()
        if not nm:
            continue
        sstats = stats_for(r, 4)
        issue["spotlights"].append({
            "name": nm, "role": "",
            "office": (r.get(office_col) or "").strip() if office_col else "",
            "blurb": _spotlight_blurb(nm.split()[0], sstats), "stats": sstats,
        })

    featured = [cname] + [s["name"] for s in issue["spotlights"]]
    columns = {"name": name_col, "office": office_col, "metrics": metric_cols}
    return issue, featured, columns
