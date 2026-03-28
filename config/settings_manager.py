"""
Settings Manager — Gestión de configuración persistente en JSON.

Guarda y carga la configuración del usuario desde config/settings.json.
Presets personalizados almacenados en config/presets.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.utils import get_app_dir

# Carpeta escribible (junto al .exe o raíz del proyecto en dev)
_APP_DIR = get_app_dir()
CONFIG_DIR = _APP_DIR / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
PRESETS_FILE = CONFIG_DIR / "presets.json"

# Configuración por defecto
DEFAULT_SETTINGS: dict[str, Any] = {
    "audio_folder": "",
    "background_image": "",
    "output_folder": "",
    "fade_in": 2,
    "fade_out": 2,
    "resolution": "1080p",
    "enable_glitch": False,
    "glitch_intensity": 1,
    "glitch_speed": 300,
    "glitch_pulse": 6,
    "enable_overlay": False,
    "normalize_audio": False,
    "overlay_path": "",
    "overlay_opacity": 0.5,
    "crf": 18,
    "audio_bitrate": "320k",
    # Output Naming
    "naming_prefix": "",
    "naming_custom_list": [],
    "naming_auto_number": True,
    # Performance
    "cpu_mode": "Medium",
    "encode_preset": "slow",
    "gpu_encoding": False,
    # Text overlay
    "enable_text_overlay": False,
    "text_content": "",
    "text_position": "Bottom",
    "text_margin": 40,
    "text_font_size": 36,
    "text_glitch_intensity": 3,
    "text_glitch_speed": 4.0,
    # UI
    "theme": "Dark",
    "font_size": "Medium",
    # Multi-image
    "multi_image": False,
    "images_folder": "",
    # Slideshow mode
    "sl_images_folder": "",
    "sl_audio_enabled": False,
    "sl_audio_file": "",
    "sl_audio_mode": "file",
    "sl_audio_folder": "",
    "sl_crossfade": 2.0,
    "sl_output_folder": "",
    "sl_output_name": "slideshow",
    "sl_duration": 5.0,
    "sl_transition": "Crossfade",
    "sl_resolution": "1080p",
    "sl_crf": 18,
    "sl_cpu_mode": "Medium",
    "sl_encode_preset": "slow",
    "sl_gpu_encoding": False,
    # YouTube Publisher (UI scaffold only for now)
    "yt_source_folders": [],
    "yt_timezone": "America/Los_Angeles",
    "yt_videos_per_day": 3,
    "yt_window_start": "09:00",
    "yt_window_end": "21:00",
    "yt_default_category": "Music",
    "yt_default_made_for_kids": False,
    "yt_bulk_title_prefix": "",
    "yt_bulk_description": "",
    "yt_cached_channel_title": "",
    "yt_cached_channel_id": "",
    "yt_cached_channel_fetched_at": "",
    "yt_cached_drafts_rows": [],
    "yt_cached_drafts_fetched_at": "",
    "yt_cached_playlists": [],
    "yt_cached_playlists_fetched_at": "",
    # Prompt Lab
    "pl_workspace": "General",
    "pl_category": "General",
    "pl_skill": "Asistente General",
    "pl_model_mode": "Calidad alta",
    "pl_prompt_text": "",
    "pl_backend_url": "http://127.0.0.1:11434",
    "pl_model_quality": "llama3.1:8b",
    "pl_model_fast": "llama3.2:3b",
    "pl_active_skills": [{"category": "General", "skill": "Asistente General"}],
}

# Preset semilla — se crea si presets.json no existe
_SEED_PRESETS: dict[str, dict[str, Any]] = {
    "Default": {
        "fade_in": 2.0,
        "fade_out": 2.0,
        "resolution": "1080p",
        "enable_glitch": True,
        "glitch_intensity": 1,
        "glitch_speed": 300,
        "glitch_pulse": 6,
        "enable_overlay": False,
        "normalize_audio": False,
        "overlay_path": "Atmos Zone",
        "overlay_opacity": 0.5,
        "crf": 20,
        "naming_prefix": "",
        "naming_custom_list": [],
        "naming_auto_number": True,
        "cpu_mode": "Max",
        "encode_preset": "slow",
        "gpu_encoding": True,
        "enable_text_overlay": True,
        "text_content": "Atmos Zone",
        "text_position": "Bottom",
        "text_margin": 40,
        "text_font_size": 20,
        "text_glitch_intensity": 3,
        "text_glitch_speed": 1.0,
        "theme": "Dark",
        "font_size": "Large",
        "naming_mode": "Default",
        "text_font": "RockSalt-Regular",
    },
}

# Keys que NO se guardan en presets (son rutas de archivo específicas del proyecto)
_PRESET_EXCLUDED_KEYS = {
    "audio_folder", "background_image", "output_folder", "images_folder", "multi_image",
    # Slideshow paths / state (project-specific)
    "sl_images_folder", "sl_audio_file", "sl_audio_folder", "sl_audio_enabled", "sl_output_folder",
    # Shorts paths (project-specific)
    "sho_audio_file", "sho_background_image", "sho_images_folder", "sho_output_folder",
    "sho_multi_image",
    # YouTube sources (project-specific)
    "yt_source_folders",
}


class SettingsManager:
    """Gestiona la configuración de la aplicación con persistencia en JSON."""

    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._presets: dict[str, dict[str, Any]] = {}
        self.load()
        self._load_presets()

    # ------------------------------------------------------------------
    # Carga / Guardado de Settings
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Carga la configuración desde disco; si no existe usa los valores por defecto."""
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                self._settings = {**DEFAULT_SETTINGS, **stored}
            except (json.JSONDecodeError, OSError):
                self._settings = dict(DEFAULT_SETTINGS)

    def save(self) -> None:
        """Persiste la configuración actual en disco."""
        try:
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            raise RuntimeError(f"No se pudo guardar la configuración: {exc}") from exc

    # ------------------------------------------------------------------
    # Acceso
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._settings[key] = value

    def update(self, data: dict[str, Any]) -> None:
        self._settings.update(data)

    def all(self) -> dict[str, Any]:
        return dict(self._settings)

    # ------------------------------------------------------------------
    # Presets — persistencia
    # ------------------------------------------------------------------

    def _preset_template(self) -> dict[str, Any]:
        """Base shape for presets, excluding project-specific path keys."""
        return {k: v for k, v in DEFAULT_SETTINGS.items() if k not in _PRESET_EXCLUDED_KEYS}

    def _normalize_preset(self, preset_data: dict[str, Any]) -> dict[str, Any]:
        """Backfill missing keys with defaults and drop excluded/unknown keys."""
        base = self._preset_template()
        for key, value in preset_data.items():
            if key in base:
                base[key] = value
        return base

    def _load_presets(self) -> None:
        """Carga presets desde presets.json; si no existe, crea con preset semilla."""
        if PRESETS_FILE.exists():
            try:
                with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if not isinstance(raw, dict):
                    raise ValueError("Formato de presets inválido")
                normalized: dict[str, dict[str, Any]] = {}
                changed = False
                for name, pdata in raw.items():
                    if not isinstance(pdata, dict):
                        changed = True
                        continue
                    preset_name = str(name)
                    normalized_data = self._normalize_preset(pdata)
                    if pdata != normalized_data:
                        changed = True
                    normalized[preset_name] = normalized_data
                if not normalized:
                    normalized = {
                        name: self._normalize_preset(data)
                        for name, data in _SEED_PRESETS.items()
                    }
                    changed = True
                self._presets = normalized
                if changed:
                    self._save_presets()
            except (json.JSONDecodeError, OSError):
                self._presets = {
                    name: self._normalize_preset(data)
                    for name, data in _SEED_PRESETS.items()
                }
                self._save_presets()
            except ValueError:
                self._presets = {
                    name: self._normalize_preset(data)
                    for name, data in _SEED_PRESETS.items()
                }
                self._save_presets()
        else:
            self._presets = {
                name: self._normalize_preset(data)
                for name, data in _SEED_PRESETS.items()
            }
            self._save_presets()

    def _save_presets(self) -> None:
        """Persiste presets en presets.json."""
        try:
            with open(PRESETS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._presets, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            raise RuntimeError(f"No se pudo guardar presets: {exc}") from exc

    # ------------------------------------------------------------------
    # Presets — API pública
    # ------------------------------------------------------------------

    def available_presets(self) -> list[str]:
        """Retorna lista de nombres de presets en orden de inserción."""
        return list(self._presets.keys())

    def apply_preset(self, name: str) -> None:
        """Aplica un preset a la configuración actual."""
        if name not in self._presets:
            raise ValueError(f"Preset desconocido: '{name}'")
        self._settings.update(self._normalize_preset(self._presets[name]))

    def save_preset(self, name: str, settings: dict[str, Any]) -> None:
        """Guarda (o reemplaza) un preset con todas las configuraciones (excepto rutas)."""
        filtered = {k: v for k, v in settings.items() if k not in _PRESET_EXCLUDED_KEYS}
        self._presets[name] = self._normalize_preset(filtered)
        self._save_presets()

    def delete_preset(self, name: str) -> None:
        """Elimina un preset."""
        if name not in self._presets:
            raise ValueError(f"Preset '{name}' no existe.")
        del self._presets[name]
        self._save_presets()

    def rename_preset(self, old_name: str, new_name: str) -> None:
        """Renombra un preset."""
        if old_name not in self._presets:
            raise ValueError(f"Preset '{old_name}' no existe.")
        if new_name in self._presets:
            raise ValueError(f"Ya existe un preset con el nombre '{new_name}'.")
        # Preservar orden: reconstruir dict
        new_presets: dict[str, dict[str, Any]] = {}
        for k, v in self._presets.items():
            new_presets[new_name if k == old_name else k] = v
        self._presets = new_presets
        self._save_presets()

    def export_preset(self, name: str, file_path: str | Path) -> None:
        """Exporta un preset a un archivo JSON externo."""
        if name not in self._presets:
            raise ValueError(f"Preset '{name}' no existe.")
        data = {name: self._presets[name]}
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as exc:
            raise RuntimeError(f"No se pudo exportar el preset: {exc}") from exc

    def import_presets(self, file_path: str | Path) -> list[str]:
        """Importa presets desde un archivo JSON externo.

        Returns the list of preset names that were successfully imported.
        Skips keys in _PRESET_EXCLUDED_KEYS. Renames duplicates with ' (2)', ' (3)', etc.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            raise RuntimeError(f"No se pudo leer el archivo: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError("Formato de archivo inválido: se esperaba un objeto JSON.")
        imported: list[str] = []
        for raw_name, preset_data in data.items():
            if not isinstance(preset_data, dict):
                continue
            filtered = {k: v for k, v in preset_data.items() if k not in _PRESET_EXCLUDED_KEYS}
            # Resolve duplicate name
            name = str(raw_name)
            if name in self._presets:
                counter = 2
                while f"{name} ({counter})" in self._presets:
                    counter += 1
                name = f"{name} ({counter})"
            self._presets[name] = self._normalize_preset(filtered)
            imported.append(name)
        if imported:
            self._save_presets()
        return imported
