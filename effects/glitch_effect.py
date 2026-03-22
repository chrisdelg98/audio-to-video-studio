"""
GlitchEffect — Efecto de glitch digital con patrones rotativos.

Usa `enable` de FFmpeg para activar/desactivar filtros por frame:
  - enable='lte(mod(n,speed),pulse)' → filtro activo solo durante el pulso
  - El 97% del tiempo todos los filtros son passthrough puro (costo ≈ 0)

4 patrones de glitch rotan por ciclo para evitar repetición:
  0. Diagonal estándar (rh+rv desplazados)
  1. Horizontal fuerte (solo rh/bh, 1.4× intensidad)
  2. Vertical (solo rv/bv)
  3. Diagonal inverso suave (dirección opuesta, 0.7× intensidad)

Cada ciclo de `speed` frames activa un patrón diferente vía:
  enable='pulse_trigger * eq(mod(floor(n/speed), 4), k)'

Solo 1 de los 4 rgbashift procesa píxeles por pulso; los otros 3
son passthrough. El eq es compartido para todos los pulsos.
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

        I = intensity

        # 4 patrones con dirección e intensidad variada
        # (rh, rv, bh, bv) — rotan cada ciclo de speed frames
        patterns = [
            ( I,             max(1, I//2),  -I,             -max(1, I//2)),  # diagonal
            ( int(I * 1.4),  0,             -int(I * 1.4),  0),             # horizontal fuerte
            ( 0,             I,              0,             -I),             # vertical
            (-int(I * 0.7),  max(1, I//2),   int(I * 0.7), -max(1, I//2)), # reverso suave
        ]

        # Trigger base: solo durante el pulso (~3% de frames)
        pulse_trigger = f"lte(mod(n\\,{speed})\\,{pulse})"

        # Cada patrón se activa en su ciclo correspondiente
        # cycle = floor(n/speed), pattern_idx = mod(cycle, 4)
        parts = []
        for k, (rh, rv, bh, bv) in enumerate(patterns):
            trigger = (
                f"{pulse_trigger}"
                f"*eq(mod(floor(n/{speed})\\,{len(patterns)})\\,{k})"
            )
            parts.append(
                f"rgbashift=rh={rh}:rv={rv}:bh={bh}:bv={bv}:enable='{trigger}'"
            )

        # Eq compartido: leve flicker durante cualquier pulso
        contrast   = 1.0 + intensity * 0.008
        brightness = intensity * 0.003
        parts.append(
            f"eq=contrast={contrast:.4f}:brightness={brightness:.4f}"
            f":enable='{pulse_trigger}'"
        )

        return f"{label_in}" + ",".join(parts) + f"{label_out}"
