"""Shared helpers for the generation engines: fonts, filenames, URLs, colors, brand logo."""
from __future__ import annotations

import io
import uuid
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

# Windows font candidates (bold heading + regular body), with graceful fallback.
_HEADING_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/Poppins-SemiBold.ttf",
]
_BODY_CANDIDATES = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/Montserrat-Regular.ttf",
]
# Handwritten/script accent for "Featuring [Name]" & anniversary numbers. The bundled Caveat (SIL OFL)
# ships with the repo so the look is identical on the dev box AND on Linux prod; OS script fonts and the
# heading font are graceful fallbacks so a missing TTF can never crash rendering.
_BUNDLED_FONTS = Path(__file__).resolve().parent.parent / "brand" / "fonts"
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


def heading_font(size: int) -> ImageFont.FreeTypeFont:
    path = _first_existing(_HEADING_CANDIDATES)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


def body_font(size: int) -> ImageFont.FreeTypeFont:
    path = _first_existing(_BODY_CANDIDATES)
    return ImageFont.truetype(path, size) if path else ImageFont.load_default(size)


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
