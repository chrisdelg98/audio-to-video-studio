"""Mass file renamer runner (pure rename, no transcoding)."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass
class RenameJobResult:
    index: int
    source_path: Path
    target_path: Path
    success: bool = False
    error: str = ""


class RenameRunner:
    """Runs bulk renaming in background thread with progress callbacks."""

    def __init__(
        self,
        on_log: Callable[[str], None],
        on_progress: Callable[[int, int, str], None],
        on_job_done: Callable[[RenameJobResult], None],
        on_finished: Callable[[list[RenameJobResult]], None],
    ) -> None:
        self.on_log = on_log
        self.on_progress = on_progress
        self.on_job_done = on_job_done
        self.on_finished = on_finished

        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        files: list[Path],
        target_stems: list[str],
        update_title_metadata: bool = False,
    ) -> None:
        if self.is_running():
            self.on_log("[RENAME] Ya hay un proceso en ejecucion.")
            return

        self._cancel_event.clear()
        self._thread = threading.Thread(
            target=self._process_all,
            args=(list(files), list(target_stems), bool(update_title_metadata)),
            daemon=True,
        )
        self._thread.start()

    def cancel(self) -> None:
        self._cancel_event.set()
        self.on_log("[RENAME] Cancelacion solicitada...")

    def _process_all(
        self,
        files: list[Path],
        target_stems: list[str],
        update_title_metadata: bool,
    ) -> None:
        results: list[RenameJobResult] = []
        total = len(files)

        if total == 0:
            self.on_finished([])
            return
        if len(target_stems) != total:
            self.on_log("[RENAME] Error: la cantidad de nombres no coincide con los archivos.")
            self.on_finished([])
            return

        lower_targets: set[str] = set()
        planned_targets: list[Path] = []
        for src, stem in zip(files, target_stems):
            dst = src.with_name(f"{stem}{src.suffix}")
            key = str(dst).lower()
            if key in lower_targets:
                self.on_log(f"[RENAME] Error: nombre destino duplicado: {dst.name}")
                self.on_finished([])
                return
            lower_targets.add(key)
            planned_targets.append(dst)

        tmp_paths: list[Path] = []
        if self._cancel_event.is_set():
            self.on_log("[RENAME] Cancelado antes de aplicar cambios.")
            self.on_finished([])
            return

        # Phase 1: move every source to a temporary name.
        # Important: once this phase starts, we must complete/rollback atomically
        # to avoid leaving hidden tmp files that look like "lost" media.
        for idx, src in enumerate(files, start=1):
            tmp = src.with_name(f".__cfstmp__{idx:04d}__{src.name}")
            while tmp.exists():
                tmp = src.with_name(f".__cfstmp__{idx:04d}__x__{src.name}")
            try:
                src.rename(tmp)
                tmp_paths.append(tmp)
            except Exception as exc:
                self.on_log(f"[RENAME] Error preparando rename de '{src.name}': {exc}")
                self._rollback_tmp(files=files, tmp_paths=tmp_paths)
                self.on_finished(results)
                return

        if self._cancel_event.is_set():
            self.on_log("[RENAME] Cancelado: revirtiendo cambios temporales...")
            self._rollback_tmp(files=files, tmp_paths=tmp_paths)
            self.on_finished(results)
            return

        # Phase 2: commit all final names. Do not abort in the middle of this
        # phase, otherwise some files could remain only under temporary names.
        for idx, (src, tmp, dst) in enumerate(zip(files, tmp_paths, planned_targets), start=1):
            job = RenameJobResult(index=idx, source_path=src, target_path=dst)
            self.on_progress(idx - 1, total, src.name)
            try:
                tmp.rename(dst)
                job.success = True
                self.on_log(f"[RENAME] {src.name} -> {dst.name}")
                if update_title_metadata and dst.suffix.lower() == ".mp3":
                    meta_ok, meta_error = self._write_title_metadata(dst, dst.stem)
                    if meta_ok:
                        self.on_log(f"[RENAME][META] Title actualizado: {dst.name}")
                    else:
                        self.on_log(f"[RENAME][META] Aviso en '{dst.name}': {meta_error}")
            except Exception as exc:
                job.success = False
                job.error = str(exc)
                self.on_log(f"[RENAME] Error en '{src.name}': {exc}")
                try:
                    tmp.rename(src)
                except Exception:
                    pass
            results.append(job)
            self.on_job_done(job)

        self.on_progress(total, total, "")
        self.on_finished(results)

    def _rollback_tmp(self, files: list[Path], tmp_paths: list[Path]) -> None:
        for src, tmp in zip(files, tmp_paths):
            if not tmp.exists():
                continue
            try:
                tmp.rename(src)
            except Exception:
                pass

    @staticmethod
    def _write_title_metadata(path: Path, title: str) -> tuple[bool, str]:
        """Update Title metadata only for MP3 files."""
        try:
            from mutagen.id3 import ID3, ID3NoHeaderError, TIT2  # type: ignore
        except Exception:
            return False, "mutagen no esta disponible en el entorno."

        suffix = path.suffix.lower()
        if suffix != ".mp3":
            return False, "solo MP3 soporta actualizacion de Title en Rename."

        try:
            try:
                tags = ID3(str(path))
            except ID3NoHeaderError:
                tags = ID3()
            tags.delall("TIT2")
            tags.add(TIT2(encoding=3, text=[title]))
            tags.save(str(path))
            return True, ""
        except Exception as exc:
            return False, str(exc)
