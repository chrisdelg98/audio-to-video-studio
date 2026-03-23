"""
SlideshowRunner — Ejecuta la generación de slideshow en un hilo dedicado.

Un job único: N imágenes → un archivo de video.
Usa SlideshowBuilder para construir el comando FFmpeg.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable

from core.slideshow_builder import SlideshowBuilder
from core.utils import ensure_dir

# Ocultar consola en modo windowed (PyInstaller --windowed)
_STARTUPINFO = None
if os.name == "nt":
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW


class SlideshowRunner:
    """
    Ejecuta la generación de slideshow en un hilo de fondo.

    Uso:
        runner = SlideshowRunner(settings, on_log, on_finished)
        runner.start(image_paths, audio_path, output_path)
        # para cancelar:
        runner.cancel()
    """

    def __init__(
        self,
        settings: dict[str, Any],
        on_log: Callable[[str], None],
        on_finished: Callable[[bool], None],
    ) -> None:
        self.settings    = settings
        self.on_log      = on_log
        self.on_finished = on_finished

        self._cancel_event   = threading.Event()
        self._thread: threading.Thread | None = None
        self._current_proc: subprocess.Popen | None = None  # type: ignore[type-arg]

    # ── API pública ──────────────────────────────────────────────────

    def start(
        self,
        image_paths: list[Path],
        audio_path: Path | None,
        output_path: Path,
    ) -> None:
        """Inicia el procesamiento en un hilo de fondo."""
        if self._thread and self._thread.is_alive():
            self.on_log("⚠ Ya hay un slideshow en ejecución.")
            return

        self._cancel_event.clear()
        ensure_dir(output_path.parent)

        self._thread = threading.Thread(
            target=self._run,
            args=(image_paths, audio_path, output_path),
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        """Solicita cancelar el proceso en curso."""
        self._cancel_event.set()
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
            except OSError:
                pass
        self.on_log("🛑 Cancelación de slideshow solicitada...")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── Procesamiento ────────────────────────────────────────────────

    def _run(
        self,
        image_paths: list[Path],
        audio_path: Path | None,
        output_path: Path,
    ) -> None:
        builder = SlideshowBuilder(self.settings)

        self.on_log(f"▶ Construyendo slideshow con {len(image_paths)} imágenes...")
        self.on_log(f"  → Transición: {self.settings.get('sl_transition', 'Ninguna')}")
        self.on_log(f"  → Duración por imagen: {self.settings.get('sl_duration', 5)}s")
        self.on_log(f"  → Resolución: {self.settings.get('sl_resolution', '1080p')}")
        self.on_log(f"  → Salida: {output_path.name}")

        try:
            cmd, temp_file = builder.build_command(image_paths, audio_path, output_path)
        except Exception as exc:
            self.on_log(f"❌ Error construyendo comando: {exc}")
            self.on_finished(False)
            return

        self.on_log(f"  → FFmpeg: {' '.join(cmd[:8])} ...")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=_STARTUPINFO,
            )
            self._current_proc = proc
            stderr_lines: list[str] = []

            assert proc.stderr is not None
            for line in proc.stderr:
                line = line.rstrip()
                if line:
                    stderr_lines.append(line)
                    if line.startswith("frame=") or "time=" in line:
                        self.on_log(f"    {line}")
                if self._cancel_event.is_set():
                    proc.terminate()
                    break

            proc.wait()

            if self._cancel_event.is_set():
                self.on_log("⚠ Slideshow cancelado por el usuario.")
                self.on_finished(False)
            elif proc.returncode == 0:
                self.on_log(f"✅ Slideshow generado: {output_path.name}")
                self.on_finished(True)
            else:
                # Mostrar últimas líneas de stderr para diagnóstico
                for ln in stderr_lines[-20:]:
                    self.on_log(f"  {ln}")
                self.on_log(f"❌ FFmpeg terminó con código {proc.returncode}")
                self.on_finished(False)

        except Exception as exc:
            self.on_log(f"❌ Error inesperado: {exc}")
            self.on_finished(False)
        finally:
            if temp_file is not None:
                try:
                    Path(temp_file).unlink(missing_ok=True)
                except OSError:
                    pass
