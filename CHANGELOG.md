# Changelog — Talentrupt Marketing Agent

All notable changes to the app, most recent first. Dates are when the work landed on
`feat/create-chip-brief-intake`.

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
- **The raw prompt no longer leaks into the post headline.** "Create an image of Nishant for Talentrupt's
  success" used to print the literal instruction ("Create an image of for talentrupts success") as the
  headline. The leading "create/make/generate an image of/for/about …" phrasing and the person's name are
  now stripped (`_clean_headline`), so the headline reads as the actual message.
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
