"""Shared helpers for the generation engines: fonts, filenames, URLs, colors, brand logo."""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..config import settings

# Brand logo mark — navy "TR" inside a coral-red square on white (the canonical Talentrupt logo).
_LOGO_NAVY = (0x0B, 0x35, 0x59)
_LOGO_RED = (0xF6, 0x40, 0x4C)
# The REAL logo, extracted from Talentrupt's brand guideline and bundled with the repo. Used by
# default on every generated asset (overridable via settings.brand_logo_path).
_BUNDLED_LOGO = Path(__file__).resolve().parent.parent / "brand" / "tr_logo.png"

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


def composite_logo_bytes(png_bytes: bytes, corner: str = "bottom-right", frac: float = 0.13) -> bytes:
    """Overlay the brand logo onto an existing PNG (e.g. an AI-generated image) so the correct
    Talentrupt mark is always present. Draws a clean white chip behind it so the logo reads even
    if the model rendered text/graphics in that corner. Returns bytes unchanged on any failure."""
    try:
        base = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        s = max(48, int(min(base.size) * frac))
        pad = int(s * 0.45)
        x = pad if "left" in corner else base.size[0] - s - pad
        y = pad if "top" in corner else base.size[1] - s - pad
        # Opaque white chip behind the mark — covers any underlying art so there's no overlap/clash.
        d = ImageDraw.Draw(base)
        m = int(s * 0.16)
        d.rounded_rectangle([x - m, y - m, x + s + m, y + s + m], radius=int(s * 0.2),
                            fill=(255, 255, 255, 255))
        paste_logo(base, x, y, s)
        out = io.BytesIO()
        base.convert("RGB").save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return png_bytes
