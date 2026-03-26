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

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

# Ocultar consola de FFmpeg en modo windowed (PyInstaller --windowed)
_STARTUPINFO = None
if os.name == "nt":
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW

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
        image_assignment: dict | None = None,
    ) -> None:
        """Inicia el procesamiento en un hilo de fondo."""
        if self._thread and self._thread.is_alive():
            self.on_log("⚠ Ya hay un proceso en ejecución.")
            return

        self._cancel_event.clear()
        img = Path(image_path) if image_path else None
        self._thread = threading.Thread(
            target=self._process_all,
            args=(Path(audio_folder), img, Path(output_folder), image_assignment),
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
        image_path: Path | None,
        output_folder: Path,
        image_assignment: dict | None = None,
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
            prefix=(
                self.settings.get("naming_name", "")
                if self.settings.get("naming_mode", "Default") == "Nombre"
                else self.settings.get("naming_prefix", "")
            ),
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
                img = image_assignment.get(audio_path.name) if image_assignment else image_path
                if img is None:
                    img = image_path
                self._process_one(job, img, output_folder, total)
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
        # Resolver texto dinámico antes de construir el builder
        s = dict(self.settings)
        if s.get("enable_dyn_text_overlay", False):
            dyn_mode = s.get("dyn_text_mode", "Texto fijo")
            if dyn_mode == "Texto fijo":
                s["_resolved_dyn_text"] = s.get("dyn_text_content", "")
            elif dyn_mode == "Nombre de canción":
                s["_resolved_dyn_text"] = job.audio_path.stem
            else:  # Prefijo + Nombre de canción
                nm_mode = s.get("naming_mode", "Default")
                prefix = (s.get("naming_name", "") if nm_mode == "Nombre"
                          else s.get("naming_prefix", ""))
                s["_resolved_dyn_text"] = f"{prefix}{job.audio_path.stem}"
        builder = FFmpegBuilder(s)
        cmd = builder.build_command(
            audio_path=job.audio_path,
            image_path=image_path,
            output_path=output_path,
            duration=duration,
        )

        self.on_log(f"  \u2192 Comando: {' '.join(cmd[:8])} ...")

        # Ejecutar FFmpeg
        start = time.time()
        try:
            success, error_msg = self._run_ffmpeg(cmd)
        finally:
            builder.cleanup()
        job.elapsed = time.time() - start

        if success:
            job.success = True
            self.on_log(f"  ✔ Completado en {job.elapsed:.1f}s → {output_path.name}")
        else:
            job.success = False
            job.error = error_msg
            # Show full error, indent each line
            for ln in error_msg.splitlines():
                self.on_log(f"  {ln}")

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
                startupinfo=_STARTUPINFO,
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
                # Step 1: find lines that look like actual errors
                _error_indicators = ("error", "invalid", "no such file", "failed",
                                     "unknown", "not found", "cannot", "unable", "fatal")
                error_lines = [
                    ln for ln in stderr_lines
                    if any(ind in ln.lower() for ind in _error_indicators)
                ]

                # Step 2: always include the last 15 lines (FFmpeg puts the final
                #         error near the end) and deduplicate order-preservingly
                tail = stderr_lines[-15:] if len(stderr_lines) > 15 else stderr_lines
                seen: set[str] = set()
                combined: list[str] = []
                for ln in error_lines + tail:
                    if ln not in seen:
                        seen.add(ln)
                        combined.append(ln)

                # Step 3: strip pure banner lines from combined
                _skip_prefixes = (
                    "ffmpeg version", "built with", "configuration:",
                    "  lib", "libav", "Press [",
                )
                filtered = [
                    ln for ln in combined
                    if not any(ln.lower().startswith(p.lower()) for p in _skip_prefixes)
                ]

                # If filtering removed everything, fall back to last 15 raw lines
                show_lines = filtered if filtered else tail
                return False, "\n".join(show_lines)

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
                    self.on_log(f"  ✘ {r.audio_path.name}:")
                    # Show up to first 5 error lines in summary
                    for ln in r.error.splitlines()[:5]:
                        self.on_log(f"    {ln}")
        self.on_log("=" * 50)


# ──────────────────────────────────────────────────────────────────────────────
# SHORTS RUNNER
# ──────────────────────────────────────────────────────────────────────────────


class ShortsJobResult:
    """Resultado de procesamiento de un short individual."""

    def __init__(self, index: int, start_s: float, output_path: Path | None = None) -> None:
        self.index = index
        self.start_s = start_s
        self.output_path = output_path
        self.success: bool = False
        self.error: str = ""
        self.elapsed: float = 0.0


class ShortsRunner:
    """Genera múltiples Shorts desde un único audio cortando fragmentos distribuidos."""

    def __init__(
        self,
        settings: dict,
        on_log: Callable[[str], None],
        on_progress: Callable[[int, int, str], None],
        on_job_done: Callable[[ShortsJobResult], None],
        on_finished: Callable[[list[ShortsJobResult]], None],
    ) -> None:
        self.settings = settings
        self.on_log = on_log
        self.on_progress = on_progress
        self.on_job_done = on_job_done
        self.on_finished = on_finished
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._current_proc: Any = None

    def start(
        self,
        audio_path: Path,
        image_paths: list[Path],
        output_folder: Path,
        starts: list[float],
        short_duration: float,
        output_names: list[str],
    ) -> None:
        if self._thread and self._thread.is_alive():
            self.on_log("⚠ Ya hay un proceso en ejecución.")
            return
        self._cancel_event.clear()
        self._thread = threading.Thread(
            target=self._process_all,
            args=(
                Path(audio_path),
                [Path(p) for p in image_paths],
                Path(output_folder),
                starts,
                short_duration,
                output_names,
            ),
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        self._cancel_event.set()
        if self._current_proc and self._current_proc.poll() is None:
            try:
                self._current_proc.terminate()
            except OSError:
                pass
        self.on_log("🛑 Cancelación solicitada...")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _process_all(
        self,
        audio_path: Path,
        image_paths: list[Path],
        output_folder: Path,
        starts: list[float],
        short_duration: float,
        output_names: list[str],
    ) -> None:
        total = len(starts)
        results: list[ShortsJobResult] = []
        self.on_log(f"▶ Generando {total} Short(s) de {short_duration:.0f}s...")
        ensure_dir(output_folder)

        for idx, (start_s, name) in enumerate(zip(starts, output_names), start=1):
            if self._cancel_event.is_set():
                self.on_log("🛑 Proceso cancelado.")
                break

            # Assign image cyclically across shorts
            img_path = image_paths[(idx - 1) % len(image_paths)] if image_paths else None
            output_path = output_folder / f"{name}.mp4"
            job = ShortsJobResult(index=idx, start_s=start_s, output_path=output_path)

            self.on_progress(idx - 1, total, f"Short {idx}/{total}")
            self.on_log(
                f"\n[{idx}/{total}] Short desde {start_s:.1f}s "
                f"(+{short_duration:.0f}s) → {output_path.name}"
            )

            try:
                self._process_one(job, audio_path, img_path, short_duration)
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
        job: ShortsJobResult,
        audio_path: Path,
        image_path: Path | None,
        short_duration: float,
    ) -> None:
        # Resolver texto dinámico antes de construir el builder
        s = dict(self.settings)
        if s.get("sho_enable_dyn_text_overlay", False):
            dyn_mode = s.get("sho_dyn_text_mode", "Texto fijo")
            if dyn_mode == "Texto fijo":
                s["_resolved_dyn_text"] = s.get("sho_dyn_text_content", "")
            elif dyn_mode == "Nombre de canción":
                # Use the output filename stem (which was resolved by NamingManager)
                s["_resolved_dyn_text"] = job.output_path.stem
            else:  # Prefijo + Nombre de canción
                nm_mode = s.get("sho_naming_mode", "Default")
                prefix = (s.get("sho_naming_name", "") if nm_mode == "Nombre"
                          else s.get("sho_naming_prefix", ""))
                s["_resolved_dyn_text"] = f"{prefix}{job.output_path.stem}"
            # Map sho_dyn_* keys to dyn_* so FFmpegBuilder can find them
            s["enable_dyn_text_overlay"]   = True
            s["dyn_text_position"]         = s.get("sho_dyn_text_position", "Bottom")
            s["dyn_text_margin"]           = s.get("sho_dyn_text_margin", 40)
            s["dyn_text_font_size"]        = s.get("sho_dyn_text_font_size", 36)
            s["dyn_text_font"]             = s.get("sho_dyn_text_font", "Arial")
            s["dyn_text_color"]            = s.get("sho_dyn_text_color", "Blanco")
            s["dyn_text_glitch_intensity"] = s.get("sho_dyn_text_glitch_intensity", 3)
            s["dyn_text_glitch_speed"]     = s.get("sho_dyn_text_glitch_speed", 4.0)
        builder = FFmpegBuilder(s)
        cmd = builder.build_short_cmd(
            audio_path=audio_path,
            image_path=image_path,
            output_path=job.output_path,
            start_s=job.start_s,
            duration_s=short_duration,
        )
        t0 = time.time()
        try:
            success, error_msg = self._run_ffmpeg(cmd)
        finally:
            builder.cleanup()
        job.elapsed = time.time() - t0
        if success:
            job.success = True
            self.on_log(f"  ✔ Completado en {job.elapsed:.1f}s → {job.output_path.name}")
        else:
            job.success = False
            job.error = error_msg
            for ln in error_msg.splitlines():
                self.on_log(f"  {ln}")

    def _run_ffmpeg(self, cmd: list[str]) -> tuple[bool, str]:
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
            for line in proc.stderr:
                line = line.rstrip()
                if line:
                    stderr_lines.append(line)
                    if line.startswith("frame=") or "time=" in line:
                        self.on_log(f"    {line}")
                if self._cancel_event.is_set():
                    proc.terminate()
                    return False, "Cancelado por el usuario."
            proc.wait()
            self._current_proc = None
            if proc.returncode == 0:
                return True, ""
            _error_indicators = (
                "error", "invalid", "no such file", "failed", "unknown",
                "not found", "cannot", "unable", "fatal",
            )
            error_lines = [
                ln for ln in stderr_lines
                if any(ind in ln.lower() for ind in _error_indicators)
            ]
            tail = stderr_lines[-15:] if len(stderr_lines) > 15 else stderr_lines
            seen: set[str] = set()
            combined: list[str] = []
            for ln in error_lines + tail:
                if ln not in seen:
                    seen.add(ln)
                    combined.append(ln)
            _skip = ("ffmpeg version", "built with", "configuration:", "  lib", "libav", "Press [")
            filtered = [ln for ln in combined if not any(ln.lower().startswith(p.lower()) for p in _skip)]
            show_lines = filtered if filtered else tail
            return False, "\n".join(show_lines)
        except FileNotFoundError:
            return False, "ffmpeg no encontrado en PATH."
        except Exception as exc:
            return False, str(exc)

    def _summarize(self, results: list[ShortsJobResult]) -> None:
        ok = sum(1 for r in results if r.success)
        fail = len(results) - ok
        self.on_log(f"\n{'=' * 50}")
        self.on_log(f"Shorts finalizados: {ok} completados, {fail} fallidos.")
        if fail:
            for r in results:
                if not r.success:
                    self.on_log(f"  ✘ Short {r.index} ({r.start_s:.1f}s):")
                    for ln in r.error.splitlines()[:5]:
                        self.on_log(f"    {ln}")
        self.on_log("=" * 50)
