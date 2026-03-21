"""
Settings Manager — Gestión de configuración persistente en JSON.

Guarda y carga la configuración del usuario desde config/settings.json.
Incluye soporte para presets: lofi, ambient, jazz.
"""

import json
import os
from pathlib import Path
from typing import Any

# Ruta base del proyecto (dos niveles arriba de este archivo)
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
SETTINGS_FILE = CONFIG_DIR / "settings.json"

# Configuración por defecto
DEFAULT_SETTINGS: dict[str, Any] = {
    "audio_folder": "",
    "background_image": "",
    "output_folder": "",
    "zoom_max": 1.05,
    "zoom_speed": 300,
    "fade_in": 2,
    "fade_out": 2,
    "resolution": "1080p",
    "enable_zoom": True,
    "enable_glitch": False,
    "enable_overlay": False,
    "normalize_audio": False,
    "overlay_path": "",
    "overlay_opacity": 0.5,
    "crf": 18,
    # Output Naming
    "naming_mode": "Default",
    "naming_prefix": "",
    "naming_custom_list": [],
    "naming_auto_number": True,
    # Performance
    "cpu_mode": "Medium",
    "encode_preset": "slow",
    # Text overlay
    "enable_text_overlay": False,
    "text_content": "",
    "text_position": "Bottom",
    "text_margin": 40,
    "text_font_size": 36,
    "text_glitch_intensity": 3,
    "text_glitch_speed": 4.0,
}

# Presets de configuración
PRESETS: dict[str, dict[str, Any]] = {
    "lofi": {
        "zoom_max": 1.03,
        "zoom_speed": 500,
        "fade_in": 3,
        "fade_out": 3,
        "enable_zoom": True,
        "enable_glitch": False,
        "enable_overlay": False,
        "normalize_audio": True,
        "crf": 20,
    },
    "ambient": {
        "zoom_max": 1.02,
        "zoom_speed": 800,
        "fade_in": 5,
        "fade_out": 5,
        "enable_zoom": True,
        "enable_glitch": False,
        "enable_overlay": True,
        "normalize_audio": False,
        "crf": 18,
    },
    "jazz": {
        "zoom_max": 1.05,
        "zoom_speed": 200,
        "fade_in": 2,
        "fade_out": 2,
        "enable_zoom": True,
        "enable_glitch": True,
        "enable_overlay": False,
        "normalize_audio": False,
        "crf": 18,
    },
}


class SettingsManager:
    """Gestiona la configuración de la aplicación con persistencia en JSON."""

    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.load()

    # ------------------------------------------------------------------
    # Carga / Guardado
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Carga la configuración desde disco; si no existe usa los valores por defecto."""
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    stored = json.load(f)
                # Mezcla para preservar claves nuevas en DEFAULT_SETTINGS
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
    # Presets
    # ------------------------------------------------------------------

    def apply_preset(self, name: str) -> None:
        """Aplica un preset predefinido (lofi, ambient, jazz)."""
        if name not in PRESETS:
            raise ValueError(f"Preset desconocido: '{name}'. Disponibles: {list(PRESETS)}")
        self._settings.update(PRESETS[name])

    @staticmethod
    def available_presets() -> list[str]:
        return list(PRESETS.keys())
