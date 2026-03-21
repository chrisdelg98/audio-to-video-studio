"""
ZoomEffect — Zoom dinámico ultra-suave con super-muestreo 3× + tmix adaptativo.

Pipeline de 4 etapas:
  1. scale:eval=frame → ampliar a ~5760px × factor de zoom (bilinear)
  2. crop             → recortar centro al tamaño del super-muestreo (fijo)
  3. scale            → reducir a resolución final (lanczos)
  4. tmix             → promediar N frames consecutivos

El super-muestreo es fijo (3× ≈ 5760px) para rendimiento constante.
La suavidad se ajusta vía tmix (barato: opera a resolución de salida):
  - Amplitud < 1.5% (ej. 1.010): tmix=9  →  0.037 px/frame
  - Amplitud 1.5-4% (ej. 1.020): tmix=5  →  0.067 px/frame
  - Amplitud ≥ 4%   (ej. 1.050): tmix=3  →  0.110 px/frame

Zoom sutil necesita más tmix porque el movimiento es tan lento que
la cuantización (0.33px) supera el desplazamiento real por frame.
tmix=9 reparte ese salto en 9 frames → transición imperceptible.

El upscale usa bilinear (4 muestras/px) en vez de bicubic (16 muestras/px)
porque su único propósito es dar precisión sub-pixel al posicionamiento.
La calidad visual la aporta el downscale con lanczos en la etapa 3.
"""

from effects.base_effect import BaseEffect


class ZoomEffect(BaseEffect):
    """
    Zoom oscilante con super-muestreo 3× + tmix adaptativo.

    Fórmula:
        z(n) = 1 + amplitude * (1 − cos(n / speed)) / 2

    Factor 3× fijo (~5760px intermedio) para rendimiento constante.
    tmix se adapta según amplitud para mantener suavidad óptima.
    """

    def __init__(
        self,
        enabled: bool = True,
        zoom_max: float = 1.02,
        zoom_speed: int = 300,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
    ) -> None:
        super().__init__(
            enabled=enabled,
            zoom_max=zoom_max,
            zoom_speed=zoom_speed,
            width=width,
            height=height,
            fps=fps,
        )

    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        if not self.enabled:
            return f"{label_in}copy{label_out}"

        zoom_max = self.params["zoom_max"]
        speed    = self.params["zoom_speed"]
        w        = self.params["width"]
        h        = self.params["height"]

        amplitude = zoom_max - 1.0

        # Factor fijo 3× para rendimiento constante (~5760px intermedio)
        factor = max(2, min(4, 5760 // max(w, 1)))

        # tmix adaptativo según amplitud (barato: opera a res. de salida)
        # Zoom sutil → más tmix para compensar cuantización lenta
        # Zoom agresivo → menos tmix, velocidad oculta los saltos
        if amplitude < 0.015:
            tmix = 9   # 0.33px / 9 = 0.037 px/frame
        elif amplitude < 0.04:
            tmix = 5   # 0.33px / 5 = 0.067 px/frame
        else:
            tmix = 3   # 0.33px / 3 = 0.110 px/frame

        weights = " ".join(["1"] * tmix)
        wf = w * factor
        hf = h * factor

        # Expresión de zoom ('n' = frame counter en scale:eval=frame)
        z = f"1+{amplitude:.6f}*(1-cos(n/{speed:.1f}))/2"

        # Dimensiones en super-resolución (par para yuv420p)
        sw = f"trunc(iw*{factor}*({z})/2)*2"
        sh = f"trunc(ih*{factor}*({z})/2)*2"

        # bilinear para upscale (solo necesita precisión posicional),
        # lanczos para downscale (preserva nitidez visual).
        return (
            f"{label_in}"
            f"scale={sw}:{sh}:eval=frame:flags=bilinear,"
            f"crop={wf}:{hf}:(in_w-{wf})/2:(in_h-{hf})/2,"
            f"scale={w}:{h}:flags=lanczos,"
            f"tmix=frames={tmix}:weights={weights}"
            f"{label_out}"
        )


