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


# Resoluciones soportadas (horizontal)
RESOLUTIONS: dict[str, tuple[int, int]] = {
    "720p": (1280, 720),
    "1080p": (1920, 1080),
    "4K": (3840, 2160),
}

# Resoluciones verticales 9:16 para Shorts
RESOLUTIONS_VERTICAL: dict[str, tuple[int, int]] = {
    "720p": (720, 1280),
    "1080p": (1080, 1920),
    "4K": (2160, 3840),
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

# Mapeo de presets x264 → NVENC (p1=fastest … p7=best quality)
_NVENC_PRESET_MAP: dict[str, str] = {
    "ultrafast":  "p1",
    "superfast":  "p1",
    "veryfast":   "p2",
    "faster":     "p3",
    "fast":       "p4",
    "medium":     "p4",
    "slow":       "p5",
    "slower":     "p6",
    "veryslow":   "p7",
}


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
        use_gpu = self.settings.get("gpu_encoding", False)
        effects.append(
            ZoomEffect(
                enabled=self.settings.get("enable_zoom", True),
                zoom_max=float(self.settings.get("zoom_max", 1.02)),
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
                intensity=int(self.settings.get("glitch_intensity", 4)),
                speed=int(self.settings.get("glitch_speed", 90)),
                pulse=int(self.settings.get("glitch_pulse", 3)),
                fast_mode=use_gpu,
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

        # Texto con glitch (estático)
        effects.append(TextOverlayEffect(self.settings))

        # Texto con glitch (dinámico) — el texto ya debe estar pre-resuelto en
        # settings["_resolved_dyn_text"] antes de construir el builder.
        if self.settings.get("enable_dyn_text_overlay", False):
            dyn_map = {
                "enable_text_overlay":   True,
                "text_content":          self.settings.get("_resolved_dyn_text", ""),
                "text_position":         self.settings.get("dyn_text_position", "Bottom"),
                "text_margin":           self.settings.get("dyn_text_margin", 40),
                "text_font_size":        self.settings.get("dyn_text_font_size", 36),
                "text_font":             self.settings.get("dyn_text_font", "Arial"),
                "text_color":            self.settings.get("dyn_text_color", "Blanco"),
                "text_glitch_intensity": self.settings.get("dyn_text_glitch_intensity", 3),
                "text_glitch_speed":     self.settings.get("dyn_text_glitch_speed", 4.0),
            }
            effects.append(TextOverlayEffect(dyn_map))

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

        # Encoder: GPU (NVENC) o CPU (libx264)
        use_gpu = self.settings.get("gpu_encoding", False)

        # --- Inputs ---
        cmd: list[str] = [
            "ffmpeg", "-y",
            "-threads", str(threads),
            "-filter_threads", str(threads),
            "-filter_complex_threads", str(threads),
        ]

        # Con GPU: aceleración de decodificación por hardware
        if use_gpu:
            cmd += ["-hwaccel", "auto"]

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
        if use_gpu:
            nvenc_preset = _NVENC_PRESET_MAP.get(effective_preset, "p5")
            if preview:
                nvenc_preset = "p1"

            # Escalar rendimiento NVENC según modo CPU
            # Max → máxima velocidad (2-pass lookahead, B-frames, más bitrate)
            # Medium/Low → conservador
            cmd += [
                "-c:v", "h264_nvenc",
                "-preset", nvenc_preset,
                "-tune", "hq",
                "-rc", "vbr",
                "-cq", str(crf),
                "-b:v", "8M",
                "-maxrate", "12M",
                "-bufsize", "16M",
                "-profile:v", "high",
                "-bf", "4" if cpu_mode == "Max" else "2",
                "-g", "250",
                "-spatial-aq", "1",
                "-temporal-aq", "1",
                "-aq-strength", "8",
                "-rc-lookahead", "32" if cpu_mode in ("Max", "High") else "16",
                "-multipass", "fullres" if cpu_mode in ("Max", "High") else "disabled",
                "-threads", str(threads),
            ]
        else:
            cmd += [
                "-c:v", "libx264",
                "-threads", str(threads),
                "-preset", effective_preset,
                "-crf", str(crf),
            ]

        audio_bitrate = str(self.settings.get("audio_bitrate", "320k"))
        cmd += [
            "-c:a", "aac",
            "-b:a", audio_bitrate,
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

    def build_short_cmd(
        self,
        audio_path: str | Path,
        image_path: str | Path,
        output_path: str | Path,
        start_s: float,
        duration_s: float,
    ) -> list[str]:
        """Build an FFmpeg command for a vertical Short (9:16).

        Uses sho_* settings keys; seeks into audio at start_s and renders
        duration_s seconds over a looped still image.
        """
        s = self.settings
        res_key = s.get("sho_resolution", "1080p")
        w, h = RESOLUTIONS_VERTICAL.get(res_key, (1080, 1920))
        crf = int(s.get("sho_crf", 18))
        encode_preset = s.get("sho_encode_preset", "slow")
        if encode_preset not in ENCODE_PRESETS:
            encode_preset = "slow"
        use_gpu = bool(s.get("sho_gpu_encoding", False))
        cpu_mode = s.get("sho_cpu_mode", "Medium")
        threads = calc_threads(cpu_mode)
        normalize = bool(s.get("sho_normalize_audio", False))
        fade_in = min(float(s.get("sho_fade_in", 0.5)), duration_s / 3)
        fade_out = min(float(s.get("sho_fade_out", 0.5)), duration_s / 3)

        # Map sho_* effect keys to standard keys for _build_effects
        short_settings: dict = {
            **s,
            "enable_zoom":           bool(s.get("sho_enable_zoom", True)),
            "zoom_max":              float(s.get("sho_zoom_max", 1.02)),
            "zoom_speed":            int(s.get("sho_zoom_speed", 300)),
            "enable_glitch":         bool(s.get("sho_enable_glitch", False)),
            "glitch_intensity":      int(s.get("sho_glitch_intensity", 4)),
            "glitch_speed":          int(s.get("sho_glitch_speed", 90)),
            "glitch_pulse":          int(s.get("sho_glitch_pulse", 3)),
            "enable_overlay":        False,
            "enable_text_overlay":   bool(s.get("sho_enable_text_overlay", False)),
            "text_content":          s.get("sho_text_content", ""),
            "text_position":         s.get("sho_text_position", "Bottom"),
            "text_margin":           int(s.get("sho_text_margin", 40)),
            "text_font_size":        int(s.get("sho_text_font_size", 36)),
            "text_font":             s.get("sho_text_font", "Arial"),
            "text_color":            s.get("sho_text_color", "Blanco"),
            "text_glitch_intensity": int(s.get("sho_text_glitch_intensity", 3)),
            "text_glitch_speed":     float(s.get("sho_text_glitch_speed", 4.0)),
            # Dynamic text overlay — use pre-resolved values from runner (sho_ prefix mapped)
            "enable_dyn_text_overlay":   bool(s.get("enable_dyn_text_overlay", bool(s.get("sho_enable_dyn_text_overlay", False)))),
            "_resolved_dyn_text":        s.get("_resolved_dyn_text", s.get("sho_dyn_text_content", "")),
            "dyn_text_position":         s.get("dyn_text_position", s.get("sho_dyn_text_position", "Bottom")),
            "dyn_text_margin":           int(s.get("dyn_text_margin", s.get("sho_dyn_text_margin", 40))),
            "dyn_text_font_size":        int(s.get("dyn_text_font_size", s.get("sho_dyn_text_font_size", 36))),
            "dyn_text_font":             s.get("dyn_text_font", s.get("sho_dyn_text_font", "Arial")),
            "dyn_text_color":            s.get("dyn_text_color", s.get("sho_dyn_text_color", "Blanco")),
            "dyn_text_glitch_intensity": int(s.get("dyn_text_glitch_intensity", s.get("sho_dyn_text_glitch_intensity", 3))),
            "dyn_text_glitch_speed":     float(s.get("dyn_text_glitch_speed", s.get("sho_dyn_text_glitch_speed", 4.0))),
            "gpu_encoding":          use_gpu,
        }

        # Temporary builder for vertical dimensions + remapped effects
        eff_builder = FFmpegBuilder.__new__(FFmpegBuilder)
        eff_builder.settings = short_settings
        eff_builder.width, eff_builder.height, eff_builder.fps = w, h, DEFAULT_FPS
        effects = eff_builder._build_effects()

        cmd = [
            "ffmpeg", "-y",
            "-threads", str(threads),
            "-filter_threads", str(threads),
            "-filter_complex_threads", str(threads),
        ]
        if use_gpu:
            cmd += ["-hwaccel", "auto"]

        cmd += ["-loop", "1", "-i", str(image_path)]            # input 0: image (looped)
        cmd += ["-ss", f"{start_s:.3f}", "-i", str(audio_path)]  # input 1: audio seek
        cmd += ["-t", f"{duration_s:.3f}"]

        filter_complex, final_label = eff_builder._build_filter_complex(
            effects, duration_s, None
        )
        audio_filter = FFmpegBuilder._build_audio_filter(
            duration_s, fade_in, fade_out, normalize
        )

        cmd += ["-filter_complex", filter_complex]
        cmd += ["-map", final_label, "-map", "1:a"]
        if audio_filter:
            cmd += ["-af", audio_filter]

        if use_gpu:
            nvenc_preset = _NVENC_PRESET_MAP.get(encode_preset, "p5")
            cmd += [
                "-c:v", "h264_nvenc", "-preset", nvenc_preset, "-tune", "hq",
                "-rc", "vbr", "-cq", str(crf),
                "-b:v", "8M", "-maxrate", "12M", "-bufsize", "16M",
                "-profile:v", "high", "-bf", "2", "-g", "250",
                "-spatial-aq", "1", "-temporal-aq", "1", "-aq-strength", "8",
                "-rc-lookahead", "16", "-threads", str(threads),
            ]
        else:
            cmd += [
                "-c:v", "libx264",
                "-threads", str(threads),
                "-preset", encode_preset,
                "-crf", str(crf),
            ]

        audio_bitrate = str(s.get("audio_bitrate", "320k"))
        cmd += [
            "-c:a", "aac", "-b:a", audio_bitrate,
            "-movflags", "+faststart",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]
        return cmd

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
