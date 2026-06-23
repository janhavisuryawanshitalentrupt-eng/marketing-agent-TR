"""Shared helpers for the generation engines: fonts, filenames, URLs, colors, brand logo."""
from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ..config import settings

# Brand logo mark — navy "TR" inside a red rounded square on white (the canonical Talentrupt logo).
_LOGO_NAVY = (0x0B, 0x35, 0x59)
_LOGO_RED = (0xF6, 0x40, 0x4C)

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
    """Draw the canonical Talentrupt logo: navy 'TR' in a red rounded-square frame on white."""
    img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    d = ImageDraw.Draw(img)
    m = int(size * 0.10)
    bw = max(8, int(size * 0.055))
    d.rounded_rectangle([m, m, size - m, size - m], radius=int(size * 0.10), outline=_LOGO_RED, width=bw)
    font = heading_font(int(size * 0.46))
    l, t, r, b = d.textbbox((0, 0), "TR", font=font)
    d.text(((size - (r - l)) / 2 - l, (size - (b - t)) / 2 - t), "TR", font=font, fill=_LOGO_NAVY)
    img.save(str(path))


def logo_path() -> Path:
    """Path to the canonical Talentrupt logo PNG. Rendered once on first use (self-healing if
    deleted) so every generated asset — image, deck, PDF — embeds the SAME, correct mark."""
    p = settings.storage_path / "brand" / "tr_logo.png"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        _render_logo(p)
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
