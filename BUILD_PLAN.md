# Talentrupt Marketing Agent — Build Plan (v2 rebuild)

> Single source of truth for the new build. Supersedes the old `Management Agent` codebase
> and its tangled `PRODUCT_CONTEXT.md`. Read this before any change; update it after any change.

Status: **Phase 4 complete & verified (2026-06-17). Phase 5 (polish/publishing) next.**
Owner: Rushikesh (rushikesh@hiretalent.com) · Date: 2026-06-17

### Build log
- **2026-06-17 — Business Dev: removed Target-profile dropdown (redundant with Industry).** Per
  user: the profile selector overlapped the Industry filter, so removed it from the bar + state
  (`profiles`/`profileKey`/`getBusinessProfiles` gone); discovery now passes `profile_key=null` →
  backend defaults the target to the focus text or "companies hiring at volume", driven by Industry +
  filters + focus. Filter bar = Title · Industry · Company size · Location only. (The 5 ICP profiles
  remain in `business/profiles.py` + the `/api/business/profiles` endpoint, unused, in case we want a
  "Signal/Trigger" filter later for newly-funded / volume-hiring plays.) Verified: profile icon gone,
  no select, Find prospects works; tsc clean; no console errors. Frontend-only.
- **2026-06-17 — Business Dev: filtered history + profile-as-icon.** The prospect list now reflects
  the active filters (`filteredOpps` memo: Industry→segment keyword map `industryMatch`, plus
  keyword/title text match; no filters → all visible) with a no-match state and a **Clear filters**
  button (also an X icon in the bar). The target-profile selector moved INTO the filter bar as an
  icon-dropdown (`FilterControl` gained `wide`/`noDot`; big `<select>` removed). Verified in-browser:
  65 accumulated prospects (multiple searches accumulate via `mergeById`); Industry=Healthcare →
  list 65→28 all-healthcare; Clear → restored 65 + icons reset; no console errors. Frontend-only.
- **2026-06-17 — Business Dev: LinkedIn-style filters + senior contacts.** Find prospects gained a
  compact **icon+dropdown filter bar** (Title/Role, Industry, Company size, Location — `FilterBar`/
  `FilterControl` in `BusinessView`; icons only, value shown + red dot when set). Filters flow to
  `discoverProspects(... , filters)` → `POST /api/business/discover {filters}` → `discover()` builds a
  filter clause + **prioritizes LinkedIn** as the primary source; default count 8 (more clients/search).
  Contacts strengthened: `_FIELDS` now requires **3-6 SENIOR decision-makers, minimum Director** —
  must include CEO + all identifiable C-suite (COO/CFO/CTO/CHRO) PLUS a Director/VP of TA/HR; cap
  raised to 6; LinkedIn profile/people-search URLs. Verified: filtered healthcare search → 5 scored
  companies each with CEO+VP TA+CFO/COO (LinkedIn); filter UI works (icon dropdowns, active state);
  tsc clean; no console errors.
- **2026-06-17 — Campaigns: clean rail + conversational intake.** (1) The planner rail now lists
  only real planned campaigns — `GET /api/campaigns?status=planning` (planner campaigns have
  status="planning"); old test/junk campaigns are hidden (their assets stay in Create's gallery), and
  truly-empty ones (0 assets + 0 items) were pruned. (2) Replaced the structured New-campaign form
  with a **conversational intake** — `planner.interpret_intent` (LLM decides ask-one-question vs
  plan-now, infers goal/audience/channels/timeframe), endpoint `POST /api/campaigns/plan-chat`
  (reuses `_build_planned_campaign`), and `NewCampaignChat` in `CampaignsView` (chat bubbles +
  starters → describes intent → plans → opens the new folder). Verified: rail shows only planned
  campaigns; chat intake created a 6-week / 12-item campaign and opened it; tsc clean; no console errors.
- **2026-06-17 — "Campaigns": future-campaign planner.** New 4th nav section (Chat · Create ·
  Campaigns · Business Dev). Set goal/audience/channels/timeframe → AI writes a brief + a DATED
  content calendar; each item has an on-demand **Generate** button (post/image/deck/pdf) that runs
  the existing engines and links the asset. New: `campaigns/planner.py` (`plan_campaign`, grounded
  via `retrieve.brand_context`), `CampaignItem` model (new table), endpoints
  `POST /api/campaigns/plan` + `POST /api/campaign-items/{id}/generate` + items in
  `GET /api/campaigns/{id}`. Frontend: `CampaignsView` (rail + new-campaign form + brief +
  calendar w/ per-item generate, reuses `AssetCard`/`EmptyState`). Ingested the **TalentRupt RPO
  Sales deck** into the brand library (config `knowledge_extra_pdfs`; `ingest.run_ingest` now also
  processes standalone PDFs; incremental — +1 file/+10 chunks, no re-vision) so briefs/content cite
  the real pitch. Verified: deck grounds `brand_context`; plan → brief + 8 dated items; per-item +
  form generate work in-browser; tsc clean; no console errors. Out of scope: auto-publishing.
- **2026-06-17 — Business Dev: multi-contact + timing + 2-col composer.** Moved from one
  `decision_maker` to a `contacts[]` array (2-4 decision-makers: name/role/linkedin/email each) and
  added a `timing` object (`reach_now` + label Reach now/Monitor/Hold + reason) — generated in both
  `discover.py` (`_FIELDS`, `_norm_contacts`, `_norm_timing`) and `analyze.py` (reuses `_FIELDS`,
  emphasizes timing). Back-compat: legacy `decision_maker*` fields still derived from the primary
  contact (outreach unchanged). `main._save_opp` stores `contacts`+`timing` in `Opportunity.why`.
  Frontend: `BusinessView` composer split into two cards (Find prospects left, Analyze right);
  `DecisionMaker` → `Contacts` (grid of contact cards w/ LinkedIn + email + unverified) + a colored
  `TimingBanner`. Verified: analyze "Stripe" → Reach now + reason + 3 contacts (Collison ×2 +
  Gaybrick) with LinkedIn; emails left blank when unknown (no fabrication); tsc clean; no console errors.
- **2026-06-17 — Generation-quality overhaul (decks/images/RAG).** Root causes found via a 4-agent
  audit: decks were ONE hardcoded python-pptx template (identical every time, no imagery, text-only
  grounding); images converged to "hand-holding-a-card" because the style-direction strings literally
  prescribed it + the planner preferred 3 card styles; and "not referring to context" was real —
  chat text used NO retrieval (grounded tools weren't wired; search was opt-in), 73/80 image captions
  were identical boilerplate so image refs were topically wrong (nonsense queries returned 4 confident
  hits), and 178/258 chunks were char-spaced PDF garbage.
  Fixes: DECKS now LLM-plan a layout PER slide (cover/section/bullets/metric/two_column/quote/
  comparison/closing) with 7 renderers + an AI cover image grounded on real decks (`decks.py`).
  IMAGES: removed the hand-card motif, added a `composition` field + "be inventive" art direction,
  default style no longer a card; refs de-dupe + relevance floor + "original composition" (`images.py`).
  RAG: chat injects `brand_context` every turn (`orchestrator.py`); `retrieve` k=8, max_chars=700,
  source titles, MIN_TEXT/IMAGE_SCORE floors, image_references n=3 + de-dupe. RE-INGESTED: new topical
  VISION_PROMPT (leads with topic/headline/format) + filename prepend + PDF `_despace()`; cleared &
  re-ran → 113 files / 215 chunks, **0/80 boilerplate captions**. Create generate_image = 1 image.
  Verified: topical captions, relevant refs ("RPO reliability"→scalability/delivery posts), floor
  drops nonsense (0), image is now a full-bleed team photo (not a card), deck has AI cover + varied
  slides, chat grounded (0 assets). Re-run ingestion anytime via `backend/reingest.py`.
- **2026-06-17 — UI polish + BD contacts + Create single-output.**
  UI: refreshed `globals.css` (deeper navy palette, red→coral `--grad-red`/`--grad-navy`, ambient
  background, component classes `.btn-primary`/`.btn-ghost`/`.card`/`.chip`/`.field`); new
  `components/Avatar.tsx` (initials w/ deterministic color) + `EmptyState.tsx`; `Shell` gained a
  user-profile footer + gradient active-nav pill; `Login`/`AuthGate` polished; BusinessView list got
  avatars + color-coded status chips (`STATUS_STYLE`). Kept navy/red/cream (no pink), no Dashboard.
  Business Dev: discovery/intake now return `decision_maker_linkedin` (profile or people-search URL)
  + `decision_maker_email` (best-effort), stored in `Opportunity.why`, shown in a `DecisionMaker`
  block (LinkedIn link + email + Copy + "unverified" chip). Create: suggestions → single-output;
  `generate_image` schema dropped `count` (one image/request); `CREATE_GUIDANCE` no longer promotes
  multiples. Verified: discover returns contacts, create emits exactly 1 image, tsc clean, refreshed
  UI in-browser, no console errors. DEFERRED (user): Gmail/LinkedIn account connections.
- **2026-06-17 — Restructure: Chat (assistant) + Create + Business Dev.** Talentrupt has no real
  campaigns, so "Campaigns" was retired. **Chat** is now a general marketing ASSISTANT (text/advice
  only — captions, hashtags, copy, "how to boost a post"; tool set = `search_brand_knowledge`).
  **Campaigns + Studio merged into "Create"** — chat-driven image/deck/PDF generation (tool set =
  `generate_image`/`build_deck`/`build_pdf`, no campaigns; assets saved `campaign_id=None`) with a
  **"Your past generations"** gallery tab. Business Dev unchanged. Image count cap raised to 10.
  - Backend: `orchestrator.run(..., mode)` + `tools.tools_for(mode)` (CHAT_TOOL_NAMES vs
    CREATE_TOOL_NAMES); `prompts.build_system_prompt(brand, mode)` (CHAT_GUIDANCE/CREATE_GUIDANCE);
    `main._stream(req, db, mode)` → `POST /api/chat/stream` (mode chat) + new `POST /api/create/stream`
    (mode create); `Conversation.kind` (chat|create) + idempotent SQLite `ADD COLUMN` migration in
    `db._migrate_sqlite()`; `GET /api/conversations?kind=`.
  - Frontend: `ChatProvider.makeChatStore(endpoint, kind)` → `ChatStore`/`useChat` +
    `CreateStore`/`useCreate`, both mounted in `AuthGate` (persist across tabs). New
    `components/CreateView.tsx` (Generate + Your-past-generations tabs) + `app/create/page.tsx`.
    Nav → Chat/Create/Business Dev. Deleted `app/campaigns`, `app/studio`, `CampaignsView`,
    `StudioView`, `Placeholder`. `streamChat(..., endpoint)`, `getConversations(kind)`.
  - Verified: chat returns text-only (10 hashtags, 0 assets); create generates images
    (campaign_id null); kind filter works; nav correct; gallery shows past generations w/
    download+delete; chat + create both persist across tab switches; tsc clean; no console errors.
  - Note: leftover test "campaign" rows are now invisible to the UI (campaign endpoints unused).
- **2026-06-17 — UX pass (chat history, campaign cleanup, richer images).**
  CHAT: lifted chat state into `ChatProvider` (mounted in AuthGate, above routed pages) so the
  conversation survives tab switches; added a conversation-history rail (New chat + reopen past
  chats via `/api/conversations`); assistant messages now persist with their asset cards.
  CAMPAIGNS: one-off generations route to a single shared **"Quick Content"** folder (stops junk
  folders); `create_campaign` reuses same-named campaigns (de-dupe); collapsible "Campaign brief"
  (KPIs tucked away); rename / delete / **export-zip** / per-asset copy+delete. New routes:
  PATCH+DELETE `/api/campaigns/{id}`, `/api/campaigns/{id}/export`, DELETE `/api/assets/{id}`.
  IMAGES: per user choice, default to RICH styles (photographic/decorative/ui_mockup) and use real
  past posts as references ONLY for rich styles (they flatten clean infographic). Added
  `style` to the image planner + `llm.generate_image_edit()` (gpt-image-1 edits/reference endpoint)
  + `retrieve.image_references()`. Verified: persistence (nav away/back keeps the chat),
  Quick Content routing, rename/delete/export/asset-delete, rich reference-grounded samples.
  NOTE: layout is desktop-first — the conversation rail is hidden below the `md` breakpoint.
- **2026-06-17 — Real AI image generation (gpt-image-1).** Added `IMAGE_PROVIDER=openai` →
  `gpt-image-1` (high quality, 1024²) producing rich, illustrative, on-brand graphics. Prompt is
  grounded in the brand system + retrieved past-post aesthetics (Phase 3 captions) + the AI-planned
  content (headline/layout/metric). Concurrent for multi-image sets. The deterministic compositor
  stays as automatic fallback (API failure) and as an explicit mode (`IMAGE_PROVIDER=compositor`)
  for guaranteed-perfect text. New: `llm.generate_image_bytes()`, `images._openai_prompt/_openai_image`,
  config `openai_image_{model,quality,size}`. Verified: clean premium designs, correct headline text.
  **Tradeoff:** gpt-image-1 renders headlines/short text cleanly but can garble DENSE small text
  (e.g. 3rd line of a steps infographic) — known model limitation. ~50-60s/image at high quality.
- **2026-06-17 — Generation quality fixes (user feedback).** (1) Healthcare bleed: the image
  compositor hardcoded `proof_points[0]` ("500+ healthcare roles") on every image — now image
  CONTENT is LLM-planned from the actual topic (no forced healthcare/recruiting metric on holidays,
  culture, data, etc.). (2) Multiple images: `generate_image` gained a `count` (1-4) producing
  distinct variations. (3) Variety/quality: 4 image layouts (metric/statement/steps/comparison) ×
  navy|cream backgrounds; deck redesigned with bullet cards, numbered markers, slide numbers,
  brand footer, and statement/section slides. Verified: a data-driven request produced 3 distinct
  on-topic images (statement/metric/steps), no healthcare default.
- **2026-06-17 — Phase 1 done.** Installed Node 24.16.0 (winget) + reused Python 3.13.5
  for `backend/.venv`. Backend (FastAPI) and frontend (Next.js 16.2.9 / React 19.2.4) scaffolded.
  Verified in-browser: admin login, brand-grounded streaming chat (SSE), 4-surface shell,
  no-key honest fallback, CORS 3000→8000. Fixed a React-Strict-Mode token-duplication bug
  (impure setState updater → made immutable). Backend run: `backend/.venv` uvicorn on :8000;
  frontend: `npm run dev` on :3000 (preview launch config in `.claude/launch.json`).
- **2026-06-17 — OpenAI key wired.** `LLM_PROVIDER=openai`, model `gpt-4o-mini` (override in
  `backend/.env`). Verified real on-brand streaming output in-browser ("AI online · openai").
  Hardened `config.py` to coerce empty `.env` values to safe defaults (an empty `DATABASE_URL=`
  had crashed boot). Run backend WITHOUT `--reload` to avoid orphaned reloader processes.
  Brand-learning source confirmed: `C:\Users\Admin\Downloads\TR POSTS ZIP.zip` (1.4 GB) — Phase 3
  will index structure + sample intelligently (too large to load wholesale).

---

## 1. What we are building

An internal AI marketing agent for **Talentrupt** (offshore RPO; tagline "RPO Done Right").
It behaves like an entire marketing department on call — strategist, copywriter, designer,
BD scout, deck-maker — and its defining value is that **everything comes out on-brand and
ready to use**, not rough drafts.

### Principles (non-negotiable)
1. **Request = action.** Chat executes and produces a saved asset; it never replies "I can…".
2. **Chat is the brain.** Every capability is reachable from chat. Other surfaces are output views.
3. **Feel = ChatGPT + Canva + Gamma.** Simple, fast, streaming, visual. Powerful behind the scenes.
4. **No internals leak to the user.** Never show reasoning, tool calls, DB ops, or "loading context".
5. **On-brand by default.** Navy `#0B3559`, red `#F6404C`, cream `#EBE9DF`, white/black; TR lockup.

---

## 2. Object model (the spine)

Only three core objects. Old "7 modules" become facets/views of these — not tabs.

- **Brand** (one row, Talentrupt) — grounding truth: identity, voice, pillars, proof points,
  brand kit (colors/fonts/logo), and learned patterns from the source library.
- **Campaign** — strategic container: name, goal, audience, pillar, channels, timeline, KPIs,
  strategy package. *Every asset belongs to a campaign.*
- **Asset** — generated output that always belongs to a campaign: `post | image | deck | pdf | outreach`.

Supporting objects: `Conversation`/`Message` (chat), `Opportunity` (BD), `BrandChunk` (RAG vectors),
`AgentRun` (audit), `CalendarTask` (future), `SourceFile` (ingested ZIP files).

---

## 3. Surfaces (4)

| Surface | Route | Purpose |
|---|---|---|
| **Chat** | `/` | The command line for the whole product. Streaming. Conversation history. |
| **Campaigns** | `/campaigns` | Folder list (names only) → campaign workspace with strategy + grouped assets. |
| **Studio** | `/studio` | Visual gallery of images & decks with preview/download. Can also trigger generation. |
| **Business Dev** | `/business` | Opportunity scout (scored target companies) + outreach generation. |

UI rules carried from old build that were correct:
- Campaign folder rail shows **names only** — no counts, status pills, or type summaries.
- No `Draft/Needs review/Scheduled/Published` badges until a real review/publish workflow exists.
- Buttons only exist if they trigger a real action.

---

## 4. The agent (the core upgrade)

Replace keyword intent-detection with a **tool-calling orchestrator** (Claude or OpenAI; provider-pluggable).

### Loop
1. User message + compact app context + brand grounding → orchestrator LLM.
2. LLM calls one or more **tools** (below). Each tool is a real backend action that returns a saved asset.
3. Backend streams **status events** (SSE) — friendly, user-facing ("Drafting strategy…", "Designing slides…").
4. Final assistant message reports the completed result and links the asset(s).

### Tools (backend functions exposed to the LLM)
| Tool | Effect |
|---|---|
| `search_brand_knowledge(query)` | RAG over brand chunks; returns grounding snippets. |
| `create_campaign(brief)` | Creates a Campaign + strategy package; returns campaign id. |
| `generate_posts(campaign_id, platform, count, angle)` | LinkedIn/IG/email posts → saved `post` assets. |
| `generate_image(campaign_id, concept)` | On-brand PNG via compositor (+ optional `gpt-image-1`) → `image` asset. |
| `build_deck(campaign_id, topic, slides)` | `.pptx` via python-pptx in TR deck style → `deck` asset. |
| `build_pdf(campaign_id, kind)` | Campaign report / proposal / one-pager → `pdf` asset. |
| `find_opportunities(query)` | Scored RPO target companies → `Opportunity` rows. |
| `write_outreach(opportunity_id|company, kind)` | Email/sequence/follow-up → `outreach` asset. |

Tools are also callable directly via REST so Studio/Business Dev buttons reuse the same code paths.

### Streaming protocol (SSE event types)
`status` (user-facing step text) · `token` (assistant text delta) · `asset` (saved asset payload) ·
`error` (provider/asset failure, shown honestly) · `done`.

---

## 5. Tech architecture

```
marketing-agent/
├─ frontend/                 # Next.js (App Router, TS, Tailwind, shadcn/ui)
│  ├─ app/                   # /, /campaigns, /studio, /business, /login
│  ├─ components/            # chat, asset cards, previews, brand UI
│  └─ lib/                   # api client, SSE hook, types
├─ backend/                  # FastAPI
│  ├─ app/
│  │  ├─ main.py             # routes + SSE
│  │  ├─ agent/              # orchestrator, tool registry, prompts
│  │  ├─ generation/        # posts, images (compositor), decks, pdf
│  │  ├─ knowledge/         # ZIP ingest, vision/OCR, chunking, embeddings
│  │  ├─ brand/             # brand_kit.py (colors/fonts/logo source of truth)
│  │  ├─ models.py          # SQLAlchemy
│  │  ├─ schemas.py         # Pydantic
│  │  ├─ db.py / config.py  # engine/session, env config
│  │  └─ providers/         # llm + image provider adapters (OpenAI/Claude/Ollama)
│  └─ requirements.txt
├─ storage/                  # generated assets (dev) — images/decks/pdfs (gitignored)
└─ BUILD_PLAN.md             # this file
```

- **DB**: PostgreSQL + **pgvector** (intended). SQLite dev fallback **without** vector search (RAG degrades to keyword) so the app still boots with no Postgres.
- **Streaming**: SSE endpoint `POST /api/chat/stream`.
- **Auth**: simple admin login (token) for v1, matching current usage. Pluggable later.
- **Secrets**: only in `backend/.env` (gitignored). Never in frontend or tracked docs.
- **Config**: `LLM_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `IMAGE_PROVIDER`, `DATABASE_URL`, etc.

---

## 6. Data model (Postgres)

```
brands(id, name, tagline, voice, pillars[], proof_points[], brand_kit jsonb, created_at)
conversations(id, title, created_at)
messages(id, conversation_id, role, content, assets jsonb, created_at)
campaigns(id, name, goal, audience, pillar, channels[], timeline, kpis jsonb,
          strategy jsonb, status, created_at)
assets(id, campaign_id, type, title, body jsonb, file_path, file_url, meta jsonb, created_at)
opportunities(id, company, segment, fit_score, signal, pain_point, service,
              suggested_campaign, why jsonb, status, created_at)
brand_chunks(id, source_file_id, kind, text, embedding vector, meta jsonb)   # pgvector
source_files(id, path, folder, file_type, analysis jsonb, created_at)
agent_runs(id, conversation_id, input, tools_called jsonb, output, created_at)
calendar_tasks(id, campaign_id, kind, due_at, payload jsonb, created_at)      # phase 5
```

---

## 7. Brand grounding / RAG

1. **Brand kit** (`brand/brand_kit.py`) — colors, fonts, logo paths, visual rules. Source of truth
   for the image compositor + deck builder. Hand-curated, not learned.
2. **Source library ingest** (`knowledge/`) — read the 115-file TR ZIP:
   - PDFs → text extraction + page render → chunks.
   - Images → **vision model** caption/layout/color/copy extraction → chunks.
   - Each chunk embedded → `brand_chunks` (pgvector).
3. **Retrieval** — `search_brand_knowledge` does vector search (or keyword fallback on SQLite) and
   feeds snippets into generation so output reflects *real* Talentrupt patterns, not just templates.

This closes the gap the old build explicitly never closed (no OCR/vision).

---

## 8. Generation subsystems

- **Posts** — LLM with brand grounding; structured output: platform, content type, hook, caption,
  CTA, hashtags, visual concept. Saved as `post` assets under the campaign.
- **Images** — deterministic **brand compositor** (Pillow) for consistent TR-branded graphics
  (red rail, cream cards, navy panels, numbered markers, count-aware recruiter layouts) +
  optional `gpt-image-1` for non-template artwork. Never fake success; if provider down, say so
  and save the visual direction.
- **Decks** — `python-pptx` in TR deck style (white/cream cover, red content rail, navy/cream split
  panels, numbered red markers, modular insight cards). Titles inferred professionally, never raw prompt.
  Versioned revisions saved as new files.
- **PDF** — campaign report / proposal / one-pager via reportlab or WeasyPrint, TR-themed.

---

## 9. Phased roadmap

**Phase 1 — Foundation**
Scaffold Next.js + FastAPI; Postgres+pgvector (SQLite fallback); Brand object + brand kit seeded
for Talentrupt; admin login; streaming chat shell (echo agent); asset storage; health checks.
*Done = log in, chat streams, brand kit loads, DB boots on Postgres or SQLite.*

**Phase 2 — Agent + core loop ✅ DONE (2026-06-17)**
Tool-calling orchestrator + tool registry; `create_campaign`, `generate_posts`, `generate_image`
(compositor), `build_deck`, `build_pdf`. Campaigns + Studio surfaces render real saved assets.
*Done = "Plan a healthcare RPO LinkedIn campaign with 3 posts, a hero image, and a deck" produces all four, on-brand, from one chat message.*
- Verified: acceptance prompt produced campaign + 3 posts + 1200x1200 PNG + 6-slide PPTX from one
  message. Files valid + served (correct content-types). In-browser: inline asset cards (post/image
  with download), Campaigns surface (folders → strategy + grouped assets, image loads via CORS),
  Studio gallery, markdown rendering (no literal `**`), no console errors, prod build passes.
- New backend: `generation/{common,strategy,posts,images,decks,pdf}.py`, `agent/tools.py`,
  rewritten `agent/orchestrator.py` (tool loop + deterministic fallback), `providers/llm.py`
  (`chat_with_tools`, `chat_json`). New routes: campaigns list/detail, assets list, `/api/files/...`.
- New frontend: `AssetCard`, `Markdown` (react-markdown+remark-gfm), `CampaignsView`, `StudioView`;
  `asset` SSE event handling; campaign/asset/file API client. Note: layout is desktop-first — view
  at ≥1100px width (the embedded preview surface is narrow and crops the detail column).

**Phase 3 — Brand learning ✅ DONE (2026-06-17)**
ZIP ingest pipeline (PDF + vision/OCR), embeddings, `search_brand_knowledge` wired into all generation.
*Done = generated posts/images visibly reflect retrieved TR patterns; 115 files indexed.*
- Ingested 113 files (80 images vision-captioned, 33 PDFs incl. the 600 MB magazine streamed to
  temp) → 258 embedded chunks (`text-embedding-3-small`) in `brand_chunks`. By folder: TR Posts 97,
  Magazines 10, Pitch Deck 4, Brand Kit 1, Handbook 1. Resumable (skips already-ingested by path).
- Vector store = embeddings as JSON in SQLite + Python cosine (`knowledge/retrieve.py`); swap to
  pgvector later by changing only that module. SQLite WAL enabled so ingest writes while API reads.
- `brand_context()` injected into strategy/posts/deck-outline prompts; `search_brand_knowledge`
  added as an agent tool (status: "Reviewing past Talentrupt work"). Sidebar shows
  "Brand library · N learned".
- New: `knowledge/{ingest,retrieve}.py`, models `SourceFile`+`BrandChunk`, `providers/llm.py`
  `embed()`+`vision_caption()`, routes `/api/knowledge/{status,import}`, dep `pypdf`.
- Verified: retrieval returns real TR patterns w/ good cosine scores; grounded post generation runs
  clean and the agent invokes brand search; sidebar indicator renders; no console errors.
- Known cosmetic: some PDF smart-quotes extract as `�` (encoding); harmless to retrieval. Re-run
  `python -m app.knowledge.ingest` anytime to ingest new/added source files (incremental).

**Phase 4 — Business Dev ✅ DONE (2026-06-17)**
Opportunity scout (scored targets), company detail reasoning, `write_outreach`, brief generation.
*Done = "Find IT staffing firms needing sourcers" returns scored opportunities + starter outreach.*
- LIVE web-research discovery via OpenAI search model (`gpt-4o-mini-search-preview`,
  `llm.web_search_json`) — returns REAL current companies + hiring signals (verified: Supabase
  Series F $500M/34 roles, Mercury, Deepgram…). Falls back to general-knowledge (flagged) if search
  model unavailable. Manual company intake also supported.
- 5 ICP target profiles (`business/profiles.py`): overloaded staffing, volume tech hiring,
  healthcare, high-growth/funded, IT staffing. Fit-scored, with why-now / why-fit / decision-maker
  / recommended service / pain points.
- Outreach (`business/outreach.py`): personalized email + LinkedIn + 2 follow-ups + talking points,
  grounded in brand library. Auto-advances status new→contacted and schedules follow-up
  `CalendarTask`s (day 3 + 7). Pipeline: new→contacted→replied→meeting.
- New: `business/{profiles,discover,analyze,outreach}.py`, model `CalendarTask`, routes
  `/api/business/{profiles,discover,intake}`, `/api/opportunities[/{id}[/outreach]]`, `/api/tasks`.
  Frontend `BusinessView` (composer, scored list, detail w/ outreach + pipeline + follow-ups).
- NOT YET: actually SENDING email/LinkedIn (drafts + copy only) — needs SendGrid/SMTP + LinkedIn
  integration. Reviewed-before-send; web leads should be verified.

**Phase 5 — Polish & publish prep**
Studio gallery polish, exports, AI Calendar, publishing queue + OAuth-ready provider metadata.

---

## 10. Open decisions (to resolve as we go)
- LLM provider for the orchestrator: OpenAI `gpt-5.2` vs Claude (Opus/Sonnet) — provider-pluggable so we can A/B.
- Vision model for ZIP ingest.
- Embedding model + dimension.
- Production deploy target (Vercel for FE + container for FastAPI?).
- Whether decks should also export to Google Slides later.

---

## 11. Development rule
1. Read this file. 2. Make the change. 3. Update this file with any new product/data/integration decision.

---

## 12. Business Dev relevance fix (ICP guardrails + Signal filter)
**Problem (audited live):** Discovery returned household-name mega-caps (Google 92, AWS 88, SAP 86,
Oracle, IBM, Microsoft, Salesforce) with clustered, inflated scores (84–92). Unrealistic RPO
prospects — regression after removing the Target-profile dropdown (lost ICP nuance).

**Fix:**
- `business/discover.py` — added `_ICP_GUARDRAILS` (EXCLUDE Fortune-100/mega-caps; target mid-market
  ~50–5,000 emp + overloaded staffing firms) and `_SCORE_RUBRIC` (spread 0–100; reserve 85+ for
  exceptional fits; most 45–80) into the discovery prompt (applies to web + fallback paths).
  Added `signal` to `_filters_clause`.
- `business/analyze.py` — added single-company score-realism note (mega-cap running in-house = weak fit).
- `BusinessView.tsx` — new **Buying signal** filter (⚡ icon, first of 5): Actively hiring / Hiring at
  volume / Newly funded / High-growth / Overloaded recruiting team / Lacks internal recruiters /
  Opened a new office. Search-only (not a history-list filter), passes `filters.signal` → discover.

**Verified:** tsc OK; backend import OK; live discover (Healthcare+Hiring-at-volume) → mid-market
names (HealthJoy, LHC Group, Cureatr, R1 RCM, WellSky), scores spread 65–85, 3 contacts + timing each;
IT+Overloaded → mid-market IT (Innovatech, CloudTech, DevOps Agency) spread 50–80; browser-confirmed
the Signal dropdown opens with all options.

**Note:** Old mega-cap rows (Google 92, etc.) persist in the prospect list — they were saved by
searches run BEFORE this fix (accumulation by design). New searches no longer add them.
**Known limitation:** when live web search returns nothing it falls back to `ai_suggested`, which
invents plausible exec names + LinkedIn URLs (labelled, "leads to verify"). Hardening = separate task.

---

## 13. Chat as the all-access agent + attachments + size preset + clear prospects
Five changes (request: "chat should answer every question and do every related task"):

**1) Company-size "Up to 500" preset** — `BusinessView.tsx` SIZES now supports `{label,value}`
options; added "Up to 500 — ideal for RPO" → sends clean `company_size:"1-500"` to discover
(`FilterControl` normalizes string|object options).

**2) Chat file attachments** — new `POST /api/chat/attach` (UploadFile, 25 MB cap, auth) →
`ingest.ingest_upload()` extracts text (PDF/pypdf), caption (image/vision), or decoded text, embeds
into `brand_chunks` (folder="Uploads", app-wide RAG) and returns an excerpt. Frontend: paperclip +
chips in `ChatPanel`, `attachments` state in `ChatProvider`, passed each turn via `streamChat` →
`ChatRequest.attachments` → `_stream` → `orchestrator.run(attachments=…)` injects them as primary
context (cap 5 files × 6000 chars). `config.uploads_path` stores raw files for provenance.

**3) Chat full tool access** — `CHAT_TOOL_NAMES` expanded to search_brand_knowledge +
**discover_prospects** + **analyze_company** + generate_image + build_deck + build_pdf. New executors
in `tools.py` call `business/discover` + `business/analyze` and save via the shared
`business/store.save_opportunity` (extracted from main.py to avoid a circular import). Rewrote
`CHAT_GUIDANCE` so Chat finds/analyzes prospects, generates visuals/decks/PDFs, AND answers product/
technical questions about the app. `ChatPanel` already renders `m.assets`, so chat-generated images/
decks show inline; discovery results render as markdown and persist to Business Dev.

**4) Clear prospects** — new `DELETE /api/opportunities` (clears all opps + their follow-up tasks);
`BusinessView` list header shows count + "Clear all", plus a per-row hover ✕ (score pill fades to a
delete). `deleteOpportunity` (per-row) already existed.

**Verified live:** tsc clean; backend imports clean; chat stream → discover_prospects saved prospects
to Business Dev and presented them; attachment upload extracted text + the assistant answered from the
attached brief; size dropdown shows "Up to 500 — ideal for RPO" and selecting it sets `1-500`; all 5
filters + Clear all render; no console errors.

**Note:** the `ai_suggested` fallback still fabricates exec names/LinkedIn when live web search is
empty (unchanged, labelled "leads to verify"). Same files' email/LinkedIn sending remains out of scope.

**Adversarial review hardening (2026-06-19):** ran a multi-agent review of the above; fixed all
confirmed issues except one Postgres-only DB-session note (N/A on SQLite). Fixes: attachments now
clear after each send (no more re-sending every turn — file persists in RAG); `send()` is blocked
while an upload is in flight (no silent drop) and uses an in-flight counter; `/api/chat/attach`
enforces the 25 MB cap while streaming (no full-body buffering) and rejects non-allowlisted file
types (415); uploads get a uuid-prefixed on-disk name (no same-name overwrite); same-name files are
de-duped client-side; the orchestrator no longer double-sends the current user turn; attachment text
is labelled "data, not instructions" (prompt-injection guardrail); per-row prospect delete is now
keyboard-focusable. Re-verified: tsc clean, backend imports clean, attach 200/415 correct, no console
errors.

---

## 14. Per-campaign target clients (scored) + Done→replace
Each campaign folder now shows **Target clients** — companies matched to that campaign's theme,
scored, that the salesperson can work through.

- **Model:** `CampaignProspect` (campaign_id, company, fit_score, data=normalized discover dict,
  status active|done) + `Campaign.prospects` relationship (cascade delete). New table auto-created
  by `init_db` on startup.
- **Scoping:** `_campaign_query(c)` builds the discover query from the campaign's audience/goal/
  pillar/name, so a "Healthcare RPO Awareness" campaign returns healthcare-staffing companies.
- **discover():** added an `exclude` param → "do NOT include these already-known companies" so
  refills/replacements are always fresh.
- **Endpoints:** `GET /api/campaigns/{id}/prospects` auto-fills to 6 active scored clients;
  `POST /api/campaign-prospects/{id}/done` marks one handled and returns one fresh replacement.
- **UI (`CampaignsView`):** a "Target clients" grid of `ClientCard`s (company, fit score, segment,
  hiring signal, top decision-maker + LinkedIn, timing chip) above the content calendar; each card
  has a **Done** button → shows "Replacing…" → the card is swapped for a new client, keeping 6.

**Verified live:** Healthcare campaign → 6 healthcare-staffing clients scored 70–85, 3 contacts +
timing each; Done returned a replacement and the list stayed at 6 (old one gone); browser confirmed
6 Done buttons, "Replacing…" busy state, and resolution back to 6; tsc + imports clean; no console errors.

**Deferred (user's standing list, to add later):** verified contact emails (enrichment API),
send-from-app (Gmail/LinkedIn), one-click outreach from Chat, saved searches + daily digest, and
gating/labelling the `ai_suggested` fabrication.

**Review hardening (campaign clients):** fixed all 7 confirmed findings. Backend: `_ensure_campaign_prospects`
now serializes fills per campaign (asyncio.Lock) and fills to TARGET from the *live* active count
(never over 6); a 180s cooldown stops re-running a paid web search on every open of a dry campaign;
GET caps the response to 6; Done is idempotent (repeat → no replacement, no over-fill); `_campaign_query`
leads with the audience only (drops goal/pillar/name copy) and passes `keywords=audience` so discovery
is scoped to the sector. Frontend: `CampaignClients` keyed by campaign id (remount discards stale
in-flight closures on switch) + a subtle "no fresh match" note instead of silently dropping below 6.
Re-verified live: GET=6, Done→replacement (real staffing firm), repeat Done→null (idempotent), list
stays 6, no console errors.

---

## 15. Anti-fabrication: never present a guess as a fact (layers 1–3)
The prospecting engine used to fabricate decision-maker names, fake LinkedIn `/in/` profile URLs and
guessed emails (worst on the `ai_suggested` fallback). Implemented the no-dependency prevention layers:

- **Layer 1 — sanitize contacts** (`discover.py::_norm_contacts`): every contact's LinkedIn is replaced
  with a real **people-search** link (`_people_search_url`, built from name/role + company), and the
  **email is blanked** (verified emails come later via enrichment). Applies to BOTH web_research and
  ai_suggested, and to the legacy flat decision-maker fields. analyze.py inherits it.
- **Layer 2 — tier + label** (`BusinessView`, `CampaignsView`): `ai_suggested` shows an amber
  "unverified · verify" badge (Business Dev) and a "verify" chip (campaign clients); contact links read
  "Find on LinkedIn" (a search) with a "confirm the person on LinkedIn before reaching out" note.
  `_serialize_cp` now exposes `source`.
- **Layer 3 — honest fallback** (`discover.py::discover` + `_normalize`): live web search → if empty,
  a **broadened web-search retry** → only then a **constrained general-knowledge fallback that is told
  to NEVER invent company names (real companies only, fewer/zero is fine) and to include the real
  website**, with `require_website=True` dropping any un-sourced company. If nothing qualifies →
  honest-empty `[]`. require_website is False for analyze.py so a user-named company is never dropped.

**Verified live:** discover → all contacts are people-search links, all emails blank, real company via
web research; unit: fake `/in/` URL → people-search, email "", un-sourced AI company dropped; UI shows
"Find on LinkedIn" + verify note (Business Dev) and "verify" chips (campaign clients); tsc + imports
clean; no console errors. **Note:** prospects saved BEFORE this change keep their old stored contacts
(Clear all / re-discover to refresh). **Layer 4 (enrichment API for real verified emails) still parked.**

**Review hardening (anti-fabrication):** the review caught that sanitization ran on WRITE only —
the live DB held ~250 fabricated `/in/` URLs + ~240 guessed emails served verbatim on READ. Fixed:
extracted a shared idempotent `sanitize_contacts(company, contacts)` and apply it on READ in
`serialize_opportunity` (store.py) and `_serialize_cp` (main.py), incl. the legacy flat
decision_maker fields — so legacy rows are neutralized too. Also: step-3 fallback wrapped in
try/except → honest-empty (not a 500); the broadened web retry keeps the `exclude` list (so it finds
DIFFERENT companies); corroboration comment corrected (website is a heuristic, not validation).
Skipped (low, would drop good leads): requiring a website on the web_research path. Re-verified live:
0 fabricated `/in/` links and 0 emails across all 105 opportunities (199 contacts) AND campaign
prospects; legacy prospect (Supabase) renders people-search links + no email in the UI; no console errors.

---

## 16. Real data: no fake names, grounded companies, vertical campaigns
Response to "all decision-maker names are fake; everything should be real" + "real-time campaigns per
sector (IT, Non-IT, Healthcare, Staffing)".

- **No fake names (free, done).** `sanitize_contacts` now drops AI-guessed NAMES entirely — it keeps
  only the role + a real LinkedIn people-search keyed on role+company, and blanks emails. Applied on
  write AND read, so legacy rows are neutralized too. `serialize_opportunity` sets decision_maker to
  the role (no name). UI: Business Dev "Decision-makers" + campaign ClientCards show role-only + "Find
  on LinkedIn"; note updated to "We don't show guessed names…". Verified: Vested Technology → CEO/COO/
  CTO/VP TA, zero names, zero emails.
- **Grounded companies (free, done).** Fixed the dead web-search path: added `llm.web_search_text`
  (raw search-model prose) and a two-stage `discover()` — research via the search model, then a
  `chat_json` structuring pass that extracts ONLY the companies the research actually named → tagged
  `web_research`. Replaced the two dead `web_search_json` calls. Verified: healthcare search → 4
  `web_research` companies (Vested Technology, AlediumHR, Staffbank, The Wolf Works), not ai_suggested.
- **Vertical quick-starts (#1, done).** `CampaignsView` rail has IT / Non-IT / Healthcare / Staffing
  quick-start buttons; each builds a context-grounded campaign (audience preset → drives target-client
  discovery), de-duped by name. Verified: IT → real clients Lovable, Leapfrog Technology, TechKraft,
  Nexton.

tsc + backend imports clean; no console errors. **Honest limits:** web-grounded counts can be lower
than requested (only what it can substantiate — real-but-fewer beats fake); real *named* contacts +
verified emails still require the parked **enrichment API (Layer 4)**.

---

## 17. Reliable LinkedIn links (or none) — fix the "wrong person" problem
A design panel (4 strategies + synthesis) confirmed: LinkedIn's own keyword people-search
(?keywords=<role> <company>) is NOT employer-scoped — it matches loosely across all profiles, so
"CEO Stivers" returns random people. Fix shipped:

- **Reliable X-ray instead of keyword search** (`discover.py::_linkedin_search_url`): build a Bing
  search `site:linkedin.com/in "<company>" <role>` — the company is EXACT-QUOTED, which scopes
  results to that employer (e.g. `"CCI Staffing"` only matches profiles mentioning CCI Staffing).
  Bing default (Google throws CAPTCHA/consent walls on shared office IPs). Never fabricates — opens
  a results page of real indexed profiles. Label changed to **"Search LinkedIn"** (a search verb,
  not "view profile").
- **Suppress when not reliable** (`_company_is_distinctive` + `_role_is_specific`): emit `""` (the
  existing `c.linkedin &&` guards then hide the link) when the role is generic ("Owner") OR the
  company name is a bare common word / surname / short acronym with no distinctive token ("Stivers",
  "Apex", "Smith Group"). Multi-word names whose tokens don't collide with a common-word/surname
  stoplist are kept (the exact-quoted phrase is specific). Enforced in `sanitize_contacts` on WRITE
  AND READ, so legacy rows are gated too. `sanitize_contacts`/`serialize_opportunity`/`_serialize_cp`
  now thread the company `website` (reserved for a future verified-company-page tier).

**Verified live:** Staffing campaign → Stivers SUPPRESSED (no link); GearPoint/CCI/Springborn/Impact/
Thrivas → `site:linkedin.com/in "<exact company>" CEO` Bing X-ray; browser confirms Stivers shows no
"Search LinkedIn" link while the rest do; tsc + imports clean; no console errors.

**Ceiling (future):** the only truly person-scoped link is the company's `/company/<slug>/people/?keywords=<role>`
page, which needs a VERIFIED company LinkedIn slug — not reliably obtainable from an LLM (it returns
plausible-but-not-always-right slugs) without enrichment. That's the gold tier, gated on the parked
enrichment work.

---

## 18. Company LinkedIn reference for every prospect + campaign Done-history
1) **A LinkedIn reference for every search** (reconciles with the suppress-wrong-person-links rule):
   `discover.company_linkedin_url(company)` → a LinkedIn COMPANY search (much less noisy than people
   search), added to every prospect via `serialize_opportunity` (Business Dev) and `_serialize_cp`
   (campaign clients). Shown as a "LinkedIn" link in the Business Dev detail header and a LinkedIn icon
   by the company name on each campaign ClientCard — so even prospects whose per-person search was
   suppressed (e.g. "Stivers") still have a reliable LinkedIn entry point to the company → People tab.
2) **Done-history** in Campaigns: `GET /api/campaigns/{id}/prospects?status=done` returns worked-through
   clients (newest first, no auto-fill/discovery). `CampaignClients` gained Active/History tabs; markDone
   invalidates the history cache so the newly-done client appears; `ClientCard` `onDone` is now optional —
   history cards are read-only with a "Done ✓" badge instead of the button.

**Verified live:** every staffing prospect (incl. Stivers) carries company_linkedin; Done(GearPoint) →
appears under History read-only; Business Dev detail shows the company LinkedIn link (legacy rows too);
tsc + imports clean; no console errors.

**Review hardening (history count):** the review's one finding — History count badge only updated
after opening the tab — fixed by loading history eagerly on mount + a `historyTick` that markDone
bumps to refetch. Verified: badge shows "History (1)" without opening, and bumps to "(2)" after a Done.

---

## 19. Verified results + LinkedIn searches are real (+ name-variant fix)
Live web verification of the generated prospects (staffing campaign + IT): every company checked is a
REAL, operating firm with a real website AND a real LinkedIn company page — Judge Group (judge.com),
Thrivas (thrivas.com, /company/thrivas), Springborn Staffing (springbornstaffing.com,
/company/springborn-staffing), CCI Staffing (ccistaff.com), Careerscape (cs-recruiters.com), Impact
Staffing (/company/impact-staffing), Leapfrog Technology (/company/lftechnology). Real people exist too
(e.g. Ken DeSimone — Owner/President of Springborn Staffing, linkedin.com/in/ken-desimone-cpa). So the
web_research path returns genuinely real companies.

LinkedIn links: the company reference (`company_linkedin_url`) reliably finds the real company page
(verified). The per-person Bing X-ray returns real profiles when the company name matches profile text.
Fixed a name-variant miss: `_search_phrase()` now quotes the multi-word CORE (drops trailing generic
suffixes while >=2 tokens remain) so "Judge Group Staffing" → `"Judge Group"` matches profiles that say
"The Judge Group". Verified live.

**Honest caveats (reported to user):** per-company DETAILS (hiring-signal text, fit score) are AI
assessments to verify, not confirmed facts; LinkedIn requires login; automated/bot access to Bing can
hit a CAPTCHA (a logged-in human usually doesn't); the only GUARANTEE of the exact person + verified
email remains the parked enrichment API.

---

## 20. UX batch: persistent state, light mode, previews, conversation delete, Create cleanup
1. **State survives navigation** (the big one): the four section views (Chat/Create/Campaigns/Business
   Dev) are now all kept MOUNTED in the persistent `Shell` and toggled by `usePathname` (route pages
   render `null`, just driving the URL). Previously Business Dev / Campaigns held state in route pages
   that unmounted on every navigation, losing in-progress tasks. Verified: a value typed in Business
   Dev survives navigating to Chat and back.
2. **Preview + download icons** (`AssetCard`): image and deck/PDF cards now show an eye (preview →
   opens in a new tab) + a download icon instead of a "Download" text button. (PPTX can't render
   in-browser → preview downloads it; images/PDF render.)
3. **Light mode**: `:root[data-theme="light"]` palette in globals.css (cream/white surfaces, navy
   text, same red/coral accents) + a sun/moon toggle in the sidebar, persisted in `localStorage`
   (`tr_theme`), applied pre-paint via an inline script in layout.tsx (no flash). Default dark.
4. **Create**: removed the redundant "Generate" tab — header is now just **New** (→ fresh generate
   view) + **Your past generations**.
5. **Delete chat history**: new `DELETE /api/conversations/{id}` (cascades to messages) +
   `deleteConversation` in `ChatProvider` + a hover trash button per conversation row in `ChatPanel`
   (clears the view if the open one is deleted).
6. **Campaign history verified correct**: History tab shows ONLY `status='done'` clients (disjoint
   from the active list — confirmed zero overlap), read-only with a "Done ✓" badge; tap Done → moves
   to History + a fresh client replaces it.

Verified live (logged-in preview): all six work; tsc + backend imports clean; no console errors.

---

## 21. Clickable clients → win strategy, coherent sector folders, native LinkedIn
1. **Clickable target clients → real win strategy**: each client card is now clickable → opens a
   `StrategyModal`. New `POST /api/campaign-prospects/{id}/strategy` calls `business/winstrategy.py`
   (LLM grounded in the prospect's REAL hiring signal + Talentrupt's brand_context) → returns
   {why_fit, approach, pain_points[], talking_points[], recommended_services[], first_touch}, cached
   on the row. Verified specific & grounded (e.g. Fuze Health → cites their TX HR expansion + maps
   Talentrupt services to their pains; first-touch references the real roles).
2. **Coherent sector per folder**: `_campaign_industry(campaign)` detects the dominant sector
   (Healthcare / Staffing / IT / Finance / Corporate) from name+audience+pillar+goal and passes it as
   a hard `filters.industry` to discovery, so a folder's clients are one clean sector instead of a mix.
   Verified: "Data-Driven Hiring Awareness" → all Healthcare (was a healthcare+tech+staffing mix).
   One-time: cleared the 38 cached active prospects so every folder re-discovers cleanly on next open.
3. **Native LinkedIn link**: per-contact "Search LinkedIn" now points to LinkedIn's OWN people search
   (`linkedin.com/search/results/people/?keywords="<company core>" <role>`) instead of a Bing X-ray —
   lands the rep directly on LinkedIn. (Truly-direct single profiles still require enrichment.)
- Fixed a dev hydration warning from the theme script (`suppressHydrationWarning` on `<html>`).

Verified live: tsc + imports clean; strategy modal renders all sections; clients coherent; LinkedIn
native; no console errors.

---

## 22. Varied decision-maker titles, follow-up de-stale, ★ Save / Shortlist
1. **Decision-maker titles vary per company** (#1): `_FIELDS` no longer forces the identical
   CEO/COO/CFO/VP-Talent-Acquisition template — it now asks for the 3-5 real decision-makers that
   fit THIS company with titles tailored & varied to its size (Director vs VP vs Senior Manager of
   TA, Founder/CEO, etc.). Verified: fresh discovery returns varied role mixes per company.
2. **Follow-ups no longer go stale** (#2): the "Follow up with Supabase" under On Target Staffing was
   stale client state (calendar_tasks was empty; SQLite reused row-id 1 after the old list was
   cleared). Fixed: `delete_opportunity` now cascade-deletes the prospect's CalendarTasks (clear
   already did), and the frontend refreshes `tasks` after Clear / per-row delete so removed follow-ups
   don't linger.
3. **★ Save / Shortlist** (#3): `update_opportunity` accepts `{saved}` (stored in `why.saved`);
   `serialize_opportunity` exposes `saved`; **`clear_opportunities` now removes only UNSAVED**
   (saved are kept) + their tasks. Frontend: a ★ toggle on every list row + a Save button in the
   detail header, a "Saved (N)" filter toggle, and "Clear all" → "Clear" (spares saved, confirm says
   "saved ★ are kept"). `setOpportunitySaved` in api.ts; optimistic toggle in BusinessView.
   Verified live: save persists; Saved filter shows only saved; Clear deletes unsaved & keeps saved;
   the Saved count updates on ★ click. tsc + imports clean; no console errors.

---

## 23. Campaign sector coherence — only matching-sector clients per folder
**Bug:** "Engineered Hiring" (a conversational campaign) showed a healthcare+staffing MIX. Root
cause (from live DB): the conversational planner templated the SAME generic persona audience
("HR professionals and hiring managers in healthcare and other industries") onto every
conversational campaign — healthcare-leaning AND cross-sector. Quick-starts were already clean.

**Fix (layered, after an adversarial review workflow caught real starvation/purity bugs):**
- **LLM sector classification** — `discover._FIELDS` now asks for a per-company `sector` (one of 5
  canonical labels); `_norm_sector` snaps it; `_normalize` carries it through (was being dropped by
  the field whitelist — the key bug). `_serialize_cp` exposes it; CampaignProspect type gains `sector?`.
- **Exact purity gate** — `_segment_ok_for_sector(item, sector)`: keep ONLY when the LLM `sector`
  matches the campaign sector; fall back to word-boundary segment-keyword matching for legacy rows
  (regex `\b…\b` kills false positives like "bank" in "Riverbank", "hospital" in "Hospitality").
- **Authoritative campaign sector** — stored in `strategy["sector"]`; quick-starts pass it
  explicitly (VERTICALS gain `sector`; planCampaign + plan endpoint thread it); conversational
  `interpret_intent` now picks ONE sector + a sector-specific (non-generic) audience and returns it;
  invalid sectors are popped, never persisted.
- **Anti-starvation** (review findings): cooldown is armed AFTER the fill based on outcome (full
  180s only on a DRY pass; 20s after a PARTIAL fill) instead of before — a thin pass no longer locks
  a folder for 3 min. Bounded in-call retry (`MAX_FILL_ROUNDS=3`, growing `exclude`) + larger
  over-fetch top a folder toward TARGET in one open. `_campaign_query` keeps the rich audience but
  STEERS toward "{sector} companies/employers hiring at volume" so a persona audience still finds companies.
- Module logger added; off-sector drops + sector-less campaigns are logged.

**Verified live:** new IT campaign → 6/6 all "IT & Software"; Staffing quick-start → 6/6 all
"Staffing & Recruiting"; "Engineered Hiring" re-filled to 3 coherent Healthcare clients (no staffing
mix). tsc + backend imports clean; no console errors.

---

## 24. Per-campaign Target Sector selector (user-controllable folder targeting)
**Problem:** "Engineered Hiring Campaign" kept showing Healthcare clients. Root cause: it's a
THEME name, not a sector, and the system inferred its sector from a stale generic persona audience
("HR professionals…healthcare and other industries") → Healthcare. Coherent, but wrong intent.

**Fix — let the user set each campaign's target sector (definitive control):**
- Backend `PATCH /api/campaigns/{id}` (was rename-only) now also accepts `{sector}`: validates
  against `_KNOWN_SECTORS`, stores `strategy["sector"]`, **realigns the audience** to a clean
  company ICP for that sector (`SECTOR_DEFAULT_AUDIENCE`), drops the campaign's ACTIVE clients +
  resets the fill cooldown so it re-fills to the new sector ('done' history preserved).
- `_campaign_detail` now returns `resolved_sector` (= `_campaign_industry(c)`) — the sector actually
  driving discovery, so the UI shows the truth even when only inferred.
- Frontend: a **"Target sector" dropdown** in the campaign header (5 canonical sectors). Changing it
  → `setCampaignSector` → reload detail → `CampaignClients` is keyed by `${id}:${sector}` so it
  remounts and re-fetches the re-filled clients. `setCampaignSector` added to api.ts; `resolved_sector`
  added to the CampaignDetail type.

**Verified live (API + browser):** re-targeting "Engineered Hiring" → IT & Software re-filled it to
5 IT/software clients (WeblineIndia, OfferZen, Zibtek, ALLPS, Cafeto); changing the dropdown in the
UI to "Staffing & Recruiting" re-filled to 5 staffing firms (RPC Company, Stivers, Anderson, Accurate,
Idea Recruitment); set back to IT & Software. tsc + imports clean, no console errors.

---

## 25. Chat-section fixes — USA default, robust failure handling, all-access tools
Audited the Chat section with an adversarial bug-hunt (18 confirmed bugs); implemented P1+P2+P3.

**P1 — USA is the default location app-wide (+ drop non-US):**
- `settings.default_location = "United States"`.
- `discover()` defaults `location` to the US when unset, computes `us_only`, and a nested `_finalize`
  drops items whose `country` is clearly non-US (keeps US + ambiguous). New `country` field in
  `_FIELDS` + `_norm_country`; helpers `_is_us_location` / `_country_is_us_or_unknown`. All three
  discover callers (chat tool, /api/business/discover, campaign fill) inherit it.
- `analyze.py` + system prompt (`prompts.py`) state the US-market default.
- Verified live: the IT query that used to surface offshore firms (WeblineIndia/OfferZen/Cafeto) now
  returns 0 non-US (all `country="United States"`).

**P2 — robust failure handling (was: errors saved blank / chat could wedge forever):**
- `_stream` event_gen now tracks `err_text`/`interrupted`, handles the `error` event, catches
  disconnect (GeneratorExit/CancelledError) + unhandled exceptions, and persists a TRUTHFUL terminal
  assistant message (answer, else error, else interrupted note) — never a blank bubble or orphaned turn.
- Frontend `send()` wrapped in try/catch/finally (recovers busy/pending on transport failure);
  `streamChat` guards the fetch + read loop and routes failures through `onError`.
- Orchestrator history: drop the current turn FIRST then keep 10 priors (was 9); skip blank turns.

**P3 — chat is truly all-access:** added `create_campaign` + `generate_posts` to `CHAT_TOOL_NAMES`.

**Bonus (grounding fidelity):** `retrieve.search`/`image_references` now exclude folder="Uploads",
so a user's one-off chat attachment no longer pollutes Talentrupt's brand voice/style on future chats.

Verified: chat streams grounded replies; tsc + backend imports clean. (Deferred, lower severity:
AbortController for mid-stream conversation switches; MAX_STEPS canned message; clear-only-sent attachments.)

---

## 26. UI: left sidebar → top nav bar (status chips removed)
UI-only change in `Shell.tsx` (no flow/behavior affected):
- The four sections (Chat / Create / Campaigns / Business Dev) moved from the left sidebar into a
  horizontal **top nav bar**: brand on the left, nav items next, theme toggle + Admin/sign-out on the right.
- Removed the **"AI online · openai"** and **"Brand library · N learned"** status chips (no user value);
  also dropped the now-unused `getKnowledgeStatus` fetch + `knowledge`/`health` state. (The chat
  empty-state still mentions "search our brand library" — that's capability copy, not the chip.)
- Active-section highlight = navy-gradient pill (replaces the old left red bar). Layout switched from
  horizontal [sidebar|main] to vertical [header/main]; the four views stay always-mounted (state
  persistence) exactly as before.
- Verified: nav routes + active state + view switching + theme toggle + sign-out all work; both chips
  gone; no sidebar; tsc clean.

---

## 27. Chat read-access — answer "what's saved" questions, not just find new
Gap: chat had only WRITE/generate tools (discover/analyze/create/generate), so "list all the
generated companies", "what campaigns do I have", "what have I created" were honestly refused —
contradicting the all-access promise. Fix: added three READ tools (`backend/app/agent/tools.py`),
registered in CHAT_TOOL_NAMES + schemas + STATUS_LABELS, with a new CHAT_GUIDANCE bullet so the
model uses them instead of deflecting:
- `list_prospects(status?, saved_only?, query?, limit?)` → reads the Opportunity table (saved
  Business-Dev companies); shows company, fit, segment, status, ★saved.
- `list_campaigns(name?)` → reads Campaigns (planning) + active target-client counts + sector;
  pass `name` to list one campaign's clients.
- `list_assets(type?, limit?)` → reads generated Assets (image/deck/pdf/post).
All read-only (no mutations). Verified live: the exact failing question now lists the saved
companies; "what campaigns do I have" lists campaigns + counts + sectors; "what have I generated"
lists assets. No deflection. Imports clean. Chat is now genuinely all-access: find/analyze + create
+ search brand library + REPORT on everything already saved.

---

## 28. Business Dev list — newest-generated prospects on top
Was sorted by fit_score only, so a freshly found company landed wherever its score fit. Now ordered
**newest-first** (just-generated clients on top), with fit_score the tiebreaker — display-only:
- Backend `list_opportunities` → `order_by(created_at desc, fit_score desc, id desc)`.
- Frontend `mergeById` → sort by `created_at` desc, then fit, then id (mirrors the backend so a
  Find keeps new ones on top without a reload).
No flow change: selection/save/Done/delete/filter all key off ids. Verified: API returns strictly
newest-first (18 rows); after reload the top row is the most recently generated prospect (SimiTree,
fit 70) above higher-fit older ones; clicking still opens the detail. tsc clean.

---

## 29. Delete option in campaign Done-history
Added a per-item delete to the campaign History tab (the "Done ✓" clients):
- Backend: `DELETE /api/campaign-prospects/{id}` removes one CampaignProspect row. It never
  auto-refills (fill counts only ACTIVE), so deleting a done item has no side effect on active clients.
- Frontend: `ClientCard` gained an optional `onDelete` → a small trash button shown next to the
  "Done ✓" chip (history cards only; active cards keep the Done button). `CampaignClients.removeHistory`
  confirms, optimistically drops the card, calls `deleteCampaignProspect`, and re-syncs on failure.
  `deleteCampaignProspect` added to api.ts.
- Verified live: deleting a history item dropped History (2)→(1), persisted on the backend, and left
  the campaign's 6 active clients untouched. tsc + imports clean. Active Done button + replace flow
  unchanged.

---

## 30. Business Dev — merged Find/Analyze into one search bar (UX)
The two separate panels (FIND PROSPECTS + ANALYZE A COMPANY) are now ONE search bar:
- A single input (+ the filter chips) with two actions: **Find prospects** (primary — uses the text
  as focus + filters → scored list) and **Analyze** (secondary — treats the text as one company
  name/website → single fit/decision-maker/timing read). A one-line helper explains the two.
- Dropped the duplicate `company` state; `analyze()` now reads the shared `query`. Both buttons key
  off the same input. `find()`/`analyze()` call the same backends as before — no flow change.
- Verified: one composer input (was two), both buttons present, old Analyze card gone; Analyze is
  disabled until text is entered, Find always enabled; tsc clean.

---

## 31. Campaign delete removed · Business Dev sort · campaign-history Revoke
1. **Removed the campaign delete button** ([CampaignsView.tsx](frontend/components/CampaignsView.tsx)) — the
   trash icon in the campaign detail header is gone (with its `onDelete` handler + `deleteCampaign`
   import), so the main campaign folders can't be deleted from the UI. (Backend DELETE endpoint left
   intact, just no UI affordance.)
2. **Sort option in Business Dev prospects** ([BusinessView.tsx](frontend/components/BusinessView.tsx)) —
   a `sortBy` state + a "Sort" dropdown in the list header: Newest first (default) / Top fit /
   Company A–Z / Saved first. Sorting is applied in the `filteredOpps` memo; selection/save/done/filter
   are unaffected (they key off id).
3. **Revoke in campaign history** — new `POST /api/campaign-prospects/{id}/revoke` (sets status
   active, no fill so it never drops the replacement) + `revokeCampaignProspect` in api.ts + a
   "Revoke" button on history cards (alongside Done ✓ / delete) that moves the client back to Active
   (optimistic, re-syncs on failure).
Verified live: no delete button on campaign detail; sort reorders correctly (A–Z→Boulevard, Top
fit→85); Revoke moves History (1)→0 and adds the client to Active. tsc + backend imports clean, no
console errors. Existing flows (Done/replace, history delete, sector re-target) untouched.

---

## 32. Bug fixes from the goal audit (working flows preserved)
Fixed the verified gaps; no existing flow changed (live: 31 opps, 6 campaigns, 63 assets, 0 orphans).
1. **Saved-flag wipe (HIGH) + country persistence** — `save_opportunity` now carries forward
   `why["saved"]` on re-upsert (a re-discovered ★ company keeps its star + survives "clear unsaved")
   and persists `why["country"]`; `serialize_opportunity` exposes `country`. ([store.py](backend/app/business/store.py))
2. **Sector + country classification** — tightened `discover._FIELDS`: SaaS/software→IT, fintech→Finance,
   "Corporate / Non-IT" = ONLY non-tech/finance/health/staffing employers; honest non-US HQ. (prevents
   the tech/fintech-in-Corporate mix + USA mis-tagging going forward). ([discover.py](backend/app/business/discover.py))
3. **Campaign-delete orphans** — added `Campaign.items` cascade=all,delete-orphan ([models.py](backend/app/models.py));
   cleaned the 36 pre-existing orphan `campaign_items`.
4. **Asset file orphan** — `delete_asset` now unlinks the on-disk file (guarded) before the row. ([main.py](backend/app/main.py))
5. **Repeat-search de-dup** — `business_discover` passes `exclude=known` so a re-run surfaces different firms.
6. **401 handling** — `ApiError(status)` + `getBrand` throws it; `AuthGate.loadContext` bounces to Login
   ONLY on a confirmed 401 (transient errors keep the shell). ([api.ts](frontend/lib/api.ts), [AuthGate.tsx](frontend/components/AuthGate.tsx))
7. **Cosine dim guard** — `_cosine` returns 0 on length mismatch. ([retrieve.py](backend/app/knowledge/retrieve.py))
8. **Ingest poison filter** — `_is_failure_sentinel`; `_chunk` + caption builds skip "[vision failed]/[pdf
   extract failed]" so they never embed into the brand corpus. ([ingest.py](backend/app/knowledge/ingest.py))
Unit-verified: saved preserved on re-upsert ✓, country persisted+served ✓, cascade deletes items ✓,
cosine guard ✓, sentinel/chunk ✓; tsc + backend imports clean; live regression clean.

---

## 33. Second bug-fix pass (remaining open bugs; working flows preserved)
Fixed the verified still-open bugs from the deep hunts. Each unit/isolation/live-verified; tsc + imports clean; no console errors; live regression intact.
**LLM-output crash guards:** posts.py filters non-dict items; decks._normalize tolerates a non-dict
slide; analyze.py unwraps a single-element array (keeps web-grounding); export join coerces with str().
**Concurrency/robustness:** `_ensure_campaign_prospects` re-validates the campaign sector AFTER the
slow discover await and aborts (rollback) if it changed mid-fill — closes the sector-retarget race
without making the PATCH wait on the fill lock (isolation-tested: commits normally, only aborts on a
real sector change). run_ingest releases the large ZIP handle right after its last read (full
exception-path try/finally deferred as too risky to refactor safely).
**Frontend:** ChatProvider now uses an AbortController + a generation id — switching/opening/deleting
a conversation mid-stream aborts it and makes stale callbacks no-op (no cross-conversation token
bleed); BusinessView `find()` has a re-entry guard (Enter no longer fires concurrent searches);
AssetCard download buttons use a fetch→blob save (cross-origin `<a download>` was ignored) — verified
40 buttons / 0 leftover anchors; the "Open campaign →" deep-link (`?open=`) is wired via useSearchParams
(verified opens the campaign); 401 bounce already added last pass.
**Lows:** fit_score recovers a number from "85%"/"85/100" (regex); `_norm_timing` derives reach_now
from the final label (never disagree); the `done` endpoint returns ALL replacements (UI no longer
under-renders); markDone note clears on tab switch; delete_campaign drops its cooldown/lock state.
**Deferred (low/cosmetic):** MAX_STEPS canned message, per-handler error toasts, Create multi-asset,
gpt-image "simplified render" badge, full run_ingest try/finally. (The 2 non-US rows were already deleted.)

---

## 34. Deck/PDF generation quality (LLM-written content; Create/Chat flow unchanged)
Audit found PPTX/PDF output "too basic + same info every time." Root causes: PDFs did ZERO
LLM generation (static template fill) and from Create/Chat were called with campaign=None + only
`kind`, so every PDF was the same generic stub (the user's prompt was discarded); decks injected
ALL 5 proof points + 8 pillars every time → repeated boilerplate slides, and were shallow (one-line
bullets, no notes). Brand data itself is rich (8 pillars, 5 real proof points, 9 services, 225 chunks).

**P0 — PDFs now LLM-written & topic-specific.** `pdf.generate_pdf_outline(brand, topic, kind)` (async)
asks the model for a tailored `{title, subtitle, sections:[{heading, body, bullets}]}` grounded in
brand_context + only the relevant proof points; `build_pdf(...)` stays SYNC and renders from the passed
`outline` (so the campaign-milestone call site in main.py is untouched — no `await` added there). The
async outline call happens in the already-async `exec_build_pdf`. Added `topic` (required) to the
build_pdf tool schema so the agent passes the user's request; the no-provider orchestrator fallback now
forwards `topic` + derives `kind`. All dynamic text XML-escaped (`_esc`) and empty sections skipped.
Verified end-to-end: "one-pager about reducing nurse turnover" → ai_written PDF titled to the topic, 5
tailored sections. Template path still builds (ai_written:false).

**P1 — Decks: less boilerplate, more depth.** `_outline` prompt is now topic-centric (explicitly
discourages the generic "Why choose us / Proven track record / Our services" template), cites at most
one or two directly-relevant proof points (not all five), asks for substantive benefit-driven bullets,
and emits per-slide `notes`. Outline temperature bumped to 0.85 so repeat requests on a topic diverge.
Speaker notes rendered into `slide.notes_slide` (verified 5/6 slides). Renderers/layouts unchanged.

**Flow unchanged:** same Create/Chat routing + endpoints + tools; only tool inputs + content quality
improved. No frontend changes (PDF inline-preview + deck slide-preview from §prior still apply).

---

## 35. Create: "Your past generations" now reflects an in-flight task live
The generation already kept running in the background when switching to the "Your past generations"
tab (the task runs in the create provider; the Shell keeps all views mounted; the tab is local state —
only the "New" button aborts). But `PastGenerations` fetched assets ONCE on mount, so a finishing task
never appeared there and there was no running indicator — it looked like the task had stopped / needed a
refresh. Fix (CreateView.tsx, gallery view only — generation/stream flow untouched): PastGenerations now
reads `busy`/`status` from `useCreate()`, shows a live "Designing presentation slides… it'll appear here
when ready" banner while a task runs, and re-fetches `getAssets()` the moment `busy` flips true→false so
the new asset appears automatically — no manual refresh. Verified live: submit deck → switch to past tab
→ banner shows during generation → on completion banner clears and the new "Pitch Deck for Staffing
Agencies" appears at the top without remount/refresh. tsc clean, no console errors.

---

## 36. Create: conversation history + non-destructive return (Create/Chat flow unchanged)
The Create conversation already persisted in memory across nav (providers wrap the Shell), and create
conversations were persisted server-side (kind="create", 29 in DB with message+asset snapshots) — but
the Create UI never surfaced them, and the ONLY way back from "Your past generations" was the "New"
button, which calls newChat() and wiped the conversation. So peeking at past generations and returning
lost your convo + image. Fix (CreateView.tsx, UI only — generation/streaming untouched): mirrored the
Chat sidebar pattern. Added a left "History" rail listing past Create sessions (reuses the provider's
`conversations`/`openConversation`/`deleteConversation`) — clicking one reopens its conversation AND the
asset it produced. Header is now a non-destructive toggle: "Generate" (returns to the conversation
WITHOUT clearing) | "Your past generations" (asset gallery). "New" is a separate explicit reset (sidebar
+ mobile header). Verified live: open a history session → switch to past generations → back to Generate
→ conversation + asset fully preserved; History shows 29 sessions; New clears to the empty state.
tsc clean, no console errors.

---

## 37. Audit fix-batch (post multi-agent audit; no working-flow changes)
Fixed the verified findings from the bug audit. All unit/tsc-verified; backend restarted; happy path re-checked (busy clears, no console errors).
- **[Med] ChatProvider send() `finally` now generation-guarded** — wrapped the cleanup (setStatus/setBusy/setAttachments/refresh) in `if (live())`, so switching/opening a conversation mid-stream no longer lets the aborted turn's finally clobber the new view (wipe staged files / flip busy). Verified the happy path still clears busy on normal completion.
- **[Low-Med] Deck metric no longer truncated** — `_metric_parts` keeps the full number (was `[:8]`, which corrupted "$1,250,000"); `_metric_size` shrinks 130→104→80→60→44pt by length so long numbers fit without overflow. Verified: "$1,250,000" intact + zero slide overflow.
- **[Low] Enter no longer discards a typed prompt while busy** — `submit()` early-returns when busy (CreateView) / busy||attaching (ChatPanel) instead of no-op-sending and clearing the textarea.
- **[Low] Image fallback metric auto-fits** — `images._render_metric` extracts the short number + shrinks font to the 320px column (was fixed 104pt, could overflow/collide with the label). Only the deterministic compositor path.
- **[Low] `preview_deck` no longer leaks raw exception text** — generic 500 detail; real error logged server-side.
- **[Low] File path check tightened** — `serve_file`/`preview_deck` now require `target.parent == base` (was `base not in target.parents`, which allowed nested subpaths). Flat storage, so no behavior change for real files.
- **[Low] No-provider create fallback wrapped in try/except** — an image-API error in `_fallback` degrades to a friendly message instead of escaping the stream.
- **[Low/defense-in-depth] `save_opportunity` sanitizes contacts on WRITE** — blanks AI-guessed names/emails before they hit the DB (was read-side only).
**Not changed (deliberately):** USA-default keeping unknown-country firms (by design — dropping them risks over-dropping legit US firms); the pre-SSE-disconnect dangling user message (edge, risky to touch). Cleared false positives: file previews are public-by-design (images render fine); the past-generations auto-reload race (asset commits before busy→false; verified live).

---

## 38. Real Talentrupt logo embedded in every generated asset (image / deck / PDF)
No logo file existed — generators drew a text "TR TALENTRUPT" lockup / badge, and the AI-image prompt
asked the model to draw its own (unreliable) "TR monogram". Added ONE canonical logo (navy "TR" in a red
rounded-square on white, matching the brand mark) rendered once via PIL to storage/brand/tr_logo.png
(self-healing if deleted), with shared helpers in generation/common.py: `logo_path()`, `paste_logo()`,
`composite_logo_bytes()`. Embedded the SAME mark everywhere, all best-effort (text/badge fallback if the
asset can't load, so generation never breaks):
- **Images (compositor):** `_lockup` pastes the real logo tile (top-left) instead of the drawn badge.
- **Images (AI/gpt-image):** `composite_logo_bytes` stamps the logo bottom-right onto the generated PNG;
  prompt changed to tell the model NOT to draw any logo (leave bottom-right clear) — avoids a clashing mark.
- **Decks:** `_logo` adds the logo picture + "TALENTRUPT" wordmark (cover/section/metric/closing).
- **PDFs:** the logo Image is prepended to every document (both LLM and template paths).
Verified: logo renders (red border + navy TR, 600px); deck embeds 1 picture shape; PDF embeds an image
XObject; compositor image shows the logo top-left; AI-composite places it bottom-right. Visual check
confirmed the mark matches the brand. Generation flow unchanged (logo is additive). Note: orphan test
files from direct-render verification are not in the DB so never appear in the gallery.

---

## 39. Quick-start campaigns: open the existing same-sector folder instead of duplicating
A sector quick-start already deduped by exact name, but it would still create a second folder of the
same sector under a different name (e.g. two Healthcare campaigns). Now `startVertical` opens an existing
campaign when one matches — preferring the canonical quick-start name, then ANY folder already targeting
that sector. Backend `list_campaigns` now includes `sector` (`_campaign_industry(c)`) in each summary and
the `CampaignSummary` type gained `sector?`. Custom "New campaign" flow is unchanged (intentional/freeform
campaigns still allowed). Verified live: clicking the Healthcare quick-start opened the existing Healthcare
folder and the planning-campaign count stayed at 7 (no duplicate). tsc clean, no console errors.

---

## 40. Campaign delete re-added (folder rail, with confirm + cascade)
Section 31 had removed the campaign delete UI (backend DELETE endpoint left intact). User asked for it
back. Added a hover trash button to each folder in the Campaigns rail (mirrors the Chat/Create history
pattern): `removeCampaign(id)` confirms, calls `deleteCampaign` (already in api.ts), clears the selection
if the deleted folder was open, and reloads the rail. Backend `DELETE /api/campaigns/{id}` cascades to
prospects/assets/items via ORM delete-orphan and clears fill cooldown/lock state. Verified end-to-end on a
throwaway campaign (with a child prospect + asset): UI delete → removed from rail → campaign + both
children gone from DB, zero leftovers. tsc clean, no console errors. The custom "New campaign" + quick-start
flows are unchanged.

---

## 41. High-ROI add-ons (additive; plan shiny-waddling-salamander) — Phases 0–3 shipped
All additive (new JSON fields in `why`/`payload`/`meta` — no migration; new endpoints/views only; existing
flows untouched). Each phase verified: backend import + curl, frontend tsc + live preview, then a 6-view
regression with zero console errors. Backend restarted; durable servers up.

**Phase 0 — foundations:** `config.py` enrichment settings + `enrichment_available()`; new
`business/enrich.py` (no-op until keyed; Apollo/Hunter adapters); `store.save_opportunity` carries forward
`why["outreach_log"]` + `why["verified_contacts"]`; `serialize_task` adds payload+created_at.

**Phase 1 — Business Dev:** outreach TRACKING (POST /api/opportunities/{id}/track → `why.outreach_log`
sent/replied/meeting + history; advances status forward only; TrackingCard in OppDetail). Tasks inbox =
new top-nav **Tasks** view + PATCH /api/tasks/{id} (done/snooze) + per-prospect follow-up Complete/Snooze.
Enrichment seam: POST /api/opportunities/{id}/enrich → `why.verified_contacts` (NEVER `contacts`); health
`enrichment_ready`; verified-contacts UI shown only when configured. Targeting: role normalization +
phrase-quoted multi-word roles in discover.py (suppression contract preserved). CSV export
(GET /api/opportunities/export) + bulk actions (POST /api/opportunities/bulk + multi-select UI).

**Phase 2 — Create:** regenerate/refine = new `generation/refine.py` (re-runs the stateless generator with
the instruction folded in; saves a NEW asset, lineage in meta; original kept) + POST
/api/assets/{id}/regenerate + Regenerate/Refine controls on gallery cards. Brand-library upload = POST
/api/knowledge/upload-brand-file (ingest_upload gained a defaulted `folder` param; "Brand Kit" is used for
grounding since retrieve only excludes "Uploads") + a "Brand kit" tab in CreateView. NO generator
signature changes.

**Phase 3 — Analytics & Campaigns:** read-only GET /api/analytics/summary + new top-nav **Analytics** view
(CSS bars, no chart lib). Content calendar = PATCH /api/campaign-items/{id} (reschedule/status; generate
untouched) + a "Content calendar" tab in the campaign detail. Campaign-client CSV (GET
/api/campaigns/{id}/prospects/export — read-only, no fill). Soft archive = additive `status` branch in
PATCH /api/campaigns/{id} + rail Archive button (drops from planning, recoverable).

**Deferred (seams left in place):** email/LinkedIn sending; committing to an enrichment provider; multi-user
auth; social auto-publishing; background schedulers/monitoring; CRM sync; chart library; campaign merge.
