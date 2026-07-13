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
— see `components/MyraLogo.tsx` for the M mark and `app/icon.png` for the favicon). This is product chrome
only: the **content** the app produces is still Talentrupt's (brand grounding, "Promote Talentrupt",
"Why Talentrupt fits") — those references are intentional and stay.

## 2. Stack & architecture
- **Frontend:** Next.js 16 (React 19), Tailwind v4. Built as a **static export** (`output: 'export'` →
  `frontend/out`). Client-side SPA; talks to the backend over `/api`.
- **Theme:** light is the default (`data-theme="light"`; dark still toggleable). Left navigation/history
  rails are a deep-navy panel via the `.rail` class in `app/globals.css` (it re-scopes theme tokens locally
  so rail utilities read light-on-navy). The Myra mark (`MyraLogo.tsx`) is the official
  pink→purple "M" (network nodes + sparkle), extracted from the brand sheet to a transparent PNG
  (`public/myra-mark.png`) so it floats on any surface; `MyraLockup` adds the "Myra" wordmark + tagline on the
  login screen, and the favicon/app-icon is the navy tile. Chat replies use a shared reply chrome — `MyraAvatar`
  beside each assistant message, `ReplyActions` (copy / 👍👎 / download / regenerate) under it, and
  `RefineChips` (one-tap image tweaks) under an image reply in Chat/Create. A user (input) message renders via
  the shared `UserMessage` component (used in Chat/Create + the campaign chat): attachments + navy bubble +
  user-initials `Avatar`, with hover actions **Copy** and **Edit** — editing turns the bubble into an inline
  textarea and, on save, drops that turn + everything after it from the transcript AND the persisted history
  (`editMessage` → `POST /api/conversations/{id}/truncate {drop}`, counted from the back) before re-sending, so
  the corrected prompt re-runs ChatGPT-style with no duplicate.
- **Backend:** FastAPI + SQLAlchemy 2 + SQLite (WAL). Pydantic-settings reads `backend/.env`.
- **AI:** OpenAI — `gpt-4o-mini` (text), `gpt-image-2` (the MAIN featured/user-facing image; auto-falls back to `gpt-image-1` if the key lacks access), `gpt-image-1` (small/auxiliary images — the split-poster panel graphic, deck cover art, and all identity/style EDITS, since the edit endpoint is a gpt-image-1 capability), `text-embedding-3-small` (RAG). `llm.generate_image_bytes(..., model=…)` routes per call.
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
| **Chat** | The single all-access section: chat + Q&A + prospecting AND image/deck/PDF **generation** (all via tools; streams via SSE). A top toggle **Chat / Your generations** opens the gallery of everything created (filters + regenerate/refine/delete; skeleton loaders, styled Confirm/Prompt dialogs via `components/Dialog.tsx`, and app-wide toasts via `components/Toast.tsx` — no native `confirm`/`prompt`). The header shows a read-only **AI status pill** (`components/AiStatus.tsx` → `/api/health/llm`): 🟢 ready / 🟠 paused — add credits. (Create was merged in; `/create` redirects here. Brand-kit UI removed — brand is backend-only.) **Chat POSTS use a dedicated Talentrupt house-style engine** (`generation/chatpost.py`, scoped to Chat only — `campaign_id is None`): the APP draws every text/brand element crisply (wordmark, bold headline with ONE coral-red keyword, kicker pill, navy/red stat cards, red-circle website footer, corner accents) over a brand base or a gpt-image-2 themed scene (observance/holiday posts) — reproducing Talentrupt's own post design language. Templates: `statement`, `stat`, `hero` (a real person composited AS-IS on the right), `observance`, and **`mission`** (Talentrupt's "Man on a Mission" spotlight — used when a person request mentions "mission"). Never invents a face; never fabricates a statistic. Campaign & Magazine keep their own renderers untouched. | all |
| **Campaigns** | **Internal** (promote Talentrupt: chat-driven content folder grounded in a brief) + **External** (client-targeting: sector → prospects → dated content calendar). A generation started in a campaign **keeps running if you switch away** — the SSE turn runs detached and the backend persists the asset; a module-level `_generatingCampaigns` flag + a resume-poll on return surface the result. | all |
| **Magazine** | Generate a branded, festive **multi-page magazine PDF** ("Talentrupt Times") from the team's REAL photos + stats. Two modes: **From data file** (default) — upload a **CSV/`.xlsx` roster**; `generation/roster.py` reads the whole workbook (`parse_workbook`, every sheet) and auto-detects the format: (a) a curated **AWARD REPORT** workbook (an awards-leaderboard tab laid out in side-by-side blocks — Margin Champions / Placements Powerhouse / Efficiency Star / Category Champions LI·Non-Tech·Tech — PLUS a raw "Deal sheet" of one row per placement) → `build_award_issue` reads each podium verbatim and aggregates the deals by Recruiter (placements=count, margin=sum(Spread), avg=margin/placements) to enrich the cover champion + per-person stat pages; or (b) a simple one-row-per-person table → `build_issue` fuzzy-detects Name/Office/metric columns and ranks (composite or `rank_by`). Each featured name is matched to a Folders photo, looked up once via a per-name cache (`POST /api/magazine/from-data`, returns `format`, matched/unmatched, and the detected `awards`). **Manual** — an issue form + cover champion + spotlights (`POST /api/magazine/generate`). Both feed `generation/magazine.py`, which renders each page as a full PIL image and assembles one PDF (cover = framed real-photo portrait + stat pills; editorial = LLM note; **award podiums = a full page per headline award with gold/silver/bronze medallions + real photos, and one combined 3-column category page**; spotlights = 2/page circular photo + chips + blurb, or initials if no photo; + closing). Saved as a `magazine` Asset, owner-scoped. | all |
| **Business Dev** | Find/analyze real hiring companies as prospects (incl. **vibe prospecting** — describe the ideal client in plain English → ranked real list); outreach drafts; pipeline tracking | all |
| **Folders** | **Reference photo library** of employees (name + role + **one or MORE photos** each). Add an employee with several photos at once (multi-select), or hit **"Add photos"** on any existing card to attach more later; a lightbox shows all their shots (switch/download/delete extras; the cover is deletable only by removing the employee). Multiple photos are stored in an **`employee_photos`** table (the cover stays on `Employee.photo_path`). When the person is featured, the app picks the photo that best **FITS the request** — `generation/photopick.py` vision-tags each photo once (attire / expression / setting / framing / caption, cached in `photo_analysis` / `analysis` JSON) and `_select_employee_photo` scores them by keyword + intent (a formal shot for a formal/announcement post, a casual/festive shot for a celebration, a confident pose for "on a mission"); it degrades to a random real photo when vision is unavailable. The FACE is never altered — this only chooses WHICH real photo. Endpoints: `POST /api/folders/{id}/employees` (multi-file, first = cover), `POST /api/employees/{id}/photos`, `DELETE /api/employees/{id}/photos/{photo_id}`; each employee serializes a `photos[]` + `photo_count`. Feature them in **Chat** by typing **`@`their name** → a post with their **real** photo (never an AI face). | all |
| **Tasks** | Follow-up reminders | **admin only** |
| **Analytics** | Pipeline/outreach/content rollup | **admin only** |

## 4. Accounts, roles & data isolation
- Logins (from `backend/.env`): **`Admin@talentrupt.com`** (admin) and one or more **members**
  (`nishant@talentrupt.com`, plus any in `EXTRA_MEMBER_LOGINS` = `email:password,…`). Each member login gets a
  stable, unforgeable session token derived (HMAC) from `MEMBER_TOKEN`. Role AND username are derived
  server-side from the bearer token (`/api/auth/me`).
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
  **wordmark** in a reserved margin. Employee/`@mention` posts rotate across brand **skins** (`SKINS`:
  light / cream / navy / red / photo — so it isn't navy every time) and reference **series** renderers
  (`spotlight_series` = Man-on-a-Mission with a red-box keyword + script "Featuring [Name]" + arrow;
  `welcome`; `anniversary` = "X Strong Years"; `grid` = multi-employee "One Year Strong";
  **`quote`** = an employee TESTIMONIAL that rotates across **5 distinct designs** (split photo-right /
  photo-left, full-bleed photo hero, centered portrait card, photo-band) so no two look the same — each keeps
  the saying **verbatim + auto-fit** (any length, never truncated) with a Name/Role attribution and the
  **real photo featured large**; auto-routed by `_extract_quote` when a message carries a saying/quote). The series is
  auto-detected from the message (`detect_series`) or set explicitly (`style`/`skin` args). The default
  individual post is `build_ai_scene`, which runs in **STRICT FACIAL-CONSISTENCY mode**: it treats the
  reference photo as the single source of truth for the face and adapts **only** the pose, lighting and
  surroundings. The exact wording is the canonical `STRICT_FACE_DIRECTIVE` constant (in `teampost.py`, also in
  `docs/IMAGE-GENERATION.md` + the assistant's memory) — every face-editing prompt reuses it; any new
  face-editing path must too. Priority order:
  1. **FACESWAP key (strongest, immersive):** if a `FACESWAP_API_KEY` (Replicate) is set, it makes a full AI
     scene (person genuinely IN the themed environment) and swaps the person's REAL face onto it via a hosted
     face-swap API (`generation/faceswap.py` → `_build_faceswap_banner`) — AI everything **except the face**.
  2. **Immersive AI scene (DEFAULT):** `_build_ai_portrait_banner` → `_ai_portrait_canvas` uses gpt-image-1's
     image-EDIT endpoint (`input_fidelity='high'`, quality medium) to place the SAME person INSIDE the theme —
     on the pitch, in a floodlit stadium, in a clean jersey (a ChatGPT-style result, no white background).
     `_portrait_prompt` drives the immersive scene/wardrobe; the headline is NOT fed to it (gpt-image would
     paint it as ghost text — the caption is overlaid after) and text/logos on clothing are forbidden (they
     render garbled). The face is preserved by input_fidelity (very close, but an AI regen — can drift; use a
     FACESWAP key for pixel-exact). Each generation is a fresh stochastic scene, so images vary.
  3. **Real cut-out / split-poster (FALLBACK):** if the edit is unavailable on the account (`_EDITS_DISABLED`),
     `_build_editorial_banner` composites the REAL cut-out onto a themed background, or — when the free keyer
     can't cut the person off a plain wall — a bold magazine SPLIT poster (`_bold_split_poster`: real photo
     crop beside a themed panel, side/colour/seam/accent rotate). Exact face + clothes, but the person is on
     their own background beside the theme rather than inside it.
  4. **Deterministic series template (never-broken):** any failure falls back to a deterministic template.
  **Nothing overrides:** `_ensure_clear` asserts mutually-disjoint boxes; every photo is **auto-enhanced**
  (`_enhance_photo`).
  **CAMPAIGN mode** (an asset generated inside a campaign) changes two things: (a) the campaign brief is passed
  as a `theme` down through `build_ai_scene` → `_portrait_prompt`/`_scene_prompt`, so the employee is staged in
  the campaign's world (a Football brief → on a pitch in kit). The theme = **campaign name + brief**
  (`_campaign_theme`), so a campaign named "Football Campaign" is themed even with an empty brief; and (b) the on-image name label is suppressed
  (`name=""`), per the "no names on campaign images" rule.
  **Post INTENT → eyebrow:** `_post_eyebrow(message, theme)` reads the user's words and sets the small eyebrow
  above the headline so the design reads as what it IS — an announcement/event → **"SAVE THE DATE"** (month
  named) or **"ANNOUNCEMENT"**, an achievement → **"CELEBRATING"**, a welcome → **"WELCOME TO THE TEAM"**;
  plumbed via `_build_one`/`build_ai_scene`/`_build_editorial_banner (eyebrow=…)` and drawn on all three
  editorial layouts. A role-model / campaign banner (no name) never says "In the Spotlight" — it defaults to
  "TALENTRUPT PRESENTS". **Shirt text always in-frame:** `_place_editorial_person` detects a HALF-BODY crop
  (bottom 10% of the alpha is a wide band = no feet) and renders it smaller + LIFTED (never top-bleed) so
  printed shirt text (e.g. "emerge-evolve-establish") clears the frame edge and the dark scrim; a full body
  still floor-anchors. Generic campaign scenes (`images.build_images`, via
  `exec_generate_image`) additionally get the account's real employee photos (`team_photos`): the planner flags
  each variation `has_people`, and every people-variation is rendered as a REAL employee (rotating the roster)
  in the themed scene — never a random AI face — while object/scenery/data variations stay AI-generated. In
  plain Chat/Create there's no forced theme, names stay, and scenes stay generic.
- **CHAT house-style posts (`generation/chatpost.py`, Chat-only — `campaign_id is None`):** a "generate a post"
  request in plain Chat — WITH a person or without — routes to a dedicated **Talentrupt house-style engine**
  (modelled on Talentrupt's own reference posts) instead of the campaign compositor. Per the "app draws text
  crisply" decision, the APP renders every brand element with Pillow — the wordmark (top), a bold headline
  with exactly ONE coral-red keyword, a red kicker pill, navy/red **stat cards**, a red-circle website footer,
  and sparse corner accents (a diagonal-hatch circle, a dotted grid) — over a brand base (navy/cream) or, for
  `observance`/holiday posts, a gpt-image-2 themed scene. A real person is composited AS-IS on the right
  (`hero` template). An LLM planner (`_plan`) picks one of four templates (`statement`/`stat`/`hero`/
  `observance`) and the copy; the `hero` person is placed cut-out-aware (`_hero_person`): only when the
  background is genuinely removed (`_clean_cutout` — alpha has real transparency, coverage ≤ 0.9) does the
  person float on the brand disc, sized to fit BOTH axes so the whole body stays in frame; otherwise (prod
  default — no bg-removal key, shadowed studio walls) they go into a clean rounded **framed photo panel**
  (background clipped to the shape, accent + white keyline + drop shadow) — never a jagged grey rectangle or a
  half-clipped body. A keyword fallback (`_fallback_plan` + `_HOLIDAY_RE`) covers a rate-limited/absent
  LLM without dumping the raw prompt. It **never invents a face** (the scene prompt forbids people; the person is
  the real `_cutout`) and **never fabricates a statistic** (a stat card is kept only when the LLM supplied both
  value+label; observance posts carry none). Wired at `exec_generate_image` (no-person Chat) and
  `exec_feature_employee` (the DEFAULT individual feature; an explicit style/skin/scene request or a special
  occasion series still uses `build_ai_scene`). The **`mission`** template ("Man on a Mission" spotlight) has
  **6 backdrop palettes** (`_MISSION_BGS`: navy / warm espresso / bright azure / deep maroon / teal / indigo —
  all dark so the fixed light text stays legible); the default is navy and a conversational edit swaps it (see
  refine, below) while keeping the person, layout, and text. Its question is **curated meaningful copy**
  (`_MISSION_QUESTIONS`, seeded per person + backdrop variant) — never the user's raw instruction; a
  caller subtext is used only when it's a real sentence (≥4 words, no styling/deliverable words). The
  "Featuring" role pill **auto-fits** (shrinks to show the full role; never a mid-word cut). Styling
  directives ("use a different style / new look / another version / different background") are stripped from
  copy upstream by `_clean_headline` (`_STYLE_DIRECTIVE_RE`) so they can't be printed as a headline/caption.
  **Every template gets meaningful copy even with the LLM offline:** `_meaningful_copy` is a curated bank of
  ~30 holiday greetings + 8 themed recruitment lines (headline + subline + kicker) + a strong default;
  `_is_weak_headline` flags any fragment/prompt-echo (too short, filler-only, dangling preposition — "On
  Mission", "Diwali") and `_coerce`/`_fallback_plan` replace it with themed copy, while `_good_subtext` keeps a
  supplied subline only when it's a real sentence. CAMPAIGN and MAGAZINE renderers are untouched.
  **Nothing overrides:** each layout keeps text left of the photo and the wordmark in a reserved margin,
  verified by `_ensure_clear`. Cut-outs use `cutout.remove_bg_api` (hosted, opt-in via `BG_REMOVAL_API_KEY`
  — the deploy injects it + `BG_REMOVAL_PROVIDER` from a GitHub secret into the droplet `.env`, same path as
  the OpenAI key; keeps rembg off the droplet) — background only, face untouched; unset → the framed card.
  `common.script_font` = bundled Caveat (OFL). `refine.py` — regenerate/refine an asset into a new version.
  **Conversational editing (ChatGPT-style):** in Campaign/Create, a follow-up that EDITS the current image —
  "change the background to a beach", "change the text to X", "the person doesn't fit", "make it more
  colourful" — is caught by `orchestrator._is_refinement` (INTENT-based — layout/placement feedback, plain dissatisfaction
like "not proper"/"doesn't look right", not just edit verbs) and routed to `refine.regenerate_asset` on the LAST
  asset (`_last_refinable_asset`, scoped by campaign) BEFORE the brief-intake can re-ask for a style. For a
  team image, `refine._parse_image_edit` (LLM) maps the instruction to `{op: text|background|fit|design}` and
  reuses the ORIGINAL design `variant`+`eyebrow` so ONLY the requested thing changes (text→new headline;
  background→new themed scene, person kept as-is; fit→scale/reposition via `build_ai_scene(fit=…)`;
  design→fresh variant). For a **Chat house-style post** (`style=chat_hero`), an edit instead keeps the same
  person + layout + text and **rotates the Mission backdrop palette** (`chatpost.mission_variant`): "warmer" →
  warm, "brighter" → azure, a named colour → that palette, generic "different background" → the next one; the
  variant is persisted (`bg_variant` in body/meta) so successive edits keep changing, and the reply says what
  actually changed ("Warmed up the background…"). A **text**-only edit leaves the backdrop alone. This works
  even when the LLM is rate-limited (regex fallback flags both "different background" and "warmer/brighter" as
  background edits). A brand-new request ("create a new image") is NOT treated as an edit.
- **DESIGN VARIETY (`generation/designs.py`) — the app designs like a person, never stamps one look:** a
  `DesignProfile` bundles a palette (bg/ink/accent/card roles), a type pairing (`head_family`/`body_family`
  resolved by `common.font`), a layout signature (align, kicker style, divider, hero photo side), and a motif.
  **9 profiles** — Classic Navy, Editorial Cream (serif, photo-left), Bold Red (display poster), Split Duotone,
  Soft Neutral (centred), Midnight (dark+gold), Charcoal Editorial (dark centred serif), Cream Bold (light
  display, photo-left), Warm Amber (warm espresso+gold). `pick_profile(owner, surface)` **auto-rotates and
  never repeats the last 3** (in-memory per owner+surface, like `teampost._SKIN_ROT`); `next_profile` powers a
  refine "use a different style" swap. `chatpost.build_chat_post(profile=…, owner=…)` applies it to hero/statement/stat/
  observance (mission keeps its own 6 backdrops); the chosen profile is stored in the asset meta. Fonts are
  bundled (Poppins/Playfair/Archivo Black, SIL OFL) so **dev == prod** — this also fixed a prod bug where the
  Linux droplet (no Windows fonts) fell back to Pillow's default font for all text. Headlines auto-shrink so a
  wide display face never breaks a word mid-line. Campaign (`teampost`) + decks keep their own variety.
  **Magazines use the SAME profiles:** `magazine.build_magazine(profile=…, owner=…)` auto-rotates a profile
  per issue and restyles the chrome only — page fill, spine (`_rail`), accent colour, masthead/title type
  (Editorial Cream = Playfair serif masthead), and **cover LAYOUT** (`cover_style` dispatches 4 real covers:
  `framed_right`/`framed_left`/`split_panel` = full-height photo + navy sidebar / `band_bottom` = display
  headline + bottom band), plus per-profile inner-page garlands (`_motif_band`) — while ALL data (award ranks,
  medal colours, stat values, category bands, real photos) and the festive festoon on holiday themes stay
  identical across profiles. Inner pages always stay light. The **default cover is `_cover_spotlight`**,
  modelled on the real reference issues in `TR Magazines/`: newspaper masthead + a HUGE display title (the
  cover headline; condensed, or serif on editorial profiles) + the champion **cut-out overlapping the title**
  (`_cutout`, framed fallback) + big stat callouts (`_big_stat`) + a "TOP PERFORMER" eyebrow/name/blurb band,
  over a paper `_grain`. (`split_panel`/`band_bottom` remain the alternates.) The **spotlight spread** matches
  the reference "Shining Stars" style too: cut-out people with an accent outline (`_outline`) on alternating
  sides, big names, big inline stat numbers, a blurb, and a hand-drawn arrow (`_hand_arrow`). The **editorial
  note** (colored masthead block + big title + justified body + script sign-off), **award** (big title + red
  name banner + huge display value + medal), **category** (big title + clipped column labels), and **closing**
  (big "THANK YOU") pages all got the same editorial treatment + paper grain — data always unchanged. Wired at both `/api/magazine/*` endpoints; profile saved in
  the asset meta. If the model
  takes the tool-loop path instead, `exec_regenerate_asset` **defaults to the most recent asset** when given
  no id/title — it never dead-ends asking the user for an internal asset title.
- **Brand grounding:** generators use `knowledge/retrieve.py` (`brand_context`, `image_references`) over
  the ingested TR library. **Campaign** generation grounds in the campaign's **brief** (`Campaign.goal`),
  threaded into every generator so content stays on the campaign's theme (no off-theme RPO leakage).

## 7. Agent (`backend/app/agent/`)
- `orchestrator.run(db, conversation_id, text, mode, attachments, campaign_id, owner)` — drives the tool
  loop and streams events (meta/status/token/asset/chips/done/error). `mode` ∈ chat | create | campaign.
  A **brief-intake** (`create_intake`) asks a short chip-driven brief before generating a vague asset —
  in Create/Campaign always, and in **Chat** for creation requests (`is_visual_create_request`); an
  `@mention` short-circuits straight to the person post before the intake. So every chat box that can make
  an image asks "what kind?" first. A `@mention` of a **known Folders employee is the SUBJECT even when an
  image is attached** (the attachment is a design/reference, not the person) — so "same design as this, but
  with @Pooja" features Pooja's REAL photo, never re-renders the attached screenshot into invented people;
  escape hatches: "use this photo", or an @-name NOT in Folders, feature the uploaded photo instead.
- **`/` + `@` palette (frontend).** The chat boxes (Chat, internal-campaign studio) share one
  implementation — `frontend/lib/atMentions.tsx` (`useAtMentions` hook + `<AtMenu>`). **Two separate
  triggers:** typing **`@`** lists only **People** (Folders employees → feature their real photo); typing
  **`/`** lists only **Create actions** (image/deck/PDF, Write a post; Chat also has Find prospects). The
  pick derives its trigger from the current text so it always replaces the right token.
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
**Password reset email:** set `SMTP_HOST` + `SMTP_FROM` (+ `SMTP_USER`/`SMTP_PASSWORD`/`SMTP_PORT`/
`SMTP_STARTTLS`) to email the "forgot password" code; the deploy injects these from GitHub secrets of the
same names (same path as the OpenAI key). Until set, the code is only written to the server log, so the
reset flow can't reach the user — the deploy leaves those `.env` lines untouched when the secrets are unset.

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
