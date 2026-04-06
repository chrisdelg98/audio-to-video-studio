from __future__ import annotations

import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable

# Hide console window on Windows
_STARTUPINFO = None
if os.name == "nt":
    _STARTUPINFO = subprocess.STARTUPINFO()
    _STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW


class AudioMergeRunner:
    """Merge multiple audio files with optional crossfade in a background thread."""

    def __init__(
        self,
        on_log: Callable[[str], None],
        on_finished: Callable[[bool, Path | None], None],
    ) -> None:
        self.on_log = on_log
        self.on_finished = on_finished
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._current_proc: subprocess.Popen | None = None

    def start(
        self,
        audio_paths: list[Path],
        output_path: Path,
        crossfade_s: float,
        output_format: str,
    ) -> None:
        if self._thread and self._thread.is_alive():
            self.on_log("[Audio Merge] Ya hay un proceso en ejecución.")
            return

        self._cancel_event.clear()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(
            target=self._run,
            args=(audio_paths, output_path, float(crossfade_s), output_format.lower().strip()),
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
        self.on_log("[Audio Merge] Cancelación solicitada...")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _codec_args(self, output_format: str) -> list[str]:
        if output_format == "wav":
            return ["-c:a", "pcm_s16le"]
        if output_format == "flac":
            return ["-c:a", "flac"]
        return ["-c:a", "libmp3lame", "-b:a", "320k"]

    def _try_run(self, cmd: list[str]) -> tuple[bool, list[str]]:
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
        err_lines: list[str] = []

        assert proc.stderr is not None
        for line in proc.stderr:
            line = line.rstrip()
            if line:
                err_lines.append(line)
                if line.startswith("size=") or line.startswith("time=") or "speed=" in line:
                    self.on_log(f"    {line}")
            if self._cancel_event.is_set():
                proc.terminate()
                break

        proc.wait()
        if self._cancel_event.is_set():
            return False, err_lines
        return proc.returncode == 0, err_lines

    def _concat_merge(self, audio_paths: list[Path], output_path: Path, output_format: str) -> bool:
        concat_list = Path(tempfile.mktemp(suffix="_audio_merge_concat.txt"))
        try:
            with open(concat_list, "w", encoding="utf-8") as fh:
                for p in audio_paths:
                    safe = str(p.resolve()).replace("\\", "/").replace("'", r"'\\''")
                    fh.write(f"file '{safe}'\n")

            # Fast-path: try stream copy for identical container/codec situations.
            copy_cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
                "-c", "copy",
                str(output_path),
            ]
            ok, _ = self._try_run(copy_cmd)
            if ok:
                return True

            # Fallback to explicit encode by selected format.
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_list),
            ] + self._codec_args(output_format) + [str(output_path)]

            ok, err = self._try_run(cmd)
            if not ok:
                for ln in err[-12:]:
                    self.on_log(f"    {ln}")
            return ok
        finally:
            try:
                concat_list.unlink(missing_ok=True)
            except OSError:
                pass

    def _crossfade_merge(self, audio_paths: list[Path], output_path: Path, crossfade_s: float, output_format: str) -> bool:
        inputs: list[str] = []
        for p in audio_paths:
            inputs += ["-i", str(p)]

        n = len(audio_paths)
        parts: list[str] = []
        prev = "[0:a]"
        for i in range(1, n):
            out_label = f"[m{i:02d}]" if i < n - 1 else "[outa]"
            parts.append(f"{prev}[{i}:a]acrossfade=d={crossfade_s}:c1=tri:c2=tri{out_label}")
            prev = out_label

        cmd = ["ffmpeg", "-y"] + inputs + [
            "-filter_complex", ";".join(parts),
            "-map", "[outa]",
        ] + self._codec_args(output_format) + [str(output_path)]

        ok, err = self._try_run(cmd)
        if not ok:
            for ln in err[-12:]:
                self.on_log(f"    {ln}")
        return ok

    def _run(
        self,
        audio_paths: list[Path],
        output_path: Path,
        crossfade_s: float,
        output_format: str,
    ) -> None:
        if not audio_paths:
            self.on_log("[Audio Merge] No hay audios para unir.")
            self.on_finished(False, None)
            return

        self.on_log(f"[Audio Merge] Uniendo {len(audio_paths)} archivo(s) -> {output_path.name}")
        self.on_log(f"[Audio Merge] Formato salida: {output_format.upper()} | Crossfade: {crossfade_s:.1f}s")

        try:
            if len(audio_paths) == 1:
                cmd = ["ffmpeg", "-y", "-i", str(audio_paths[0])] + self._codec_args(output_format) + [str(output_path)]
                ok, err = self._try_run(cmd)
                if not ok:
                    for ln in err[-12:]:
                        self.on_log(f"    {ln}")
                    self.on_log("[Audio Merge] Error al convertir audio único.")
                    self.on_finished(False, None)
                    return
            elif crossfade_s <= 0.0:
                if not self._concat_merge(audio_paths, output_path, output_format):
                    self.on_log("[Audio Merge] Error al concatenar audios.")
                    self.on_finished(False, None)
                    return
            else:
                if not self._crossfade_merge(audio_paths, output_path, crossfade_s, output_format):
                    self.on_log("[Audio Merge] Error al mezclar con crossfade.")
                    self.on_finished(False, None)
                    return

            if self._cancel_event.is_set():
                self.on_log("[Audio Merge] Proceso cancelado.")
                self.on_finished(False, None)
            else:
                self.on_log(f"[Audio Merge] OK: {output_path}")
                self.on_finished(True, output_path)
        except Exception as exc:
            self.on_log(f"[Audio Merge] Error inesperado: {exc}")
            self.on_finished(False, None)
