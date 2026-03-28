"""
Validator — Verificación de dependencias del sistema al arranque.

Comprueba que Python, FFmpeg y ffprobe están disponibles en PATH.
Retorna resultados estructurados para que la UI pueda informar al usuario.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field

_STARTUPINFO = None
if os.name == "nt":
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW


@dataclass
class ValidationResult:
    ok: bool
    messages: list[str] = field(default_factory=list)
    details: dict[str, bool] = field(default_factory=dict)

    def add(self, name: str, passed: bool, msg: str) -> None:
        self.details[name] = passed
        self.messages.append(msg)
        if not passed:
            self.ok = False


def _run_version(cmd: str) -> str:
    """Ejecuta '<cmd> -version' y retorna la primera línea de salida."""
    try:
        result = subprocess.run(
            [cmd, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            startupinfo=_STARTUPINFO,
        )
        first_line = (result.stdout or result.stderr or "").splitlines()
        return first_line[0] if first_line else "versión desconocida"
    except FileNotFoundError:
        return ""
    except subprocess.TimeoutExpired:
        return ""


def _is_win7_profile() -> bool:
    """Detecta si la app se esta ejecutando con el perfil Win7 (Python 3.8)."""
    env_hint = (os.environ.get("CREATORFLOW_WIN7_PROFILE") or "").strip().lower()
    if env_hint in {"1", "true", "yes", "on"}:
        return True

    candidates = [
        os.environ.get("VIRTUAL_ENV", ""),
        getattr(sys, "prefix", ""),
        getattr(sys, "executable", ""),
    ]
    for value in candidates:
        v = (value or "").replace("\\", "/").lower()
        if "/.venv-win7" in v or v.endswith(".venv-win7"):
            return True
    return False


def validate_environment() -> ValidationResult:
    """
    Valida todo el entorno requerido por la aplicación.

    Returns:
        ValidationResult con estado, mensajes y detalle por herramienta.
    """
    result = ValidationResult(ok=True)

    # --- Python ---
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    is_frozen = bool(getattr(sys, "frozen", False))
    is_win7_profile = _is_win7_profile()
    min_required = (3, 8) if is_win7_profile else (3, 10)
    py_ok = is_frozen or sys.version_info >= min_required
    if py_ok:
        if is_frozen:
            result.add("python", True, f"✔ Python embebido {py_version}")
        elif is_win7_profile:
            result.add("python", True, f"✔ Python {py_version} (perfil Win7)")
        else:
            result.add("python", True, f"✔ Python {py_version}")
    else:
        required_text = "3.8" if is_win7_profile else "3.10"
        result.add("python", False, f"✘ Python {py_version} — Se requiere Python {required_text} o superior.")

    # --- FFmpeg ---
    ffmpeg_version = _run_version("ffmpeg")
    if ffmpeg_version:
        result.add("ffmpeg", True, f"✔ FFmpeg detectado: {ffmpeg_version}")
    else:
        result.add(
            "ffmpeg",
            False,
            "✘ FFmpeg no encontrado en PATH.\n"
            "  Instala FFmpeg desde https://ffmpeg.org/download.html\n"
            "  y asegúrate de que 'ffmpeg' esté disponible en tu PATH del sistema.",
        )

    # --- ffprobe ---
    ffprobe_version = _run_version("ffprobe")
    if ffprobe_version:
        result.add("ffprobe", True, f"✔ ffprobe detectado: {ffprobe_version}")
    else:
        result.add(
            "ffprobe",
            False,
            "✘ ffprobe no encontrado en PATH.\n"
            "  ffprobe viene incluido con FFmpeg. Verifica tu instalación.",
        )

    return result
