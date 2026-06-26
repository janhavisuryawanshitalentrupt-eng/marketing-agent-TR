"""Retrieval over ingested brand chunks (Python cosine search; no pgvector yet).

For the current archive (~hundreds of chunks) brute-force cosine is fast enough.
Swapping in pgvector later only changes this module.
"""
from __future__ import annotations

import math
import os
import re
import zipfile

from ..config import settings
from ..db import SessionLocal
from ..models import BrandChunk, SourceFile
from ..providers import llm
from .ingest import _clean_name

# Relevance floors so off-topic queries return nothing rather than confident noise.
MIN_TEXT_SCORE = 0.18
MIN_IMAGE_SCORE = 0.24

# Folders whose images must NEVER be used as visual STYLE references for generation: Uploads (one-off
# chat attachments) and Team (real people's photos — feeding a face into a normal post would leak a
# real likeness into an unrelated image).
EXCLUDED_REF_FOLDERS = {"Uploads", "Team"}


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0  # mismatched dims (e.g. embedding-model swap w/o re-ingest) -> no score, not garbage
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _title(path: str) -> str:
    base = os.path.basename(path or "")
    return os.path.splitext(base)[0][:60]


async def search(query: str, k: int = 8, min_score: float = MIN_TEXT_SCORE) -> list[dict]:
    """Return the top-k brand chunks for a query, each {text, folder, title, kind, score}."""
    if not llm.provider_available() or not query.strip():
        return []
    try:
        qvec = (await llm.embed([query]))[0]
    except Exception:
        return []

    db = SessionLocal()
    try:
        rows = db.query(BrandChunk).all()
        if not rows:
            return []
        meta = {sf.id: (sf.folder, sf.path) for sf in db.query(SourceFile).all()}
        # Chat attachments are ingested under "Uploads" purely for per-turn context — exclude them
        # here so a user's one-off file never masquerades as Talentrupt's own brand voice/style.
        upload_ids = {sid for sid, (folder, _p) in meta.items() if (folder or "") == "Uploads"}
        rows = [r for r in rows if r.source_file_id not in upload_ids]
        if not rows:
            return []
        scored = [(_cosine(qvec, r.embedding or []), r) for r in rows]
        scored.sort(key=lambda t: t[0], reverse=True)
        out = []
        for score, r in scored[:k]:
            if score < min_score:
                continue
            folder, path = meta.get(r.source_file_id, ("", ""))
            out.append({
                "text": r.text,
                "folder": folder,
                "title": _title(path),
                "kind": r.kind,
                "score": round(score, 3),
            })
        return out
    finally:
        db.close()


async def image_references(query: str, n: int = 3, min_score: float = MIN_IMAGE_SCORE) -> list[str]:
    """Return ZIP member paths of the most topically-relevant past-post IMAGES,
    for visual style references. Applies a relevance floor + de-dupes by file so
    off-topic queries don't return confidently-wrong images."""
    if not llm.provider_available() or not query.strip():
        return []
    try:
        qvec = (await llm.embed([query]))[0]
    except Exception:
        return []
    db = SessionLocal()
    try:
        rows = db.query(BrandChunk).filter(BrandChunk.kind == "image_caption").all()
        if not rows:
            return []
        sources = db.query(SourceFile).all()
        paths = {sf.id: sf.path for sf in sources}
        excluded_ids = {sf.id for sf in sources if (sf.folder or "") in EXCLUDED_REF_FOLDERS}
        rows = [r for r in rows if r.source_file_id not in excluded_ids]
        if not rows:
            return []
        scored = [(_cosine(qvec, r.embedding or []), r) for r in rows]
        scored.sort(key=lambda t: t[0], reverse=True)
        out, seen = [], set()
        for score, r in scored:
            if score < min_score or len(out) >= n:
                break
            p = paths.get(r.source_file_id)
            if p and p not in seen:
                seen.add(p)
                out.append(p)
        return out
    finally:
        db.close()


# --- Team photos (real people, composited into branded posts — never AI-synthesized) ---------------
_GROUP_CUES = {"team", "leadership", "everyone", "group", "all", "staff", "crew", "founders", "leaders",
               "whole", "company", "office", "department"}


def list_team_photos() -> list[dict]:
    """Every photo under the brand ZIP's Team/ folder, as {path, label, caption}. The label is the
    descriptive filename (e.g. 'Team/rushikesh-founder.jpg' -> 'rushikesh founder'), which is the only
    way to identify WHO is in a shot (vision captions can't name individuals)."""
    db = SessionLocal()
    try:
        rows = db.query(SourceFile).filter(SourceFile.folder == "Team").all()
        return [{"path": sf.path, "label": _clean_name(sf.path),
                 "caption": (sf.analysis or {}).get("caption", "")} for sf in rows]
    finally:
        db.close()


def _team_score(query: str, item: dict) -> float:
    """Keyword overlap of the request against the filename label (weighted) + caption, with a boost
    when the request asks for a group and the photo reads as a group."""
    q = {w for w in re.findall(r"[a-z0-9]+", (query or "").lower()) if len(w) > 1}
    if not q:
        return 0.0
    label = set(re.findall(r"[a-z0-9]+", item["label"].lower()))
    cap = set(re.findall(r"[a-z0-9]+", (item.get("caption") or "").lower()))
    score = 2.0 * len(q & label) + 0.5 * len(q & cap)
    if (q & _GROUP_CUES) and ({"team", "group", "people", "leadership"} & (label | cap | _GROUP_CUES & q)):
        score += 1.5
    return score


def match_team_photos(query: str, n: int = 1) -> list[dict]:
    """Best-matching Team/ photo(s) for a user's request (e.g. 'the founder', 'leadership team').
    Returns [] when nothing scores — the caller then lists options instead of inventing a face."""
    items = list_team_photos()
    scored = sorted(((_team_score(query, it), it) for it in items), key=lambda t: t[0], reverse=True)
    return [it for s, it in scored if s > 0][:n]


def person_photos(query: str, limit: int = 12) -> list[dict]:
    """ALL Team/ photos of the same person/group the query names — the rotation set, so repeated
    'feature X' requests can cycle through different shots instead of reusing one. Keeps the photos
    that score near the top match (same person; extra shots are named '<base>-2.jpg', '-3.jpg', …).
    [] when nothing matches — caller lists options rather than inventing a face."""
    items = list_team_photos()
    scored = sorted(((_team_score(query, it), it) for it in items), key=lambda t: t[0], reverse=True)
    scored = [(s, it) for s, it in scored if s > 0]
    if not scored:
        return []
    top = scored[0][0]
    return [it for s, it in scored if s >= max(0.1, top * 0.5)][:limit]


def team_reference_bytes(path: str) -> bytes | None:
    """Full-resolution bytes of one Team/ photo straight from the brand ZIP (no downscale, so the face
    stays crisp). Returns None on any read failure."""
    try:
        with zipfile.ZipFile(settings.knowledge_zip_path) as zf:
            return zf.read(path)
    except Exception:
        return None


async def brand_context(query: str, k: int = 8, max_chars: int = 700) -> str:
    """A grounding block to inject into generation prompts. '' if none relevant."""
    hits = await search(query, k)
    if not hits:
        return ""
    lines = []
    for h in hits:
        snippet = " ".join(h["text"].split())[:max_chars]
        label = h["title"] or h["folder"] or "source"
        lines.append(f"- [{h['folder']}/{label}] {snippet}")
    return (
        "Reference patterns from Talentrupt's own past work (mirror this voice/style; "
        "do not copy verbatim):\n" + "\n".join(lines)
    )
