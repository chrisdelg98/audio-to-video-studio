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

        # Ease-in/ease-out con (1-cos)/2:
        #   n=0              → zoom = 1.0      (sin zoom)
        #   n = PI*speed     → zoom = zoom_max (pico suave)
        #   n = 2*PI*speed   → zoom = 1.0      (regresa suave)
        zoom_expr = f"1+{amplitude:.5f}*(1-cos(n/{speed:.1f}))/2"

        # scale agranda el frame según zoom_expr; trunc()*2 garantiza
        # dimensiones pares (requerido por H.264/libx264).
        scale_w = f"trunc(iw*({zoom_expr})*0.5)*2"
        scale_h = f"trunc(ih*({zoom_expr})*0.5)*2"

        # crop recorta el centro exacto al tamaño de salida deseado.
        # eval=frame es requerido en FFmpeg 8+ para que 'n' se evalúe por frame
        # (el modo default 'init' no permite variables de frame como n, t, pos).
        return (
            f"{label_in}"
            f"scale=w='{scale_w}':h='{scale_h}':flags=lanczos+accurate_rnd+full_chroma_inp:eval=frame,"
            f"crop={w}:{h}"
            f"{label_out}"
        )

