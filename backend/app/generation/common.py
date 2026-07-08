"""Shared helpers for the generation engines: fonts, filenames, URLs, colors, brand logo."""
from __future__ import annotations

import io
import uuid
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ..config import settings

# Brand logo mark — navy "TR" inside a coral-red square on white (the canonical Talentrupt logo).
_LOGO_NAVY = (0x0B, 0x35, 0x59)
_LOGO_RED = (0xF6, 0x40, 0x4C)
# The REAL logo, extracted from Talentrupt's brand guideline and bundled with the repo. Used by
# default on every generated asset (overridable via settings.brand_logo_path).
_BUNDLED_LOGO = Path(__file__).resolve().parent.parent / "brand" / "tr_logo.png"
# The official TALENTRUPT WORDMARK (transparent PNG, true aspect ratio) — navy for light backgrounds,
# white for dark. Composited into RESERVED clean space (never stamped over content). From the brand PDF.
_BUNDLED_WORDMARK = Path(__file__).resolve().parent.parent / "brand" / "tr_wordmark.png"
_BUNDLED_WORDMARK_WHITE = Path(__file__).resolve().parent.parent / "brand" / "tr_wordmark_white.png"

# Bundled OFL fonts (ship with the repo -> identical look on the dev box AND on Linux prod). These come
# FIRST so dev == prod; OS fonts (Windows dev box, Linux DejaVu) are graceful fallbacks and Pillow's
# built-in default is the last resort so a missing TTF can NEVER crash rendering. NOTE: before this,
# the candidates were Windows-only paths, so on the Linux droplet EVERY renderer fell back to Pillow's
# generic default font — bundling real fonts fixes that app-wide.
_BUNDLED_FONTS = Path(__file__).resolve().parent.parent / "brand" / "fonts"

# Design-system font FAMILIES. `font(family, size)` resolves the first existing path; a family may be a
# variable font, in which case `_FAMILY_VARIATION` names the master to select (e.g. Playfair -> "Bold").
_FAMILIES: dict[str, list[str]] = {
    "sans": [                                                   # default heading (bold-ish)
        str(_BUNDLED_FONTS / "Poppins-SemiBold.ttf"),
        "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "sans_light": [                                             # default body (regular)
        str(_BUNDLED_FONTS / "Poppins-Regular.ttf"),
        "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "serif": [                                                  # editorial display serif (variable -> Bold)
        str(_BUNDLED_FONTS / "PlayfairDisplay-VF.ttf"),
        "C:/Windows/Fonts/georgiab.ttf", "C:/Windows/Fonts/timesbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ],
    "display": [                                                # heavy poster display
        str(_BUNDLED_FONTS / "ArchivoBlack-Regular.ttf"),
        "C:/Windows/Fonts/ariblk.ttf", "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}
_FAMILY_VARIATION = {"serif": "Bold"}   # variable-font families -> named master to pick

# Handwritten/script accent for "Featuring [Name]" & anniversary numbers (bundled Caveat, variable -> Bold).
_SCRIPT_CANDIDATES = [
    str(_BUNDLED_FONTS / "Caveat-Bold.ttf"),
    "C:/Windows/Fonts/segoesc.ttf",   # Segoe Script (dev-box hand feel)
    "C:/Windows/Fonts/segoeprb.ttf",  # Segoe Print Bold
    "C:/Windows/Fonts/segoeuib.ttf",  # last resort: heading font (never crashes)
]


def _first_existing(candidates: list[str]) -> str | None:
    for c in candidates:
        if Path(c).exists():
            return c
    return None


@lru_cache(maxsize=8)
def _family_path(family: str) -> str | None:
    return _first_existing(_FAMILIES.get(family) or _FAMILIES["sans"])


def font(family: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a design-system font family at `size`. Bundled-first (dev==prod), graceful OS/default
    fallback (never raises). Selects the correct master on variable-font families."""
    path = _family_path(family)
    if not path:
        return ImageFont.load_default(size)
    f = ImageFont.truetype(path, size)
    var = _FAMILY_VARIATION.get(family)
    if var and path.lower().endswith(".ttf"):
        try:
            f.set_variation_by_name(var)   # e.g. Playfair Display VF -> "Bold" master
        except Exception:
            pass
    return f


def heading_font(size: int) -> ImageFont.FreeTypeFont:
    """Default bold heading font — now the bundled 'sans' family (Poppins). Kept as an alias so EVERY
    existing renderer (teampost, decks, pdf, posts) benefits with zero call-site edits."""
    return font("sans", size)


def body_font(size: int) -> ImageFont.FreeTypeFont:
    """Default regular body font — the bundled 'sans_light' family (Poppins Regular)."""
    return font("sans_light", size)


def script_font(size: int) -> ImageFont.FreeTypeFont:
    """Handwritten/script accent font (bundled Caveat). Best-effort selects the Bold master on the
    variable font; falls back to an OS script font, then the heading font — never raises."""
    path = _first_existing(_SCRIPT_CANDIDATES)
    if not path:
        return heading_font(size)
    f = ImageFont.truetype(path, size)
    try:
        f.set_variation_by_name("Bold")  # Caveat is a variable font; pick the bold master when present
    except Exception:
        pass
    return f


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def unique_name(prefix: str, ext: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}.{ext}"


def storage_subdir(kind: str) -> Path:
    return settings.storage_path / kind


def public_url(kind: str, file_name: str) -> str:
    """Relative URL served by the backend; the frontend prepends API_BASE."""
    return f"/api/files/{kind}/{file_name}"


def _render_logo(path: Path, size: int = 600) -> None:
    """Draw a close approximation of the Talentrupt logo: navy 'TR' in a coral-red near-square frame
    on white. Used only as a fallback when no real logo file is configured (see logo_path)."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    m = int(size * 0.09)
    bw = max(10, int(size * 0.06))
    # Near-square corners (small radius) to match the real mark's square red frame.
    d.rounded_rectangle([m, m, size - m, size - m], radius=int(size * 0.05), outline=_LOGO_RED, width=bw)
    # Large, tight 'TR' filling the frame.
    font = heading_font(int(size * 0.52))
    l, t, r, b = d.textbbox((0, 0), "TR", font=font)
    d.text(((size - (r - l)) / 2 - l, (size - (b - t)) / 2 - t), "TR", font=font, fill=_LOGO_NAVY)
    img.save(str(path))


def _install_real_logo(src: Path, dest: Path) -> bool:
    """Normalize a user-provided logo file into the cache as a square RGBA PNG. Best-effort."""
    try:
        logo = Image.open(str(src)).convert("RGBA")
        w, h = logo.size
        side = max(w, h)
        # Center on a white square so a non-square or transparent source still composites cleanly.
        canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
        canvas.paste(logo, ((side - w) // 2, (side - h) // 2), logo)
        canvas.save(str(dest))
        return True
    except Exception:
        return False


def logo_path() -> Path:
    """Path to the canonical Talentrupt logo PNG used by EVERY generated asset (image/deck/PDF).
    Resolution order: (1) the real logo file at settings.brand_logo_path, if set + present — it is
    normalized into the cache and refreshed whenever the source changes; (2) an existing cached
    logo (e.g. a real PNG dropped in directly); (3) a synthesized fallback. Self-healing."""
    p = settings.storage_path / "brand" / "tr_logo.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    # Source for the REAL logo: an explicit override path wins; otherwise the bundled repo asset.
    cfg = (settings.brand_logo_path or "").strip()
    srcp = Path(cfg) if cfg else _BUNDLED_LOGO
    if srcp.exists() and srcp.resolve() != p.resolve():
        # Install/refresh the cache when it's missing or the source is newer.
        if (not p.exists()) or srcp.stat().st_mtime > p.stat().st_mtime:
            if _install_real_logo(srcp, p):
                return p
        if p.exists():
            return p
    if not p.exists():
        _render_logo(p)  # synthesized fallback only when no real logo is available
    return p


def paste_logo(img, x: int, y: int, size: int) -> bool:
    """Paste the brand logo (square, `size` px) at (x, y) onto a PIL image. Best-effort."""
    try:
        logo = Image.open(str(logo_path())).convert("RGBA").resize((size, size))
        img.paste(logo, (int(x), int(y)), logo)
        return True
    except Exception:
        return False


def wordmark_path(dark_bg: bool = False) -> Path:
    """Path to the official Talentrupt WORDMARK (a transparent, true-aspect PNG). White variant on a dark
    background, navy on a light one. Falls back to the square logo if the wordmark asset is missing."""
    p = _BUNDLED_WORDMARK_WHITE if dark_bg else _BUNDLED_WORDMARK
    return p if p.exists() else logo_path()


def paste_wordmark(img, x: int, y: int, max_w: int, max_h: int, dark_bg: bool = False, align: str = "left") -> bool:
    """Fit the official wordmark into a (max_w x max_h) box at (x, y), preserving aspect ratio, on a
    TRANSPARENT background — so it sits in reserved space and NEVER covers content with a chip/box.
    `align` positions the (narrower) wordmark within the box: left | center | right. Best-effort."""
    try:
        wm = Image.open(str(wordmark_path(dark_bg))).convert("RGBA")
        scale = min(max_w / wm.width, max_h / wm.height)
        w, h = max(1, int(wm.width * scale)), max(1, int(wm.height * scale))
        wm = wm.resize((w, h), Image.LANCZOS)
        if align == "center":
            x = int(x + (max_w - w) / 2)
        elif align == "right":
            x = int(x + (max_w - w))
        img.paste(wm, (int(x), int(y)), wm)  # wm's own alpha is the mask -> no opaque box
        return True
    except Exception:
        return False


def composite_logo_bytes(png_bytes: bytes, corner: str = "bottom-right", frac: float = 0.10) -> bytes:
    """Overlay the brand logo onto an existing PNG (e.g. an AI-generated image) so the correct
    Talentrupt mark is always present. Kept SMALL with a TIGHT chip so it reads as a corner badge and
    does not cover the image's headline or stat text. Sits on an opaque white chip with a soft drop
    shadow + subtle border so it lifts off ANY background. Returns bytes unchanged on failure."""
    try:
        base = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        s = max(56, int(min(base.size) * frac))  # small logo edge in px
        pad = int(s * 0.40)
        x = pad if "left" in corner else base.size[0] - s - pad
        y = pad if "top" in corner else base.size[1] - s - pad
        m = int(s * 0.10)  # tight chip margin — minimal coverage of the underlying image
        chip = [x - m, y - m, x + s + m, y + s + m]
        rad = int(s * 0.22)
        # Soft drop shadow on its own layer so the chip reads on light AND dark/busy backgrounds.
        off = max(2, int(s * 0.06))
        shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ImageDraw.Draw(shadow).rounded_rectangle(
            [chip[0] + off, chip[1] + off, chip[2] + off, chip[3] + off], radius=rad,
            fill=(11, 53, 89, 120),  # navy-tinted shadow
        )
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(3, int(s * 0.07))))
        base = Image.alpha_composite(base, shadow)
        # Opaque white chip + faint navy hairline border.
        d = ImageDraw.Draw(base)
        d.rounded_rectangle(chip, radius=rad, fill=(255, 255, 255, 255),
                            outline=(11, 53, 89, 45), width=max(1, int(s * 0.012)))
        paste_logo(base, x, y, s)
        out = io.BytesIO()
        base.convert("RGB").save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return png_bytes
