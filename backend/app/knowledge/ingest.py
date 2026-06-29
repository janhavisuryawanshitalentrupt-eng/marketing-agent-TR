"""Ingest the Talentrupt source library (TR POSTS ZIP) into a searchable store.

- Images (.jpg/.png): downscaled and captioned by a vision model -> 1 chunk each.
- PDFs (.pdf): streamed to a temp file (handles the 600 MB magazine without
  loading it into RAM), capped pages of text extracted and chunked.
- All chunks are embedded and stored in `brand_chunks` for retrieval.

Resumable: files already in `source_files` (matched by path) are skipped.
Run:  python -m app.knowledge.ingest
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import shutil
import tempfile
import zipfile
from uuid import uuid4

from PIL import Image

from ..config import settings
from ..db import SessionLocal, init_db
from ..models import BrandChunk, SourceFile
from ..providers import llm

IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
VISION_PROMPT = (
    "Analyze this Talentrupt marketing asset (offshore RPO, 'RPO Done Right'). Write a concise "
    "description that LEADS WITH THE SUBJECT, in this order:\n"
    "1) TOPIC/THEME in a few words, and any visible HEADLINE and CTA text (quote it).\n"
    "2) The post FORMAT — pick the closest: stat/metric card, photo hero, quote, infographic/"
    "process diagram, carousel cover, holiday/greeting, hiring announcement, myth-vs-truth, "
    "service breakdown, testimonial.\n"
    "3) The service or messaging pillar it relates to (e.g. healthcare staffing, sourcing, "
    "scalability, data-driven hiring, credentialing).\n"
    "4) Briefly, the color/layout/typography style.\n"
    "Start with the subject matter — do NOT begin with generic phrases like 'The visual layout "
    "of the Talentrupt marketing asset'."
)
VISION_CONCURRENCY = 5
EMBED_BATCH = 64


def _top_folder(name: str) -> str:
    parts = name.replace("\\", "/").split("/")
    return parts[0] if len(parts) > 1 else "(root)"


def _image_b64(data: bytes, max_side: int = 1024) -> str:
    im = Image.open(io.BytesIO(data))
    if im.mode != "RGB":
        im = im.convert("RGB")
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def _is_failure_sentinel(text: str) -> bool:
    """True for the placeholder strings produced when vision/PDF extraction fails — so we never
    embed '[vision failed: …]' / '[pdf extract failed: …]' into the retrievable brand corpus."""
    return (text or "").lstrip().startswith(("[vision failed", "[pdf extract failed"))


def _chunk(text: str, size: int = 900, overlap: int = 120, limit: int = 15) -> list[str]:
    text = " ".join(text.split())
    if not text or _is_failure_sentinel(text):
        return []
    out, i = [], 0
    while i < len(text) and len(out) < limit:
        out.append(text[i : i + size])
        i += size - overlap
    return out


def _despace(text: str) -> str:
    """Fix character-spaced PDF extraction ('S u c c e s s f u l' -> 'Successful').
    Heuristic: on lines that are mostly single-character tokens, drop single spaces
    (intra-word) and collapse double spaces (word breaks) to one."""
    out = []
    for line in text.splitlines():
        toks = [t for t in line.split(" ") if t]
        if len(toks) >= 6 and sum(1 for t in toks if len(t) == 1) / len(toks) > 0.6:
            line = line.replace("  ", "\x00").replace(" ", "").replace("\x00", " ")
        out.append(line)
    return "\n".join(out)


def _extract_pdf_text(path: str, max_pages: int) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(path)
        parts = []
        for page in reader.pages[:max_pages]:
            try:
                parts.append(page.extract_text() or "")
            except Exception:
                continue
        return _despace("\n".join(parts))
    except Exception as e:
        return f"[pdf extract failed: {e}]"


def _clean_name(path: str) -> str:
    base = os.path.splitext(os.path.basename(path))[0]
    # Drop Canva-style size/format noise; keep topical words.
    base = base.replace("_", " ").replace("-", " ")
    return " ".join(base.split())


async def _caption_image(sem: asyncio.Semaphore, data: bytes) -> str:
    async with sem:
        try:
            b64 = _image_b64(data)
            return await llm.vision_caption(b64, VISION_PROMPT)
        except Exception as e:
            return f"[vision failed: {e}]"


TEXT_EXTS = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".rtf", ".html", ".htm"}
SUPPORTED_UPLOAD_EXTS = IMAGE_EXTS | {".pdf"} | TEXT_EXTS


def is_supported_upload(filename: str) -> bool:
    return os.path.splitext(filename or "")[1].lower() in SUPPORTED_UPLOAD_EXTS


async def ingest_upload(db, filename: str, data: bytes, folder: str = "Uploads", owner: str | None = None) -> dict:
    """Ingest ONE user-uploaded file into the brand library.

    Extracts text (PDF), a vision caption (image), or decoded text (txt/csv/…),
    embeds it into ``brand_chunks``, persists the raw file for provenance, and returns an
    excerpt. ``folder`` defaults to 'Uploads' (chat attachments — EXCLUDED from brand grounding
    by retrieve.py). Pass a different folder (e.g. 'Brand Kit') for a real brand asset that SHOULD
    be used for grounding.
    """
    safe = os.path.basename(filename) or "attachment"
    ext = os.path.splitext(safe)[1].lower()
    kind = "text"
    text = ""
    chunks: list[str] = []

    if ext in IMAGE_EXTS:
        kind = "image"
        try:
            caption = await llm.vision_caption(_image_b64(data), VISION_PROMPT)
        except Exception as e:  # pragma: no cover - provider hiccup
            caption = f"[vision failed: {e}]"
        text = f"{_clean_name(safe)}. {caption}"
        chunks = [] if _is_failure_sentinel(caption) else [text]
    elif ext == ".pdf":
        kind = "pdf"
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            tmp.write(data)
            tmp.close()
            text = await asyncio.to_thread(_extract_pdf_text, tmp.name, 30)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        chunks = _chunk(text, limit=40)
    else:
        kind = "text"
        text = _despace(data.decode("utf-8", errors="ignore").lstrip("﻿"))
        chunks = _chunk(text, limit=40)

    # Persist the raw upload for provenance (best-effort). Unique prefix so same-named
    # uploads don't overwrite each other on disk.
    dest = str(settings.uploads_path / f"{uuid4().hex[:8]}_{safe}")
    try:
        with open(dest, "wb") as f:
            f.write(data)
    except OSError:
        dest = f"upload:{safe}"

    sf = SourceFile(
        path=dest, folder=folder, file_type=kind, size=len(data), owner=owner,
        analysis={"filename": safe, "chars": len(text), "chunk_count": len(chunks),
                  "preview": " ".join(text.split())[:500]},
    )
    db.add(sf)
    db.commit()
    db.refresh(sf)

    written = 0
    if chunks and llm.provider_available():
        kind_label = "image_caption" if kind == "image" else "pdf_text"
        texts = [c[:6000] for c in chunks]
        vectors: list[list[float]] = []
        for i in range(0, len(texts), EMBED_BATCH):
            try:
                vectors.extend(await llm.embed(texts[i : i + EMBED_BATCH]))
            except Exception:
                vectors.extend([[] for _ in texts[i : i + EMBED_BATCH]])
        for c, v in zip(chunks, vectors):
            if not v:
                continue
            db.add(BrandChunk(
                source_file_id=sf.id, kind=kind_label, text=c,
                embedding=v, meta={"file": safe, "upload": True},
            ))
            written += 1
        db.commit()

    excerpt = " ".join(text.split())[:4000]
    return {
        "id": sf.id, "filename": safe, "kind": kind,
        "chars": len(text), "chunks": written, "text": excerpt,
    }


async def run_ingest() -> dict:
    init_db()
    if not llm.provider_available():
        print("[ingest] No AI provider configured — aborting.")
        return {"error": "no_provider"}

    zip_path = settings.knowledge_zip_path
    if not os.path.exists(zip_path):
        print(f"[ingest] ZIP not found: {zip_path}")
        return {"error": "zip_not_found"}

    db = SessionLocal()
    done_paths = {p for (p,) in db.query(SourceFile.path).all()}
    print(f"[ingest] Already ingested: {len(done_paths)} files")

    zf = zipfile.ZipFile(zip_path)
    infos = [
        i for i in zf.infolist()
        if not i.is_dir() and os.path.splitext(i.filename)[1].lower() in (IMAGE_EXTS | {".pdf"})
    ]
    todo = [i for i in infos if i.filename not in done_paths]
    print(f"[ingest] {len(todo)} new files to process (of {len(infos)})")

    # records: list of (SourceFile-kwargs, [chunk dicts])
    records: list[tuple[dict, list[dict]]] = []
    sem = asyncio.Semaphore(VISION_CONCURRENCY)

    # --- Images (concurrent vision) ---
    images = [i for i in todo if os.path.splitext(i.filename)[1].lower() in IMAGE_EXTS]
    images = images[: settings.knowledge_max_images]
    if settings.knowledge_use_vision and images:
        print(f"[ingest] Captioning {len(images)} images…")
        datas = [zf.read(i) for i in images]
        captions = await asyncio.gather(*[_caption_image(sem, d) for d in datas])
        for info, cap in zip(images, captions):
            sf = {
                "path": info.filename, "folder": _top_folder(info.filename),
                "file_type": "image", "size": info.file_size,
                "analysis": {"caption": cap},
            }
            if _is_failure_sentinel(cap):
                records.append((sf, []))  # captioning failed — keep provenance, embed nothing
            else:
                # Prepend the (topical) filename so retrieval ranks on subject, not just style.
                embed_text = f"{_clean_name(info.filename)}. {cap}"
                records.append((sf, [{"kind": "image_caption", "text": embed_text, "meta": {"file": info.filename}}]))
            print(f"  [img] {info.filename[:60]}")

    # --- PDFs (sequential, streamed to temp) ---
    pdfs = [i for i in todo if os.path.splitext(i.filename)[1].lower() == ".pdf"]
    for info in pdfs:
        max_pages = 6 if info.file_size > 40 * 1024 * 1024 else 25
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        try:
            with zf.open(info) as src:
                shutil.copyfileobj(src, tmp, length=4 * 1024 * 1024)
            tmp.close()
            text = await asyncio.to_thread(_extract_pdf_text, tmp.name, max_pages)
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        chunks = _chunk(text)
        sf = {
            "path": info.filename, "folder": _top_folder(info.filename),
            "file_type": "pdf", "size": info.file_size,
            "analysis": {"pages_scanned": max_pages, "chars": len(text), "chunk_count": len(chunks)},
        }
        records.append((sf, [{"kind": "pdf_text", "text": c, "meta": {"file": info.filename}} for c in chunks]))
        print(f"  [pdf] {info.filename[:60]}  ({len(chunks)} chunks)")

    zf.close()  # done reading the archive — release the (large) ZIP handle before embed/persist

    # --- Extra standalone PDFs (e.g. the sales deck) ---
    for extra in settings.knowledge_extra_pdf_list:
        if extra in done_paths or not os.path.exists(extra):
            continue
        size = os.path.getsize(extra)
        max_pages = 6 if size > 40 * 1024 * 1024 else 25
        text = await asyncio.to_thread(_extract_pdf_text, extra, max_pages)
        chunks = _chunk(text, limit=20)
        sf = {
            "path": extra, "folder": "Sales Deck", "file_type": "pdf", "size": size,
            "analysis": {"pages_scanned": max_pages, "chars": len(text), "chunk_count": len(chunks)},
        }
        records.append((sf, [{"kind": "pdf_text", "text": c, "meta": {"file": os.path.basename(extra)}} for c in chunks]))
        print(f"  [extra-pdf] {os.path.basename(extra)[:50]}  ({len(chunks)} chunks)")

    # --- Embed all chunk texts ---
    all_chunks = [c for (_, cs) in records for c in cs]
    texts = [c["text"][:6000] for c in all_chunks]
    print(f"[ingest] Embedding {len(texts)} chunks…")
    vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBED_BATCH):
        batch = texts[i : i + EMBED_BATCH]
        try:
            vectors.extend(await llm.embed(batch))
        except Exception as e:
            print(f"  [embed] batch {i} failed: {e}")
            vectors.extend([[] for _ in batch])
    for c, v in zip(all_chunks, vectors):
        c["embedding"] = v

    # --- Persist ---
    written_files = written_chunks = 0
    for sf_kwargs, chunk_dicts in records:
        sf = SourceFile(**sf_kwargs)
        db.add(sf)
        db.commit()
        db.refresh(sf)
        written_files += 1
        for c in chunk_dicts:
            if not c.get("embedding"):
                continue
            db.add(BrandChunk(
                source_file_id=sf.id, kind=c["kind"], text=c["text"],
                embedding=c["embedding"], meta=c.get("meta", {}),
            ))
            written_chunks += 1
        db.commit()

    total_files = db.query(SourceFile).count()
    total_chunks = db.query(BrandChunk).count()
    db.close()
    print(f"[ingest] DONE. +{written_files} files, +{written_chunks} chunks. "
          f"Totals: {total_files} files, {total_chunks} chunks.")
    return {"new_files": written_files, "new_chunks": written_chunks,
            "total_files": total_files, "total_chunks": total_chunks}


if __name__ == "__main__":
    asyncio.run(run_ingest())
