"""
VignetteEffect — Viñeta estática (oscurecimiento de bordes).

Usa el filtro `vignette` de FFmpeg con ángulo fijo (eval=init).
Se calcula la máscara una sola vez → costo ~0.

Cuando la imagen es estática (ATV/Shorts), se pre-aplica la viñeta
con PIL para eliminar por completo el filtro de FFmpeg (0 costo/frame).
"""

from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

from effects.base_effect import BaseEffect


class VignetteEffect(BaseEffect):
    """Viñeta estática de bordes."""

    def __init__(
        self,
        enabled: bool = False,
        intensity: float = 0.4,
        **kwargs,
    ) -> None:
        super().__init__(enabled=enabled)
        self.intensity = max(0.0, min(intensity, 1.0))

    def build_filter(self, label_in: str, label_out: str, duration: float) -> str:
        if not self.enabled or self.intensity <= 0:
            return ""
        # angle controla apertura: PI/2 = sin viñeta, 0 = máxima.
        # Mapeamos intensity 0..1.0 → angle PI/2..PI/5 (más intenso = ángulo menor)
        angle = 1.5708 - self.intensity * 1.0472  # PI/2 - intensity*(PI/2 - PI/5)
        return (
            f"{label_in}"
            f"vignette=angle={angle:.4f}"
            f"{label_out}"
        )

    # ------------------------------------------------------------------
    # PIL pre-bake (elimina viñeta del pipeline FFmpeg)
    # ------------------------------------------------------------------

    @staticmethod
    def make_vignette_mask(width: int, height: int, intensity: float):
        """Crea máscara de viñeta reutilizable (PIL Image modo RGB).

        Replica la fórmula exacta de FFmpeg vf_vignette.c:
            dist = hypot(x - midx, y - midy) / hypot(midx, midy)
            factor = cos(angle * dist)²

        Se calcula a 1/4 de resolución y se escala (gradiente suave).
        """
        from PIL import Image

        angle = 1.5708 - intensity * 1.0472

        FACTOR = 4
        lw = max(1, width // FACTOR)
        lh = max(1, height // FACTOR)
        midx = lw / 2.0
        midy = lh / 2.0
        inv_norm = 1.0 / math.hypot(midx, midy)

        _cos = math.cos
        _sqrt = math.sqrt

        data = bytearray(lw * lh)
        for y in range(lh):
            dy2 = (y - midy) ** 2
            row = y * lw
            for x in range(lw):
                dx = x - midx
                d = _sqrt(dx * dx + dy2) * inv_norm
                f = _cos(angle * d)
                data[row + x] = min(int(f * f * 255 + 0.5), 255)

        mask_l = Image.frombytes("L", (lw, lh), bytes(data))
        mask_l = mask_l.resize((width, height), Image.BILINEAR)
        return Image.merge("RGB", (mask_l, mask_l, mask_l))

    @staticmethod
    def bake_to_image(
        image_path: Path,
        width: int,
        height: int,
        intensity: float,
        mask=None,
    ) -> Path:
        """Pre-aplica viñeta a la imagen con PIL (= FFmpeg exacto).

        Args:
            image_path: Imagen fuente.
            width, height: Resolución objetivo (igual que FFmpeg).
            intensity: Intensidad 0.0–1.0.
            mask: Máscara pre-calculada (make_vignette_mask) para batch.

        Returns:
            Path a PNG temporal con viñeta integrada.
        """
        from PIL import Image, ImageChops

        if mask is None:
            mask = VignetteEffect.make_vignette_mask(width, height, intensity)

        # Abrir y escalar+recortar a resolución objetivo
        # (replica scale=W:H:force_original_aspect_ratio=increase,crop=W:H)
        img = Image.open(image_path).convert("RGB")
        src_w, src_h = img.size
        scale = max(width / src_w, height / src_h)
        new_w = round(src_w * scale)
        new_h = round(src_h * scale)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - width) // 2
        top = (new_h - height) // 2
        img = img.crop((left, top, left + width, top + height))

        # Aplicar viñeta via multiplicación de píxeles
        result = ImageChops.multiply(img, mask)

        fd, tmp_path = tempfile.mkstemp(suffix="_vignette.png")
        os.close(fd)
        result.save(tmp_path, "PNG")
        return Path(tmp_path)
