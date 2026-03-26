"""
BreathEffect — Pulso suave de brillo (fade respiración).

Usa el filtro `eq` de FFmpeg con una expresión sinusoidal en brightness.
Costo computacional: ~0 (expresión evaluada por píxel sin copia extra).
"""

from __future__ import annotations

from effects.base_effect import BaseEffect


class BreathEffect(BaseEffect):
    """Pulso cíclico de brillo (brightness sine wave)."""

    def __init__(
        self,
        enabled: bool = False,
        intensity: float = 0.04,
        speed: float = 1.0,
        **kwargs,
    ) -> None:
        super().__init__(enabled=enabled)
        self.intensity = max(0.01, min(intensity, 0.15))
        self.speed = max(0.1, min(speed, 3.0))

    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        if not self.enabled:
            return ""
        return (
            f"{label_in}"
            f"eq=brightness='{self.intensity}*sin({self.speed}*2*PI*t)':eval=frame"
            f"{label_out}"
        )
