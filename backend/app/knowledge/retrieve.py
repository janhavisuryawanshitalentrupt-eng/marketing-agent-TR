"""Retrieval over ingested brand chunks (Python cosine search; no pgvector yet).

For the current archive (~hundreds of chunks) brute-force cosine is fast enough.
Swapping in pgvector later only changes this module.
"""
from __future__ import annotations

import math
import os

from ..db import SessionLocal
from ..models import BrandChunk, SourceFile
from ..providers import llm

# Relevance floors so off-topic queries return nothing rather than confident noise.
MIN_TEXT_SCORE = 0.18
MIN_IMAGE_SCORE = 0.24


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
        upload_ids = {sf.id for sf in sources if (sf.folder or "") == "Uploads"}
        rows = [r for r in rows if r.source_file_id not in upload_ids]
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
