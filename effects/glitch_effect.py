"""
GlitchEffect — Efecto de glitch leve usando el filtro rgbashift de FFmpeg.

Desplaza levemente los canales RGB para simular artefactos digitales sutiles
sin saturar visualmente el video.
"""

from effects.base_effect import BaseEffect


class GlitchEffect(BaseEffect):
    """
    Aplica un glitch cromático leve usando rgbashift.

    Parámetros:
        rh: Desplazamiento horizontal del canal rojo (px).
        bh: Desplazamiento horizontal del canal azul (px).
        rv: Desplazamiento vertical del canal rojo (px).
        bv: Desplazamiento vertical del canal azul (px).
    """

    def __init__(
        self,
        enabled: bool = True,
        rh: int = 2,
        bh: int = -2,
        rv: int = 1,
        bv: int = -1,
    ) -> None:
        super().__init__(enabled=enabled, rh=rh, bh=bh, rv=rv, bv=bv)

    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        if not self.enabled:
            return f"{label_in}copy{label_out}"

        rh = self.params["rh"]
        bh = self.params["bh"]
        rv = self.params["rv"]
        bv = self.params["bv"]

        return (
            f"{label_in}rgbashift="
            f"rh={rh}:bh={bh}:rv={rv}:bv={bv}"
            f"{label_out}"
        )
