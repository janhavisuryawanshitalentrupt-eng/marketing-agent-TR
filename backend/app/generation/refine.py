"""Regenerate / refine a previously-generated asset.

Re-runs the SAME stateless generator with the asset's stored inputs plus an optional natural-language
instruction folded in (e.g. "make it punchier", "shorten it", "new variation"). Saves the result as a
NEW asset by default (lineage recorded in meta) so the original is preserved; pass replace=True to
overwrite in place. This is additive — the one-shot generation flow is untouched.
"""
from __future__ import annotations

import random
import re

from ..models import Asset, Brand, Campaign, Employee
from ..providers import llm
from . import decks, images, pdf, posts, teampost


def _augment(base: str, instruction: str) -> str:
    base = (base or "").strip()
    instr = (instruction or "").strip()
    if not instr:
        return base
    return f"{base}. {instr}".strip(". ").strip()


async def _parse_image_edit(instruction: str, prev_headline: str = "", prev_eyebrow: str = "") -> dict:
    """Interpret a natural-language edit on an existing employee campaign image (ChatGPT-style). The image has
    a REAL person photo (kept as-is), a themed BACKGROUND, a big HEADLINE and a small EYEBROW label. Returns
    {op, headline, background, fit, eyebrow} where op ∈ text|background|fit|design|other. Best-effort: falls
    back to a regex parse when no AI provider is configured."""
    instr = (instruction or "").strip()
    if not instr:
        return {"op": "other"}
    if llm.provider_available():
        try:
            out = await llm.chat_json([
                {"role": "system", "content":
                 "You edit an existing marketing image. It has a REAL person photo (kept unchanged), a themed "
                 "BACKGROUND scene, a big HEADLINE, and a small EYEBROW label above the headline. Read the "
                 "user's edit instruction and return ONLY JSON: {\"op\": \"text\"|\"background\"|\"fit\"|"
                 "\"design\"|\"other\", \"headline\": \"\", \"background\": \"\", \"fit\": \"smaller\"|"
                 "\"bigger\"|\"fit\"|\"\", \"eyebrow\": \"\"}. Rules: changing the WORDS / text / headline / "
                 "caption / what it says -> op=text and put ONLY the new headline words (Title Case, no quotes) "
                 "in \"headline\". Changing the background / scene / setting / location / place / where they "
                 "are -> op=background and describe the NEW scene in \"background\". The person doesn't fit / "
                 "is too big / too small / make them bigger|smaller / reposition -> op=fit and set \"fit\". A "
                 "different design / layout / colours / style / another version -> op=design. Changing ONLY "
                 "the small eyebrow/label -> put it in \"eyebrow\". Fill ONLY the field(s) you actually change; "
                 "leave the others as empty strings."},
                {"role": "user", "content":
                 f'Current headline: "{prev_headline}". Current eyebrow: "{prev_eyebrow}".\nEdit: {instr}'},
            ], temperature=0.2)
            if isinstance(out, dict) and out.get("op"):
                return out
        except Exception:
            pass
    low = instr.lower()
    m = re.search(r"(?:text|headline|caption|words?|title|heading)\s+(?:to|into|say[s]?|as|reads?|:)\s+(.+)",
                  instr, re.I)
    if m:
        return {"op": "text", "headline": m.group(1).strip().strip('"').strip()}
    m = re.search(r"(?:background|backdrop|scene|setting|location|place)\s+(?:to|into|as|with|:)\s+(.+)",
                  instr, re.I)
    if m:
        return {"op": "background", "background": m.group(1).strip().strip('"').strip()}
    if re.search(r"\b(smaller|too\s+big|reduce|shrink)\b", low):
        return {"op": "fit", "fit": "smaller"}
    if re.search(r"\b(bigger|larger|too\s+small|zoom)\b", low):
        return {"op": "fit", "fit": "bigger"}
    if re.search(r"\b(fit|doesn'?t\s+fit|not\s+fit|reposition|centre|center)\b", low):
        return {"op": "fit", "fit": "fit"}
    if re.search(r"\b(design|layout|colou?r|style|different|another|variation|redesign|again)\b", low):
        return {"op": "design"}
    return {"op": "other"}


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
    elif a.type == "image" and (body.get("kind") == "team" or meta_in.get("team_photo")
                                or meta_in.get("employee_id") or body.get("employee_id")):
        # TEAM image: re-run the REAL-photo composer with a FRESH random design. NEVER synthesize a new
        # (wrong) face — we only recolor/redesign. Find the photo: prefer the uploaded Employee record
        # (Folders), else the ZIP Team library.
        from ..knowledge import retrieve
        raw = None
        name = body.get("person") or a.title
        role = body.get("role") or ""
        team_label = meta_in.get("team_photo") or ""
        emp_id = meta_in.get("employee_id") or body.get("employee_id")
        if emp_id:
            try:
                emp = db.get(Employee, int(emp_id))
                if emp and emp.photo_path:
                    # regenerate -> pick a RANDOM real photo (cover + extras) so a "different look / new
                    # pose" actually varies (a different real shot of the SAME person, face untouched).
                    paths = [p for p in ([emp.photo_path] + [ep.photo_path for ep in (emp.photos or [])]) if p]
                    random.shuffle(paths)
                    for p in paths:
                        try:
                            with open(p, "rb") as f:
                                raw = f.read()
                            break
                        except Exception:
                            continue
                    name, role = emp.name or name, emp.role or role
            except Exception:
                raw = None
        if raw is None:  # ZIP Team library fallback (photos uploaded to the brand knowledge base)
            photo = next((it for it in retrieve.list_team_photos() if it["label"] == team_label), None)
            if photo is None:
                cand = retrieve.person_photos(name)
                photo = cand[0] if cand else None
            if photo is not None:
                raw = retrieve.team_reference_bytes(photo["path"])
                team_label = photo["label"]
        if not raw:
            return None  # no real photo on file -> refuse rather than invent a face
        # Campaign asset -> keep the campaign theme + suppress the on-image name (as the campaign generator does).
        theme, in_campaign = "", a.campaign_id is not None
        if in_campaign:
            camp = db.get(Campaign, a.campaign_id)
            if camp:
                theme = (f"{camp.name} — {camp.goal}" if (camp.goal or "").strip() else (camp.name or "")).strip(" —")
        # Reuse the ORIGINAL design inputs so a conversational edit changes ONLY what the user asked
        # (ChatGPT-style): keep the same headline/eyebrow/design variant unless the edit targets one of them.
        head, sub = body.get("headline") or "", body.get("subline") or ""
        eyebrow = body.get("eyebrow") or ""
        try:
            variant = int(body.get("variant")) if body.get("variant") is not None else random.randint(0, 5)
        except (TypeError, ValueError):
            variant = random.randint(0, 5)
        fit, note = "", ""
        edit = await _parse_image_edit(instruction, head, eyebrow)
        op = (edit.get("op") or "other").lower()
        if op == "text" and (edit.get("headline") or "").strip():
            head, sub = teampost.split_message(edit["headline"].strip())
            note = f'Updated the text to “{edit["headline"].strip()}”.'
        elif op == "background" and (edit.get("background") or "").strip():
            theme = edit["background"].strip()              # person stays; only the scene changes
            note = f'Changed the background to {theme}.'
        elif op == "fit":
            fit = (edit.get("fit") or "fit").lower()
            note = "Adjusted how the person fits the frame."
        elif op in ("design", "other"):
            variant = random.randint(0, 5)                  # a fresh take on the same brief
            note = "Refreshed the design."
        if (edit.get("eyebrow") or "").strip():             # optional standalone label change
            eyebrow = edit["eyebrow"].strip()
            note = note or f'Changed the label to “{eyebrow}”.'
        # A Chat house-style hero regenerates through chatpost (consistent look; a fresh photo/bg/template) —
        # NOT the old editorial scene renderer. This also avoids a gpt-image call, so it can't 429-error.
        is_chat_hero = (body.get("style") == "chat_hero" or meta_in.get("renderer") == "chat_talentrupt") \
            and not in_campaign
        if is_chat_hero:
            from . import chatpost
            # A conversational edit on a Chat house-style post keeps the SAME person + layout + text and
            # changes the BACKDROP (this branch used to ignore the edit and re-render an identical image).
            # Rotate to a different backdrop variant unless the edit only touched the text.
            try:
                prev_variant = int(body.get("bg_variant") or meta_in.get("bg_variant") or 0)
            except (TypeError, ValueError):
                prev_variant = 0
            change_bg = op in ("background", "design", "other")
            new_variant = prev_variant
            if change_bg:
                new_variant = chatpost.mission_variant(instruction, prev_variant)
                if new_variant == prev_variant:          # keyword landed on the current one -> force a change
                    new_variant = (prev_variant + 1) % chatpost.MISSION_BG_COUNT
                lo = (instruction or "").lower()
                if any(w in lo for w in ("warm", "cozy", "cosy")):
                    note = "Warmed up the background — same person, same layout."
                elif any(w in lo for w in ("bright", "light", "vivid", "vibrant", "lighter")):
                    note = "Brightened the background — same person, same layout."
                else:
                    note = "Switched to a fresh background — same person, same layout."
            hp = await chatpost.build_chat_post(brand, concept=(head or name), count=1, person_photo=raw,
                                                person_name=name, headline=(head or name), subtext=sub,
                                                person_role=role, bg_variant=new_variant)
            if not hp:
                return None
            path, _fn, m = hp[0]
            file_path, file_url, new_meta = path, m["url"], dict(m)
            new_meta["bg_variant"] = new_variant
            new_body = {"person": name, "role": role, "headline": head, "subline": sub, "kind": "team",
                        "style": "chat_hero", "employee_id": emp_id, "template": m.get("template"),
                        "bg_variant": new_variant}
        else:
            path, _fn, m = await teampost.build_ai_scene(
                brand, raw, name=("" if in_campaign else name), role=("" if in_campaign else role),
                headline=head, question=sub, variant=variant, theme=theme, eyebrow=eyebrow, fit=fit)
            file_path, file_url, new_meta = path, m["url"], dict(m)
            new_body = {"person": name, "role": role, "headline": head, "subline": sub, "kind": "team",
                        "style": m.get("style", "ai"), "employee_id": emp_id,
                        "variant": m.get("variant", variant), "eyebrow": eyebrow}
        if team_label:
            new_meta["team_photo"] = team_label
        if emp_id:
            new_meta["employee_id"] = emp_id
        if note:
            new_meta["refine_note"] = note
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
        campaign_id=a.campaign_id, owner=getattr(a, "owner", None) or "admin", type=a.type, title=title[:380],
        body=new_body, file_path=file_path, file_url=file_url, meta=new_meta,
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return new
