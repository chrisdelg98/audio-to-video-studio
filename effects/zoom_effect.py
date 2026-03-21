"""
ZoomEffect — Zoom dinámico ultra-suave con super-muestreo 4× + tmix.

Pipeline de 4 etapas:
  1. scale:eval=frame → ampliar a ~7680px × factor de zoom (bicubic)
  2. crop             → recortar centro al tamaño del super-muestreo (fijo)
  3. scale            → reducir a resolución final (lanczos)
  4. tmix=frames=5    → promediar 5 frames consecutivos

Etapas 1-3 eliminan la mayor parte de la cuantización (≤0.5 px en salida).
La etapa 4 (tmix) convierte el salto residual de 0.5 px en una transición
lineal de 5 frames (0.1 px/frame), completamente invisible al ojo humano.

tmix funciona porque la fuente es una imagen estática:
  - Durante las fases "hold" (dimensión constante), los 5 frames son
    idénticos → promedio = frame sin cambio alguno.
  - En el instante del salto (frame K), el promedio crea:
      K:   20% nuevo + 80% anterior
      K+1: 40% nuevo + 60% anterior
      K+2: 60% nuevo + 40% anterior
      K+3: 80% nuevo + 20% anterior
      K+4: 100% nuevo
    → transición lineal perfecta en 167 ms, imperceptible.
"""

from effects.base_effect import BaseEffect


class ZoomEffect(BaseEffect):
    """
    Zoom oscilante con super-muestreo 4× + interpolación temporal.

    Fórmula:
        z(n) = 1 + amplitude * (1 − cos(n / speed)) / 2

    El factor de super-muestreo mantiene ~7680 px de ancho intermedio.
    tmix=5 suaviza los saltos residuales de cuantización.
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

        # Factor adaptativo: ~7680px ancho intermedio
        #   720p→4×  1080p→4×  1440p→3×  4K→2×
        factor = max(2, min(4, 7680 // max(w, 1)))
        wf = w * factor
        hf = h * factor

        # Expresión de zoom ('n' = frame counter en scale:eval=frame)
        z = f"1+{amplitude:.6f}*(1-cos(n/{speed:.1f}))/2"

        # Dimensiones en super-resolución (par para yuv420p)
        sw = f"trunc(iw*{factor}*({z})/2)*2"
        sh = f"trunc(ih*{factor}*({z})/2)*2"

        # tmix=5: promedia 5 frames → transición lineal entre pasos
        # de cuantización. Máximo cambio visible = 0.1 px/frame.
        return (
            f"{label_in}"
            f"scale={sw}:{sh}:eval=frame:flags=bicubic,"
            f"crop={wf}:{hf}:(in_w-{wf})/2:(in_h-{hf})/2,"
            f"scale={w}:{h}:flags=lanczos,"
            f"tmix=frames=5:weights=1 1 1 1 1"
            f"{label_out}"
        )


