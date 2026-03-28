"""
Utils — Utilidades compartidas del proyecto.

Incluye:
- Detección de duración de audio via ffprobe
- Generación de nombres de archivo de salida
- Validación de archivos de audio/imagen
- Normalización de rutas
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

_STARTUPINFO = None
if os.name == "nt":
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW


def get_bundle_dir() -> Path:
    """Directorio de recursos empaquetados (_MEIPASS) o raíz del proyecto."""
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent


def get_app_dir() -> Path:
    """Directorio del ejecutable (frozen) o raíz del proyecto (dev).

    Usar para archivos escribibles como config/settings.json."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


SUPPORTED_AUDIO = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}
SUPPORTED_IMAGE = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}


def get_audio_duration(file_path: str | Path) -> float:
    """
    Retorna la duración en segundos de un archivo de audio usando ffprobe.

    Raises:
        RuntimeError: Si ffprobe falla o no puede determinar la duración.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        str(file_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                               startupinfo=_STARTUPINFO)
        if result.returncode != 0:
            raise RuntimeError(f"ffprobe error: {result.stderr.strip()}")
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
        return duration
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"No se pudo leer la duración de '{file_path}': {exc}") from exc
    except FileNotFoundError:
        raise RuntimeError("ffprobe no está disponible en PATH.")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"ffprobe tardó demasiado procesando '{file_path}'.")


def get_audio_files(folder: str | Path) -> list[Path]:
    """
    Retorna una lista ordenada de archivos de audio soportados dentro de una carpeta.
    """
    folder = Path(folder)
    files = [
        f for f in sorted(folder.iterdir())
        if f.is_file() and f.suffix.lower() in SUPPORTED_AUDIO
    ]
    return files


def get_image_files(folder: str | Path) -> list[Path]:
    """
    Retorna una lista ordenada de archivos de imagen soportados dentro de una carpeta.
    """
    folder = Path(folder)
    return [
        f for f in sorted(folder.iterdir())
        if f.is_file() and f.suffix.lower() in SUPPORTED_IMAGE
    ]


def is_valid_image(path: str | Path) -> bool:
    """Verifica si el archivo es una imagen con extensión soportada."""
    return Path(path).suffix.lower() in SUPPORTED_IMAGE


def is_valid_audio(path: str | Path) -> bool:
    """Verifica si el archivo es un audio con extensión soportada."""
    return Path(path).suffix.lower() in SUPPORTED_AUDIO


def build_output_filename(index: int, audio_path: str | Path, output_folder: str | Path) -> Path:
    """
    Genera el nombre de salida en formato '01 - Nombre.mp4'.

    Args:
        index: Número de orden (1-based).
        audio_path: Ruta del archivo de audio fuente.
        output_folder: Carpeta de destino.

    Returns:
        Path completo del archivo de salida.
    """
    stem = Path(audio_path).stem
    # Sanitiza el nombre para evitar caracteres problemáticos
    safe_stem = re.sub(r'[<>:"/\\|?*]', "_", stem)
    filename = f"{index:02d} - {safe_stem}.mp4"
    return Path(output_folder) / filename


def ensure_dir(path: str | Path) -> Path:
    """Crea el directorio si no existe y lo retorna como Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def format_duration(seconds: float) -> str:
    """Convierte segundos a formato HH:MM:SS para mostrar en UI."""
    secs = int(seconds)
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _run_merge_cmd(cmd: list[str]) -> None:
    """Ejecuta un comando FFmpeg de merge; lanza RuntimeError si falla."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        startupinfo=_STARTUPINFO,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg merge falló (código {result.returncode}):\n{result.stderr[-2000:]}"
        )


def merge_audio_files(
    paths: list[Path],
    crossfade_s: float,
    out_path: Path,
    on_log: Callable[[str], None] | None = None,
) -> Path:
    """Combina N archivos de audio en un único WAV (PCM s16le).

    crossfade_s == 0  →  concat demuxer (bit-perfect, sin re-encode).
    crossfade_s > 0   →  filtro acrossfade encadenado (fade triangular en cada empalme).

    Retorna out_path.
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if len(paths) == 1:
        if on_log:
            on_log("    Audio único: convirtiendo a WAV…")
        _run_merge_cmd([
            "ffmpeg", "-y", "-i", str(paths[0]),
            "-acodec", "pcm_s16le", str(out_path),
        ])
        return out_path

    if crossfade_s <= 0.0:
        # Concat demuxer — fastest, no quality loss
        concat_path = out_path.with_suffix(".concat_list.txt")
        try:
            with open(concat_path, "w", encoding="utf-8") as fh:
                for p in paths:
                    safe = str(p.resolve()).replace("\\", "/")
                    fh.write(f"file '{safe}'\n")
            if on_log:
                on_log(f"    Concatenando {len(paths)} audios (sin crossfade)…")
            _run_merge_cmd([
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_path),
                "-acodec", "pcm_s16le",
                str(out_path),
            ])
        finally:
            try:
                concat_path.unlink(missing_ok=True)
            except OSError:
                pass
        return out_path

    # acrossfade filter chain: [0:a][1:a]acrossfade=...[m01]; [m01][2:a]acrossfade=...[m02]; ...
    n = len(paths)
    inputs: list[str] = []
    for p in paths:
        inputs += ["-i", str(p)]

    filter_parts: list[str] = []
    prev = "[0:a]"
    for i in range(1, n):
        label_out = f"[m{i:02d}]" if i < n - 1 else "[outa]"
        filter_parts.append(
            f"{prev}[{i}:a]acrossfade=d={crossfade_s}:c1=tri:c2=tri{label_out}"
        )
        prev = label_out

    filter_complex = ";".join(filter_parts)
    if on_log:
        on_log(f"    Mezclando {n} audios con crossfade de {crossfade_s}s…")
    _run_merge_cmd(
        ["ffmpeg", "-y"]
        + inputs
        + [
            "-filter_complex", filter_complex,
            "-map", "[outa]",
            "-acodec", "pcm_s16le",
            str(out_path),
        ]
    )
    return out_path
