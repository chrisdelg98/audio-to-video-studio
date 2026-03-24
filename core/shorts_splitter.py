"""
shorts_splitter — Fragment distribution logic for Shorts generation.

Provides pure functions (no I/O) for:
  - Suggesting how many shorts to generate given audio length + short duration
  - Distributing start-times equitably without out-of-bounds overlap
  - Validating generation requests
"""

from __future__ import annotations

import math


def suggest_quantity(audio_s: float, short_s: float) -> int:
    """Suggest how many shorts can be extracted.

    Rules:
        • short_s 30–44s  →  3 shorts per complete minute of audio
        • short_s 45–59s  →  2 shorts per complete minute of audio
    Always returns at least 1.
    """
    if audio_s <= 0 or short_s <= 0 or short_s >= audio_s:
        return 1
    mins = audio_s / 60.0
    rate = 3 if short_s <= 44 else 2
    return max(1, math.floor(mins * rate))


def distribute_fragments(audio_s: float, short_s: float, qty: int) -> list[float]:
    """Return *qty* start-times (seconds) distributed equitably across the audio.

    Guarantees:
        • starts[0] == 0.0   (always starts from t=0)
        • starts[i] + short_s <= audio_s  (never out of bounds)
        • No duplicates when qty <= floor(audio_s - short_s) + 1
    """
    if qty <= 0:
        return []
    total_usable = max(0.0, audio_s - short_s)
    if qty == 1:
        return [0.0]
    step = total_usable / (qty - 1)
    return [round(i * step, 3) for i in range(qty)]


def validate_request(
    audio_s: float, short_s: float, qty: int
) -> tuple[bool, str]:
    """Validate that the generation request is feasible.

    Returns:
        (ok, message)
            ok=False   → blocking error; message contains the reason.
            ok=True    → valid; message may carry a non-blocking warning.
    """
    if short_s <= 0:
        return False, "La duración del short debe ser mayor a 0."
    if audio_s <= 0:
        return False, "No se pudo determinar la duración del audio."
    if short_s >= audio_s:
        return False, (
            f"El short ({short_s:.0f}s) es igual o más largo que el audio "
            f"({audio_s:.1f}s). Elige una duración menor."
        )
    if qty <= 0:
        return False, "La cantidad de shorts debe ser al menos 1."
    sugerido = suggest_quantity(audio_s, short_s)
    if qty > sugerido * 2:
        return True, (
            f"Advertencia: se solicitaron {qty} shorts pero se sugieren {sugerido}. "
            "Los fragmentos se solaparán significativamente."
        )
    return True, ""
