"""
GlitchEffect — Efecto de glitch digital con temporización aleatoria.

En lugar de un intervalo periódico exacto, usa probabilidad por grupo
de frames (chunk) para decidir cuándo activar el glitch.  Esto produce
intervalos pseudo-aleatorios que promedian el valor de 'speed' pero
con variación natural (nunca es exactamente igual).

Cada ráfaga de glitch afecta una región diferente del frame:
  - 25% de las ráfagas → full-frame
  - 75% de las ráfagas → bandas horizontales aleatorias (patrón sinusoidal
    con fase aleatoria por ráfaga → 3-4 franjas que varían de posición)

La intensidad de blend también varía por ráfaga (50-100%),
haciendo que algunos glitches sean sutiles y otros dramáticos.
"""

from effects.base_effect import BaseEffect


class GlitchEffect(BaseEffect):
    """
    Parámetros:
        intensity   Magnitud del desplazamiento RGB y ruido (1-20 px).
        speed       Intervalo promedio entre glitches (en frames).
        pulse       Duración del pulso en frames.
    """

    def __init__(
        self,
        enabled: bool = True,
        intensity: int = 4,
        speed: int = 90,
        pulse: int = 3,
    ) -> None:
        super().__init__(enabled=enabled, intensity=intensity, speed=speed, pulse=pulse)

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

        # Ruido digital proporcional a la intensidad (máx 30).
        noise_str = min(intensity * 2, 30)

        # Leve flicker de contraste/brillo.
        contrast   = 1.0 + intensity * 0.008
        brightness = intensity * 0.003

        # ── Expresión de blend con temporización aleatoria ──
        #
        # chunk: grupo de `pulse` frames que comparten la misma decisión.
        # random(seed) = hash determinista → mismo resultado para mismo seed
        # → todos los píxeles de un chunk reciben la misma decisión temporal.
        chunk = f"(floor(N/{pulse})*{pulse})"

        # Probabilidad de trigger por chunk
        # (promedia 1 ráfaga cada `speed` frames).
        prob = pulse / speed

        # Trigger temporal aleatorio por chunk.
        trigger = f"lt(random({chunk}*7919),{prob:.4f})"

        # 25% de ráfagas son full-frame; 75% solo bandas.
        full = f"lt(random({chunk}*5003),0.25)"

        # Bandas sinusoidales con fase aleatoria por ráfaga.
        # ~3-4 franjas cubriendo ~30% del frame; posición varía por burst.
        bands = f"lt(sin(Y*37.68/H+random({chunk}*3571)*6.28)*0.5+0.5,0.3)"

        # Región: full-frame OR dentro de una banda.
        region = f"max({full},{bands})"

        # Fuerza de blend variable por ráfaga (50-100%).
        strength = f"0.5+0.5*random({chunk}*1237)"

        blend_expr = f"if({trigger}*{region},A+(B-A)*({strength}),A)"

        return (
            # Dividir en rama limpia y rama glitch
            f"{label_in}split=2[_gbase][_graw];"
            # Rama glitch: shift RGB + ruido + eq
            f"[_graw]"
            f"rgbashift=rh={rh}:rv={rv}:bh={bh}:bv={bv},"
            f"noise=alls={noise_str}:allf=t,"
            f"eq=contrast={contrast:.4f}:brightness={brightness:.4f}"
            f"[_gmod];"
            # Blend: mezcla limpio/glitch según trigger + región
            f"[_gbase][_gmod]blend=all_expr='{blend_expr}'"
            f"{label_out}"
        )
