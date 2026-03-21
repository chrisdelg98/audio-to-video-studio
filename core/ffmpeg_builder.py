"""
FFmpegBuilder — Construye comandos FFmpeg a partir de parámetros y efectos.

Responsabilidades:
  - Componer el filter_complex final
  - Combinar efectos (plugin arch)
  - Generar el comando completo listo para subprocess
  - Generar comandos de preview corto (10s)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from effects.base_effect import BaseEffect
from effects.glitch_effect import GlitchEffect
from effects.overlay_effect import OverlayEffect
from effects.text_overlay_effect import TextOverlayEffect
from effects.zoom_effect import ZoomEffect


# Resoluciones soportadas
RESOLUTIONS: dict[str, tuple[int, int]] = {
    "1080p": (1920, 1080),
    "4K": (3840, 2160),
}

# FPS por defecto
DEFAULT_FPS = 30

# Modos de CPU → fracción de núcleos a usar
CPU_MODES: dict[str, float] = {
    "Low":    0.25,
    "Medium": 0.50,
    "High":   0.75,
    "Max":    1.00,
}

# Presets de encoding válidos para libx264
ENCODE_PRESETS = (
    "ultrafast", "superfast", "veryfast",
    "faster", "fast", "medium", "slow", "slower", "veryslow",
)


def calc_threads(cpu_mode: str) -> int:
    """Calcula el número de threads según el modo seleccionado.

    Usa os.cpu_count() para detectar los núcleos disponibles.
    Garantiza mínimo 1 thread aunque cpu_count() devuelva None.
    """
    total = os.cpu_count() or 2
    fraction = CPU_MODES.get(cpu_mode, 0.50)
    return max(1, int(total * fraction))


class FFmpegBuilder:
    """
    Construye comandos FFmpeg completos para generar un video a partir de:
    - Una imagen de fondo
    - Un archivo de audio
    - Efectos visuales configurados
    """

    def __init__(self, settings: dict[str, Any]) -> None:
        self.settings = settings
        width, height = RESOLUTIONS.get(settings.get("resolution", "1080p"), (1920, 1080))
        self.width = width
        self.height = height
        self.fps = DEFAULT_FPS

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def build_command(
        self,
        audio_path: str | Path,
        image_path: str | Path,
        output_path: str | Path,
        duration: float,
    ) -> list[str]:
        """
        Construye el comando FFmpeg completo para generar el video.

        Args:
            audio_path:  Ruta al archivo de audio fuente.
            image_path:  Ruta a la imagen de fondo.
            output_path: Ruta del archivo de video de salida.
            duration:    Duración del audio en segundos.

        Returns:
            Lista de strings lista para subprocess.run().
        """
        effects = self._build_effects()
        return self._assemble_command(
            audio_path=str(audio_path),
            image_path=str(image_path),
            output_path=str(output_path),
            duration=duration,
            effects=effects,
            preview=False,
        )

    def build_preview_command(
        self,
        audio_path: str | Path,
        image_path: str | Path,
        output_path: str | Path,
        duration: float,
        preview_duration: float = 10.0,
    ) -> list[str]:
        """
        Construye un comando FFmpeg para un preview corto (por defecto 10 segundos).
        """
        effects = self._build_effects()
        return self._assemble_command(
            audio_path=str(audio_path),
            image_path=str(image_path),
            output_path=str(output_path),
            duration=min(duration, preview_duration),
            effects=effects,
            preview=True,
        )

    # ------------------------------------------------------------------
    # Construcción de efectos
    # ------------------------------------------------------------------

    def _build_effects(self) -> list[BaseEffect]:
        """Instancia los efectos según la configuración."""
        effects: list[BaseEffect] = []

        # Zoom dinámico
        effects.append(
            ZoomEffect(
                enabled=self.settings.get("enable_zoom", True),
                zoom_max=float(self.settings.get("zoom_max", 1.05)),
                zoom_speed=int(self.settings.get("zoom_speed", 300)),
                width=self.width,
                height=self.height,
                fps=self.fps,
            )
        )

        # Glitch
        effects.append(
            GlitchEffect(
                enabled=self.settings.get("enable_glitch", False),
            )
        )

        # Overlay de video
        effects.append(
            OverlayEffect(
                enabled=self.settings.get("enable_overlay", False),
                overlay_path=self.settings.get("overlay_path", ""),
                opacity=float(self.settings.get("overlay_opacity", 0.5)),
            )
        )

        # Texto con glitch
        effects.append(TextOverlayEffect(self.settings))

        return effects

    # ------------------------------------------------------------------
    # Ensamblado del comando
    # ------------------------------------------------------------------

    def _assemble_command(
        self,
        audio_path: str,
        image_path: str,
        output_path: str,
        duration: float,
        effects: list[BaseEffect],
        preview: bool,
    ) -> list[str]:
        """Ensambla el comando FFmpeg completo."""

        fade_in = float(self.settings.get("fade_in", 2))
        fade_out = float(self.settings.get("fade_out", 2))
        crf = int(self.settings.get("crf", 18))
        normalize = self.settings.get("normalize_audio", False)

        # --- Determinar si hay overlay ---
        overlay_effect: OverlayEffect | None = None
        for eff in effects:
            if isinstance(eff, OverlayEffect) and eff.enabled and eff.params.get("overlay_path"):
                overlay_effect = eff
                break

        # --- Performance (threads + preset) ---
        cpu_mode = self.settings.get("cpu_mode", "Medium")
        threads = calc_threads(cpu_mode)
        encode_preset = self.settings.get("encode_preset", "slow")
        if encode_preset not in ENCODE_PRESETS:
            encode_preset = "slow"
        # Preview siempre usa ultrafast para velocidad
        effective_preset = "ultrafast" if preview else encode_preset

        # --- Inputs ---
        cmd: list[str] = ["ffmpeg", "-y", "-threads", str(threads)]

        # Input 0: imagen de fondo (loop)
        cmd += ["-loop", "1", "-i", image_path]

        # Input 1: audio
        cmd += ["-i", audio_path]

        # Input 2 (opcional): overlay
        overlay_input_index: int | None = None
        if overlay_effect is not None:
            overlay_input_index = 2
            cmd += ["-stream_loop", "-1", "-i", overlay_effect.params["overlay_path"]]

        # --- Duración del video ---
        cmd += ["-t", f"{duration:.3f}"]

        # --- Filtros de video ---
        filter_complex, final_video_label = self._build_filter_complex(
            effects=effects,
            duration=duration,
            overlay_input_index=overlay_input_index,
        )

        # --- Filtros de audio ---
        audio_filter = self._build_audio_filter(
            duration=duration,
            fade_in=fade_in,
            fade_out=fade_out,
            normalize=normalize,
        )

        cmd += ["-filter_complex", filter_complex]
        cmd += ["-map", final_video_label]
        cmd += ["-map", "1:a"]

        # Aplicar filtro de audio si hay fades o normalización
        if audio_filter:
            cmd += ["-af", audio_filter]

        # --- Codec y calidad ---
        cmd += [
            "-c:v", "libx264",
            "-threads", str(threads),
            "-preset", effective_preset,
            "-crf", str(crf),
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            output_path,
        ]

        return cmd

    def _build_filter_complex(
        self,
        effects: list[BaseEffect],
        duration: float,
        overlay_input_index: int | None,
    ) -> tuple[str, str]:
        """
        Construye el filter_complex y retorna (filter_string, label_final).
        """
        parts: list[str] = []

        # Escalar y recortar imagen base para llenar la resolución exacta
        scale_crop = (
            f"[0:v]scale={self.width}:{self.height}:"
            f"force_original_aspect_ratio=increase,"
            f"crop={self.width}:{self.height},"
            f"fps={self.fps}[vbase]"
        )
        parts.append(scale_crop)

        current_label = "[vbase]"
        label_counter = 0

        # Aplicar efectos secuencialmente
        # OverlayEffect se maneja al final (necesita stream extra)
        # TextOverlayEffect es un filtro puro (no necesita stream extra)
        for effect in effects:
            if isinstance(effect, OverlayEffect):
                continue

            if not effect.enabled:
                continue

            next_label = f"[v{label_counter}]"
            parts.append(effect.build_filter(current_label, next_label, duration))
            current_label = next_label
            label_counter += 1

        # Aplicar overlay al final si existe
        if overlay_input_index is not None:
            overlay_eff: OverlayEffect | None = None
            for eff in effects:
                if isinstance(eff, OverlayEffect) and eff.enabled:
                    overlay_eff = eff
                    break

            if overlay_eff is not None:
                # Preparar stream de overlay
                parts.append(overlay_eff.get_overlay_input_filter(overlay_input_index, duration))

                # Aplicar overlay
                next_label = f"[v{label_counter}]"
                parts.append(overlay_eff.build_filter(current_label, next_label, duration))
                current_label = next_label
                label_counter += 1

        filter_string = ";".join(parts)
        return filter_string, current_label

    @staticmethod
    def _build_audio_filter(
        duration: float,
        fade_in: float,
        fade_out: float,
        normalize: bool,
    ) -> str:
        """Construye el filtro de audio con fade in/out y normalización opcional."""
        filters: list[str] = []

        # Clamp fades para que no superen la duración disponible
        max_fade = duration / 3
        fi = min(fade_in, max_fade)
        fo = min(fade_out, max_fade)
        fade_out_start = max(0.0, duration - fo)

        if fi > 0:
            filters.append(f"afade=t=in:st=0:d={fi:.3f}")
        if fo > 0:
            filters.append(f"afade=t=out:st={fade_out_start:.3f}:d={fo:.3f}")
        if normalize:
            filters.append("loudnorm")

        return ",".join(filters)
