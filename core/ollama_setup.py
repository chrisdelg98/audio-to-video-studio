"""Ollama setup helpers for startup dependency preparation.

This module mirrors the FFmpeg startup strategy:
- Detect local installation
- Optionally install Ollama on Windows
- Check server availability
- Check/pull required models with progress callbacks
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib import error as url_error
from urllib import request as url_request

OLLAMA_SETUP_URL = "https://ollama.com/download/OllamaSetup.exe"

# Conservative rough estimates used for user prompts in startup UI.
MODEL_SIZE_ESTIMATES_GB = {
    "llama3.2:1b": 1.3,
    "llama3.2:3b": 2.0,
    "llama3.1:8b": 4.7,
    "llama3:8b": 4.7,
    "mistral:7b": 4.1,
    "qwen2.5:7b": 4.4,
}

ProgressCallback = Callable[[str, Optional[float]], None]


@dataclass
class OllamaStatus:
    supported_os: bool
    installed: bool
    running: bool
    installed_models: set[str]
    missing_models: list[str]


def _report_progress(
    on_progress: ProgressCallback | None,
    message: str,
    progress: float | None = None,
) -> None:
    if on_progress:
        on_progress(message, progress)


def _normalize_base_url(base_url: str) -> str:
    return (base_url or "").strip().rstrip("/")


def _request_json(url: str, timeout_seconds: int = 8) -> dict:
    req = url_request.Request(url, method="GET")
    with url_request.urlopen(req, timeout=max(2, int(timeout_seconds))) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise RuntimeError("Respuesta JSON no compatible")
    return parsed


def _windows_ollama_candidates() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    pf = Path(os.environ.get("ProgramFiles", ""))
    return [
        local / "Programs" / "Ollama" / "ollama.exe",
        local / "Programs" / "Ollama" / "ollama app.exe",
        pf / "Ollama" / "ollama.exe",
        pf / "Ollama" / "ollama app.exe",
    ]


def _find_ollama_cli() -> str | None:
    in_path = shutil.which("ollama")
    if in_path:
        return in_path

    if os.name == "nt":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        pf = Path(os.environ.get("ProgramFiles", ""))
        candidates = [
            local / "Programs" / "Ollama" / "ollama.exe",
            pf / "Ollama" / "ollama.exe",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)
    return None


def is_supported_os() -> bool:
    if os.name != "nt":
        return True
    # Win10+ required for Ollama binaries.
    return (sys_getwindowsmajor() >= 10)


def sys_getwindowsmajor() -> int:
    try:
        if os.name != "nt":
            return 0
        return int(sys.getwindowsversion().major)
    except Exception:
        return 0


def is_ollama_installed() -> bool:
    if shutil.which("ollama"):
        return True
    if os.name == "nt":
        for candidate in _windows_ollama_candidates():
            if candidate.is_file():
                return True
    return False


def is_ollama_running(base_url: str) -> bool:
    b = _normalize_base_url(base_url)
    if not b:
        return False
    try:
        _request_json(f"{b}/api/tags", timeout_seconds=4)
        return True
    except Exception:
        return False


def list_local_models(base_url: str) -> set[str]:
    b = _normalize_base_url(base_url)
    if not b:
        return set()
    data = _request_json(f"{b}/api/tags", timeout_seconds=8)
    models = data.get("models", [])
    found: set[str] = set()
    if isinstance(models, list):
        for item in models:
            if isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                if name:
                    found.add(name)
                    # Accept both full and short forms where possible.
                    if ":" in name:
                        found.add(name.split(":", 1)[0])
    return found


def list_installed_models_with_sizes(base_url: str) -> list[dict[str, object]]:
    """Return installed Ollama models with best-effort size metadata."""
    b = _normalize_base_url(base_url)
    if not b:
        return []

    data = _request_json(f"{b}/api/tags", timeout_seconds=8)
    models = data.get("models", [])
    if not isinstance(models, list):
        return []

    out: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)

        size_bytes = item.get("size", 0)
        try:
            size_gb = round(float(size_bytes) / (1024 ** 3), 2) if float(size_bytes) > 0 else 0.0
        except Exception:
            size_gb = 0.0

        out.append({"name": name, "size_gb": size_gb})

    out.sort(key=lambda it: str(it.get("name", "")).lower())
    return out


def estimate_models_size_gb(models: list[str]) -> float:
    total = 0.0
    for raw in models:
        name = (raw or "").strip().lower()
        if not name:
            continue
        if name in MODEL_SIZE_ESTIMATES_GB:
            total += MODEL_SIZE_ESTIMATES_GB[name]
            continue
        base = name.split(":", 1)[0]
        if base in MODEL_SIZE_ESTIMATES_GB:
            total += MODEL_SIZE_ESTIMATES_GB[base]
            continue
        # Fallback conservative default for unknown models.
        total += 3.5
    return round(total, 1)


def collect_status(base_url: str, required_models: list[str]) -> OllamaStatus:
    supported = is_supported_os()
    installed = is_ollama_installed()
    running = is_ollama_running(base_url) if installed and supported else False
    installed_models = list_local_models(base_url) if running else set()

    missing: list[str] = []
    for model in required_models:
        m = model.strip()
        if not m:
            continue
        if m not in installed_models and m.split(":", 1)[0] not in installed_models:
            if m not in missing:
                missing.append(m)

    return OllamaStatus(
        supported_os=supported,
        installed=installed,
        running=running,
        installed_models=installed_models,
        missing_models=missing,
    )


def install_ollama_windows(
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Instalacion automatica disponible solo en Windows."

    _report_progress(on_progress, "Descargando instalador de Ollama...", 0.0)

    req = url_request.Request(OLLAMA_SETUP_URL, headers={"User-Agent": "CreatorFlowStudio/1.0"})
    try:
        with url_request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            with tempfile.NamedTemporaryFile(delete=False, suffix=".exe") as temp:
                setup_path = Path(temp.name)
                while True:
                    if cancel_event and cancel_event.is_set():
                        return False, "Instalacion de Ollama cancelada por usuario."
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    temp.write(chunk)
                    downloaded += len(chunk)
                    pct = None
                    if total > 0:
                        pct = min(80.0, (downloaded / total) * 80.0)
                    _report_progress(on_progress, "Descargando instalador de Ollama...", pct)
    except Exception as exc:
        return False, f"No se pudo descargar Ollama: {exc}"

    try:
        _report_progress(on_progress, "Instalando Ollama...", 85.0)
        # Keep installer silent to avoid opening Ollama UI during first-run setup.
        attempts = ["/VERYSILENT /NORESTART", "/SILENT /NORESTART", "/S"]
        ok = False
        last_code = -1
        for args in attempts:
            if cancel_event and cancel_event.is_set():
                return False, "Instalacion de Ollama cancelada por usuario."
            try:
                proc = subprocess.Popen([str(setup_path)] + (args.split() if args else []))
                waited_seconds = 0
                while True:
                    if cancel_event and cancel_event.is_set():
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        return False, "Instalacion de Ollama cancelada por usuario."
                    ret = proc.poll()
                    if ret is not None:
                        last_code = int(ret)
                        break
                    time.sleep(0.5)
                    waited_seconds += 1
                    if waited_seconds >= 1800:
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        return False, "Timeout instalando Ollama."
                if last_code in (0, 1638, 3010):
                    ok = True
                    break
            except Exception:
                continue

        if not ok:
            return False, f"Instalador de Ollama devolvio codigo {last_code}."

        _report_progress(on_progress, "Verificando instalacion de Ollama...", 95.0)
        for _ in range(20):
            if cancel_event and cancel_event.is_set():
                return False, "Instalacion de Ollama cancelada por usuario."
            if is_ollama_installed():
                _report_progress(on_progress, "Ollama instalado correctamente.", 100.0)
                return True, "OK"
            time.sleep(1)

        return False, "La instalacion finalizo pero Ollama no fue detectado."
    finally:
        try:
            setup_path.unlink(missing_ok=True)
        except Exception:
            pass


def try_start_ollama_server(base_url: str, on_progress: ProgressCallback | None = None) -> bool:
    if is_ollama_running(base_url):
        return True

    ollama_cli = _find_ollama_cli()
    if not ollama_cli:
        return False

    _report_progress(on_progress, "Iniciando servicio local de Ollama...", None)

    creationflags = 0
    startupinfo = None
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

    try:
        subprocess.Popen(
            [ollama_cli, "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            startupinfo=startupinfo,
        )
    except Exception:
        return False

    for _ in range(20):
        if is_ollama_running(base_url):
            return True
        time.sleep(0.8)
    return False


def pull_models(
    models: list[str],
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[bool, str]:
    unique_models = [m.strip() for m in models if m.strip()]
    if not unique_models:
        return True, "Sin modelos pendientes."

    ollama_cli = _find_ollama_cli()
    if not ollama_cli:
        return False, "No se encontro el ejecutable de Ollama para descargar modelos."

    pct_re = re.compile(r"(\d{1,3})%")

    for index, model in enumerate(unique_models, start=1):
        base_offset = ((index - 1) / len(unique_models)) * 100.0
        model_weight = 100.0 / len(unique_models)

        _report_progress(
            on_progress,
            f"Descargando modelo {index}/{len(unique_models)}: {model}",
            base_offset,
        )

        try:
            proc = subprocess.Popen(
                [ollama_cli, "pull", model],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except Exception as exc:
            return False, f"No se pudo ejecutar 'ollama pull {model}': {exc}"

        latest_pct = 0.0
        assert proc.stdout is not None
        for line in proc.stdout:
            if cancel_event and cancel_event.is_set():
                try:
                    proc.terminate()
                except Exception:
                    pass
                return False, "Descarga de modelos cancelada por usuario."

            text = line.strip()
            if not text:
                continue

            match = pct_re.search(text)
            if match:
                try:
                    model_pct = max(0.0, min(float(match.group(1)), 100.0))
                    latest_pct = model_pct
                    overall = base_offset + (model_pct / 100.0) * model_weight
                    _report_progress(
                        on_progress,
                        f"{model}: {text}",
                        overall,
                    )
                except Exception:
                    pass
            else:
                _report_progress(
                    on_progress,
                    f"{model}: {text}",
                    base_offset + (latest_pct / 100.0) * model_weight,
                )

        code = proc.wait(timeout=1800)
        if code != 0:
            return False, f"Fallo descarga de modelo '{model}' (codigo {code})."

    _report_progress(on_progress, "Modelos de Ollama listos.", 100.0)
    return True, "OK"


def remove_models(
    models: list[str],
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[bool, str]:
    """Remove selected Ollama models using `ollama rm` CLI."""
    selected = [m.strip() for m in models if m.strip()]
    if not selected:
        return True, "Sin modelos seleccionados para eliminar."

    ollama_cli = _find_ollama_cli()
    if not ollama_cli:
        return False, "No se encontro el ejecutable de Ollama para eliminar modelos."

    for idx, model in enumerate(selected, start=1):
        if cancel_event and cancel_event.is_set():
            return False, "Eliminacion de modelos cancelada por usuario."

        pct = (idx - 1) / max(1, len(selected)) * 100.0
        _report_progress(on_progress, f"Eliminando modelo {idx}/{len(selected)}: {model}", pct)

        try:
            run = subprocess.run(
                [ollama_cli, "rm", model],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
            )
        except Exception as exc:
            return False, f"No se pudo ejecutar 'ollama rm {model}': {exc}"

        if run.returncode != 0:
            detail = (run.stderr or run.stdout or "").strip()
            return False, f"No se pudo eliminar '{model}': {detail or ('codigo ' + str(run.returncode))}"

    _report_progress(on_progress, "Modelos eliminados correctamente.", 100.0)
    return True, "OK"


def uninstall_ollama_windows(
    on_progress: ProgressCallback | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[bool, str]:
    """Best-effort uninstallation of Ollama on Windows."""
    if os.name != "nt":
        return False, "Desinstalacion automatica de Ollama disponible solo en Windows."

    _report_progress(on_progress, "Preparando desinstalacion de Ollama...", 5.0)

    if cancel_event and cancel_event.is_set():
        return False, "Desinstalacion de Ollama cancelada por usuario."

    # Close running processes first to avoid uninstall blocks.
    for proc_name in ("ollama app.exe", "ollama.exe"):
        try:
            subprocess.run(
                ["taskkill", "/IM", proc_name, "/F"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except Exception:
            pass

    local = Path(os.environ.get("LOCALAPPDATA", ""))
    pf = Path(os.environ.get("ProgramFiles", ""))
    uninstall_candidates = [
        local / "Programs" / "Ollama" / "Uninstall Ollama.exe",
        local / "Programs" / "Ollama" / "Uninstall.exe",
        pf / "Ollama" / "Uninstall Ollama.exe",
        pf / "Ollama" / "Uninstall.exe",
    ]

    for idx, uninstaller in enumerate(uninstall_candidates, start=1):
        if cancel_event and cancel_event.is_set():
            return False, "Desinstalacion de Ollama cancelada por usuario."
        if not uninstaller.is_file():
            continue

        _report_progress(on_progress, f"Ejecutando desinstalador ({idx})...", 35.0)
        for args in ("/S", "/VERYSILENT /NORESTART", ""):
            if cancel_event and cancel_event.is_set():
                return False, "Desinstalacion de Ollama cancelada por usuario."
            try:
                proc = subprocess.Popen([str(uninstaller)] + (args.split() if args else []))
                waited = 0
                while True:
                    if cancel_event and cancel_event.is_set():
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        return False, "Desinstalacion de Ollama cancelada por usuario."
                    ret = proc.poll()
                    if ret is not None:
                        break
                    time.sleep(0.5)
                    waited += 1
                    if waited >= 900:
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        return False, "Timeout desinstalando Ollama."
            except Exception:
                continue

        break
    else:
        # Fallback to winget if local uninstaller is not available.
        _report_progress(on_progress, "Intentando desinstalar Ollama con winget...", 45.0)
        try:
            run = subprocess.run(
                [
                    "winget",
                    "uninstall",
                    "-e",
                    "--id",
                    "Ollama.Ollama",
                    "--silent",
                    "--accept-source-agreements",
                ],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if run.returncode != 0:
                return False, "No se encontro desinstalador local ni fue posible desinstalar con winget."
        except Exception:
            return False, "No se encontro desinstalador local ni fue posible desinstalar con winget."

    _report_progress(on_progress, "Verificando desinstalacion...", 90.0)
    for _ in range(20):
        if cancel_event and cancel_event.is_set():
            return False, "Desinstalacion de Ollama cancelada por usuario."
        if not is_ollama_installed():
            _report_progress(on_progress, "Ollama desinstalado correctamente.", 100.0)
            return True, "OK"
        time.sleep(1)

    return False, "La desinstalacion termino pero Ollama aun parece instalado."
