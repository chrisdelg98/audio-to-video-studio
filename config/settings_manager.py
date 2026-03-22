"""
Settings Manager — Gestión de configuración persistente en JSON.

Guarda y carga la configuración del usuario desde config/settings.json.
Presets personalizados almacenados en config/presets.json.
"""

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
    "zoom_max": 1.01,
    "zoom_speed": 500,
    "fade_in": 2,
    "fade_out": 2,
    "resolution": "1080p",
    "enable_zoom": True,
    "enable_glitch": False,
    "glitch_intensity": 1,
    "glitch_speed": 300,
    "glitch_pulse": 6,
    "enable_overlay": False,
    "normalize_audio": False,
    "overlay_path": "",
    "overlay_opacity": 0.5,
    "crf": 18,
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
}

# Preset semilla — se crea si presets.json no existe
_SEED_PRESETS: dict[str, dict[str, Any]] = {
    "Default": {
        "zoom_max": 1.01,
        "zoom_speed": 500,
        "fade_in": 2.0,
        "fade_out": 2.0,
        "resolution": "1080p",
        "enable_zoom": True,
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
_PRESET_EXCLUDED_KEYS = {"audio_folder", "background_image", "output_folder"}


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

    def _load_presets(self) -> None:
        """Carga presets desde presets.json; si no existe, crea con preset semilla."""
        if PRESETS_FILE.exists():
            try:
                with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                    self._presets = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._presets = dict(_SEED_PRESETS)
                self._save_presets()
        else:
            self._presets = dict(_SEED_PRESETS)
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
        self._settings.update(self._presets[name])

    def save_preset(self, name: str, settings: dict[str, Any]) -> None:
        """Guarda (o reemplaza) un preset con todas las configuraciones (excepto rutas)."""
        filtered = {k: v for k, v in settings.items() if k not in _PRESET_EXCLUDED_KEYS}
        self._presets[name] = filtered
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
