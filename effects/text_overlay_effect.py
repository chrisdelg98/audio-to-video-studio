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

from core.utils import get_bundle_dir
from effects.base_effect import BaseEffect

# Carpeta de fuentes (dentro del bundle o raíz del proyecto)
_FONTS_DIR = get_bundle_dir() / "fonts"


def available_fonts() -> list[str]:
    """Retorna lista de nombres de fuentes .ttf/.otf disponibles en fonts/."""
    if not _FONTS_DIR.is_dir():
        return []
    fonts = sorted(
        f.stem
        for f in _FONTS_DIR.iterdir()
        if f.suffix.lower() in (".ttf", ".otf")
    )
    return fonts


def _resolve_font(font_name: str) -> str:
    """Resuelve nombre de fuente a ruta compatible con drawtext fontfile=."""
    for ext in (".ttf", ".otf"):
        p = _FONTS_DIR / f"{font_name}{ext}"
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
    """Dibuja texto con animación glitch usando el filtro drawtext de FFmpeg."""

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

    # ------------------------------------------------------------------

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
