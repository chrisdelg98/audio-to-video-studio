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
from core.utils import ensure_dir, get_audio_duration, get_audio_files, merge_audio_files

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

    def _run_ffmpeg(self, cmd: list[str]) -> tuple[bool, list[str]]:
        """Ejecuta un comando ffmpeg con logging incremental y soporte de cancelación."""
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
                if line.startswith("frame=") or "time=" in line or "speed=" in line:
                    self.on_log(f"    {line}")
            if self._cancel_event.is_set():
                proc.terminate()
                break

        proc.wait()
        if self._cancel_event.is_set():
            return False, stderr_lines
        return proc.returncode == 0, stderr_lines

    def _should_use_loop_mux(self, image_paths: list[Path], audio_path: Path | None) -> bool:
        """Activa estrategia 2-pass en slideshows largos con transición para evitar cuellos de botella."""
        if not audio_path:
            return False
        if len(image_paths) < 2:
            return False
        if self.settings.get("sl_transition", "Ninguna") == "Ninguna":
            return False
        try:
            audio_dur = get_audio_duration(audio_path)
        except Exception:
            return False
        per_image = float(self.settings.get("sl_duration", 5.0))
        cycle_dur = max(0.1, len(image_paths) * per_image)
        # Sólo usar 2-pass cuando el audio es al menos ~2 ciclos
        return audio_dur >= cycle_dur * 1.9

    # ── Procesamiento ────────────────────────────────────────────────

    def _run(
        self,
        image_paths: list[Path],
        audio_path: Path | None,
        output_path: Path,
    ) -> None:
        builder = SlideshowBuilder(self.settings)
        merge_temp: Path | None = None
        temp_file: Path | None = None
        loop_cycle_file: Path | None = None

        try:
            # ── Pre-step: merge audio folder if requested ─────────────────
            if (
                audio_path is None
                and self.settings.get("sl_audio_enabled", False)
                and self.settings.get("sl_audio_mode") == "folder"
                and self.settings.get("sl_audio_folder")
            ):
                folder = Path(self.settings["sl_audio_folder"])
                audio_files = get_audio_files(folder)
                if audio_files:
                    merge_temp = output_path.parent / f"_merge_tmp_{output_path.stem}.wav"
                    crossfade_s = float(self.settings.get("sl_crossfade", 2.0))
                    self.on_log(
                        f"  → Mezclando {len(audio_files)} pistas de audio "
                        f"(crossfade: {crossfade_s}s)…"
                    )
                    try:
                        audio_path = merge_audio_files(
                            audio_files, crossfade_s, merge_temp, on_log=self.on_log
                        )
                    except Exception as exc:
                        self.on_log(f"❌ Error mezclando audios: {exc}")
                        self.on_finished(False)
                        return
                else:
                    self.on_log("⚠ La carpeta de audios está vacía — se generará sin audio.")

            self.on_log(f"▶ Construyendo slideshow con {len(image_paths)} imágenes...")
            self.on_log(f"  → Transición: {self.settings.get('sl_transition', 'Ninguna')}")
            self.on_log(f"  → Duración por imagen: {self.settings.get('sl_duration', 5)}s")
            self.on_log(f"  → Resolución: {self.settings.get('sl_resolution', '1080p')}")
            self.on_log(f"  → Salida: {output_path.name}")

            use_loop_mux = self._should_use_loop_mux(image_paths, audio_path)
            if use_loop_mux:
                self.on_log("  → Optimización activa: render ciclo corto + loop mux (2-pass).")
                # Cerrar ciclo visual (última -> primera) para que el loop no tenga salto brusco.
                cycle_images = list(image_paths) + [image_paths[0]]
                loop_cycle_file = output_path.parent / f"_sl_cycle_{output_path.stem}.mp4"
                try:
                    cycle_cmd, temp_file = builder.build_command(cycle_images, None, loop_cycle_file)
                except Exception as exc:
                    self.on_log(f"❌ Error construyendo comando de ciclo: {exc}")
                    self.on_finished(False)
                    return

                self.on_log(f"  → FFmpeg ciclo: {' '.join(cycle_cmd[:8])} ...")
                ok, err = self._run_ffmpeg(cycle_cmd)
                if not ok:
                    for ln in err[-20:]:
                        self.on_log(f"  {ln}")
                    if self._cancel_event.is_set():
                        self.on_log("⚠ Slideshow cancelado por el usuario.")
                    else:
                        self.on_log("❌ Falló el render del ciclo base.")
                    self.on_finished(False)
                    return

                if not audio_path:
                    self.on_log("❌ No hay audio para aplicar loop mux.")
                    self.on_finished(False)
                    return

                mux_cmd: list[str] = [
                    "ffmpeg", "-y",
                    "-stream_loop", "-1", "-i", str(loop_cycle_file),
                    "-thread_queue_size", "512", "-i", str(audio_path),
                    "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "320k",
                    "-shortest",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
                self.on_log(f"  → FFmpeg mux: {' '.join(mux_cmd[:8])} ...")
                ok, err = self._run_ffmpeg(mux_cmd)
                if self._cancel_event.is_set():
                    self.on_log("⚠ Slideshow cancelado por el usuario.")
                    self.on_finished(False)
                    return
                if ok:
                    self.on_log(f"✅ Slideshow generado: {output_path.name}")
                    self.on_finished(True)
                    return
                for ln in err[-20:]:
                    self.on_log(f"  {ln}")
                self.on_log("❌ Falló el mux final del slideshow.")
                self.on_finished(False)
                return

            try:
                cmd, temp_file = builder.build_command(image_paths, audio_path, output_path)
            except Exception as exc:
                self.on_log(f"❌ Error construyendo comando: {exc}")
                self.on_finished(False)
                return

            self.on_log(f"  → FFmpeg: {' '.join(cmd[:8])} ...")

            try:
                ok, stderr_lines = self._run_ffmpeg(cmd)
                if self._cancel_event.is_set():
                    self.on_log("⚠ Slideshow cancelado por el usuario.")
                    self.on_finished(False)
                elif ok:
                    self.on_log(f"✅ Slideshow generado: {output_path.name}")
                    self.on_finished(True)
                else:
                    # Mostrar últimas líneas de stderr para diagnóstico
                    for ln in stderr_lines[-20:]:
                        self.on_log(f"  {ln}")
                    self.on_log("❌ FFmpeg terminó con error.")
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
            if loop_cycle_file is not None:
                try:
                    loop_cycle_file.unlink(missing_ok=True)
                except OSError:
                    pass
            if merge_temp is not None:
                try:
                    merge_temp.unlink(missing_ok=True)
                except OSError:
                    pass
