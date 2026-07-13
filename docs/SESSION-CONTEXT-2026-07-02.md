# Session Context — Talentrupt / Myra Marketing Agent

- **Date:** 2026-07-01 → 2026-07-02
- **Branch:** `feat/create-chip-brief-intake`
- **Live:** https://myra.htuniverse.com (shared DigitalOcean droplet, single PM2 process `myra` on :8100)
- **Release:** `deploy/ship.ps1 "<msg>"` → builds frontend gate → commits → pushes → GitHub Actions
  (`.github/workflows/deploy.yml`) rebuilds UI on the runner, ships to the droplet, `pm2 restart myra
  --update-env`, health-checks. Verify with `curl https://myra.htuniverse.com/api/health` → `version` = commit SHA.
- **Stack:** Next.js 16 static export (frontend) + FastAPI / SQLAlchemy 2 / SQLite (backend); OpenAI
  `gpt-4o-mini` (text) + `gpt-image-2` / `gpt-image-1` (images).

---

## TL;DR

This session did three families of work:

1. **Chat attachments** — the attached file now shows in the transcript next to the prompt, clears from the
   composer the instant you hit send, and opens in an in-app lightbox (same tab). Fixed in **both** the main
   Chat and the Campaign studio.
2. **Folders** — clicking an employee photo opens it full-size in an in-app lightbox.
3. **Employee-featured images** — a long iteration that **settled on this rule: the employee's REAL face is
   NEVER changed; only the design around them varies.** (See the dedicated section below — this flip-flopped
   and the final state is what matters.)

Everything is shipped and live (final version `6fa655a`).

---

## The employee-image feature — FINAL settled state (read this)

This is the part that changed the most across the session, so here is the **current, authoritative**
behavior (superseding earlier commits):

### The rule
> Change everything — background, background colour, theme, fonts, colours, layout — **but never change the
> person's face.**

### How it works now (`backend/app/generation/teampost.py` → `build_ai_scene`)
The employee's **real photo is composited** (face + clothes untouched). The **design rotates** so posts
don't look identical:

- **Design A — `_build_phone_banner`:** the real photo inside a clean **portrait iPhone-frame mockup**
  (`_place_person_phone`: titanium rail, charcoal bezel, dynamic-island notch, soft drop shadow, glass rim).
  Skin colours (light / cream / navy / red) rotate. Caption on a reserved LEFT column.
- **Design B — `_build_scene_banner`:** the real person on a **varied AI-generated background**
  (`_scene_prompt` → gpt-image makes the **scene only, no people, no text**), with the real cut-out (or a
  premium framed card) composited on top via `_place_person`. This is the "change the background, keep the
  face" look.
- Rotation: Design B ~2/3, Design A ~1/3 (`variant % 3`). B falls through to A if the AI background is
  unavailable; any failure → a deterministic series template (`build_team_image`, still the real face).
- **No overlaps:** `_ensure_clear` asserts mutually-disjoint bounding boxes (device/photo, headline, subline,
  featuring block, wordmark).

### What is explicitly NOT done anymore
- **No image-to-image (img2img) edit on the person.** An earlier iteration fed the real photo into
  gpt-image-1's edit endpoint (`input_fidelity=high`) to re-pose / re-dress / re-background the person. It
  produced great-looking, *varied* portraits **but repainted the face** — the featured employee came out
  looking like a *different person*. That is removed. (`_phone_portrait_img`, `_ai_portrait_canvas`,
  `_portrait_prompt`, `_phone_portrait_prompt`, `_PORTRAIT_LOOKS`, `_PHONE_WEAR` are now dead code, left in
  place but unused.)

### Trade-offs the user accepted
- **Real face ⇒ real clothes.** Keeping the exact face means keeping the exact photo, so there is **no AI
  blazer** (an AI blazer requires repainting the person → changes the face). To feature someone in a blazer,
  upload a photo where they wear one.

### To make it even better (optional, needs one secret)
- **Enable clean cut-outs on prod:** add a `BG_REMOVAL_API_KEY` (remove.bg free tier; optional
  `BG_REMOVAL_PROVIDER=removebg`) as a **GitHub Actions secret**. The deploy already injects it into the
  droplet `.env`. With it, Design B floats the real person directly on the AI background (a clean cut-out);
  without it, Design B uses a premium framed card. Heavy `rembg`/`onnxruntime` is deliberately kept OFF the
  2 GB droplet.

---

## Requests handled this session (chronological)

1. **Attachment not displaying in chat** → the file now renders next to the prompt (image thumbnail / file
   chip). The backend already *read* the file (text extracted, image captioned); only the display was
   missing. Applied to the main Chat first, then the Campaign studio (which has its own chat).
2. **Attachment stays in the composer after send** → now snapshotted onto the message and the composer
   clears immediately (removed the "staged photo" retention).
3. **Image in a message opens in a new tab** → now opens an in-app same-tab lightbox (new shared
   `frontend/components/ImageLightbox.tsx`; click-outside / Esc to close).
4. **Click an employee photo in Folders** → opens a full-size in-app lightbox (Download / Close / Esc).
5. **"Best AI picture using the employee's photo" / "same images every time"** → explored img2img +
   iPhone-frame + blazer, then **reverted** per the face rule above.
6. **Hallucination — "@Pooja + attached design screenshot" produced random invented people** → a known
   `@mention` of a Folders employee now wins over an attachment (their real photo is the subject; the
   attachment is a reference), and the portrait prompt hard-requires exactly one person. (This was on the
   img2img path; the face rule later superseded the person-repaint entirely.)
7. **Portrait iPhone frame** → designed via a multi-agent "senior graphics team" workflow (4 designers →
   art-director synthesis) and implemented as `_place_person_phone`.
8. **Don't change the face** → the final revert to real-photo compositing.

---

## Files changed

### Backend
- `backend/app/generation/teampost.py` — the employee-image engine: `build_ai_scene` (design rotation,
  real-photo composite), `_build_phone_banner` (Design A), `_build_scene_banner` (Design B),
  `_place_person_phone` (iPhone mockup), `_scene_prompt` (clean AI background, no ghost text), skins.
- `backend/app/providers/llm.py` — `generate_image_edit` gained opt-in `input_fidelity` + `mime`, and now
  prefers **gpt-image-1** for `/images/edits` (gpt-image-2 returns 400 on edits). *(Still used by the
  campaign/deck style-transfer callers; the employee path no longer edits the person.)*
- `backend/app/agent/orchestrator.py` — a known `@mention` of a Folders employee is the subject even when an
  image is attached (escape hatches: "use this photo", or an unknown @name).
- `backend/app/agent/tools.py` — `exec_feature_employee` default routing.
- `.github/workflows/deploy.yml` — injects `BG_REMOVAL_API_KEY` (+ `BG_REMOVAL_PROVIDER`) from a GitHub
  secret into the droplet `.env` (same CRLF-safe, re-export-before-restart path as the OpenAI key).

### Frontend
- `frontend/components/ImageLightbox.tsx` — **new** reusable in-app lightbox (same-tab preview).
- `frontend/components/ChatProvider.tsx` — snapshot attachments onto the user message + clear composer on send.
- `frontend/components/ChatPanel.tsx` — render attachments on the user message; open thumbnail in the lightbox;
  look-aware refine chips.
- `frontend/components/CampaignsView.tsx` — same attachment display + clear-on-send + lightbox for the
  Campaign studio chat.
- `frontend/components/FoldersView.tsx` — clickable employee photo → lightbox.
- `frontend/components/RefineChips.tsx` — person-aware refine options.
- `frontend/lib/types.ts` — `ChatMessage.attachments?`, `Attachment.previewUrl?`.

### Docs
- `APPLICATION.md` and `CHANGELOG.md` updated each commit (project rule).

---

## Deploys this session (all live)

| SHA | Summary |
|-----|---------|
| `1ebd0c5` | Auto-enhance every employee photo + designed scene; wire `BG_REMOVAL_API_KEY` into deploy |
| `6654305` | (superseded) img2img "AI portraits" + attachment display + Folders photo preview + look-aware refine |
| `25b9cc0` | Edit endpoint prefers gpt-image-1 (gpt-image-2 400s on `/images/edits`) |
| `7c75249` | Campaign attachments show in chat + `@mention` wins over an attached reference |
| `f381709` | (superseded) Portrait iPhone-frame banner (senior-graphics-team design) |
| `30d58d4` | Attachment clears on send + in-app lightbox + varied employee designs (rotation) |
| `5c31ade` | (superseded) Employee portraits wear a blazer + favour the full-scene look |
| `6fa655a` | **CURRENT** — never change the face: revert img2img, composite the REAL photo, vary the design only |

"(superseded)" = later work changed that behavior; `6fa655a` is the authoritative current state for the
employee-image feature.

---

## Open recommendations / follow-ups

1. **Enable remove.bg** (GitHub secret `BG_REMOVAL_API_KEY`) for clean cut-outs on prod — biggest single
   quality win for Design B; employee photos have clean backgrounds so it will cut out perfectly.
2. **Blazer vs real face** — currently real face wins (no AI blazer). If a blazer is wanted, use a photo of
   the person actually wearing one.
3. **More design families** — currently Design A (iPhone) + Design B (AI background). An editorial magazine /
   split layout could be added to the rotation for more variety (all still real-face).
4. **Dead code cleanup** — the unused img2img helpers in `teampost.py` can be deleted when convenient.

---

## How to build / ship / verify

```powershell
# One-command release (build gate → commit → push → auto-deploy):
./deploy/ship.ps1 "short description of what changed"

# Then confirm the deploy is live (version == the new commit SHA):
curl https://myra.htuniverse.com/api/health
```

- Backend-only render checks: run the app's venv Python and call `teampost.build_ai_scene(...)` directly
  (no server needed) — it writes PNGs under `storage/images/`.
- Frontend preview: `.claude/launch.json` defines the `frontend` dev server (port 3000); it talks to a local
  backend at `http://127.0.0.1:8000` (`frontend/.env.local`).
- Local backend: `backend/.venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`.

---

*Generated 2026-07-02 as a session hand-off. The authoritative living docs are `APPLICATION.md` (master app
doc) and `CHANGELOG.md` (most-recent-first history).*
