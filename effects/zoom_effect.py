"""
ZoomEffect — Efecto de zoom dinámico suave usando zoompan de FFmpeg.

Genera un zoom que oscila sinusoidalmente para dar sensación de movimiento
sin cortes abruptos (loop suave).
"""

from effects.base_effect import BaseEffect


class ZoomEffect(BaseEffect):
    """
    Aplica un zoom dinámico usando el filtro zoompan de FFmpeg.

    Parámetros:
        zoom_max:   Factor máximo de zoom sobre 1.0 (ej. 1.05 → 5% de zoom).
        zoom_speed: Período de la oscilación en frames. Mayor = más lento.
        width:      Anchura del frame de salida en píxeles.
        height:     Altura del frame de salida en píxeles.
        fps:        Frames por segundo del video de salida.
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
        fps = self.params["fps"]

        # Amplitud del zoom sobre 1.0 (ej. 0.05 para 5%)
        amplitude = zoom_max - 1.0

        # zoompan genera frames uno a uno; 'on' es el número de frame de salida
        zoom_expr = f"1+{amplitude:.4f}*sin(on/{speed})"

        # d=1 procesa un frame de entrada por iteración (imagen estática → loop)
        return (
            f"{label_in}zoompan="
            f"z='{zoom_expr}':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d=1:"
            f"s={w}x{h}:"
            f"fps={fps}"
            f"{label_out}"
        )
