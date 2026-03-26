"""
LightZoomEffect — Zoom ligero via zoompan d=1 (sin supersampling ni tmix).

Usa zoompan con d=1 para procesar un frame de entrada → un frame de salida
con zoom sinusoidal. Mucho más barato que el ZoomEffect original que usaba
scale 2×, crop, scale back y tmix(8).

Costo: ~2 M px/frame (un solo rescale interno de zoompan).
"""

from __future__ import annotations

from effects.base_effect import BaseEffect

DEFAULT_FPS = 30


class LightZoomEffect(BaseEffect):
    """Zoom suave vía zoompan d=1 (sin supersampling)."""

    def __init__(
        self,
        enabled: bool = False,
        zoom_max: float = 1.04,
        speed: float = 0.5,
        width: int = 1920,
        height: int = 1080,
        fps: int = DEFAULT_FPS,
        **kwargs,
    ) -> None:
        super().__init__(enabled=enabled)
        self.zoom_max = max(1.01, min(zoom_max, 1.15))
        self.speed = max(0.1, min(speed, 2.0))
        self.width = width
        self.height = height
        self.fps = fps

    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        if not self.enabled:
            return ""
        zm = self.zoom_max
        half = (zm - 1.0) / 2.0
        mid = 1.0 + half
        w, h = self.width, self.height
        # scale+crop en lugar de zoompan: evita el temblor por lround() en zoompan.
        # trunc(.../2)*2 → dimensiones pares siempre.
        # max(1.01,...) → imagen siempre ≥ 1% más grande que el canvas:
        # garantiza que (in_w - W)/2 ≥ ~10px, nunca llega a 0.
        return (
            f"{label_in}"
            f"scale="
            f"w='trunc(iw*max(1.01,{mid:.6f}+{half:.6f}*sin({self.speed:.6f}*2*PI*t))/2)*2':"
            f"h='trunc(ih*max(1.01,{mid:.6f}+{half:.6f}*sin({self.speed:.6f}*2*PI*t))/2)*2':"
            f"eval=frame,"
            f"crop={w}:{h}:(in_w-{w})/2:(in_h-{h})/2"
            f"{label_out}"
        )
