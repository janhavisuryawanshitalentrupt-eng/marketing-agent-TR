# Changelog — Talentrupt Marketing Agent

All notable changes to the app, most recent first. Dates are when the work landed on
`feat/create-chip-brief-intake`.

## Fix: "keep the same person, change the background" no longer swaps the person (2026-07-07)
Refining an image in Chat with "keep the same person but use a different background" swapped the person (Pooja
→ Vaishnav). Cause: when the refine had no explicit asset id/title it fell back to the account's GLOBAL
most-recent asset — which could be a different person from another chat. Now it targets the last asset IN THE
CURRENT CONVERSATION first:

- New `_last_conversation_asset(db, conversation_id, owner)` reads the conversation's own messages
  (`Message.assets`) to find the image the user is actually looking at. `state` now carries `conversation_id`.
- `exec_regenerate_asset` and the orchestrator's `_last_refinable_asset` resolve the conversation asset FIRST,
  only falling back to the campaign/owner most-recent when the thread has none.
- `_is_refinement` now also recognises "different"/"another" (so "use a different background" is caught).
- Verified: with Vaishnav as the global most-recent asset, refining inside the Pooja thread resolves to Pooja.

## Softened photo sharpening so it stops garbling real shirt text (2026-07-07)
An aggressive `UnsharpMask` (radius 1.5, 95%) added crunchy halos to the small, already-soft logo printed on a
real (out-of-focus, wrinkled) t-shirt — making "emerge·evolve·establish" look broken. Dialed it back to a
moderate mask (radius 1.1, 55%) that still keeps printed text legible without haloing. Confirmed on a
clean-text synthetic that the pipeline itself renders shirt text crisply — the remaining softness is inherent
to the SOURCE photo's small logo (we keep it exactly as-is; we never redraw it). Truly large/crisp shirt text
needs a closer/higher-res source photo or a tighter chest crop.

## Fix: campaign images no longer bleed into the general Chat area (2026-07-07)
Chat and Campaign are different jobs — Chat = general Talentrupt-brand image creation; Campaign = images
customized to that campaign's brief. But the Chat/Create "Your generations" gallery listed EVERY asset the
account owned, including campaign-specific ones — so a Football-campaign banner showed up in the general Chat
section. Fixed:

- `/api/assets` gained a `general=true` param that returns only NON-campaign assets (`campaign_id IS NULL`);
  the Chat/Create gallery (`getAssets`) now always passes it. Campaign images stay in that campaign's
  Generated-content tab. Verified live: `general=true` dropped all 58 campaign assets (163→105), and the Chat
  gallery renders only brand posts (e.g. Nishant "Inspiration through Excellence" on the navy brand backdrop),
  no football.
- Hardened `images.build_images`: the SCENE theme now comes ONLY from an explicit campaign theme/brief, never
  the free-text `concept` (`scene_theme = theme or brief or ""`). So a campaign topic can never theme a Chat
  scene; in Chat a featured person is staged on the generic Talentrupt brand backdrop. (Chat's feature path
  already used `theme=""` — the on-image name is kept and the eyebrow is the team rotation, confirmed by test.)

## Fix: green speckles on the person + crisper shirt text (2026-07-06)
On a green-pitch scene, coloured speckles appeared on the subject's arms/hands — the bright background showing
through tiny holes the free keyer punched in the body (a watch, a specular highlight, a light tattoo). Fixed
in the cut-out + compositor:

- **Interior solidify** (`_key_plain_bg`): after the neutral / bright-wall gates run, the alpha is re-flooded
  from the border and every 0-pixel NOT reached (i.e. enclosed by the subject) is forced OPAQUE — so the scene
  can no longer show through the body as speckles. Genuine see-through gaps that open to the frame edge stay
  cut, which is correct.
- **Green despill** (`_place_editorial_person`): the subject has no real green (warm skin, navy shirt, dark
  hair), so any strongly green-dominant pixel is spill/fringe from the pitch — its green channel is pulled down
  to just above max(R,B), killing green edge-fringe on a photo background.
- **Crisper shirt text** (`_enhance_photo`): swapped part of the flat Sharpness boost for an `UnsharpMask`
  (radius 1.5, 95%, threshold 3) that crisps EDGES — a printed brand-tee logo stays legible — and the
  half-body subject is sized a touch larger (0.80→0.84·H, cap 0.52→0.56·W) so the text reads.

Verified on a synthetic with a bright forearm spot over a green pitch: the hole fills with the person's own
pixels (no green dot) and the shirt logo renders clearly. NOTE: a hosted `BG_REMOVAL_API_KEY` (remove.bg)
still gives the cleanest alpha of all — recommended for photos with busy arms/tattoos.

## Image model routing: gpt-image-2 for the main image, gpt-image-1 for small tasks (2026-07-06)
The featured/user-facing image now always uses the best model; small auxiliary graphics use the lighter,
cheaper one. `generate_image_bytes` gained a `model` override: the MAIN images — the featured campaign/employee
scene backgrounds (`_scene_prompt`) and any user-requested "create an image" (`images.build_images`) — keep the
configured **gpt-image-2** (with gpt-image-1 only as an emergency fallback if gpt-image-2 is ever rejected),
while the small/auxiliary jobs are pinned to **gpt-image-1**: the split-poster PANEL graphic (`_panel_theme_
prompt`) and the deck COVER image (`decks.py`). Image EDITS already run on gpt-image-1 (the edit endpoint is a
gpt-image-1 capability). Net: the deliverable the user sees is gpt-image-2; the behind-the-scenes bits are
gpt-image-1.

## Fix: half-body person placement (no more corner-jam / floating / edge-cut) (2026-07-06)
The composited subject was being shoved into the bottom corner, cut off on the outer edge, and left floating
above a gap of background — which repeatedly read as "the placement is not proper." `_place_editorial_person`
now composes a half-body cut-out properly: a narrower width cap (≤0.50–0.52·W) + a bigger side inset
(right_pad 24→60, layout-3 left inset 24→46) so it never jams into or bleeds off the SIDE, and it's GROUNDED
— the torso bottom bleeds a touch OFF the frame (`hy = H - h + 0.03·H`) instead of the old 5% lift, so there's
no floating gap and no hard cut line, while the chest (and its printed shirt text) still sits mid-frame.
Verified on a realistic half-body render across layouts 1 and 3.

## Fix: refine never dead-ends asking for an asset title (2026-07-06)
A follow-up like "the person's placement is not proper" could get stuck in a loop where the assistant kept
asking for "the exact title or ID of the asset" — an internal detail the user doesn't know. Root causes fixed:

- **`exec_regenerate_asset` now defaults to the MOST RECENT asset** in the campaign/context when no id or
  title matches (was: returned "tell me which asset" → the LLM relayed it → infinite loop). It also scopes
  the title/id match to the caller's own assets. The loop is impossible now: refine always has a target.
- **`regenerate_asset` tool description rewritten** to tell the model to OMIT asset_id/title (it auto-targets
  the latest) and to NEVER ask the user for a title — just call it with the user's feedback as the instruction.
- **`_is_refinement` is now intent-based, not keyword-rigid** (the user's ask: "free it to think on its own").
  It catches layout feedback ("placement", "reposition", "cropped", "framing"), plain dissatisfaction ("not
  proper", "doesn't look right", "isn't clear", "not visible"), and "is/looks off" — while still excluding
  genuine new-asset requests ("create a new image") and unrelated asks ("our market position", "position to
  hire"). Verified end-to-end: a wrong guessed title still refines the latest asset instead of looping.

## Edit + copy on your own chat messages (2026-07-06)
User (input) messages in the transcript now have hover actions — **Copy** and **Edit** — in Chat/Create and
in the campaign chat. Copy puts the message text on the clipboard. Edit turns the bubble into an inline
textarea (Enter saves · Esc cancels · Shift+Enter newline); saving re-runs the corrected prompt ChatGPT-style:
it removes that turn + everything after it from BOTH the on-screen transcript and the persisted history, then
re-sends — so there's no duplicate and the history stays consistent on reload.

- New shared `UserMessage` component (attachments + bubble + hover copy/edit + inline editing) replaces the
  duplicated user-row markup in `ChatPanel` and `CampaignsView`.
- `ChatProvider.editMessage(index, text)` (and the campaign view's local equivalent) drop `messages.length -
  index` turns — counted from the BACK, so it's unaffected by any synthetic (unpersisted) greeting at the
  front — via a new `POST /api/conversations/{id}/truncate` (`{drop}`, owner-checked), then re-send.
- Verified live end-to-end: editing "List three colors" → "List three fruits" removed the old turn + reply,
  truncated the conversation (`/truncate → 200`), and produced a fresh fruit list — clean transcript, no errors.

## Conversational image editing (ChatGPT-style) + a person "fit" control (2026-07-06)
Follow-up edits on a generated image now EDIT that image in place instead of re-asking for a style. Before,
saying "the person doesn't fit" or "change the background" made the campaign brief-intake treat it as a brand
-new request and ask "What style do you envision?". Now:

- **Routing** (`orchestrator.py`): `_is_refinement(text)` detects an edit follow-up ("change the background",
  "change the text to X", "make the person smaller", "the person doesn't fit", "make it more colourful") vs a
  brand-new request ("create a new image"). When one fires in Campaign/Create mode and a refinable asset
  exists (`_last_refinable_asset`, scoped by campaign), `_refine_and_emit` refines the LAST asset in place —
  BEFORE the brief-intake can re-ask for a style.
- **Interpretation** (`refine.py`): `_parse_image_edit` uses the LLM to turn the instruction into
  `{op: text|background|fit|design, headline, background, fit, eyebrow}`. The team-image regenerate reuses the
  ORIGINAL design `variant` + `eyebrow` so only the requested thing changes: text → new headline;
  background/scene/location → new themed scene (person kept as-is); "doesn't fit"/too big/small → a `fit`
  nudge; "different design" → a fresh variant. Returns a plain-English confirmation (`refine_note`).
- **Fit control** (`teampost.py`): `build_ai_scene`/`_build_editorial_banner`/`_place_editorial_person` take
  `fit` ('smaller'|'bigger'|'fit') to scale + reposition the subject, and `build_ai_scene` now stamps the
  design `variant`+`eyebrow` into the result meta so refines stay consistent. The default half-body lift was
  softened (7%→5%) so the subject looks grounded, not floating.

Verified end-to-end against a real DB asset: "change the text to Register Now for the August Cup" → headline
updates, eyebrow/theme/person unchanged; "change the background to a beach" → person kept on a new beach
scene; "the person doesn't fit" → subject scaled down, shirt text still readable.

## Announcement banners read as announcements + shirt text stays in-frame (2026-07-06)
Two fixes for the campaign employee banner (reported on the Football announcement featuring Pooja):

**Reads like an announcement, not a success story.** The eyebrow above the headline was a fixed rotation of
feature labels ("IN THE SPOTLIGHT", "MEET THE TEAM"…), which made an event announcement look like an
achievement / spotlight post. New `_post_eyebrow(message, theme)` classifies the post INTENT from the user's
words: an announcement / advertisement / event → **"SAVE THE DATE"** (when a month is named) or
**"ANNOUNCEMENT"**; an achievement → **"CELEBRATING"**; a welcome → **"WELCOME TO THE TEAM"**. The label is
plumbed through `_build_one → build_ai_scene → _build_editorial_banner (eyebrow=…)` and drawn on ALL three
editorial layouts (layout 2 previously drew no eyebrow at all). A role-model / campaign banner (no on-image
name) now NEVER says "In the Spotlight" — it falls back to "TALENTRUPT PRESENTS" when no intent matches.

**Shirt text no longer cut off / darkened.** `_place_editorial_person` scaled the cut-out to 90% height and
bottom-anchored it, so a HALF-BODY (head-to-torso) photo jammed the shirt — and any printed text like
"emerge-evolve-establish" — against the bottom edge and into the dark bottom scrim. It now detects a half-body
crop (bottom 10% of the alpha is a wide band of body = no feet) and renders it a touch smaller (80% H) and
LIFTED (7% H) on every template (never the top-bleed crop), so the shirt text sits fully in-frame, above the
scrim. A full-body shot still floor-anchors with a contact shadow. Verified across layouts 1/2/3.

## Preserve the text on the person's t-shirt (2026-07-03)
Rule: never change or garble the text/logo printed on a person's shirt (e.g. the "emerge-evolve-establish"
tee) — preserve it exactly unless explicitly asked. The default already honours this (themed images keep the
real photo as-is — only the background changes). The face-swap / gpt-image edit path is locked down too:
`STRICT_FACE_DIRECTIVE` now says to preserve the clothing and reproduce any printed text/logo exactly, and the
`_portrait_prompt` WARDROBE clause was changed from "dress them in a jersey / NO text on clothing" to "KEEP
their exact clothing and shirt text — do not swap, re-letter or garble it."

## No person's name in campaign/event banners (the person is a role model) (2026-07-03)
Campaign banners were putting the featured person's name in the copy (e.g. "Join Pooja at the Championship
Showdown!"). On a campaign/event/advertisement banner the person is just a ROLE MODEL for the visual — the
headline should be about the theme/event, never their name. `_polish_headline` was explicitly told to "weave
in their first name"; it now takes `use_name` and `exec_feature_employee` passes `use_name=False` in campaign
mode, so the headline is written about the event/theme with no name (plus a regex safety strip). Verified:
campaign → "Kick Off the Ultimate Championship!" (no name); Chat/Create still allows the first name for
personal posts (e.g. a welcome). The on-image "Featuring [Name]" label was already suppressed on campaigns.

## Themed images: keep the person AS-IS, change only the background to a realistic scene (2026-07-03)
Per the user: keep the person's photo exactly as-is (do NOT regenerate them) and just change the background to
a realistic themed one. So the themed default is now the REAL cut-out person (their exact photo — face, pose,
clothes untouched) composited onto a **realistic themed BACKGROUND PHOTO** (a real football stadium/pitch),
graded + grounded so they sit in the scene — NOT the gpt-image edit (which re-generated the person) and NOT
the split panel. `_scene_prompt` for a theme is now a realistic photographic prompt (real green pitch, floodlit
stadium, depth of field — no people/text) instead of an abstract corporate graphic (which was producing that
random indoor-lounge background). `build_ai_scene` themed default → `_build_editorial_banner` (cut-out on
realistic bg; split-poster fallback). Verified with the real photo: person unchanged on a realistic floodlit
stadium, blended, no white wall.

## Themed images: seamless photorealistic scene (person genuinely IN the location, no cutout) (2026-07-03)
Per the user's spec — for a themed image the person should be *seamlessly photographed inside the themed
environment* (realistic perspective, shadows, reflections, depth of field, colour grading), *blended
perfectly with NO cutout or artificial look*, features preserved, cinematic/premium. So the immersive
identity-preserving AI scene (`_build_ai_portrait_banner`, gpt-image-1 edit, `input_fidelity='high'`) is the
**default again for any theme** (`build_ai_scene`: faceswap → immersive scene [theme, non-'graphic'] → split
poster). `_portrait_prompt` now embeds the seamless-integration spec verbatim (perspective/shadows/reflections/
DoF/colour-grade, no cut-out edges/halo, preserve skin tones/features/clothing/proportions, photorealistic +
cinematic). Verified with the real photo: person genuinely inside the floodlit stadium, blended, features
preserved. The 'Bold graphic poster' choice and the no-theme case still use the split-poster cut-out.
*input_fidelity preserves the face well but isn't pixel-exact — `FACESWAP_API_KEY` gives the seamless scene
with the EXACT real face.*

## The split poster now cuts the person out (transparent) + drops the pasted full-scene composite (2026-07-03)
The user liked the SPLIT design (person beside a themed panel) but (a) the person showed their white wall and
(b) a separate "full-scene composite" path was putting the cut-out on a random indoor room and looked pasted.
Both fixed:
- `_bold_split_poster` now floats a **clean CUT-OUT of the person on a dark brand gradient** (no white studio
  wall) with a soft grounding shadow when the cut is clean; falls back to the photo crop otherwise.
- `_build_editorial_banner` now **always renders the split poster** (the liked design) and no longer does the
  pasted-looking full-scene composite. `build_ai_scene` simplified to: FACESWAP → split poster → template.
- The themed panel keeps the reliable real football pitch (`_panel_theme_prompt`).
Verified with the real photo: person cut out on a brand gradient beside a real green-pitch panel — clean,
professional, on-theme, real face. (A guaranteed cut-out on every photo still benefits from `BG_REMOVAL_API_KEY`.)

## Cut-out works when hair reaches the top of the frame (2026-07-03)
Subjects with tall hair / head near the top of the photo were failing the cut-out (the wall estimate used the
whole top strip, which their hair made non-uniform → the remover bailed → the raw white-wall photo shipped in
the split poster). `_key_plain_bg` now estimates the wall from the top-LEFT + top-RIGHT CORNERS (beside the
head) instead of the full strip, so a clean studio wall is detected even with hair at the top → the person
cuts out (transparent) and floats on the themed scene. Verified no regression on the reference photos. (A
guaranteed cut-out on every photo still needs `BG_REMOVAL_API_KEY` — the free, correct key for transparent
backgrounds.)

## HARD RULE: never an AI face — always the real uploaded photo's face (2026-07-03)
Per the user: for any image, do NOT generate an AI face — only use the uploaded photo's face. The gpt-image
edit path (`_build_ai_portrait_banner`) regenerates the face (an AI face), so it's **removed from the default**
in `build_ai_scene`. New priority: **FACESWAP key (immersive AI scene + the EXACT real face swapped on) → real
cut-out composite (the actual photo) → clean framed/split design (still the real photo) → template.** The edit
path now survives ONLY inside faceswap, where the real face is swapped back on. Consequence: the fully
immersive "person in the stadium" look with a REAL face needs a `FACESWAP_API_KEY`; without it you get the real
cut-out on a themed background or a framed design — but the face is always genuinely theirs. Verified: the
default renderer is now the real-photo composite, never the AI-face edit.

## Never ship a rough cut-out — quality gate on the free keyer (2026-07-03)
Some photos still cut out messy on the free keyer (jagged edge / leftover "cream shadow" wall), and with the
relaxed `cut_ok` those messy cuts were being shipped. Added a **quality gate** at the end of `_key_plain_bg`:
it measures the cut's edge roughness (perimeter/area) and leftover bright-neutral wall inside the silhouette
(a clean cut ≈ 0.9% roughness / 0.1% wall) and **returns None if the cut is messy** (roughness > 2.4% or
wall > 1.5%) — so the caller falls back to the CLEAN framed/split design instead of a rough cut-out. Verified
the clean reference cut still passes. Net: "Bold & colourful" (and any cut-out path) now yields a clean
cut-out on good photos and a clean framed design on hard ones — never a rough one. (A guaranteed clean cut-out
on *every* photo still needs `BG_REMOVAL_API_KEY`.)

## "In the action" is now the immersive DRAMATIC scene (ChatGPT-level) (2026-07-03)
The user compared a ChatGPT poster (person standing powerfully inside an epic floodlit stadium) to our flat
cut-out-on-a-panel and asked why ours wasn't as professional. So the DEFAULT / "In the action" themed image is
the **immersive dramatic AI scene** again — the person re-posed as a HERO standing INSIDE the theme. Two
levers: (1) routing — `build_ai_scene` now runs the immersive AI scene FIRST for the scene/default path
(cut-out composite is the fallback + the "Bold graphic poster" choice); (2) the themed `_portrait_prompt` is
much more cinematic — "EPIC, packed floodlit stadium at night, roaring crowd, lens flares, glowing embers,
dramatic high-contrast rim lighting, powerful hero stance". It even re-poses a casual/sitting source photo
into a standing hero. Verified with the real photo: dramatic stadium, hero pose, clean jersey, face preserved,
legible headline — far closer to the ChatGPT reference. ("Bold graphic poster" still gives the clean cut-out
on a designed plate.)

## Cleaner cut-outs — strip the "cream shadow" wall remnant + smooth rough edges (2026-07-03)
On some photos the cut-out left a light **wall remnant behind the shoulder** (a cream "shadow") and rough,
jagged edges — because the hole-fill step re-filled a wall region enclosed behind the shoulder as if it were
the person. Fixed in `_key_plain_bg`: after the hole-fill, any **bright NEUTRAL patch that's still opaque is
stripped** (leftover light wall — it isn't warm skin, hair or dark clothes), and the edge cleanup is stronger
(MedianFilter 7 → MinFilter → MedianFilter 5 → feather) to remove the rough fringe. Verified on the real
studio photo: clean cut-out onto the graphic plate, no cream remnant, smooth edges. (A busy/non-plain
background can still leave an edge — `BG_REMOVAL_API_KEY` guarantees a perfect cut on any photo.)

## Themed images now cut the person out (transparent) onto the scene — no more white wall (2026-07-03)
The person kept showing their white studio wall (beside a themed panel) instead of being cut out and placed
IN the theme. Root cause: the `cut_ok` gate required the cut-out to be ≥42% of the ORIGINAL photo width — but
the team's studio shots are landscape, so the person is a narrow strip and every valid cut-out was rejected →
it always fell back to the white-wall split poster. Fixed: `cut_ok` now judges the cut ITSELF (real
transparency + a 30–97% opaque coverage of its tight crop), independent of the source aspect ratio. So the
free keyer's clean cut-outs are accepted, and the **default for a themed image is now a real CUT-OUT portrait
(transparent background) composited onto the themed scene** (the person on the football pitch — exact face,
real shirt). Fallback order: faceswap → cut-out composite → immersive AI scene (no white bg either) → split
poster (last resort). Themed background dropped to `quality='medium'` to trim latency. Verified with the real
Nishant photo: cut out cleanly onto the pitch. *Note:* the free keyer handles plain studio walls; a busy/non-
plain background still needs `BG_REMOVAL_API_KEY` for a guaranteed cut.

## Campaigns now ASK "what kind of image?" before generating (2026-07-03)
Featuring a teammate in a campaign (e.g. "@Pooja" or "create an image of @Pooja") now first asks the image
TYPE with tappable chips — **In the action — themed scene** (immersive: the person inside the themed scene,
on the pitch/in the stadium), **Bold graphic poster** (the designed split poster), or **Surprise me** — and
generates the chosen type. Chat/Create keep the existing style palette. Wired end-to-end: `_EMP_TYPE_CHIPS` +
`_type_to_design` route the choice through `_feature_and_emit` → `exec_feature_employee(design=…)` →
`_build_one` → `build_ai_scene(prefer=…)` (`prefer='graphic'` skips the ~50s immersive edit and goes straight
to the fast split poster). A bare mention asks; a mention that already gives direction still generates
straight away.

## Immersive AI scene is the default again — person INSIDE the theme (ChatGPT-style) (2026-07-03)
The user shared a ChatGPT image (the person standing in a floodlit stadium, in a jersey, on the pitch — real
face) vs our split poster (person on their white studio wall beside a themed panel) and asked why it always
uses the white background. So the **gpt-image-1 image-EDIT path is the default again** — it places the SAME
person INSIDE the themed scene (`input_fidelity='high'`, quality medium), giving a full immersive result with
no white background. Priority: FACESWAP key → **immersive AI edit (default)** → real cut-out / split poster
(fallback if the edit is unavailable) → template.
- **Immersive themed prompt.** `_portrait_prompt` now places them ON LOCATION (football → on the green pitch
  in a floodlit stadium, in a clean navy football jersey), a cinematic sports photograph — not a studio/white
  backdrop.
- **No ghost text, no garbled shirt.** Stopped feeding the headline into the edit prompt (gpt-image was
  painting it as ghost text in the scene — the caption is overlaid separately), and the wardrobe clause forbids
  any text/logo on the clothing (which was rendering as garbled text).
- **Variety by design.** Each generation is a fresh stochastic scene/pose, so every image differs.
- *Trade-offs:* the edit is slower (~40–90s) and the face is preserved by input_fidelity (very close, but an AI
  regen — not pixel-exact; a `FACESWAP_API_KEY` gives exact). If the edit endpoint is unavailable on the
  account, it falls back to the split poster automatically.

## Realistic themed panel (green football pitch) + more campaign variety (2026-07-03)
- **The themed panel now looks real.** It was forced "navy-dominant" (for text legibility) so a football pitch
  came out dark/navy with no green. Now `_panel_theme_prompt` asks for the scene in its NATURAL colours (a
  football theme → a lush GREEN pitch, white lines, a real black-and-white ball, goal net, floodlit stadium),
  rendered at `quality='medium'`, and the scrim darkens ONLY the top third (near-black, not navy) so the
  headline stays readable while the rest keeps its true colour. Verified: green pitch + proper ball, both
  panel sides.
- **Campaign generic images vary too.** `images.build_images` was rendering people-variations with a fixed
  `variant=i` (so count-1 was always variant 0 → same design). Now it uses a random variant, so every campaign
  image differs (on top of the split-poster side/colour/seam/accent rotation shipped in e28896d).

## Different design every time + "change the design" works (2026-07-03)
Employee posts looked the same each time (studio photos always fail the cut-out → always the one split
poster, with only a subtle shade change), and typing "change the design" errored. Fixed both:
- **Genuine variety in the split poster.** `_bold_split_poster` now rotates by `variant`: the panel/photo
  **side flips** (mirror — text left vs right), plus the **colour scheme, seam style (ribbon/bar/double-rule)
  and accent (ring/dots/chevrons/squiggle)** all rotate. Consecutive generations (random variant) now look
  clearly different — verified across all 6 variants with no text collisions.
- **"Change the design" (regenerate) now works for uploaded employees.** `refine.regenerate_asset` looked for
  the photo only in the ZIP Team library, so employees added via **Folders** (an `employee_id` asset) weren't
  found → it returned an error. It now loads the photo from the **Employee record**, re-runs the **current
  engine** (`build_ai_scene`) with a fresh random design, preserves the campaign **theme** and name
  suppression, and — for a "change the design / different style" instruction — keeps the original copy and just
  re-rolls the design (rather than turning "change the design" into the headline).

## Regenerate button on replies (2026-07-03)
Added a **Regenerate** button (the curved-arrow icon) to the reply action row in `ReplyActions`, next to the
existing thumbs/copy/download. Clicking it **re-runs the same prompt** for a fresh result (finds the nearest
preceding user message and re-submits it). Wired in the main **Chat** and the **internal Campaign** chat; it's
hidden when there's no prior prompt and disabled (with a spinning icon) while a turn is in flight.

## Fix: 502 on image generation (out-of-memory on the 2 GB droplet) (2026-07-03)
Generating an employee image could return a **502** — the process was OOM-killed mid-request. Employee
uploads are 5000px+ (~5 MB), and `_enhance_photo` + the numpy `_cutout` ran on the FULL-resolution image
(~60 MB arrays × several copies), which spikes past the shared 2 GB droplet's memory. Fix: cap the working
image size with `thumbnail((1800, 1800))` BEFORE the enhance/cut-out in both `build_ai_scene` and
`build_team_image`. The output is 1080px, so there's no quality loss (verified) — and it's a touch faster.

## Split-poster panel now shows the campaign THEME (free, real face) (2026-07-03)
The bold split poster kept the real face but its panel was a flat brand colour — so a "football" campaign
didn't look like football. Now, when a theme is set, the panel background is a **themed graphic** (a
gpt-image football pitch / ball / goal-net — no people, no text, navy-dominant) generated behind the
oversized caption, beside the person's real photo crop. So the poster visibly reflects the campaign AND keeps
the exact real face — no cut-out or API key needed. `_panel_theme_prompt` + async `_bold_split_poster(theme)`;
a navy scrim fades top→down so the headline stays legible while the theme shows lower. One low-quality panel
call (~15s); no theme (or provider down) → the instant flat brand panel.

## Bold magazine-poster design when there's no clean cut-out (free, no key) (2026-07-03)
Previously, when the free keyer couldn't cut a person off their background, the image fell back to a plain
full photo + a scrim + headline — clean but flat. That fallback is now a **bold designed magazine SPLIT
poster** (`_bold_split_poster`): a solid brand-colour panel with oversized type + red keyword box + kicker +
wordmark + accents (angled coral seam ribbon, ring, squiggle), beside a **tight portrait crop of the real
photo**. The face + clothing are exactly theirs (just a crop, nothing redrawn), every graphic sits in a safe
zone (never over the subject or text, verified by `_ensure_clear`), and it's **instant (~3–5s)** because a
failed cut-out no longer triggers a wasted gpt-image scene call — the banner also now cuts out FIRST and only
generates a themed scene when it can actually composite the person onto it.

## Employee images keep the REAL face again (no AI face-swap drift, no garbled shirt text) (2026-07-03)
The gpt-image image-EDIT default (added for "strict facial consistency") turned out to REGENERATE the face
(it drifted to a different person) and hallucinated garbage text on the person's shirt. Reverted the default:
- `build_ai_scene` priority is now: **FACESWAP key → real cut-out composite (DEFAULT) → deterministic
  template.** The default composites the person's ACTUAL photo, so the face + clothing are exactly theirs —
  never redrawn, no invented text. The drifting image-EDIT path is no longer used except *inside* faceswap
  (where the real face is swapped back on).
- **Known limit (needs a key):** the free, code-only background remover can't reliably cut a person off a
  plain studio wall, so when it can't, the image falls back to the person on their ORIGINAL background
  (no themed scene). A **themed scene + the real face** requires one small API key — `BG_REMOVAL_API_KEY`
  (remove.bg → clean cut-out onto a themed background) or `FACESWAP_API_KEY` (Replicate → an immersive AI
  scene with the real face swapped on). Both are already wired; unset → the clean real-photo spotlight above.

## Campaign images: themed by campaign NAME, faster, clearer wait (2026-07-03)
Two fixes for "campaign image generation doesn't use the theme / seems not to generate":
- **Themed by the campaign NAME, not just the brief.** The image theme is now `campaign name + brief`, so a
  campaign called "Football Campaign" with an empty brief is still themed by its name (football). Both the
  employee-feature path and the generic campaign-image planner use it (`_campaign_theme` in `tools.py`).
- **Stop re-attempting a dead edit endpoint.** If this account's OpenAI plan can't do `/images/edits` (e.g.
  only gpt-image-2, which 400s on edits), we now trip a process flag after the first proven failure and
  **fast-fail every later attempt** instead of paying the doomed round-trip per image — the employee image
  falls straight to the real-cutout composite (exact real face, themed). Resets on any successful edit.
- **Clearer expectation.** The "working" status now says *"…this can take up to a minute"* so a genuine
  ~40–60s AI render (the model's own latency — unavoidable for a themed photographic image) doesn't read as
  broken. Employee AI edits also drop to `quality='medium'` (identity is held by `input_fidelity`, not
  quality) to trim latency where the endpoint is available.

## Campaign work continues when you switch tabs (2026-07-02)
Starting a generation in a campaign and then switching to another campaign/section no longer *looks* like it
stopped — and now reliably shows the result when you come back:
- The backend already keeps generating and **saves the asset even if you navigate away** (the SSE turn runs
  detached; assets are committed to the DB immediately and the assistant reply is persisted when the turn
  ends). We now **don't tear that down** on view unmount.
- A generation in progress is tracked in a **module-level registry** (`_generatingCampaigns`) that survives
  the campaign view unmounting. When you **return to that campaign while it's still generating**, it shows a
  "Still generating — this kept running while you were away…" status and **polls the saved thread** until the
  reply + asset cards land, then renders them and refreshes the gallery. If it already finished while you were
  away, the normal thread restore shows it immediately.

## Strict facial consistency is now the app-wide standard for face images (2026-07-02)
The user's directive — *"prioritize the facial feature from the provided reference image … maintain the
subject's identity accurately while only adapting the pose, lighting, and surrounding. Do not alter their
facial structure."* — is now the single canonical rule for every image path that edits a real face:
- Centralized as **`STRICT_FACE_DIRECTIVE`** in `teampost.py` (one source of truth) and injected into every
  person-editing prompt (`_portrait_prompt`, `_phone_portrait_prompt`) — which run through gpt-image-1's
  `/images/edits` with `input_fidelity='high'`.
- Documented verbatim in **`docs/IMAGE-GENERATION.md`** (with the rule that any new face-editing path must
  reuse the constant), and saved to the assistant's memory.

## Fix: "View" tooltip no longer covers the image (2026-07-02)
Hovering a generated image popped a native **"View" tooltip right over the picture** (the whole image is a
click-to-open button that carried `title="View"`). Removed the `title` from the full-image and full-video
wrapper buttons in `AssetCard` — the `aria-label` stays for screen readers, and the image is still
click-to-zoom. Nothing overlays the artwork now. (The small eye-icon button in the card footer keeps its
tooltip — it sits below the image, not over it.)

## Campaign images: on-theme, real employee faces, no name labels (2026-07-02)
Two fixes for the **internal campaign** image flow, so generated images match the campaign and show YOUR team:
- **Employee images now follow the campaign theme.** When you feature a teammate inside a campaign, the
  campaign brief becomes the scene: the person is re-posed/re-lit into an environment that reflects the
  theme (a Football campaign → on a pitch in sporty kit; a Diwali campaign → festive decor), with wardrobe to
  match — instead of the old fixed office/studio "look". The face stays locked to their real photo (only
  pose/lighting/surroundings change). Threaded via a new `theme` arg through `build_ai_scene` →
  `_portrait_prompt` / `_scene_prompt` and `exec_feature_employee` (reads `state["campaign_brief"]`).
- **No random AI faces in campaign scenes — real employees instead.** The generic campaign image planner now
  flags which variations depict people (`has_people`), and for those the app swaps in a REAL employee
  (rotating through your roster) placed in the campaign-themed scene — never an invented face. Object/scenery/
  data images stay AI-generated. Wired through `images.build_images(team_photos=…, theme=…)` +
  `exec_generate_image` (campaign mode only; Chat/Create keep generic scenes).
- **No names on campaign images.** The on-image "Featuring [Name]" label and role badge are suppressed for
  every campaign image (single feature, grid, and generic scenes) — the caption/headline and wordmark remain.
  (Chat/Create posts still show the name.)

## Strict facial-consistency mode is now the default for employee AI images (2026-07-02)
Employee-featured images now regenerate the **pose, lighting and surroundings** with AI while locking the
**face to the reference photo** — the strongest identity preservation the image API offers:
- **New default = identity-locked AI edit.** `build_ai_scene` now routes to the gpt-image-1 image-EDIT
  endpoint with `input_fidelity='high'`, which re-poses/re-lights/re-stages the *same* person (blazer + a
  rotating premium environment: office / studio / golden-hour / bold-brand / rooftop, 8 looks) instead of
  pasting the flat cut-out onto a designed background. The real cut-out composite is now the *fallback* if the
  edit fails or is refused, so the face is always still theirs.
- **Stronger prompt lock.** The portrait prompts now instruct the model to treat the reference photo as the
  single source of truth for the face and preserve **every** facial feature exactly (bone structure, face
  shape, jaw, nose, lips, eyes, eyebrows, skin tone, hair, facial hair, age, gender) — adapting **only** pose,
  lighting and surroundings, and never slimming, reshaping, smoothing or beautifying the face.
- **Priority order:** FACESWAP key (pixel-exact real face) → identity-locked AI edit (new default) → real
  cut-out composite → deterministic template. Adding a `FACESWAP_API_KEY` still gives the strongest guarantee.
- *Note:* `input_fidelity='high'` is a very strong lock but is still an AI regeneration, so the face can drift
  slightly on some photos. For a pixel-exact face on the AI scene, add a Replicate `FACESWAP_API_KEY`.

## Cleaner cut-outs — no more "white shadow" behind the person (2026-07-02)
Fixed the leftover light-wall patch (the "white shadow" behind a shoulder) and rough edges in the free
background keyer:
- **Removes leftover light wall + cast shadow** by keying on low *saturation* (the wall and shadow are
  neutral greys/whites; skin is warm and hair/dark clothes are dark), so it strips the wall without eating
  the face — the earlier attempt keyed by colour-distance and punched holes in light skin.
- **Fills interior holes** (eye-whites, printed shirt text) via a border flood-fill, so no stray background
  colour shows through the person.
- Verified on a navy-tee-on-light-wall studio headshot (the Talentrupt photo style): clean cut-out, no wall
  remnant, face intact, and the composited banner looks professional.
- *Note:* the free keyer handles the team's studio photos well but a busy/gradient or warm-tinted wall (or
  light-coloured clothing) can still leave a small edge — the **remove.bg** key (already wired) guarantees a
  clean cut-out on any photo.

## Employee posts now ask "what style?" first (2026-07-02)
- **`@mention` a teammate → it asks the style before generating.** A bare mention (e.g. "create an image of
  @Vaishnav") now replies with a friendly question + tappable chips — **Bold & colourful / Clean & minimal /
  Photographic scene / Warm & editorial / Surprise me** — and generates the matching design when you pick one
  (the choice maps to the design variant). A mention that already gives a direction still generates straight
  away, and the deterministic real-photo routing is unchanged. (Chat/Create only; campaigns keep auto-generating.)
- **Fixed: the main Chat never rendered intake chips.** The "what kind of image?" quick-picks (this new one
  AND the existing create-brief) only showed in the Campaign studio — the main Chat showed the question with
  no tappable options. Chat now renders them.

## Employee banners: less "fake", genuinely different designs (2026-07-02)
- **Killed the fake look.** Removed the bright "focal-pocket" glow (the white cloud behind the person),
  softened the rim light to a whisper, and tightened the cut-out edge (an extra 1px erode) so there's no
  pasted-on halo. Colour-grading now only tone-matches a *photographic* backdrop (never tints the person on
  a flat colour block).
- **Fixed the cut-out for tight portraits.** The free background keyer estimated the wall from all four
  borders — which fails when the person fills the frame and touches the bottom/side edges (it was silently
  falling back to a full-photo layout, making every post look the same). It now reads the wall from the TOP
  strip (above the head) and only flood-fills from wall-coloured points — clean cut-outs on real headshots.
- **Six distinct designs now rotate** (was effectively one): bold flat-graphic posters — deep navy, coral +
  navy disc, warm cream/gold, coral disc, cream + navy arc, diagonal split — plus an occasional photographic
  scene, across three layouts with rotating kicker labels. Each post looks different, and the flat-graphic
  posters read as *designed* (not a fake composite) — and they're instant (no image-model call, so faster).
- **Chat + Campaign studio** now show a **Stop** button (red square) in place of Send while the assistant is
  working. Clicking it **aborts the in-flight turn** (cancels the stream via `AbortController`), clears the
  busy/typing state, and keeps whatever was already produced (or drops the empty pending bubble). Added
  `stop()` to the chat store (`ChatProvider`) and an equivalent in the Campaign studio chat (its own store),
  which now also passes an abort signal into `streamChat`.

## Premium editorial employee banners — the real person, integrated (not framed) (2026-07-02)
Reworked the default featured-employee banner (real face preserved) so the person **blends into the
artwork** instead of sitting in a photo frame. Designed by a multi-agent senior graphics/compositing team.
- **No more framed card.** The real cut-out is composited INTO a gpt-image editorial scene and made to look
  photographed there, via an 8-stage integration pipeline (`_place_editorial_person`): a soft focal-pocket
  bloom behind the subject, a colour-grade/tone-match that pulls the cut-out's white balance to the plate,
  edge feather + despill, a grounded contact shadow + a soft navy cast shadow, a directional rim/edge light,
  and shared film grain over the whole frame. The person is graded, grounded and lit into the scene.
- **Free clean cut-outs on the droplet.** Added a numpy + flood-fill **plain-studio-background keyer**
  (`_key_plain_bg`) — the team's photos are studio shots on a plain wall, so it removes the background
  (incl. the cast wall-shadow) with NO paid service; it also handles remove.bg / rembg when available.
- **Modern editorial layouts, rotating.** Three dynamic compositions rotate: masthead hero-right, off-centre
  big-crop (head bleeds off the top), and hero-left mirror — oversized editorial type, kicker, script
  "Featuring [Name]". All text stays provably clear of the subject (`_ensure_clear`).
- **Face + architecture preserved.** The employee's real face is never AI-changed; the same
  `build_ai_scene` entry/workflow is used. The face-swap upgrade path is unchanged.

## Default employee look = the polished AI blazer portrait (2026-07-02)
Per the user's call, the default featured-employee post is now the **polished AI portrait** (blazer + a
varied scene — office / studio / golden-hour / bold-brand / rooftop, 8 looks) that gpt-image produces
(`_build_ai_portrait_banner` → `team_ai_portrait`). Trade-off (accepted): this is a full AI edit, so the
**face is AI-generated** (a close likeness, not the exact real face). If a `FACESWAP_API_KEY` is set, the
same look is produced but the person's **real face is swapped on** — so adding the key later restores the
exact face with no other change. If the image provider is down, it falls back to the real-photo composite,
then a deterministic template — a post never breaks.

## Face-swap: the AI-blazer look WITH the exact real face (opt-in) (2026-07-02)
The best of both — the polished AI portrait (blazer, varied scene) **and** the person's exact real face —
now possible via an opt-in hosted face-swap step. A single AI pass can't do both (editing the clothes
repaints the face), so: gpt-image makes the AI portrait, then a face-swap API pastes the person's REAL face
onto it (body/clothes/background stay AI, the face is theirs).
- **New `generation/faceswap.py`** (async, gated by `FACESWAP_API_KEY` — a Replicate token). New
  `_build_faceswap_banner` in `teampost.py`; `build_ai_scene` uses it when a key is set.
- **Safe fallback:** with no key (default), or if the swap fails, employee posts stay on the current
  real-photo composite (exact face, real clothes) — nothing breaks. Heavy insightface/onnxruntime stays OFF
  the droplet.
- **To enable:** create a Replicate account, add `FACESWAP_API_KEY` (your Replicate token) as a GitHub
  Actions secret, redeploy. The deploy injects it (+ `FACESWAP_PROVIDER=replicate`,
  `FACESWAP_MODEL=cdingram/face-swap`) into the droplet `.env`. Small per-image cost (~a few cents).

## The employee's REAL face is never changed again — only the design varies (2026-07-02)
The AI image-to-image path was **repainting the whole person, including the face** — so a featured
employee came out looking like a *different person*. Reverted: we now keep the **real photo** (face and
all) and only change the design around them.
- **Face never AI-regenerated.** Both employee designs now composite the person's ACTUAL photo:
  **Design A** — the real photo inside the portrait iPhone frame (skin colours rotate); **Design B** — the
  real person on a **varied AI-generated background** (gpt-image makes the scene only — no people — and the
  real cut-out / framed photo goes on top). This is "change the background, colours, theme, fonts — but
  never the face."
- **Cleaner AI backgrounds.** The background prompt no longer feeds the headline text into gpt-image (it was
  causing faint ghost-text in the scene) and now bans text/numbers/signage outright.
- *Trade-off:* keeping the exact real face means keeping the real photo's clothes too (no AI blazer) — an
  AI blazer required repainting the person, which changed the face. For a clean cut-out of the person on the
  AI background (vs. a framed card), enable the `BG_REMOVAL_API_KEY` (remove.bg) secret.

## Employee portraits now wear a sharp blazer + lean to the full-scene look (2026-07-02)
- **Consistent professional blazer.** Featured-employee portraits now always dress the person in a sharp,
  well-fitted business blazer (navy/charcoal over a crisp shirt) — a premium corporate-headshot look — in
  BOTH design families, instead of a mix of t-shirts / smart-casual. (Identity still locked; the setting,
  background and pose keep varying.)
- **More of the full-scene portrait.** The rotation now favours the full-scene professional portrait
  (the reference the user liked) ~2/3 of the time, with the iPhone-frame design ~1/3 for variety.

## Attachment clears on send · in-app image preview · varied employee designs (2026-07-02)
- **The attached file leaves the composer the moment you hit send.** It used to linger in the input box
  during generation (an image was kept "staged"); now it's snapshotted onto your message and the composer
  clears immediately — in both the main Chat and the Campaign studio.
- **Tapping an image in a message opens it in-app, not a new browser tab.** Attachment thumbnails now open
  a same-tab lightbox (click-outside / Esc to close), matching every other image preview in the app
  (new shared `ImageLightbox`).
- **Employee posts stop looking identical.** Featuring a teammate no longer always produces the same
  iPhone-frame design. It now **rotates two distinct design families**, both AI-generating only the
  employee's identity-locked portrait: **(A)** the clean portrait iPhone frame, and **(B)** a full-scene
  portrait where the person is re-rendered into a varied premium environment (office / studio / golden-hour
  / bold-brand / rooftop / …, 8 looks). With skins and environments rotating inside each, consecutive posts
  look different — like the variety the non-employee image generator already produces.

## Employee banners: the photo now sits in a clean PORTRAIT iPhone frame (2026-07-02)
The default employee/`@mention` post is now a premium **portrait phone-mockup** banner, designed by a
multi-agent "senior graphics team" (4 designers → art-director synthesis).
- **The portrait iPhone frame.** The employee's identity-locked professional portrait sits inside a clean
  phone mockup on the right — titanium rail, charcoal bezel, a real dynamic-island notch, soft floating drop
  shadow and a glass-edge highlight — with the branded caption (wordmark, red-box keyword headline, subline,
  script "Featuring [Name]" + role badge) in a reserved LEFT column. It reads as a real iPhone on every skin.
- **The photo inside is a clean, professional portrait.** The person's REAL photo is re-rendered (img2img,
  `input_fidelity=high`, identity-locked) into a centered, well-lit studio portrait for the screen; if that's
  unavailable it falls back to the enhanced real photo — either way the mockup carries the polish.
- **Nothing overrides.** The device and the text column are separated by a provable 64px gutter and validated
  by `_ensure_clear` (mutually-disjoint bounding boxes) — a hard "nothing overlaps" guarantee. Verified across
  the light / cream / navy / red skins.
- **Rotates skins** (not navy every time); the special occasion series (welcome / anniversary / team grid)
  still fire on their own keywords.

## Campaign attachments show in chat + @mention wins over an attached reference (2026-07-02)
- **Attachments now show in the CAMPAIGN studio chat too.** The earlier "attachment shows next to your
  message" fix only covered the main Chat; the campaign studio (`CampaignsView`) had its own chat that still
  dropped the attachment. Same fix applied there — an attached image shows a thumbnail (a file shows a chip)
  right next to your message.
- **`@mention` of a known teammate now wins over an attached image (fixes the "it did something totally
  different" hallucination).** Before: if you attached a *design screenshot* and wrote "make it in the same
  design, but with @Pooja", the app fed the SCREENSHOT (a multi-person graphic) into the identity-locked
  AI-portrait edit, which then **invented random people**. Now a named, known Folders employee is always the
  SUBJECT — their REAL stored photo is used, and any attached image is treated as a reference, not the
  person. Escape hatches preserved: saying "use this photo" or @-naming someone NOT in Folders still
  features the uploaded photo. *(Note: this features the real teammate in a fresh professional design — it
  does not yet pixel-replicate the attached design; ask if you want reference-design matching.)*
- **AI portrait can't invent extra faces.** The portrait prompt now hard-requires EXACTLY ONE person (no
  added/duplicated/hallucinated people) and, if the source is a graphic or has multiple people, to focus on
  the single main subject — a second guard against the multi-person hallucination.

## AI portraits from a real photo + attachment display + Folders photo preview (2026-07-01)
Four things: employee posts now vary for real, attachments show in chat, and Folders photos open.
- **True image-to-image "AI portraits" (biggest change).** Employee/`@mention` posts no longer paste the
  same cut-out onto a background every time. The person's REAL photo is now fed into gpt-image-1's EDIT
  endpoint with `input_fidelity: high`, so the model **re-renders the SAME person** (identity locked — same
  face/features/skin/hair) into a genuinely different premium scene each time: new **pose, lighting,
  background and even wardrobe**. Eight rotating art-directions (bright office, studio, golden-hour, bold
  brand, rooftop, cream-geometric, tech, co-working) mean consecutive posts look different, not identical.
  Verified end-to-end (`teampost.build_ai_scene` → `_ai_portrait_canvas` → `llm.generate_image_edit`).
  *Note on identity:* an AI edit preserves LIKENESS but is not pixel-identical to the original photo. If
  the edit is refused or the provider is down, it falls back to the safe real cut-out composite, then to a
  deterministic template — so a post is never broken.
- **Attachments now show in the chat.** When you attach a file with a prompt, the transcript shows the file
  next to your message — a real thumbnail for an image, a labelled chip for a PDF/text file (it was already
  being read by the backend; now it's visible too). Click an image thumbnail to open it.
- **Post-generation options are look-aware.** After an employee post, the one-tap refine chips now offer
  *"Try a different look", "More formal", "Different background", "Bright office", "Clean studio",
  "Outdoor/rooftop", "Bolder brand colours"* — each re-runs the AI portrait with a new look (same face) so
  you can quickly get a different image if you don't like the first.
- **Folders: click a photo to view it full-size.** Employee photos in the Folders library open in an in-app
  lightbox (with Download + Close, click-outside and Esc to dismiss) — matching the app's existing preview.

## Professional employee posts — auto-enhance + designed scene + prod cut-outs (2026-07-01)
Made employee posts look ChatGPT-grade professional while keeping the real face exactly as-is.
- **Auto-enhance (identity unchanged).** Every employee photo is now cleaned before compositing —
  `_enhance_photo` runs a gentle auto-contrast + brightness/colour/contrast/sharpness pass (pixel-level
  only; the face is never redrawn or altered). The person just looks crisp and well-lit on any skin.
- **Designed scene, not a flat panel.** New `_pro_scene` builds a premium backdrop — a soft brand-colour
  confetti burst (`_confetti`) + a dot-grid accent in the reserved zones — and `_place_person` now floats
  the person on a subtle navy halo so a cut-out reads as intentional design (matching the reference look).
  Long names / roles / taglines auto-shrink to fit (`_fit_font`) so nothing ever overflows the person.
- **Real cut-outs now activate on prod.** The deploy wires an optional `BG_REMOVAL_API_KEY`
  (+ `BG_REMOVAL_PROVIDER`) GitHub secret straight into the droplet's `.env` (same encrypted-secret path
  as the OpenAI key, CRLF-safe, re-exported before `pm2 restart` so `--update-env` can't blank it). Set the
  secret → the real person is cut out (background removed via remove.bg / Photoroom, **face untouched**) and
  floated on the designed scene. Unset → the premium framed-card fallback (double frame + red corner tab).
  Still no heavy `rembg`/`onnxruntime` on the 2GB droplet.
- **Verified across the rotation.** Rendered spotlight_series / welcome / anniversary on light / cream /
  navy / red — all premium and legible, **0 overlaps** (`_ensure_clear` never triggered).

## Split the input palette: `/` to create, `@` for teammates (2026-07-01)
- The chat/campaign input palette now has **two focused triggers** (Slack/Notion style): typing **`/`**
  surfaces only the **create actions** (Create image / deck / PDF / post / find prospects), and **`@`**
  surfaces only **teammates** from the Folders library. `@` no longer lists create actions and `/` no
  longer lists people. Selecting inserts the right text (the pick derives its trigger from the current
  text, so it can't replace the wrong token). Placeholders updated to "type / to create, @ for teammates".

## Merge Create into Chat + remove Brand-kit UI (2026-07-01)
- **One section: Chat.** The Create section is merged into **Chat**, which now handles everything — chat,
  Q&A, prospecting, AND image/deck/PDF generation (it already had all the generation tools). "Create" is
  removed from the top nav; `/create` redirects to Chat.
- **"Your generations" moved into Chat.** A top toggle **Chat / Your generations** — the generations tab
  is the gallery of everything created (images/decks/PDFs) with All/Images/Decks/Documents filters and
  regenerate / refine / delete (new self-contained `GenerationsGallery.tsx`; `CreateView.tsx` retired).
- **Brand kit removed from the frontend.** The Brand-kit tab/panel is gone from the UI; brand assets +
  grounding stay managed in the **backend** only (as requested).

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
