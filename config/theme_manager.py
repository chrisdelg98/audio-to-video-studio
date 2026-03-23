"""
ThemeManager — Centralised theming system for Audio to Video Studio.

Loads and persists colour tokens for Dark/Light modes from theme.json.
Falls back to built-in defaults if the file is missing or malformed.

Usage:
    from config.theme_manager import ThemeManager
    TM = ThemeManager(theme_path=..., default_path=...)
    palette = TM.get_palette("Dark")      # dict of all C_* colours
    TM.set_color("C_ACCENT", "#ff0000")    # update + auto-save
    TM.reset()                             # restore from theme_default.json
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


# ── Built-in fallback palettes ──────────────────────────────────────────────
_DARK_DEFAULTS: dict[str, str] = {
    "C_BG":             "#010409",
    "C_PANEL":          "#010409",
    "C_CARD":           "#0d1117",
    "C_BORDER":         "#262C36",
    "C_ACCENT":         "#3b82f6",
    "C_ACCENT_H":       "#2563eb",
    "C_ACCENT_SLIDE":   "#7c3bf6",
    "C_ACCENT_SLIDE_H": "#6b2fe0",
    "C_BTN_PRIMARY":    "#3b82f6",
    "C_BTN_SECONDARY":  "#010409",
    "C_BTN_OK":         "#2d8f5a",
    "C_BTN_DANGER":     "#d64040",
    "C_TEXT":           "#eaeaf8",
    "C_TEXT_DIM":       "#7a7aa0",
    "C_MUTED":          "#505070",
    "C_HOVER":          "#1a1a30",
    "C_SUCCESS":        "#40c880",
    "C_ERROR":          "#e05050",
    "C_WARN":           "#e8a030",
    "C_INPUT":          "#010409",
    "C_LOG":            "#010409",
}

_LIGHT_DEFAULTS: dict[str, str] = {
    "C_BG":             "#f0f2f8",
    "C_PANEL":          "#e6e9f4",
    "C_CARD":           "#ffffff",
    "C_BORDER":         "#cdd2e8",
    "C_ACCENT":         "#4361ee",
    "C_ACCENT_H":       "#3451d1",
    "C_ACCENT_SLIDE":   "#7c3bf6",
    "C_ACCENT_SLIDE_H": "#6b2fe0",
    "C_BTN_PRIMARY":    "#4361ee",
    "C_BTN_SECONDARY":  "#dde2f0",
    "C_BTN_OK":         "#2d8f5a",
    "C_BTN_DANGER":     "#d64040",
    "C_TEXT":           "#18182e",
    "C_TEXT_DIM":       "#50507a",
    "C_MUTED":          "#8888aa",
    "C_HOVER":          "#dde2f0",
    "C_SUCCESS":        "#2d8f5a",
    "C_ERROR":          "#c83030",
    "C_WARN":           "#b87020",
    "C_INPUT":          "#f4f6ff",
    "C_LOG":            "#111128",
}

_FALLBACK_DATA: dict[str, Any] = {
    "current_theme": "Dark",
    "themes": {
        "Dark":  _DARK_DEFAULTS.copy(),
        "Light": _LIGHT_DEFAULTS.copy(),
    },
}


class ThemeManager:
    """Loads, persists and provides colour tokens for the application theme."""

    # All valid colour keys in display order
    KEYS: list[str] = list(_DARK_DEFAULTS.keys())

    # Grouped categories for the settings modal
    CATEGORIES: dict[str, list[str]] = {
        "Base y Superficies":   ["C_BG", "C_PANEL", "C_CARD", "C_INPUT", "C_LOG"],
        "Bordes y Hover":       ["C_BORDER", "C_HOVER"],
        "Texto":                ["C_TEXT", "C_TEXT_DIM", "C_MUTED"],
        "Acento — ATV":         ["C_ACCENT", "C_ACCENT_H"],
        "Acento — Slideshow":   ["C_ACCENT_SLIDE", "C_ACCENT_SLIDE_H"],
        "Botones":              ["C_BTN_PRIMARY", "C_BTN_SECONDARY", "C_BTN_OK", "C_BTN_DANGER"],
        "Estados":              ["C_SUCCESS", "C_ERROR", "C_WARN"],
    }

    def __init__(self, theme_path: Path, default_path: Path) -> None:
        self._theme_path = Path(theme_path)
        self._default_path = Path(default_path)
        self._data: dict[str, Any] = {}
        self._ensure_files()
        self._data = self._load_file(self._theme_path)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _ensure_files(self) -> None:
        """Create theme_default.json and theme.json from built-ins if missing."""
        if not self._default_path.exists():
            self._save_file(_FALLBACK_DATA, self._default_path)
        if not self._theme_path.exists():
            shutil.copy(str(self._default_path), str(self._theme_path))

    def _load_file(self, path: Path) -> dict[str, Any]:
        """Load and validate JSON; fill missing keys with built-in defaults."""
        try:
            with open(path, encoding="utf-8") as fh:
                data: dict[str, Any] = json.load(fh)
        except Exception:
            return _FALLBACK_DATA.copy()

        # Ensure both modes exist and all keys are present
        for mode, defaults in (("Dark", _DARK_DEFAULTS), ("Light", _LIGHT_DEFAULTS)):
            data.setdefault("themes", {})[mode] = {
                **defaults,
                **data.get("themes", {}).get(mode, {}),
            }
        return data

    def _save_file(self, data: dict[str, Any], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

    # ── Public API ────────────────────────────────────────────────────────

    def get_current_mode(self) -> str:
        return self._data.get("current_theme", "Dark")

    def set_current_mode(self, mode: str) -> None:
        """Persist the active theme mode (Dark/Light)."""
        self._data["current_theme"] = mode
        self.save()

    def get_palette(self, mode: str) -> dict[str, str]:
        """Return a copy of the full colour dict for the given mode."""
        defaults = _DARK_DEFAULTS if mode == "Dark" else _LIGHT_DEFAULTS
        return {**defaults, **self._data.get("themes", {}).get(mode, {})}

    def get_color(self, key: str, mode: str | None = None) -> str:
        """Return a single colour value for the current (or given) mode."""
        m = mode or self.get_current_mode()
        palette = self._data.get("themes", {}).get(m, {})
        default = _DARK_DEFAULTS if m == "Dark" else _LIGHT_DEFAULTS
        return palette.get(key, default.get(key, "#ffffff"))

    def set_color(self, key: str, value: str, mode: str | None = None) -> None:
        """Update a single colour and save to theme.json immediately."""
        m = mode or self.get_current_mode()
        self._data.setdefault("themes", {}).setdefault(m, {})[key] = value
        self.save()

    def save(self) -> None:
        """Persist current state to theme.json."""
        self._save_file(self._data, self._theme_path)

    def reset(self) -> None:
        """Restore all colours to defaults from theme_default.json."""
        self._data = self._load_file(self._default_path)
        self.save()
