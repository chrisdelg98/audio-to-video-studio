"""
TextRenderer — Pre-render text overlays to transparent PNG using Pillow.

Why PNG instead of drawtext:
  drawtext rasterizes glyphs per-frame (30×/s per layer).
  Pillow renders once; FFmpeg overlay composites cached pixels (~5-10× faster).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from core.utils import get_bundle_dir

_FONTS_DIR = get_bundle_dir() / "fonts"


def _load_font(font_name: str, size: int) -> ImageFont.FreeTypeFont:
    """Load a FreeType font from the bundled fonts directory."""
    for ext in (".ttf", ".otf"):
        p = _FONTS_DIR / f"{font_name}{ext}"
        if p.exists():
            return ImageFont.truetype(str(p), size)
    # Fallback: Pillow default
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def render_text_layer(
    text: str,
    font_name: str,
    font_size: int,
    color: tuple[int, int, int, int],
    output_path: Path,
    shadow_color: tuple[int, int, int, int] | None = None,
    shadow_offset: tuple[int, int] = (2, 2),
) -> Path:
    """Render text to a transparent RGBA PNG sized to fit the text.

    Args:
        text:          The text string to render.
        font_name:     Font stem name (resolved from _FONTS_DIR).
        font_size:     Font size in points.
        color:         (R, G, B, A) fill colour.
        output_path:   Where to save the PNG.
        shadow_color:  Optional shadow colour (R, G, B, A).
        shadow_offset: Shadow (dx, dy) in pixels.

    Returns:
        output_path (same as input, for chaining).
    """
    font = _load_font(font_name, font_size)

    # Measure text bounding box
    bbox = font.getbbox(text)  # (left, top, right, bottom)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    # Padding for shadow + anti-aliasing bleed
    sx = abs(shadow_offset[0]) if shadow_color else 0
    sy = abs(shadow_offset[1]) if shadow_color else 0
    pad = 8

    w = tw + sx + pad * 2
    h = th + sy + pad * 2
    # Make dimensions even (yuv420p compatibility)
    w += w % 2
    h += h % 2

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Text origin (compensate for font bbox offset)
    ox = pad - bbox[0]
    oy = pad - bbox[1]

    # Shadow first (behind main text)
    if shadow_color:
        draw.text(
            (ox + shadow_offset[0], oy + shadow_offset[1]),
            text, font=font, fill=shadow_color,
        )

    # Main text on top
    draw.text((ox, oy), text, font=font, fill=color)

    img.save(output_path, "PNG")
    return output_path
