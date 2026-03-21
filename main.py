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

# Asegurar que el directorio raíz del proyecto esté en PYTHONPATH,
# independientemente de desde dónde se ejecute el script.
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main() -> None:
    # Importación diferida para que los mensajes de error iniciales sean visibles
    try:
        from ui.app import AudioToVideoApp
    except ImportError as exc:
        print(
            f"\n[ERROR] No se pudieron importar los módulos de la aplicación:\n  {exc}\n\n"
            "Asegúrate de haber instalado las dependencias con:\n"
            "  pip install -r requirements.txt\n",
            file=sys.stderr,
        )
        sys.exit(1)

    app = AudioToVideoApp()
    app.mainloop()


if __name__ == "__main__":
    main()
