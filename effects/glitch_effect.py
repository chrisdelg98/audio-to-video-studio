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
        fast      = bool(self.params.get("fast_mode", False))

        # RGB shift: canales R y B se desplazan en sentidos opuestos.
        rh = intensity
        bh = -intensity
        rv = intensity // 2
        bv = -(intensity // 2)

        # Leve flicker de contraste/brillo.
        contrast   = 1.0 + intensity * 0.008
        brightness = intensity * 0.003

        if fast:
            # ── Fast path (GPU mode): sin random() ni noise ──
            # Trigger: mod(N,speed) — determinista, ~0 costo
            # Bandas: sin(Y) con fase basada en burst index (golden ratio
            # 2.39 rad ≈ 137.5° → patrón no repetitivo, parece aleatorio)
            burst = f"floor(N/{max(pulse, 1)})"
            trigger = f"lte(mod(N,{speed}),{pulse})"
            # 25% full-frame (cada 4 bursts), 75% bandas sinusoidales
            full_frame = f"lte(mod({burst},4),0)"
            bands = f"gt(sin(Y*12.57/H+{burst}*2.39)*0.5+0.5,0.6)"
            region = f"max({full_frame},{bands})"

            blend_expr = f"if({trigger}*{region},B,A)"

            return (
                f"{label_in}split=2[_gbase][_graw];"
                f"[_graw]"
                f"rgbashift=rh={rh}:rv={rv}:bh={bh}:bv={bv},"
                f"eq=contrast={contrast:.4f}:brightness={brightness:.4f}"
                f"[_gmod];"
                f"[_gbase][_gmod]blend=all_expr='{blend_expr}'"
                f"{label_out}"
            )

        # ── Quality path (CPU mode): random timing + noise + bandas ──
        noise_str = min(intensity * 2, 30)

        chunk = f"(floor(N/{pulse})*{pulse})"
        prob = pulse / speed

        trigger = f"lt(random({chunk}*7919),{prob:.4f})"
        full = f"lt(random({chunk}*5003),0.25)"
        bands = f"lt(sin(Y*37.68/H+random({chunk}*3571)*6.28)*0.5+0.5,0.3)"
        region = f"max({full},{bands})"
        strength = f"0.5+0.5*random({chunk}*1237)"

        blend_expr = f"if({trigger}*{region},A+(B-A)*({strength}),A)"

        return (
            f"{label_in}split=2[_gbase][_graw];"
            f"[_graw]"
            f"rgbashift=rh={rh}:rv={rv}:bh={bh}:bv={bv},"
            f"noise=alls={noise_str}:allf=t,"
            f"eq=contrast={contrast:.4f}:brightness={brightness:.4f}"
            f"[_gmod];"
            f"[_gbase][_gmod]blend=all_expr='{blend_expr}'"
            f"{label_out}"
        )
