# Talentrupt AI — Application Reference

> **This is the single source of truth for the whole application.** It is kept up to date after every
> change. For the chronological list of changes see [CHANGELOG.md](CHANGELOG.md); for deploy mechanics see
> [deploy/DEPLOY.md](deploy/DEPLOY.md).

Last updated: 2026-06-30

---

## 1. What it is
An internal AI marketing workspace for **Talentrupt** (an offshore RPO — "RPO Done Right"). One logged-in
team uses it to chat with an AI assistant, generate on-brand content (posts, images, decks, PDFs), run
internal/external marketing campaigns, and do lead generation ("Business Dev"). Live at
**https://myra.htuniverse.com**.

The **app's UI is branded "Myra" / "Marketing Agent"** (header, login, loading screen, page title, favicon
— see `components/MyraLogo.tsx` for the M mark and `app/icon.svg` for the favicon). This is product chrome
only: the **content** the app produces is still Talentrupt's (brand grounding, "Promote Talentrupt",
"Why Talentrupt fits") — those references are intentional and stay.

## 2. Stack & architecture
- **Frontend:** Next.js 16 (React 19), Tailwind v4. Built as a **static export** (`output: 'export'` →
  `frontend/out`). Client-side SPA; talks to the backend over `/api`.
- **Backend:** FastAPI + SQLAlchemy 2 + SQLite (WAL). Pydantic-settings reads `backend/.env`.
- **AI:** OpenAI — `gpt-4o-mini` (text), `gpt-image-2` (images; auto-falls back to `gpt-image-1` if the key lacks access), `text-embedding-3-small` (RAG).
  Providers are gated: `LLM_PROVIDER`/`IMAGE_PROVIDER` must be `openai` or you get a deterministic fallback.
- **Single process:** in production the FastAPI/uvicorn process serves BOTH the static UI and the API —
  no separate Node server. (Dev runs them apart: `next dev` :3000 + uvicorn :8000.)

```
Browser ──HTTPS──▶ Nginx (myra.htuniverse.com) ──▶ uvicorn :8100
                                                     ├─ /api/*  → FastAPI (REST + SSE + /api/files)
                                                     └─ /*      → static UI (frontend/out)
```

## 3. Sections (features)
| Section | What it does | Who can see it |
|---|---|---|
| **Chat** | All-access assistant with tools (generate content, prospect, read app data) — streams via SSE | all |
| **Create** | Visual/document generation studio (image / deck / PDF) | all |
| **Campaigns** | **Internal** (promote Talentrupt: chat-driven content folder grounded in a brief) + **External** (client-targeting: sector → prospects → dated content calendar) | all |
| **Business Dev** | Find/analyze real hiring companies as prospects (incl. **vibe prospecting** — describe the ideal client in plain English → ranked real list); outreach drafts; pipeline tracking | all |
| **Folders** | **Reference photo library** of employees (photo + name + role). Feature them in **Create/Chat** by typing **`@`their name** → a post with their **real** photo (never an AI face) | all |
| **Tasks** | Follow-up reminders | **admin only** |
| **Analytics** | Pipeline/outreach/content rollup | **admin only** |

## 4. Accounts, roles & data isolation
- Two logins (from `backend/.env`): **`Admin@talentrupt.com`** (admin) and **`nishant@talentrupt.com`**
  (member). Role is derived server-side from the bearer token (`/api/auth/me`).
- **Tasks & Analytics** are admin-only — hidden in the nav AND enforced 403 at the API.
- **Per-account data isolation:** every owned record carries an `owner` column and is scoped to the
  logged-in account (conversations, campaigns, assets, opportunities, tasks, uploads). Cross-account
  access returns 404. Pre-existing rows are assigned to **admin** by a startup migration.

## 5. Data model (`backend/app/models.py`)
- **Owned (per-account, have `owner`):** `Conversation` (chat/create/campaign threads) · `Campaign`
  (internal/external) · `Asset` (post/image/deck/pdf/video) · `Opportunity` (Business Dev) ·
  `CalendarTask`.
- **Children (scoped via parent):** `Message` (→conversation) · `CampaignItem`, `CampaignProspect`
  (→campaign).
- **Shared / global:** `Brand` (the Talentrupt brand) · `SourceFile` + `BrandChunk` (brand knowledge
  library; `SourceFile.owner` is NULL for the shared library, a role for a user upload) · `AppSetting`.

## 6. Generation pipeline (`backend/app/generation/`)
- `posts.py` — captions/posts. `images.py` — `gpt-image-1` art (`_plan` art-director plans a topic-specific
  **`scene`** used as the AUTHORITATIVE subject so imagery stays on the post's topic; a per-image
  **palette + decoration variety** pass (`_variety`) so posts don't all share one skin — RPO stays
  brand-weighted, internal campaigns roam; a **blur gate** that measures sharpness and regenerates a soft
  frame keeping the sharpest, then a gentle `_crispen`; a **contrast gate** that rejects washed-out/hazy
  frames; and a clean brand **footer band** (`_brand_footer`) carrying the official wordmark beneath the
  art so the logo never covers content) and a deterministic compositor fallback. `decks.py` — PPTX.
  `pdf.py` — branded PDFs. `teampost.py` — real-person posts (NEVER an AI face), with the official
  **wordmark** in the layout's reserved bottom margin. Employee/`@mention` posts default to an
  **AI-designed scene** (`build_ai_scene`: gpt-image-2 makes an on-theme branded background from the post's
  message; the real photo is floated via `rembg` if present, else placed in a designed framed card).
  `refine.py` — regenerate/refine an asset into a new version.
- **Brand grounding:** generators use `knowledge/retrieve.py` (`brand_context`, `image_references`) over
  the ingested TR library. **Campaign** generation grounds in the campaign's **brief** (`Campaign.goal`),
  threaded into every generator so content stays on the campaign's theme (no off-theme RPO leakage).

## 7. Agent (`backend/app/agent/`)
- `orchestrator.run(db, conversation_id, text, mode, attachments, campaign_id, owner)` — drives the tool
  loop and streams events (meta/status/token/asset/chips/done/error). `mode` ∈ chat | create | campaign.
  A **brief-intake** (`create_intake`) asks a short chip-driven brief before generating a vague asset —
  in Create/Campaign always, and in **Chat** for creation requests (`is_visual_create_request`); an
  `@mention` short-circuits straight to the person post before the intake.
- `tools.py` — the tool registry + executors (`generate_posts`, `generate_image`, `generate_team_image`,
  `feature_uploaded_person`, `feature_employee` (feature a Folders employee by @name using their real
  photo), `build_deck`, `build_pdf`, `discover_prospects`, `vibe_prospect` (**vibe prospecting** — NL
  ideal-client → `discover.vibe_to_icp` → ranked real companies), `draft_outreach`, etc.). `tools_for(mode)` picks the
  set per section. Every created record is stamped with `state['owner']`, and **every READ tool must
  filter by `state['owner']`** too (e.g. `list_campaigns`/`list_assets`) — otherwise chat leaks another
  account's data and miscounts. `list_campaigns` also splits by `type` (internal vs external) so counts
  aren't conflated.
- **Rule:** every new app feature must also be exposed to the Chat agent (a tool + prompt) so Chat can do
  it too.

## 8. Key API endpoints (`backend/app/main.py`)
- Auth: `POST /api/auth/login`, `GET /api/auth/me`, forgot/reset.
- Streams (SSE): `POST /api/chat|create/stream`, `POST /api/campaigns/{id}/stream`.
- Conversations, Campaigns (+items/prospects/plan/export), Assets (`/api/assets`, regenerate, delete),
  Business Dev (`/api/business/*`, `/api/opportunities/*`), Tasks, `GET /api/analytics/summary`,
  uploads (`/api/chat/attach`, `/api/knowledge/upload-brand-file`), `GET /api/files/{kind}/{name}`.

## 9. Configuration (`backend/.env`)
Template: `backend/.env.example`. Must-sets for real AI: `LLM_PROVIDER=openai`, `IMAGE_PROVIDER=openai`,
`OPENAI_API_KEY`. Accounts: `ADMIN_PASSWORD`/`MEMBER_PASSWORD`, `ADMIN_TOKEN`/`MEMBER_TOKEN` (random in
prod). Also `CORS_ORIGINS`, `STORAGE_DIR`, `KNOWLEDGE_ZIP_PATH`/`BRAND_LOGO_PATH` (brand grounding).

## 10. Run & deploy
- **Dev:** backend `uvicorn app.main:app --port 8000` (in `backend/`, venv); frontend `npm run dev` (`frontend/`, :3000).
- **Prod:** single PM2 process `myra` on the shared droplet at `myra.htuniverse.com`.
- **Release = one command: `deploy/ship.ps1 "what changed"`** — it (1) builds the frontend locally as a
  pre-flight gate, (2) commits, (3) pushes. The push triggers
  [.github/workflows/deploy.yml](.github/workflows/deploy.yml), which rebuilds the UI on GitHub's runner
  (full RAM), ships code + built UI to the droplet, and `pm2 restart myra` — then health-checks `/api/health`.
  **No manual droplet steps.** `.env`, `talentrupt.db*` and `storage/` on the server are never touched.
- **One-time enablement** (needed once, by someone with droplet access — CI can't bootstrap server trust
  itself): authorize a deploy key on the droplet and add two GitHub repo secrets `DROPLET_HOST` +
  `DROPLET_SSH_KEY`. Steps: [deploy/DEPLOY.md](deploy/DEPLOY.md) → "Auto-deploy enablement".

## 11. Hard rules (do not break)
- **Never AI-generate or alter a real person's face** — team posts use real photos only.
- **Never fabricate data** — counts/names/metrics must be real; report tool results verbatim.
- **Every feature is also a Chat tool** (see §7).
- **Per-account isolation** — never query owned data without the owner filter (see §4).

## 12. Repo map
```
frontend/        Next.js app (components/, lib/api.ts, lib/types.ts, app/, next.config.ts)
backend/app/     main.py (API) · models.py · db.py · config.py · agent/ · generation/ · business/ · knowledge/
deploy/          DEPLOY.md · bootstrap.sh · nginx-myra.conf · deploy.sh
.github/workflows/deploy.yml   auto-deploy on push
ecosystem.config.js            PM2 (single process)
APPLICATION.md (this) · CHANGELOG.md
```
