# Changelog — Talentrupt Marketing Agent

All notable changes to the app, most recent first. Dates are when the work landed on
`feat/create-chip-brief-intake`.

## Advanced, varied employee posts — brand skins + reference series (2026-07-01)
Learned from 40+ real Talentrupt posts and rebuilt the employee-image engine (`generation/teampost.py`).
- **Not navy every time.** Introduced brand **skins** — `light` (clean white), `cream` (warm), `navy`,
  `red`, and `photo` (a gpt-image-2 photographic scene, now with VARIED non-navy moods). Employee posts
  now **rotate** across them (no immediate repeat), so consecutive posts look different. Ask for a look
  and it's honoured ("on white" → light, "photographic" → photo).
- **Reference "series" templates.** New skin-aware renderers matching the real posts: **spotlight_series**
  ("Man on a Mission / Women Crush Wednesday" — red-box keyword headline, script "Featuring [Name]" + a
  hand-drawn arrow, role badge), **welcome** (new-hire), **anniversary** ("X Strong Years" — giant script
  number + story), and a multi-employee **grid** ("One Year Strong"). The agent auto-picks the series from
  the message ("7 years" → anniversary, "welcome" → welcome, "the team" → grid) or you can name it.
- **Nothing overrides — verified.** Every layout computes fixed non-overlapping regions (photo one side,
  text clamped to the other, wordmark in a reserved margin) and a final `_ensure_clear` guard asserts the
  photo / headline / subline / name / badge / wordmark bounding boxes are mutually disjoint. Rendered the
  full matrix (styles × skins × both cut-out branches + edge cases) — **0 overlaps**.
- **Real cut-outs (opt-in).** Added a hosted background-removal hook (`generation/cutout.py`, remove.bg /
  Photoroom) gated by `BG_REMOVAL_API_KEY` — set it to float the person on the scene; without it (default)
  the person sits in a premium framed card. Keeps the heavy `rembg`/`onnxruntime` off the 2GB droplet. The
  API only strips the background — the face is never altered.
- **Script font.** Bundled Caveat (SIL OFL) for the handwritten "Featuring [Name]" accent, with graceful
  fallbacks (`common.script_font`).

## Reply thumbs now react visibly (2026-07-01)
- **👍/👎 give clear feedback.** Clicking a thumb under a reply now flips it from a grey outline to a
  solid, accent-coloured fill (with a small press animation) and toggles off on a second click — so the
  user can actually react. It's a local reaction (per message, no backend), which is what was asked for.

## Logo → the real isometric-cube "M" (2026-07-01)
- **Myra mark rebuilt to the actual logo** — the 3D isometric cube "M": a red roof with a white diamond
  notch, a red centre spike, and two navy legs, on a white disc (`MyraMark` in `MyraLogo.tsx`, hand-traced
  to SVG so it stays crisp at every size). The white disc is the theme adjustment: it blends into the white
  light-theme header (you just see the M) and gives the navy legs a light backdrop on the dark theme, so a
  single mark reads on both. Used in the header, reply avatar, and login / loading screens.

## Logo fix + sidebar row icons (2026-07-01)
- **Myra mark corrected.** The badge now carries the real Myra "M" — two white legs + a coral inner V +
  the coral swoosh over the top — on the navy tile, instead of the flat single-stroke coral "M" from the
  first pass. (UI only; the "Myra" wordmark is still untouched and no Talentrupt wordmark in the chrome.)
- **Icons on the sidebar rows.** Each Chat conversation row now has a chat-bubble glyph on the left (and
  Create's history rows an image glyph), matching the design — a small leading icon + the title.

## New Myra badge logo + image refine chips (2026-07-01)
- **New Myra logo.** The Myra mark is now an app-icon-style **navy rounded badge with a coral "M"**
  (`MyraMark` in `MyraLogo.tsx`) — self-contained so it reads on the white header, the light chat area
  (as the reply avatar), and the login / loading screens. Only the Myra mark changed; the "Myra" wordmark
  and everything else are untouched, and the Talentrupt wordmark is NOT shown in the chrome.
- **One-tap image refine chips.** Under an image reply in Chat and Create you now get quick refinements —
  **Make it square · Add company logo · Use different colours · More options** (which reveals a few more
  inline). Each just sends a follow-up prompt the agent already understands, so it re-works the last image.
- **Download on the reply.** The assistant action row now includes a **download** button when the reply
  produced a file (alongside copy + 👍/👎). The reply also reorders to text → image → actions → chips,
  matching the design.

## Navy-sidebar theme + polished reply UI (2026-07-01)
- **Deep-navy left rails.** Every navigation/history rail — Chat conversations, Create history, the
  Campaigns list, and the Folders list — is now a deep-navy panel (matching the app design), with a red
  "New …" button on top and light-on-navy list items. It's driven by a single `.rail` class in
  `globals.css` that re-scopes the theme tokens locally (`--surface`, `--muted`, `--foreground`,
  `--border`, and the active `--brand-navy` highlight), so the existing rail utilities adapt to navy with
  no per-element edits. The top header is now solid white. (Business Dev's prospect list stays light — it's
  a data panel with colored status chips, not a nav rail.)
- **Redesigned assistant replies.** Across Chat, Create and both campaign chats, a reply now shows the
  **Myra "M" avatar** beside it, a clean card (soft shadow, chat-style corner), and a compact action row
  (copy the reply + quick 👍/👎). User messages show your initials avatar. Copy is real; the thumbs are a
  local acknowledgement.
- **Myra logo & wordmark untouched** — this was a colour-theme + layout pass only; the Myra mark and "Myra"
  text are unchanged.
- Verified end-to-end: navy rails compile correctly (`.rail{…;background:#0b3559}`), reply avatars/actions
  render in all four chat surfaces, no dark-on-navy invisibility, production build clean.

## "@" palette in campaign chat + unified chat UI (2026-07-01)
- **The "@" mention palette now works in the internal-campaign chat**, exactly like Chat and Create.
  Type `@` in a campaign's studio and you get **People** (real teammates from the Folders library — mention
  one to feature their real photo) plus **Quick actions** (Create image / deck / PDF / Write a post). The
  campaign studio already runs the "what kind of image?" brief-intake (it's on for `mode="campaign"`), so
  every place you can generate an image now both asks the clarifying question AND offers the `@` shortcuts.
- **One shared `@` implementation.** The palette logic + dropdown were duplicated in ChatPanel and CreateView;
  they're now a single module (`lib/atMentions.tsx` — `useAtMentions` hook + `<AtMenu>`), used by all three
  chat boxes so they can't drift apart. Chat keeps its extra "post"/"prospects" actions; the campaign studio
  uses image/deck/PDF/post.
- **Campaign chat UI now matches the other chat sections.** The studio's messages + composer were rebuilt to
  mirror ChatPanel: an open (un-boxed) message area, a centered `max-w-3xl` column, a top-divider composer,
  and the same "Enter to send · Shift+Enter · type @…" footer hint + placeholder.
- **Fixed the horizontal scrollbar in the campaign chat.** Generated asset cards (`DeletableAsset`) lacked
  `min-w-0`, so a card wouldn't shrink to its grid track and spilled ~90px past the column, forcing a
  horizontal scrollbar. Added `min-w-0` to the asset wrapper (and to the image/video card title so a long
  title truncates instead of pushing width). Assets now cap cleanly at the column width — no more sideways
  scroll.

## Creative, name-aware headlines + no text overlap (2026-07-01)
- **The AI writes the copy, not just cleans it up.** For a featured-person post the headline is now written
  creatively from your CONTEXT and uses the person's FIRST NAME — so *"@Pooja welcoming her at talentrupt"*
  becomes **"Pooja Joins the Talentrupt Family!"** (not the literal "Welcoming Her To Talentrupt"). Other
  examples: a deadline congrats → "Cheers to Vaishnav's Timely Triumph!", a 5-year anniversary → "Cheers to
  Five Years, Aarav!". You give the intent; the model owns the wording.
- **Headline can no longer touch the photo.** `_draw_headline` now shrinks the font when a single long word
  (e.g. "Talentrupt") would overflow the column width — not just when there are too many lines — so the
  caption never spills onto the person / photo card.

## Light theme by default (2026-07-01)
- **Light is now the default theme.** A fresh load (no saved preference) renders the **light** theme
  instead of dark — the pre-paint script sets `data-theme="light"` by default and the Shell falls back to
  light. Anyone who explicitly toggled a theme keeps their choice, and the light/dark toggle is unchanged.

## Chat brief-intake + no-overlap (2026-07-01)
- **Chat asks "what kind of image?" too.** The Create studio's brief-intake (a short, chip-driven
  back-and-forth about look/style/audience before generating) now also runs in **Chat** — but ONLY for
  visual/document **creation** requests (gated by `create_intake.is_visual_create_request`), so
  prospecting, Q&A and other chat work are never interrupted. A specific request or "your call" still
  generates immediately, and `@mention` posts skip it (they're already specific).
- **No text/logo overlap in employee posts.** In the AI-scene layout the headline + subtext width is now
  clamped to the space to the LEFT of the person/photo card (`person_left`), so a long headline can never
  run under the photo. The wordmark sits in its own reserved margin below the card. (AI images already
  reserve a clean footer band for the wordmark, so no overlap there either.)

## Designed employee posts (2026-07-01)
- **Employee posts are now AI-DESIGNED, not flat templates.** An `@mention` (or any "feature <person>")
  now defaults to the **AI-scene** path: gpt-image-2 generates a rich, on-theme branded background — tied
  to the post's **message** (a "deadline success" post gets an achievement mood; a "welcome" post a
  welcome mood) — and the person's **REAL photo** is composited on it (face never AI-generated). Where the
  cut-out lib (`rembg`) is present the person floats on the scene; otherwise the real photo is placed in a
  designed rounded **framed card** (not a pasted rectangle). Big step up from the flat navy panel.
- **Headline no longer echoes a filler prompt.** A vague back-reference like *"and the same for @Pooja"*
  now falls back to a proper headline (it carries no real message) instead of printing "And The Same For".

## Vibe prospecting (2026-07-01)
- **Describe your ideal client in plain English → a ranked list of real companies.** A "vibe" layer on
  top of the existing discovery engine (reuses all the real web-research, fit-scoring, contacts + pipeline):
  - `business/discover.py:vibe_to_icp()` — an LLM step that interprets a freeform "ideal client"
    description into a sharp, structured profile (industry, size, location, buying **signal**, keywords)
    + a plain-English read-back. Extracts only what's stated — never invents specifics (no-fabrication rule).
  - **Chat / agent:** new `vibe_prospect` tool — e.g. *"vibe: US healthcare groups scaling clinical hiring
    fast"* → interprets, finds REAL fit-scored companies, ranks by fit, saves to Business Dev, and offers
    to refine ("smaller companies", "drop staffing agencies"). (Per "every feature is a Chat tool.")
  - **Business Dev:** a **"✨ Vibe match"** button + a *"Read your vibe as: …"* read-back of the interpreted
    profile. Plain **Find** and **Analyze** stay.
  - **External Campaigns:** a campaign's **audience** is now run through the same interpreter to sharpen its
    client discovery (adds inferred size/location/signal; the vetted sector stays authoritative).
  - New endpoint `POST /api/business/vibe-discover` (returns the interpreted ICP + the scored list).
    Real data only — deeper real-time "why now" signals still need a data provider (enrichment is off in prod).

## Image model → gpt-image-2 (2026-06-30)
- **Default image model switched to `gpt-image-2`** (OpenAI's latest — now live; it didn't exist when we
  first tried). Verified end-to-end through the app's own pipeline: it returns b64 like gpt-image-1,
  accepts `quality=high`, and `meta.model` came back `gpt-image-2` (a real run, not a fallback). The
  gpt-image-1 auto-fallback stays, so a key without access can never break generation. `/api/health` now
  reports `image_model` (configured) + `image_model_last` (what actually ran) to verify which is live.
  **Requires an `OPENAI_API_KEY` with gpt-image-2 access in the server's `backend/.env`** (the deploy
  never touches `.env`, so this is set on the droplet, not in the repo).

## Feature an employee by @mention (2026-06-30)
- **Folders is now a pure reference library**; the in-section "Generate post" / "Generate for everyone"
  controls are removed. You feature people from **Create or Chat** instead.
- **New agent tool `feature_employee`** (owner-scoped): looks an employee up in your Folders by name,
  reads their REAL saved photo, and builds a branded post (real-photo template — never an AI face).
  Wired into Chat, Create and internal campaigns, so however you ask, it can do it.
- **`@` autocomplete in Create & Chat.** Type `@` in the message box and your **employees** appear at the
  top (with their photo), the existing **quick actions** below. Pick someone → it inserts `@Their Name`;
  add context and send → a post with their real photo. New flat `GET /api/employees` backs the picker.
- **The raw prompt no longer leaks into the post headline.** "Create an image of @Nishant promoting for
  Talentrupt" used to print the literal words ("promoting for talentrupt") as the headline — because an
  `@mention` is handled deterministically and skips the agent that would normally polish it. Now the
  instruction phrasing + name are stripped (`_clean_headline`) and a quick LLM pass (`_polish_headline`)
  rewrites the rough phrase into a punchy headline (e.g. "promoting for talentrupt" → "Elevate Your Hiring
  Game"), with a safe fallback to the cleaned text if the LLM is unavailable.
- **`generate_team_image` finds Folders employees too (no `@` needed).** Even a plain request like
  "create an image of Nishant promoting Talentrupt" now resolves the name against your Folders library
  first and features their real photo — instead of failing with "no team photos for Nishant in the
  library / add to the Team/ folder." A single shared matcher (`_find_employee`) backs both tools.
- **`@mentions` are deterministic.** An `@Name` in Create or Chat now runs `feature_employee` **directly**
  (the orchestrator resolves the name against your Folders and generates immediately) — it never gets
  caught by the Create brief-intake questions and never mistakenly calls `generate_team_image` (the old
  brand-library "Team/" folder). Fixes the "no team photos for X in the brand library" reply when X was
  actually uploaded to Folders.

## Real brand logo in generated images (2026-06-30)
- **The official TALENTRUPT wordmark now appears in generated images — without ever covering content.**
  Extracted the real wordmark from the brand-guideline PDF (transparent **navy** + **white** variants)
  and replaced the old square "TR" badge that was being *stamped on top* of team/folder posts (it landed
  on the person's photo — the overlap you saw). Now:
  - **Team / folder posts** place the white wordmark in the clean **bottom margin** of every layout
    (spotlight / magazine / split / framed) — reserved navy/scrim space, never over the photo or text.
  - **AI images** get a slim brand **footer band** (cream strip + coral keyline + navy wordmark) beneath
    the artwork, and the prompt now keeps the bottom ~12% clear so nothing important is covered.
  - New `paste_wordmark` + `wordmark_path` helpers in `common.py`; assets bundled at
    `backend/app/brand/tr_wordmark.png` + `tr_wordmark_white.png`. Decks/PDFs are unchanged.

## Image quality + Folders fixes (2026-06-30)
- **No more decorative starburst/squiggle symbols.** The little coral starburst/asterisk and the
  hand-drawn squiggle/swoosh were being drawn on most images. Removed: the decoration treatments are now
  clean-only, and the prompt explicitly forbids any starburst, asterisk, sparkle, squiggle, swoosh,
  scribble or dotted-grid motif.
- **No more dark / hazy / washed-out images.** One image shipped dim and foggy with barely-legible text.
  Two guards now stop that: (1) the render prompt demands **bright, high-contrast, fully-legible** output
  and forbids fog/haze/dim/grey-wash renders, and the dark "premium" palette is dropped from RPO content;
  (2) a new **contrast gate** measures each frame's contrast (alongside the existing sharpness gate) and
  **regenerates a washed-out frame, keeping the best** — so a hazy frame can't ship.
- **Folders generate the REAL employee, not random AI people.** Folder post generation was using the
  AI-scene path, which painted an AI background (with AI people) and needed a cut-out lib the server
  doesn't have — so you saw strangers. It now uses the **real-photo template** (`build_team_image`
  magazine/split): the employee's actual uploaded photo, full-bleed, in a branded navy layout. No AI
  faces, ever.
- **Employee photo thumbnails now display** (`/api/files/employees/*` was 404 — `employees` wasn't an
  allowed file kind) and the **"Upload photo from your device"** action on each folder is clearer.

## Folders — employee posts (2026-06-30)
- **New "Folders" section.** Create folders of employees (each = photo + name + role), then generate
  branded posts that feature their **real photos** (the real-photo template — never an AI face).
  "Generate post" per employee or "Generate for everyone" with an optional topic. New `Folder` +
  `Employee` models (owner-scoped) and `/api/folders` + `/api/employees` endpoints; nothing existing
  was changed.

## Chat & image model (2026-06-30)
- **`@` quick-actions in Chat.** Type `@` in the chat box for a command palette — Create image / Create
  deck / Create PDF / Write a post / Find prospects. Selecting one drops in a ready-to-fill prompt
  (Chat already runs these). Arrow keys + Enter/Tab to pick, Esc to dismiss.
- **Image model: safe, switchable, with auto-fallback.** Tried `gpt-image-2` per request — OpenAI
  **rejected it** (not a real model yet; verified live, the asset fell back to `gpt-image-1`), so the
  default stays `gpt-image-1` (no wasted failed call per image). The model is one-line switchable
  (`OPENAI_IMAGE_MODEL`) and `llm.py` now falls back to `gpt-image-1` automatically if a configured model
  is unavailable, so a future switch can never break generation; the asset `meta.model` records which
  model actually ran.

## Reliability (2026-06-30)
- **Past generations / history no longer "vanish" after a deploy.** The data was never lost — the DB keeps
  accumulating (verified 44 → 52 assets across deploys). But the view-load GETs (`/assets`,
  `/conversations`, `/campaigns`, `/opportunities`, `/auth/me`, `/brand`) had **no retry**, so a fetch that
  happened to hit the ~2-4s backend restart during a deploy failed and was **silently swallowed**, leaving
  the gallery/history empty until a manual refresh. Those GETs now retry through the restart blip
  (`fetchRetry`), and `/auth/me` retries too so a deploy can't momentarily log you out.

## Content & viewing (2026-06-30)
- **No more stamped logo on generated images.** The Talentrupt "TR" badge that was composited onto every
  AI image is removed — images ship clean and use the full canvas (the "keep the corner empty" reservation
  is gone). The no‑wordmark guard stays so the model still won't *draw* a brand name. (Team‑photo posts and
  the deterministic fallback are separate paths and unchanged.)
- **Images/videos preview in‑app, not a new tab.** The "view" (eye) action — and clicking the image — now
  opens an in‑app lightbox modal (download + close) instead of `target="_blank"`. (`AssetCard.tsx`.)
- **External campaign "Content calendar" → "Content ideas."** It's now an inspiration board (dated
  post/image/deck ideas you can reschedule); the per‑row Generate/Open was removed — generate from Chat or
  Create. Backend/data untouched.

## Image design variety (2026-06-30)
- **Designs lock to the post's TOPIC (not off-theme).** The art-director now plans a topic-specific
  `scene` (the concrete imagery to depict — analytics dashboards for a data post, a yoga pose for a yoga
  post, players/pitch for a football post) and the renderer treats that scene as the **AUTHORITATIVE
  subject**, overriding the style templates' generic example subjects (handshakes, office props). So a
  data-driven post gets data designs and a culture post gets that culture's imagery — never an unrelated
  theme. The VARIETY is in the LOOK (palette/decoration); the SUBJECT stays on the topic.
- **Generated images no longer all share one look.** The image prompt forced the SAME skin on every post
  (fixed navy/coral/cream palette + a headline with exactly one coral word + the same coral starburst/
  squiggle motifs). Now each image picks a **color palette** and a **decoration treatment** that vary
  image-to-image, **context-aware**: RPO/sales content stays close to brand (the signature look is
  weighted ~45%), internal campaigns roam the full palette set. The format is ALL that changed — quality
  and content rules are untouched (blur gate, face guard, logo overlay + bottom-right space,
  no-fabrication, brief grounding). One shared engine, so it applies to **Create and internal campaigns**.

## UI (2026-06-30)
- **Account menu.** The header now shows just your **avatar**; clicking it opens a dropdown with your
  name, email, a light/dark **theme toggle**, and **Sign out** (closes on outside-click / Esc). Replaces
  the always-on name + email + logout + theme icons.
- **Stream retry widened to cover a deploy restart.** Chat/Create/Campaign streams now retry the initial
  connection for ~4s (up to 5 attempts) on a transient 502/network blip, so the brief backend restart
  during a deploy no longer surfaces as "network error".

## Accounts & security (2026-06-29)
- **Member login added** — `nishant@talentrupt.com` signs in as a non-admin **member**; the existing
  `Admin@talentrupt.com` stays admin. Role is derived server-side from the bearer token (`/api/auth/me`),
  so it can't be spoofed from the browser.
- **Tasks & Analytics are admin-only** — hidden from the member's nav *and* their APIs return 403, so a
  member can't reach that data even by calling the endpoints directly.
- **Per-account data isolation** — every owned record (conversations, campaigns, assets, opportunities,
  tasks, uploads) now carries an `owner` and is scoped to the logged-in account. Each account sees only
  its own data; cross-account get/delete returns 404. Existing data is assigned to **admin** by a
  one-time migration that runs automatically on startup. (Fixes "one account's info showing on another".)

## Campaigns & chat accuracy (2026-06-30)
- **Chat no longer mislabels campaigns.** Asked "how many *internal* campaigns", chat was lumping
  external client-targeting "RPO Outreach" campaigns in as internal. The `list_campaigns` tool now
  splits results by **type** (internal = promote Talentrupt; external = client-targeting), takes a
  `type` filter, and — critically — is **owner-scoped** (it was counting every account's campaigns).
  `list_assets` was owner-scoped for the same leak.
- **Archived campaigns are viewable & restorable.** Archived campaigns now hide from the active rails
  (they were leaking into the Internal rail) and live under a **"View archived"** toggle in Campaigns,
  each with a **Restore** action. `GET /api/campaigns` hides archived by default; `?status=archived`
  lists them.

## Reliability & fixes (2026-06-30)
- **Blurry images no longer ship.** gpt-image-1 occasionally returns a soft/out-of-focus frame. The
  pipeline now measures each frame's sharpness (variance-of-Laplacian, calibrated: sharp ≈ 1000–1300,
  blurry < ~220) and, when a frame is soft, **regenerates and keeps the sharpest** (up to 3 tries) before
  the gentle crisp pass. Sharp frames pass on the first try, so the extra cost only kicks in on a
  genuinely blurry result. (`generation/images.py:_sharpness` / `_openai_image`.)
- **Campaign clients no longer come back empty for overlapping sectors.** The client purity gate
  required an exact sector match, so healthcare *staffing* agencies (labeled "Staffing & Recruiting")
  were dropped from a **Healthcare** campaign — leaving 0 clients. The gate now also keeps a company
  when its segment text clearly belongs to the campaign's sector, so a "healthcare staffing agency"
  correctly counts as a Healthcare target. (`main.py:_segment_ok_for_sector`.)
- **Streams ride through restart blips.** Chat/Create/Campaign streams now retry the initial
  connection on a transient `502/503/504` or a pre-response network drop (which happen briefly during a
  deploy restart) instead of immediately surfacing "network error" / "Request failed (502)".

## Branding (2026-06-30)
- **Logo refined to the M mark only** — the header/login/loading badge dropped the white tile; the "M"
  now uses `currentColor` for its legs so it adapts to **both light and dark themes** (navy on light,
  white on dark), with the coral swoosh constant. The favicon is theme-aware too (via
  `prefers-color-scheme`), transparent, no tile.
- **App rebranded to "Myra".** The UI chrome — header, login, loading screen, page `<title>` and favicon —
  now shows the **Myra** name and a new "M" brand mark (navy legs + coral→pink swoosh), via the new
  `components/MyraLogo.tsx` and `app/icon.svg`. UI-only: auth/session keys, APIs, and the Talentrupt
  *content* brand used for generation are untouched, so the working flow is unchanged.
- **Clean static redeploys** — the deploy now wipes `frontend/out` before extracting the build, so assets
  removed from the build (like the old default `favicon.ico`) don't linger on the droplet (`tar -x`
  overlays files but never deletes ones dropped from a later build).

## Business Dev (2026-06-30)
- **C-level "Search LinkedIn" links now actually return results.** The people-search URL used to
  exact-quote BOTH the company and the title and AND them (e.g. `"SCIGON" "Chief Operating Officer"`),
  which LinkedIn answered with "No results found." Now the title is unquoted and the company is quoted
  only when it's multi-word — a high-recall query (`SCIGON Chief Operating Officer`) that lands the rep
  on the right people. The no-fabricated-names rule and the suppression of generic roles / ambiguous
  company names are unchanged. Existing prospects pick up the fix automatically (URLs regenerate on read).

## Campaigns (2026-06-29)
- **Internal vs External** split. Internal campaigns are a Create-style chat studio that promotes
  Talentrupt itself.
- **Brief-driven generation** — a new internal campaign **auto-generates a starter pack from its
  description**; the chat is then for edits. Editable brief via the **Brief** button (updates the
  grounding for future generations).
- **On-theme content** — the campaign brief now flows into *every* generator (image/post/deck/PDF), so a
  cricket campaign makes cricket content and a football campaign makes football content — no more
  off-theme "RPO DONE RIGHT" creatives leaking in. Magazine/brochure/etc. route to a PDF, not a deck.
- **Delete** control on each generated asset; the description is editable, not a static header.

## Images (2026-06-29)
- A deterministic **crisp-up pass** removes gpt-image-1's occasional soft/hazy frames, tuned to a gentle
  level (not over-sharpened).

## Deployment (2026-06-30)
- **Auto-deploy is live & green** — the GitHub Actions pipeline now deploys end-to-end on every push
  (build → ship → restart → health-check). Fixed three first-run issues: the scp source must live inside
  the workspace (`tar: empty archive`), deploys now **queue** instead of cancel mid-flight, and the
  post-restart health check **retries for ~60s** instead of a single `sleep 2` (uvicorn + migrations need
  a moment to boot, which was reporting a false failure even though the app was up).

## Deployment (2026-06-29)
- **Deploy verification** — `GET /api/health` now returns the live `version` (the deployed commit SHA,
  stamped by CI). Confirms from the outside exactly which commit is live after a deploy.
- **One-command, fully-automated release** — `deploy/ship.ps1 "what changed"` builds the frontend locally
  (pre-flight gate), commits, and pushes; the push triggers `.github/workflows/deploy.yml`, which rebuilds
  the UI on GitHub's runner, ships it to the droplet, restarts `myra`, and health-checks `/api/health`.
  No manual droplet steps. One-time enablement = authorize a deploy key + add `DROPLET_HOST` /
  `DROPLET_SSH_KEY` repo secrets (see `deploy/DEPLOY.md` → "Auto-deploy enablement").
- **Single process** — the Next.js frontend is statically exported (`output: 'export'`) and served by the
  FastAPI/uvicorn process, so the whole app runs as **one** PM2 process (`myra`), no separate Node server.
- **Deploy artifacts** under `deploy/` — `bootstrap.sh` (one-command first-time setup), `nginx-myra.conf`,
  `ecosystem.config.js`, `deploy.sh`, and `DEPLOY.md`, all targeting **myra.htuniverse.com**.
- The heavy/optional team-photo cut-out deps (`rembg`/`onnxruntime`/`pillow-heif`) moved to
  `backend/requirements-optional.txt` so a default install resolves cleanly.

## Live
- **https://myra.htuniverse.com** on the shared HT droplet — see `deploy/DEPLOY.md`.
