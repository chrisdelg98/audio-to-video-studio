"""
GlitchEffect — Efecto de glitch digital eficiente con enable/disable per-frame.

Usa la opción `enable` de FFmpeg para activar/desactivar filtros por frame:
  - enable='lte(mod(n,speed),pulse)' → filtro activo solo durante el pulso
  - El 97% del tiempo ambos filtros son passthrough puro (costo = 0)

Filtros activos durante el pulso:
  - rgbashift: desplaza canales R y B en sentidos opuestos → efecto cromático
  - eq: bump de contraste/brillo → sensación de interferencia

Sin split, sin blend, sin evaluaciones per-pixel → rendimiento constante.
"""

from effects.base_effect import BaseEffect


class GlitchEffect(BaseEffect):
    """
    Parámetros:
        intensity   Magnitud del desplazamiento RGB (1-20 px).
        speed       Intervalo entre glitches (en frames).
        pulse       Duración del pulso en frames.
    """

    def __init__(
        self,
        enabled: bool = True,
        intensity: int = 4,
        speed: int = 90,
        pulse: int = 3,
        fast_mode: bool = False,
    ) -> None:
        super().__init__(
            enabled=enabled, intensity=intensity, speed=speed,
            pulse=pulse, fast_mode=fast_mode,
        )

    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        if not self.enabled:
            return f"{label_in}copy{label_out}"

        intensity = max(1, int(self.params["intensity"]))
        speed     = max(10, int(self.params["speed"]))
        pulse     = max(1, min(int(self.params["pulse"]), speed - 1))

        # RGB shift: canales R y B se desplazan en sentidos opuestos.
        rh = intensity
        bh = -intensity
        rv = intensity // 2
        bv = -(intensity // 2)

        # Leve flicker de contraste/brillo.
        contrast   = 1.0 + intensity * 0.008
        brightness = intensity * 0.003

        # enable='expr' → cuando false, el filtro es passthrough puro (0 costo).
        # Solo ~pulse/speed fracción de frames son procesados (~3%).
        trigger = f"lte(mod(n\\,{speed})\\,{pulse})"

        return (
            f"{label_in}"
            f"rgbashift=rh={rh}:rv={rv}:bh={bh}:bv={bv}:enable='{trigger}',"
            f"eq=contrast={contrast:.4f}:brightness={brightness:.4f}:enable='{trigger}'"
            f"{label_out}"
        )
