r"""
FFmpeg Setup — Localización e instalación automática de FFmpeg.

Busca ffmpeg/ffprobe en este orden:
1. Junto al ejecutable (.exe) o raíz del proyecto
2. %LOCALAPPDATA%\CreatorFlowStudio\ffmpeg\
3. PATH del sistema

Si no se encuentra en ninguno, descarga el build essentials de gyan.dev
a %LOCALAPPDATA%\CreatorFlowStudio\ffmpeg\ y lo agrega al PATH del usuario.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import winreg
import zipfile
from pathlib import Path
from typing import Callable, Optional
from urllib.request import urlopen, Request

from core.utils import get_app_dir

_FFMPEG_URL = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
)

ProgressCallback = Callable[[str, Optional[float]], None]

_INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "CreatorFlowStudio" / "ffmpeg"


def _report_progress(
    on_progress: ProgressCallback | None,
    message: str,
    progress: float | None = None,
) -> None:
    if on_progress:
        on_progress(message, progress)


def _exe_dir() -> Path:
    """Directorio del ejecutable (frozen) o raíz del proyecto."""
    return get_app_dir()


def _find_ffmpeg() -> str | None:
    """Retorna el directorio donde vive ffmpeg.exe, o None."""
    # 1. Junto al exe
    d = _exe_dir()
    if (d / "ffmpeg.exe").is_file():
        return str(d)

    # 2. Carpeta de instalación local
    bin_dir = _INSTALL_DIR / "bin"
    if (bin_dir / "ffmpeg.exe").is_file():
        return str(bin_dir)

    # 2b. Directamente en _INSTALL_DIR (sin subcarpeta bin)
    if (_INSTALL_DIR / "ffmpeg.exe").is_file():
        return str(_INSTALL_DIR)

    # 3. Ya en PATH
    if shutil.which("ffmpeg"):
        return ""  # cadena vacía = ya en PATH, no agregar nada

    return None


def _add_to_user_path(directory: str) -> None:
    """Agrega un directorio al PATH persistente del usuario (registro)."""
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Environment",
        0,
        winreg.KEY_READ | winreg.KEY_WRITE,
    )
    try:
        current, _ = winreg.QueryValueEx(key, "Path")
    except FileNotFoundError:
        current = ""

    # Evitar duplicados
    dirs = [d.strip() for d in current.split(";") if d.strip()]
    norm = os.path.normcase(os.path.normpath(directory))
    if any(os.path.normcase(os.path.normpath(d)) == norm for d in dirs):
        winreg.CloseKey(key)
        return

    dirs.append(directory)
    new_path = ";".join(dirs)
    winreg.SetValueEx(key, "Path", 0, winreg.REG_EXPAND_SZ, new_path)
    winreg.CloseKey(key)

    # Notificar al sistema del cambio (WM_SETTINGCHANGE)
    try:
        import ctypes
        HWND_BROADCAST = 0xFFFF
        WM_SETTINGCHANGE = 0x001A
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0, "Environment", 0x0002, 5000, None
        )
    except Exception:
        pass


def _download_ffmpeg(on_progress: ProgressCallback | None = None) -> str:
    """Descarga FFmpeg essentials y lo extrae. Retorna el directorio bin/.

    on_progress: callback(status_text: str, progress_percent: float | None).
    """
    _report_progress(on_progress, "Descargando FFmpeg essentials...", 0.0)

    req = Request(_FFMPEG_URL, headers={"User-Agent": "CreatorFlowStudio/1.0"})
    with urlopen(req, timeout=120) as resp:
        total_bytes = int(resp.headers.get("Content-Length") or 0)
        chunks: list[bytes] = []
        downloaded = 0

        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            chunks.append(chunk)
            downloaded += len(chunk)
            progress = None
            if total_bytes > 0:
                progress = min(85.0, (downloaded / total_bytes) * 85.0)
            _report_progress(on_progress, "Descargando FFmpeg essentials...", progress)

    data = b"".join(chunks)

    _report_progress(on_progress, "Extrayendo FFmpeg...", 90.0)

    _INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # El zip contiene una carpeta raíz como "ffmpeg-7.1-essentials_build/"
        # Necesitamos encontrar ffmpeg.exe dentro
        bin_entries = [
            n for n in zf.namelist()
            if n.endswith(("ffmpeg.exe", "ffprobe.exe"))
        ]
        total_entries = max(1, len(bin_entries))
        for index, entry in enumerate(bin_entries, start=1):
            filename = Path(entry).name
            dest = _INSTALL_DIR / filename
            with zf.open(entry) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
            progress = 90.0 + (index / total_entries) * 8.0
            _report_progress(on_progress, f"Extrayendo {filename}...", progress)

    ffmpeg_dir = str(_INSTALL_DIR)
    _report_progress(on_progress, "Configurando PATH...", 99.0)

    _add_to_user_path(ffmpeg_dir)
    return ffmpeg_dir


def ensure_ffmpeg(on_progress: ProgressCallback | None = None) -> str | None:
    """Asegura que ffmpeg esté disponible. Retorna directorio a agregar a PATH o None.

    Si FFmpeg no existe, lo descarga e instala automáticamente.
    on_progress: callback(status_text: str, progress_percent: float | None).

    Returns:
        Directorio con ffmpeg (para agregar a os.environ["PATH"]),
        cadena vacía si ya estaba en PATH, o None si falló.
    """
    ffmpeg_dir = _find_ffmpeg()

    if ffmpeg_dir is not None:
        # Encontrado (o ya en PATH)
        if ffmpeg_dir:
            os.environ["PATH"] = ffmpeg_dir + ";" + os.environ.get("PATH", "")
            _report_progress(on_progress, "FFmpeg encontrado en esta instalacion.", 100.0)
        else:
            _report_progress(on_progress, "FFmpeg ya estaba disponible en el sistema.", 100.0)
        return ffmpeg_dir

    # No encontrado — descargar
    try:
        ffmpeg_dir = _download_ffmpeg(on_progress=on_progress)
        os.environ["PATH"] = ffmpeg_dir + ";" + os.environ.get("PATH", "")
        _report_progress(on_progress, "FFmpeg instalado correctamente.", 100.0)
        return ffmpeg_dir
    except Exception as exc:
        _report_progress(on_progress, f"Error instalando FFmpeg: {exc}", None)
        return None
