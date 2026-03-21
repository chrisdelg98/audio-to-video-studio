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
"""

from __future__ import annotations

from effects.base_effect import BaseEffect


class TextOverlayEffect(BaseEffect):
    """Dibuja texto con animación glitch usando el filtro drawtext de FFmpeg."""

    def __init__(self, settings: dict) -> None:
        super().__init__(enabled=settings.get("enable_text_overlay", False))
        self.text: str = settings.get("text_content", "")
        self.position: str = settings.get("text_position", "Bottom")   # Top / Middle / Bottom
        self.margin: int = int(settings.get("text_margin", 40))
        self.font_size: int = int(settings.get("text_font_size", 36))
        self.glitch_intensity: int = int(settings.get("text_glitch_intensity", 3))
        self.glitch_speed: float = float(settings.get("text_glitch_speed", 4.0))

    # ------------------------------------------------------------------

    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        if not self.enabled or not self.text.strip():
            return f"{label_in}copy{label_out}"

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

        # Coordenada Y según posición elegida
        if self.position == "Top":
            y_expr = str(m)
        elif self.position == "Middle":
            y_expr = "(h-text_h)/2"
        else:                          # Bottom (default)
            y_expr = f"h-text_h-{m}"

        x_expr = "(w-text_w)/2"

        layers: list[str] = []

        if gi > 0:
            # Fantasma cian (desplazado a la izquierda según oscilación)
            layers.append(
                f"drawtext=text='{safe}':fontcolor=cyan@0.5:fontsize={fs}"
                f":x={x_expr}-{gi}*abs(sin(t*{gs:.1f})):y={y_expr}"
                f":shadowcolor=black@0.3:shadowx=1:shadowy=1"
            )
            # Fantasma rojo (desplazado a la derecha)
            layers.append(
                f"drawtext=text='{safe}':fontcolor=red@0.5:fontsize={fs}"
                f":x={x_expr}+{gi}*abs(sin(t*{gs:.1f})):y={y_expr}"
                f":shadowcolor=black@0.3:shadowx=1:shadowy=1"
            )

        # Texto blanco principal (siempre encima)
        layers.append(
            f"drawtext=text='{safe}':fontcolor=white:fontsize={fs}"
            f":x={x_expr}:y={y_expr}"
            f":shadowcolor=black@0.7:shadowx=2:shadowy=2"
        )

        chain = ",".join(layers)
        return f"{label_in}{chain}{label_out}"
