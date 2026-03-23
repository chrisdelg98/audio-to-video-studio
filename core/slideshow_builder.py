"""
SlideshowBuilder — Construye comandos FFmpeg para slideshow (secuencia de imágenes → video).

Soporta:
- Secuencia sin transición (concat demuxer, más rápido)
- Transición única (xfade): crossfade, fade negro, deslizar, difuminar, etc.
- Modo aleatorio: elige una transición distinta en cada corte
- Zoom suave por imagen (zoompan)
- Audio opcional (un archivo de música para todo el slideshow)
"""

from __future__ import annotations

import os
import random
import tempfile
from pathlib import Path
from typing import Any

# ── Constantes ──────────────────────────────────────────────────────

RESOLUTIONS: dict[str, tuple[int, int]] = {
    "720p":  (1280,  720),
    "1080p": (1920, 1080),
    "4K":    (3840, 2160),
}

DEFAULT_FPS = 30

CPU_MODES: dict[str, float] = {
    "Low":    0.25,
    "Medium": 0.50,
    "High":   0.75,
    "Max":    1.00,
}

# Duración del efecto de transición xfade en segundos
XFADE_DUR = 0.8

# Mapa display-name → nombre de transición en xfade filter
TRANSITION_MAP: dict[str, str] = {
    "Crossfade":     "dissolve",
    "Fade negro":    "fade",
    "Deslizar izq.": "slideleft",
    "Deslizar der.": "slideright",
    "Difuminar":     "hblur",
    "Empujar izq.":  "coverleft",
    "Empujar der.":  "coverright",
}

# Pool usado cuando el modo es "Aleatorio"
_RANDOM_POOL: list[str] = list(TRANSITION_MAP.values()) + [
    "wipeleft", "wiperight", "smoothleft", "smoothright",
]

# Opciones del desplegable en la UI (en este orden)
TRANSITION_CHOICES: list[str] = (
    ["Ninguna"] + list(TRANSITION_MAP.keys()) + ["Aleatorio"]
)


# ── Helpers ─────────────────────────────────────────────────────────

def _calc_threads(cpu_mode: str) -> int:
    total = os.cpu_count() or 2
    fraction = CPU_MODES.get(cpu_mode, 0.50)
    return max(1, int(total * fraction))


# ── Builder ─────────────────────────────────────────────────────────

class SlideshowBuilder:
    """Construye comandos FFmpeg completos para un slideshow."""

    def __init__(self, settings: dict[str, Any]) -> None:
        self.settings = settings
        w, h = RESOLUTIONS.get(settings.get("sl_resolution", "1080p"), (1920, 1080))
        self.width = w
        self.height = h

    # ── API pública ──────────────────────────────────────────────────

    def build_command(
        self,
        image_paths: list[Path],
        audio_path: Path | None,
        output_path: Path,
    ) -> tuple[list[str], Path | None]:
        """
        Construye el comando FFmpeg.

        Returns:
            (cmd, temp_file_or_None)
            El llamador debe borrar temp_file tras que el proceso finalice.
        """
        transition = self.settings.get("sl_transition", "Ninguna")
        duration = float(self.settings.get("sl_duration", 5.0))

        if transition == "Ninguna":
            return self._build_concat(image_paths, audio_path, output_path, duration)
        return self._build_xfade(image_paths, audio_path, output_path, duration, transition)

    # ── Filtros internos ─────────────────────────────────────────────

    def _scale_crop(self) -> str:
        """Filtro scale+crop centrado que rellena la resolución destino (replica FFmpeg real)."""
        return (
            f"scale={self.width}:{self.height}:"
            f"force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height},"
            f"setsar=1"
        )

    def _codec_args(self) -> list[str]:
        threads = _calc_threads(self.settings.get("sl_cpu_mode", "Medium"))
        crf     = self.settings.get("sl_crf", 18)
        preset  = self.settings.get("sl_encode_preset", "slow")
        gpu     = self.settings.get("sl_gpu_encoding", False)
        if gpu:
            return ["-c:v", "h264_nvenc", "-cq", str(crf), "-preset", "p5"]
        return [
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            "-threads", str(threads),
        ]

    def _audio_args(self, audio_path: Path | None) -> list[str]:
        if audio_path:
            return ["-c:a", "aac", "-b:a", "320k", "-shortest"]
        return ["-an"]

    # ── Estrategia: concat demuxer (sin transición) ──────────────────

    def _build_concat(
        self,
        image_paths: list[Path],
        audio_path: Path | None,
        output_path: Path,
        duration: float,
    ) -> tuple[list[str], Path]:
        """Usa concat demuxer para secuencia sin transición (el más rápido)."""
        tf = Path(tempfile.mktemp(suffix="_sl_concat.txt"))
        lines: list[str] = []
        for p in image_paths:
            safe = str(p).replace("\\", "/").replace("'", r"'\''")
            lines.append(f"file '{safe}'")
            lines.append(f"duration {duration:.3f}")
        # Duplicar última imagen sin duration para evitar frame negro al final
        last = str(image_paths[-1]).replace("\\", "/").replace("'", r"'\''")
        lines.append(f"file '{last}'")
        tf.write_text("\n".join(lines), encoding="utf-8")

        cmd: list[str] = ["ffmpeg", "-y"]
        cmd += ["-f", "concat", "-safe", "0", "-i", str(tf)]
        if audio_path:
            cmd += ["-i", str(audio_path)]

        vf = f"{self._scale_crop()},fps={DEFAULT_FPS}"
        cmd += ["-vf", vf]
        cmd += self._codec_args()
        cmd += self._audio_args(audio_path)
        cmd += ["-movflags", "+faststart", str(output_path)]
        return cmd, tf

    # ── Estrategia: filter_complex con xfade ────────────────────────

    def _build_xfade(
        self,
        image_paths: list[Path],
        audio_path: Path | None,
        output_path: Path,
        duration: float,
        transition: str,
    ) -> tuple[list[str], None]:
        """Genera filter_complex con xfade entre cada par de imágenes."""
        n           = len(image_paths)
        xd          = XFADE_DUR
        is_random   = (transition == "Aleatorio")
        xfade_name  = TRANSITION_MAP.get(transition, "dissolve")
        enable_zoom = self.settings.get("sl_enable_zoom", False)
        zoom_max    = float(self.settings.get("sl_zoom_max", 1.05))
        d_frames    = int(duration * DEFAULT_FPS)

        cmd: list[str] = ["ffmpeg", "-y"]
        # Cada imagen se loopea duration+xd segundos para que el overlap sea suficiente
        for p in image_paths:
            cmd += ["-loop", "1", "-t", f"{duration + xd:.3f}", "-i", str(p)]
        if audio_path:
            cmd += ["-i", str(audio_path)]

        sc = self._scale_crop()
        parts: list[str] = []

        # Preparar streams de cada imagen
        for i in range(n):
            if enable_zoom and d_frames > 0:
                zoom_inc = (zoom_max - 1.0) / d_frames
                zf = (
                    f"zoompan=z='min(zoom+{zoom_inc:.7f},{zoom_max:.4f})':"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d={d_frames}:s={self.width}x{self.height}:fps={DEFAULT_FPS}"
                )
                parts.append(f"[{i}:v]{sc},{zf}[v{i}]")
            else:
                parts.append(f"[{i}:v]{sc},fps={DEFAULT_FPS}[v{i}]")

        # Encadenar xfades
        # offset para xfade entre imagen i e i+1: (i+1) * (duration - xd)
        prev = "v0"
        for i in range(1, n):
            t      = random.choice(_RANDOM_POOL) if is_random else xfade_name
            offset = i * (duration - xd)
            label  = "xout" if i == n - 1 else f"x{i:02d}"
            parts.append(
                f"[{prev}][v{i}]xfade=transition={t}:"
                f"duration={xd}:offset={offset:.3f}[{label}]"
            )
            prev = label

        filter_complex = ";".join(parts)
        final_label    = "xout" if n > 1 else "v0"

        cmd += ["-filter_complex", filter_complex]
        cmd += ["-map", f"[{final_label}]"]
        if audio_path:
            cmd += ["-map", f"{n}:a"]

        cmd += self._codec_args()
        cmd += self._audio_args(audio_path)
        cmd += ["-movflags", "+faststart", str(output_path)]
        return cmd, None
