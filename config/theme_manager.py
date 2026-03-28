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
    "C_BG":               "#0E0E0E",
    "C_PANEL":            "#0E0E0E",
    "C_CARD":             "#131313",
    "C_BORDER":           "#484848",
    "C_ACCENT":           "#587EB8",
    "C_ACCENT_H":         "#80A1D3",
    "C_ACCENT_SLIDE":     "#8587F8",
    "C_ACCENT_SLIDE_H":   "#6760EC",
    "C_BTN_PRIMARY":      "#4361EE",
    "C_BTN_PRIMARY_TEXT": "#FFFFFF",
    "C_BTN_SECONDARY":    "#0E0E0E",
    "C_BTN_OK":           "#22C55E",
    "C_BTN_DANGER":       "#FF716C",
    "C_TEXT":             "#FFFFFF",
    "C_TEXT_DIM":         "#ADABAA",
    "C_MUTED":            "#707070",
    "C_HOVER":            "#1F2020",
    "C_SUCCESS":          "#22C55E",
    "C_ERROR":            "#FF716C",
    "C_WARN":             "#F59E0B",
    "C_INPUT":            "#262626",
    "C_LOG":              "#131313",
    "C_LOG_TEXT":         "#9AF1B9",
}

_LIGHT_DEFAULTS: dict[str, str] = {
    "C_BG":               "#F8F9FA",
    "C_PANEL":            "#F8F9FA",
    "C_CARD":             "#FFFFFF",
    "C_BORDER":           "#DEE2E6",
    "C_ACCENT":           "#4361EE",
    "C_ACCENT_H":         "#3451D1",
    "C_ACCENT_SLIDE":     "#8587F8",
    "C_ACCENT_SLIDE_H":   "#6760EC",
    "C_BTN_PRIMARY":      "#4361EE",
    "C_BTN_PRIMARY_TEXT": "#FFFFFF",
    "C_BTN_SECONDARY":    "#FFFFFF",
    "C_BTN_OK":           "#16A34A",
    "C_BTN_DANGER":       "#DC2626",
    "C_TEXT":             "#0F172A",
    "C_TEXT_DIM":         "#475569",
    "C_MUTED":            "#7B8794",
    "C_HOVER":            "#EEF2F7",
    "C_SUCCESS":          "#16A34A",
    "C_ERROR":            "#DC2626",
    "C_WARN":             "#D97706",
    "C_INPUT":            "#FFFFFF",
    "C_LOG":              "#1A1A2E",
    "C_LOG_TEXT":         "#22C55E",
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
        "Base y Superficies":   ["C_BG", "C_PANEL", "C_CARD", "C_INPUT", "C_LOG", "C_LOG_TEXT"],
        "Bordes y Hover":       ["C_BORDER", "C_HOVER"],
        "Texto":                ["C_TEXT", "C_TEXT_DIM", "C_MUTED"],
        "Acento — ATV":         ["C_ACCENT", "C_ACCENT_H"],
        "Acento — Slideshow":   ["C_ACCENT_SLIDE", "C_ACCENT_SLIDE_H"],
        "Botones":              ["C_BTN_PRIMARY", "C_BTN_PRIMARY_TEXT", "C_BTN_SECONDARY", "C_BTN_OK", "C_BTN_DANGER"],
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
