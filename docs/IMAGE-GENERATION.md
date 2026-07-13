# Image generation — Strict Facial Consistency (canonical directive)

**This directive governs EVERY image generation in the application that uses a real person's reference
photo.** It is the user's standing rule. Save it verbatim; apply it everywhere a real face is
edited/re-rendered.

## The directive (verbatim)

> Enable strict facial consistency mode, prioritize the facial feature from the provided reference image for
> all the subsequent generation, maintain the subject's identity accurately while only adapting the pose,
> lighting, and surrounding. Do not alter their any facial structure.

## Where it lives in the code

- **Single source of truth:** `STRICT_FACE_DIRECTIVE` in
  [`backend/app/generation/teampost.py`](../backend/app/generation/teampost.py). This constant is the
  enforced expansion of the directive above.
- **Applied in every person-editing prompt:**
  - `_portrait_prompt(...)` — the default employee AI scene (gpt-image-1 `/images/edits`,
    `input_fidelity='high'`).
  - `_phone_portrait_prompt(...)` — the phone-frame portrait edit.
  - Both run through `generate_image_edit(..., input_fidelity='high', mime='image/png')` in
    [`backend/app/providers/llm.py`](../backend/app/providers/llm.py), the strongest identity lock the image
    API offers.
- **Routing:** `build_ai_scene(...)` is the chokepoint for featured-person images (Chat, Create, and
  campaigns, including the campaign real-employee substitution in `images.build_images`). Priority:
  1. FACESWAP key set → pixel-exact real face swapped onto the AI scene (`_build_faceswap_banner`).
  2. Identity-locked AI edit → **default** (`_build_ai_portrait_banner`, uses `STRICT_FACE_DIRECTIVE`).
  3. Real cut-out composite → fallback (the face is literally their photo).
  4. Deterministic template → never-broken final fallback.

## Rule for future work

Any NEW image path that edits or re-renders a real person's face **MUST** import and prepend
`STRICT_FACE_DIRECTIVE`. Do not duplicate the wording inline — reference the constant so there is one
canonical copy. Backgrounds/scenes with **no** person (`_scene_prompt`, generic non-people campaign images)
do not need it (there is no face to preserve).

## Honest limitation

`input_fidelity='high'` is the strongest identity preservation the image API provides, but it is still an AI
regeneration and can drift slightly on some photos. For a pixel-exact face, set a Replicate `FACESWAP_API_KEY`
(it takes priority automatically).
