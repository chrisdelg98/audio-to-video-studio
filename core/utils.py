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


def seconds_to_timestamp(seconds: float) -> str:
    """Convierte segundos a timestamp tipo H:MM:SS o M:SS (estilo capítulos)."""
    secs = max(0, int(round(float(seconds))))
    h = secs // 3600
    m = (secs % 3600) // 60
    s = secs % 60
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_audio_timeline(
    paths: list[Path],
    crossfade_s: float,
) -> list[dict[str, float | int | str]]:
    """Construye una línea de tiempo de canciones usando las duraciones de entrada.

    Campos por entrada:
      - index: índice 1-based
      - file_name: nombre de archivo original
      - title: stem del archivo
      - start_sec: inicio real del track en la mezcla
      - chapter_sec: inicio sugerido para capítulo (después del crossfade)
      - end_sec: fin del track
      - duration_sec: duración individual
    """
    timeline: list[dict[str, float | int | str]] = []
    if not paths:
        return timeline

    xf = max(0.0, float(crossfade_s))
    current_start = 0.0

    for idx, p in enumerate(paths, start=1):
        dur = float(get_audio_duration(p))
        if dur <= 0.0:
            continue

        audio_start = current_start
        audio_end = audio_start + dur

        if idx == 1:
            chapter_start = 0.0
        else:
            chapter_start = min(audio_end, audio_start + xf)

        timeline.append(
            {
                "index": idx,
                "file_name": p.name,
                "title": p.stem,
                "start_sec": round(audio_start, 3),
                "chapter_sec": round(chapter_start, 3),
                "end_sec": round(audio_end, 3),
                "duration_sec": round(dur, 3),
            }
        )

        current_start = max(audio_start, audio_end - xf)

    return timeline


def _timeline_to_chapters_text(timeline: list[dict[str, float | int | str]]) -> str:
    lines: list[str] = []
    for item in timeline:
        ts = seconds_to_timestamp(float(item.get("chapter_sec", 0.0)))
        title = str(item.get("title", "")).strip() or str(item.get("file_name", "")).strip() or "Track"
        lines.append(f"{ts} {title}")
    return "\n".join(lines).strip() + ("\n" if lines else "")


def _timeline_to_segments_text(timeline: list[dict[str, float | int | str]]) -> str:
    lines: list[str] = ["index|chapter_ts|start_sec|chapter_sec|end_sec|duration_sec|title|file_name"]
    for item in timeline:
        lines.append(
            "|".join(
                [
                    str(item.get("index", "")),
                    seconds_to_timestamp(float(item.get("chapter_sec", 0.0))),
                    f"{float(item.get('start_sec', 0.0)):.3f}",
                    f"{float(item.get('chapter_sec', 0.0)):.3f}",
                    f"{float(item.get('end_sec', 0.0)):.3f}",
                    f"{float(item.get('duration_sec', 0.0)):.3f}",
                    str(item.get("title", "")).replace("|", "/"),
                    str(item.get("file_name", "")).replace("|", "/"),
                ]
            )
        )
    return "\n".join(lines).strip() + "\n"


def export_audio_timeline_txts(
    timeline: list[dict[str, float | int | str]],
    chapters_path: str | Path,
    segments_path: str | Path,
) -> tuple[Path, Path]:
    """Exporta dos TXT de timeline: capítulos listos para pegar y tabla técnica."""
    ch_path = Path(chapters_path)
    sg_path = Path(segments_path)
    ch_path.parent.mkdir(parents=True, exist_ok=True)
    sg_path.parent.mkdir(parents=True, exist_ok=True)

    chapters_txt = _timeline_to_chapters_text(timeline)
    segments_txt = _timeline_to_segments_text(timeline)

    ch_path.write_text(chapters_txt, encoding="utf-8")
    sg_path.write_text(segments_txt, encoding="utf-8")
    return ch_path, sg_path


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
