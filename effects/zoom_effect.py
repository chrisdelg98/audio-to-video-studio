"""
ZoomEffect — Efecto de zoom dinámico suave usando scale+crop de FFmpeg.

Usa scale con expresión por frame + crop centrado para producir un zoom
perfectamente fluido con ease-in/ease-out real.

Por qué NO se usa zoompan:
  - zoompan es secuencial y lento (procesa un frame a la vez con estado interno)
  - Genera tiempos de frame irregulares → se percibe como "lag" o "choppiness"
  - scale+crop procesa cada frame de forma independiente → mucho más rápido y uniforme
"""

from effects.base_effect import BaseEffect


class ZoomEffect(BaseEffect):
    """
    Aplica un zoom dinámico usando scale+crop con expresión matemática per-frame.

    Fórmula de easing:
        zoom_factor = 1 + amplitude * (1 - cos(n / speed)) / 2

        - Basada en (1-cos)/2 → oscila suavemente entre 0 y 1
        - Derivada = 0 en los extremos → ease-in/ease-out perfecto
        - Siempre >= 1.0 → el crop nunca sobrepasa los bordes
        - Período completo de un ciclo: 2 * PI * speed frames

    Parámetros:
        zoom_max:   Factor máximo de zoom (ej. 1.05 = 5% máximo). Default 1.05.
        zoom_speed: Controla la duración del ciclo. Mayor = ciclo más lento.
                    A 30fps, speed=300 ≈ 63s por ciclo (zoom muy lento y suave).
        width:      Anchura del frame de salida en píxeles.
        height:     Altura del frame de salida en píxeles.
        fps:        FPS del video de salida.
    """

    def __init__(
        self,
        enabled: bool = True,
        zoom_max: float = 1.05,
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
        speed = self.params["zoom_speed"]
        w = self.params["width"]
        h = self.params["height"]

        amplitude = zoom_max - 1.0

        # Pre-escalar a la tamaño máximo de zoom (FIJO, sin eval=frame).
        # Esto estabiliza el kernel de filtrado lanczos entre frames, eliminando
        # los artefactos de ringing que cambian cuando la dimensión de scale salta.
        # Se fuerza número par para compatibilidad YUV420 / H.264.
        max_w = (int(w * zoom_max) + 1) // 2 * 2
        max_h = (int(h * zoom_max) + 1) // 2 * 2

        # Zoom oscila suavemente: n=0 → 1.0, n=PI*speed → zoom_max, n=2PI*speed → 1.0
        zoom_expr = f"1+{amplitude:.5f}*(1-cos(n/{speed:.1f}))/2"

        # Ventana de crop variable: a zoom=1.0 cubre toda la imagen preescalada;
        # a zoom=zoom_max cubre exactamente la resolución de salida.
        # La precisión es ±1 píxel (trunc), pero la escala final la distribuye
        # sobre los {w} píxeles de salida → cambio imperceptible.
        crop_w = f"trunc({max_w}/({zoom_expr}))"
        crop_h = f"trunc({max_h}/({zoom_expr}))"
        x_expr = f"({max_w}-{crop_w})/2"
        y_expr = f"({max_h}-{crop_h})/2"

        return (
            f"{label_in}"
            # Paso 1: escalar al tamaño máximo (FIJO, una sola vez)
            f"scale={max_w}:{max_h}:flags=lanczos+accurate_rnd+full_chroma_inp,"
            # Paso 2: recortar ventana variable por frame
            f"crop=w='{crop_w}':h='{crop_h}':x='{x_expr}':y='{y_expr}':eval=frame,"
            # Paso 3: escalar de vuelta a la resolución exacta de salida
            f"scale={w}:{h}:flags=lanczos+accurate_rnd+full_chroma_inp"
            f"{label_out}"
        )

