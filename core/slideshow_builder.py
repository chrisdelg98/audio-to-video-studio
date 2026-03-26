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

import math
import os
import random
import tempfile
from pathlib import Path
from typing import Any

from effects.text_overlay_effect import TextOverlayEffect
from core.utils import get_audio_duration

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

        # Expand image list so the slideshow covers the full audio duration
        image_paths = self._loop_images_to_audio(image_paths, duration, audio_path)

        if transition == "Ninguna":
            return self._build_concat(image_paths, audio_path, output_path, duration)
        return self._build_xfade(image_paths, audio_path, output_path, duration, transition)

    # ── Helpers ──────────────────────────────────────────────────────

    def _loop_images_to_audio(
        self,
        image_paths: list[Path],
        duration: float,
        audio_path: Path | None,
    ) -> list[Path]:
        """Repite la secuencia de imágenes las veces necesarias para cubrir la duración del audio.
        Si no hay audio, o no se puede leer su duración, devuelve la lista original.
        """
        if not audio_path or not image_paths:
            return image_paths
        try:
            audio_dur = get_audio_duration(audio_path)
        except Exception:
            return image_paths
        seq_dur = len(image_paths) * duration
        if seq_dur >= audio_dur:
            return image_paths
        loops = math.ceil(audio_dur / seq_dur)
        return image_paths * loops

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
            return ["-c:v", "h264_nvenc", "-cq", str(crf), "-preset", "p5",
                    "-pix_fmt", "yuv420p"]
        return [
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            "-pix_fmt", "yuv420p",
            "-threads", str(threads),
        ]

    def _audio_args(self, audio_path: Path | None) -> list[str]:
        if audio_path:
            return ["-c:a", "aac", "-b:a", "320k", "-shortest"]
        return ["-an"]

    def _text_overlay_filters(self, dummy_duration: float = 300.0) -> list[str]:
        """Devuelve lista de filtros drawtext para los overlays de texto activos."""
        filters: list[str] = []

        # Estático
        if self.settings.get("sl_enable_text_overlay", False):
            static_settings = {
                "enable_text_overlay":   True,
                "text_content":          self.settings.get("sl_text_content", ""),
                "text_position":         self.settings.get("sl_text_position", "Bottom"),
                "text_margin":           self.settings.get("sl_text_margin", 40),
                "text_font_size":        self.settings.get("sl_text_font_size", 36),
                "text_font":             self.settings.get("sl_text_font", "Arial"),
                "text_color":            self.settings.get("sl_text_color", "Blanco"),
                "text_glitch_intensity": self.settings.get("sl_text_glitch_intensity", 3),
                "text_glitch_speed":     self.settings.get("sl_text_glitch_speed", 4.0),
            }
            eff = TextOverlayEffect(static_settings)
            raw = eff.build_filter("[x]", "[y]", dummy_duration)
            # Extraer la parte del filtro (entre [x] y [y])
            inner = raw[len("[x]"):-len("[y]")]
            if inner != "copy":
                filters.append(inner)

        # Dinámico
        if self.settings.get("sl_enable_dyn_text_overlay", False):
            dyn_text = self._resolve_sl_dyn_text()
            dyn_settings = {
                "enable_text_overlay":   True,
                "text_content":          dyn_text,
                "text_position":         self.settings.get("sl_dyn_text_position", "Bottom"),
                "text_margin":           self.settings.get("sl_dyn_text_margin", 40),
                "text_font_size":        self.settings.get("sl_dyn_text_font_size", 36),
                "text_font":             self.settings.get("sl_dyn_text_font", "Arial"),
                "text_color":            self.settings.get("sl_dyn_text_color", "Blanco"),
                "text_glitch_intensity": self.settings.get("sl_dyn_text_glitch_intensity", 3),
                "text_glitch_speed":     self.settings.get("sl_dyn_text_glitch_speed", 4.0),
            }
            eff = TextOverlayEffect(dyn_settings)
            raw = eff.build_filter("[x]", "[y]", dummy_duration)
            inner = raw[len("[x]"):-len("[y]")]
            if inner != "copy":
                filters.append(inner)

        return filters

    def _resolve_sl_dyn_text(self) -> str:
        """Resuelve el texto dinámico para Slideshow según el modo seleccionado."""
        mode = self.settings.get("sl_dyn_text_mode", "Texto fijo")
        if mode == "Texto fijo":
            return self.settings.get("sl_dyn_text_content", "")
        elif mode == "Nombre de canción":
            # Para Slideshow usamos el nombre de salida configurado
            return self.settings.get("sl_output_name", "slideshow")
        else:  # Prefijo + Nombre de canción
            # Slideshow no tiene prefijo de naming; usamos el nombre de salida
            return self.settings.get("sl_output_name", "slideshow")

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
        # Lightweight effects
        sl_breath      = self.settings.get("sl_enable_breath", False)
        sl_light_zoom  = self.settings.get("sl_enable_light_zoom", False)
        sl_vignette    = self.settings.get("sl_enable_vignette", False)
        sl_color_shift = self.settings.get("sl_enable_color_shift", False)
        if sl_breath:
            bi = float(self.settings.get("sl_breath_intensity", 0.04))
            bs = float(self.settings.get("sl_breath_speed", 1.0))
            vf += f",eq=brightness='{bi}*sin({bs}*2*PI*t)':eval=frame"
        if sl_light_zoom:
            lzm = float(self.settings.get("sl_light_zoom_max", 1.04))
            lzs = float(self.settings.get("sl_light_zoom_speed", 0.5))
            half = (lzm - 1.0) / 2.0
            mid = 1.0 + half
            sw, sh = self.width, self.height
            vf += (
                f",scale="
                f"w='trunc(iw*max(1.01,{mid:.6f}+{half:.6f}*sin({lzs:.6f}*2*PI*t))/2)*2':"
                f"h='trunc(ih*max(1.01,{mid:.6f}+{half:.6f}*sin({lzs:.6f}*2*PI*t))/2)*2':"
                f"eval=frame,"
                f"crop={sw}:{sh}:(in_w-{sw})/2:(in_h-{sh})/2"
            )
        if sl_vignette:
            vi = float(self.settings.get("sl_vignette_intensity", 0.4))
            if vi > 0:
                angle = 1.5708 - vi * 1.0472
                vf += f",vignette=angle={angle:.4f}"
        if sl_color_shift:
            ca = float(self.settings.get("sl_color_shift_amount", 15.0))
            cs = float(self.settings.get("sl_color_shift_speed", 0.5))
            vf += f",hue=h='{ca:.1f}*sin({cs}*2*PI*t)'"
        text_filters = self._text_overlay_filters()
        if text_filters:
            vf += "," + ",".join(text_filters)
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
        d_frames    = int(duration * DEFAULT_FPS)

        # Lightweight effects settings
        sl_breath      = self.settings.get("sl_enable_breath", False)
        sl_light_zoom  = self.settings.get("sl_enable_light_zoom", False)
        sl_vignette    = self.settings.get("sl_enable_vignette", False)
        sl_color_shift = self.settings.get("sl_enable_color_shift", False)

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
            chain = [sc, f"fps={DEFAULT_FPS}"]
            # Lightweight effects (applied after scale/fps)
            if sl_breath:
                bi = float(self.settings.get("sl_breath_intensity", 0.04))
                bs = float(self.settings.get("sl_breath_speed", 1.0))
                chain.append(f"eq=brightness='{bi}*sin({bs}*2*PI*t)':eval=frame")
            if sl_light_zoom:
                lzm = float(self.settings.get("sl_light_zoom_max", 1.04))
                lzs = float(self.settings.get("sl_light_zoom_speed", 0.5))
                half = (lzm - 1.0) / 2.0
                mid = 1.0 + half
                sw, sh = self.width, self.height
                chain.append(
                    f"scale="
                    f"w='trunc(iw*max(1.01,{mid:.6f}+{half:.6f}*sin({lzs:.6f}*2*PI*t))/2)*2':"
                    f"h='trunc(ih*max(1.01,{mid:.6f}+{half:.6f}*sin({lzs:.6f}*2*PI*t))/2)*2':"
                    f"eval=frame,"
                    f"crop={sw}:{sh}:(in_w-{sw})/2:(in_h-{sh})/2"
                )
            if sl_vignette:
                vi = float(self.settings.get("sl_vignette_intensity", 0.4))
                if vi > 0:
                    angle = 1.5708 - vi * 1.0472
                    chain.append(f"vignette=angle={angle:.4f}")
            if sl_color_shift:
                ca = float(self.settings.get("sl_color_shift_amount", 15.0))
                cs = float(self.settings.get("sl_color_shift_speed", 0.5))
                chain.append(f"hue=h='{ca:.1f}*sin({cs}*2*PI*t)'")
            parts.append(f"[{i}:v]{','.join(chain)}[v{i}]")

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

        # Texto overlay (estático y/o dinámico)
        total_dur = n * duration
        text_filters = self._text_overlay_filters(dummy_duration=total_dur)
        if text_filters:
            filter_complex += f";[{final_label}]{','.join(text_filters)}[vtxt]"
            final_label = "vtxt"

        cmd += ["-filter_complex", filter_complex]
        cmd += ["-map", f"[{final_label}]"]
        if audio_path:
            cmd += ["-map", f"{n}:a"]

        cmd += self._codec_args()
        cmd += self._audio_args(audio_path)
        cmd += ["-movflags", "+faststart", str(output_path)]
        return cmd, None
