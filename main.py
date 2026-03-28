"""
Audio to Video Studio — Punto de entrada principal.

═══════════════════════════════════════════════════════════════
INSTALACIÓN DE DEPENDENCIAS
═══════════════════════════════════════════════════════════════

0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001. Crear entorno virtual (recomendado):
       python -m venv .venv
       .venv\\Scripts\\activate          # Windows
       source .venv/bin/activate        # macOS/Linux

2. Instalar dependencias Python:
       pip install -r requirements.txt

═══════════════════════════════════════════════════════════════
INSTALACIÓN DE FFmpeg
═══════════════════════════════════════════════════════════════

Windows:
  - Descarga desde https://ffmpeg.org/download.html
  - Extrae y agrega la carpeta bin/ al PATH del sistema.
  - Verifica con: ffmpeg -version

macOS (Homebrew):
  brew install ffmpeg

Linux (apt):
  sudo apt install ffmpeg

═══════════════════════════════════════════════════════════════
EJECUCIÓN
═══════════════════════════════════════════════════════════════

    python main.py

═══════════════════════════════════════════════════════════════
COMPILAR A .EXE (Windows, con PyInstaller)
═══════════════════════════════════════════════════════════════

    pip install pyinstaller
    pyinstaller --onefile --windowed --name "AudioToVideoStudio" main.py

El ejecutable aparecerá en dist/AudioToVideoStudio.exe

Nota: Incluir FFmpeg junto al .exe o asegurarse de que esté en PATH.

═══════════════════════════════════════════════════════════════
"""

import sys
import os
import traceback

# Asegurar que el directorio raíz del proyecto esté en PYTHONPATH,
# independientemente de desde dónde se ejecute el script.
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _startup_log_path() -> str:
    base = os.environ.get("LOCALAPPDATA") or ROOT
    log_dir = os.path.join(base, "CreatorFlowStudio")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception:
        return os.path.join(ROOT, "startup_error.log")
    return os.path.join(log_dir, "startup_error.log")


def _write_startup_log(message: str) -> None:
    try:
        with open(_startup_log_path(), "a", encoding="utf-8") as fh:
            fh.write(message + "\n")
    except Exception:
        pass


def _show_startup_error(title: str, message: str) -> None:
    try:
        import tkinter as tk
        import tkinter.messagebox as mbox

        root = tk.Tk()
        root.withdraw()
        mbox.showerror(title, message)
        root.destroy()
    except Exception:
        pass


def main() -> None:
    # Importación diferida para que los mensajes de error iniciales sean visibles
    try:
        from ui.app import AudioToVideoApp
    except ImportError as exc:
        details = (
            f"[STARTUP][IMPORT_ERROR] {exc}\n"
            f"Python: {sys.version}\n"
            f"Executable: {sys.executable}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )
        _write_startup_log(details)
        _show_startup_error(
            "CreatorFlow Studio",
            "No se pudieron cargar modulos de la aplicacion.\n"
            f"Detalle: {exc}\n\n"
            "Revisa startup_error.log en %LOCALAPPDATA%\\CreatorFlowStudio.",
        )
        print(
            f"\n[ERROR] No se pudieron importar los módulos de la aplicación:\n  {exc}\n\n"
            "Asegúrate de haber instalado las dependencias con:\n"
            "  pip install -r requirements.txt\n",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        app = AudioToVideoApp()
        app.mainloop()
    except Exception as exc:
        details = (
            f"[STARTUP][RUNTIME_ERROR] {exc}\n"
            f"Python: {sys.version}\n"
            f"Executable: {sys.executable}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )
        _write_startup_log(details)
        _show_startup_error(
            "CreatorFlow Studio",
            "La aplicacion fallo durante el arranque.\n"
            f"Detalle: {exc}\n\n"
            "Revisa startup_error.log en %LOCALAPPDATA%\\CreatorFlowStudio.",
        )
        raise


if __name__ == "__main__":
    main()
