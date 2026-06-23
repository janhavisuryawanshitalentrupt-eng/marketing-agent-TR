"""Talentrupt brand system — the single source of truth for visual identity.

Used by the image compositor, deck builder, and PDF builder. Hand-curated
(not learned). Learned patterns from the source library augment generation copy,
but these visual rules stay fixed for brand consistency.
"""
from __future__ import annotations

# --- Palette --------------------------------------------------------------
NAVY = "#0B3559"
RED = "#F6404C"
CREAM = "#EBE9DF"
WHITE = "#FFFFFF"
BLACK = "#111111"

PALETTE = {
    "navy": NAVY,
    "red": RED,
    "cream": CREAM,
    "white": WHITE,
    "black": BLACK,
}

# --- Typography -----------------------------------------------------------
FONTS = {
    "heading": "Poppins",   # bold, structured headings
    "body": "Montserrat",   # clean body copy
}

# --- Visual rules ---------------------------------------------------------
VISUAL_RULES = [
    "Red side rail on content slides/cards",
    "Navy and cream split panels",
    "Rounded cards with generous padding",
    "Numbered red markers for steps",
    "TR lockup treatment; coral/red accent around the TR mark",
    "Infographic, process-diagram, and proof-point card layouts",
    "Count-aware recruiter-capacity visuals",
]

BRAND_KIT = {
    "name": "Talentrupt",
    "tagline": "RPO Done Right",
    "palette": PALETTE,
    "fonts": FONTS,
    "visual_rules": VISUAL_RULES,
    "logo": {
        "mark": "TR",
        "accent": RED,
        "treatment": "TR lockup with coral/red accent on navy or cream",
    },
}


def brand_kit() -> dict:
    return BRAND_KIT
