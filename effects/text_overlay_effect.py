"""
TextOverlayEffect — Superposición de texto animado con efecto glitch usando drawtext.

El glitch se logra con tres capas drawtext:
  1. Fantasma cian desplazado a la izquierda  (oscila con sin())
  2. Fantasma rojo  desplazado a la derecha   (oscila con sin())
  3. Texto blanco principal (centrado, sombra)

Configuración de posición:
  - Top    → y = margen desde arriba
  - Middle → y = (h - text_h) / 2
  - Bottom → y = h - text_h - margen   (recomendado para subtítulos)

Las fuentes se cargan desde la carpeta 'fonts/' del proyecto usando rutas
relativas, lo que evita el problema de ':' en rutas de Windows con drawtext.
"""

from __future__ import annotations

from pathlib import Path

from core.utils import get_app_dir, get_bundle_dir
from effects.base_effect import BaseEffect

# Carpetas de fuentes (bundle + usuario)
_BUNDLED_FONTS_DIR = get_bundle_dir() / "fonts"
_USER_FONTS_DIR = get_app_dir() / "fonts"


def _is_disallowed_font(font_name: str) -> bool:
    return "font awesome" in (font_name or "").strip().lower()


def _iter_font_dirs() -> list[Path]:
    return [_USER_FONTS_DIR, _BUNDLED_FONTS_DIR]


def available_fonts() -> list[str]:
    """Retorna lista de fuentes disponibles para overlay (sin Font Awesome)."""
    names: set[str] = {"Arial"}
    for base in _iter_font_dirs():
        if not base.is_dir():
            continue
        for f in base.iterdir():
            if f.suffix.lower() in (".ttf", ".otf"):
                names.add(f.stem)
    return sorted((n for n in names if not _is_disallowed_font(n)), key=str.casefold)


def _resolve_font(font_name: str) -> str:
    """Resuelve nombre de fuente a ruta compatible con drawtext fontfile=."""
    for base in _iter_font_dirs():
        for ext in (".ttf", ".otf"):
            p = base / f"{font_name}{ext}"
            if p.exists():
                # FFmpeg drawtext necesita '/' y ':' escapado como '\\:'
                return str(p).replace("\\", "/").replace(":", "\\\\:")
    return ""


# Mapeo nombre → hex FFmpeg (sin #)
_COLOR_MAP: dict[str, str] = {
    "Blanco": "FFFFFF",
    "Gris claro": "D0D0D0",
    "Gris": "808080",
    "Gris oscuro": "404040",
    "Negro": "000000",
}


class TextOverlayEffect(BaseEffect):
    """Texto overlay con efecto glitch — pre-renderizado a PNG (Pillow) + overlay FFmpeg."""

    def __init__(self, settings: dict) -> None:
        super().__init__(enabled=settings.get("enable_text_overlay", False))
        self.text: str = settings.get("text_content", "")
        self.position: str = settings.get("text_position", "Bottom")   # Top / Middle / Bottom
        self.margin: int = int(settings.get("text_margin", 40))
        self.font_size: int = int(settings.get("text_font_size", 36))
        self.font_name: str = settings.get("text_font", "Arial")
        self.text_color: str = _COLOR_MAP.get(settings.get("text_color", "Blanco"), "FFFFFF")
        self.glitch_intensity: int = int(settings.get("text_glitch_intensity", 3))
        self.glitch_speed: float = float(settings.get("text_glitch_speed", 4.0))

    # ── PNG pre-render (Pillow) ──────────────────────────────────────

    def render_pngs(self, temp_dir: Path) -> list[tuple[Path, str]]:
        """Render all text layers into a **single** composite RGBA PNG.

        Ghost cyan/magenta and main text are composited in Pillow so FFmpeg
        only needs **one** ``overlay`` operation instead of three, eliminating
        two intermediate full-frame copies per text effect.

        Returns:
            List with one ``(png_path, "composite")`` tuple, or empty list.
        """
        if not self.enabled or not self.text.strip():
            return []

        from effects.text_renderer import _load_font
        from PIL import Image, ImageDraw

        uid = id(self)
        fc = self.text_color
        r, g, b = int(fc[0:2], 16), int(fc[2:4], 16), int(fc[4:6], 16)
        gi = self.glitch_intensity

        # Shadow: dark text → white shadow, light text → black shadow
        if fc in ("000000", "404040"):
            shadow = (255, 255, 255, int(255 * 0.7))
        else:
            shadow = (0, 0, 0, int(255 * 0.7))

        font = _load_font(self.font_name, self.font_size)
        bbox = font.getbbox(self.text)  # (left, top, right, bottom)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]

        sx, sy = 2, 2       # shadow offset
        pad = 8              # AA bleed
        extra_x = gi         # room for chromatic shift on each side

        w = tw + sx + pad * 2 + extra_x * 2
        h = th + sy + pad * 2
        w += w % 2           # even dims (yuv420p compat)
        h += h % 2

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        ox = pad + extra_x - bbox[0]   # text origin x (centred in canvas)
        oy = pad - bbox[1]             # text origin y

        # 1) Ghost layers (behind main)
        if gi > 0:
            draw.text((ox - gi, oy), self.text, font=font,
                      fill=(0, 255, 255, int(255 * 0.85)))
            draw.text((ox + gi, oy), self.text, font=font,
                      fill=(255, 0, 255, int(255 * 0.85)))

        # 2) Shadow
        draw.text((ox + sx, oy + sy), self.text, font=font, fill=shadow)

        # 3) Main text on top
        draw.text((ox, oy), self.text, font=font, fill=(r, g, b, 255))

        path = temp_dir / f"txt_{uid}_composite.png"
        img.save(path, "PNG")
        return [(path, "composite")]

    def get_overlay_position(self, layer_name: str) -> tuple[str, str]:
        """Return (x_expr, y_expr) for FFmpeg overlay filter.

        Overlay variables: W/H = main video size, w/h = overlay size, t = time.
        """
        m = self.margin

        # Y position
        if self.position == "Top":
            y_expr = f"round({m}*(H/1080))"
        elif self.position == "Middle":
            y_expr = "(H-h)/2"
        else:  # Bottom
            y_expr = f"H-h-round({m}*(H/1080))"

        # X position — composite is centred; subtle jitter for glitch feel
        x_center = "(W-w)/2"
        if self.glitch_intensity > 0:
            jitter = max(1, self.glitch_intensity // 2)
            x_expr = f"{x_center}+{jitter}*sin(t*{self.glitch_speed:.1f})"
        else:
            x_expr = x_center

        return x_expr, y_expr

    # ── Legacy drawtext path (kept for SlideshowBuilder -vf) ─────────

    def get_filter_chain(self, duration: float) -> str:
        """Retorna solo la cadena de drawtext (sin labels).

        Usado por FFmpegBuilder para fusionar overlays consecutivos en un
        solo segmento del filter_complex, evitando copias intermedias de frames.
        """
        if not self.enabled or not self.text.strip():
            return ""

        # Escapar caracteres especiales para drawtext
        safe = (
            self.text
            .replace("\\", "\\\\")
            .replace("'",  "\u2019")   # comilla tipográfica; evita romper el filtro
            .replace(":",  "\\:")
            .replace("%",  "\\%")
        )

        m  = self.margin
        fs = self.font_size
        gi = self.glitch_intensity
        gs = self.glitch_speed

        # Coordenada Y según posición elegida (normalizada a altura de referencia 1080)
        if self.position == "Top":
            y_expr = f"round({m}*(h/1080))"
        elif self.position == "Middle":
            y_expr = "(h-text_h)/2"
        else:                          # Bottom (default)
            y_expr = f"h-text_h-round({m}*(h/1080))"

        x_expr = "(w-text_w)/2"

        # Ruta relativa a la fuente local (sin ':' → compatible con drawtext)
        font_path = _resolve_font(self.font_name)
        ff = f":fontfile={font_path}" if font_path else ""

        layers: list[str] = []

        if gi > 0:
            # Fantasma cian (#00FFFF) — desplazado a la izquierda
            layers.append(
                f"drawtext=text='{safe}'{ff}:fontcolor=0x00FFFF@0.85:fontsize={fs}"
                f":x={x_expr}-{gi}*abs(sin(t*{gs:.1f})):y={y_expr}"
            )
            # Fantasma magenta (#FF00FF) — desplazado a la derecha
            layers.append(
                f"drawtext=text='{safe}'{ff}:fontcolor=0xFF00FF@0.85:fontsize={fs}"
                f":x={x_expr}+{gi}*abs(sin(t*{gs:.1f})):y={y_expr}"
            )

        # Texto principal (siempre encima)
        fc = self.text_color
        # Shadow: si el texto es oscuro, usar sombra blanca; si claro, sombra negra
        sc = "white" if fc in ("000000", "404040") else "black"
        layers.append(
            f"drawtext=text='{safe}'{ff}:fontcolor=0x{fc}:fontsize={fs}"
            f":x={x_expr}:y={y_expr}"
            f":shadowcolor={sc}@0.7:shadowx=2:shadowy=2"
        )

        return ",".join(layers)

    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        chain = self.get_filter_chain(duration)
        if not chain:
            return f"{label_in}copy{label_out}"
        return f"{label_in}{chain}{label_out}"
