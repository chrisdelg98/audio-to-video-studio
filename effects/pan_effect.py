"""
PanEffect — Paneo lento vía zoompan (subpixel-smooth).

Usa zoompan con zoom=1 y x/y animados sinusoidalmente.
A diferencia de crop (que redondea a píxeles enteros),
zoompan interpola sub-píxel → movimiento suave incluso
a baja amplitud y velocidad.

Costo: ~2 M px/frame (un rescale interno de zoompan).
"""

from __future__ import annotations

from effects.base_effect import BaseEffect

DEFAULT_FPS = 30


class PanEffect(BaseEffect):
    """Paneo horizontal/vertical suave mediante zoompan (subpixel)."""

    def __init__(
        self,
        enabled: bool = False,
        amplitude: int = 20,
        speed: float = 0.5,
        width: int = 1920,
        height: int = 1080,
        fps: int = DEFAULT_FPS,
        **kwargs,
    ) -> None:
        super().__init__(enabled=enabled)
        self.amplitude = max(4, min(amplitude, 60))
        self.speed = max(0.1, min(speed, 2.0))
        self.width = width
        self.height = height
        self.fps = fps

    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        if not self.enabled:
            return ""
        a = self.amplitude
        fps = self.fps
        # zoompan x/y son offset desde esquina superior izquierda
        # centro = iw/2 - iw/zoom/2, pero con zoom=1 → x = 0 + oscilación
        # Necesitamos que la imagen sea un poco más grande para tener margen
        # Primero escalar un poco más grande, luego zoompan recorta al tamaño final
        pad = a * 2
        sw = self.width + pad
        sh = self.height + pad
        cx = a  # centro de oscilación en x
        cy = a  # centro de oscilación en y
        return (
            f"{label_in}"
            f"scale={sw}:{sh}:flags=fast_bilinear,"
            f"zoompan=z=1:"
            f"x='{cx}+{a}*sin({self.speed}*2*PI*in/{fps})':"
            f"y='{cy}+{a}*sin({self.speed}*1.3*2*PI*in/{fps})':"
            f"d=1:s={self.width}x{self.height}:fps={fps}"
            f"{label_out}"
        )
