"""
OverlayEffect — Efecto de overlay animado en loop sobre el video.

Superpone un video de overlay (con transparencia o blend) en loop
sobre el stream principal de video.
"""

from effects.base_effect import BaseEffect


class OverlayEffect(BaseEffect):
    """
    Superpone un video en loop con opacidad configurable.

    Parámetros:
        overlay_path: Ruta al archivo de video de overlay.
        opacity:      Valor de 0.0 (transparente) a 1.0 (opaco). Default 0.5.
        x:            Posición X del overlay (px o expr). Default 0.
        y:            Posición Y del overlay (px o expr). Default 0.
    """

    def __init__(
        self,
        enabled: bool = True,
        overlay_path: str = "",
        opacity: float = 0.5,
        x: str = "0",
        y: str = "0",
    ) -> None:
        super().__init__(
            enabled=enabled,
            overlay_path=overlay_path,
            opacity=opacity,
            x=x,
            y=y,
        )

    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        """
        Nota: Este efecto requiere una entrada de video adicional en FFmpeg.
        El índice de entrada del overlay debe ser pasado como parte del label_in.
        Por convención: label_in = "[vN]" y el overlay es el input "[ovr]".
        """
        if not self.enabled or not self.params.get("overlay_path"):
            return f"{label_in}copy{label_out}"

        opacity = self.params["opacity"]
        x = self.params["x"]
        y = self.params["y"]

        # El overlay se referencia como [ovr] tras ser preparado por el builder
        return (
            f"{label_in}[ovr]overlay="
            f"x={x}:y={y}:"
            f"shortest=1,"
            f"format=yuv420p"
            f"{label_out}"
        )

    def get_overlay_input_filter(self, input_index: int, duration: float) -> str:
        """
        Genera el filtro de entrada para el overlay (loop + escala + opacidad).

        Args:
            input_index: Índice del input de overlay en el comando FFmpeg.
            duration:    Duración total del video en segundos.

        Returns:
            Fragmento de filter_complex para preparar el stream de overlay.
        """
        opacity = self.params["opacity"]
        # loop=-1 hace loop infinito, cut en 0 para arrancar desde el primer frame
        return (
            f"[{input_index}:v]loop=-1:size=32767:start=0,"
            f"format=rgba,"
            f"colorchannelmixer=aa={opacity:.2f}"
            f"[ovr]"
        )
