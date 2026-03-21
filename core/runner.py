"""
Runner — Motor de cola de procesamiento batch.

Gestiona:
  - Cola de trabajos (audio → video)
  - Ejecución en hilo separado (no bloquea la UI)
  - Progreso global y por archivo
  - Cancelación de proceso
  - Logs en tiempo real via callbacks
"""

from __future__ import annotations

import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from core.ffmpeg_builder import FFmpegBuilder
from core.naming_manager import NamingManager
from core.utils import (
    ensure_dir,
    get_audio_duration,
    get_audio_files,
)


class JobResult:
    """Resultado de procesamiento de un archivo de audio."""

    def __init__(self, index: int, audio_path: Path, output_path: Path | None = None) -> None:
        self.index = index
        self.audio_path = audio_path
        self.output_path = output_path
        self.success = False
        self.error: str = ""
        self.duration_audio: float = 0.0
        self.elapsed: float = 0.0


class Runner:
    """
    Motor de procesamiento batch.

    Uso:
        runner = Runner(settings, on_log, on_progress, on_job_done, on_finished)
        runner.start(audio_folder, image_path, output_folder)
        # para cancelar:
        runner.cancel()
    """

    def __init__(
        self,
        settings: dict[str, Any],
        on_log: Callable[[str], None],
        on_progress: Callable[[int, int, str], None],
        on_job_done: Callable[[JobResult], None],
        on_finished: Callable[[list[JobResult]], None],
    ) -> None:
        """
        Args:
            settings:    Configuración completa de la aplicación.
            on_log:      Callback para mensajes de log (llamado desde el hilo).
            on_progress: Callback (completados, total, archivo_actual).
            on_job_done: Callback por cada archivo procesado.
            on_finished: Callback al terminar todos los trabajos.
        """
        self.settings = settings
        self.on_log = on_log
        self.on_progress = on_progress
        self.on_job_done = on_job_done
        self.on_finished = on_finished

        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._current_proc: subprocess.Popen | None = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def start(
        self,
        audio_folder: str | Path,
        image_path: str | Path,
        output_folder: str | Path,
    ) -> None:
        """Inicia el procesamiento en un hilo de fondo."""
        if self._thread and self._thread.is_alive():
            self.on_log("⚠ Ya hay un proceso en ejecución.")
            return

        self._cancel_event.clear()
        self._thread = threading.Thread(
            target=self._process_all,
            args=(Path(audio_folder), Path(image_path), Path(output_folder)),
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
        self.on_log("🛑 Cancelación solicitada. Esperando que el proceso actual termine...")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Procesamiento
    # ------------------------------------------------------------------

    def _process_all(
        self,
        audio_folder: Path,
        image_path: Path,
        output_folder: Path,
    ) -> None:
        """Lógica principal de procesamiento (ejecutada en hilo secundario)."""
        results: list[JobResult] = []

        try:
            audio_files = get_audio_files(audio_folder)
        except Exception as exc:
            self.on_log(f"✘ Error leyendo carpeta de audios: {exc}")
            self.on_finished([])
            return

        if not audio_files:
            self.on_log("✘ No se encontraron archivos de audio en la carpeta seleccionada.")
            self.on_finished([])
            return

        total = len(audio_files)

        # ── Naming ──────────────────────────────────────────────────
        nm = NamingManager(
            mode=self.settings.get("naming_mode", "Default"),
            prefix=self.settings.get("naming_prefix", ""),
            custom_names=self.settings.get("naming_custom_list", []),
            auto_number=self.settings.get("naming_auto_number", True),
        )

        naming_errors = nm.validate(total)
        if naming_errors:
            for err in naming_errors:
                self.on_log(f"✘ Naming: {err}")
            self.on_finished([])
            return

        for warn in nm.get_warnings(total):
            self.on_log(f"⚠ Naming: {warn}")

        output_names = nm.generate_names(audio_files)
        # ────────────────────────────────────────────────────────────

        self.on_log(f"▶ Iniciando procesamiento de {total} archivo(s)...\n")
        ensure_dir(output_folder)

        for idx, (audio_path, output_name) in enumerate(
            zip(audio_files, output_names), start=1
        ):
            if self._cancel_event.is_set():
                self.on_log("🛑 Proceso cancelado por el usuario.")
                break

            output_path = nm.build_output_path(output_name, output_folder)
            job = JobResult(index=idx, audio_path=audio_path, output_path=output_path)
            self.on_progress(idx - 1, total, audio_path.name)
            self.on_log(f"\n[{idx}/{total}] Procesando: {audio_path.name}")
            self.on_log(f"  → Output: {output_path.name}")

            try:
                self._process_one(job, image_path, output_folder, total)
            except Exception as exc:
                job.success = False
                job.error = str(exc)
                self.on_log(f"  ✘ Error inesperado: {exc}")

            results.append(job)
            self.on_job_done(job)

        self.on_progress(total, total, "")
        self._summarize(results)
        self.on_finished(results)

    def _process_one(
        self,
        job: JobResult,
        image_path: Path,
        output_folder: Path,
        total: int,
    ) -> None:
        """Procesa un único archivo de audio. output_path ya viene asignado en job."""
        # Duración
        self.on_log(f"  → Obteniendo duración...")
        duration = get_audio_duration(job.audio_path)
        job.duration_audio = duration
        self.on_log(f"  → Duración: {duration:.2f}s")

        # output_path ya fue resuelto por NamingManager en _process_all
        output_path = job.output_path

        # Construir comando
        builder = FFmpegBuilder(self.settings)
        cmd = builder.build_command(
            audio_path=job.audio_path,
            image_path=image_path,
            output_path=output_path,
            duration=duration,
        )

        self.on_log(f"  → Comando: {' '.join(cmd[:6])} ...")

        # Ejecutar FFmpeg
        start = time.time()
        success, error_msg = self._run_ffmpeg(cmd)
        job.elapsed = time.time() - start

        if success:
            job.success = True
            self.on_log(f"  ✔ Completado en {job.elapsed:.1f}s → {output_path.name}")
        else:
            job.success = False
            job.error = error_msg
            self.on_log(f"  ✘ FFmpeg falló: {error_msg[:300]}")

    def _run_ffmpeg(self, cmd: list[str]) -> tuple[bool, str]:
        """
        Ejecuta FFmpeg y captura stderr para el log en tiempo real.

        Returns:
            (éxito: bool, mensaje_error: str)
        """
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self._current_proc = proc

            stderr_lines: list[str] = []

            # Leer stderr línea a línea para log en tiempo real
            assert proc.stderr is not None
            for line in proc.stderr:
                line = line.rstrip()
                if line:
                    stderr_lines.append(line)
                    # Solo mostrar líneas de progreso relevantes
                    if line.startswith("frame=") or "time=" in line:
                        self.on_log(f"    {line}")

                if self._cancel_event.is_set():
                    proc.terminate()
                    return False, "Cancelado por el usuario."

            proc.wait()
            self._current_proc = None

            if proc.returncode == 0:
                return True, ""
            else:
                # Filtrar líneas de cabecera de FFmpeg (version banner, libs, etc.)
                # para mostrar solo las líneas con el error real.
                _skip_prefixes = (
                    "ffmpeg version", "built with", "configuration:",
                    "lib", "  lib", "Input #", "Output #", "Stream mapping",
                    "Press [", "frame=", "  Duration", "    Stream",
                    "video:", "audio:", "  Metadata",
                )
                meaningful = [
                    ln for ln in stderr_lines
                    if not any(ln.startswith(p) for p in _skip_prefixes)
                ]
                # Si el filtrado dejó vacío, mostrar las últimas líneas sin filtrar
                show_lines = meaningful[-30:] if meaningful else stderr_lines[-30:]
                error_detail = "\n".join(show_lines)
                return False, error_detail

        except FileNotFoundError:
            return False, "ffmpeg no encontrado en PATH."
        except Exception as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # Test FFmpeg
    # ------------------------------------------------------------------

    def test_ffmpeg(self, output_path: str | Path) -> tuple[bool, str]:
        """
        Genera un clip de prueba sintético (tono + color) para verificar FFmpeg.

        Args:
            output_path: Ruta donde guardar el video de prueba.

        Returns:
            (éxito: bool, mensaje: str)
        """
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=1920x1080:d=3:r=30",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-t", "3",
            str(output_path),
        ]
        ok, err = self._run_ffmpeg(cmd)
        if ok:
            return True, f"✔ FFmpeg funciona correctamente. Test guardado en: {output_path}"
        return False, f"✘ FFmpeg test falló: {err[:200]}"

    # ------------------------------------------------------------------
    # Resumen
    # ------------------------------------------------------------------

    def _summarize(self, results: list[JobResult]) -> None:
        ok = sum(1 for r in results if r.success)
        fail = len(results) - ok
        self.on_log(f"\n{'=' * 50}")
        self.on_log(f"Procesamiento finalizado: {ok} completados, {fail} fallidos.")
        if fail:
            for r in results:
                if not r.success:
                    self.on_log(f"  ✘ {r.audio_path.name}: {r.error[:100]}")
        self.on_log("=" * 50)
