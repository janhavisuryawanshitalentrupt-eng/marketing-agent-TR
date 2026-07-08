"""Shared DESIGN-VARIETY system — makes the app behave like an in-house graphic designer.

Every Chat post and every Magazine picks a DesignProfile (a coherent palette + typography + layout
signature + decorative motif) and rotates so consecutive pieces for the same owner never repeat — the
output looks designed, not machine-stamped. Consumed by BOTH `chatpost.py` (surface="post") and
`magazine.py` (surface="magazine"); imports nothing from them (no cycles). `teampost.py`/`decks.py`
keep their own variety systems.

Brand rules are inviolable and live OUTSIDE this module: real photos as-is (never AI faces), no
fabricated stats, the app draws all text with Pillow, the wordmark is always present. A profile only
decides how the brand-safe chrome LOOKS — never what it SAYS.
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

# Brand anchor colours (kept local so this module depends on nothing).
NAVY = (0x0B, 0x35, 0x59)
NAVY2 = (0x12, 0x44, 0x6E)
RED = (0xF6, 0x40, 0x4C)
RED2 = (0xD2, 0x2A, 0x35)
CREAM = (0xEB, 0xE9, 0xDF)
WHITE = (0xFF, 0xFF, 0xFF)
INK = (0x14, 0x22, 0x3A)          # near-navy body ink on light backgrounds
SUBINK = (0x51, 0x60, 0x74)       # muted grey-navy subline on light
WARMWHITE = (0xF7, 0xF5, 0xEF)
SAND = (0xE2, 0xDC, 0xCE)
WARMGREY = (0xC4, 0xBC, 0xAA)
ICE = (0x9E, 0xC6, 0xEC)          # light-blue subline on dark
GOLD = (0xF5, 0xC0, 0x42)
MIDNIGHT = (0x07, 0x16, 0x26)     # near-black navy
MIDNIGHT2 = (0x0D, 0x29, 0x42)


@dataclass(frozen=True)
class DesignProfile:
    key: str
    name: str
    # -- palette roles --
    bg: tuple = NAVY
    bg_alt: tuple = NAVY2
    ink: tuple = WHITE
    sub: tuple = CREAM
    accent: tuple = RED
    accent2: tuple = WHITE
    on_accent: tuple = WHITE
    card_bg: tuple = NAVY2
    card_ink: tuple = WHITE
    dark: bool = True                 # True -> white wordmark + dark-bg logic
    # -- typography (families resolved by common.font) --
    head_family: str = "sans"         # sans | serif | display
    body_family: str = "sans_light"
    head_scale: float = 1.0           # multiply headline size (soft_neutral breathes at 0.9)
    # -- layout signature --
    align: str = "left"               # left | center
    kicker_style: str = "pill"        # pill | band | rule | plain
    divider: str = "bar"              # bar | dots | double_rule | none
    motif: str = "diag_circle"        # diag_circle | dot_grid | arcs | facets | hairline_frame
    hero_photo_side: str = "right"    # right | left
    # -- optional colour overrides (fall back to accent) --
    divider_color: tuple | None = None
    disc_color: tuple | None = None   # accent disc/panel behind a hero person
    # -- magazine-specific --
    rail: str = "left_red"            # left_red | left_navy | thin_navy | top_bottom_rules | none
    cover_style: str = "framed_right"  # framed_right | framed_left | split_panel | band_bottom
    page_bg: tuple = CREAM            # inner magazine page fill (ALWAYS light for legibility)

    @property
    def divider_col(self) -> tuple:
        return self.divider_color if self.divider_color is not None else self.accent

    @property
    def disc_col(self) -> tuple:
        return self.disc_color if self.disc_color is not None else self.accent


# --------------------------------------------------------------------------------------------------
# The six profiles. #1 reproduces today's look (nothing regresses); #2-6 add real variety across the
# four axes the user asked for: colour theme, layout/composition, typography, decorative motif.
# --------------------------------------------------------------------------------------------------
PROFILES: dict[str, DesignProfile] = {
    "classic_navy": DesignProfile(
        key="classic_navy", name="Classic Navy",
        bg=NAVY, bg_alt=NAVY2, ink=WHITE, sub=CREAM, accent=RED, accent2=WHITE, on_accent=WHITE,
        card_bg=NAVY2, card_ink=WHITE, dark=True,
        head_family="sans", body_family="sans_light",
        align="left", kicker_style="pill", divider="bar", motif="diag_circle", hero_photo_side="right",
        rail="left_red", cover_style="framed_right", page_bg=CREAM,
    ),
    "editorial_cream": DesignProfile(
        key="editorial_cream", name="Editorial Cream",
        bg=CREAM, bg_alt=(0xDD, 0xD8, 0xC8), ink=NAVY, sub=SUBINK, accent=RED, accent2=NAVY, on_accent=WHITE,
        card_bg=WHITE, card_ink=NAVY, dark=False,
        head_family="serif", body_family="sans_light",
        align="left", kicker_style="rule", divider="double_rule", motif="hairline_frame",
        hero_photo_side="left",
        rail="top_bottom_rules", cover_style="framed_left", page_bg=WARMWHITE,
    ),
    "bold_red": DesignProfile(
        key="bold_red", name="Bold Red",
        bg=RED, bg_alt=RED2, ink=WHITE, sub=CREAM, accent=NAVY, accent2=CREAM, on_accent=WHITE,
        card_bg=NAVY, card_ink=WHITE, dark=True,
        head_family="display", body_family="sans_light",
        align="left", kicker_style="band", divider="bar", motif="dot_grid", hero_photo_side="right",
        disc_color=NAVY,
        rail="left_navy", cover_style="band_bottom", page_bg=CREAM,
    ),
    "split_duotone": DesignProfile(
        key="split_duotone", name="Split Duotone",
        bg=NAVY, bg_alt=CREAM, ink=WHITE, sub=ICE, accent=RED, accent2=NAVY, on_accent=WHITE,
        card_bg=WHITE, card_ink=NAVY, dark=True,
        head_family="sans", body_family="sans_light",
        align="left", kicker_style="pill", divider="bar", motif="arcs", hero_photo_side="right",
        rail="none", cover_style="split_panel", page_bg=CREAM,
    ),
    "soft_neutral": DesignProfile(
        key="soft_neutral", name="Soft Neutral",
        bg=WARMWHITE, bg_alt=SAND, ink=INK, sub=SUBINK, accent=RED, accent2=WARMGREY, on_accent=WHITE,
        card_bg=WHITE, card_ink=NAVY, dark=False,
        head_family="sans", body_family="sans_light", head_scale=0.9,
        align="center", kicker_style="plain", divider="dots", motif="dot_grid", hero_photo_side="right",
        disc_color=SAND,
        rail="thin_navy", cover_style="framed_right", page_bg=WARMWHITE,
    ),
    "midnight": DesignProfile(
        key="midnight", name="Midnight",
        bg=MIDNIGHT, bg_alt=MIDNIGHT2, ink=WHITE, sub=ICE, accent=RED, accent2=GOLD, on_accent=WHITE,
        card_bg=MIDNIGHT2, card_ink=WHITE, dark=True,
        head_family="display", body_family="sans_light",
        align="left", kicker_style="pill", divider="bar", motif="facets", hero_photo_side="right",
        divider_color=GOLD, disc_color=GOLD,
        rail="left_red", cover_style="framed_right", page_bg=CREAM,
    ),
}

PROFILE_ORDER = ["classic_navy", "editorial_cream", "bold_red", "split_duotone", "soft_neutral", "midnight"]
DEFAULT_PROFILE = "classic_navy"


def resolve_profile(key: str | None) -> DesignProfile | None:
    """A profile by key (from a stored asset / explicit request), or None if unknown/blank."""
    return PROFILES.get((key or "").strip()) if key else None


# --------------------------------------------------------------------------------------------------
# Rotation — "auto-rotate, never repeat the last". Per (owner, surface) we remember the last 3 keys
# and pick randomly from the rest, so posts and magazines rotate independently and a pm2 restart can
# never cause a deterministic repeat streak. In-memory, mirroring teampost._SKIN_ROT.
# --------------------------------------------------------------------------------------------------
_RECENT: dict[tuple[str, str], deque] = {}


def pick_profile(owner: str = "", surface: str = "post") -> DesignProfile:
    rec = _RECENT.setdefault((owner or "admin", surface), deque(maxlen=3))
    pool = [k for k in PROFILE_ORDER if k not in rec] or list(PROFILE_ORDER)
    key = random.choice(pool)
    rec.append(key)
    return PROFILES[key]


def next_profile(current: str | None, owner: str = "", surface: str = "post") -> DesignProfile:
    """A DIFFERENT profile from `current` — for a 'use a different style' edit. Records it in the
    rotation memory too, so a subsequent auto-pick won't immediately echo it."""
    cur = (current or "").strip()
    pool = [k for k in PROFILE_ORDER if k != cur] or list(PROFILE_ORDER)
    rec = _RECENT.setdefault((owner or "admin", surface), deque(maxlen=3))
    fresh = [k for k in pool if k not in rec] or pool
    key = random.choice(fresh)
    rec.append(key)
    return PROFILES[key]
