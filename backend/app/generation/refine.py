"""Regenerate / refine a previously-generated asset.

Re-runs the SAME stateless generator with the asset's stored inputs plus an optional natural-language
instruction folded in (e.g. "make it punchier", "shorten it", "new variation"). Saves the result as a
NEW asset by default (lineage recorded in meta) so the original is preserved; pass replace=True to
overwrite in place. This is additive — the one-shot generation flow is untouched.
"""
from __future__ import annotations

import random

from ..models import Asset, Brand
from . import decks, images, pdf, posts, teampost


def _augment(base: str, instruction: str) -> str:
    base = (base or "").strip()
    instr = (instruction or "").strip()
    if not instr:
        return base
    return f"{base}. {instr}".strip(". ").strip()


# Refine-instruction keywords -> team post FORMAT (a refine may change layout, never the face).
_STYLE_CUES = {
    "magazine": "magazine", "full photo": "magazine", "full-photo": "magazine", "cover": "magazine",
    "split": "split", "side by side": "split", "side-by-side": "split", "panel": "split",
    "framed": "framed", "frame": "framed", "card": "framed", "portrait": "framed",
    "spotlight": "spotlight", "cut out": "spotlight", "cut-out": "spotlight", "cutout": "spotlight",
}


def _team_style_from(instruction: str, default: str) -> str:
    instr = (instruction or "").lower()
    for cue, style in _STYLE_CUES.items():
        if cue in instr:
            return style
    return default


async def regenerate_asset(
    db, asset_id: int, instruction: str = "", replace: bool = False
) -> Asset | None:
    a = db.get(Asset, asset_id)
    if not a:
        return None
    brand = db.query(Brand).first()
    body = dict(a.body or {})
    meta_in = dict(a.meta or {})
    file_path = file_url = None
    new_body: dict = dict(body)
    new_meta: dict = {}
    title = a.title

    if a.type == "post":
        platform = meta_in.get("platform") or body.get("platform") or "LinkedIn"
        angle = _augment(body.get("hook") or body.get("content_type") or a.title, instruction) or instruction
        items = await posts.generate_posts(brand, None, count=1, platform=platform, angle=angle)
        p = items[0] if items else body
        new_body, new_meta, title = p, {"platform": p.get("platform", platform)}, p.get("hook", title)
    elif a.type == "image" and (body.get("kind") == "team" or meta_in.get("team_photo")):
        # TEAM image: re-run the REAL-photo composer. NEVER fall through to images.build_images —
        # that would synthesize a brand-new (wrong) face. We only ever recolor/redesign, never the face.
        from ..knowledge import retrieve
        label = meta_in.get("team_photo") or ""
        photo = next((it for it in retrieve.list_team_photos() if it["label"] == label), None)
        if photo is None:  # fall back to any real shot of the same person
            cand = retrieve.person_photos(body.get("person") or a.title)
            photo = cand[0] if cand else None
        if photo is None:
            return None  # no real photo on file -> refuse rather than invent a face
        raw = retrieve.team_reference_bytes(photo["path"])
        if not raw:
            return None
        name = body.get("person") or a.title
        role = body.get("role") or ""
        style = _team_style_from(instruction, body.get("style") or meta_in.get("style") or "spotlight")
        if instruction.strip():  # an instruction supplies new copy; else keep the original message
            head, sub = teampost.split_message(instruction)
        else:
            head, sub = body.get("headline") or "", body.get("subline") or ""
        path, _fn, m = teampost.build_team_image(
            brand, raw, name=name, role=role, headline=head, question=sub,
            variant=random.randint(0, 5), style=style)
        file_path, file_url, new_meta = path, m["url"], dict(m)
        new_meta["team_photo"] = photo["label"]
        new_body = {"person": name, "role": role, "headline": head, "subline": sub,
                    "kind": "team", "style": style}
        title = name + (f" — {role}" if role else "")
    elif a.type == "image":
        concept = _augment(body.get("concept") or a.title, instruction)
        rendered = await images.build_images(brand, None, concept, count=1)
        if not rendered:
            return None
        path, _fn, m = rendered[0]
        file_path, file_url, new_meta = path, m["url"], dict(m)
        new_body, title = {"concept": concept, "layout": m.get("layout")}, concept or title
    elif a.type == "deck":
        topic = _augment(body.get("topic") or a.title, instruction)
        style = {k: body[k] for k in ("audience", "tone", "depth", "design_theme") if body.get(k)}
        path, _fn, m = await decks.build_deck(brand, None, topic, slides=meta_in.get("slides") or 6, **style)
        file_path, file_url, new_meta = path, m["url"], dict(m)
        new_body, title = {"topic": topic, **style}, topic
    elif a.type == "pdf":
        kind = body.get("kind") or "report"
        topic = _augment(body.get("topic") or a.title, instruction)
        style = {k: body[k] for k in ("audience", "tone", "depth", "design_theme") if body.get(k)}
        outline = await pdf.generate_pdf_outline(brand, topic, kind, **style) if topic else None
        path, _fn, m = pdf.build_pdf(brand, None, kind=kind, topic=topic, outline=outline, **style)
        file_path, file_url, new_meta = path, m["url"], dict(m)
        new_body, title = {"kind": kind, "topic": topic, **style}, topic
    else:
        return None  # campaigns / unknown types aren't regeneratable

    # Lineage in meta (no migration): track the root + immediate parent + version.
    root_id = meta_in.get("root_id") or a.id
    new_meta = {
        **new_meta,
        "parent_id": a.id,
        "root_id": root_id,
        "version": int(meta_in.get("version") or 1) + 1,
        "origin": "regenerate",
        "instruction": instruction,
    }

    if replace:
        a.body, a.meta, a.title = new_body, new_meta, title[:380]
        a.file_path, a.file_url = file_path, file_url
        db.commit()
        db.refresh(a)
        return a

    new = Asset(
        campaign_id=a.campaign_id, type=a.type, title=title[:380],
        body=new_body, file_path=file_path, file_url=file_url, meta=new_meta,
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return new
