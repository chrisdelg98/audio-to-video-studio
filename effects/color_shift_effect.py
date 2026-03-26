"""
ColorShiftEffect — Rotación cíclica de tono (hue shift).

Usa el filtro `hue` de FFmpeg con una expresión sinusoidal.

Costo: ~2 M px/frame (conversión de color space).
"""

from __future__ import annotations

from effects.base_effect import BaseEffect


class ColorShiftEffect(BaseEffect):
    """Rotación suave de tono (hue) con oscilación sinusoidal."""

    def __init__(
        self,
        enabled: bool = False,
        amount: float = 15.0,
        speed: float = 0.5,
        **kwargs,
    ) -> None:
        super().__init__(enabled=enabled)
        self.amount = max(1.0, min(amount, 90.0))
        self.speed = max(0.1, min(speed, 3.0))

    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        if not self.enabled:
            return ""
        return (
            f"{label_in}"
            f"hue=h='{self.amount:.1f}*sin({self.speed}*2*PI*t)'"
            f"{label_out}"
        )
