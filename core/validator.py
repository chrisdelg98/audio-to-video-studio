"""
Validator — Verificación de dependencias del sistema al arranque.

Comprueba que Python, FFmpeg y ffprobe están disponibles en PATH.
Retorna resultados estructurados para que la UI pueda informar al usuario.
"""

import shutil
import subprocess
import sys
from dataclasses import dataclass, field


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
        )
        first_line = (result.stdout or result.stderr or "").splitlines()
        return first_line[0] if first_line else "versión desconocida"
    except FileNotFoundError:
        return ""
    except subprocess.TimeoutExpired:
        return ""


def validate_environment() -> ValidationResult:
    """
    Valida todo el entorno requerido por la aplicación.

    Returns:
        ValidationResult con estado, mensajes y detalle por herramienta.
    """
    result = ValidationResult(ok=True)

    # --- Python ---
    py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    if py_ok:
        result.add("python", True, f"✔ Python {py_version}")
    else:
        result.add("python", False, f"✘ Python {py_version} — Se requiere Python 3.10 o superior.")

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
