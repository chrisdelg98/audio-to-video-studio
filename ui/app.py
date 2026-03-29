"""
App — Interfaz gráfica principal con CustomTkinter.

Layout:
  +---------------------------------------------+
  ¦  Header (título + validación de entorno)    ¦
  +---------------------------------------------¦
  ¦  Panel Izq.  ¦  Panel Der.                  ¦
  ¦  - Inputs    ¦  - Preview imagen            ¦
  ¦  - Parámetros¦  - Área de logs              ¦
  ¦  - Efectos   ¦  - Barra de progreso global  ¦
  ¦  - Presets   ¦  - Barra de progreso archivo ¦
  +---------------------------------------------¦
  ¦  Botones de acción                          ¦
  +---------------------------------------------+

Principios:
  - Toda la lógica de dominio vive en core/ y effects/
  - La UI solo llama a Runner y SettingsManager
  - Comunicación con el hilo de runner a través de after() (seguro para Tkinter)
"""

from __future__ import annotations

import ctypes
import datetime as dt
import json
import os
import threading
import time
import tkinter as tk
import tkinter.colorchooser as colorchooser
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from pathlib import Path
from typing import Any
try:
    from zoneinfo import ZoneInfo
except Exception:
    try:
        from backports.zoneinfo import ZoneInfo  # type: ignore
    except Exception:
        ZoneInfo = None  # type: ignore

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from config.settings_manager import SettingsManager
from config.theme_manager import ThemeManager as _ThemeManager
from core.runner import JobResult, Runner, ShortsJobResult, ShortsRunner
from core.shorts_splitter import distribute_fragments, suggest_quantity, validate_request
from core.slideshow_runner import SlideshowRunner
from core.naming_manager import NamingManager as _NamingManager
from core.utils import get_audio_files, get_audio_duration, get_image_files, get_bundle_dir
from core.ffmpeg_setup import ensure_ffmpeg
from core.ollama_setup import (
    collect_status as collect_ollama_status,
    estimate_models_size_gb,
    install_ollama_windows,
    list_installed_models_with_sizes,
    pull_models as pull_ollama_models,
    remove_models as remove_ollama_models,
    try_start_ollama_server,
    uninstall_ollama_windows,
)
from core.prompt_lab_backend import PromptBackendConfig, PromptLabBackend, PromptLabBackendError
from core.youtube_auth import YouTubeAuthError, YouTubeAuthService
from core.validator import ValidationResult, validate_environment
from config.prompt_lab_manager import PromptLabManager
from effects.text_overlay_effect import available_fonts
from ui.prompt_lab_tab import build_prompt_lab_panel
from ui.youtube_tab import build_youtube_publisher_panel

_BUNDLE_DIR = get_bundle_dir()

# -- Theme manager (singleton) -----------------------------------------------
_TM = _ThemeManager(
    theme_path=_BUNDLE_DIR / "theme.json",
    default_path=_BUNDLE_DIR / "theme_default.json",
)

# -- Font Awesome ------------------------------------------------------------
_FA_FONT_PATH = str(_BUNDLE_DIR / "fonts" / "Font Awesome 6 Free-Solid-900.otf")
_FA_FAMILY = "Font Awesome 6 Free Solid"  # Family name inside the .otf

def _load_font_awesome() -> None:
    """Registra Font Awesome como fuente del sistema (solo Windows)."""
    if os.name == "nt" and Path(_FA_FONT_PATH).exists():
        FR_PRIVATE = 0x10
        ctypes.windll.gdi32.AddFontResourceExW(_FA_FONT_PATH, FR_PRIVATE, 0)

_load_font_awesome()

# Iconos Font Awesome (codepoints Unicode)
FA_SAVE   = "\uf0c7"   # floppy-disk
FA_EDIT   = "\uf044"   # pen-to-square
FA_TRASH  = "\uf2ed"   # trash-can
FA_PLUS   = "\uf067"   # plus
FA_PLAY   = "\uf04b"   # play
FA_FILM    = "\uf008"   # film
FA_SHORTS  = "\uf03d"   # video 
FA_SUN     = "\uf185"   # sun
FA_MOON    = "\uf186"   # moon
FA_FOLDER  = "\uf07c"   # folder-open
FA_EXPAND  = "\uf065"   # up-right-and-down-left-from-center
FA_GEAR    = "\uf013"   # gear
FA_WAND    = "\uf0d0"   # wand-magic
FA_FONT_IC = "\uf031"   # font (icon)
FA_SLIDERS = "\uf1de"   # sliders
FA_TAG     = "\uf02b"   # tag
FA_LIST    = "\uf46d"   # clipboard-list
FA_STOP    = "\uf04d"   # stop
FA_EYE     = "\uf06e"   # eye
FA_WRENCH  = "\uf0ad"   # wrench
FA_BOLT    = "\uf0e7"   # bolt (rendimiento)
FA_IMAGES  = "\uf302"   # images (slideshow)
FA_YT      = "\uf167"   # youtube (brand)
FA_CHEVRON_DOWN  = "\uf078"   # chevron-down (expanded)
FA_CHEVRON_RIGHT = "\uf054"   # chevron-right (collapsed)
FA_DOWNLOAD      = "\uf019"   # download (arrow-down-to-line)
FA_UPLOAD        = "\uf093"   # upload (arrow-up-from-bracket)
FA_CHECK         = "\uf00c"   # check
FA_WARNING       = "\uf071"   # triangle-exclamation


# -- Tema --------------------------------------------------------------------
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# -- Design system (dark defaults — Obsidian Curator) ---------------------
C_BG            = "#0E0E0E"   # Root background — The void
C_PANEL         = "#0E0E0E"   # Panel background
C_CARD          = "#131313"   # Card / surface container low
C_BORDER        = "#484848"   # UI Outline (ghost border)
C_ACCENT        = "#7CA8FF"   # Primary Electric — modo ATV
C_ACCENT_H      = "#9FC0FF"   # Accent hover +10%
C_ACCENT_SLIDE  = "#8587F8"   # Indigo — modo Slideshow
C_ACCENT_SLIDE_H= "#6760EC"   # Indigo hover
C_ACCENT_SHORTS = "#F97316"   # Orange — modo Shorts
C_ACCENT_SHORTS_H="#FB923C"   # Orange hover
C_ACCENT_YT     = "#FF4D4F"   # Red — modo YouTube Publisher
C_ACCENT_YT_H   = "#FF6B6D"   # Red hover
C_ACCENT_LAB    = "#14B8A6"   # Teal — modo Prompt Lab
C_ACCENT_LAB_H  = "#2DD4BF"   # Teal hover
C_BTN_PRIMARY   = "#7CA8FF"   # Generate / primary CTA (light blue)
C_BTN_PRIMARY_TEXT = "#002C65" # Text on primary CTA (dark navy)
C_BTN_SECONDARY = "#0E0E0E"   # Secondary button bg (ghost)
C_BTN_OK        = "#22C55E"   # OK / success action
C_BTN_DANGER    = "#FF716C"   # Danger / destructive
C_TEXT          = "#FFFFFF"   # Primary text — On-Surface
C_TEXT_DIM      = "#ADABAA"   # Secondary — On-Surface Variant
C_MUTED         = "#707070"   # Muted labels / hints
C_HOVER         = "#1F2020"   # Surface Container High
C_SUCCESS       = "#22C55E"
C_ERROR         = "#FF716C"
C_WARN          = "#F59E0B"
C_INPUT         = "#262626"   # Input field background (Surface High)
C_LOG           = "#131313"   # Log textarea background
C_LOG_TEXT      = "#9AF1B9"   # Log text color (terminal green)

# -- Paletas -----------------------------------------------------------------
_DARK_PALETTE: dict[str, str] = {
    "BG": "#0E0E0E", "PANEL": "#0E0E0E", "CARD": "#131313", "BORDER": "#484848",
    "ACCENT": "#7CA8FF", "ACCENT_H": "#9FC0FF",
    "BTN_PRIMARY": "#7CA8FF", "BTN_PRIMARY_TEXT": "#002C65", "BTN_SECONDARY": "#0E0E0E",
    "BTN_OK": "#22C55E", "BTN_DANGER": "#FF716C",
    "TEXT": "#FFFFFF", "TEXT_DIM": "#ADABAA", "MUTED": "#707070",
    "HOVER": "#1F2020",
    "SUCCESS": "#22C55E", "ERROR": "#FF716C", "WARN": "#F59E0B",
    "INPUT": "#262626", "LOG": "#131313", "LOG_TEXT": "#9AF1B9",
}
_LIGHT_PALETTE: dict[str, str] = {
    "BG": "#F8F9FA", "PANEL": "#F8F9FA", "CARD": "#FFFFFF", "BORDER": "#DEE2E6",
    "ACCENT": "#4361EE", "ACCENT_H": "#3451D1",
    "BTN_PRIMARY": "#4361EE", "BTN_PRIMARY_TEXT": "#FFFFFF", "BTN_SECONDARY": "#FFFFFF",
    "BTN_OK": "#16A34A", "BTN_DANGER": "#DC2626",
    "TEXT": "#0F172A", "TEXT_DIM": "#475569", "MUTED": "#7B8794",
    "HOVER": "#EEF2F7",
    "SUCCESS": "#16A34A", "ERROR": "#DC2626", "WARN": "#D97706",
    "INPUT": "#FFFFFF", "LOG": "#1A1A2E", "LOG_TEXT": "#22C55E",
}

_FONT_SIZE_SCALE = {"Small": 1.0, "Medium": 1.22, "Large": 1.5}


def _apply_theme(mode: str) -> None:
    """Actualiza las variables globales de color leyendo desde ThemeManager."""
    global C_BG, C_PANEL, C_CARD, C_BORDER, C_ACCENT, C_ACCENT_H
    global C_ACCENT_SLIDE, C_ACCENT_SLIDE_H
    global C_ACCENT_SHORTS, C_ACCENT_SHORTS_H
    global C_ACCENT_YT, C_ACCENT_YT_H
    global C_ACCENT_LAB, C_ACCENT_LAB_H
    global C_BTN_PRIMARY, C_BTN_PRIMARY_TEXT, C_BTN_SECONDARY, C_BTN_OK, C_BTN_DANGER
    global C_TEXT, C_TEXT_DIM, C_MUTED, C_HOVER
    global C_SUCCESS, C_ERROR, C_WARN, C_INPUT, C_LOG, C_LOG_TEXT
    t = _TM.get_palette(mode)
    C_BG = t["C_BG"]; C_PANEL = t["C_PANEL"]; C_CARD = t["C_CARD"]; C_BORDER = t["C_BORDER"]
    C_ACCENT = t["C_ACCENT"]; C_ACCENT_H = t["C_ACCENT_H"]
    C_ACCENT_SLIDE = t["C_ACCENT_SLIDE"]; C_ACCENT_SLIDE_H = t["C_ACCENT_SLIDE_H"]
    # Shorts/YouTube accents are fixed (not exposed in ThemeManager yet)
    C_ACCENT_SHORTS = "#F97316"; C_ACCENT_SHORTS_H = "#FB923C"
    C_ACCENT_YT = "#FF4D4F"; C_ACCENT_YT_H = "#FF6B6D"
    C_ACCENT_LAB = "#14B8A6"; C_ACCENT_LAB_H = "#2DD4BF"
    C_BTN_PRIMARY = t["C_BTN_PRIMARY"]; C_BTN_PRIMARY_TEXT = t["C_BTN_PRIMARY_TEXT"]; C_BTN_SECONDARY = t["C_BTN_SECONDARY"]
    C_BTN_OK = t["C_BTN_OK"]; C_BTN_DANGER = t["C_BTN_DANGER"]
    C_TEXT = t["C_TEXT"]; C_TEXT_DIM = t["C_TEXT_DIM"]; C_MUTED = t["C_MUTED"]
    C_HOVER = t["C_HOVER"]
    C_SUCCESS = t["C_SUCCESS"]; C_ERROR = t["C_ERROR"]; C_WARN = t["C_WARN"]
    C_INPUT = t["C_INPUT"]; C_LOG = t["C_LOG"]; C_LOG_TEXT = t["C_LOG_TEXT"]


# -- Hover-transition animation helpers --------------------------------------
_ANIM_JOBS:  dict = {}   # widget id ? pending animation after-job id
_LEAVE_JOBS: dict = {}   # widget id ? pending leave-debounce after-job id


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def _center_window_on_screen(window: tk.Toplevel) -> None:
    """Center a toplevel window on the current screen."""
    window.update_idletasks()
    w = max(window.winfo_width(), window.winfo_reqwidth())
    h = max(window.winfo_height(), window.winfo_reqheight())
    sw = window.winfo_screenwidth()
    sh = window.winfo_screenheight()
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    window.geometry(f"+{x}+{y}")


def _animate_widget(widget, props: dict, steps: int = 10, delay: int = 14, _step: int = 0) -> None:
    """Smoothly interpolate colour properties on a CTk widget.
    props = {attribute_name: (from_hex, to_hex)}
    Total duration ˜ steps × delay ms  (default ~140 ms).
    """
    wid = id(widget)
    if _step == 0 and wid in _ANIM_JOBS:
        try:
            widget.after_cancel(_ANIM_JOBS.pop(wid))
        except Exception:
            _ANIM_JOBS.pop(wid, None)
    if _step > steps:
        _ANIM_JOBS.pop(wid, None)
        return
    alpha = _step / steps
    kw: dict = {}
    for attr, (from_h, to_h) in props.items():
        r1, g1, b1 = _hex_to_rgb(from_h)
        r2, g2, b2 = _hex_to_rgb(to_h)
        kw[attr] = _rgb_to_hex(
            round(r1 + (r2 - r1) * alpha),
            round(g1 + (g2 - g1) * alpha),
            round(b1 + (b2 - b1) * alpha),
        )
    try:
        widget.configure(**kw)
        job = widget.after(delay, lambda: _animate_widget(widget, props, steps, delay, _step + 1))
        _ANIM_JOBS[wid] = job
    except Exception:
        _ANIM_JOBS.pop(wid, None)


def _val_to_pct(v: float, lo: float, hi: float) -> str:
    """Convert a real value to a percentage string given its range."""
    rng = hi - lo
    if rng == 0:
        return "0%"
    return f"{int(round((v - lo) / rng * 100))}%"


def _init_scrollbar(frame: "ctk.CTkScrollableFrame", width: int = 6) -> None:  # noqa: ARG001
    """Hide the built-in scrollbar — scrolling is done via mouse wheel only."""
    frame._scrollbar.grid_remove()


def _apply_sec_hover(btn: "ctk.CTkButton") -> None:
    """Animated accent hover for secondary buttons.

    Debounces leave events (40 ms) so that crossing internal child widgets
    (the CTkButton text label) does not restart the animation. A state flag
    prevents redundant enter/leave calls.
    """
    _state = {"entered": False}

    def _cancel_leave():
        wid = id(btn)
        if wid in _LEAVE_JOBS:
            try:
                btn.after_cancel(_LEAVE_JOBS.pop(wid))
            except Exception:
                _LEAVE_JOBS.pop(wid, None)

    def on_enter(_e):
        _cancel_leave()
        if _state["entered"] or str(btn.cget("state")) == "disabled":
            return
        _state["entered"] = True
        _animate_widget(btn, {
            "border_color": (C_BORDER, C_ACCENT),
            "text_color":   (C_TEXT,   C_ACCENT),
        })

    def on_leave(_e):
        def _do_leave():
            _LEAVE_JOBS.pop(id(btn), None)
            if not _state["entered"]:
                return
            _state["entered"] = False
            _animate_widget(btn, {
                "border_color": (C_ACCENT, C_BORDER),
                "text_color":   (C_ACCENT, C_TEXT),
            })
        _cancel_leave()
        _LEAVE_JOBS[id(btn)] = btn.after(40, _do_leave)

    # Bind the button frame and all its internal children (text label, etc.)
    for widget in (btn, *btn.winfo_children()):
        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Leave>", on_leave, add="+")



class _Tooltip:
    """Ventana flotante que aparece al pasar el mouse sobre un widget."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._win: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event: object = None) -> None:
        if self._win:
            return
        # Use current theme globals for consistent styling
        bg = C_CARD
        fg = C_TEXT
        border_c = C_BORDER
        wx = self._widget.winfo_rootx() + self._widget.winfo_width() + 8
        wy = self._widget.winfo_rooty()
        self._win = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.configure(bg=bg)
        tw.wm_geometry(f"+{wx}+{wy}")
        tk.Label(
            tw,
            text=self._text,
            justify="left",
            bg=bg,
            fg=fg,
            font=("Segoe UI", 10),
            wraplength=300,
            padx=12,
            pady=10,
            relief="flat",
            bd=0,
        ).pack()
        tw.configure(highlightbackground=border_c, highlightthickness=1)

    def _hide(self, _event: object = None) -> None:
        if self._win:
            self._win.destroy()
            self._win = None


# ------------------------------------------------------------------------------
# DIÁLOGO DE ASIGNACIÓN MULTI-IMAGEN
# ------------------------------------------------------------------------------

class ImageAssignmentDialog(ctk.CTkToplevel):
    """Modal que permite asignar una imagen de fondo a cada archivo de audio."""

    def __init__(
        self,
        parent: ctk.CTk,
        audio_files: list[Path],
        image_files: list[Path],
        current_assignment: dict[str, Path],
    ) -> None:
        super().__init__(parent)
        self.title("Asignación de imágenes por audio")
        self.resizable(False, False)
        self.grab_set()

        self._audio_files = audio_files
        self._image_files = image_files
        self._image_names = [f.name for f in image_files]
        self.result: dict[str, Path] | None = None

        # Build initial assignment: use current or round-robin
        self._vars: dict[str, tk.StringVar] = {}
        for i, af in enumerate(audio_files):
            img_path = current_assignment.get(af.name)
            if img_path and img_path.name in self._image_names:
                val = img_path.name
            else:
                val = image_files[i % len(image_files)].name
            self._vars[af.name] = tk.StringVar(value=val)

        self._build()
        self.after(50, self._center)

    def _center(self) -> None:
        _center_window_on_screen(self)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self, text="Asignar imagen a cada audio",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C_TEXT,
        ).grid(row=0, column=0, padx=16, pady=(14, 4), sticky="w")

        ctk.CTkLabel(
            self,
            text="Puedes cambiar la imagen para cada audio individualmente.\n"
                 "Usa 'Reset auto' para volver a la distribución round-robin.",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
            justify="left",
        ).grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")

        # Scrollable list
        scroll = ctk.CTkScrollableFrame(self, width=560, height=320, fg_color=C_CARD)
        scroll.grid(row=2, column=0, padx=12, pady=(0, 8), sticky="ew")
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=0)

        ctk.CTkLabel(scroll, text="Audio", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUTED, anchor="w").grid(row=0, column=0, sticky="w", padx=8, pady=(4, 2))
        ctk.CTkLabel(scroll, text="Imagen", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color=C_MUTED, anchor="w").grid(row=0, column=1, sticky="w", padx=8, pady=(4, 2))

        for row_idx, af in enumerate(self._audio_files, start=1):
            ctk.CTkLabel(
                scroll, text=af.name, font=ctk.CTkFont(size=11),
                text_color=C_TEXT, anchor="w",
            ).grid(row=row_idx, column=0, sticky="ew", padx=12, pady=2)
            ctk.CTkOptionMenu(
                scroll,
                values=self._image_names,
                variable=self._vars[af.name],
                width=200,
                fg_color=C_CARD,
                button_color=C_ACCENT,
                text_color=C_TEXT,
                font=ctk.CTkFont(size=11),
            ).grid(row=row_idx, column=1, sticky="w", padx=8, pady=2)

        # Buttons row
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="ew")
        btn_row.grid_columnconfigure(1, weight=1)

        _btn_reset_auto = ctk.CTkButton(
            btn_row, text="Reset auto",
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, width=110, height=32,
            command=self._reset_auto,
        )
        _btn_reset_auto.grid(row=0, column=0, padx=(0, 8))
        _apply_sec_hover(_btn_reset_auto)

        _btn_cancel_assign = ctk.CTkButton(
            btn_row, text="Cancelar",
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, width=90, height=32,
            command=self.destroy,
        )
        _btn_cancel_assign.grid(row=0, column=2, padx=(8, 4))
        _apply_sec_hover(_btn_cancel_assign)

        ctk.CTkButton(
            btn_row, text="Confirmar",
            fg_color=C_BTN_PRIMARY, hover_color=C_ACCENT_H,
            text_color=C_BTN_PRIMARY_TEXT, width=100, height=32,
            command=self._confirm,
        ).grid(row=0, column=3, padx=(4, 0))

    def _reset_auto(self) -> None:
        for i, af in enumerate(self._audio_files):
            self._vars[af.name].set(self._image_files[i % len(self._image_files)].name)

    def _confirm(self) -> None:
        name_to_path = {f.name: f for f in self._image_files}
        self.result = {
            af.name: name_to_path[self._vars[af.name].get()]
            for af in self._audio_files
        }
        self.destroy()


# ------------------------------------------------------------------------------
# DIÁLOGO DE LISTA DE NOMBRES PERSONALIZADOS
# ------------------------------------------------------------------------------

class NamesListDialog(ctk.CTkToplevel):
    """Modal para editar la lista de nombres personalizados de canciones."""

    _USED_PREFIX = "\u25a0 "  # ¦ + space

    def __init__(self, parent: ctk.CTk, current_names: list[str],
                 used_names: set[str] | None = None) -> None:
        super().__init__(parent)
        self.title("Lista de nombres personalizados")
        self.resizable(False, False)
        self.grab_set()
        self.result: list[str] | None = None
        self._used_names = used_names or set()
        # Prepend \u25a0 to names that are in used set
        self._current = [
            (self._USED_PREFIX + n if n in self._used_names else n)
            for n in current_names
        ]
        self._build()
        self.after(50, self._center)

    def _center(self) -> None:
        _center_window_on_screen(self)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        # Header
        ctk.CTkLabel(
            self, text="Nombres personalizados",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT,
        ).grid(row=0, column=0, padx=16, pady=(14, 2), sticky="w")

        self._lbl_count = ctk.CTkLabel(
            self, text=self._count_text(),
            font=ctk.CTkFont(size=11), text_color=C_MUTED,
        )
        self._lbl_count.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")

        # Textbox
        self._txt = ctk.CTkTextbox(
            self, width=520, height=380,
            fg_color=C_INPUT, text_color=C_TEXT,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self._txt.grid(row=2, column=0, padx=12, pady=(0, 6), sticky="nsew")
        if self._current:
            self._txt.insert("1.0", "\n".join(self._current))
        self._apply_used_tags()
        self._txt.bind("<KeyRelease>", self._on_text_change)

        # Buttons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.grid(row=3, column=0, padx=12, pady=(0, 12), sticky="ew")
        btn_row.grid_columnconfigure(2, weight=1)

        _btn_limpiar_todo = ctk.CTkButton(
            btn_row, text="Limpiar todo",
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, width=110, height=32,
            command=self._clear_all,
        )
        _btn_limpiar_todo.grid(row=0, column=0, padx=(0, 4))
        _apply_sec_hover(_btn_limpiar_todo)

        _btn_limpiar_usados = ctk.CTkButton(
            btn_row, text="Limpiar usados",
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, width=120, height=32,
            command=self._clear_used,
        )
        _btn_limpiar_usados.grid(row=0, column=1, padx=(0, 4))
        _apply_sec_hover(_btn_limpiar_usados)

        _btn_cancel_names = ctk.CTkButton(
            btn_row, text="Cancelar",
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, width=90, height=32,
            command=self.destroy,
        )
        _btn_cancel_names.grid(row=0, column=3, padx=(8, 4))
        _apply_sec_hover(_btn_cancel_names)

        ctk.CTkButton(
            btn_row, text="Confirmar",
            fg_color=C_BTN_PRIMARY, hover_color=C_ACCENT_H,
            text_color=C_BTN_PRIMARY_TEXT, width=100, height=32,
            command=self._confirm,
        ).grid(row=0, column=4, padx=(4, 0))

    def _apply_used_tags(self) -> None:
        """Aplica color muted a las l\xedneas marcadas con \u25a0."""
        tb = self._txt._textbox
        tb.tag_configure("used_line", foreground="#4a4a6a")
        tb.tag_remove("used_line", "1.0", "end")
        lines = self._txt.get("1.0", "end").splitlines()
        for i, line in enumerate(lines):
            if line.startswith(self._USED_PREFIX):
                tb.tag_add("used_line", f"{i + 1}.0", f"{i + 1}.end")

    def _count_text(self) -> str:
        lines = self._txt.get("1.0", "end").splitlines() if hasattr(self, "_txt") else self._current
        total = sum(1 for l in lines if l.strip())
        used = sum(1 for l in lines if l.strip().startswith(self._USED_PREFIX))
        base = f"{total} nombre{'s' if total != 1 else ''} en la lista"
        return base + (f"  ({used} usados)" if used else "")

    def _on_text_change(self, _event: object = None) -> None:
        self._apply_used_tags()
        self._lbl_count.configure(text=self._count_text())

    def _clear_all(self) -> None:
        self._txt.delete("1.0", "end")
        self._lbl_count.configure(text=self._count_text())

    def _clear_used(self) -> None:
        lines = self._txt.get("1.0", "end").splitlines()
        clean = [l for l in lines if not l.strip().startswith(self._USED_PREFIX)]
        self._txt.delete("1.0", "end")
        if clean:
            self._txt.insert("1.0", "\n".join(clean))
        self._lbl_count.configure(text=self._count_text())

    def _confirm(self) -> None:
        p = self._USED_PREFIX
        self.result = [
            (l.strip()[len(p):] if l.strip().startswith(p) else l.strip())
            for l in self._txt.get("1.0", "end").splitlines()
            if l.strip() and l.strip() != p.strip()
        ]
        self.destroy()


# ------------------------------------------------------------------------------
# DIÁLOGO DE CONFIGURACIÓN DE TEMA
# ------------------------------------------------------------------------------

class ThemeSettingsDialog(ctk.CTkToplevel):
    """Modal para editar los colores del tema (Dark/Light) en tiempo real."""

    # Human-readable labels for each key
    _KEY_LABELS: dict[str, str] = {
        "C_BG":             "Fondo principal",
        "C_PANEL":          "Fondo de paneles",
        "C_CARD":           "Fondo de tarjetas",
        "C_INPUT":          "Fondo de inputs",
        "C_LOG":            "Fondo de logs",
        "C_LOG_TEXT":       "Texto de logs",
        "C_BORDER":         "Bordes",
        "C_HOVER":          "Hover de superficies",
        "C_TEXT":           "Texto principal",
        "C_TEXT_DIM":       "Texto secundario",
        "C_MUTED":          "Texto apagado",
        "C_ACCENT":         "Acento ATV",
        "C_ACCENT_H":       "Acento ATV (hover)",
        "C_ACCENT_SLIDE":   "Acento Slideshow",
        "C_ACCENT_SLIDE_H": "Acento Slideshow (hover)",
        "C_BTN_PRIMARY":      "Botón primario",
        "C_BTN_PRIMARY_TEXT": "Texto de botón primario",
        "C_BTN_SECONDARY":    "Botón secundario",
        "C_BTN_OK":         "Botón OK",
        "C_BTN_DANGER":     "Botón peligro",
        "C_SUCCESS":        "Éxito",
        "C_ERROR":          "Error",
        "C_WARN":           "Advertencia",
    }

    def __init__(self, parent: "AudioToVideoApp") -> None:
        super().__init__(parent)
        self._app = parent
        self.title("Configuración de Tema")
        self.resizable(True, True)
        self.geometry("540x680")
        self.minsize(480, 500)
        self.configure(fg_color=C_BG)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search)
        self._swatch_widgets: dict[str, ctk.CTkFrame] = {}
        self._hex_labels: dict[str, ctk.CTkLabel] = {}
        self._row_frames: dict[str, ctk.CTkFrame] = {}
        self._copy_btns: dict[str, ctk.CTkButton] = {}

        self._build()
        self.after(60, self._center)

    def _center(self) -> None:
        _center_window_on_screen(self)

    # -- Build --------------------------------------------------------------

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # -- Header (title | spacer | badge | toggle button) ----------
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 0))
        hdr.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            hdr, text="Configuración de Tema",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=C_TEXT,
        ).grid(row=0, column=0, sticky="w")

        _mode_color = C_ACCENT if self._app._current_theme == "Dark" else C_ACCENT_SLIDE
        self._mode_badge = ctk.CTkFrame(hdr, fg_color=C_CARD, corner_radius=10,
                                        border_width=1, border_color=_mode_color)
        self._mode_badge.grid(row=0, column=2, sticky="e", padx=(0, 8))
        self._mode_lbl = ctk.CTkLabel(
            self._mode_badge, text=f"? {self._app._current_theme}",
            font=ctk.CTkFont(size=10, weight="bold"), text_color=_mode_color,
        )
        self._mode_lbl.pack(padx=10, pady=4)

        _btn_toggle_mode = ctk.CTkButton(
            hdr, text="Dark / Light", height=28, width=120,
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, corner_radius=6,
            font=ctk.CTkFont(size=11),
            command=self._toggle_mode,
        )
        _btn_toggle_mode.grid(row=0, column=3, sticky="e")
        _apply_sec_hover(_btn_toggle_mode)

        # -- Search bar --
        search_f = ctk.CTkFrame(self, fg_color="transparent")
        search_f.grid(row=1, column=0, sticky="ew", padx=20, pady=(10, 0))
        search_f.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(
            search_f, textvariable=self._search_var,
            placeholder_text="Buscar variable de color...",
            height=34, corner_radius=8,
            fg_color=C_CARD, border_color=C_BORDER,
            text_color=C_TEXT, placeholder_text_color=C_MUTED,
        ).grid(row=0, column=0, sticky="ew")

        # -- Scrollable list --
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
        )
        self._scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=(10, 0))
        self._scroll.grid_columnconfigure(0, weight=1)
        _init_scrollbar(self._scroll, width=8)

        self._build_color_list()

        # -- Footer --
        footer = ctk.CTkFrame(self, fg_color=C_CARD, corner_radius=0,
                               border_width=1, border_color=C_BORDER)
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        footer.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            footer, text="?  Restablecer por defecto",
            fg_color=C_BTN_DANGER, hover_color=C_ERROR,
            text_color="#ffffff", height=34, corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._reset,
        ).grid(row=0, column=0, padx=(14, 8), pady=10)

        _btn_close_theme = ctk.CTkButton(
            footer, text="Cerrar",
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, height=34, width=90, corner_radius=6,
            font=ctk.CTkFont(size=11),
            command=self.destroy,
        )
        _btn_close_theme.grid(row=0, column=2, padx=(8, 14), pady=10)
        _apply_sec_hover(_btn_close_theme)

    def _build_color_list(self) -> None:
        """Populate the scrollable frame with category headers and color rows."""
        r = 0
        for cat, keys in _TM.CATEGORIES.items():
            # Category label
            cat_f = ctk.CTkFrame(self._scroll, fg_color="transparent")
            cat_f.grid(row=r, column=0, sticky="ew", padx=4, pady=(8, 2))
            ctk.CTkLabel(
                cat_f, text=cat.upper(),
                font=ctk.CTkFont(size=9, weight="bold"),
                text_color=C_MUTED,
            ).pack(anchor="w", padx=8)
            r += 1

            # Separator under category label
            ctk.CTkFrame(self._scroll, height=1, fg_color=C_BORDER, corner_radius=0
                         ).grid(row=r, column=0, sticky="ew", padx=12, pady=(0, 4))
            r += 1

            for key in keys:
                color = _TM.get_color(key, self._app._current_theme)
                row_f = ctk.CTkFrame(
                    self._scroll, fg_color=C_CARD, corner_radius=8,
                    border_width=1, border_color=C_BORDER,
                )
                row_f.grid(row=r, column=0, sticky="ew", padx=4, pady=2)
                row_f.grid_columnconfigure(2, weight=1)
                self._row_frames[key] = row_f

                # Color swatch — clickable
                swatch = ctk.CTkFrame(
                    row_f, fg_color=color, width=36, height=36,
                    corner_radius=6, cursor="hand2",
                    border_width=1, border_color=C_BORDER,
                )
                swatch.grid(row=0, column=0, padx=(10, 8), pady=8)
                swatch.grid_propagate(False)
                swatch.bind("<Button-1>", lambda e, k=key: self._pick_color(k))
                self._swatch_widgets[key] = swatch

                # Key + description
                labels_f = ctk.CTkFrame(row_f, fg_color="transparent")
                labels_f.grid(row=0, column=1, sticky="w")
                ctk.CTkLabel(
                    labels_f, text=key,
                    font=ctk.CTkFont(size=11, weight="bold", family="Consolas"),
                    text_color=C_TEXT, anchor="w",
                ).pack(anchor="w")
                ctk.CTkLabel(
                    labels_f, text=self._KEY_LABELS.get(key, ""),
                    font=ctk.CTkFont(size=10), text_color=C_MUTED, anchor="w",
                ).pack(anchor="w")

                # Hex value
                hex_lbl = ctk.CTkLabel(
                    row_f, text=color.upper(),
                    font=ctk.CTkFont(size=11, family="Consolas"),
                    text_color=C_TEXT_DIM, anchor="e",
                )
                hex_lbl.grid(row=0, column=2, sticky="e", padx=8)
                self._hex_labels[key] = hex_lbl

                # Buttons: copy + edit
                btns_f = ctk.CTkFrame(row_f, fg_color="transparent")
                btns_f.grid(row=0, column=3, padx=(4, 10), pady=8)

                copy_btn = ctk.CTkButton(
                    btns_f, text="?", width=30, height=30,
                    fg_color="transparent", hover_color=C_HOVER,
                    border_width=1, border_color=C_BORDER,
                    text_color=C_TEXT_DIM, corner_radius=6,
                    font=ctk.CTkFont(size=13),
                    command=lambda v=color, b=None: self._copy_hex(v, b),
                )
                copy_btn.pack(side="left", padx=(0, 4))
                # rebind with actual button ref
                copy_btn.configure(command=lambda v=color, b=copy_btn: self._copy_hex(v, b))
                self._copy_btns[key] = copy_btn

                ctk.CTkButton(
                    btns_f, text="?", width=30, height=30,
                    fg_color=C_ACCENT, hover_color=C_ACCENT_H,
                    text_color="#ffffff", corner_radius=6,
                    font=ctk.CTkFont(size=13),
                    command=lambda k=key: self._pick_color(k),
                ).pack(side="left")

                r += 1

    # -- Actions ------------------------------------------------------------

    def _pick_color(self, key: str) -> None:
        """Open native color picker and apply the chosen value."""
        current = _TM.get_color(key, self._app._current_theme)
        result = colorchooser.askcolor(color=current, title=f"Editar {key}", parent=self)
        if result and result[1]:
            hex_val = result[1].upper()
            self._apply_color(key, hex_val)

    def _apply_color(self, key: str, hex_val: str) -> None:
        """Persist colour, update dialog swatches, and live-apply to main UI."""
        _TM.set_color(key, hex_val, self._app._current_theme)
        # Update dialog widgets immediately
        if key in self._swatch_widgets:
            self._swatch_widgets[key].configure(fg_color=hex_val)
        if key in self._hex_labels:
            self._hex_labels[key].configure(text=hex_val.upper())
        # Update copy button command to use new value
        if key in self._copy_btns:
            btn = self._copy_btns[key]
            btn.configure(command=lambda v=hex_val, b=btn: self._copy_hex(v, b))
        # Live-apply to main window
        self._app._apply_theme_color_change(caller=self)

    def _copy_hex(self, value: str, btn: ctk.CTkButton | None = None) -> None:
        """Copy hex value to clipboard and briefly flash the button."""
        try:
            self.clipboard_clear()
            self.clipboard_append(value)
        except Exception:
            pass
        if btn:
            btn.configure(text="?", fg_color=C_SUCCESS, text_color="#ffffff")
            self.after(1200, lambda: btn.configure(text="?", fg_color="transparent",
                                                   text_color=C_TEXT_DIM))

    def _toggle_mode(self) -> None:
        """Switch between Dark/Light within the dialog and rebuild main UI."""
        new_mode = "Light" if self._app._current_theme == "Dark" else "Dark"
        self._app._current_theme = new_mode
        self._app.settings.update({"theme": new_mode})
        _TM.set_current_mode(new_mode)
        self._app._apply_theme_color_change(caller=self)
        # Update own badge
        _c = C_ACCENT if new_mode == "Dark" else C_ACCENT_SLIDE
        self._mode_badge.configure(border_color=_c)
        self._mode_lbl.configure(text=f"? {new_mode}", text_color=_c)
        # Rebuild color list for new mode
        for w in self._scroll.winfo_children():
            w.destroy()
        self._swatch_widgets.clear()
        self._hex_labels.clear()
        self._row_frames.clear()
        self._copy_btns.clear()
        self._build_color_list()

    def _reset(self) -> None:
        """Restore all colours to theme_default.json values."""
        if not messagebox.askyesno(
            "Restablecer tema",
            "¿Restaurar todos los colores al tema por defecto?\n"
            "Esta acción sobreescribirá tus colores personalizados.",
            parent=self,
        ):
            return
        _TM.reset()
        # Rebuild dialog color list
        for w in self._scroll.winfo_children():
            w.destroy()
        self._swatch_widgets.clear()
        self._hex_labels.clear()
        self._row_frames.clear()
        self._copy_btns.clear()
        self._build_color_list()
        # Apply to main window
        self._app._apply_theme_color_change(caller=self)

    def _on_search(self, *_) -> None:
        """Show/hide rows based on the search query."""
        query = self._search_var.get().lower().strip()
        for key, row_f in self._row_frames.items():
            label = self._KEY_LABELS.get(key, "").lower()
            visible = not query or query in key.lower() or query in label
            if visible:
                row_f.grid()
            else:
                row_f.grid_remove()


class PresetsDialog(ctk.CTkToplevel):
    """Ventana global de gestión de presets (accesible desde cualquier modo)."""

    def __init__(self, app: "AudioToVideoApp") -> None:
        super().__init__(app)
        self._app = app
        self.title("Gestionar Presets")
        self.resizable(True, True)
        self.minsize(560, 420)
        self.geometry("700x520")
        self.configure(fg_color=C_BG)
        self._build()
        # Expose tiles frame to app so _rebuild_preset_tiles populates this dialog
        app._preset_tiles_frame = self._tiles_frame
        app._rebuild_preset_tiles()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.grab_set()
        self.after(60, self._center)

    def _center(self) -> None:
        _center_window_on_screen(self)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # -- Header --------------------------------------------------
        hdr = ctk.CTkFrame(self, fg_color=C_CARD, corner_radius=0, height=46)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        ctk.CTkLabel(
            hdr, text=FA_SLIDERS,
            font=ctk.CTkFont(family=_FA_FAMILY, size=14),
            text_color=C_ACCENT,
        ).pack(side="left", padx=(14, 6), pady=8)
        ctk.CTkLabel(
            hdr, text="Presets",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=C_TEXT,
        ).pack(side="left", pady=8)
        ctk.CTkLabel(
            hdr, text="Clic en un preset para aplicarlo",
            font=ctk.CTkFont(size=11), text_color=C_MUTED,
        ).pack(side="left", padx=(12, 0), pady=8)
        ctk.CTkFrame(hdr, height=1, fg_color=C_BORDER, corner_radius=0).pack(
            side="bottom", fill="x"
        )

        # -- Scrollable tiles area ------------------------------------
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(12, 4))
        scroll.grid_columnconfigure(0, weight=1)
        _init_scrollbar(scroll)

        self._tiles_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._tiles_frame.grid(row=0, column=0, sticky="ew")
        self._tiles_frame.grid_columnconfigure(0, weight=1)
        self._tiles_frame.grid_columnconfigure(1, weight=1)

        # -- Footer actions -------------------------------------------
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 14))
        footer.grid_columnconfigure(0, weight=1)
        footer.grid_columnconfigure(1, weight=1)

        _plus_frame = ctk.CTkFrame(footer, fg_color=C_BTN_SECONDARY, corner_radius=6)
        _plus_frame.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        _plus_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            _plus_frame, text=FA_PLUS, width=24,
            font=ctk.CTkFont(family=_FA_FAMILY, size=12), text_color=C_TEXT,
        ).grid(row=0, column=0, padx=(10, 0), pady=6)
        ctk.CTkButton(
            _plus_frame, text="Nuevo preset", height=30,
            fg_color="transparent", hover_color=C_HOVER,
            text_color=C_TEXT, corner_radius=6, anchor="w",
            font=ctk.CTkFont(size=12),
            command=self._app._create_new_preset,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 4), pady=2)

        _imp_frame = ctk.CTkFrame(footer, fg_color=C_BTN_SECONDARY, corner_radius=6)
        _imp_frame.grid(row=0, column=1, sticky="ew", padx=(4, 0))
        _imp_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            _imp_frame, text=FA_UPLOAD, width=24,
            font=ctk.CTkFont(family=_FA_FAMILY, size=12), text_color=C_TEXT,
        ).grid(row=0, column=0, padx=(10, 0), pady=6)
        ctk.CTkButton(
            _imp_frame, text="Importar", height=30,
            fg_color="transparent", hover_color=C_HOVER,
            text_color=C_TEXT, corner_radius=6, anchor="w",
            font=ctk.CTkFont(size=12),
            command=self._app._import_presets,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 4), pady=2)

    def _on_close(self) -> None:
        self._app._preset_tiles_frame = None
        self._app._presets_dialog = None
        self.grab_release()
        self.destroy()


class StartupDependencyDialog(ctk.CTkToplevel):
    """Modal simple para la preparación inicial de dependencias."""

    def __init__(self, parent: ctk.CTk) -> None:
        super().__init__(parent)
        self.title("Preparando CreatorFlow Studio")
        self.resizable(False, False)
        self.overrideredirect(True)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.configure(fg_color=C_CARD)

        self._progress_mode = "indeterminate"
        self._on_cancel = None
        self._var_title = tk.StringVar(value="Verificando dependencias...")
        self._var_detail = tk.StringVar(value="Preparando herramientas necesarias para iniciar.")

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text="Inicializacion del entorno",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=C_TEXT,
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 6))

        ctk.CTkLabel(
            self,
            textvariable=self._var_title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C_TEXT,
            anchor="w",
            justify="left",
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 4))

        ctk.CTkLabel(
            self,
            textvariable=self._var_detail,
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
            anchor="w",
            justify="left",
            wraplength=420,
        ).grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))

        self._progress = ctk.CTkProgressBar(
            self,
            width=420,
            progress_color=C_ACCENT,
            fg_color=C_INPUT,
            mode="indeterminate",
        )
        self._progress.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 18))
        self._progress.start()

        ctk.CTkLabel(
            self,
            text="No cierres la app durante esta instalacion.",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=C_WARN,
            anchor="w",
            justify="left",
        ).grid(row=4, column=0, sticky="ew", padx=18, pady=(0, 10))

        self._btn_cancel = ctk.CTkButton(
            self,
            text="Cancelar",
            height=30,
            fg_color=C_BTN_SECONDARY,
            hover_color=C_HOVER,
            text_color=C_TEXT,
            border_width=1,
            border_color=C_BORDER,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._handle_cancel,
        )
        self._btn_cancel.grid(row=5, column=0, sticky="e", padx=18, pady=(0, 14))

        self.geometry("460x225")
        self.after(60, self._center)

    def _center(self) -> None:
        _center_window_on_screen(self)

    def set_status(self, title: str, detail: str, progress: float | None = None) -> None:
        self._var_title.set(title)
        self._var_detail.set(detail)

        if progress is None:
            if self._progress_mode != "indeterminate":
                self._progress.stop()
                self._progress.configure(mode="indeterminate")
                self._progress.start()
                self._progress_mode = "indeterminate"
            return

        if self._progress_mode != "determinate":
            self._progress.stop()
            self._progress.configure(mode="determinate")
            self._progress_mode = "determinate"
        self._progress.set(max(0.0, min(progress, 100.0)) / 100.0)

    def set_cancel_handler(self, callback) -> None:
        self._on_cancel = callback

    def set_cancel_enabled(self, enabled: bool) -> None:
        self._btn_cancel.configure(state="normal" if enabled else "disabled")

    def _handle_cancel(self) -> None:
        if self._on_cancel:
            self._on_cancel()

    def close(self) -> None:
        self._progress.stop()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class BusyDialog(ctk.CTkToplevel):
    """Small modal used while a blocking task runs in the background."""

    def __init__(self, parent: ctk.CTk, title: str, headline: str, detail: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.configure(fg_color=C_CARD)

        self._var_headline = tk.StringVar(value=headline)
        self._var_detail = tk.StringVar(value=detail)

        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            textvariable=self._var_headline,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=C_TEXT,
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 6))

        ctk.CTkLabel(
            self,
            textvariable=self._var_detail,
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
            anchor="w",
            justify="left",
            wraplength=380,
        ).grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 12))

        self._progress = ctk.CTkProgressBar(
            self,
            width=380,
            progress_color=C_ACCENT_YT,
            fg_color=C_INPUT,
            mode="indeterminate",
        )
        self._progress.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        self._progress.start()

        self.geometry("420x130")
        self.after(60, self._center)

    def _center(self) -> None:
        _center_window_on_screen(self)

    def set_detail(self, headline: str, detail: str) -> None:
        self._var_headline.set(headline)
        self._var_detail.set(detail)

    def close(self) -> None:
        self._progress.stop()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class ThemedConfirmDialog(ctk.CTkToplevel):
    """Themed Yes/No modal that follows app colors and typography."""

    def __init__(self, parent: ctk.CTk, title: str, headline: str, detail: str) -> None:
        super().__init__(parent)
        self._result = False
        self._font_scale = float(getattr(parent, "_font_scale", 1.0) or 1.0)

        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_no)
        self.configure(fg_color=C_CARD)

        self.grid_columnconfigure(0, weight=1)

        width = max(580, min(760, int(640 * self._font_scale)))
        wraplength = width - 60
        chars_per_line = max(34, int(wraplength / max(7.0, 7.0 * self._font_scale)))

        wrapped_lines = 0
        for raw_line in detail.splitlines() or [detail]:
            line = raw_line if raw_line else " "
            wrapped_lines += max(1, (len(line) + chars_per_line - 1) // chars_per_line)
        wrapped_lines = max(4, min(wrapped_lines, 16))
        detail_height = int(18 * self._font_scale * wrapped_lines)
        window_height = 136 + detail_height

        ctk.CTkLabel(
            self,
            text=headline,
            font=ctk.CTkFont(size=max(16, int(18 * self._font_scale)), weight="bold"),
            text_color=C_TEXT,
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))

        ctk.CTkLabel(
            self,
            text=detail,
            font=ctk.CTkFont(size=max(12, int(14 * self._font_scale))),
            text_color=C_TEXT_DIM,
            anchor="w",
            justify="left",
            wraplength=wraplength,
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 18))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            buttons,
            text="No",
            height=34,
            fg_color=C_BTN_SECONDARY,
            hover_color=C_HOVER,
            text_color=C_TEXT,
            border_width=1,
            border_color=C_BORDER,
            font=ctk.CTkFont(size=max(12, int(13 * self._font_scale)), weight="bold"),
            command=self._on_no,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            buttons,
            text="Si, continuar",
            height=34,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_H,
            text_color=C_BTN_PRIMARY_TEXT,
            font=ctk.CTkFont(size=max(12, int(13 * self._font_scale)), weight="bold"),
            command=self._on_yes,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self.geometry(f"{width}x{window_height}")
        self.after(60, self._center)

    def _center(self) -> None:
        _center_window_on_screen(self)

    def _on_yes(self) -> None:
        self._result = True
        self._close()

    def _on_no(self) -> None:
        self._result = False
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def run_modal(self) -> bool:
        self.wait_window()
        return self._result


class ModelSelectionDialog(ctk.CTkToplevel):
    """Modal para seleccionar modelos de Ollama a instalar con peso estimado."""

    def __init__(
        self,
        parent: ctk.CTk,
        *,
        title: str,
        missing_models: list[str],
        estimate_cb,
    ) -> None:
        super().__init__(parent)
        self._result: list[str] = []
        self._estimate_cb = estimate_cb
        self._font_scale = float(getattr(parent, "_font_scale", 1.0) or 1.0)

        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.configure(fg_color=C_CARD)

        self._catalog = [
            {
                "model": "llama3.1:8b",
                "label": "Llama 3.1 8B",
                "purpose": "Respuestas mas robustas y detalladas (modo Calidad alta).",
                "ram": "16 GB recomendados (minimo 12 GB)",
                "recommended": True,
                "alternative": False,
            },
            {
                "model": "llama3.2:3b",
                "label": "Llama 3.2 3B",
                "purpose": "Respuestas rapidas con buen balance calidad/rendimiento.",
                "ram": "8 GB recomendados (minimo 6 GB)",
                "recommended": True,
                "alternative": False,
            },
            {
                "model": "llama3.2:1b",
                "label": "Llama 3.2 1B (Ligero)",
                "purpose": "Opcion liviana: menor calidad, pero util para tareas simples.",
                "ram": "4 GB recomendados (minimo 3 GB)",
                "recommended": False,
                "alternative": True,
            },
        ]

        missing_set = {m.strip().lower() for m in missing_models if m.strip()}
        self._vars: dict[str, tk.BooleanVar] = {}
        for item in self._catalog:
            model = item["model"]
            # Preseleccionar recomendaciones faltantes; la ligera queda opcional.
            default_checked = (model.lower() in missing_set) and (not item["alternative"])
            self._vars[model] = tk.BooleanVar(value=default_checked)

        self.grid_columnconfigure(0, weight=1)
        width = max(680, min(820, int(740 * self._font_scale)))

        ctk.CTkLabel(
            self,
            text="Selecciona los modelos a instalar",
            font=ctk.CTkFont(size=max(16, int(18 * self._font_scale)), weight="bold"),
            text_color=C_TEXT,
            anchor="w",
            justify="left",
        ).grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 6))

        ctk.CTkLabel(
            self,
            text=(
                "Recomendado: instalar Llama 3.1 8B + Llama 3.2 3B. "
                "La opcion 1B es alternativa ligera para equipos con menos recursos."
            ),
            font=ctk.CTkFont(size=max(12, int(13 * self._font_scale))),
            text_color=C_TEXT_DIM,
            anchor="w",
            justify="left",
            wraplength=width - 70,
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))

        options = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=8)
        options.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 10))
        options.grid_columnconfigure(0, weight=1)

        row = 0
        for item in self._catalog:
            model = item["model"]
            tag = "Recomendado" if item["recommended"] else "Alternativa ligera"
            tag_color = C_SUCCESS if item["recommended"] else C_WARN

            line = ctk.CTkFrame(options, fg_color="transparent")
            line.grid(row=row, column=0, sticky="ew", padx=12, pady=(10 if row == 0 else 2, 4))
            line.grid_columnconfigure(0, weight=1)

            ctk.CTkCheckBox(
                line,
                text=f"{item['label']}  ({model})",
                variable=self._vars[model],
                font=ctk.CTkFont(size=max(12, int(13 * self._font_scale)), weight="bold"),
                text_color=C_TEXT,
                command=self._refresh_estimate,
            ).grid(row=0, column=0, sticky="w")

            ctk.CTkLabel(
                line,
                text=tag,
                font=ctk.CTkFont(size=max(11, int(11 * self._font_scale)), weight="bold"),
                text_color=tag_color,
                anchor="e",
                justify="right",
            ).grid(row=0, column=1, sticky="e", padx=(8, 0))

            ctk.CTkLabel(
                options,
                text=f"{item['purpose']}\nRAM recomendada: {item['ram']}",
                font=ctk.CTkFont(size=max(11, int(12 * self._font_scale))),
                text_color=C_MUTED,
                anchor="w",
                justify="left",
                wraplength=width - 110,
            ).grid(row=row + 1, column=0, sticky="ew", padx=16, pady=(0, 6))

            row += 2

        self._var_estimate = tk.StringVar(value="")
        ctk.CTkLabel(
            self,
            textvariable=self._var_estimate,
            font=ctk.CTkFont(size=max(12, int(13 * self._font_scale)), weight="bold"),
            text_color=C_ACCENT,
            anchor="w",
            justify="left",
        ).grid(row=3, column=0, sticky="ew", padx=20, pady=(0, 10))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=4, column=0, sticky="ew", padx=20, pady=(0, 18))
        buttons.grid_columnconfigure(0, weight=1)
        buttons.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            buttons,
            text="Cancelar",
            height=34,
            fg_color=C_BTN_SECONDARY,
            hover_color=C_HOVER,
            text_color=C_TEXT,
            border_width=1,
            border_color=C_BORDER,
            font=ctk.CTkFont(size=max(12, int(13 * self._font_scale)), weight="bold"),
            command=self._on_cancel,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        ctk.CTkButton(
            buttons,
            text="Instalar seleccion",
            height=34,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_H,
            text_color=C_BTN_PRIMARY_TEXT,
            font=ctk.CTkFont(size=max(12, int(13 * self._font_scale)), weight="bold"),
            command=self._on_confirm,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

        self._refresh_estimate()
        self.geometry(f"{width}x520")
        self.after(60, self._center)

    def _center(self) -> None:
        _center_window_on_screen(self)

    def _selected_models(self) -> list[str]:
        out: list[str] = []
        for item in self._catalog:
            model = item["model"]
            if self._vars[model].get():
                out.append(model)
        return out

    def _refresh_estimate(self) -> None:
        selected = self._selected_models()
        if not selected:
            self._var_estimate.set("Peso estimado: 0 GB (sin seleccion)")
            return
        total = float(self._estimate_cb(selected))
        self._var_estimate.set(f"Peso estimado segun seleccion: {total:.1f} GB")

    def _on_confirm(self) -> None:
        self._result = self._selected_models()
        self._close()

    def _on_cancel(self) -> None:
        self._result = []
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()

    def run_modal(self) -> list[str]:
        self.wait_window()
        return list(self._result)


class AudioToVideoApp(ctk.CTk):
    """Ventana principal de la aplicación."""

    WINDOW_TITLE = "CreatorFlow Studio"
    WINDOW_SIZE = "1280x800"
    MIN_SIZE = (1100, 700)
    SCROLL_SPEED = 3.75   # Multiplicador de velocidad del scroll con rueda del ratón
    YT_CHANNEL_CACHE_TTL_MINUTES = 30
    YT_DRAFTS_CACHE_TTL_MINUTES = 20
    YT_PLAYLISTS_CACHE_TTL_MINUTES = 240

    def __init__(self) -> None:
        # Desactivar manipulación de título antes de que CTk la aplique
        self._deactivate_windows_window_header_manipulation = True
        super().__init__()

        self.settings = SettingsManager()
        self._prompt_lab = PromptLabManager()
        self._prompt_backend = PromptLabBackend()
        self._runner: Runner | None = None
        self._image_assignment: dict[str, Path] = {}
        self._used_names: set[str] = set()
        self._last_run_names: list[str] = []
        self._current_mode: str = "Audio ? Video"
        self._slideshow_runner: SlideshowRunner | None = None
        self._shorts_runner: ShortsRunner | None = None
        self._sho_image_paths: list[Path] = []
        self._sho_used_names: set[str] = set()
        self._sho_last_run_names: list[str] = []
        self._yt_video_rows: list[dict[str, str]] = []  # filled when drafts are fetched
        self._yt_auth_service: YouTubeAuthService | None = None
        self._yt_auth_dialog: BusyDialog | None = None
        self._yt_auth_in_progress = False
        self._yt_cached_channel_title = ""
        self._yt_cached_channel_id = ""
        self._yt_cached_channel_fetched_at = ""
        self._yt_cached_drafts_fetched_at = ""
        self._yt_cached_playlists: list[dict[str, str]] = []
        self._yt_cached_playlists_fetched_at = ""
        self._yt_activate_subtab = None
        self._yt_sync_in_progress = False
        self._yt_sync_modal = None
        self._yt_sync_progress = None
        self._yt_sync_status_var = None
        self._yt_sync_summary_var = None
        self._yt_sync_close_btn = None
        self._yt_sync_total = 0
        self._var_pl_workspace = tk.StringVar(value=self.settings.get("pl_workspace", "General"))
        self._var_pl_category = tk.StringVar(value=self.settings.get("pl_category", "General"))
        self._var_pl_skill = tk.StringVar(value=self.settings.get("pl_skill", "Skill General"))
        self._var_pl_model_mode = tk.StringVar(value=self.settings.get("pl_model_mode", "Calidad alta"))
        self._var_pl_backend_url = tk.StringVar(value=self.settings.get("pl_backend_url", "http://127.0.0.1:11434"))
        self._var_pl_model_quality = tk.StringVar(value=self.settings.get("pl_model_quality", "llama3.1:8b"))
        self._var_pl_model_fast = tk.StringVar(value=self.settings.get("pl_model_fast", "llama3.2:3b"))
        self._var_pl_model_quality_display = tk.StringVar(value=self._var_pl_model_quality.get())
        self._var_pl_model_fast_display = tk.StringVar(value=self._var_pl_model_fast.get())
        self._pl_quality_display_to_raw: dict[str, str] = {}
        self._pl_fast_display_to_raw: dict[str, str] = {}
        raw_active_skills = self.settings.get("pl_active_skills", [])
        self._pl_active_skills: list[dict[str, str]] = []
        if isinstance(raw_active_skills, list):
            for item in raw_active_skills:
                if not isinstance(item, dict):
                    continue
                cat = str(item.get("category", "")).strip()
                sk = str(item.get("skill", "")).strip()
                if cat and sk:
                    self._pl_active_skills.append({"category": cat, "skill": sk})
        self._pl_last_ws_for_preload = self._var_pl_workspace.get().strip() or "General"
        self._pl_last_category_for_preload = self._var_pl_category.get().strip() or "General"
        self._pl_generation_in_progress = False
        self._pl_prompt_template_current = ""
        self._pl_last_inserted_template = ""
        raw_insert_mode_by_category = self.settings.get("pl_template_insert_mode_by_category", {})
        self._pl_template_insert_mode_by_category: dict[str, str] = (
            dict(raw_insert_mode_by_category)
            if isinstance(raw_insert_mode_by_category, dict)
            else {}
        )
        self._presets_dialog: PresetsDialog | None = None
        self._preset_tiles_frame: ctk.CTkFrame | None = None
        self._startup_dependency_dialog: StartupDependencyDialog | None = None
        self._startup_last_status_message = ""
        self._startup_cancel_requested = threading.Event()
        self._validation_in_progress = False
        self._log_queue: list[str] = []
        self._log_lock = threading.Lock()

        # Tema y escala de fuente (se inicializan antes de construir la UI)
        saved_theme = self.settings.get("theme", "Dark")
        saved_font = self.settings.get("font_size", "Medium")
        self._current_theme: str = saved_theme
        self._font_scale: float = _FONT_SIZE_SCALE.get(saved_font, 1.0)
        _apply_theme(saved_theme)
        ctk.set_appearance_mode(saved_theme)

        self._setup_window()
        # Load slider ranges from config
        self._slider_ranges: dict = {}
        _ranges_path = _BUNDLE_DIR / "config" / "slider_ranges.json"
        if _ranges_path.exists():
            try:
                self._slider_ranges = json.loads(_ranges_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        # Section toggle callbacks (for collapsing all on startup)
        self._section_toggles: list = []
        self._build_ui()
        # Collapse all sections after UI is fully built
        self.after_idle(self._collapse_all_sections)
        self._load_settings_to_ui()

        # Silenciar errores de widgets destruidos en callbacks pendientes (CTk interno)
        self.report_callback_exception = self._handle_callback_exception

        # Validar entorno al iniciar
        self.after(200, self._run_validation)
        # Procesar cola de logs periódicamente
        self.after(100, self._flush_log_queue)

    # ------------------------------------------------------------------
    # VENTANA
    # ------------------------------------------------------------------

    def _setup_window(self) -> None:
        self.title(self.WINDOW_TITLE)
        self.geometry(self.WINDOW_SIZE)
        self.minsize(*self.MIN_SIZE)
        try:
            self.state("zoomed")
        except tk.TclError:
            # Some legacy Windows setups can reject this state; keep normal window.
            pass
        self.configure(fg_color=C_BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Icono de la ventana (title bar + taskbar)
        ico = _BUNDLE_DIR / "logoAtV.ico"
        if ico.is_file():
            self.after(10, lambda: self.iconbitmap(str(ico)))

    # ------------------------------------------------------------------
    # BUILD UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._section_toggles = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_main_area()
        # Thin separator between main and footer
        ctk.CTkFrame(self, height=2, fg_color=C_BORDER, corner_radius=0).grid(
            row=2, column=0, sticky="ew"
        )
        self._build_footer()
        self._setup_fast_scroll()

    def _setup_fast_scroll(self) -> None:
        """Override CTkScrollableFrame's mouse-wheel handler using SCROLL_SPEED multiplier."""
        import platform
        _os = platform.system()
        spd = self.SCROLL_SPEED

        def _fast_wheel(event: "tk.Event") -> None:  # type: ignore[name-defined]
            widget = event.widget
            # Walk up to find the canvas that belongs to a CTkScrollableFrame
            while widget:
                try:
                    canvas = widget._parent_canvas  # type: ignore[attr-defined]
                    if _os == "Windows":
                        canvas.yview_scroll(int(-event.delta / (120 // spd)), "units")
                    elif _os == "Darwin":
                        canvas.yview_scroll(int(-event.delta * spd), "units")
                    else:
                        if event.num == 4:
                            canvas.yview_scroll(-spd, "units")
                        elif event.num == 5:
                            canvas.yview_scroll(spd, "units")
                    return  # handled
                except AttributeError:
                    pass
                try:
                    widget = widget.master
                except AttributeError:
                    break

        if _os == "Linux":
            self.bind_all("<Button-4>", _fast_wheel, add="+")
            self.bind_all("<Button-5>", _fast_wheel, add="+")
        else:
            self.bind_all("<MouseWheel>", _fast_wheel, add="+")

    # --- Header -------------------------------------------------------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0, height=48)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=0)   # accent bar
        header.grid_columnconfigure(1, weight=0)   # title
        header.grid_columnconfigure(2, weight=0)   # mode buttons
        header.grid_columnconfigure(3, weight=1)   # spacer
        header.grid_columnconfigure(4, weight=0)   # status badge
        header.grid_columnconfigure(5, weight=0)   # ctrl (theme + font)
        header.grid_rowconfigure(0, weight=1)
        header.grid_rowconfigure(1, weight=0)      # separator

        # -- Barra de acento vertical izquierda --
        ctk.CTkFrame(header, width=3, fg_color=C_ACCENT, corner_radius=1).grid(
            row=0, column=0, padx=(14, 0), pady=8, sticky="ns"
        )

        # -- Título --
        _title_frame = ctk.CTkFrame(header, fg_color="transparent")
        _title_frame.grid(row=0, column=1, padx=(8, 0), sticky="w")
        ctk.CTkLabel(
            _title_frame, text=FA_FILM,
            font=ctk.CTkFont(family=_FA_FAMILY, size=16),
            text_color=C_TEXT,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            _title_frame,
            text="CreatorFlow Studio",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=C_TEXT,
        ).pack(side="left")

        # -- Botones de modo: ATV y SLIDE ----------------------------
        mode_grp = ctk.CTkFrame(
            header, fg_color=C_CARD, corner_radius=8,
            border_width=1, border_color=C_BORDER,
        )
        mode_grp.grid(row=0, column=2, padx=(24, 0))

        def _create_mode_btn(icon, acronym, is_active, accent, cmd, prefix):
            btn_w = 126
            # Outer wrapper: fixed 110×42px, placed children for precise layout
            wrap = ctk.CTkFrame(mode_grp, fg_color="transparent",
                                corner_radius=0, width=btn_w, height=42)
            wrap.pack(side="left", padx=3, pady=(4, 0))
            wrap.pack_propagate(False)

            bg  = C_INPUT if is_active else "transparent"
            txt = C_TEXT  if is_active else C_TEXT_DIM
            ind = accent  if is_active else "transparent"

            # Content area (40px tall) — fills wrap, bar sits beneath it
            inner = ctk.CTkFrame(wrap, fg_color=bg, corner_radius=6,
                                 cursor="hand2", width=btn_w, height=40)
            inner.pack(fill="x")
            inner.pack_propagate(False)

            # Icon + text row — centered inside inner
            row = ctk.CTkFrame(inner, fg_color="transparent")
            row.place(relx=0.5, rely=0.5, anchor="center")
            icon_lbl = ctk.CTkLabel(
                row, text=icon, width=18,
                font=ctk.CTkFont(family=_FA_FAMILY, size=12), text_color=txt)
            icon_lbl.pack(side="left", padx=(0, 4))
            text_lbl = ctk.CTkLabel(
                row, text=acronym,
                font=ctk.CTkFont(size=12, weight="bold"), text_color=txt)
            text_lbl.pack(side="left")

            # Bottom accent bar (2px)
            bar = ctk.CTkFrame(wrap, height=2, fg_color=ind, corner_radius=0)
            bar.pack(fill="x")

            setattr(self, f"_frame_mode_{prefix}",    inner)
            setattr(self, f"_lbl_mode_{prefix}_icon", icon_lbl)
            setattr(self, f"_lbl_mode_{prefix}_text", text_lbl)
            setattr(self, f"_bar_mode_{prefix}",      bar)
            setattr(self, f"_mode_{prefix}_base",     bg)
            setattr(self, f"_mode_{prefix}_accent",   accent)

            _lbls = (icon_lbl, text_lbl)

            def _on_enter(e, _inner=inner, _bar=bar, _prefix=prefix):
                if getattr(self, f"_mode_{prefix}_base") != "transparent":
                    return  # already active, skip hover
                _inner.configure(fg_color=C_HOVER)
                _bar.configure(fg_color=C_BORDER)
                for lbl in _lbls:
                    lbl.configure(text_color=C_TEXT)

            def _on_leave(e, _inner=inner, _bar=bar, _prefix=prefix):
                def _check():
                    try:
                        mx, my = _inner.winfo_pointerxy()
                        w = _inner.winfo_containing(mx, my)
                        if w and (str(w) == str(_inner) or str(w).startswith(str(_inner) + ".")):
                            return
                    except Exception:
                        pass
                    if getattr(self, f"_mode_{prefix}_base") != "transparent":
                        return  # already active when leave fires
                    _inner.configure(fg_color="transparent")
                    _bar.configure(fg_color="transparent")
                    for lbl in _lbls:
                        lbl.configure(text_color=C_TEXT_DIM)
                _inner.after(30, _check)

            for w in (inner, row, icon_lbl, text_lbl):
                w.bind("<Enter>",    _on_enter, add="+")
                w.bind("<Leave>",    _on_leave, add="+")
                w.bind("<Button-1>", lambda e, c=cmd: c(), add="+")

        _atv_active = self._current_mode == "Audio \u2192 Video"
        _create_mode_btn(FA_FILM, "ATV", _atv_active, C_ACCENT,
                         lambda: self._switch_mode("Audio \u2192 Video"), "atv")
        _create_mode_btn(FA_IMAGES, "SLIDESHOW", self._current_mode == "Slideshow",
                         C_ACCENT_SLIDE, lambda: self._switch_mode("Slideshow"), "slide")
        _create_mode_btn(FA_SHORTS, "SHORTS", self._current_mode == "Shorts",
                         C_ACCENT_SHORTS, lambda: self._switch_mode("Shorts"), "shorts")
        _create_mode_btn(FA_YT, "YOUTUBE", self._current_mode == "YouTube Publisher",
                         C_ACCENT_YT, lambda: self._switch_mode("YouTube Publisher"), "yt")
        _create_mode_btn(FA_WAND, "PROMPT LAB", self._current_mode == "Prompt Lab",
                 C_ACCENT_LAB, lambda: self._switch_mode("Prompt Lab"), "pl")


        # -- Badge de estado del entorno ------------------------------
        self._status_badge = ctk.CTkFrame(
            header, fg_color=C_CARD, corner_radius=20,
            border_width=1, border_color=C_BORDER,
        )
        self._status_badge.grid(row=0, column=4, padx=(8, 4))
        self._lbl_status_dot = ctk.CTkLabel(
            self._status_badge, text="?",
            font=ctk.CTkFont(size=9),
            text_color=C_WARN,
        )
        self._lbl_status_dot.pack(side="left", padx=(8, 2), pady=6)
        self._lbl_status = ctk.CTkLabel(
            self._status_badge,
            text="Verificando entorno...",
            font=ctk.CTkFont(size=11),
            text_color=C_TEXT_DIM,
        )
        self._lbl_status.pack(side="left", padx=(0, 10), pady=6)

        # -- Controles (tema + tamaño de fuente) ---------------------
        ctrl = ctk.CTkFrame(
            header, fg_color=C_CARD, corner_radius=6,
            border_width=1, border_color=C_BORDER,
        )
        ctrl.grid(row=0, column=5, padx=(4, 14))

        # -- Presets button ----------------------------------------
        ctk.CTkButton(
            ctrl, text=FA_SLIDERS, width=30, height=26,
            fg_color="transparent", hover_color=C_HOVER,
            text_color=C_TEXT_DIM,
            font=ctk.CTkFont(family=_FA_FAMILY, size=13),
            corner_radius=4,
            command=self._open_presets_dialog,
        ).pack(side="left", padx=(4, 0), pady=4)
        ctk.CTkFrame(ctrl, width=1, height=18, fg_color=C_BORDER).pack(
            side="left", padx=5, pady=4
        )

        _theme_icon = FA_SUN if self._current_theme == "Dark" else FA_MOON
        self._btn_theme = ctk.CTkButton(
            ctrl, text=_theme_icon, width=30, height=26,
            fg_color="transparent", hover_color=C_HOVER,
            text_color=C_TEXT,
            font=ctk.CTkFont(family=_FA_FAMILY, size=14),
            corner_radius=4,
            command=self._toggle_theme,
        )
        self._btn_theme.pack(side="left", padx=(4, 0), pady=4)

        ctk.CTkFrame(ctrl, width=1, height=18, fg_color=C_BORDER).pack(
            side="left", padx=5, pady=4
        )

        self._font_btns: dict[str, ctk.CTkButton] = {}
        for _label, _size in (("A?", "Small"), ("A", "Medium"), ("A?", "Large")):
            _active = (self._font_scale == _FONT_SIZE_SCALE[_size])
            btn = ctk.CTkButton(
                ctrl, text=_label,
                width=30, height=26,
                fg_color=C_ACCENT if _active else "transparent",
                hover_color=C_HOVER,
                text_color=C_TEXT if _active else C_TEXT_DIM,
                border_width=0,
                font=ctk.CTkFont(
                    size=12 if _label == "A" else (10 if _label == "A?" else 14)
                ),
                corner_radius=4,
                command=lambda s=_size: self._on_font_size(s),
            )
            btn.pack(side="left", padx=2, pady=4)
            self._font_btns[_size] = btn

        # -- Divisor + Botón de configuración de tema -----------------
        ctk.CTkFrame(ctrl, width=1, height=18, fg_color=C_BORDER).pack(
            side="left", padx=5, pady=4
        )
        ctk.CTkButton(
            ctrl, text=FA_GEAR, width=30, height=26,
            fg_color="transparent", hover_color=C_HOVER,
            text_color=C_TEXT_DIM,
            font=ctk.CTkFont(family=_FA_FAMILY, size=13),
            corner_radius=4,
            command=self._open_theme_settings,
        ).pack(side="left", padx=(0, 4), pady=4)

        # -- Separador inferior del header ----------------------------
        ctk.CTkFrame(header, height=1, fg_color=C_BORDER, corner_radius=0).grid(
            row=1, column=0, columnspan=6, sticky="ew"
        )

    # --- Main area ----------------------------------------------------

    def _build_main_area(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=16, pady=16)
        main.grid_columnconfigure(0, weight=3, minsize=380)  # 60%
        main.grid_columnconfigure(1, weight=2, minsize=300)  # 40%
        main.grid_rowconfigure(0, weight=1)  # panels
        self._main_panel = main

        self._build_left_panel(main)
        self._build_right_panel(main)
        self._build_slideshow_left_panel(main)
        self._build_shorts_left_panel(main)
        self._build_youtube_left_panel(main)
        self._build_prompt_lab_left_panel(main)

    # --- Left panel ---------------------------------------------------

    def _build_left_panel(self, parent: ctk.CTkFrame) -> None:
        panel, _tabs = self._make_tab_panel(
            parent,
            [("Archivos", "archivos"), ("Visual", "visual"), ("Salida", "salida")],
            accent=C_ACCENT,
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self._scroll_frame = panel

        tab_archivos = _tabs["archivos"]
        tab_visual   = _tabs["visual"]
        tab_salida   = _tabs["salida"]

        # --------------------------------------------------------------
        # TAB: ARCHIVOS
        # --------------------------------------------------------------
        af = ctk.CTkScrollableFrame(tab_archivos, fg_color="transparent")
        af.pack(fill="both", expand=True, padx=16, pady=(8, 12))
        af.grid_columnconfigure(0, weight=1)
        _init_scrollbar(af)

        _card_dir = ctk.CTkFrame(af, fg_color=C_CARD, corner_radius=10,
                                 border_width=1, border_color=C_BORDER)
        _card_dir.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        _card_dir.grid_columnconfigure(0, weight=1)
        self._section_header(_card_dir, "Configuración de directorios").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _dir_inner = ctk.CTkFrame(_card_dir, fg_color="transparent")
        _dir_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _dir_inner.grid_columnconfigure(0, weight=1)
        ar = 0

        self._var_audio_folder = tk.StringVar()
        ar = self._file_row(_dir_inner, "Carpeta de audios:", self._var_audio_folder,
                            self._browse_audio_folder, ar)

        # Single-image wrapper
        self._single_image_wrapper = ctk.CTkFrame(_dir_inner, fg_color="transparent")
        self._single_image_wrapper.grid(row=ar, column=0, sticky="ew")
        self._single_image_wrapper.grid_columnconfigure(0, weight=1)
        self._var_image = tk.StringVar()
        self._file_row(self._single_image_wrapper, "Imagen de fondo:", self._var_image,
                       self._browse_image, 0)
        ar += 1

        self._var_multi_image = tk.BooleanVar(value=False)
        ar = self._check_row(_dir_inner, "Múltiples imágenes de fondo", self._var_multi_image,
                             ar, command=self._toggle_multi_image)

        self._multi_image_wrapper = ctk.CTkFrame(_dir_inner, fg_color="transparent")
        self._multi_image_wrapper.grid(row=ar, column=0, sticky="ew")
        self._multi_image_wrapper.grid_columnconfigure(0, weight=1)
        self._var_images_folder = tk.StringVar()
        self._file_row(self._multi_image_wrapper, "Carpeta de imágenes:", self._var_images_folder,
                       self._browse_images_folder, 0)
        self._btn_assign_images = ctk.CTkButton(
            self._multi_image_wrapper,
            text="Ver / editar asignación  \u25b6",
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, height=40,
            font=ctk.CTkFont(size=self._fs(11)),
            command=self._open_image_assignment,
        )
        self._btn_assign_images.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        _apply_sec_hover(self._btn_assign_images)
        self._multi_image_wrapper.grid_remove()
        ar += 1

        self._var_output = tk.StringVar()
        ar = self._file_row(_dir_inner, "Carpeta de salida:", self._var_output,
                            self._browse_output, ar)

        _btn_reload = ctk.CTkButton(
            _dir_inner, text="\u21bb  RECARGAR CARPETAS",
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, height=40,
            font=ctk.CTkFont(size=self._fs(11)),
            command=self._reload_folders,
        )
        _btn_reload.grid(row=ar, column=0, sticky="ew", padx=12, pady=10)
        _apply_sec_hover(_btn_reload)

        # --------------------------------------------------------------
        # TAB: VISUAL
        # --------------------------------------------------------------
        vf = ctk.CTkScrollableFrame(tab_visual, fg_color="transparent")
        vf.pack(fill="both", expand=True, padx=16, pady=(8, 12))
        vf.grid_columnconfigure(0, weight=1)
        _init_scrollbar(vf)
        vr = 0

        # --- Resolución ---
        _sec_res = ctk.CTkFrame(vf, fg_color=C_CARD, corner_radius=10,
                                border_width=1, border_color=C_BORDER)
        _sec_res.grid(row=vr, column=0, sticky="ew", padx=0, pady=(0, 16))
        self._section_header(_sec_res, "Resolución").pack(fill="x")
        self._var_resolution = tk.StringVar(value="1080p")
        _res_inner = ctk.CTkFrame(_sec_res, fg_color="transparent")
        _res_inner.pack(fill="x", padx=16, pady=(16, 20))
        for _rv in ("720p", "1080p", "4K"):
            ctk.CTkRadioButton(_res_inner, text=_rv, variable=self._var_resolution,
                               value=_rv, font=ctk.CTkFont(size=self._fs(11))
                               ).pack(side="left", padx=8)
        vr += 1

        # --- Parámetros ---
        _sec_par = ctk.CTkFrame(vf, fg_color=C_CARD, corner_radius=10,
                                border_width=1, border_color=C_BORDER)
        _sec_par.grid(row=vr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_par.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_par, "Parámetros").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _par_inner = ctk.CTkFrame(_sec_par, fg_color="transparent")
        _par_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _par_inner.grid_columnconfigure(0, weight=1)
        self._var_fade_in = tk.DoubleVar(value=2.0)
        pr = self._slider_row(_par_inner, "Fade in (s):", self._var_fade_in, 0, 5, 0, fmt="{:.1f}")
        self._var_fade_out = tk.DoubleVar(value=2.0)
        pr = self._slider_row(_par_inner, "Fade out (s):", self._var_fade_out, 0, 5, pr, fmt="{:.1f}")
        self._var_crf = tk.IntVar(value=18)
        pr = self._slider_row(
            _par_inner, "Calidad CRF:", self._var_crf, 0, 51, pr, fmt="{:.0f}", pct=True,
            tooltip_text=(
                "CRF (Constant Rate Factor) — controla la calidad del video.\n\n"
                "• 0  ? Lossless (sin pérdida). Archivo enorme.\n"
                "• 18 ? Alta calidad (recomendado). Buen balance.\n"
                "• 23 ? Calidad media. Archivo más liviano.\n"
                "• 28 ? Baja calidad. Solo para pruebas.\n"
                "• 51 ? La peor calidad posible.\n\n"
                "Menor número = mejor imagen, archivo más grande."
            ),
        )
        vr += 1

        # --- Efectos ---
        _sec_fx = ctk.CTkFrame(vf, fg_color=C_CARD, corner_radius=10,
                               border_width=1, border_color=C_BORDER)
        _sec_fx.grid(row=vr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_fx.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_fx, "Efectos visuales").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _fx_inner = ctk.CTkFrame(_sec_fx, fg_color="transparent")
        _fx_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _fx_inner.grid_columnconfigure(0, weight=1)

        self._var_breath = tk.BooleanVar(value=False)
        self._var_light_zoom = tk.BooleanVar(value=False)
        self._var_vignette = tk.BooleanVar(value=False)
        self._var_color_shift = tk.BooleanVar(value=False)
        self._var_glitch = tk.BooleanVar(value=False)
        self._var_overlay = tk.BooleanVar(value=False)
        self._var_normalize = tk.BooleanVar(value=False)
        fr = 0

        # -- Fade respiración --
        fr = self._check_row(_fx_inner, "Fade respiración (brillo)", self._var_breath, fr)
        self._breath_settings_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._breath_settings_frame.grid(row=fr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._breath_settings_frame.grid_columnconfigure(0, weight=1)
        self._var_breath_intensity = tk.DoubleVar(value=0.04)
        self._var_breath_speed = tk.DoubleVar(value=1.0)
        br = 0
        br = self._slider_row(self._breath_settings_frame, "Intensidad:",
                               self._var_breath_intensity, 0.01, 0.08, br, fmt="{:.3f}", number_of_steps=70, pct=True)
        br = self._slider_row(self._breath_settings_frame, "Velocidad:",
                               self._var_breath_speed, 0.1, 2.0, br, fmt="{:.1f}", number_of_steps=19, pct=True)
        self._breath_settings_frame.grid_remove()
        self._var_breath.trace_add("write", lambda *_: (
            self._breath_settings_frame.grid() if self._var_breath.get()
            else self._breath_settings_frame.grid_remove()
        ))
        fr += 1

        # -- Zoom ligero --
        fr = self._check_row(_fx_inner, "Zoom ligero (crop)", self._var_light_zoom, fr)
        self._light_zoom_settings_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._light_zoom_settings_frame.grid(row=fr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._light_zoom_settings_frame.grid_columnconfigure(0, weight=1)
        self._var_light_zoom_max = tk.DoubleVar(value=1.04)
        self._var_light_zoom_speed = tk.DoubleVar(value=0.5)
        lzr = 0
        lzr = self._slider_row(self._light_zoom_settings_frame, "Zoom máx:",
                               self._var_light_zoom_max, 1.01, 1.08, lzr, fmt="{:.3f}", number_of_steps=70, pct=True)
        lzr = self._slider_row(self._light_zoom_settings_frame, "Velocidad:",
                               self._var_light_zoom_speed, 0.1, 1.5, lzr, fmt="{:.1f}", number_of_steps=14, pct=True)
        self._light_zoom_settings_frame.grid_remove()
        self._var_light_zoom.trace_add("write", lambda *_: (
            self._light_zoom_settings_frame.grid() if self._var_light_zoom.get()
            else self._light_zoom_settings_frame.grid_remove()
        ))
        fr += 1

        # -- Viñeta --
        fr = self._check_row(_fx_inner, "Viñeta (bordes)", self._var_vignette, fr)
        self._vignette_settings_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._vignette_settings_frame.grid(row=fr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._vignette_settings_frame.grid_columnconfigure(0, weight=1)
        self._var_vignette_intensity = tk.DoubleVar(value=0.4)
        vir = 0
        vir = self._slider_row(self._vignette_settings_frame, "Intensidad:",
                               self._var_vignette_intensity, 0.0, 1.0, vir, fmt="{:.1f}", number_of_steps=100, pct=True)
        self._vignette_settings_frame.grid_remove()
        self._var_vignette.trace_add("write", lambda *_: (
            self._vignette_settings_frame.grid() if self._var_vignette.get()
            else self._vignette_settings_frame.grid_remove()
        ))
        fr += 1

        # -- Color shift --
        fr = self._check_row(_fx_inner, "Color shift (hue)", self._var_color_shift, fr)
        self._color_shift_settings_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._color_shift_settings_frame.grid(row=fr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._color_shift_settings_frame.grid_columnconfigure(0, weight=1)
        self._var_color_shift_amount = tk.DoubleVar(value=15.0)
        self._var_color_shift_speed = tk.DoubleVar(value=0.5)
        csr = 0
        csr = self._slider_row(self._color_shift_settings_frame, "Cantidad (°):",
                               self._var_color_shift_amount, 1.0, 45.0, csr, fmt="{:.0f}", pct=True)
        csr = self._slider_row(self._color_shift_settings_frame, "Velocidad:",
                               self._var_color_shift_speed, 0.1, 2.0, csr, fmt="{:.1f}", number_of_steps=19, pct=True)
        self._color_shift_settings_frame.grid_remove()
        self._var_color_shift.trace_add("write", lambda *_: (
            self._color_shift_settings_frame.grid() if self._var_color_shift.get()
            else self._color_shift_settings_frame.grid_remove()
        ))
        fr += 1

        fr = self._check_row(_fx_inner, "Glitch effect (video)", self._var_glitch, fr)

        self._glitch_settings_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._glitch_settings_frame.grid(row=fr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._glitch_settings_frame.grid_columnconfigure(0, weight=1)
        self._var_glitch_intensity = tk.IntVar(value=4)
        self._var_glitch_speed = tk.IntVar(value=90)
        self._var_glitch_pulse = tk.IntVar(value=3)
        gr = 0
        gr = self._slider_row(self._glitch_settings_frame, "Intensidad:",
                               self._var_glitch_intensity, 1, 10, gr, fmt="{:.0f}", pct=True)
        gr = self._slider_row(self._glitch_settings_frame, "Frecuencia (frames):",
                               self._var_glitch_speed, 20, 180, gr, fmt="{:.0f}", pct=True)
        gr = self._slider_row(self._glitch_settings_frame, "Duración pulso:",
                               self._var_glitch_pulse, 1, 6, gr, fmt="{:.0f}", pct=True)
        if not self._var_glitch.get():
            self._glitch_settings_frame.grid_remove()
        self._var_glitch.trace_add("write", lambda *_: (
            self._glitch_settings_frame.grid() if self._var_glitch.get()
            else self._glitch_settings_frame.grid_remove()
        ))
        fr += 1

        fr = self._check_row(_fx_inner, "Overlay animado (video)", self._var_overlay,
                             fr, command=self._toggle_overlay_widgets)
        fr = self._check_row(_fx_inner, "Normalizar audio", self._var_normalize, fr)

        self._overlay_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._overlay_frame.grid(row=fr, column=0, sticky="ew", padx=12)
        self._var_overlay_path = tk.StringVar()
        ctk.CTkLabel(self._overlay_frame, text="Video overlay:",
                     text_color=C_MUTED, font=ctk.CTkFont(size=self._fs(11))).pack(side="left", padx=4)
        ctk.CTkEntry(self._overlay_frame, textvariable=self._var_overlay_path,
                     width=140).pack(side="left", padx=4)
        ctk.CTkButton(self._overlay_frame, text="...", width=30,
                      command=self._browse_overlay).pack(side="left")
        self._var_overlay_opacity = tk.DoubleVar(value=0.5)
        ctk.CTkLabel(self._overlay_frame, text="Opacidad:",
                     text_color=C_MUTED, font=ctk.CTkFont(size=self._fs(11))).pack(side="left", padx=(8, 2))
        ctk.CTkSlider(self._overlay_frame, from_=0.0, to=1.0,
                      variable=self._var_overlay_opacity, width=80,
                      fg_color=C_INPUT, progress_color=C_ACCENT,
                      button_color=C_ACCENT, button_hover_color=C_ACCENT_H).pack(side="left")
        self._overlay_frame.grid_remove()
        vr += 1

        # --- Texto overlay ---
        _sec_txt = ctk.CTkFrame(vf, fg_color=C_CARD, corner_radius=10,
                                border_width=1, border_color=C_BORDER)
        _sec_txt.grid(row=vr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_txt.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_txt, "Texto overlay").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _txt_inner = ctk.CTkFrame(_sec_txt, fg_color="transparent")
        _txt_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _txt_inner.grid_columnconfigure(0, weight=1)

        self._var_text_overlay = tk.BooleanVar(value=False)
        tr = self._check_row(_txt_inner, "Activar texto overlay estático", self._var_text_overlay,
                             0, command=self._toggle_text_overlay_widgets)

        self._text_overlay_frame = ctk.CTkFrame(
            _txt_inner, fg_color=C_PANEL, corner_radius=6,
            border_width=1, border_color=C_BORDER,
        )
        self._text_overlay_frame.grid(row=tr, column=0, sticky="ew", padx=12, pady=(16, 20))
        self._text_overlay_frame.grid_columnconfigure(0, weight=1)
        tof = 0

        ctk.CTkLabel(self._text_overlay_frame, text="Texto:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), anchor="w").grid(
            row=tof, column=0, sticky="w", padx=10, pady=(8, 0))
        tof += 1
        self._var_text_content = tk.StringVar()
        ctk.CTkEntry(self._text_overlay_frame, textvariable=self._var_text_content,
                     placeholder_text="Ej: Lo-Fi Beats \u266a", height=28).grid(
            row=tof, column=0, sticky="ew", padx=10, pady=(2, 6))
        tof += 1

        font_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        font_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        font_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(font_f, text="Fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        _fonts = available_fonts() or ["Arial"]
        self._var_text_font = tk.StringVar(value=_fonts[0])
        ctk.CTkOptionMenu(font_f, variable=self._var_text_font, values=_fonts,
                          width=160, height=28,
                          font=ctk.CTkFont(size=self._fs(11))).grid(row=0, column=1, sticky="w", padx=4)
        tof += 1

        _TEXT_COLORS = ["Blanco", "Gris claro", "Gris", "Gris oscuro", "Negro"]
        col_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        col_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        col_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(col_f, text="Color:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        self._var_text_color = tk.StringVar(value="Blanco")
        self._text_color_preview = ctk.CTkLabel(
            col_f, text="", width=16, height=16, corner_radius=8, fg_color="#FFFFFF")
        self._text_color_preview.grid(row=0, column=2, padx=(6, 0))
        _color_hex_map = {
            "Blanco": "#FFFFFF", "Gris claro": "#D0D0D0",
            "Gris": "#808080", "Gris oscuro": "#404040", "Negro": "#000000",
        }
        def _update_color_preview(name: str) -> None:
            self._text_color_preview.configure(fg_color=_color_hex_map.get(name, "#FFFFFF"))
            self._update_preview_overlay()
        ctk.CTkOptionMenu(col_f, variable=self._var_text_color, values=_TEXT_COLORS,
                          width=140, height=28, command=_update_color_preview,
                          font=ctk.CTkFont(size=self._fs(11))).grid(row=0, column=1, sticky="w", padx=4)
        tof += 1

        pos_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        pos_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(pos_f, text="Posición:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").pack(side="left")
        self._var_text_position = tk.StringVar(value="Bottom")
        for _pos in ("Top", "Middle", "Bottom"):
            ctk.CTkRadioButton(pos_f, text=_pos, variable=self._var_text_position,
                               value=_pos, font=ctk.CTkFont(size=self._fs(11))).pack(side="left", padx=6)
        tof += 1

        m_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        m_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        m_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(m_f, text="Margen (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_margin = tk.IntVar(value=40)
        _m_lbl = ctk.CTkLabel(m_f, text=_val_to_pct(40, 10, 120), text_color=C_TEXT,
                              font=ctk.CTkFont(size=self._fs(11)), width=40)
        _m_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(m_f, from_=10, to=120, variable=self._var_text_margin,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _m_lbl.configure(text=_val_to_pct(float(v), 10, 120))).grid(
            row=0, column=1, sticky="ew", padx=4)
        tof += 1

        fs_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        fs_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        fs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(fs_f, text="Tamaño fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_font_size = tk.IntVar(value=36)
        _fs_lbl = ctk.CTkLabel(fs_f, text=_val_to_pct(36, 12, 72), text_color=C_TEXT,
                               font=ctk.CTkFont(size=self._fs(11)), width=40)
        _fs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(fs_f, from_=12, to=72, variable=self._var_text_font_size,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _fs_lbl.configure(text=_val_to_pct(float(v), 12, 72))).grid(
            row=0, column=1, sticky="ew", padx=4)
        tof += 1

        gi_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        gi_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        gi_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(gi_f, text="Glitch (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_glitch_intensity = tk.IntVar(value=3)
        _gi_lbl = ctk.CTkLabel(gi_f, text=_val_to_pct(3, 0, 10), text_color=C_TEXT,
                               font=ctk.CTkFont(size=self._fs(11)), width=40)
        _gi_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(gi_f, from_=0, to=10, variable=self._var_text_glitch_intensity,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _gi_lbl.configure(text=_val_to_pct(float(v), 0, 10))).grid(
            row=0, column=1, sticky="ew", padx=4)
        tof += 1

        gs_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        gs_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=(2, 8))
        gs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(gs_f, text="Velocidad glitch:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_glitch_speed = tk.DoubleVar(value=4.0)
        _gs_lbl = ctk.CTkLabel(gs_f, text=_val_to_pct(4.0, 0.5, 12.0), text_color=C_TEXT,
                               font=ctk.CTkFont(size=self._fs(11)), width=40)
        _gs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(gs_f, from_=0.5, to=12.0, variable=self._var_text_glitch_speed,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _gs_lbl.configure(text=_val_to_pct(float(v), 0.5, 12.0))).grid(
            row=0, column=1, sticky="ew", padx=4)

        self._text_overlay_frame.grid_remove()

        # --- Texto overlay DINÁMICO (ATV) ---
        self._var_dyn_text_overlay = tk.BooleanVar(value=False)
        dyn_tr = tr + 1   # row after the static frame
        dyn_tr = self._check_row(_txt_inner, "Activar texto overlay dinámico",
                                 self._var_dyn_text_overlay, dyn_tr,
                                 command=self._toggle_dyn_text_overlay_widgets)
        self._dyn_text_overlay_frame = ctk.CTkFrame(
            _txt_inner, fg_color=C_PANEL, corner_radius=6,
            border_width=1, border_color=C_BORDER,
        )
        self._dyn_text_overlay_frame.grid(row=dyn_tr, column=0, sticky="ew", padx=12, pady=(4, 16))
        self._dyn_text_overlay_frame.grid_columnconfigure(0, weight=1)
        dtof = 0

        # Modo dinámico
        _dyn_mode_f = ctk.CTkFrame(self._dyn_text_overlay_frame, fg_color="transparent")
        _dyn_mode_f.grid(row=dtof, column=0, sticky="ew", padx=10, pady=(8, 4))
        _dyn_mode_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_dyn_mode_f, text="Fuente del texto:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        _DYN_MODES = ["Texto fijo", "Nombre de canción", "Prefijo + Nombre de canción"]
        self._var_dyn_text_mode = tk.StringVar(value="Texto fijo")
        ctk.CTkOptionMenu(
            _dyn_mode_f, variable=self._var_dyn_text_mode, values=_DYN_MODES,
            width=210, height=28, font=ctk.CTkFont(size=self._fs(11)),
            command=lambda _: self._on_dyn_text_mode_change(),
        ).grid(row=0, column=1, sticky="w", padx=4)
        dtof += 1

        # Texto fijo (visible only when mode == "Texto fijo")
        self._dyn_text_fixed_frame = ctk.CTkFrame(self._dyn_text_overlay_frame, fg_color="transparent")
        self._dyn_text_fixed_frame.grid(row=dtof, column=0, sticky="ew", padx=10, pady=(0, 2))
        self._dyn_text_fixed_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self._dyn_text_fixed_frame, text="Texto:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), anchor="w").grid(
            row=0, column=0, sticky="w", pady=(4, 0))
        self._var_dyn_text_content = tk.StringVar()
        ctk.CTkEntry(self._dyn_text_fixed_frame, textvariable=self._var_dyn_text_content,
                     placeholder_text="Ej: Lo-Fi Beats ?", height=28).grid(
            row=1, column=0, sticky="ew", pady=(2, 4))
        dtof += 1

        _dyn_font_f = ctk.CTkFrame(self._dyn_text_overlay_frame, fg_color="transparent")
        _dyn_font_f.grid(row=dtof, column=0, sticky="ew", padx=10, pady=2)
        _dyn_font_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_dyn_font_f, text="Fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        _dyn_fonts = available_fonts() or ["Arial"]
        self._var_dyn_text_font = tk.StringVar(value=_dyn_fonts[0])
        ctk.CTkOptionMenu(_dyn_font_f, variable=self._var_dyn_text_font, values=_dyn_fonts,
                          width=160, height=28,
                          font=ctk.CTkFont(size=self._fs(11))).grid(row=0, column=1, sticky="w", padx=4)
        dtof += 1

        _TEXT_COLORS_DYN = ["Blanco", "Gris claro", "Gris", "Gris oscuro", "Negro"]
        _dyn_col_f = ctk.CTkFrame(self._dyn_text_overlay_frame, fg_color="transparent")
        _dyn_col_f.grid(row=dtof, column=0, sticky="ew", padx=10, pady=2)
        _dyn_col_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_dyn_col_f, text="Color:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        self._var_dyn_text_color = tk.StringVar(value="Blanco")
        self._dyn_text_color_preview = ctk.CTkLabel(
            _dyn_col_f, text="", width=16, height=16, corner_radius=8, fg_color="#FFFFFF")
        self._dyn_text_color_preview.grid(row=0, column=2, padx=(6, 0))
        _dyn_color_hex_map = {
            "Blanco": "#FFFFFF", "Gris claro": "#D0D0D0",
            "Gris": "#808080", "Gris oscuro": "#404040", "Negro": "#000000",
        }
        def _update_dyn_color_preview(name: str) -> None:
            self._dyn_text_color_preview.configure(fg_color=_dyn_color_hex_map.get(name, "#FFFFFF"))
            self._update_preview_overlay()
        ctk.CTkOptionMenu(_dyn_col_f, variable=self._var_dyn_text_color, values=_TEXT_COLORS_DYN,
                          width=140, height=28, command=_update_dyn_color_preview,
                          font=ctk.CTkFont(size=self._fs(11))).grid(row=0, column=1, sticky="w", padx=4)
        dtof += 1

        _dyn_pos_f = ctk.CTkFrame(self._dyn_text_overlay_frame, fg_color="transparent")
        _dyn_pos_f.grid(row=dtof, column=0, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(_dyn_pos_f, text="Posición:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").pack(side="left")
        self._var_dyn_text_position = tk.StringVar(value="Top")
        for _pos in ("Top", "Middle", "Bottom"):
            ctk.CTkRadioButton(_dyn_pos_f, text=_pos, variable=self._var_dyn_text_position,
                               value=_pos, font=ctk.CTkFont(size=self._fs(11))).pack(side="left", padx=6)
        dtof += 1

        _dyn_m_f = ctk.CTkFrame(self._dyn_text_overlay_frame, fg_color="transparent")
        _dyn_m_f.grid(row=dtof, column=0, sticky="ew", padx=10, pady=2)
        _dyn_m_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_dyn_m_f, text="Margen (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_dyn_text_margin = tk.IntVar(value=40)
        _dyn_m_lbl = ctk.CTkLabel(_dyn_m_f, text=_val_to_pct(40, 10, 120), text_color=C_TEXT,
                                  font=ctk.CTkFont(size=self._fs(11)), width=40)
        _dyn_m_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_dyn_m_f, from_=10, to=120, variable=self._var_dyn_text_margin,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _dyn_m_lbl.configure(text=_val_to_pct(float(v), 10, 120))).grid(
            row=0, column=1, sticky="ew", padx=4)
        dtof += 1

        _dyn_fs_f = ctk.CTkFrame(self._dyn_text_overlay_frame, fg_color="transparent")
        _dyn_fs_f.grid(row=dtof, column=0, sticky="ew", padx=10, pady=2)
        _dyn_fs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_dyn_fs_f, text="Tamaño fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_dyn_text_font_size = tk.IntVar(value=36)
        _dyn_fs_lbl = ctk.CTkLabel(_dyn_fs_f, text=_val_to_pct(36, 12, 72), text_color=C_TEXT,
                                   font=ctk.CTkFont(size=self._fs(11)), width=40)
        _dyn_fs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_dyn_fs_f, from_=12, to=72, variable=self._var_dyn_text_font_size,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _dyn_fs_lbl.configure(text=_val_to_pct(float(v), 12, 72))).grid(
            row=0, column=1, sticky="ew", padx=4)
        dtof += 1

        _dyn_gi_f = ctk.CTkFrame(self._dyn_text_overlay_frame, fg_color="transparent")
        _dyn_gi_f.grid(row=dtof, column=0, sticky="ew", padx=10, pady=2)
        _dyn_gi_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_dyn_gi_f, text="Glitch (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_dyn_text_glitch_intensity = tk.IntVar(value=3)
        _dyn_gi_lbl = ctk.CTkLabel(_dyn_gi_f, text=_val_to_pct(3, 0, 10), text_color=C_TEXT,
                                   font=ctk.CTkFont(size=self._fs(11)), width=40)
        _dyn_gi_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_dyn_gi_f, from_=0, to=10, variable=self._var_dyn_text_glitch_intensity,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _dyn_gi_lbl.configure(text=_val_to_pct(float(v), 0, 10))).grid(
            row=0, column=1, sticky="ew", padx=4)
        dtof += 1

        _dyn_gs_f = ctk.CTkFrame(self._dyn_text_overlay_frame, fg_color="transparent")
        _dyn_gs_f.grid(row=dtof, column=0, sticky="ew", padx=10, pady=(2, 8))
        _dyn_gs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_dyn_gs_f, text="Velocidad glitch:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_dyn_text_glitch_speed = tk.DoubleVar(value=4.0)
        _dyn_gs_lbl = ctk.CTkLabel(_dyn_gs_f, text=_val_to_pct(4.0, 0.5, 12.0), text_color=C_TEXT,
                                   font=ctk.CTkFont(size=self._fs(11)), width=40)
        _dyn_gs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_dyn_gs_f, from_=0.5, to=12.0, variable=self._var_dyn_text_glitch_speed,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _dyn_gs_lbl.configure(text=_val_to_pct(float(v), 0.5, 12.0))).grid(
            row=0, column=1, sticky="ew", padx=4)

        self._dyn_text_overlay_frame.grid_remove()

        _refresh = lambda *_: (self._update_preview_overlay()
                               if getattr(self, "_current_mode", "") == "Audio \u2192 Video" else None)
        self._var_text_overlay.trace_add("write", _refresh)
        self._var_text_content.trace_add("write", _refresh)
        self._var_text_position.trace_add("write", _refresh)
        self._var_text_margin.trace_add("write", _refresh)
        self._var_text_font_size.trace_add("write", _refresh)
        self._var_text_font.trace_add("write", _refresh)
        self._var_text_color.trace_add("write", _refresh)
        self._var_dyn_text_overlay.trace_add("write", _refresh)
        self._var_dyn_text_content.trace_add("write", _refresh)
        self._var_dyn_text_mode.trace_add("write", _refresh)
        self._var_dyn_text_position.trace_add("write", _refresh)
        self._var_dyn_text_margin.trace_add("write", _refresh)
        self._var_dyn_text_font_size.trace_add("write", _refresh)
        self._var_dyn_text_font.trace_add("write", _refresh)
        self._var_dyn_text_color.trace_add("write", _refresh)

        # --------------------------------------------------------------
        # TAB: SALIDA
        # --------------------------------------------------------------
        sf = ctk.CTkScrollableFrame(tab_salida, fg_color="transparent")
        sf.pack(fill="both", expand=True, padx=16, pady=(8, 12))
        sf.grid_columnconfigure(0, weight=1)
        _init_scrollbar(sf)
        sr = 0

        # --- Naming ---
        _sec_name = ctk.CTkFrame(sf, fg_color=C_CARD, corner_radius=10,
                                 border_width=1, border_color=C_BORDER)
        _sec_name.grid(row=sr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_name.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_name, "Nombre de salida").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _name_inner = ctk.CTkFrame(_sec_name, fg_color="transparent")
        _name_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _name_inner.grid_columnconfigure(0, weight=1)
        nr = 0

        inner_mode = ctk.CTkFrame(_name_inner, fg_color="transparent")
        inner_mode.grid(row=nr, column=0, sticky="ew", padx=4, pady=4)
        inner_mode.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(inner_mode, text="Modo:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=60, anchor="w"
                     ).grid(row=0, column=0, sticky="w")
        self._var_naming_mode = tk.StringVar(value="Default")
        ctk.CTkOptionMenu(
            inner_mode,
            values=["Default", "Nombre", "Prefijo", "Lista personalizada", "Prefijo + Lista personalizada"],
            variable=self._var_naming_mode,
            command=self._on_naming_mode_change,
            fg_color=C_CARD,
            button_color=C_ACCENT if self._current_theme == "Dark" else C_BORDER,
            text_color=C_TEXT,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        nr += 1

        self._naming_name_frame = ctk.CTkFrame(_name_inner, fg_color="transparent")
        self._naming_name_frame.grid(row=nr, column=0, sticky="ew", padx=4, pady=(2, 0))
        self._naming_name_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self._naming_name_frame, text="Nombre:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=60, anchor="w"
                     ).grid(row=0, column=0, sticky="w")
        self._var_naming_name = tk.StringVar()
        ctk.CTkEntry(self._naming_name_frame, textvariable=self._var_naming_name,
                     placeholder_text="Ej: Lofi Chill", height=28
                     ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._naming_name_frame.grid_remove()
        nr += 1

        self._naming_prefix_frame = ctk.CTkFrame(_name_inner, fg_color="transparent")
        self._naming_prefix_frame.grid(row=nr, column=0, sticky="ew", padx=4, pady=(2, 0))
        self._naming_prefix_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self._naming_prefix_frame, text="Prefijo:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=60, anchor="w"
                     ).grid(row=0, column=0, sticky="w")
        self._var_naming_prefix = tk.StringVar()
        ctk.CTkEntry(self._naming_prefix_frame, textvariable=self._var_naming_prefix,
                     placeholder_text="Ej: Lofi - ", height=28
                     ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._naming_prefix_frame.grid_remove()
        nr += 1

        self._naming_list_frame = ctk.CTkFrame(_name_inner, fg_color="transparent")
        self._naming_list_frame.grid(row=nr, column=0, sticky="ew", padx=4, pady=(4, 0))
        self._naming_list_frame.grid_columnconfigure(0, weight=1)
        _nl_hdr = ctk.CTkFrame(self._naming_list_frame, fg_color="transparent")
        _nl_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        _nl_hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(_nl_hdr, text="Nombres personalizados (uno por línea):",
                     text_color=C_MUTED, font=ctk.CTkFont(size=self._fs(11)), anchor="w"
                     ).grid(row=0, column=0, sticky="w")
        self._lbl_names_count = ctk.CTkLabel(
            _nl_hdr, text="0 nombres", text_color=C_TEXT_DIM,
            font=ctk.CTkFont(size=self._fs(10)))
        self._lbl_names_count.grid(row=0, column=1, sticky="e", padx=(4, 0))
        self._txt_naming_list = ctk.CTkTextbox(
            self._naming_list_frame, height=80, fg_color=C_INPUT,
            text_color=C_TEXT, font=ctk.CTkFont(family="Consolas", size=self._fs(11)))
        self._txt_naming_list.grid(row=1, column=0, sticky="ew")
        self._txt_naming_list.bind("<KeyRelease>", lambda *_: self._refresh_names_count())
        _btn_names_list = ctk.CTkButton(
            self._naming_list_frame, text="Ver / editar lista  \u25b6",
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, height=40,
            font=ctk.CTkFont(size=self._fs(11)),
            command=self._open_names_list_dialog,
        )
        _btn_names_list.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        _apply_sec_hover(_btn_names_list)
        self._naming_list_frame.grid_remove()
        nr += 1

        self._var_naming_autonumber = tk.BooleanVar(value=True)
        self._cb_naming_autonumber = ctk.CTkCheckBox(
            _name_inner,
            text="Numeración automática (01, 02…)",
            variable=self._var_naming_autonumber,
            font=ctk.CTkFont(size=self._fs(11)),
            text_color=C_TEXT,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_H,
            border_color=C_BORDER,
            checkmark_color="#ffffff",
        )
        self._cb_naming_autonumber.grid(row=nr, column=0, sticky="w", padx=16, pady=(6, 6))
        sr += 1

        # --- Rendimiento ---
        _sec_perf = ctk.CTkFrame(sf, fg_color=C_CARD, corner_radius=10,
                                 border_width=1, border_color=C_BORDER)
        _sec_perf.grid(row=sr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_perf.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_perf, "Rendimiento").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)

        inner_perf = ctk.CTkFrame(_sec_perf, fg_color="transparent")
        inner_perf.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        inner_perf.grid_columnconfigure(1, weight=1)
        inner_perf.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(inner_perf, text="CPU:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=40, anchor="w"
                     ).grid(row=0, column=0, sticky="w")
        self._var_cpu_mode = tk.StringVar(value="Medium")
        ctk.CTkOptionMenu(
            inner_perf, values=["Low", "Medium", "High", "Max"],
            variable=self._var_cpu_mode, fg_color=C_CARD,
            button_color=C_ACCENT if self._current_theme == "Dark" else C_BORDER,
            text_color=C_TEXT, width=100,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 2))
        _cpu_btn = ctk.CTkButton(
            inner_perf, text="?", width=28, height=28,
            fg_color=C_ACCENT, hover_color=C_ACCENT_H,
            text_color="#ffffff",
            font=ctk.CTkFont(size=self._fs(11), weight="bold"), corner_radius=4,
        )
        _cpu_btn.grid(row=0, column=2, padx=(4, 10))
        _Tooltip(
            _cpu_btn,
            "Controla cuántos núcleos del procesador usa FFmpeg.\n\n"
            "• Low   (25%)  ?  El sistema sigue libre, encoding lento.\n"
            "• Medium (50%) ?  Balance recomendado para uso diario.\n"
            "• High  (75%)  ?  Más rápido, el sistema puede sentirse pesado.\n"
            "• Max  (100%)  ?  Usa todos los núcleos. Máxima velocidad.",
        )
        ctk.CTkLabel(inner_perf, text="Preset:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=50, anchor="w"
                     ).grid(row=0, column=3, sticky="w")
        self._var_encode_preset = tk.StringVar(value="slow")
        ctk.CTkOptionMenu(
            inner_perf,
            values=["ultrafast", "superfast", "veryfast",
                    "faster", "fast", "medium", "slow", "slower", "veryslow"],
            variable=self._var_encode_preset, fg_color=C_CARD,
            button_color=C_ACCENT if self._current_theme == "Dark" else C_BORDER,
            text_color=C_TEXT, width=100,
        ).grid(row=0, column=4, sticky="ew", padx=(4, 2))
        _preset_btn = ctk.CTkButton(
            inner_perf, text="?", width=28, height=28,
            fg_color=C_ACCENT, hover_color=C_ACCENT_H,
            text_color="#ffffff",
            font=ctk.CTkFont(size=self._fs(11), weight="bold"), corner_radius=4,
        )
        _preset_btn.grid(row=0, column=5, padx=(4, 0))
        _Tooltip(
            _preset_btn,
            "Velocidad de encoding vs calidad/tamaño del archivo.\n\n"
            "Más rápido = archivo más grande, encode ágil.\n"
            "Más lento  = archivo más pequeño, mejor calidad.\n\n"
            "• ultrafast / superfast ? Solo para pruebas rápidas.\n"
            "• fast / medium         ? Buena calidad, uso general.\n"
            "• slow                  ? Calidad óptima (recomendado).\n"
            "• veryslow              ? Máxima compresión, muy lento.",
        )

        inner_gpu = ctk.CTkFrame(_sec_perf, fg_color="transparent")
        inner_gpu.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 4))
        inner_gpu.grid_columnconfigure(1, weight=1)
        self._var_gpu_encoding = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            inner_gpu, text="GPU Encoding (NVENC)",
            variable=self._var_gpu_encoding,
            font=ctk.CTkFont(size=self._fs(11)),
            text_color=C_TEXT, progress_color=C_ACCENT,
            button_color=C_BORDER, button_hover_color=C_ACCENT_H,
        ).grid(row=0, column=0, sticky="w")
        _gpu_btn = ctk.CTkButton(
            inner_gpu, text="?", width=28, height=28,
            fg_color=C_ACCENT, hover_color=C_ACCENT_H,
            text_color="#ffffff",
            font=ctk.CTkFont(size=self._fs(11), weight="bold"), corner_radius=4,
        )
        _gpu_btn.grid(row=0, column=1, sticky="w", padx=(8, 0))
        _Tooltip(
            _gpu_btn,
            "Usa el encoder de hardware NVIDIA NVENC.\n\n"
            "• Requiere GPU NVIDIA con NVENC (GTX 1050+).\n"
            "• 5-10× más rápido que libx264.\n"
            "• Libera la CPU para los filtros de video.\n"
            "• Calidad similar para YouTube/streaming.\n\n"
            "Si el encoding falla, desactiva esta opción.",
        )
        _cpu_total = os.cpu_count() or 2
        ctk.CTkLabel(
            _sec_perf, text=f"CPU detectados: {_cpu_total} núcleos",
            text_color=C_MUTED, font=ctk.CTkFont(size=self._fs(10)), anchor="w",
        ).grid(row=3, column=0, sticky="w", padx=14, pady=(0, 6))

    # --- Right panel --------------------------------------------------

    def _build_right_panel(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent",
                             corner_radius=0, border_width=0)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        self._right_panel_frame = frame

        # Preview imagen
        self._preview_frame = ctk.CTkFrame(
            frame, fg_color=C_CARD, corner_radius=6, height=360,
            border_width=1, border_color=C_BORDER,
        )
        self._preview_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 0))
        self._preview_frame.grid_propagate(False)
        self._preview_frame.grid_columnconfigure(0, weight=1)
        self._preview_frame.grid_columnconfigure(1, weight=0, minsize=0)
        self._preview_frame.grid_rowconfigure(0, weight=1)
        self._preview_frame.grid_rowconfigure(1, weight=0)

        self._lbl_preview = ctk.CTkLabel(
            self._preview_frame,
            text="Sin imagen seleccionada",
            text_color=C_MUTED,
            font=ctk.CTkFont(size=12),
        )
        self._lbl_preview.grid(row=0, column=0, sticky="nsew")
        self._lbl_preview.bind("<Double-Button-1>", lambda _e: self._open_fullscreen_preview())
        self._preview_img_path: str = ""  # ruta original para re-renderizar overlay
        # Rutas de preview por modo — cada modo guarda su propio estado
        self._atv_preview_path: str = ""
        self._sl_preview_path:  str = ""
        self._sho_preview_path: str = ""

        # Filmstrip horizontal — ATV y Slideshow (debajo del preview)
        self._thumb_strip = ctk.CTkScrollableFrame(
            self._preview_frame,
            orientation="horizontal",
            height=42,
            fg_color=C_BG,
            scrollbar_button_color=C_BORDER,
            scrollbar_button_hover_color=C_HOVER,
        )
        self._thumb_strip.grid(row=1, column=0, sticky="ew")
        self._thumb_strip.grid_remove()
        self._thumb_strip_imgs: list[ctk.CTkImage] = []

        # Filmstrip vertical — Shorts (a la derecha del preview)
        self._thumb_strip_vert = ctk.CTkScrollableFrame(
            self._preview_frame,
            orientation="vertical",
            width=52,
            fg_color=C_BG,
            scrollbar_button_color=C_BORDER,
            scrollbar_button_hover_color=C_HOVER,
        )
        self._thumb_strip_vert.grid(row=0, column=1, sticky="ns", rowspan=2)
        self._thumb_strip_vert.grid_remove()
        self._thumb_strip_vert_imgs: list[ctk.CTkImage] = []

        # Mostrar imagen de fondo por defecto si existe (sin asignarla como selección)
        _default_bg = _BUNDLE_DIR / "defaultbg.png"
        if _default_bg.is_file():
            try:
                _img = Image.open(str(_default_bg))
                _img = AudioToVideoApp._crop_img_to_16_9(_img)
                _ctk_img = ctk.CTkImage(light_image=_img, dark_image=_img, size=_img.size)
                self._lbl_preview.configure(image=_ctk_img, text="")
                self._lbl_preview.image = _ctk_img
            except Exception:
                pass

        # Info de audios detectados (pegado justo debajo del preview)
        _audio_lbl_wrap = ctk.CTkFrame(frame, fg_color="transparent", width=1, height=26)
        _audio_lbl_wrap.grid(row=1, column=0, sticky="ew", padx=16, pady=(6, 0))
        _audio_lbl_wrap.grid_propagate(False)
        self._lbl_audio_count = ctk.CTkLabel(
            _audio_lbl_wrap,
            text="Audios: \u2014",
            font=ctk.CTkFont(size=self._fs(11)),
            text_color=C_MUTED,
            anchor="w",
        )
        self._lbl_audio_count.pack(fill="both", expand=True)

        # Process Logs
        _logs_hdr = ctk.CTkFrame(frame, fg_color="transparent")
        _logs_hdr.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 2))
        ctk.CTkLabel(
            _logs_hdr, text=FA_LIST,
            font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(13)),
            text_color=C_TEXT,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            _logs_hdr, text="Process Logs",
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
            text_color=C_TEXT,
        ).pack(side="left")
        # "Clear" button
        ctk.CTkButton(
            _logs_hdr, text="Clear", width=50, height=22,
            fg_color="transparent", hover_color=C_HOVER,
            text_color=C_TEXT_DIM, corner_radius=4,
            font=ctk.CTkFont(size=self._fs(10)),
            command=lambda: (
                self._log_text.configure(state="normal"),
                self._log_text.delete("1.0", "end"),
                self._log_text.configure(state="disabled"),
            ),
        ).pack(side="right")

        self._log_text = ctk.CTkTextbox(
            frame,
            width=1,
            fg_color=C_LOG,
            text_color=C_LOG_TEXT,
            font=ctk.CTkFont(family="Consolas", size=self._fs(11)),
            wrap="word",
            state="disabled",
            border_width=1,
            border_color=C_BORDER,
            corner_radius=6,
        )
        self._log_text.grid(row=3, column=0, sticky="nsew", padx=16, pady=(0, 6))
        frame.grid_rowconfigure(3, weight=1)

        # Progreso global
        self._lbl_progress_global = ctk.CTkLabel(
            frame, text="Progreso: \u2014", font=ctk.CTkFont(size=self._fs(11)), text_color=C_MUTED
        )
        self._lbl_progress_global.grid(row=4, column=0, sticky="w", padx=16)

        self._progress_global = ctk.CTkProgressBar(
            frame, mode="determinate",
            progress_color=C_ACCENT, fg_color=C_CARD,
            border_color=C_BORDER, corner_radius=4)
        self._progress_global.set(0)
        self._progress_global.grid(row=5, column=0, sticky="ew", padx=16, pady=(2, 2))

        # Progreso por archivo
        self._lbl_progress_file = ctk.CTkLabel(
            frame, text="", font=ctk.CTkFont(size=self._fs(10)), text_color=C_MUTED
        )
        self._lbl_progress_file.grid(row=6, column=0, sticky="w", padx=16)

        self._progress_file = ctk.CTkProgressBar(
            frame, mode="indeterminate", height=8,
            progress_color=C_ACCENT, fg_color=C_CARD,
            corner_radius=4)
        self._progress_file.grid(row=7, column=0, sticky="ew", padx=16, pady=(0, 0))
        self._progress_file.stop()

    # --- Slideshow left panel -----------------------------------------

    def _build_slideshow_left_panel(self, parent: ctk.CTkFrame) -> None:
        """Panel izquierdo del modo Slideshow (separado, comparte panel derecho)."""
        from core.slideshow_builder import TRANSITION_CHOICES

        panel, _tabs = self._make_tab_panel(
            parent,
            [("Archivos", "archivos"), ("Secuencia", "secuencia"), ("Rendimiento", "rendimiento")],
            accent=C_ACCENT_SLIDE,
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self._sl_scroll_frame = panel
        panel.grid_remove()  # hidden until mode is switched

        tab_archivos    = _tabs["archivos"]
        tab_secuencia   = _tabs["secuencia"]
        tab_rendimiento = _tabs["rendimiento"]

        # --------------------------------------------------------------
        # TAB: ARCHIVOS
        # --------------------------------------------------------------
        af = ctk.CTkScrollableFrame(tab_archivos, fg_color="transparent")
        af.pack(fill="both", expand=True, padx=16, pady=(8, 12))
        af.grid_columnconfigure(0, weight=1)
        _init_scrollbar(af)

        _card_dir = ctk.CTkFrame(af, fg_color=C_CARD, corner_radius=10,
                                 border_width=1, border_color=C_BORDER)
        _card_dir.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        _card_dir.grid_columnconfigure(0, weight=1)
        self._section_header(_card_dir, "Configuración de archivos").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _dir_inner = ctk.CTkFrame(_card_dir, fg_color="transparent")
        _dir_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _dir_inner.grid_columnconfigure(0, weight=1)
        ar = 0

        self._var_sl_images_folder = tk.StringVar()
        ar = self._file_row(_dir_inner, "Carpeta de imágenes:", self._var_sl_images_folder,
                            self._sl_browse_images_folder, ar)

        self._var_sl_audio_enabled = tk.BooleanVar(value=False)
        ar = self._check_row(_dir_inner, "Incluir audio (opcional)", self._var_sl_audio_enabled,
                             ar, command=self._sl_toggle_audio)
        self._sl_audio_wrapper = ctk.CTkFrame(_dir_inner, fg_color="transparent")
        self._sl_audio_wrapper.grid(row=ar, column=0, sticky="ew")
        self._sl_audio_wrapper.grid_columnconfigure(0, weight=1)

        # -- Mode radio: Un archivo / Carpeta de audios ---------------
        self._var_sl_audio_mode = tk.StringVar(value="file")
        _radio_row = ctk.CTkFrame(self._sl_audio_wrapper, fg_color="transparent")
        _radio_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 2))
        ctk.CTkRadioButton(
            _radio_row, text="Un archivo", variable=self._var_sl_audio_mode,
            value="file", command=self._sl_toggle_audio_mode,
            fg_color=C_ACCENT_SLIDE, hover_color=C_ACCENT_SLIDE_H,
            text_color=C_TEXT, font=ctk.CTkFont(size=self._fs(11)),
        ).pack(side="left", padx=(0, 16))
        ctk.CTkRadioButton(
            _radio_row, text="Carpeta de audios", variable=self._var_sl_audio_mode,
            value="folder", command=self._sl_toggle_audio_mode,
            fg_color=C_ACCENT_SLIDE, hover_color=C_ACCENT_SLIDE_H,
            text_color=C_TEXT, font=ctk.CTkFont(size=self._fs(11)),
        ).pack(side="left")

        # -- Single-file sub-frame -------------------------------------
        self._sl_single_audio_frame = ctk.CTkFrame(self._sl_audio_wrapper, fg_color="transparent")
        self._sl_single_audio_frame.grid(row=1, column=0, sticky="ew")
        self._sl_single_audio_frame.grid_columnconfigure(0, weight=1)
        self._var_sl_audio_file = tk.StringVar()
        self._file_row(self._sl_single_audio_frame, "Archivo de audio:", self._var_sl_audio_file,
                       self._sl_browse_audio_file, 0)

        # -- Folder sub-frame ------------------------------------------
        self._sl_folder_audio_frame = ctk.CTkFrame(self._sl_audio_wrapper, fg_color="transparent")
        self._sl_folder_audio_frame.grid(row=1, column=0, sticky="ew")
        self._sl_folder_audio_frame.grid_columnconfigure(0, weight=1)
        self._var_sl_audio_folder = tk.StringVar()
        self._file_row(self._sl_folder_audio_frame, "Carpeta de audios:", self._var_sl_audio_folder,
                       self._sl_browse_audio_folder, 0)
        self._sl_audio_folder_lbl = ctk.CTkLabel(
            self._sl_folder_audio_frame, text="",
            text_color=C_MUTED, font=ctk.CTkFont(size=self._fs(10)), anchor="w",
        )
        self._sl_audio_folder_lbl.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 4))
        self._sl_folder_audio_frame.grid_remove()  # hidden until folder mode selected

        # -- Crossfade slider ------------------------------------------
        self._var_sl_crossfade = tk.DoubleVar(value=2.0)
        _xf_row = ctk.CTkFrame(self._sl_audio_wrapper, fg_color="transparent")
        _xf_row.grid(row=2, column=0, sticky="ew", padx=12, pady=(8, 6))
        _xf_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            _xf_row, text="Crossfade (s):", text_color=C_TEXT,
            font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        _xf_val_lbl = ctk.CTkLabel(
            _xf_row, text="2.0s", text_color=C_TEXT,
            font=ctk.CTkFont(size=self._fs(11)), width=50,
        )
        _xf_val_lbl.grid(row=0, column=2, padx=(4, 0))

        def _update_xf_lbl(v: str) -> None:
            try:
                _xf_val_lbl.configure(text=f"{float(v):.1f}s")
            except ValueError:
                pass

        ctk.CTkSlider(
            _xf_row, from_=0.0, to=5.0, number_of_steps=10,
            variable=self._var_sl_crossfade, command=_update_xf_lbl,
            fg_color=C_INPUT, progress_color=C_ACCENT_SLIDE,
            button_color=C_ACCENT_SLIDE, button_hover_color=C_ACCENT_SLIDE_H,
        ).grid(row=0, column=1, sticky="ew", padx=8)

        self._sl_audio_wrapper.grid_remove()
        ar += 1

        self._var_sl_output_folder = tk.StringVar()
        ar = self._file_row(_dir_inner, "Carpeta de salida:", self._var_sl_output_folder,
                            self._sl_browse_output_folder, ar)

        _nm_inner = ctk.CTkFrame(_dir_inner, fg_color="transparent")
        _nm_inner.grid(row=ar, column=0, sticky="ew", padx=12, pady=(0, 8))
        _nm_inner.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_nm_inner, text="Nombre del archivo:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0, 8))
        self._var_sl_output_name = tk.StringVar(value="slideshow")
        ctk.CTkEntry(_nm_inner, textvariable=self._var_sl_output_name, height=30).grid(
            row=0, column=1, sticky="ew")
        ctk.CTkLabel(_nm_inner, text=".mp4", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11))).grid(row=0, column=2, padx=(4, 0))
        ar += 1

        _btn_sl_reload = ctk.CTkButton(
            _dir_inner, text="\u21bb  RECARGAR CARPETAS",
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, height=40,
            font=ctk.CTkFont(size=self._fs(11)),
            command=self._sl_reload,
        )
        _btn_sl_reload.grid(row=ar, column=0, padx=12, pady=(0, 8), sticky="ew")
        _apply_sec_hover(_btn_sl_reload)
        ar += 1

        self._sl_lbl_count = ctk.CTkLabel(
            _dir_inner, text="\u266b Imágenes: \u2014",
            font=ctk.CTkFont(size=self._fs(11)), text_color=C_MUTED,
            justify="left", anchor="w",
        )
        self._sl_lbl_count.grid(row=ar, column=0, sticky="w", padx=14, pady=(0, 6))

        # --------------------------------------------------------------
        # TAB: SECUENCIA
        # --------------------------------------------------------------
        sqf = ctk.CTkScrollableFrame(tab_secuencia, fg_color="transparent")
        sqf.pack(fill="both", expand=True, padx=16, pady=(8, 12))
        sqf.grid_columnconfigure(0, weight=1)
        _init_scrollbar(sqf)
        sqr = 0

        # Duración
        _sec_dur = ctk.CTkFrame(sqf, fg_color=C_CARD, corner_radius=10,
                                border_width=1, border_color=C_BORDER)
        _sec_dur.grid(row=sqr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_dur.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_dur, "Duración y transición").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _dur_inner = ctk.CTkFrame(_sec_dur, fg_color="transparent")
        _dur_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _dur_inner.grid_columnconfigure(0, weight=1)
        self._var_sl_duration = tk.DoubleVar(value=5.0)
        dr = self._slider_row(
            _dur_inner, "Dur. por imagen:", self._var_sl_duration,
            3.0, 30.0, 0, fmt="{:.0f} s",
            tooltip_text="Segundos que se muestra cada imagen (3\u201330 s)",
            number_of_steps=27,
        )
        _tr_row = ctk.CTkFrame(_dur_inner, fg_color="transparent")
        _tr_row.grid(row=dr, column=0, sticky="ew", padx=4, pady=(4, 6))
        _tr_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_tr_row, text="Transición:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(
            row=0, column=0, sticky="w")
        self._var_sl_transition = tk.StringVar(value="Crossfade")
        ctk.CTkComboBox(
            _tr_row, values=TRANSITION_CHOICES,
            variable=self._var_sl_transition, state="readonly",
            fg_color=C_INPUT, button_color=C_ACCENT_SLIDE,
            border_color=C_BORDER, text_color=C_TEXT,
            font=ctk.CTkFont(size=self._fs(11)), height=30,
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        sqr += 1

        # Resolución
        _sec_res = ctk.CTkFrame(sqf, fg_color=C_CARD, corner_radius=10,
                                border_width=1, border_color=C_BORDER)
        _sec_res.grid(row=sqr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_res.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_res, "Resolución").pack(fill="x")
        self._var_sl_resolution = tk.StringVar(value="1080p")
        _res_inner = ctk.CTkFrame(_sec_res, fg_color="transparent")
        _res_inner.pack(fill="x", padx=16, pady=(16, 20))
        for _res in ("720p", "1080p", "4K"):
            ctk.CTkRadioButton(
                _res_inner, text=_res,
                variable=self._var_sl_resolution, value=_res,
                font=ctk.CTkFont(size=self._fs(11)), text_color=C_TEXT,
            ).pack(side="left", padx=6)
        sqr += 1

        # Efectos
        _sec_fx = ctk.CTkFrame(sqf, fg_color=C_CARD, corner_radius=10,
                               border_width=1, border_color=C_BORDER)
        _sec_fx.grid(row=sqr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_fx.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_fx, "Efectos").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _fx_inner = ctk.CTkFrame(_sec_fx, fg_color="transparent")
        _fx_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _fx_inner.grid_columnconfigure(0, weight=1)
        self._var_sl_breath = tk.BooleanVar(value=False)
        self._var_sl_light_zoom = tk.BooleanVar(value=False)
        self._var_sl_vignette = tk.BooleanVar(value=False)
        self._var_sl_color_shift = tk.BooleanVar(value=False)
        fxr = 0

        # Fade respiración
        fxr = self._check_row(_fx_inner, "Fade respiración (brillo)", self._var_sl_breath, fxr)
        self._sl_breath_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._sl_breath_frame.grid(row=fxr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._sl_breath_frame.grid_columnconfigure(0, weight=1)
        self._var_sl_breath_intensity = tk.DoubleVar(value=0.04)
        self._var_sl_breath_speed = tk.DoubleVar(value=1.0)
        sbr = 0
        sbr = self._slider_row(self._sl_breath_frame, "Intensidad:",
                               self._var_sl_breath_intensity, 0.01, 0.08, sbr, fmt="{:.3f}", number_of_steps=70, pct=True)
        sbr = self._slider_row(self._sl_breath_frame, "Velocidad:",
                               self._var_sl_breath_speed, 0.1, 2.0, sbr, fmt="{:.1f}", number_of_steps=19, pct=True)
        self._sl_breath_frame.grid_remove()
        self._var_sl_breath.trace_add("write", lambda *_: (
            self._sl_breath_frame.grid() if self._var_sl_breath.get()
            else self._sl_breath_frame.grid_remove()
        ))
        fxr += 1

        # Zoom ligero
        fxr = self._check_row(_fx_inner, "Zoom ligero (crop)", self._var_sl_light_zoom, fxr)
        self._sl_light_zoom_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._sl_light_zoom_frame.grid(row=fxr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._sl_light_zoom_frame.grid_columnconfigure(0, weight=1)
        self._var_sl_light_zoom_max = tk.DoubleVar(value=1.04)
        self._var_sl_light_zoom_speed = tk.DoubleVar(value=0.5)
        slzr = 0
        slzr = self._slider_row(self._sl_light_zoom_frame, "Zoom máx:",
                               self._var_sl_light_zoom_max, 1.01, 1.08, slzr, fmt="{:.3f}", number_of_steps=70, pct=True)
        slzr = self._slider_row(self._sl_light_zoom_frame, "Velocidad:",
                               self._var_sl_light_zoom_speed, 0.1, 1.5, slzr, fmt="{:.1f}", number_of_steps=14, pct=True)
        self._sl_light_zoom_frame.grid_remove()
        self._var_sl_light_zoom.trace_add("write", lambda *_: (
            self._sl_light_zoom_frame.grid() if self._var_sl_light_zoom.get()
            else self._sl_light_zoom_frame.grid_remove()
        ))
        fxr += 1

        # Viñeta
        fxr = self._check_row(_fx_inner, "Viñeta (bordes)", self._var_sl_vignette, fxr)
        self._sl_vignette_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._sl_vignette_frame.grid(row=fxr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._sl_vignette_frame.grid_columnconfigure(0, weight=1)
        self._var_sl_vignette_intensity = tk.DoubleVar(value=0.4)
        svr = 0
        svr = self._slider_row(self._sl_vignette_frame, "Intensidad:",
                               self._var_sl_vignette_intensity, 0.0, 1.0, svr, fmt="{:.1f}", number_of_steps=100, pct=True)
        self._sl_vignette_frame.grid_remove()
        self._var_sl_vignette.trace_add("write", lambda *_: (
            self._sl_vignette_frame.grid() if self._var_sl_vignette.get()
            else self._sl_vignette_frame.grid_remove()
        ))
        fxr += 1

        # Color shift
        fxr = self._check_row(_fx_inner, "Color shift (hue)", self._var_sl_color_shift, fxr)
        self._sl_color_shift_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._sl_color_shift_frame.grid(row=fxr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._sl_color_shift_frame.grid_columnconfigure(0, weight=1)
        self._var_sl_color_shift_amount = tk.DoubleVar(value=15.0)
        self._var_sl_color_shift_speed = tk.DoubleVar(value=0.5)
        scsr = 0
        scsr = self._slider_row(self._sl_color_shift_frame, "Cantidad (°):",
                               self._var_sl_color_shift_amount, 1.0, 45.0, scsr, fmt="{:.0f}", pct=True)
        scsr = self._slider_row(self._sl_color_shift_frame, "Velocidad:",
                               self._var_sl_color_shift_speed, 0.1, 2.0, scsr, fmt="{:.1f}", number_of_steps=19, pct=True)
        self._sl_color_shift_frame.grid_remove()
        self._var_sl_color_shift.trace_add("write", lambda *_: (
            self._sl_color_shift_frame.grid() if self._var_sl_color_shift.get()
            else self._sl_color_shift_frame.grid_remove()
        ))
        fxr += 1
        sqr += 1

        # --- Texto overlay (Slideshow) ---
        _sl_sec_txt = ctk.CTkFrame(sqf, fg_color=C_CARD, corner_radius=10,
                                   border_width=1, border_color=C_BORDER)
        _sl_sec_txt.grid(row=sqr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sl_sec_txt.grid_columnconfigure(0, weight=1)
        self._section_header(_sl_sec_txt, "Texto overlay").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _sl_txt_inner = ctk.CTkFrame(_sl_sec_txt, fg_color="transparent")
        _sl_txt_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _sl_txt_inner.grid_columnconfigure(0, weight=1)

        self._var_sl_text_overlay = tk.BooleanVar(value=False)
        sl_tr = self._check_row(_sl_txt_inner, "Activar texto overlay estático",
                                self._var_sl_text_overlay, 0,
                                command=self._sl_toggle_text_overlay_widgets)
        self._sl_text_overlay_frame = ctk.CTkFrame(
            _sl_txt_inner, fg_color=C_PANEL, corner_radius=6,
            border_width=1, border_color=C_BORDER,
        )
        self._sl_text_overlay_frame.grid(row=sl_tr, column=0, sticky="ew", padx=12, pady=(16, 4))
        self._sl_text_overlay_frame.grid_columnconfigure(0, weight=1)
        sl_tof = 0

        ctk.CTkLabel(self._sl_text_overlay_frame, text="Texto:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), anchor="w").grid(
            row=sl_tof, column=0, sticky="w", padx=10, pady=(8, 0))
        sl_tof += 1
        self._var_sl_text_content = tk.StringVar()
        ctk.CTkEntry(self._sl_text_overlay_frame, textvariable=self._var_sl_text_content,
                     placeholder_text="Ej: Lo-Fi Beats ?", height=28).grid(
            row=sl_tof, column=0, sticky="ew", padx=10, pady=(2, 6))
        sl_tof += 1

        _sl_font_f = ctk.CTkFrame(self._sl_text_overlay_frame, fg_color="transparent")
        _sl_font_f.grid(row=sl_tof, column=0, sticky="ew", padx=10, pady=2)
        _sl_font_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_font_f, text="Fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        _sl_fonts = available_fonts() or ["Arial"]
        self._var_sl_text_font = tk.StringVar(value=_sl_fonts[0])
        ctk.CTkOptionMenu(_sl_font_f, variable=self._var_sl_text_font, values=_sl_fonts,
                          width=160, height=28,
                          font=ctk.CTkFont(size=self._fs(11))).grid(row=0, column=1, sticky="w", padx=4)
        sl_tof += 1

        _sl_col_f = ctk.CTkFrame(self._sl_text_overlay_frame, fg_color="transparent")
        _sl_col_f.grid(row=sl_tof, column=0, sticky="ew", padx=10, pady=2)
        _sl_col_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_col_f, text="Color:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        self._var_sl_text_color = tk.StringVar(value="Blanco")
        self._sl_text_color_preview = ctk.CTkLabel(
            _sl_col_f, text="", width=16, height=16, corner_radius=8, fg_color="#FFFFFF")
        self._sl_text_color_preview.grid(row=0, column=2, padx=(6, 0))
        _sl_color_hex_map = {
            "Blanco": "#FFFFFF", "Gris claro": "#D0D0D0",
            "Gris": "#808080", "Gris oscuro": "#404040", "Negro": "#000000",
        }
        def _sl_update_color_preview(name: str) -> None:
            self._sl_text_color_preview.configure(fg_color=_sl_color_hex_map.get(name, "#FFFFFF"))
        ctk.CTkOptionMenu(_sl_col_f, variable=self._var_sl_text_color,
                          values=list(_sl_color_hex_map.keys()), width=140, height=28,
                          command=_sl_update_color_preview,
                          font=ctk.CTkFont(size=self._fs(11))).grid(row=0, column=1, sticky="w", padx=4)
        sl_tof += 1

        _sl_pos_f = ctk.CTkFrame(self._sl_text_overlay_frame, fg_color="transparent")
        _sl_pos_f.grid(row=sl_tof, column=0, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(_sl_pos_f, text="Posición:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").pack(side="left")
        self._var_sl_text_position = tk.StringVar(value="Bottom")
        for _pos in ("Top", "Middle", "Bottom"):
            ctk.CTkRadioButton(_sl_pos_f, text=_pos, variable=self._var_sl_text_position,
                               value=_pos, font=ctk.CTkFont(size=self._fs(11))).pack(side="left", padx=6)
        sl_tof += 1

        _sl_m_f = ctk.CTkFrame(self._sl_text_overlay_frame, fg_color="transparent")
        _sl_m_f.grid(row=sl_tof, column=0, sticky="ew", padx=10, pady=2)
        _sl_m_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_m_f, text="Margen (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sl_text_margin = tk.IntVar(value=40)
        _sl_m_lbl = ctk.CTkLabel(_sl_m_f, text=_val_to_pct(40, 10, 120), text_color=C_TEXT,
                                 font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sl_m_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sl_m_f, from_=10, to=120, variable=self._var_sl_text_margin,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sl_m_lbl.configure(text=_val_to_pct(float(v), 10, 120))).grid(
            row=0, column=1, sticky="ew", padx=4)
        sl_tof += 1

        _sl_fs_f = ctk.CTkFrame(self._sl_text_overlay_frame, fg_color="transparent")
        _sl_fs_f.grid(row=sl_tof, column=0, sticky="ew", padx=10, pady=2)
        _sl_fs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_fs_f, text="Tamaño fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sl_text_font_size = tk.IntVar(value=36)
        _sl_fs_lbl = ctk.CTkLabel(_sl_fs_f, text=_val_to_pct(36, 12, 72), text_color=C_TEXT,
                                  font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sl_fs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sl_fs_f, from_=12, to=72, variable=self._var_sl_text_font_size,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sl_fs_lbl.configure(text=_val_to_pct(float(v), 12, 72))).grid(
            row=0, column=1, sticky="ew", padx=4)
        sl_tof += 1

        _sl_gi_f = ctk.CTkFrame(self._sl_text_overlay_frame, fg_color="transparent")
        _sl_gi_f.grid(row=sl_tof, column=0, sticky="ew", padx=10, pady=2)
        _sl_gi_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_gi_f, text="Glitch (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sl_text_glitch_intensity = tk.IntVar(value=3)
        _sl_gi_lbl = ctk.CTkLabel(_sl_gi_f, text=_val_to_pct(3, 0, 10), text_color=C_TEXT,
                                  font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sl_gi_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sl_gi_f, from_=0, to=10, variable=self._var_sl_text_glitch_intensity,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sl_gi_lbl.configure(text=_val_to_pct(float(v), 0, 10))).grid(
            row=0, column=1, sticky="ew", padx=4)
        sl_tof += 1

        _sl_gs_f = ctk.CTkFrame(self._sl_text_overlay_frame, fg_color="transparent")
        _sl_gs_f.grid(row=sl_tof, column=0, sticky="ew", padx=10, pady=(2, 8))
        _sl_gs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_gs_f, text="Velocidad glitch:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sl_text_glitch_speed = tk.DoubleVar(value=4.0)
        _sl_gs_lbl = ctk.CTkLabel(_sl_gs_f, text=_val_to_pct(4.0, 0.5, 12.0), text_color=C_TEXT,
                                  font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sl_gs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sl_gs_f, from_=0.5, to=12.0, variable=self._var_sl_text_glitch_speed,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sl_gs_lbl.configure(text=_val_to_pct(float(v), 0.5, 12.0))).grid(
            row=0, column=1, sticky="ew", padx=4)
        self._sl_text_overlay_frame.grid_remove()

        # --- Texto overlay DINÁMICO (Slideshow) ---
        self._var_sl_dyn_text_overlay = tk.BooleanVar(value=False)
        sl_dyn_tr = sl_tr + 1
        sl_dyn_tr = self._check_row(_sl_txt_inner, "Activar texto overlay dinámico",
                                    self._var_sl_dyn_text_overlay, sl_dyn_tr,
                                    command=self._sl_toggle_dyn_text_overlay_widgets)
        self._sl_dyn_text_overlay_frame = ctk.CTkFrame(
            _sl_txt_inner, fg_color=C_PANEL, corner_radius=6,
            border_width=1, border_color=C_BORDER,
        )
        self._sl_dyn_text_overlay_frame.grid(row=sl_dyn_tr, column=0, sticky="ew", padx=12, pady=(4, 16))
        self._sl_dyn_text_overlay_frame.grid_columnconfigure(0, weight=1)
        sl_dtof = 0

        _sl_dyn_mode_f = ctk.CTkFrame(self._sl_dyn_text_overlay_frame, fg_color="transparent")
        _sl_dyn_mode_f.grid(row=sl_dtof, column=0, sticky="ew", padx=10, pady=(8, 4))
        _sl_dyn_mode_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_dyn_mode_f, text="Fuente del texto:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        _SL_DYN_MODES = ["Texto fijo", "Nombre de canción", "Prefijo + Nombre de canción"]
        self._var_sl_dyn_text_mode = tk.StringVar(value="Texto fijo")
        ctk.CTkOptionMenu(
            _sl_dyn_mode_f, variable=self._var_sl_dyn_text_mode, values=_SL_DYN_MODES,
            width=210, height=28, font=ctk.CTkFont(size=self._fs(11)),
            command=lambda _: self._on_sl_dyn_text_mode_change(),
        ).grid(row=0, column=1, sticky="w", padx=4)
        sl_dtof += 1

        self._sl_dyn_text_fixed_frame = ctk.CTkFrame(self._sl_dyn_text_overlay_frame, fg_color="transparent")
        self._sl_dyn_text_fixed_frame.grid(row=sl_dtof, column=0, sticky="ew", padx=10, pady=(0, 2))
        self._sl_dyn_text_fixed_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self._sl_dyn_text_fixed_frame, text="Texto:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), anchor="w").grid(
            row=0, column=0, sticky="w", pady=(4, 0))
        self._var_sl_dyn_text_content = tk.StringVar()
        ctk.CTkEntry(self._sl_dyn_text_fixed_frame, textvariable=self._var_sl_dyn_text_content,
                     placeholder_text="Ej: Lo-Fi Beats ?", height=28).grid(
            row=1, column=0, sticky="ew", pady=(2, 4))
        sl_dtof += 1

        _sl_dyn_font_f = ctk.CTkFrame(self._sl_dyn_text_overlay_frame, fg_color="transparent")
        _sl_dyn_font_f.grid(row=sl_dtof, column=0, sticky="ew", padx=10, pady=2)
        _sl_dyn_font_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_dyn_font_f, text="Fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        _sl_dyn_fonts = available_fonts() or ["Arial"]
        self._var_sl_dyn_text_font = tk.StringVar(value=_sl_dyn_fonts[0])
        ctk.CTkOptionMenu(_sl_dyn_font_f, variable=self._var_sl_dyn_text_font, values=_sl_dyn_fonts,
                          width=160, height=28,
                          font=ctk.CTkFont(size=self._fs(11))).grid(row=0, column=1, sticky="w", padx=4)
        sl_dtof += 1

        _sl_dyn_col_f = ctk.CTkFrame(self._sl_dyn_text_overlay_frame, fg_color="transparent")
        _sl_dyn_col_f.grid(row=sl_dtof, column=0, sticky="ew", padx=10, pady=2)
        _sl_dyn_col_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_dyn_col_f, text="Color:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        self._var_sl_dyn_text_color = tk.StringVar(value="Blanco")
        self._sl_dyn_text_color_preview = ctk.CTkLabel(
            _sl_dyn_col_f, text="", width=16, height=16, corner_radius=8, fg_color="#FFFFFF")
        self._sl_dyn_text_color_preview.grid(row=0, column=2, padx=(6, 0))
        def _sl_dyn_upd_color(name: str) -> None:
            self._sl_dyn_text_color_preview.configure(fg_color=_sl_color_hex_map.get(name, "#FFFFFF"))
        ctk.CTkOptionMenu(_sl_dyn_col_f, variable=self._var_sl_dyn_text_color,
                          values=list(_sl_color_hex_map.keys()), width=140, height=28,
                          command=_sl_dyn_upd_color,
                          font=ctk.CTkFont(size=self._fs(11))).grid(row=0, column=1, sticky="w", padx=4)
        sl_dtof += 1

        _sl_dyn_pos_f = ctk.CTkFrame(self._sl_dyn_text_overlay_frame, fg_color="transparent")
        _sl_dyn_pos_f.grid(row=sl_dtof, column=0, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(_sl_dyn_pos_f, text="Posición:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").pack(side="left")
        self._var_sl_dyn_text_position = tk.StringVar(value="Top")
        for _pos in ("Top", "Middle", "Bottom"):
            ctk.CTkRadioButton(_sl_dyn_pos_f, text=_pos, variable=self._var_sl_dyn_text_position,
                               value=_pos, font=ctk.CTkFont(size=self._fs(11))).pack(side="left", padx=6)
        sl_dtof += 1

        _sl_dyn_m_f = ctk.CTkFrame(self._sl_dyn_text_overlay_frame, fg_color="transparent")
        _sl_dyn_m_f.grid(row=sl_dtof, column=0, sticky="ew", padx=10, pady=2)
        _sl_dyn_m_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_dyn_m_f, text="Margen (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sl_dyn_text_margin = tk.IntVar(value=40)
        _sl_dyn_m_lbl = ctk.CTkLabel(_sl_dyn_m_f, text=_val_to_pct(40, 10, 120), text_color=C_TEXT,
                                     font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sl_dyn_m_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sl_dyn_m_f, from_=10, to=120, variable=self._var_sl_dyn_text_margin,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sl_dyn_m_lbl.configure(text=_val_to_pct(float(v), 10, 120))).grid(
            row=0, column=1, sticky="ew", padx=4)
        sl_dtof += 1

        _sl_dyn_fs_f = ctk.CTkFrame(self._sl_dyn_text_overlay_frame, fg_color="transparent")
        _sl_dyn_fs_f.grid(row=sl_dtof, column=0, sticky="ew", padx=10, pady=2)
        _sl_dyn_fs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_dyn_fs_f, text="Tamaño fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sl_dyn_text_font_size = tk.IntVar(value=36)
        _sl_dyn_fs_lbl = ctk.CTkLabel(_sl_dyn_fs_f, text=_val_to_pct(36, 12, 72), text_color=C_TEXT,
                                      font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sl_dyn_fs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sl_dyn_fs_f, from_=12, to=72, variable=self._var_sl_dyn_text_font_size,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sl_dyn_fs_lbl.configure(text=_val_to_pct(float(v), 12, 72))).grid(
            row=0, column=1, sticky="ew", padx=4)
        sl_dtof += 1

        _sl_dyn_gi_f = ctk.CTkFrame(self._sl_dyn_text_overlay_frame, fg_color="transparent")
        _sl_dyn_gi_f.grid(row=sl_dtof, column=0, sticky="ew", padx=10, pady=2)
        _sl_dyn_gi_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_dyn_gi_f, text="Glitch (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sl_dyn_text_glitch_intensity = tk.IntVar(value=3)
        _sl_dyn_gi_lbl = ctk.CTkLabel(_sl_dyn_gi_f, text=_val_to_pct(3, 0, 10), text_color=C_TEXT,
                                      font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sl_dyn_gi_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sl_dyn_gi_f, from_=0, to=10, variable=self._var_sl_dyn_text_glitch_intensity,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sl_dyn_gi_lbl.configure(text=_val_to_pct(float(v), 0, 10))).grid(
            row=0, column=1, sticky="ew", padx=4)
        sl_dtof += 1

        _sl_dyn_gs_f = ctk.CTkFrame(self._sl_dyn_text_overlay_frame, fg_color="transparent")
        _sl_dyn_gs_f.grid(row=sl_dtof, column=0, sticky="ew", padx=10, pady=(2, 8))
        _sl_dyn_gs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sl_dyn_gs_f, text="Velocidad glitch:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sl_dyn_text_glitch_speed = tk.DoubleVar(value=4.0)
        _sl_dyn_gs_lbl = ctk.CTkLabel(_sl_dyn_gs_f, text=_val_to_pct(4.0, 0.5, 12.0), text_color=C_TEXT,
                                      font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sl_dyn_gs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sl_dyn_gs_f, from_=0.5, to=12.0, variable=self._var_sl_dyn_text_glitch_speed,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sl_dyn_gs_lbl.configure(text=_val_to_pct(float(v), 0.5, 12.0))).grid(
            row=0, column=1, sticky="ew", padx=4)
        self._sl_dyn_text_overlay_frame.grid_remove()
        sqr += 1

        # --------------------------------------------------------------
        # TAB: RENDIMIENTO
        # --------------------------------------------------------------
        rf = ctk.CTkScrollableFrame(tab_rendimiento, fg_color="transparent")
        rf.pack(fill="both", expand=True, padx=16, pady=(8, 12))
        rf.grid_columnconfigure(0, weight=1)
        _init_scrollbar(rf)

        _sec_perf = ctk.CTkFrame(rf, fg_color=C_CARD, corner_radius=10,
                                 border_width=1, border_color=C_BORDER)
        _sec_perf.grid(row=0, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_perf.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_perf, "Rendimiento").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)

        _perf_inner = ctk.CTkFrame(_sec_perf, fg_color="transparent")
        _perf_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _perf_inner.grid_columnconfigure(0, weight=1)

        _cpu_inner = ctk.CTkFrame(_perf_inner, fg_color="transparent")
        _cpu_inner.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ctk.CTkLabel(_cpu_inner, text="CPU:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=80, anchor="w").pack(side="left")
        self._var_sl_cpu_mode = tk.StringVar(value="Medium")
        for _m in ("Low", "Medium", "High", "Max"):
            ctk.CTkRadioButton(
                _cpu_inner, text=_m, variable=self._var_sl_cpu_mode, value=_m,
                font=ctk.CTkFont(size=self._fs(11)), text_color=C_TEXT,
            ).pack(side="left", padx=4)

        _pre_inner = ctk.CTkFrame(_perf_inner, fg_color="transparent")
        _pre_inner.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        _pre_inner.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_pre_inner, text="Preset:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=80, anchor="w").grid(
            row=0, column=0, sticky="w")
        self._var_sl_encode_preset = tk.StringVar(value="slow")
        ctk.CTkComboBox(
            _pre_inner,
            values=["ultrafast", "superfast", "veryfast", "faster", "fast",
                    "medium", "slow", "slower", "veryslow"],
            variable=self._var_sl_encode_preset, state="readonly",
            fg_color=C_INPUT, button_color=C_ACCENT_SLIDE,
            border_color=C_BORDER, text_color=C_TEXT,
            font=ctk.CTkFont(size=self._fs(11)), height=30,
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))

        self._var_sl_crf = tk.IntVar(value=18)
        self._slider_row(_perf_inner, "Calidad (CRF):", self._var_sl_crf,
                         0, 51, 2, fmt="{:.0f}", pct=True,
                         tooltip_text="0=máxima calidad, 18=alta, 28=media, 51=mínima")

        self._var_sl_gpu_encoding = tk.BooleanVar(value=False)
        self._check_row(_perf_inner, "Usar GPU (NVENC)", self._var_sl_gpu_encoding, 3)

    def _build_shorts_left_panel(self, parent: ctk.CTkFrame) -> None:
        """Panel izquierdo del modo Shorts (separado, comparte panel derecho)."""
        panel, _tabs = self._make_tab_panel(
            parent,
            [("Config", "config"), ("Visual", "visual"), ("Salida", "salida")],
            accent=C_ACCENT_SHORTS,
        )
        panel.grid(row=0, column=0, sticky="nsew", padx=(0, 16))
        self._sho_scroll_frame = panel
        panel.grid_remove()  # hidden until mode is switched

        tab_config = _tabs["config"]
        tab_visual = _tabs["visual"]
        tab_salida = _tabs["salida"]

        # --------------------------------------------------------------
        # TAB: CONFIG
        # --------------------------------------------------------------
        cf = ctk.CTkScrollableFrame(tab_config, fg_color="transparent")
        cf.pack(fill="both", expand=True, padx=16, pady=(8, 12))
        cf.grid_columnconfigure(0, weight=1)
        _init_scrollbar(cf)
        cr = 0

        # --- Audio ---
        _sec_audio = ctk.CTkFrame(cf, fg_color=C_CARD, corner_radius=10,
                                  border_width=1, border_color=C_BORDER)
        _sec_audio.grid(row=cr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_audio.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_audio, "Audio").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _audio_inner = ctk.CTkFrame(_sec_audio, fg_color="transparent")
        _audio_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 12))
        _audio_inner.grid_columnconfigure(0, weight=1)
        self._var_sho_audio = tk.StringVar()
        self._file_row(_audio_inner, "Archivo de audio:", self._var_sho_audio,
                       self._sho_browse_audio, 0)
        self._sho_lbl_duration = ctk.CTkLabel(
            _audio_inner, text="Duración: —", text_color=C_MUTED,
            font=ctk.CTkFont(size=self._fs(11)), anchor="w",
        )
        self._sho_lbl_duration.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 4))
        self._var_sho_audio.trace_add("write", lambda *_: self._sho_on_audio_selected())
        cr += 1

        # --- Imágenes ---
        _sec_img = ctk.CTkFrame(cf, fg_color=C_CARD, corner_radius=10,
                                border_width=1, border_color=C_BORDER)
        _sec_img.grid(row=cr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_img.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_img, "Imagen de fondo").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _img_inner = ctk.CTkFrame(_sec_img, fg_color="transparent")
        _img_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 12))
        _img_inner.grid_columnconfigure(0, weight=1)
        self._var_sho_multi_image = tk.BooleanVar(value=False)
        _img_r = self._check_row(_img_inner, "Usar múltiples imágenes (rotar)",
                                 self._var_sho_multi_image, 0,
                                 command=self._sho_toggle_multi_image)
        # Single image wrapper
        self._sho_single_img_wrapper = ctk.CTkFrame(_img_inner, fg_color="transparent")
        self._sho_single_img_wrapper.grid(row=_img_r, column=0, sticky="ew")
        self._sho_single_img_wrapper.grid_columnconfigure(0, weight=1)
        self._var_sho_image = tk.StringVar()
        self._file_row(self._sho_single_img_wrapper, "Imagen:", self._var_sho_image,
                       self._sho_browse_image, 0)
        self._var_sho_image.trace_add("write", lambda *_: self._on_sho_image_change())
        # Multi image wrapper
        self._sho_multi_img_wrapper = ctk.CTkFrame(_img_inner, fg_color="transparent")
        self._sho_multi_img_wrapper.grid(row=_img_r, column=0, sticky="ew")
        self._sho_multi_img_wrapper.grid_columnconfigure(0, weight=1)
        self._var_sho_images_folder = tk.StringVar()
        self._file_row(self._sho_multi_img_wrapper, "Carpeta de imágenes:",
                       self._var_sho_images_folder,
                       self._sho_browse_images_folder, 0)
        self._sho_lbl_img_count = ctk.CTkLabel(
            self._sho_multi_img_wrapper, text="\u266b Imágenes: —",
            font=ctk.CTkFont(size=self._fs(11)), text_color=C_MUTED, anchor="w",
        )
        self._sho_lbl_img_count.grid(row=2, column=0, sticky="w", padx=14, pady=(0, 4))
        self._sho_multi_img_wrapper.grid_remove()
        cr += 1

        # --- Fragmentos ---
        _sec_frag = ctk.CTkFrame(cf, fg_color=C_CARD, corner_radius=10,
                                 border_width=1, border_color=C_BORDER)
        _sec_frag.grid(row=cr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_frag.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_frag, "Fragmentos").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _frag_inner = ctk.CTkFrame(_sec_frag, fg_color="transparent")
        _frag_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 12))
        _frag_inner.grid_columnconfigure(0, weight=1)
        self._var_sho_duration = tk.IntVar(value=45)
        self._slider_row(
            _frag_inner, "Duración por short:", self._var_sho_duration,
            30, 59, 0, fmt="{:.0f} s", number_of_steps=29,
            tooltip_text="Duración de cada short en segundos (30–59 s)",
        )
        self._var_sho_duration.trace_add("write", lambda *_: self._sho_update_fragment_suggestion())
        _qty_row = ctk.CTkFrame(_frag_inner, fg_color="transparent")
        _qty_row.grid(row=2, column=0, sticky="ew", padx=4, pady=(8, 4))
        _qty_row.grid_columnconfigure(2, weight=1)
        ctk.CTkLabel(_qty_row, text="Cantidad de shorts:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=140, anchor="w").grid(
            row=0, column=0, sticky="w")
        self._var_sho_quantity = tk.IntVar(value=3)
        ctk.CTkEntry(_qty_row, textvariable=self._var_sho_quantity,
                     width=64, height=28, justify="center").grid(
            row=0, column=1, padx=(8, 0))
        self._sho_lbl_suggestion = ctk.CTkLabel(
            _frag_inner, text="Sugerencia: —",
            font=ctk.CTkFont(size=self._fs(10)), text_color=C_MUTED, anchor="w",
        )
        self._sho_lbl_suggestion.grid(row=3, column=0, sticky="w", padx=8, pady=(2, 6))
        cr += 1

        # --------------------------------------------------------------
        # TAB: VISUAL
        # --------------------------------------------------------------
        vf = ctk.CTkScrollableFrame(tab_visual, fg_color="transparent")
        vf.pack(fill="both", expand=True, padx=16, pady=(8, 12))
        vf.grid_columnconfigure(0, weight=1)
        _init_scrollbar(vf)
        vr = 0

        # --- Resolución 9:16 ---
        _sec_res = ctk.CTkFrame(vf, fg_color=C_CARD, corner_radius=10,
                                border_width=1, border_color=C_BORDER)
        _sec_res.grid(row=vr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_res.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_res, "Resolución 9:16").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _res_inner = ctk.CTkFrame(_sec_res, fg_color="transparent")
        _res_inner.grid(row=1, column=0, sticky="ew", padx=16, pady=(16, 20))
        self._var_sho_resolution = tk.StringVar(value="1080p")
        for _res in ("720p", "1080p", "4K"):
            ctk.CTkRadioButton(
                _res_inner, text=_res,
                variable=self._var_sho_resolution, value=_res,
                fg_color=C_ACCENT_SHORTS,
                font=ctk.CTkFont(size=self._fs(11)), text_color=C_TEXT,
            ).pack(side="left", padx=6)
        vr += 1

        # --- Efectos visuales ---
        _sec_fx = ctk.CTkFrame(vf, fg_color=C_CARD, corner_radius=10,
                               border_width=1, border_color=C_BORDER)
        _sec_fx.grid(row=vr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_fx.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_fx, "Efectos visuales").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _fx_inner = ctk.CTkFrame(_sec_fx, fg_color="transparent")
        _fx_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _fx_inner.grid_columnconfigure(0, weight=1)

        self._var_sho_breath = tk.BooleanVar(value=False)
        self._var_sho_light_zoom = tk.BooleanVar(value=False)
        self._var_sho_vignette = tk.BooleanVar(value=False)
        self._var_sho_color_shift = tk.BooleanVar(value=False)
        fr = 0

        # Fade respiración
        fr = self._check_row(_fx_inner, "Fade respiración (brillo)", self._var_sho_breath, fr)
        self._sho_breath_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._sho_breath_frame.grid(row=fr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._sho_breath_frame.grid_columnconfigure(0, weight=1)
        self._var_sho_breath_intensity = tk.DoubleVar(value=0.04)
        self._var_sho_breath_speed = tk.DoubleVar(value=1.0)
        sbr = 0
        sbr = self._slider_row(self._sho_breath_frame, "Intensidad:",
                               self._var_sho_breath_intensity, 0.01, 0.08, sbr, fmt="{:.3f}", number_of_steps=70, pct=True)
        sbr = self._slider_row(self._sho_breath_frame, "Velocidad:",
                               self._var_sho_breath_speed, 0.1, 2.0, sbr, fmt="{:.1f}", number_of_steps=19, pct=True)
        self._sho_breath_frame.grid_remove()
        self._var_sho_breath.trace_add("write", lambda *_: (
            self._sho_breath_frame.grid() if self._var_sho_breath.get()
            else self._sho_breath_frame.grid_remove()
        ))
        fr += 1

        # Zoom ligero
        fr = self._check_row(_fx_inner, "Zoom ligero (crop)", self._var_sho_light_zoom, fr)
        self._sho_light_zoom_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._sho_light_zoom_frame.grid(row=fr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._sho_light_zoom_frame.grid_columnconfigure(0, weight=1)
        self._var_sho_light_zoom_max = tk.DoubleVar(value=1.04)
        self._var_sho_light_zoom_speed = tk.DoubleVar(value=0.5)
        slzr = 0
        slzr = self._slider_row(self._sho_light_zoom_frame, "Zoom máx:",
                               self._var_sho_light_zoom_max, 1.01, 1.08, slzr, fmt="{:.3f}", number_of_steps=70, pct=True)
        slzr = self._slider_row(self._sho_light_zoom_frame, "Velocidad:",
                               self._var_sho_light_zoom_speed, 0.1, 1.5, slzr, fmt="{:.1f}", number_of_steps=14, pct=True)
        self._sho_light_zoom_frame.grid_remove()
        self._var_sho_light_zoom.trace_add("write", lambda *_: (
            self._sho_light_zoom_frame.grid() if self._var_sho_light_zoom.get()
            else self._sho_light_zoom_frame.grid_remove()
        ))
        fr += 1

        # Viñeta
        fr = self._check_row(_fx_inner, "Viñeta (bordes)", self._var_sho_vignette, fr)
        self._sho_vignette_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._sho_vignette_frame.grid(row=fr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._sho_vignette_frame.grid_columnconfigure(0, weight=1)
        self._var_sho_vignette_intensity = tk.DoubleVar(value=0.4)
        svr = 0
        svr = self._slider_row(self._sho_vignette_frame, "Intensidad:",
                               self._var_sho_vignette_intensity, 0.0, 1.0, svr, fmt="{:.1f}", number_of_steps=100, pct=True)
        self._sho_vignette_frame.grid_remove()
        self._var_sho_vignette.trace_add("write", lambda *_: (
            self._sho_vignette_frame.grid() if self._var_sho_vignette.get()
            else self._sho_vignette_frame.grid_remove()
        ))
        fr += 1

        # Color shift
        fr = self._check_row(_fx_inner, "Color shift (hue)", self._var_sho_color_shift, fr)
        self._sho_color_shift_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._sho_color_shift_frame.grid(row=fr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._sho_color_shift_frame.grid_columnconfigure(0, weight=1)
        self._var_sho_color_shift_amount = tk.DoubleVar(value=15.0)
        self._var_sho_color_shift_speed = tk.DoubleVar(value=0.5)
        scsr = 0
        scsr = self._slider_row(self._sho_color_shift_frame, "Cantidad (°):",
                               self._var_sho_color_shift_amount, 1.0, 45.0, scsr, fmt="{:.0f}", pct=True)
        scsr = self._slider_row(self._sho_color_shift_frame, "Velocidad:",
                               self._var_sho_color_shift_speed, 0.1, 2.0, scsr, fmt="{:.1f}", number_of_steps=19, pct=True)
        self._sho_color_shift_frame.grid_remove()
        self._var_sho_color_shift.trace_add("write", lambda *_: (
            self._sho_color_shift_frame.grid() if self._var_sho_color_shift.get()
            else self._sho_color_shift_frame.grid_remove()
        ))
        fr += 1

        self._var_sho_glitch = tk.BooleanVar(value=False)
        fr = self._check_row(_fx_inner, "Glitch effect (video)", self._var_sho_glitch, fr)
        self._sho_glitch_frame = ctk.CTkFrame(_fx_inner, fg_color="transparent")
        self._sho_glitch_frame.grid(row=fr, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._sho_glitch_frame.grid_columnconfigure(0, weight=1)
        self._var_sho_glitch_intensity = tk.IntVar(value=4)
        self._var_sho_glitch_speed_fx = tk.IntVar(value=90)
        self._var_sho_glitch_pulse = tk.IntVar(value=3)
        gr = 0
        gr = self._slider_row(self._sho_glitch_frame, "Intensidad:",
                              self._var_sho_glitch_intensity, 1, 10, gr, fmt="{:.0f}", pct=True)
        gr = self._slider_row(self._sho_glitch_frame, "Frecuencia (frames):",
                              self._var_sho_glitch_speed_fx, 20, 180, gr, fmt="{:.0f}", pct=True)
        self._slider_row(self._sho_glitch_frame, "Duración pulso:",
                         self._var_sho_glitch_pulse, 1, 6, gr, fmt="{:.0f}", pct=True)
        if not self._var_sho_glitch.get():
            self._sho_glitch_frame.grid_remove()
        self._var_sho_glitch.trace_add("write", lambda *_: (
            self._sho_glitch_frame.grid() if self._var_sho_glitch.get()
            else self._sho_glitch_frame.grid_remove()
        ))
        fr += 1

        self._var_sho_normalize = tk.BooleanVar(value=False)
        self._check_row(_fx_inner, "Normalizar audio", self._var_sho_normalize, fr)
        vr += 1

        # --- Texto overlay ---
        _sec_txt = ctk.CTkFrame(vf, fg_color=C_CARD, corner_radius=10,
                                border_width=1, border_color=C_BORDER)
        _sec_txt.grid(row=vr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_txt.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_txt, "Texto overlay").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _txt_inner = ctk.CTkFrame(_sec_txt, fg_color="transparent")
        _txt_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _txt_inner.grid_columnconfigure(0, weight=1)

        self._var_sho_text_overlay = tk.BooleanVar(value=False)
        txt_r = self._check_row(_txt_inner, "Activar texto overlay estático",
                                self._var_sho_text_overlay, 0,
                                command=self._sho_toggle_text_overlay)
        self._sho_text_overlay_frame = ctk.CTkFrame(
            _txt_inner, fg_color=C_PANEL, corner_radius=6,
            border_width=1, border_color=C_BORDER,
        )
        self._sho_text_overlay_frame.grid(row=txt_r, column=0, sticky="ew",
                                          padx=12, pady=(16, 20))
        self._sho_text_overlay_frame.grid_columnconfigure(0, weight=1)
        tof = 0

        ctk.CTkLabel(self._sho_text_overlay_frame, text="Texto:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), anchor="w").grid(
            row=tof, column=0, sticky="w", padx=10, pady=(8, 0))
        tof += 1
        self._var_sho_text_content = tk.StringVar()
        ctk.CTkEntry(self._sho_text_overlay_frame, textvariable=self._var_sho_text_content,
                     placeholder_text="Ej: Lo-Fi Beats \u266a", height=28).grid(
            row=tof, column=0, sticky="ew", padx=10, pady=(2, 6))
        tof += 1

        _font_f = ctk.CTkFrame(self._sho_text_overlay_frame, fg_color="transparent")
        _font_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        _font_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_font_f, text="Fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        _sho_fonts = available_fonts() or ["Arial"]
        self._var_sho_text_font = tk.StringVar(value=_sho_fonts[0])
        ctk.CTkOptionMenu(_font_f, variable=self._var_sho_text_font, values=_sho_fonts,
                          width=160, height=28,
                          font=ctk.CTkFont(size=self._fs(11))).grid(
            row=0, column=1, sticky="w", padx=4)
        tof += 1

        _col_f = ctk.CTkFrame(self._sho_text_overlay_frame, fg_color="transparent")
        _col_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        _col_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_col_f, text="Color:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        self._var_sho_text_color = tk.StringVar(value="Blanco")
        self._sho_text_color_preview = ctk.CTkLabel(
            _col_f, text="", width=16, height=16, corner_radius=8, fg_color="#FFFFFF")
        self._sho_text_color_preview.grid(row=0, column=2, padx=(6, 0))
        _sho_color_hex = {
            "Blanco": "#FFFFFF", "Gris claro": "#D0D0D0",
            "Gris": "#808080", "Gris oscuro": "#404040", "Negro": "#000000",
        }
        def _sho_upd_color(name: str) -> None:
            self._sho_text_color_preview.configure(
                fg_color=_sho_color_hex.get(name, "#FFFFFF"))
        ctk.CTkOptionMenu(_col_f, variable=self._var_sho_text_color,
                          values=list(_sho_color_hex.keys()), width=140, height=28,
                          command=_sho_upd_color,
                          font=ctk.CTkFont(size=self._fs(11))).grid(
            row=0, column=1, sticky="w", padx=4)
        tof += 1

        _pos_f = ctk.CTkFrame(self._sho_text_overlay_frame, fg_color="transparent")
        _pos_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(_pos_f, text="Posición:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").pack(side="left")
        self._var_sho_text_position = tk.StringVar(value="Bottom")
        for _pos in ("Top", "Middle", "Bottom"):
            ctk.CTkRadioButton(_pos_f, text=_pos, variable=self._var_sho_text_position,
                               value=_pos, font=ctk.CTkFont(size=self._fs(11))).pack(
                side="left", padx=6)
        tof += 1

        _m_f = ctk.CTkFrame(self._sho_text_overlay_frame, fg_color="transparent")
        _m_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        _m_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_m_f, text="Margen (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sho_text_margin = tk.IntVar(value=40)
        _m_lbl = ctk.CTkLabel(_m_f, text=_val_to_pct(40, 10, 120), text_color=C_TEXT,
                              font=ctk.CTkFont(size=self._fs(11)), width=40)
        _m_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_m_f, from_=10, to=120, variable=self._var_sho_text_margin,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _m_lbl.configure(text=_val_to_pct(float(v), 10, 120))).grid(
            row=0, column=1, sticky="ew", padx=4)
        tof += 1

        _fsz_f = ctk.CTkFrame(self._sho_text_overlay_frame, fg_color="transparent")
        _fsz_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        _fsz_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_fsz_f, text="Tamaño fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sho_text_font_size = tk.IntVar(value=36)
        _fsz_lbl = ctk.CTkLabel(_fsz_f, text=_val_to_pct(36, 12, 72), text_color=C_TEXT,
                                font=ctk.CTkFont(size=self._fs(11)), width=40)
        _fsz_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_fsz_f, from_=12, to=72, variable=self._var_sho_text_font_size,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _fsz_lbl.configure(text=_val_to_pct(float(v), 12, 72))).grid(
            row=0, column=1, sticky="ew", padx=4)
        tof += 1

        _gi_f = ctk.CTkFrame(self._sho_text_overlay_frame, fg_color="transparent")
        _gi_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        _gi_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_gi_f, text="Glitch (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sho_text_glitch_intensity = tk.IntVar(value=3)
        _gi_lbl = ctk.CTkLabel(_gi_f, text=_val_to_pct(3, 0, 10), text_color=C_TEXT,
                               font=ctk.CTkFont(size=self._fs(11)), width=40)
        _gi_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_gi_f, from_=0, to=10, variable=self._var_sho_text_glitch_intensity,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _gi_lbl.configure(text=_val_to_pct(float(v), 0, 10))).grid(
            row=0, column=1, sticky="ew", padx=4)
        tof += 1

        _gs_f = ctk.CTkFrame(self._sho_text_overlay_frame, fg_color="transparent")
        _gs_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=(2, 8))
        _gs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_gs_f, text="Velocidad glitch:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sho_text_glitch_speed = tk.DoubleVar(value=4.0)
        _gs_lbl = ctk.CTkLabel(_gs_f, text=_val_to_pct(4.0, 0.5, 12.0), text_color=C_TEXT,
                               font=ctk.CTkFont(size=self._fs(11)), width=40)
        _gs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_gs_f, from_=0.5, to=12.0, variable=self._var_sho_text_glitch_speed,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _gs_lbl.configure(text=_val_to_pct(float(v), 0.5, 12.0))).grid(
            row=0, column=1, sticky="ew", padx=4)
        self._sho_text_overlay_frame.grid_remove()

        # --- Texto overlay DINÁMICO (Shorts) ---
        self._var_sho_dyn_text_overlay = tk.BooleanVar(value=False)
        sho_dyn_tr = txt_r + 1
        sho_dyn_tr = self._check_row(_txt_inner, "Activar texto overlay dinámico",
                                     self._var_sho_dyn_text_overlay, sho_dyn_tr,
                                     command=self._sho_toggle_dyn_text_overlay)
        self._sho_dyn_text_overlay_frame = ctk.CTkFrame(
            _txt_inner, fg_color=C_PANEL, corner_radius=6,
            border_width=1, border_color=C_BORDER,
        )
        self._sho_dyn_text_overlay_frame.grid(row=sho_dyn_tr, column=0, sticky="ew",
                                              padx=12, pady=(4, 16))
        self._sho_dyn_text_overlay_frame.grid_columnconfigure(0, weight=1)
        sho_dtof = 0

        _sho_dyn_mode_f = ctk.CTkFrame(self._sho_dyn_text_overlay_frame, fg_color="transparent")
        _sho_dyn_mode_f.grid(row=sho_dtof, column=0, sticky="ew", padx=10, pady=(8, 4))
        _sho_dyn_mode_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sho_dyn_mode_f, text="Fuente del texto:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        _SHO_DYN_MODES = ["Texto fijo", "Nombre de canción", "Prefijo + Nombre de canción"]
        self._var_sho_dyn_text_mode = tk.StringVar(value="Texto fijo")
        ctk.CTkOptionMenu(
            _sho_dyn_mode_f, variable=self._var_sho_dyn_text_mode, values=_SHO_DYN_MODES,
            width=210, height=28, font=ctk.CTkFont(size=self._fs(11)),
            command=lambda _: self._on_sho_dyn_text_mode_change(),
        ).grid(row=0, column=1, sticky="w", padx=4)
        sho_dtof += 1

        self._sho_dyn_text_fixed_frame = ctk.CTkFrame(self._sho_dyn_text_overlay_frame, fg_color="transparent")
        self._sho_dyn_text_fixed_frame.grid(row=sho_dtof, column=0, sticky="ew", padx=10, pady=(0, 2))
        self._sho_dyn_text_fixed_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self._sho_dyn_text_fixed_frame, text="Texto:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), anchor="w").grid(
            row=0, column=0, sticky="w", pady=(4, 0))
        self._var_sho_dyn_text_content = tk.StringVar()
        ctk.CTkEntry(self._sho_dyn_text_fixed_frame, textvariable=self._var_sho_dyn_text_content,
                     placeholder_text="Ej: Lo-Fi Beats ?", height=28).grid(
            row=1, column=0, sticky="ew", pady=(2, 4))
        sho_dtof += 1

        _sho_dyn_font_f = ctk.CTkFrame(self._sho_dyn_text_overlay_frame, fg_color="transparent")
        _sho_dyn_font_f.grid(row=sho_dtof, column=0, sticky="ew", padx=10, pady=2)
        _sho_dyn_font_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sho_dyn_font_f, text="Fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        _sho_dyn_fonts = available_fonts() or ["Arial"]
        self._var_sho_dyn_text_font = tk.StringVar(value=_sho_dyn_fonts[0])
        ctk.CTkOptionMenu(_sho_dyn_font_f, variable=self._var_sho_dyn_text_font, values=_sho_dyn_fonts,
                          width=160, height=28,
                          font=ctk.CTkFont(size=self._fs(11))).grid(row=0, column=1, sticky="w", padx=4)
        sho_dtof += 1

        _sho_dyn_col_f = ctk.CTkFrame(self._sho_dyn_text_overlay_frame, fg_color="transparent")
        _sho_dyn_col_f.grid(row=sho_dtof, column=0, sticky="ew", padx=10, pady=2)
        _sho_dyn_col_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sho_dyn_col_f, text="Color:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        self._var_sho_dyn_text_color = tk.StringVar(value="Blanco")
        self._sho_dyn_text_color_preview = ctk.CTkLabel(
            _sho_dyn_col_f, text="", width=16, height=16, corner_radius=8, fg_color="#FFFFFF")
        self._sho_dyn_text_color_preview.grid(row=0, column=2, padx=(6, 0))
        _sho_dyn_color_hex = {
            "Blanco": "#FFFFFF", "Gris claro": "#D0D0D0",
            "Gris": "#808080", "Gris oscuro": "#404040", "Negro": "#000000",
        }
        def _sho_dyn_upd_color(name: str) -> None:
            self._sho_dyn_text_color_preview.configure(
                fg_color=_sho_dyn_color_hex.get(name, "#FFFFFF"))
        ctk.CTkOptionMenu(_sho_dyn_col_f, variable=self._var_sho_dyn_text_color,
                          values=list(_sho_dyn_color_hex.keys()), width=140, height=28,
                          command=_sho_dyn_upd_color,
                          font=ctk.CTkFont(size=self._fs(11))).grid(row=0, column=1, sticky="w", padx=4)
        sho_dtof += 1

        _sho_dyn_pos_f = ctk.CTkFrame(self._sho_dyn_text_overlay_frame, fg_color="transparent")
        _sho_dyn_pos_f.grid(row=sho_dtof, column=0, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(_sho_dyn_pos_f, text="Posición:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").pack(side="left")
        self._var_sho_dyn_text_position = tk.StringVar(value="Top")
        for _pos in ("Top", "Middle", "Bottom"):
            ctk.CTkRadioButton(_sho_dyn_pos_f, text=_pos, variable=self._var_sho_dyn_text_position,
                               value=_pos, font=ctk.CTkFont(size=self._fs(11))).pack(side="left", padx=6)
        sho_dtof += 1

        _sho_dyn_m_f = ctk.CTkFrame(self._sho_dyn_text_overlay_frame, fg_color="transparent")
        _sho_dyn_m_f.grid(row=sho_dtof, column=0, sticky="ew", padx=10, pady=2)
        _sho_dyn_m_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sho_dyn_m_f, text="Margen (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sho_dyn_text_margin = tk.IntVar(value=40)
        _sho_dyn_m_lbl = ctk.CTkLabel(_sho_dyn_m_f, text=_val_to_pct(40, 10, 120), text_color=C_TEXT,
                                      font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sho_dyn_m_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sho_dyn_m_f, from_=10, to=120, variable=self._var_sho_dyn_text_margin,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sho_dyn_m_lbl.configure(text=_val_to_pct(float(v), 10, 120))).grid(
            row=0, column=1, sticky="ew", padx=4)
        sho_dtof += 1

        _sho_dyn_fs_f = ctk.CTkFrame(self._sho_dyn_text_overlay_frame, fg_color="transparent")
        _sho_dyn_fs_f.grid(row=sho_dtof, column=0, sticky="ew", padx=10, pady=2)
        _sho_dyn_fs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sho_dyn_fs_f, text="Tamaño fuente:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sho_dyn_text_font_size = tk.IntVar(value=36)
        _sho_dyn_fs_lbl = ctk.CTkLabel(_sho_dyn_fs_f, text=_val_to_pct(36, 12, 72), text_color=C_TEXT,
                                       font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sho_dyn_fs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sho_dyn_fs_f, from_=12, to=72, variable=self._var_sho_dyn_text_font_size,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sho_dyn_fs_lbl.configure(text=_val_to_pct(float(v), 12, 72))).grid(
            row=0, column=1, sticky="ew", padx=4)
        sho_dtof += 1

        _sho_dyn_gi_f = ctk.CTkFrame(self._sho_dyn_text_overlay_frame, fg_color="transparent")
        _sho_dyn_gi_f.grid(row=sho_dtof, column=0, sticky="ew", padx=10, pady=2)
        _sho_dyn_gi_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sho_dyn_gi_f, text="Glitch (px):", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sho_dyn_text_glitch_intensity = tk.IntVar(value=3)
        _sho_dyn_gi_lbl = ctk.CTkLabel(_sho_dyn_gi_f, text=_val_to_pct(3, 0, 10), text_color=C_TEXT,
                                       font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sho_dyn_gi_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sho_dyn_gi_f, from_=0, to=10, variable=self._var_sho_dyn_text_glitch_intensity,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sho_dyn_gi_lbl.configure(text=_val_to_pct(float(v), 0, 10))).grid(
            row=0, column=1, sticky="ew", padx=4)
        sho_dtof += 1

        _sho_dyn_gs_f = ctk.CTkFrame(self._sho_dyn_text_overlay_frame, fg_color="transparent")
        _sho_dyn_gs_f.grid(row=sho_dtof, column=0, sticky="ew", padx=10, pady=(2, 8))
        _sho_dyn_gs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_sho_dyn_gs_f, text="Velocidad glitch:", text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_sho_dyn_text_glitch_speed = tk.DoubleVar(value=4.0)
        _sho_dyn_gs_lbl = ctk.CTkLabel(_sho_dyn_gs_f, text=_val_to_pct(4.0, 0.5, 12.0), text_color=C_TEXT,
                                       font=ctk.CTkFont(size=self._fs(11)), width=40)
        _sho_dyn_gs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(_sho_dyn_gs_f, from_=0.5, to=12.0, variable=self._var_sho_dyn_text_glitch_speed,
                      fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
                      button_hover_color=C_ACCENT_H,
                      command=lambda v: _sho_dyn_gs_lbl.configure(text=_val_to_pct(float(v), 0.5, 12.0))).grid(
            row=0, column=1, sticky="ew", padx=4)
        self._sho_dyn_text_overlay_frame.grid_remove()

        # Traces to refresh preview when any Shorts text setting changes
        _sho_prev = lambda *_: (self._update_preview_overlay()
                                if getattr(self, "_current_mode", "") == "Shorts" else None)
        self._var_sho_text_content.trace_add("write", _sho_prev)
        self._var_sho_text_position.trace_add("write", _sho_prev)
        self._var_sho_text_color.trace_add("write", _sho_prev)
        self._var_sho_text_margin.trace_add("write", _sho_prev)
        self._var_sho_text_font_size.trace_add("write", _sho_prev)
        self._var_sho_text_font.trace_add("write", _sho_prev)
        self._var_sho_dyn_text_overlay.trace_add("write", _sho_prev)
        self._var_sho_dyn_text_content.trace_add("write", _sho_prev)
        self._var_sho_dyn_text_mode.trace_add("write", _sho_prev)
        self._var_sho_dyn_text_position.trace_add("write", _sho_prev)
        self._var_sho_dyn_text_margin.trace_add("write", _sho_prev)
        self._var_sho_dyn_text_font_size.trace_add("write", _sho_prev)
        self._var_sho_dyn_text_font.trace_add("write", _sho_prev)
        self._var_sho_dyn_text_color.trace_add("write", _sho_prev)
        vr += 1

        # --- Parámetros (fade) ---
        _sec_par_sho = ctk.CTkFrame(vf, fg_color=C_CARD, corner_radius=10,
                                    border_width=1, border_color=C_BORDER)
        _sec_par_sho.grid(row=vr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_par_sho.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_par_sho, "Parámetros").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _par_sho_inner = ctk.CTkFrame(_sec_par_sho, fg_color="transparent")
        _par_sho_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _par_sho_inner.grid_columnconfigure(0, weight=1)
        self._var_sho_fade_in = tk.DoubleVar(value=0.5)
        sho_pr = self._slider_row(_par_sho_inner, "Fade in (s):",
                                  self._var_sho_fade_in, 0, 5, 0, fmt="{:.1f}")
        self._var_sho_fade_out = tk.DoubleVar(value=0.5)
        self._slider_row(_par_sho_inner, "Fade out (s):",
                         self._var_sho_fade_out, 0, 5, sho_pr, fmt="{:.1f}")
        vr += 1

        # --------------------------------------------------------------
        # TAB: SALIDA
        # --------------------------------------------------------------
        xf = ctk.CTkScrollableFrame(tab_salida, fg_color="transparent")
        xf.pack(fill="both", expand=True, padx=16, pady=(8, 12))
        xf.grid_columnconfigure(0, weight=1)
        _init_scrollbar(xf)
        xr = 0

        # --- Naming ---
        _sec_name = ctk.CTkFrame(xf, fg_color=C_CARD, corner_radius=10,
                                 border_width=1, border_color=C_BORDER)
        _sec_name.grid(row=xr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_name.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_name, "Nombre de salida").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _nm_inner = ctk.CTkFrame(_sec_name, fg_color="transparent")
        _nm_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _nm_inner.grid_columnconfigure(0, weight=1)
        nr = 0

        _mode_row = ctk.CTkFrame(_nm_inner, fg_color="transparent")
        _mode_row.grid(row=nr, column=0, sticky="ew", padx=4, pady=4)
        _mode_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_mode_row, text="Modo:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=60, anchor="w",
                     ).grid(row=0, column=0, sticky="w")
        self._var_sho_naming_mode = tk.StringVar(value="Default")
        ctk.CTkOptionMenu(
            _mode_row,
            values=["Default", "Nombre", "Prefijo", "Lista personalizada",
                    "Prefijo + Lista personalizada"],
            variable=self._var_sho_naming_mode,
            command=self._on_sho_naming_mode_change,
            fg_color=C_CARD,
            button_color=C_ACCENT_SHORTS if self._current_theme == "Dark" else C_BORDER,
            text_color=C_TEXT,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        nr += 1

        self._sho_naming_name_frame = ctk.CTkFrame(_nm_inner, fg_color="transparent")
        self._sho_naming_name_frame.grid(row=nr, column=0, sticky="ew",
                                         padx=4, pady=(2, 0))
        self._sho_naming_name_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self._sho_naming_name_frame, text="Nombre:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=60, anchor="w",
                     ).grid(row=0, column=0, sticky="w")
        self._var_sho_naming_name = tk.StringVar()
        ctk.CTkEntry(self._sho_naming_name_frame,
                     textvariable=self._var_sho_naming_name,
                     placeholder_text="Ej: Short Chill", height=28,
                     ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._sho_naming_name_frame.grid_remove()
        nr += 1

        self._sho_naming_prefix_frame = ctk.CTkFrame(_nm_inner, fg_color="transparent")
        self._sho_naming_prefix_frame.grid(row=nr, column=0, sticky="ew",
                                           padx=4, pady=(2, 0))
        self._sho_naming_prefix_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self._sho_naming_prefix_frame, text="Prefijo:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=60, anchor="w",
                     ).grid(row=0, column=0, sticky="w")
        self._var_sho_naming_prefix = tk.StringVar()
        ctk.CTkEntry(self._sho_naming_prefix_frame,
                     textvariable=self._var_sho_naming_prefix,
                     placeholder_text="Ej: short - ", height=28,
                     ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._sho_naming_prefix_frame.grid_remove()
        nr += 1

        self._sho_naming_list_frame = ctk.CTkFrame(_nm_inner, fg_color="transparent")
        self._sho_naming_list_frame.grid(row=nr, column=0, sticky="ew",
                                         padx=4, pady=(4, 0))
        self._sho_naming_list_frame.grid_columnconfigure(0, weight=1)
        _nl_hdr = ctk.CTkFrame(self._sho_naming_list_frame, fg_color="transparent")
        _nl_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        _nl_hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(_nl_hdr, text="Nombres personalizados (uno por línea):",
                     text_color=C_MUTED, font=ctk.CTkFont(size=self._fs(11)), anchor="w",
                     ).grid(row=0, column=0, sticky="w")
        self._lbl_sho_names_count = ctk.CTkLabel(
            _nl_hdr, text="0 nombres", text_color=C_TEXT_DIM,
            font=ctk.CTkFont(size=self._fs(10)))
        self._lbl_sho_names_count.grid(row=0, column=1, sticky="e", padx=(4, 0))
        self._txt_sho_naming_list = ctk.CTkTextbox(
            self._sho_naming_list_frame, height=80, fg_color=C_INPUT,
            text_color=C_TEXT, font=ctk.CTkFont(family="Consolas", size=self._fs(11)))
        self._txt_sho_naming_list.grid(row=1, column=0, sticky="ew")
        self._txt_sho_naming_list.bind(
            "<KeyRelease>", lambda *_: self._refresh_sho_names_count())
        _btn_sho_names = ctk.CTkButton(
            self._sho_naming_list_frame, text="Ver / editar lista  \u25b6",
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, height=40,
            font=ctk.CTkFont(size=self._fs(11)),
            command=self._open_sho_names_list_dialog,
        )
        _btn_sho_names.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        _apply_sec_hover(_btn_sho_names)
        self._sho_naming_list_frame.grid_remove()
        nr += 1

        self._var_sho_naming_autonumber = tk.BooleanVar(value=True)
        self._cb_sho_naming_autonumber = ctk.CTkCheckBox(
            _nm_inner,
            text="Numeración automática (01, 02…)",
            variable=self._var_sho_naming_autonumber,
            font=ctk.CTkFont(size=self._fs(11)),
            text_color=C_TEXT,
            fg_color=C_ACCENT_SHORTS,
            hover_color=C_ACCENT_SHORTS_H,
            border_color=C_BORDER,
            checkmark_color="#ffffff",
        )
        self._cb_sho_naming_autonumber.grid(row=nr, column=0, sticky="w", padx=16, pady=(6, 6))
        xr += 1

        # --- Carpeta de salida ---
        _sec_out = ctk.CTkFrame(xf, fg_color=C_CARD, corner_radius=10,
                                border_width=1, border_color=C_BORDER)
        _sec_out.grid(row=xr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_out.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_out, "Carpeta de salida").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _out_inner = ctk.CTkFrame(_sec_out, fg_color="transparent")
        _out_inner.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 12))
        _out_inner.grid_columnconfigure(0, weight=1)
        self._var_sho_output_folder = tk.StringVar()
        self._file_row(_out_inner, "Carpeta de salida:", self._var_sho_output_folder,
                       self._sho_browse_output, 0)
        xr += 1

        # --- Rendimiento ---
        _sec_perf = ctk.CTkFrame(xf, fg_color=C_CARD, corner_radius=10,
                                 border_width=1, border_color=C_BORDER)
        _sec_perf.grid(row=xr, column=0, sticky="ew", padx=0, pady=(0, 16))
        _sec_perf.grid_columnconfigure(0, weight=1)
        self._section_header(_sec_perf, "Rendimiento").grid(
            row=0, column=0, sticky="ew", padx=0, pady=0)
        _perf_inner_sho = ctk.CTkFrame(_sec_perf, fg_color="transparent")
        _perf_inner_sho.grid(row=1, column=0, sticky="ew", padx=12, pady=(16, 20))
        _perf_inner_sho.grid_columnconfigure(0, weight=1)
        _cpu_r = ctk.CTkFrame(_perf_inner_sho, fg_color="transparent")
        _cpu_r.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ctk.CTkLabel(_cpu_r, text="CPU:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=80, anchor="w").pack(side="left")
        self._var_sho_cpu_mode = tk.StringVar(value="Medium")
        for _m in ("Low", "Medium", "High", "Max"):
            ctk.CTkRadioButton(
                _cpu_r, text=_m, variable=self._var_sho_cpu_mode, value=_m,
                font=ctk.CTkFont(size=self._fs(11)), text_color=C_TEXT,
            ).pack(side="left", padx=4)
        _pre_r = ctk.CTkFrame(_perf_inner_sho, fg_color="transparent")
        _pre_r.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        _pre_r.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(_pre_r, text="Preset:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=80, anchor="w").grid(
            row=0, column=0, sticky="w")
        self._var_sho_encode_preset = tk.StringVar(value="slow")
        ctk.CTkComboBox(
            _pre_r,
            values=["ultrafast", "superfast", "veryfast", "faster", "fast",
                    "medium", "slow", "slower", "veryslow"],
            variable=self._var_sho_encode_preset, state="readonly",
            fg_color=C_INPUT, button_color=C_ACCENT_SHORTS,
            border_color=C_BORDER, text_color=C_TEXT,
            font=ctk.CTkFont(size=self._fs(11)), height=30,
        ).grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self._var_sho_crf = tk.IntVar(value=18)
        self._slider_row(_perf_inner_sho, "Calidad (CRF):", self._var_sho_crf,
                         0, 51, 2, fmt="{:.0f}", pct=True,
                         tooltip_text="0=máxima calidad, 18=alta, 28=media, 51=mínima")
        self._var_sho_gpu_encoding = tk.BooleanVar(value=False)
        self._check_row(_perf_inner_sho, "Usar GPU (NVENC)", self._var_sho_gpu_encoding, 4)


    # --- YouTube Publisher left panel --------------------------------

    def _build_youtube_left_panel(self, parent: ctk.CTkFrame) -> None:
        """Panel izquierdo del modo YouTube Publisher (solo interfaz inicial)."""
        self._yt_scroll_frame = build_youtube_publisher_panel(
            self,
            parent,
            accent=C_ACCENT_YT,
            colors={
                "C_CARD": C_CARD,
                "C_BORDER": C_BORDER,
                "C_TEXT": C_TEXT,
                "C_TEXT_DIM": C_TEXT_DIM,
                "C_MUTED": C_MUTED,
                "C_HOVER": C_HOVER,
                "C_INPUT": C_INPUT,
            },
            icons={
                "FA_UPLOAD": FA_UPLOAD,
            },
        )
        self._yt_restore_channel_cache_from_settings()
        self._yt_restore_drafts_cache_from_settings()
        self._yt_restore_playlists_cache_from_settings()
        self._yt_render_queue_preview()

    def _build_prompt_lab_left_panel(self, parent: ctk.CTkFrame) -> None:
        """Panel izquierdo del modo Prompt Lab."""
        self._pl_scroll_frame = build_prompt_lab_panel(
            self,
            parent,
            accent=C_ACCENT_LAB,
            colors={
                "C_CARD": C_CARD,
                "C_BORDER": C_BORDER,
                "C_TEXT": C_TEXT,
                "C_TEXT_DIM": C_TEXT_DIM,
                "C_MUTED": C_MUTED,
                "C_HOVER": C_HOVER,
                "C_INPUT": C_INPUT,
            },
            icons={
                "FA_WAND": FA_WAND,
            },
        )
        self._pl_refresh_workspace_menu(select=self._var_pl_workspace.get())
        self._pl_refresh_available_models()
        self._pl_on_skill_selected()
        saved_prompt = self.settings.get("pl_prompt_text", "")
        if hasattr(self, "_txt_pl_prompt") and saved_prompt:
            self._txt_pl_prompt.delete("1.0", "end")
            self._txt_pl_prompt.insert("1.0", saved_prompt)

    def _pl_refresh_available_models(self) -> None:
        """Refresca los selectores de modelos usando los modelos instalados en Ollama."""
        quality_current = self._var_pl_model_quality.get().strip() if hasattr(self, "_var_pl_model_quality") else ""
        fast_current = self._var_pl_model_fast.get().strip() if hasattr(self, "_var_pl_model_fast") else ""

        defaults = [
            quality_current,
            fast_current,
            str(self.settings.get("pl_model_quality", "")).strip(),
            str(self.settings.get("pl_model_fast", "")).strip(),
            "llama3.1:8b",
            "llama3.2:3b",
        ]
        fallback_values: list[str] = []
        for value in defaults:
            if value and value not in fallback_values:
                fallback_values.append(value)

        base_url = "http://127.0.0.1:11434"
        if hasattr(self, "_var_pl_backend_url"):
            base_url = self._var_pl_backend_url.get().strip() or base_url
        else:
            base_url = str(self.settings.get("pl_backend_url", base_url) or base_url).strip()

        values: list[str] = []
        try:
            installed = list_installed_models_with_sizes(base_url)
            values = [str(item.get("name", "")).strip() for item in installed if str(item.get("name", "")).strip()]
        except Exception:
            values = []

        if not values:
            values = fallback_values

        if not values:
            values = ["llama3.1:8b", "llama3.2:3b"]

        # Mantener los actuales si existen; si no, escoger opciones razonables.
        if quality_current not in values:
            self._var_pl_model_quality.set(values[0])
            quality_current = values[0]
        if fast_current not in values:
            self._var_pl_model_fast.set(values[1] if len(values) > 1 else values[0])
            fast_current = self._var_pl_model_fast.get().strip()

        quality_display_values: list[str] = []
        fast_display_values: list[str] = []
        self._pl_quality_display_to_raw = {}
        self._pl_fast_display_to_raw = {}
        for raw in values:
            display = f"{raw} ({self._pl_model_weight_tag(raw)})"
            quality_display_values.append(display)
            fast_display_values.append(display)
            self._pl_quality_display_to_raw[display] = raw
            self._pl_fast_display_to_raw[display] = raw

        selected_quality_display = next(
            (d for d, r in self._pl_quality_display_to_raw.items() if r == quality_current),
            quality_display_values[0],
        )
        selected_fast_display = next(
            (d for d, r in self._pl_fast_display_to_raw.items() if r == fast_current),
            fast_display_values[1] if len(fast_display_values) > 1 else fast_display_values[0],
        )

        self._var_pl_model_quality_display.set(selected_quality_display)
        self._var_pl_model_fast_display.set(selected_fast_display)

        if hasattr(self, "_pl_quality_model_menu"):
            self._pl_quality_model_menu.configure(values=quality_display_values)
        if hasattr(self, "_pl_fast_model_menu"):
            self._pl_fast_model_menu.configure(values=fast_display_values)

        self._pl_update_model_hints()

    def _pl_model_weight_tag(self, model_name: str) -> str:
        name = (model_name or "").strip().lower()
        if not name:
            return "Sin clasificar"
        if ":1b" in name:
            return "Ligero"
        if ":2b" in name or ":3b" in name or ":4b" in name:
            return "Medio"
        if ":7b" in name or ":8b" in name or ":13b" in name:
            return "Pesado"
        return "Medio"

    def _pl_on_quality_model_selected(self, selected_display: str) -> None:
        raw = self._pl_quality_display_to_raw.get(selected_display, "")
        if not raw:
            raw = selected_display.split(" (", 1)[0].strip()
        if raw:
            self._var_pl_model_quality.set(raw)
        self._pl_update_model_hints()

    def _pl_on_fast_model_selected(self, selected_display: str) -> None:
        raw = self._pl_fast_display_to_raw.get(selected_display, "")
        if not raw:
            raw = selected_display.split(" (", 1)[0].strip()
        if raw:
            self._var_pl_model_fast.set(raw)
        self._pl_update_model_hints()

    def _pl_describe_model_tier(self, model_name: str) -> tuple[str, str]:
        name = (model_name or "").strip().lower()
        if not name:
            return ("SIN MODELO", "Selecciona un modelo para ver su perfil.")

        if ":1b" in name:
            return ("LIGERO", "Menor consumo de RAM, mas rapido, menor detalle.")
        if ":2b" in name or ":3b" in name or ":4b" in name:
            return ("BALANCEADO", "Buen equilibrio entre velocidad, RAM y calidad.")
        if ":7b" in name or ":8b" in name or ":13b" in name:
            return ("ALTA CALIDAD", "Mejor redaccion/consistencia, pero mas pesado.")
        return ("ESTANDAR", "Perfil intermedio. Si va lento, usa un modelo 1b o 3b.")

    def _pl_update_model_hints(self) -> None:
        if not hasattr(self, "_lbl_pl_model_hint"):
            return

        mode = self._var_pl_model_mode.get().strip() if hasattr(self, "_var_pl_model_mode") else "Calidad alta"
        quality = self._var_pl_model_quality.get().strip() if hasattr(self, "_var_pl_model_quality") else ""
        fast = self._var_pl_model_fast.get().strip() if hasattr(self, "_var_pl_model_fast") else ""

        quality_tier, quality_desc = self._pl_describe_model_tier(quality)
        fast_tier, fast_desc = self._pl_describe_model_tier(fast)

        active_line = (
            "Modo actual: CALIDAD ALTA (usa Modelo calidad)."
            if mode == "Calidad alta"
            else "Modo actual: RESPUESTA RAPIDA (usa Modelo rapido)."
        )

        text = (
            f"Modelo calidad: [{quality_tier}] {quality} - {quality_desc}\n"
            f"Modelo rapido: [{fast_tier}] {fast} - {fast_desc}\n"
            f"{active_line} Recomendado para equipos modestos: 1b o 3b en modo rapido."
        )
        self._lbl_pl_model_hint.configure(text=text)

    def _pl_refresh_workspace_menu(self, select: str = "") -> None:
        if not hasattr(self, "_pl_workspace_menu"):
            return
        values = self._prompt_lab.workspaces() or ["General"]
        self._pl_workspace_menu.configure(values=values)
        selected = select if select in values else values[0]
        self._var_pl_workspace.set(selected)
        self._pl_on_workspace_selected()

    def _pl_on_workspace_selected(self) -> None:
        if not hasattr(self, "_pl_category_menu"):
            return
        ws = self._var_pl_workspace.get().strip() or "General"
        categories = self._prompt_lab.categories(ws) or ["General"]
        self._pl_category_menu.configure(values=categories)
        current = self._var_pl_category.get().strip()
        if current not in categories:
            current = categories[0]
            self._var_pl_category.set(current)

        self._pl_on_category_selected()

    def _pl_build_preloaded_active_skills(self, ws: str, cat: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []

        def _append(category_name: str, skill_name: str) -> None:
            entry = {"category": category_name, "skill": skill_name}
            if entry not in out:
                out.append(entry)

        # Always preload at least one General skill.
        general_skills = self._prompt_lab.skills(ws, "General")
        general_preload = self._prompt_lab.category_preload_skills(ws, "General")
        if not general_preload and general_skills:
            general_preload = [general_skills[0]]
        for sk in general_preload:
            if sk in general_skills:
                _append("General", sk)

        # Preload selected category skills.
        cat_skills = self._prompt_lab.skills(ws, cat)
        cat_preload = self._prompt_lab.category_preload_skills(ws, cat)
        if not cat_preload and cat_skills:
            cat_preload = [cat_skills[0]]
        for sk in cat_preload:
            if sk in cat_skills:
                _append(cat, sk)

        return out

    def _pl_on_category_selected(self) -> None:
        ws = self._var_pl_workspace.get().strip() or "General"
        cat = self._var_pl_category.get().strip() or "General"
        skills = self._prompt_lab.skills(ws, cat) or ["Skill General"]

        changed_scope = (ws != self._pl_last_ws_for_preload) or (cat != self._pl_last_category_for_preload)
        self._pl_last_ws_for_preload = ws
        self._pl_last_category_for_preload = cat

        # Keep only valid skills from General + selected category.
        allowed = {"General", cat}
        filtered: list[dict[str, str]] = []
        for item in self._pl_active_skills:
            ac = str(item.get("category", "")).strip()
            an = str(item.get("skill", "")).strip()
            if not ac or not an or ac not in allowed:
                continue
            if an not in self._prompt_lab.skills(ws, ac):
                continue
            entry = {"category": ac, "skill": an}
            if entry not in filtered:
                filtered.append(entry)

        if changed_scope:
            filtered = self._pl_build_preloaded_active_skills(ws, cat)

        self._pl_active_skills = filtered

        current = self._var_pl_skill.get().strip()
        if current not in skills:
            current = skills[0]
            self._var_pl_skill.set(current)

        if not self._pl_active_skills:
            self._pl_active_skills = self._pl_build_preloaded_active_skills(ws, cat)
        if not self._pl_active_skills:
            self._pl_active_skills = [{"category": cat, "skill": current}]

        # Ensure selected skill exists in active list.
        found = False
        for item in self._pl_active_skills:
            if item.get("category") == cat and item.get("skill") == current:
                found = True
                break
        if not found:
            self._pl_active_skills.append({"category": cat, "skill": current})

        self._pl_refresh_applied_skills_label()
        self._pl_on_skill_selected()

    def _pl_refresh_applied_skills_label(self) -> None:
        self._pl_render_applied_skill_tiles()

    def _pl_render_applied_skill_tiles(self) -> None:
        container = getattr(self, "_pl_skill_tiles", None)
        if container is None:
            return
        for child in container.winfo_children():
            child.destroy()

        if not self._pl_active_skills:
            ctk.CTkLabel(
                container,
                text="No hay skills aplicadas.",
                text_color=C_TEXT_DIM,
                anchor="w",
                font=ctk.CTkFont(size=self._fs(10)),
            ).grid(row=0, column=0, sticky="ew", padx=10, pady=8)
            return

        for idx, item in enumerate(self._pl_active_skills):
            cat = str(item.get("category", "")).strip()
            sk = str(item.get("skill", "")).strip()
            tile = ctk.CTkFrame(
                container,
                fg_color=C_CARD,
                corner_radius=8,
                border_width=1,
                border_color=C_BORDER,
            )
            tile.grid(row=idx, column=0, sticky="ew", padx=8, pady=(6 if idx == 0 else 2, 4))
            tile.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                tile,
                text=f"{cat}:{sk}",
                text_color=C_TEXT,
                anchor="w",
                font=ctk.CTkFont(size=self._fs(10), weight="bold"),
            ).grid(row=0, column=0, sticky="w", padx=10, pady=7)

            ctk.CTkButton(
                tile,
                text="Ver",
                width=58,
                height=24,
                fg_color="transparent",
                hover_color=C_HOVER,
                border_width=1,
                border_color=C_BORDER,
                text_color=C_TEXT,
                font=ctk.CTkFont(size=self._fs(9)),
                command=lambda c=cat, s=sk: self._pl_open_skill_editor_modal(c, s),
            ).grid(row=0, column=1, padx=(6, 4), pady=6)

            ctk.CTkButton(
                tile,
                text="Quitar",
                width=64,
                height=24,
                fg_color="transparent",
                hover_color=C_HOVER,
                border_width=1,
                border_color=C_BORDER,
                text_color=C_TEXT_DIM,
                font=ctk.CTkFont(size=self._fs(9)),
                command=lambda c=cat, s=sk: self._pl_remove_active_skill(c, s),
            ).grid(row=0, column=2, padx=(0, 8), pady=6)

    def _pl_remove_active_skill(self, category: str, skill_name: str) -> None:
        kept = [
            item for item in self._pl_active_skills
            if not (
                str(item.get("category", "")).strip() == category
                and str(item.get("skill", "")).strip() == skill_name
            )
        ]
        if not kept:
            messagebox.showwarning("Prompt Lab", "Debe quedar al menos una skill aplicada.")
            return
        self._pl_active_skills = kept
        first = self._pl_active_skills[0]
        self._var_pl_category.set(str(first.get("category", "General")))
        self._var_pl_skill.set(str(first.get("skill", "Skill General")))
        self._pl_on_skill_selected()
        self._pl_refresh_applied_skills_label()

    def _pl_on_skill_selected(self) -> None:
        if not hasattr(self, "_lbl_pl_status"):
            self._pl_refresh_prompt_helper()
            return
        ws = self._var_pl_workspace.get().strip()
        cat = self._var_pl_category.get().strip()
        skill_name = self._var_pl_skill.get().strip()
        skill = self._prompt_lab.get_skill(ws, cat, skill_name)
        if skill:
            self._pl_set_status("Listo")
        else:
            self._pl_set_status("Skill sin instrucciones")
        self._pl_refresh_prompt_helper()

    def _pl_set_status(self, text: str, *, max_chars: int = 34) -> None:
        if not hasattr(self, "_lbl_pl_status"):
            return
        value = (text or "").strip()
        if len(value) > max_chars:
            value = value[: max_chars - 1].rstrip() + "..."
        self._lbl_pl_status.configure(text=value)

    def _pl_build_prompt_helper_for_skill(self, category: str, skill_name: str) -> tuple[str, str]:
        ws = self._var_pl_workspace.get().strip() if hasattr(self, "_var_pl_workspace") else "General"
        skill = self._prompt_lab.get_skill(ws, category, skill_name)
        if skill and skill.prompt_template.strip():
            return (
                "Plantilla personalizada de la skill lista para insertar.",
                skill.prompt_template.strip(),
            )

        return (
            "Esta skill no tiene plantilla. Editala y agrega una plantilla sugerida.",
            "",
        )

    def _pl_refresh_prompt_helper(self) -> None:
        has_label = hasattr(self, "_lbl_pl_prompt_helper")
        cat = self._var_pl_category.get().strip() if hasattr(self, "_var_pl_category") else "General"
        sk = self._var_pl_skill.get().strip() if hasattr(self, "_var_pl_skill") else "Skill General"
        previous_template = (self._pl_prompt_template_current or "").strip()
        helper, template = self._pl_build_prompt_helper_for_skill(cat, sk)
        self._pl_prompt_template_current = template

        # Clear stale auto-inserted template when switching to a different skill/category template.
        if hasattr(self, "_txt_pl_prompt"):
            current_prompt = self._txt_pl_prompt.get("1.0", "end").strip()
            last_inserted = (self._pl_last_inserted_template or "").strip()
            if (
                current_prompt
                and last_inserted
                and current_prompt == last_inserted
                and template.strip() != previous_template
            ):
                self._txt_pl_prompt.delete("1.0", "end")
                self._pl_last_inserted_template = ""

        if has_label:
            self._lbl_pl_prompt_helper.configure(text="Guia disponible: usa 'Insertar plantilla'")

    def _pl_template_category_key(self) -> str:
        ws = self._var_pl_workspace.get().strip() if hasattr(self, "_var_pl_workspace") else "General"
        cat = self._var_pl_category.get().strip() if hasattr(self, "_var_pl_category") else "General"
        return f"{ws}::{cat}"

    def _pl_collect_active_template_candidates(self) -> list[dict[str, str]]:
        ws = self._var_pl_workspace.get().strip() if hasattr(self, "_var_pl_workspace") else "General"
        out: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for item in self._pl_active_skills:
            cat = str(item.get("category", "")).strip()
            sk = str(item.get("skill", "")).strip()
            if not cat or not sk:
                continue
            key = (cat, sk)
            if key in seen:
                continue
            seen.add(key)
            skill = self._prompt_lab.get_skill(ws, cat, sk)
            if not skill:
                continue
            template = (skill.prompt_template or "").strip()
            if not template:
                continue
            out.append(
                {
                    "id": f"{cat}::{sk}",
                    "category": cat,
                    "skill": sk,
                    "template": template,
                }
            )
        return out

    def _pl_build_combined_template(self, candidates: list[dict[str, str]]) -> str:
        chunks: list[str] = []
        for item in candidates:
            cat = item.get("category", "").strip()
            sk = item.get("skill", "").strip()
            template = item.get("template", "").strip()
            if not template:
                continue
            chunks.append(f"[{cat}/{sk}]\n{template}")
        return "\n\n".join(chunks).strip()

    def _pl_pick_template_candidate(self, candidates: list[dict[str, str]]) -> tuple[str | None, bool]:
        modal = ctk.CTkToplevel(self)
        modal.title("Insertar plantilla")
        modal.geometry("740x500")
        modal.resizable(True, True)
        modal.configure(fg_color=C_BG)
        modal.grab_set()
        _center_window_on_screen(modal)

        root = ctk.CTkFrame(modal, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=16, pady=14)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            root,
            text="Hay multiples plantillas activas. Elige una skill o combina todas.",
            text_color=C_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=self._fs(12), weight="bold"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        choice_var = tk.StringVar(value=(candidates[0].get("id", "") if candidates else ""))
        remember_combine_var = tk.BooleanVar(value=False)

        box = ctk.CTkScrollableFrame(root, fg_color=C_CARD)
        box.grid(row=1, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1)

        for idx, item in enumerate(candidates):
            cid = item.get("id", "")
            label = f"Usar {item.get('category', '')}:{item.get('skill', '')}"
            ctk.CTkRadioButton(
                box,
                text=label,
                variable=choice_var,
                value=cid,
                fg_color=C_ACCENT_LAB,
                hover_color=C_ACCENT_LAB_H,
                text_color=C_TEXT,
                border_color=C_BORDER,
                font=ctk.CTkFont(size=self._fs(11)),
            ).grid(row=idx * 2, column=0, sticky="w", padx=10, pady=(8, 2))

            preview = item.get("template", "").replace("\n", " ")[:160].strip()
            ctk.CTkLabel(
                box,
                text=preview,
                text_color=C_TEXT_DIM,
                anchor="w",
                justify="left",
                wraplength=660,
                font=ctk.CTkFont(size=self._fs(10)),
            ).grid(row=idx * 2 + 1, column=0, sticky="ew", padx=28, pady=(0, 6))

        combine_value = "__combine__"
        ctk.CTkRadioButton(
            box,
            text="Combinar todas las plantillas activas",
            variable=choice_var,
            value=combine_value,
            fg_color=C_ACCENT_LAB,
            hover_color=C_ACCENT_LAB_H,
            text_color=C_TEXT,
            border_color=C_BORDER,
            font=ctk.CTkFont(size=self._fs(11), weight="bold"),
        ).grid(row=max(1, len(candidates) * 2), column=0, sticky="w", padx=10, pady=(10, 4))

        ctk.CTkCheckBox(
            box,
            text="Recordar: combinar siempre en esta categoria",
            variable=remember_combine_var,
            fg_color=C_ACCENT_LAB,
            hover_color=C_ACCENT_LAB_H,
            text_color=C_TEXT,
            border_color=C_BORDER,
            font=ctk.CTkFont(size=self._fs(10)),
        ).grid(row=max(2, len(candidates) * 2 + 1), column=0, sticky="w", padx=28, pady=(0, 8))

        result: dict[str, str | bool | None] = {"choice": None, "remember_combine": False}

        def _accept() -> None:
            result["choice"] = choice_var.get().strip()
            result["remember_combine"] = bool(remember_combine_var.get())
            modal.destroy()

        def _cancel() -> None:
            result["choice"] = None
            result["remember_combine"] = False
            modal.destroy()

        btns = ctk.CTkFrame(root, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        ctk.CTkButton(
            btns,
            text="Insertar",
            fg_color=C_ACCENT_LAB,
            hover_color=C_ACCENT_LAB_H,
            text_color="#FFFFFF",
            command=_accept,
        ).pack(side="left")

        ctk.CTkButton(
            btns,
            text="Cancelar",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=_cancel,
        ).pack(side="left", padx=(8, 0))

        modal.wait_window()
        choice = result.get("choice")
        remember = bool(result.get("remember_combine", False))
        return (str(choice).strip() if isinstance(choice, str) and choice.strip() else None, remember)

    def _pl_insert_prompt_template(self) -> None:
        if not hasattr(self, "_txt_pl_prompt"):
            return
        self._pl_refresh_prompt_helper()

        candidates = self._pl_collect_active_template_candidates()
        selected_template = ""

        if not candidates:
            template = (self._pl_prompt_template_current or "").strip()
            if template:
                selected_template = template
            else:
                if hasattr(self, "_lbl_pl_status"):
                    self._pl_set_status("No hay plantillas disponibles en las skills activas")
                return
        elif len(candidates) == 1:
            selected_template = str(candidates[0].get("template", "")).strip()
        else:
            pref_key = self._pl_template_category_key()
            pref_mode = str(self._pl_template_insert_mode_by_category.get(pref_key, "ask")).strip().lower()

            if pref_mode == "combine":
                selected_template = self._pl_build_combined_template(candidates)
            else:
                choice, remember_combine = self._pl_pick_template_candidate(candidates)
                if not choice:
                    return
                if choice == "__combine__":
                    selected_template = self._pl_build_combined_template(candidates)
                    if remember_combine:
                        self._pl_template_insert_mode_by_category[pref_key] = "combine"
                        self._save_settings()
                else:
                    picked = next((item for item in candidates if item.get("id") == choice), None)
                    if not picked:
                        if hasattr(self, "_lbl_pl_status"):
                            self._pl_set_status("No se pudo identificar la plantilla elegida")
                        return
                    selected_template = str(picked.get("template", "")).strip()

        current = self._txt_pl_prompt.get("1.0", "end").strip()
        if current:
            replace = messagebox.askyesno(
                "Prompt Lab",
                "Ya hay texto en el prompt. Quieres reemplazarlo por la plantilla?",
            )
            if not replace:
                return

        self._txt_pl_prompt.delete("1.0", "end")
        self._txt_pl_prompt.insert("1.0", selected_template)
        self._pl_last_inserted_template = selected_template
        if hasattr(self, "_lbl_pl_status"):
            self._pl_set_status("Plantilla de prompt insertada")

    def _pl_export_workspace(self) -> None:
        ws = self._var_pl_workspace.get().strip()
        if not ws:
            return
        file_path = filedialog.asksaveasfilename(
            title="Exportar workspace de Prompt Lab",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile=f"prompt-lab-{ws}.json",
        )
        if not file_path:
            return
        try:
            self._prompt_lab.export_workspace(ws, Path(file_path))
            self._log(f"[Prompt Lab] Workspace exportado: {file_path}")
            if hasattr(self, "_lbl_pl_status"):
                self._pl_set_status(f"Workspace exportado: {ws}")
        except ValueError as exc:
            messagebox.showwarning("Prompt Lab", str(exc))
        except Exception as exc:
            messagebox.showerror("Prompt Lab", f"Error exportando workspace: {exc}")

    def _pl_import_workspace(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Importar workspace de Prompt Lab",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
        )
        if not file_path:
            return
        replace = messagebox.askyesno(
            "Prompt Lab",
            "Si ya existe un workspace con ese nombre, deseas reemplazarlo?",
        )
        try:
            imported_name = self._prompt_lab.import_workspace(Path(file_path), replace_if_exists=replace)
            self._pl_refresh_workspace_menu(select=imported_name)
            self._log(f"[Prompt Lab] Workspace importado: {imported_name}")
        except ValueError as exc:
            messagebox.showwarning("Prompt Lab", str(exc))
        except Exception as exc:
            messagebox.showerror("Prompt Lab", f"Error importando workspace: {exc}")

    def _pl_create_catalog_template(self) -> None:
        ws = self._var_pl_workspace.get().strip() or "General"
        try:
            path = self._prompt_lab.write_initial_catalog_template(ws)
        except ValueError as exc:
            messagebox.showwarning("Prompt Lab", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Prompt Lab", f"No se pudo crear la plantilla: {exc}")
            return

        self._log(f"[Prompt Lab] Plantilla de catalogo creada: {path}")
        messagebox.showinfo(
            "Prompt Lab",
            "Se creo la plantilla de catalogo inicial.\n\n"
            f"Archivo: {path}\n\n"
            "Completa las instrucciones y luego usa 'Instalar catalogo'.",
        )

    def _pl_install_catalog(self) -> None:
        ws = self._var_pl_workspace.get().strip() or "General"
        default_catalog = self._prompt_lab.catalog_file()
        file_path = filedialog.askopenfilename(
            title="Instalar catalogo inicial de skills",
            initialdir=str(default_catalog.parent),
            initialfile=default_catalog.name,
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
        )
        if not file_path:
            return

        try:
            result = self._prompt_lab.install_catalog(
                ws,
                Path(file_path),
                overwrite_existing=False,
            )
            self._pl_refresh_workspace_menu(select=ws)
            self._log(
                "[Prompt Lab] Catalogo instalado "
                f"(creadas={result['created']}, actualizadas={result['updated']}, omitidas={result['skipped']})."
            )
            messagebox.showinfo(
                "Prompt Lab",
                "Catalogo aplicado correctamente.\n\n"
                f"Creadas: {result['created']}\n"
                f"Actualizadas: {result['updated']}\n"
                f"Omitidas: {result['skipped']}\n\n"
                "Nota: no se modificaron skills existentes con el mismo nombre.",
            )
        except ValueError as exc:
            messagebox.showwarning("Prompt Lab", str(exc))
        except Exception as exc:
            messagebox.showerror("Prompt Lab", f"Error instalando catalogo: {exc}")

    def _pl_open_preload_config_modal(self) -> None:
        ws = self._var_pl_workspace.get().strip() or "General"
        categories = self._prompt_lab.categories(ws) or ["General"]

        modal = ctk.CTkToplevel(self)
        modal.title("Configurar precarga de skills")
        modal.geometry("700x540")
        modal.resizable(True, True)
        modal.grab_set()
        modal.configure(fg_color=C_BG)
        _center_window_on_screen(modal)

        root = ctk.CTkFrame(modal, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=16, pady=14)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            root,
            text="Precarga por categoria",
            text_color=C_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        top = ctk.CTkFrame(root, fg_color="transparent")
        top.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(top, text="Categoria", text_color=C_MUTED).grid(row=0, column=0, sticky="w", padx=(0, 8))
        selected_cat = tk.StringVar(value=self._var_pl_category.get().strip() or categories[0])
        cat_menu = ctk.CTkOptionMenu(
            top,
            variable=selected_cat,
            values=categories,
            fg_color=C_INPUT,
            button_color=C_ACCENT_LAB,
            button_hover_color=C_ACCENT_LAB_H,
            text_color=C_TEXT,
            dropdown_fg_color=C_CARD,
            dropdown_hover_color=C_HOVER,
            dropdown_text_color=C_TEXT,
        )
        cat_menu.grid(row=0, column=1, sticky="ew")

        box = ctk.CTkScrollableFrame(root, fg_color=C_CARD)
        box.grid(row=2, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1)

        summary_var = tk.StringVar(value="")
        ctk.CTkLabel(
            root,
            textvariable=summary_var,
            text_color=C_TEXT_DIM,
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=self._fs(10)),
        ).grid(row=3, column=0, sticky="ew", pady=(8, 0))

        vars_map: dict[str, tk.BooleanVar] = {}

        def _refresh() -> None:
            for child in box.winfo_children():
                child.destroy()
            vars_map.clear()

            cat = selected_cat.get().strip() or "General"
            skills = self._prompt_lab.skill_objects(ws, cat)
            preload = set(self._prompt_lab.category_preload_skills(ws, cat))

            if not skills:
                ctk.CTkLabel(
                    box,
                    text="No hay skills en esta categoria.",
                    text_color=C_TEXT_DIM,
                    anchor="w",
                ).grid(row=0, column=0, sticky="ew", padx=10, pady=10)
                summary_var.set("No hay skills para configurar.")
                return

            for idx, sk in enumerate(skills):
                row = ctk.CTkFrame(box, fg_color="transparent")
                row.grid(row=idx, column=0, sticky="ew", padx=10, pady=(4, 2))
                row.grid_columnconfigure(0, weight=1)

                var = tk.BooleanVar(value=(sk.name in preload))
                vars_map[sk.name] = var

                ctk.CTkCheckBox(
                    row,
                    text=sk.name,
                    variable=var,
                    fg_color=C_ACCENT_LAB,
                    hover_color=C_ACCENT_LAB_H,
                    text_color=C_TEXT,
                ).grid(row=0, column=0, sticky="w")

                desc = sk.description.strip() or "Sin descripcion"
                ctk.CTkLabel(
                    row,
                    text=desc,
                    text_color=C_TEXT_DIM,
                    anchor="w",
                    justify="left",
                    wraplength=560,
                    font=ctk.CTkFont(size=self._fs(10)),
                ).grid(row=1, column=0, sticky="ew", pady=(0, 4))

            summary_var.set(
                "Marca las skills que deben cargarse automaticamente al seleccionar esta categoria. "
                "Recomendado: 1 general + 1 de categoria."
            )

        def _save() -> None:
            cat = selected_cat.get().strip() or "General"
            chosen = [name for name, var in vars_map.items() if var.get()]
            try:
                self._prompt_lab.set_category_preload_skills(ws, cat, chosen)
                self._log(f"[Prompt Lab] Precarga actualizada para '{cat}' ({len(chosen)} skills).")
                # Reaplicar precarga si el usuario guarda la categoria actualmente activa.
                if cat == (self._var_pl_category.get().strip() or "General"):
                    self._pl_last_category_for_preload = ""
                    self._pl_on_category_selected()
                messagebox.showinfo("Prompt Lab", "Precarga guardada correctamente.")
            except ValueError as exc:
                messagebox.showwarning("Prompt Lab", str(exc))

        btns = ctk.CTkFrame(root, fg_color="transparent")
        btns.grid(row=4, column=0, sticky="ew", pady=(10, 0))

        ctk.CTkButton(
            btns,
            text="Guardar precarga",
            fg_color=C_ACCENT_LAB,
            hover_color=C_ACCENT_LAB_H,
            text_color="#FFFFFF",
            command=_save,
        ).pack(side="left")
        ctk.CTkButton(
            btns,
            text="Cerrar",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=modal.destroy,
        ).pack(side="right")

        selected_cat.trace_add("write", lambda *_: _refresh())
        _refresh()

    def _pl_open_versions_modal(self) -> None:
        ws = self._var_pl_workspace.get().strip() or "General"
        cat = self._var_pl_category.get().strip() or "General"
        skill_name = self._var_pl_skill.get().strip()
        if not skill_name:
            messagebox.showwarning("Prompt Lab", "Selecciona una skill primero.")
            return

        versions = self._prompt_lab.skill_versions(ws, cat, skill_name)
        if not versions:
            messagebox.showinfo("Prompt Lab", "Esta skill aun no tiene historial de versiones.")
            return

        modal = ctk.CTkToplevel(self)
        modal.title("Historial de versiones")
        modal.geometry("640x460")
        modal.resizable(True, True)
        modal.grab_set()
        modal.configure(fg_color=C_BG)
        _center_window_on_screen(modal)

        inner = ctk.CTkFrame(modal, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=20, pady=(14, 10))
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            inner,
            text=f"Skill: {skill_name} ({len(versions)} versiones)",
            text_color=C_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        box = ctk.CTkScrollableFrame(inner, fg_color=C_CARD)
        box.grid(row=1, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1)

        selected_version = tk.IntVar(value=versions[-1].version)
        for idx, rev in enumerate(reversed(versions)):
            row = ctk.CTkFrame(box, fg_color="transparent")
            row.grid(row=idx, column=0, sticky="ew", padx=8, pady=(2, 4))
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkRadioButton(
                row,
                text=f"v{rev.version}",
                variable=selected_version,
                value=rev.version,
                fg_color=C_ACCENT_LAB,
                hover_color=C_ACCENT_LAB_H,
                text_color=C_TEXT,
            ).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(
                row,
                text=rev.updated_at or "sin fecha",
                text_color=C_TEXT_DIM,
                anchor="w",
                font=ctk.CTkFont(size=self._fs(10)),
            ).grid(row=0, column=1, sticky="w", padx=(8, 0))

        btns = ctk.CTkFrame(modal, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(0, 14))

        def _restore_selected() -> None:
            try:
                self._prompt_lab.restore_skill_version(
                    workspace_name=ws,
                    category_name=cat,
                    skill_name=skill_name,
                    version=selected_version.get(),
                )
                self._pl_on_skill_selected()
                self._log(f"[Prompt Lab] Restaurada version v{selected_version.get()} de {skill_name}")
                modal.destroy()
            except ValueError as exc:
                messagebox.showwarning("Prompt Lab", str(exc))

        ctk.CTkButton(
            btns,
            text="Restaurar version",
            fg_color=C_ACCENT_LAB,
            hover_color=C_ACCENT_LAB_H,
            text_color="#FFFFFF",
            command=_restore_selected,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            btns,
            text="Cerrar",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=2,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=modal.destroy,
        ).pack(side="left")

    def _pl_open_model_manager_modal(self) -> None:
        base_url = "http://127.0.0.1:11434"
        if hasattr(self, "_var_pl_backend_url"):
            base_url = self._var_pl_backend_url.get().strip() or base_url
        else:
            base_url = str(self.settings.get("pl_backend_url", base_url) or base_url).strip()

        modal = ctk.CTkToplevel(self)
        modal.title("Gestion de almacenamiento IA")
        modal.geometry("760x560")
        modal.resizable(True, True)
        modal.grab_set()
        modal.configure(fg_color=C_BG)
        _center_window_on_screen(modal)

        root = ctk.CTkFrame(modal, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=20, pady=(14, 14))
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            root,
            text="Gestionar modelos y Ollama",
            text_color=C_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=self._fs(14), weight="bold"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 4))

        ctk.CTkLabel(
            root,
            text=(
                "Desde aqui puedes eliminar modelos individuales o desinstalar Ollama completo "
                "para liberar espacio en disco."
            ),
            text_color=C_TEXT_DIM,
            anchor="w",
            justify="left",
            wraplength=700,
            font=ctk.CTkFont(size=self._fs(11)),
        ).grid(row=1, column=0, sticky="ew", pady=(0, 10))

        box = ctk.CTkScrollableFrame(root, fg_color=C_CARD)
        box.grid(row=2, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1)

        summary_var = tk.StringVar(value="Cargando modelos instalados...")
        ctk.CTkLabel(
            root,
            textvariable=summary_var,
            text_color=C_ACCENT_LAB,
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=self._fs(11), weight="bold"),
        ).grid(row=3, column=0, sticky="ew", pady=(10, 8))

        btns = ctk.CTkFrame(root, fg_color="transparent")
        btns.grid(row=4, column=0, sticky="ew")

        model_vars: dict[str, tk.BooleanVar] = {}
        model_sizes: dict[str, float] = {}

        def _update_summary() -> None:
            selected = [name for name, var in model_vars.items() if var.get()]
            selected_gb = round(sum(model_sizes.get(name, 0.0) for name in selected), 2)
            total_gb = round(sum(model_sizes.values()), 2)
            summary_var.set(
                f"Modelos instalados: {len(model_vars)} | Seleccionados: {len(selected)} | "
                f"Peso seleccionado: {selected_gb:.2f} GB | Total aprox: {total_gb:.2f} GB"
            )

        def _set_buttons(enabled: bool) -> None:
            state = "normal" if enabled else "disabled"
            btn_delete.configure(state=state)
            btn_uninstall.configure(state=state)
            btn_refresh.configure(state=state)
            btn_close.configure(state=state)

        def _load_models() -> None:
            for child in box.winfo_children():
                child.destroy()
            model_vars.clear()
            model_sizes.clear()

            try:
                models = list_installed_models_with_sizes(base_url)
            except Exception as exc:
                ctk.CTkLabel(
                    box,
                    text=f"No se pudo consultar modelos: {exc}",
                    text_color=C_ERROR,
                    anchor="w",
                    justify="left",
                    wraplength=680,
                    font=ctk.CTkFont(size=self._fs(11)),
                ).grid(row=0, column=0, sticky="ew", padx=12, pady=12)
                summary_var.set("No fue posible consultar modelos instalados.")
                return

            if not models:
                ctk.CTkLabel(
                    box,
                    text="No hay modelos instalados en Ollama.",
                    text_color=C_TEXT_DIM,
                    anchor="w",
                    justify="left",
                    font=ctk.CTkFont(size=self._fs(11)),
                ).grid(row=0, column=0, sticky="ew", padx=12, pady=12)
                summary_var.set("No hay modelos instalados.")
                return

            for idx, item in enumerate(models):
                name = str(item.get("name", "")).strip()
                size_gb = float(item.get("size_gb", 0.0) or 0.0)
                if not name:
                    continue

                model_sizes[name] = size_gb
                var = tk.BooleanVar(value=False)
                model_vars[name] = var

                row = ctk.CTkFrame(box, fg_color="transparent")
                row.grid(row=idx, column=0, sticky="ew", padx=8, pady=(4, 2))
                row.grid_columnconfigure(0, weight=1)

                ctk.CTkCheckBox(
                    row,
                    text=name,
                    variable=var,
                    text_color=C_TEXT,
                    command=_update_summary,
                    fg_color=C_ACCENT_LAB,
                    hover_color=C_ACCENT_LAB_H,
                    font=ctk.CTkFont(size=self._fs(11), weight="bold"),
                ).grid(row=0, column=0, sticky="w")

                size_text = f"{size_gb:.2f} GB" if size_gb > 0 else "tamano no reportado"
                ctk.CTkLabel(
                    row,
                    text=size_text,
                    text_color=C_TEXT_DIM,
                    anchor="e",
                    font=ctk.CTkFont(size=self._fs(10)),
                ).grid(row=0, column=1, sticky="e", padx=(8, 0))

            _update_summary()

        def _run_task(title: str, headline: str, task_fn, on_done) -> None:
            busy = BusyDialog(self, title=title, headline=headline, detail="Preparando...")

            def _progress(message: str, _pct: float | None = None) -> None:
                self.after(0, busy.set_detail, headline, message)

            def _worker() -> None:
                try:
                    ok, detail = task_fn(_progress)
                except Exception as exc:
                    ok, detail = False, str(exc)

                def _done() -> None:
                    busy.close()
                    on_done(ok, detail)

                self.after(0, _done)

            threading.Thread(target=_worker, daemon=True).start()

        def _delete_selected_models() -> None:
            selected = [name for name, var in model_vars.items() if var.get()]
            if not selected:
                messagebox.showinfo("Prompt Lab", "Selecciona al menos un modelo para eliminar.")
                return

            total_gb = round(sum(model_sizes.get(name, 0.0) for name in selected), 2)
            confirm = ThemedConfirmDialog(
                self,
                "Eliminar modelos",
                "Confirmar eliminacion de modelos",
                "Se eliminaran los modelos seleccionados de Ollama.\n"
                f"Espacio estimado a liberar: {total_gb:.2f} GB.\n\n"
                "Podras volver a descargarlos despues desde Prompt Lab.",
            ).run_modal()
            if not confirm:
                return

            _set_buttons(False)

            def _task(progress_cb):
                return remove_ollama_models(selected, on_progress=progress_cb)

            def _done(ok: bool, detail: str) -> None:
                _set_buttons(True)
                if ok:
                    self._log(f"[Prompt Lab] Modelos eliminados: {', '.join(selected)}")
                    messagebox.showinfo("Prompt Lab", "Modelos eliminados correctamente.")
                    _load_models()
                else:
                    messagebox.showerror("Prompt Lab", f"No se pudieron eliminar modelos.\n\n{detail}")

            _run_task("Prompt Lab IA", "Eliminando modelos...", _task, _done)

        def _uninstall_ollama() -> None:
            confirm = ThemedConfirmDialog(
                self,
                "Desinstalar Ollama",
                "Confirmar desinstalacion completa",
                "Esto eliminara Ollama del sistema.\n"
                "Prompt Lab no podra generar respuestas hasta reinstalarlo.\n\n"
                "Deseas continuar?",
            ).run_modal()
            if not confirm:
                return

            _set_buttons(False)

            def _task(progress_cb):
                return uninstall_ollama_windows(on_progress=progress_cb)

            def _done(ok: bool, detail: str) -> None:
                _set_buttons(True)
                if ok:
                    self._log("[Prompt Lab] Ollama desinstalado por el usuario.")
                    messagebox.showinfo(
                        "Prompt Lab",
                        "Ollama fue desinstalado correctamente. Prompt Lab IA quedara deshabilitado hasta reinstalarlo.",
                    )
                    modal.destroy()
                else:
                    messagebox.showerror("Prompt Lab", f"No se pudo desinstalar Ollama.\n\n{detail}")

            _run_task("Prompt Lab IA", "Desinstalando Ollama...", _task, _done)

        btn_delete = ctk.CTkButton(
            btns,
            text="Eliminar modelos seleccionados",
            fg_color=C_BTN_DANGER,
            hover_color=C_ERROR,
            text_color="#FFFFFF",
            command=_delete_selected_models,
        )
        btn_delete.pack(side="left")

        btn_uninstall = ctk.CTkButton(
            btns,
            text="Desinstalar Ollama",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=_uninstall_ollama,
        )
        btn_uninstall.pack(side="left", padx=(8, 0))

        btn_refresh = ctk.CTkButton(
            btns,
            text="Actualizar lista",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=_load_models,
        )
        btn_refresh.pack(side="left", padx=(8, 0))

        btn_close = ctk.CTkButton(
            btns,
            text="Cerrar",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=modal.destroy,
        )
        btn_close.pack(side="right")

        _load_models()

    def _pl_open_categories_modal(self) -> None:
        ws = self._var_pl_workspace.get().strip() or "General"

        modal = ctk.CTkToplevel(self)
        modal.title("Categorias de skills")
        modal.geometry("560x440")
        modal.resizable(True, True)
        modal.grab_set()
        modal.configure(fg_color=C_BG)
        _center_window_on_screen(modal)

        root = ctk.CTkFrame(modal, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=16, pady=14)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            root,
            text=f"Workspace: {ws}",
            text_color=C_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        list_box = ctk.CTkScrollableFrame(root, fg_color=C_CARD)
        list_box.grid(row=1, column=0, sticky="nsew")
        list_box.grid_columnconfigure(0, weight=1)

        selected = tk.StringVar(value=self._var_pl_category.get().strip() or "General")

        def _refresh() -> None:
            for c in list_box.winfo_children():
                c.destroy()
            categories = self._prompt_lab.categories(ws) or ["General"]
            if selected.get() not in categories:
                selected.set(categories[0])
            for i, cat_name in enumerate(categories):
                row = ctk.CTkFrame(list_box, fg_color="transparent")
                row.grid(row=i, column=0, sticky="ew", padx=8, pady=(4, 2))
                row.grid_columnconfigure(1, weight=1)
                ctk.CTkRadioButton(
                    row,
                    text=cat_name,
                    variable=selected,
                    value=cat_name,
                    fg_color=C_ACCENT_LAB,
                    hover_color=C_ACCENT_LAB_H,
                    text_color=C_TEXT,
                ).grid(row=0, column=0, sticky="w")
                if cat_name.lower() == "general":
                    tag = "Base"
                    col = C_SUCCESS
                else:
                    tag = "Personalizada"
                    col = C_TEXT_DIM
                ctk.CTkLabel(
                    row,
                    text=tag,
                    text_color=col,
                    anchor="e",
                    font=ctk.CTkFont(size=self._fs(10)),
                ).grid(row=0, column=1, sticky="e")

        btns = ctk.CTkFrame(root, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        def _add() -> None:
            dlg = ctk.CTkInputDialog(text="Nombre de la nueva categoria:", title="Prompt Lab")
            _center_window_on_screen(dlg)
            name = (dlg.get_input() or "").strip()
            if not name:
                return
            try:
                self._prompt_lab.ensure_category(ws, name)
                self._pl_refresh_workspace_menu(select=ws)
                self._var_pl_category.set(name)
                self._pl_on_category_selected()
                _refresh()
            except ValueError as exc:
                messagebox.showwarning("Prompt Lab", str(exc))

        def _delete() -> None:
            name = selected.get().strip()
            if not name:
                return
            confirm = ThemedConfirmDialog(
                self,
                "Prompt Lab",
                "Eliminar categoria",
                f"Se eliminara la categoria '{name}' y sus skills.\n\nEstas seguro?",
            ).run_modal()
            if not confirm:
                return
            try:
                self._prompt_lab.delete_category(ws, name)
                self._pl_refresh_workspace_menu(select=ws)
                self._pl_on_category_selected()
                _refresh()
            except ValueError as exc:
                messagebox.showwarning("Prompt Lab", str(exc))

        ctk.CTkButton(
            btns,
            text="Nueva categoria",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=_add,
        ).pack(side="left")

        ctk.CTkButton(
            btns,
            text="Eliminar categoria",
            fg_color=C_BTN_DANGER,
            hover_color=C_ERROR,
            text_color="#FFFFFF",
            command=_delete,
        ).pack(side="left", padx=(8, 0))

        ctk.CTkButton(
            btns,
            text="Cerrar",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=modal.destroy,
        ).pack(side="right")

        _refresh()

    def _pl_open_skill_editor_modal(self, category: str = "", skill_name: str = "") -> None:
        ws = self._var_pl_workspace.get().strip() or "General"
        cat = category.strip() or self._var_pl_category.get().strip() or "General"
        current_name = skill_name.strip() or self._var_pl_skill.get().strip()
        if not current_name:
            messagebox.showwarning("Prompt Lab", "Selecciona una skill primero.")
            return

        skill = self._prompt_lab.get_skill(ws, cat, current_name)
        if not skill:
            messagebox.showwarning("Prompt Lab", "No se encontro la skill seleccionada.")
            return

        modal = ctk.CTkToplevel(self)
        modal.title("Ver / editar skill")
        modal.geometry("820x640")
        modal.resizable(True, True)
        modal.grab_set()
        modal.configure(fg_color=C_BG)
        _center_window_on_screen(modal)

        root = ctk.CTkFrame(modal, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=16, pady=14)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(3, weight=1)
        root.grid_rowconfigure(5, weight=0)

        ctk.CTkLabel(root, text="Nombre", text_color=C_MUTED).grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        var_name = tk.StringVar(value=skill.name)
        ent_name = ctk.CTkEntry(root, textvariable=var_name, fg_color=C_INPUT, border_color=C_BORDER, text_color=C_TEXT)
        ent_name.grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(root, text="Categoria", text_color=C_MUTED).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        all_categories = self._prompt_lab.categories(ws) or ["General"]
        if cat not in all_categories:
            all_categories.append(cat)
        selected_category = tk.StringVar(value=cat)
        ctk.CTkOptionMenu(
            root,
            variable=selected_category,
            values=all_categories,
            fg_color=C_INPUT,
            button_color=C_ACCENT_LAB,
            button_hover_color=C_ACCENT_LAB_H,
            text_color=C_TEXT,
            dropdown_fg_color=C_CARD,
            dropdown_hover_color=C_HOVER,
            dropdown_text_color=C_TEXT,
        ).grid(row=1, column=1, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(root, text="Nota opcional (1 linea)", text_color=C_MUTED).grid(row=2, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        var_note = tk.StringVar(value=(skill.description or "")[:180])
        ent_note = ctk.CTkEntry(root, textvariable=var_note, fg_color=C_INPUT, border_color=C_BORDER, text_color=C_TEXT)
        ent_note.grid(row=2, column=1, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(root, text="Comportamiento (instrucciones)", text_color=C_MUTED).grid(row=3, column=0, sticky="nw", padx=(0, 8), pady=(0, 8))
        txt_behavior = ctk.CTkTextbox(root, fg_color=C_INPUT, border_color=C_BORDER, text_color=C_TEXT)
        txt_behavior.configure(wrap="word")
        txt_behavior.grid(row=3, column=1, sticky="nsew", pady=(0, 8))
        txt_behavior.insert("1.0", skill.instructions)

        ctk.CTkLabel(root, text="Plantilla sugerida (opcional)", text_color=C_MUTED).grid(row=4, column=0, sticky="nw", padx=(0, 8), pady=(0, 8))
        template_expanded = tk.BooleanVar(value=False)

        txt_template = ctk.CTkTextbox(root, height=90, fg_color=C_INPUT, border_color=C_BORDER, text_color=C_TEXT)
        txt_template.configure(wrap="word")
        txt_template.grid(row=5, column=1, sticky="ew", pady=(0, 8))
        txt_template.insert("1.0", (skill.prompt_template or ""))

        def _toggle_template_visibility() -> None:
            if template_expanded.get():
                txt_template.grid_remove()
                btn_toggle_template.configure(text="Mostrar")
                template_expanded.set(False)
            else:
                txt_template.grid()
                btn_toggle_template.configure(text="Ocultar")
                template_expanded.set(True)

        btn_toggle_template = ctk.CTkButton(
            root,
            text="Mostrar",
            width=90,
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=_toggle_template_visibility,
        )
        btn_toggle_template.grid(row=4, column=1, sticky="e", pady=(0, 8))

        # Start collapsed to maximize instructions workspace.
        txt_template.grid_remove()

        btns = ctk.CTkFrame(root, fg_color="transparent")
        btns.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        def _update() -> None:
            source_category = cat
            source_name = current_name
            target_category = selected_category.get().strip() or source_category
            new_name = var_name.get().strip()
            if not new_name:
                messagebox.showwarning("Prompt Lab", "El nombre de skill no puede estar vacio.")
                return
            desc = var_note.get().strip()
            behavior = txt_behavior.get("1.0", "end").strip()
            prompt_template = txt_template.get("1.0", "end").strip()
            try:
                self._prompt_lab.edit_skill(
                    workspace_name=ws,
                    source_category_name=source_category,
                    source_skill_name=source_name,
                    target_category_name=target_category,
                    target_skill_name=new_name,
                    instructions=behavior,
                    description=desc,
                    prompt_template=prompt_template,
                )

                for item in self._pl_active_skills:
                    if item.get("category") == source_category and item.get("skill") == source_name:
                        item["category"] = target_category
                        item["skill"] = new_name

                self._var_pl_category.set(target_category)
                self._var_pl_skill.set(new_name)
                self._pl_on_category_selected()
                if hasattr(self, "_txt_pl_instructions"):
                    self._txt_pl_instructions.delete("1.0", "end")
                    self._txt_pl_instructions.insert("1.0", behavior)
                self._log(f"[Prompt Lab] Skill actualizada: {new_name} ({target_category})")
                messagebox.showinfo("Prompt Lab", "Skill actualizada correctamente.")
            except ValueError as exc:
                messagebox.showwarning("Prompt Lab", str(exc))

        ctk.CTkButton(
            btns,
            text="Actualizar",
            fg_color=C_ACCENT_LAB,
            hover_color=C_ACCENT_LAB_H,
            text_color="#FFFFFF",
            command=_update,
        ).pack(side="left")
        ctk.CTkButton(
            btns,
            text="Cerrar",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=modal.destroy,
        ).pack(side="left", padx=(8, 0))

    def _pl_open_skills_manager_modal(self) -> None:
        ws = self._var_pl_workspace.get().strip() or "General"
        cat = self._var_pl_category.get().strip() or "General"

        modal = ctk.CTkToplevel(self)
        modal.title("Gestionar skills")
        modal.geometry("860x620")
        modal.resizable(True, True)
        modal.grab_set()
        modal.configure(fg_color=C_BG)
        _center_window_on_screen(modal)

        root = ctk.CTkFrame(modal, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=16, pady=14)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(2, weight=1)

        title_var = tk.StringVar(value=f"Workspace: {ws} | Categoria: {cat}")
        ctk.CTkLabel(
            root,
            textvariable=title_var,
            text_color=C_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        filters = ctk.CTkFrame(root, fg_color="transparent")
        filters.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        filters.grid_columnconfigure(1, weight=1)
        filters.grid_columnconfigure(3, weight=1)

        ctk.CTkLabel(filters, text="Categoria", text_color=C_MUTED).grid(row=0, column=0, sticky="w", padx=(0, 8))
        category_filter_var = tk.StringVar(value=cat)
        category_values = ["Todas"] + (self._prompt_lab.categories(ws) or ["General"])
        if category_filter_var.get() not in category_values:
            category_filter_var.set("Todas")
        category_filter = ctk.CTkOptionMenu(
            filters,
            variable=category_filter_var,
            values=category_values,
            fg_color=C_INPUT,
            button_color=C_ACCENT_LAB,
            button_hover_color=C_ACCENT_LAB_H,
            text_color=C_TEXT,
            dropdown_fg_color=C_CARD,
            dropdown_hover_color=C_HOVER,
            dropdown_text_color=C_TEXT,
            command=lambda _v: _refresh(),
        )
        category_filter.grid(row=0, column=1, sticky="ew", padx=(0, 12))

        ctk.CTkLabel(filters, text="Buscar", text_color=C_MUTED).grid(row=0, column=2, sticky="w", padx=(0, 8))
        search_var = tk.StringVar(value="")
        search_entry = ctk.CTkEntry(
            filters,
            textvariable=search_var,
            fg_color=C_INPUT,
            border_color=C_BORDER,
            text_color=C_TEXT,
            placeholder_text="Filtrar por nombre de skill...",
        )
        search_entry.grid(row=0, column=3, sticky="ew")

        box = ctk.CTkScrollableFrame(root, fg_color=C_CARD)
        box.grid(row=2, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1)

        def _refresh() -> None:
            nonlocal ws, cat
            ws = self._var_pl_workspace.get().strip() or "General"
            cat = self._var_pl_category.get().strip() or "General"
            title_var.set(f"Workspace: {ws} | Categoria: {cat}")

            all_categories = self._prompt_lab.categories(ws) or ["General"]
            new_values = ["Todas"] + all_categories
            category_filter.configure(values=new_values)
            if category_filter_var.get() not in new_values:
                category_filter_var.set("Todas")

            for child in box.winfo_children():
                child.destroy()

            selected_cat = category_filter_var.get().strip() or "Todas"
            query = search_var.get().strip().lower()

            entries: list[tuple[str, str]] = []
            for cat_name in all_categories:
                if selected_cat != "Todas" and cat_name != selected_cat:
                    continue
                for sk in self._prompt_lab.skill_objects(ws, cat_name):
                    if query and query not in sk.name.lower():
                        continue
                    entries.append((cat_name, sk.name))

            if not entries:
                ctk.CTkLabel(
                    box,
                    text="No hay skills para el filtro actual.",
                    text_color=C_TEXT_DIM,
                    anchor="w",
                ).grid(row=0, column=0, sticky="ew", padx=10, pady=10)
                return

            for idx, (skill_cat, sk_name) in enumerate(entries):
                item = ctk.CTkFrame(
                    box,
                    fg_color=C_INPUT,
                    corner_radius=8,
                    border_width=1,
                    border_color=C_BORDER,
                )
                item.grid(row=idx, column=0, sticky="ew", padx=8, pady=(6 if idx == 0 else 2, 4))
                item.grid_columnconfigure(0, weight=1)

                ctk.CTkLabel(
                    item,
                    text=f"{sk_name}  [{skill_cat}]",
                    text_color=C_TEXT,
                    anchor="w",
                    font=ctk.CTkFont(size=self._fs(11), weight="bold"),
                ).grid(row=0, column=0, sticky="w", padx=10, pady=8)

                ctk.CTkButton(
                    item,
                    text="Ver/Editar",
                    width=90,
                    fg_color="transparent",
                    hover_color=C_HOVER,
                    border_width=1,
                    border_color=C_BORDER,
                    text_color=C_TEXT,
                    command=lambda c=skill_cat, s=sk_name: self._pl_open_skill_editor_modal(c, s),
                ).grid(row=0, column=1, padx=(0, 6), pady=6)

                ctk.CTkButton(
                    item,
                    text="Versiones",
                    width=86,
                    fg_color="transparent",
                    hover_color=C_HOVER,
                    border_width=1,
                    border_color=C_BORDER,
                    text_color=C_TEXT,
                    command=lambda c=skill_cat, s=sk_name: [
                        self._var_pl_category.set(c),
                        self._var_pl_skill.set(s),
                        self._pl_open_versions_modal(),
                    ],
                ).grid(row=0, column=2, padx=(0, 6), pady=6)

                def _delete_skill(category_name: str, name: str) -> None:
                    confirm = ThemedConfirmDialog(
                        self,
                        "Prompt Lab",
                        "Eliminar skill",
                        f"Se eliminara la skill '{name}' de la categoria '{category_name}'.\n\nEstas seguro?",
                    ).run_modal()
                    if not confirm:
                        return
                    try:
                        self._prompt_lab.delete_skill(ws, category_name, name)
                    except ValueError as exc:
                        messagebox.showwarning("Prompt Lab", str(exc))
                        return

                    self._pl_active_skills = [
                        i for i in self._pl_active_skills
                        if not (i.get("category") == category_name and i.get("skill") == name)
                    ]
                    self._pl_on_category_selected()
                    _refresh()

                ctk.CTkButton(
                    item,
                    text="Eliminar",
                    width=82,
                    fg_color=C_BTN_DANGER,
                    hover_color=C_ERROR,
                    text_color="#FFFFFF",
                    command=lambda c=skill_cat, s=sk_name: _delete_skill(c, s),
                ).grid(row=0, column=3, padx=(0, 8), pady=6)

        btns = ctk.CTkFrame(root, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="ew", pady=(10, 0))

        ctk.CTkButton(
            btns,
            text="Actualizar",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=_refresh,
        ).pack(side="left")
        ctk.CTkButton(
            btns,
            text="Configurar precarga",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=self._pl_open_preload_config_modal,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            btns,
            text="Crear plantilla catalogo",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=self._pl_create_catalog_template,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            btns,
            text="Instalar catalogo",
            fg_color=C_ACCENT_LAB,
            hover_color=C_ACCENT_LAB_H,
            text_color="#FFFFFF",
            command=self._pl_install_catalog,
        ).pack(side="left", padx=(8, 0))
        ctk.CTkButton(
            btns,
            text="Cerrar",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=modal.destroy,
        ).pack(side="right")

        search_var.trace_add("write", lambda *_: _refresh())

        _refresh()

    def _pl_open_skill_selector_modal(self) -> None:
        ws = self._var_pl_workspace.get().strip() or "General"
        current_cat = self._var_pl_category.get().strip() or "General"
        categories = ["General"]
        if current_cat != "General":
            categories.append(current_cat)

        modal = ctk.CTkToplevel(self)
        modal.title("Aplicar multiples skills")
        modal.geometry("720x520")
        modal.resizable(True, True)
        modal.grab_set()
        modal.configure(fg_color=C_BG)
        _center_window_on_screen(modal)

        root = ctk.CTkFrame(modal, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=16, pady=14)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            root,
            text="Selecciona skills a aplicar (General + categoria actual)",
            text_color=C_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
        ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

        box = ctk.CTkScrollableFrame(root, fg_color=C_CARD)
        box.grid(row=1, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1)

        vars_map: dict[tuple[str, str], tk.BooleanVar] = {}

        row_index = 0
        for cat_name in categories:
            ctk.CTkLabel(
                box,
                text=cat_name,
                text_color=C_ACCENT_LAB,
                anchor="w",
                font=ctk.CTkFont(size=self._fs(11), weight="bold"),
            ).grid(row=row_index, column=0, sticky="ew", padx=10, pady=(8, 2))
            row_index += 1

            for sk in self._prompt_lab.skill_objects(ws, cat_name):
                key = (cat_name, sk.name)
                default_checked = any(
                    item.get("category") == cat_name and item.get("skill") == sk.name
                    for item in self._pl_active_skills
                )
                var = tk.BooleanVar(value=default_checked)
                vars_map[key] = var
                line = ctk.CTkFrame(box, fg_color="transparent")
                line.grid(row=row_index, column=0, sticky="ew", padx=16, pady=(2, 2))
                line.grid_columnconfigure(0, weight=1)
                ctk.CTkCheckBox(
                    line,
                    text=sk.name,
                    variable=var,
                    fg_color=C_ACCENT_LAB,
                    hover_color=C_ACCENT_LAB_H,
                    text_color=C_TEXT,
                ).grid(row=0, column=0, sticky="w")
                desc = sk.description.strip() or "Sin descripcion"
                ctk.CTkLabel(
                    line,
                    text=desc,
                    text_color=C_TEXT_DIM,
                    anchor="w",
                    justify="left",
                    wraplength=560,
                    font=ctk.CTkFont(size=self._fs(10)),
                ).grid(row=1, column=0, sticky="ew", pady=(0, 4))
                row_index += 1

        btns = ctk.CTkFrame(root, fg_color="transparent")
        btns.grid(row=2, column=0, sticky="ew", pady=(10, 0))

        def _apply() -> None:
            chosen: list[dict[str, str]] = []
            for (cat_name, skill_name), var in vars_map.items():
                if var.get():
                    chosen.append({"category": cat_name, "skill": skill_name})
            if not chosen:
                messagebox.showwarning("Prompt Lab", "Selecciona al menos una skill.")
                return
            self._pl_active_skills = chosen
            self._pl_refresh_applied_skills_label()
            self._log(f"[Prompt Lab] Skills aplicadas actualizadas ({len(chosen)}).")
            modal.destroy()

        ctk.CTkButton(
            btns,
            text="Actualizar skills aplicadas",
            fg_color=C_ACCENT_LAB,
            hover_color=C_ACCENT_LAB_H,
            text_color="#FFFFFF",
            command=_apply,
        ).pack(side="left")
        ctk.CTkButton(
            btns,
            text="Cerrar",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=modal.destroy,
        ).pack(side="left", padx=(8, 0))

    def _pl_new_workspace_dialog(self) -> None:
        dialog = ctk.CTkInputDialog(text="Nombre del nuevo workspace:", title="Prompt Lab")
        _center_window_on_screen(dialog)
        name = (dialog.get_input() or "").strip()
        if not name:
            return
        try:
            self._prompt_lab.create_workspace(name)
            self._pl_refresh_workspace_menu(select=name)
            self._log(f"[Prompt Lab] Workspace creado: {name}")
        except ValueError as exc:
            messagebox.showwarning("Prompt Lab", str(exc))

    def _pl_delete_workspace(self) -> None:
        ws = self._var_pl_workspace.get().strip()
        if not ws:
            return
        if not messagebox.askyesno("Prompt Lab", f"Eliminar workspace '{ws}'?"):
            return
        try:
            self._prompt_lab.delete_workspace(ws)
            self._pl_refresh_workspace_menu()
            self._log(f"[Prompt Lab] Workspace eliminado: {ws}")
        except ValueError as exc:
            messagebox.showwarning("Prompt Lab", str(exc))

    def _pl_new_skill_dialog(self) -> None:
        ws = self._var_pl_workspace.get().strip() or "General"
        categories = self._prompt_lab.categories(ws) or ["General"]
        selected_category = tk.StringVar(value=self._var_pl_category.get().strip() or categories[0])

        modal = ctk.CTkToplevel(self)
        modal.title("Nueva skill")
        modal.geometry("860x650")
        modal.resizable(True, True)
        modal.grab_set()
        modal.configure(fg_color=C_BG)
        _center_window_on_screen(modal)

        root = ctk.CTkFrame(modal, fg_color="transparent")
        root.pack(fill="both", expand=True, padx=16, pady=14)
        root.grid_columnconfigure(1, weight=1)
        root.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            root,
            text="Crear nueva skill",
            text_color=C_TEXT,
            anchor="w",
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(root, text="Nombre", text_color=C_MUTED).grid(
            row=1, column=0, sticky="w", padx=(0, 8), pady=(0, 8)
        )
        ent_name = ctk.CTkEntry(
            root,
            fg_color=C_INPUT,
            border_color=C_BORDER,
            text_color=C_TEXT,
            placeholder_text="Ej: Asistente SEO",
        )
        ent_name.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(root, text="Categoria", text_color=C_MUTED).grid(
            row=2, column=0, sticky="nw", padx=(0, 8), pady=(0, 8)
        )
        category_menu = ctk.CTkOptionMenu(
            root,
            variable=selected_category,
            values=categories,
            fg_color=C_INPUT,
            button_color=C_ACCENT_LAB,
            button_hover_color=C_ACCENT_LAB_H,
            text_color=C_TEXT,
            dropdown_fg_color=C_CARD,
            dropdown_hover_color=C_HOVER,
            dropdown_text_color=C_TEXT,
        )
        category_menu.grid(row=2, column=1, sticky="ew", pady=(0, 8))

        ctk.CTkLabel(root, text="Skill (comportamiento)", text_color=C_MUTED).grid(
            row=3, column=0, sticky="nw", padx=(0, 8), pady=(0, 8)
        )
        txt_skill = ctk.CTkTextbox(
            root,
            height=360,
            fg_color=C_INPUT,
            border_color=C_BORDER,
            text_color=C_TEXT,
        )
        txt_skill.configure(wrap="word")
        txt_skill.grid(row=3, column=1, sticky="nsew", pady=(0, 8))

        ctk.CTkLabel(root, text="Plantilla sugerida (opcional)", text_color=C_MUTED).grid(
            row=4, column=0, sticky="nw", padx=(0, 8), pady=(0, 8)
        )
        txt_template = ctk.CTkTextbox(
            root,
            height=120,
            fg_color=C_INPUT,
            border_color=C_BORDER,
            text_color=C_TEXT,
        )
        txt_template.configure(wrap="word")
        txt_template.grid(row=4, column=1, sticky="nsew", pady=(0, 8))

        btns = ctk.CTkFrame(root, fg_color="transparent")
        btns.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))

        def _create() -> None:
            skill_name = ent_name.get().strip()
            category = selected_category.get().strip() or "General"
            instructions = txt_skill.get("1.0", "end").strip()
            prompt_template = txt_template.get("1.0", "end").strip()
            if not skill_name:
                messagebox.showwarning("Prompt Lab", "El nombre de la skill no puede estar vacio.")
                return
            if not instructions:
                messagebox.showwarning("Prompt Lab", "Escribe el comportamiento de la skill.")
                return
            try:
                self._prompt_lab.upsert_skill(
                    ws,
                    category,
                    skill_name,
                    instructions,
                    description="",
                    prompt_template=prompt_template,
                )
                self._var_pl_category.set(category)
                self._var_pl_skill.set(skill_name)
                self._pl_on_workspace_selected()
                self._log(f"[Prompt Lab] Skill creada: {skill_name} ({category})")
                modal.destroy()
            except ValueError as exc:
                messagebox.showwarning("Prompt Lab", str(exc))

        ctk.CTkButton(
            btns,
            text="Crear",
            fg_color=C_ACCENT_LAB,
            hover_color=C_ACCENT_LAB_H,
            text_color="#FFFFFF",
            command=_create,
        ).pack(side="left")

        ctk.CTkButton(
            btns,
            text="Cerrar",
            fg_color="transparent",
            hover_color=C_HOVER,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=modal.destroy,
        ).pack(side="left", padx=(8, 0))

    def _pl_save_skill_dialog(self) -> None:
        ws = self._var_pl_workspace.get().strip() or "General"
        category = self._var_pl_category.get().strip() or "General"
        skill_name = self._var_pl_skill.get().strip()
        if not skill_name:
            messagebox.showwarning("Prompt Lab", "Selecciona o crea una skill primero.")
            return
        instructions = ""
        if hasattr(self, "_txt_pl_instructions"):
            instructions = self._txt_pl_instructions.get("1.0", "end").strip()
        current = self._prompt_lab.get_skill(ws, category, skill_name)
        description = current.description if current else ""
        try:
            self._prompt_lab.upsert_skill(
                ws,
                category,
                skill_name,
                instructions,
                description=description,
            )
            self._pl_on_workspace_selected()
            self._log(f"[Prompt Lab] Skill guardada: {skill_name}")
        except ValueError as exc:
            messagebox.showwarning("Prompt Lab", str(exc))

    def _pl_copy_output(self) -> None:
        if not hasattr(self, "_txt_pl_output"):
            return
        content = self._txt_pl_output.get("1.0", "end").strip()
        if not content:
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        if hasattr(self, "_lbl_pl_status"):
            self._pl_set_status("Salida copiada al portapapeles")

    def _on_generate_prompt_lab(self) -> None:
        if self._pl_generation_in_progress:
            messagebox.showinfo("Prompt Lab", "Ya hay una generacion en progreso.")
            return
        if not hasattr(self, "_txt_pl_prompt") or not hasattr(self, "_txt_pl_output"):
            return
        prompt = self._txt_pl_prompt.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("Prompt Lab", "Escribe un prompt antes de generar.")
            return

        ws = self._var_pl_workspace.get().strip() or "General"
        cat = self._var_pl_category.get().strip() or "General"
        skill_name = self._var_pl_skill.get().strip() or "Skill General"
        mode = self._var_pl_model_mode.get().strip() or "Calidad alta"
        if not self._pl_active_skills:
            self._pl_active_skills = [{"category": cat, "skill": skill_name}]

        parts: list[str] = []
        for item in self._pl_active_skills:
            ac = str(item.get("category", "")).strip()
            an = str(item.get("skill", "")).strip()
            if not ac or not an:
                continue
            sk = self._prompt_lab.get_skill(ws, ac, an)
            if sk and sk.instructions.strip():
                parts.append(f"[{ac}/{an}]\n{sk.instructions.strip()}")
        instructions = "\n\n".join(parts).strip()
        if not instructions:
            skill = self._prompt_lab.get_skill(ws, cat, skill_name)
            instructions = skill.instructions if skill else ""

        config = PromptBackendConfig(
            base_url=self._var_pl_backend_url.get().strip(),
            quality_model=self._var_pl_model_quality.get().strip(),
            fast_model=self._var_pl_model_fast.get().strip(),
            timeout_seconds=120,
        )

        self._pl_generation_in_progress = True
        self._btn_generate.configure(state="disabled")
        if hasattr(self, "_lbl_pl_status"):
            self._pl_set_status(f"Generando con backend local ({mode})...")

        def _worker() -> None:
            try:
                response = self._prompt_backend.generate(
                    prompt=prompt,
                    skill_instructions=instructions,
                    mode=mode,
                    config=config,
                )
                self.after(0, self._pl_on_backend_response, response, mode)
            except Exception as exc:
                self.after(0, self._pl_on_backend_error, exc)

        threading.Thread(target=_worker, daemon=True).start()

    def _pl_on_backend_response(self, response: str, mode: str) -> None:
        self._pl_generation_in_progress = False
        self._btn_generate.configure(state="normal")
        if hasattr(self, "_txt_pl_output"):
            self._txt_pl_output.delete("1.0", "end")
            self._txt_pl_output.insert("1.0", response.strip())
        if hasattr(self, "_lbl_pl_status"):
            self._pl_set_status(f"Generado con backend local ({mode})")
        self._log(f"[Prompt Lab] Respuesta generada via backend local ({mode})")

    def _pl_on_backend_error(self, exc: Exception) -> None:
        self._pl_generation_in_progress = False
        self._btn_generate.configure(state="normal")
        msg = str(exc)
        if isinstance(exc, PromptLabBackendError):
            msg = str(exc)
        if hasattr(self, "_lbl_pl_status"):
            self._pl_set_status("Error al generar")
        self._log(f"[Prompt Lab] Error backend: {msg}")
        messagebox.showerror(
            "Prompt Lab",
            "No fue posible generar con el backend local.\n\n"
            "Verifica URL/modelos y que el servidor este activo.\n\n"
            f"Detalle: {msg}",
        )

    def _yt_stub_action(self, action: str) -> None:
        labels = {
            "connect": "Conexion de canal",
            "refresh": "Refresco de estado",
            "suggest_schedule": "Sugerencia de calendario",
            "apply_all": "Aplicar en lote",
            "validate": "Validacion local",
            "sync": "Sincronizacion de borradores",
        }
        self._log(f"[YouTube] {labels.get(action, action)} listo para implementar.")

    def _yt_get_auth_service(self) -> YouTubeAuthService:
        if self._yt_auth_service is None:
            self._yt_auth_service = YouTubeAuthService()
        return self._yt_auth_service

    def _yt_has_linked_channel(self) -> bool:
        try:
            return bool(self._yt_get_auth_service().has_stored_credentials())
        except Exception:
            return False

    def _yt_require_channel_link(self, *, show_message: bool = True) -> bool:
        if self._yt_has_linked_channel():
            return True

        if callable(self._yt_activate_subtab):
            try:
                self._yt_activate_subtab("channel")
            except Exception:
                pass

        if show_message:
            msg = (
                "Debes enlazar tu canal de YouTube antes de usar la Cola o hacer Sync.\n\n"
                "Pulsa 'Conectar canal' en la pestaña Canal."
            )
            messagebox.showwarning("YouTube Publisher", msg)
            self._log("[YouTube] Accion bloqueada: no hay canal enlazado.")
        return False

    def _yt_on_subtab_activate(self, tab_name: str) -> bool:
        if tab_name != "queue":
            return True
        return self._yt_require_channel_link(show_message=True)

    def _yt_open_sync_modal(self, total: int) -> None:
        import customtkinter as _ctk8

        total = max(1, int(total))
        self._yt_sync_total = total

        modal = _ctk8.CTkToplevel(self)
        modal.title('Sync de borradores')
        w, h = 560, 250
        modal.geometry(f'{w}x{h}')
        modal.resizable(False, False)
        modal.grab_set()
        modal.focus_force()
        modal.configure(fg_color=C_BG)
        modal.protocol('WM_DELETE_WINDOW', lambda: None)
        _center_window_on_screen(modal)

        inner = _ctk8.CTkFrame(modal, fg_color='transparent')
        inner.pack(fill='both', expand=True, padx=20, pady=(16, 12))
        inner.grid_columnconfigure(0, weight=1)

        _ctk8.CTkLabel(
            inner,
            text='Sincronizando borradores con YouTube',
            text_color=C_TEXT,
            anchor='w',
            font=_ctk8.CTkFont(size=self._fs(14), weight='bold'),
        ).grid(row=0, column=0, sticky='ew', pady=(0, 10))

        self._yt_sync_status_var = tk.StringVar(value='Preparando envio...')
        _ctk8.CTkLabel(
            inner,
            textvariable=self._yt_sync_status_var,
            text_color=C_TEXT_DIM,
            anchor='w',
            justify='left',
            wraplength=500,
            font=_ctk8.CTkFont(size=self._fs(11)),
        ).grid(row=1, column=0, sticky='ew', pady=(0, 8))

        bar = _ctk8.CTkProgressBar(inner, height=12, corner_radius=999)
        bar.grid(row=2, column=0, sticky='ew', pady=(0, 8))
        bar.set(0)

        self._yt_sync_summary_var = tk.StringVar(value=f'0/{total} completados  |  OK: 0  |  Error: 0')
        _ctk8.CTkLabel(
            inner,
            textvariable=self._yt_sync_summary_var,
            text_color=C_MUTED,
            anchor='w',
            font=_ctk8.CTkFont(size=self._fs(10)),
        ).grid(row=3, column=0, sticky='ew')

        btns = _ctk8.CTkFrame(modal, fg_color='transparent')
        btns.pack(fill='x', padx=20, pady=(4, 16))
        close_btn = _ctk8.CTkButton(
            btns,
            text='Sincronizando...',
            fg_color='transparent',
            hover_color=C_HOVER,
            border_width=2,
            border_color=C_BORDER,
            text_color=C_TEXT_DIM,
            state='disabled',
            command=modal.destroy,
        )
        close_btn.pack(side='left')

        self._yt_sync_modal = modal
        self._yt_sync_progress = bar
        self._yt_sync_close_btn = close_btn

    def _yt_update_sync_modal(
        self,
        done: int,
        total: int,
        ok: int,
        fail: int,
        status: str,
    ) -> None:
        if self._yt_sync_status_var is not None:
            self._yt_sync_status_var.set(status)
        if self._yt_sync_summary_var is not None:
            self._yt_sync_summary_var.set(f'{done}/{total} completados  |  OK: {ok}  |  Error: {fail}')
        if self._yt_sync_progress is not None:
            self._yt_sync_progress.set(0 if total <= 0 else min(1.0, max(0.0, done / total)))

    def _yt_finish_sync_modal(self, *, ok: int, fail: int, total: int) -> None:
        final_status = (
            f'Sync finalizado. OK: {ok}, Error: {fail}.'
            if fail
            else f'Sync finalizado correctamente. OK: {ok} de {total}.'
        )
        self._yt_update_sync_modal(total, total, ok, fail, final_status)
        if self._yt_sync_close_btn is not None:
            self._yt_sync_close_btn.configure(
                text='Cerrar',
                state='normal',
                text_color=C_TEXT,
            )
        if self._yt_sync_modal is not None:
            try:
                self._yt_sync_modal.protocol('WM_DELETE_WINDOW', self._yt_sync_modal.destroy)
            except Exception:
                pass

    def _yt_restore_channel_cache_from_settings(self) -> None:
        self._yt_cached_channel_title = str(self.settings.get("yt_cached_channel_title", "") or "")
        self._yt_cached_channel_id = str(self.settings.get("yt_cached_channel_id", "") or "")
        self._yt_cached_channel_fetched_at = str(
            self.settings.get("yt_cached_channel_fetched_at", "") or ""
        )

        if hasattr(self, "_var_yt_channel_status"):
            if self._yt_cached_channel_title and self._yt_cached_channel_id:
                self._var_yt_channel_status.set(
                    f"Conectado (cache): {self._yt_cached_channel_title} ({self._yt_cached_channel_id})"
                )
            elif self._yt_get_auth_service().has_stored_credentials():
                self._var_yt_channel_status.set("Sesion guardada. Pulsa 'Refrescar estado'.")
            else:
                self._var_yt_channel_status.set("No conectado.")

        self._yt_update_cache_status_label()

    def _yt_channel_cache_age_minutes(self) -> int | None:
        if not self._yt_cached_channel_fetched_at:
            return None
        try:
            parsed = dt.datetime.fromisoformat(self._yt_cached_channel_fetched_at)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            now_utc = dt.datetime.now(dt.timezone.utc)
            age = now_utc - parsed.astimezone(dt.timezone.utc)
            return max(0, int(age.total_seconds() // 60))
        except Exception:
            return None

    def _yt_is_channel_cache_stale(self) -> bool:
        age = self._yt_channel_cache_age_minutes()
        if age is None:
            return True
        return age >= self.YT_CHANNEL_CACHE_TTL_MINUTES

    def _yt_update_cache_status_label(self) -> None:
        if not hasattr(self, "_var_yt_cache_status"):
            return

        if not self._yt_cached_channel_fetched_at:
            self._var_yt_cache_status.set("Cache: sin datos. Pulsa 'Refrescar estado' para consultar.")
            return

        age = self._yt_channel_cache_age_minutes()
        if age is None:
            self._var_yt_cache_status.set("Cache: fecha invalida. Pulsa 'Refrescar estado'.")
            return

        if age == 0:
            age_text = "hace menos de 1 minuto"
        elif age == 1:
            age_text = "hace 1 minuto"
        else:
            age_text = f"hace {age} minutos"

        if self._yt_is_channel_cache_stale():
            self._var_yt_cache_status.set(
                f"Cache vencida ({age_text}). Pulsa 'Refrescar estado' para actualizar."
            )
        else:
            self._var_yt_cache_status.set(
                f"Cache vigente ({age_text}). Consultas solo bajo demanda."
            )

    def _yt_save_channel_cache(self, *, title: str, channel_id: str) -> None:
        previous_channel_id = self._yt_cached_channel_id
        self._yt_cached_channel_title = title
        self._yt_cached_channel_id = channel_id
        self._yt_cached_channel_fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
        self.settings.update(
            {
                "yt_cached_channel_title": self._yt_cached_channel_title,
                "yt_cached_channel_id": self._yt_cached_channel_id,
                "yt_cached_channel_fetched_at": self._yt_cached_channel_fetched_at,
            }
        )
        try:
            self.settings.save()
        except Exception:
            pass
        self._yt_update_cache_status_label()

        if previous_channel_id and previous_channel_id != channel_id:
            # Different account/channel: queue cache from previous channel is no longer valid.
            self._yt_clear_drafts_cache(clear_rows=True)

    def _yt_clear_channel_cache(self) -> None:
        self._yt_cached_channel_title = ""
        self._yt_cached_channel_id = ""
        self._yt_cached_channel_fetched_at = ""
        self.settings.update(
            {
                "yt_cached_channel_title": "",
                "yt_cached_channel_id": "",
                "yt_cached_channel_fetched_at": "",
            }
        )
        try:
            self.settings.save()
        except Exception:
            pass
        self._yt_update_cache_status_label()

    def _yt_restore_drafts_cache_from_settings(self) -> None:
        raw_rows = self.settings.get("yt_cached_drafts_rows", [])
        if not isinstance(raw_rows, list):
            raw_rows = []

        normalized: list[dict[str, str]] = []
        for item in raw_rows:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "video_id": str(item.get("video_id", "") or ""),
                    "path": str(item.get("path", "") or ""),
                    "title": str(item.get("title", "") or ""),
                    "category": str(item.get("category", "Music") or "Music"),
                    "kids": "Si" if str(item.get("kids", "No") or "No") == "Si" else "No",
                    "schedule": str(item.get("schedule", "") or ""),
                    "description": str(item.get("description", "") or ""),
                    "tags": str(item.get("tags", "") or ""),
                    "playlist_id": str(item.get("playlist_id", "") or ""),
                    "playlist_title": str(item.get("playlist_title", "") or ""),
                }
            )

        self._yt_video_rows = normalized
        self._yt_cached_drafts_fetched_at = str(
            self.settings.get("yt_cached_drafts_fetched_at", "") or ""
        )
        self._yt_update_queue_cache_status_label()

    def _yt_drafts_cache_age_minutes(self) -> int | None:
        if not self._yt_cached_drafts_fetched_at:
            return None
        try:
            parsed = dt.datetime.fromisoformat(self._yt_cached_drafts_fetched_at)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            now_utc = dt.datetime.now(dt.timezone.utc)
            age = now_utc - parsed.astimezone(dt.timezone.utc)
            return max(0, int(age.total_seconds() // 60))
        except Exception:
            return None

    def _yt_is_drafts_cache_stale(self) -> bool:
        age = self._yt_drafts_cache_age_minutes()
        if age is None:
            return True
        return age >= self.YT_DRAFTS_CACHE_TTL_MINUTES

    def _yt_update_queue_cache_status_label(self) -> None:
        if not hasattr(self, "_var_yt_queue_cache_status"):
            return

        row_count = len(self._yt_video_rows)
        if not self._yt_cached_drafts_fetched_at:
            if row_count:
                self._var_yt_queue_cache_status.set(
                    f"Cola: {row_count} video(s) cargados localmente sin marca de consulta."
                )
            else:
                self._var_yt_queue_cache_status.set(
                    "Cola: sin cache. Pulsa 'Obtener borradores'."
                )
            return

        age = self._yt_drafts_cache_age_minutes()
        if age is None:
            self._var_yt_queue_cache_status.set(
                "Cola: cache con fecha invalida. Pulsa 'Obtener borradores'."
            )
            return

        if age == 0:
            age_text = "hace menos de 1 minuto"
        elif age == 1:
            age_text = "hace 1 minuto"
        else:
            age_text = f"hace {age} minutos"

        if self._yt_is_drafts_cache_stale():
            self._var_yt_queue_cache_status.set(
                f"Cola cache vencida ({age_text}) con {row_count} video(s). Pulsa 'Obtener borradores' para actualizar."
            )
        else:
            self._var_yt_queue_cache_status.set(
                f"Cola cache vigente ({age_text}) con {row_count} video(s)."
            )

    def _yt_save_drafts_cache(self) -> None:
        serializable_rows = [dict(row) for row in self._yt_video_rows]
        self._yt_cached_drafts_fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
        self.settings.update(
            {
                "yt_cached_drafts_rows": serializable_rows,
                "yt_cached_drafts_fetched_at": self._yt_cached_drafts_fetched_at,
            }
        )
        try:
            self.settings.save()
        except Exception:
            pass
        self._yt_update_queue_cache_status_label()

    def _yt_mark_drafts_cache_stale(self) -> None:
        stale_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(
            minutes=self.YT_DRAFTS_CACHE_TTL_MINUTES + 1
        )
        self._yt_cached_drafts_fetched_at = stale_at.isoformat()
        self.settings.update(
            {
                "yt_cached_drafts_rows": [dict(row) for row in self._yt_video_rows],
                "yt_cached_drafts_fetched_at": self._yt_cached_drafts_fetched_at,
            }
        )
        try:
            self.settings.save()
        except Exception:
            pass
        self._yt_update_queue_cache_status_label()

    def _yt_clear_drafts_cache(self, *, clear_rows: bool) -> None:
        if clear_rows:
            self._yt_video_rows = []
        self._yt_cached_drafts_fetched_at = ""
        self.settings.update(
            {
                "yt_cached_drafts_rows": [],
                "yt_cached_drafts_fetched_at": "",
            }
        )
        try:
            self.settings.save()
        except Exception:
            pass
        self._yt_update_queue_cache_status_label()

    def _yt_restore_playlists_cache_from_settings(self) -> None:
        raw = self.settings.get("yt_cached_playlists", [])
        if not isinstance(raw, list):
            raw = []

        playlists: list[dict[str, str]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("id", "") or "").strip()
            title = str(item.get("title", "") or "").strip()
            if not pid:
                continue
            playlists.append({"id": pid, "title": title or pid})

        playlists.sort(key=lambda x: (x.get("title", "") or "").lower())
        self._yt_cached_playlists = playlists
        self._yt_cached_playlists_fetched_at = str(
            self.settings.get("yt_cached_playlists_fetched_at", "") or ""
        )

    def _yt_playlists_cache_age_minutes(self) -> int | None:
        if not self._yt_cached_playlists_fetched_at:
            return None
        try:
            parsed = dt.datetime.fromisoformat(self._yt_cached_playlists_fetched_at)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            now_utc = dt.datetime.now(dt.timezone.utc)
            age = now_utc - parsed.astimezone(dt.timezone.utc)
            return max(0, int(age.total_seconds() // 60))
        except Exception:
            return None

    def _yt_is_playlists_cache_stale(self) -> bool:
        age = self._yt_playlists_cache_age_minutes()
        if age is None:
            return True
        return age >= self.YT_PLAYLISTS_CACHE_TTL_MINUTES

    def _yt_playlists_cache_status_text(self) -> str:
        count = len(self._yt_cached_playlists)
        age = self._yt_playlists_cache_age_minutes()
        if not self._yt_cached_playlists_fetched_at:
            return f"Sin cache de playlists. Hay {count} en memoria local."
        if age is None:
            return f"Cache de playlists con fecha invalida ({count} item(s))."
        if age == 0:
            age_text = "hace menos de 1 minuto"
        elif age == 1:
            age_text = "hace 1 minuto"
        else:
            age_text = f"hace {age} minutos"
        if self._yt_is_playlists_cache_stale():
            return f"Cache de playlists vencida ({age_text}) con {count} item(s)."
        return f"Cache de playlists vigente ({age_text}) con {count} item(s)."

    def _yt_save_playlists_cache(self, playlists: list[dict[str, str]]) -> None:
        normalized: list[dict[str, str]] = []
        for item in playlists:
            pid = str(item.get("id", "") or "").strip()
            title = str(item.get("title", "") or "").strip()
            if not pid:
                continue
            normalized.append({"id": pid, "title": title or pid})
        normalized.sort(key=lambda x: (x.get("title", "") or "").lower())

        self._yt_cached_playlists = normalized
        self._yt_cached_playlists_fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
        self.settings.update(
            {
                "yt_cached_playlists": [dict(x) for x in normalized],
                "yt_cached_playlists_fetched_at": self._yt_cached_playlists_fetched_at,
            }
        )
        try:
            self.settings.save()
        except Exception:
            pass

    def _yt_fetch_playlists_and_cache(self) -> bool:
        if not self._yt_require_channel_link(show_message=True):
            return False
        self._log("[YouTube] Consultando playlists del canal...")
        try:
            playlists = self._yt_get_auth_service().list_my_playlists(limit=200)
        except YouTubeAuthError as exc:
            self._log(f"[YouTube] {exc}")
            messagebox.showwarning("YouTube Publisher", str(exc))
            return False
        except Exception as exc:
            self._log(f"[YouTube] Error al consultar playlists: {exc}")
            messagebox.showwarning("YouTube Publisher", f"Error al consultar playlists: {exc}")
            return False

        self._yt_save_playlists_cache(playlists)
        self._log(f"[YouTube] Playlists cacheadas: {len(self._yt_cached_playlists)} item(s).")
        return True

    def _yt_playlist_options(self) -> list[str]:
        options = ["Sin playlist (no asignar)"]
        for p in self._yt_cached_playlists:
            title = (p.get("title") or "").strip() or p.get("id", "")
            pid = (p.get("id") or "").strip()
            if not pid:
                continue
            options.append(f"{title} [{pid}]")
        return options

    def _yt_playlist_label_to_data(self, label: str) -> tuple[str, str]:
        label = (label or "").strip()
        if not label or label == "Sin playlist (no asignar)":
            return "", ""
        for p in self._yt_cached_playlists:
            pid = (p.get("id") or "").strip()
            title = (p.get("title") or "").strip() or pid
            if label == f"{title} [{pid}]":
                return pid, title
        if label.endswith("]") and "[" in label:
            title_part, id_part = label.rsplit("[", 1)
            pid = id_part[:-1].strip()
            title = title_part.strip()
            if pid:
                return pid, (title or pid)
        return "", ""

    def _yt_playlist_data_to_label(self, playlist_id: str, playlist_title: str = "") -> str:
        pid = (playlist_id or "").strip()
        if not pid:
            return "Sin playlist (no asignar)"
        for p in self._yt_cached_playlists:
            if (p.get("id") or "").strip() == pid:
                title = (p.get("title") or "").strip() or pid
                return f"{title} [{pid}]"
        title = (playlist_title or "").strip() or pid
        return f"{title} [{pid}]"

    def _yt_open_playlists_modal(self) -> None:
        import customtkinter as _ctk7

        modal = _ctk7.CTkToplevel(self)
        modal.title('Playlists del canal')
        w, h = 640, 420
        modal.geometry(f'{w}x{h}')
        modal.resizable(True, True)
        modal.grab_set()
        modal.focus_force()
        modal.configure(fg_color=C_BG)
        _center_window_on_screen(modal)

        inner = _ctk7.CTkFrame(modal, fg_color='transparent')
        inner.pack(fill='both', expand=True, padx=20, pady=(16, 8))
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(2, weight=1)

        _ctk7.CTkLabel(
            inner,
            text='Playlists',
            text_color=C_TEXT,
            anchor='w',
            font=_ctk7.CTkFont(size=self._fs(14), weight='bold'),
        ).grid(row=0, column=0, sticky='ew', pady=(0, 6))

        status_var = tk.StringVar(value=self._yt_playlists_cache_status_text())
        _ctk7.CTkLabel(
            inner,
            textvariable=status_var,
            text_color=C_MUTED,
            anchor='w',
            justify='left',
            wraplength=560,
            font=_ctk7.CTkFont(size=self._fs(10)),
        ).grid(row=1, column=0, sticky='ew', pady=(0, 8))

        list_box = _ctk7.CTkScrollableFrame(inner, fg_color=C_CARD)
        list_box.grid(row=2, column=0, sticky='nsew')
        list_box.grid_columnconfigure(0, weight=1)

        def _render_items() -> None:
            for wdg in list_box.winfo_children():
                wdg.destroy()
            if not self._yt_cached_playlists:
                _ctk7.CTkLabel(
                    list_box,
                    text='No hay playlists cacheadas. Pulsa "Recargar playlists".',
                    text_color=C_TEXT_DIM,
                    anchor='w',
                    justify='left',
                    font=_ctk7.CTkFont(size=self._fs(11)),
                ).grid(row=0, column=0, sticky='ew', padx=8, pady=8)
                return
            for idx, p in enumerate(self._yt_cached_playlists):
                title = (p.get('title') or '').strip() or (p.get('id') or '').strip()
                pid = (p.get('id') or '').strip()
                _ctk7.CTkLabel(
                    list_box,
                    text=f'{title} [{pid}]',
                    text_color=C_TEXT,
                    anchor='w',
                    justify='left',
                    wraplength=560,
                    font=_ctk7.CTkFont(size=self._fs(11)),
                ).grid(row=idx, column=0, sticky='ew', padx=8, pady=4)

        _render_items()

        btns = _ctk7.CTkFrame(modal, fg_color='transparent')
        btns.pack(fill='x', padx=20, pady=(8, 16))

        def _reload() -> None:
            if self._yt_fetch_playlists_and_cache():
                status_var.set(self._yt_playlists_cache_status_text())
                _render_items()

        _ctk7.CTkButton(
            btns,
            text='Recargar playlists',
            fg_color=C_ACCENT_YT,
            hover_color=C_ACCENT_YT_H,
            text_color='#FFFFFF',
            command=_reload,
        ).pack(side='left', padx=(0, 8))
        _ctk7.CTkButton(
            btns,
            text='Cerrar',
            fg_color='transparent',
            hover_color=C_HOVER,
            border_width=2,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=modal.destroy,
        ).pack(side='left')

    def _yt_merge_drafts_preserving_local(
        self,
        fresh_rows: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], int, int]:
        """Merge fresh API rows with local queue by video_id, preserving local edits.

        Returns:
            merged_rows, preserved_count, dropped_local_count
        """
        editable_keys = (
            "title",
            "category",
            "kids",
            "schedule",
            "description",
            "tags",
            "playlist_id",
            "playlist_title",
        )
        local_by_id: dict[str, dict[str, str]] = {}
        for row in self._yt_video_rows:
            vid = (row.get("video_id") or "").strip()
            if vid:
                local_by_id[vid] = row

        merged: list[dict[str, str]] = []
        preserved = 0
        seen_ids: set[str] = set()

        for fresh in fresh_rows:
            vid = (fresh.get("video_id") or "").strip()
            if not vid:
                merged.append(fresh)
                continue

            seen_ids.add(vid)
            local = local_by_id.get(vid)
            if not local:
                merged.append(fresh)
                continue

            row = dict(fresh)
            for key in editable_keys:
                local_val = local.get(key)
                if local_val is not None:
                    row[key] = local_val
            merged.append(row)
            preserved += 1

        dropped_local = len([vid for vid in local_by_id.keys() if vid not in seen_ids])
        return merged, preserved, dropped_local

    def _yt_fetch_drafts_with_merge(self, *, source_label: str = "manual") -> bool:
        """Fetch drafts from API and merge with local queue preserving user edits.

        Returns:
            True if refresh succeeded, False otherwise.
        """
        if not self._yt_require_channel_link(show_message=True):
            return False
        self._log("[YouTube] Consultando borradores privados sin fecha...")
        try:
            fresh_rows = self._yt_get_auth_service().list_private_unscheduled_drafts(limit=200)
        except YouTubeAuthError as exc:
            self._log(f"[YouTube] {exc}")
            self._yt_update_queue_cache_status_label()
            messagebox.showwarning("YouTube Publisher", str(exc))
            return False
        except Exception as exc:
            self._log(f"[YouTube] Error al cargar borradores: {exc}")
            self._yt_update_queue_cache_status_label()
            messagebox.showwarning("YouTube Publisher", f"Error al cargar borradores: {exc}")
            return False

        merged_rows, preserved, dropped = self._yt_merge_drafts_preserving_local(fresh_rows)
        self._yt_video_rows = merged_rows
        self._yt_save_drafts_cache()
        self._yt_render_queue_preview()

        self._log(
            f"[YouTube] Cola actualizada ({source_label}): {len(merged_rows)} video(s), "
            f"progreso conservado en {preserved}, removidos {dropped} que ya no estaban elegibles."
        )
        return True

    def _yt_refresh_channel_status(self, silent: bool = False) -> None:
        """Refresh channel status label using stored OAuth credentials if available."""
        if not hasattr(self, "_var_yt_channel_status"):
            return

        service = self._yt_get_auth_service()
        try:
            if not service.has_stored_credentials():
                self._var_yt_channel_status.set("No conectado.")
                self._yt_clear_channel_cache()
                if not silent:
                    self._log("[YouTube] No hay sesion guardada. Pulsa 'Conectar canal'.")
                return

            info = service.get_channel_info()
            self._var_yt_channel_status.set(
                f"Conectado: {info.title} ({info.channel_id})"
            )
            self._yt_save_channel_cache(title=info.title, channel_id=info.channel_id)
            if not silent:
                self._log(f"[YouTube] Canal activo: {info.title}")
        except YouTubeAuthError as exc:
            if self._yt_cached_channel_title and self._yt_cached_channel_id:
                self._var_yt_channel_status.set(
                    f"Conectado (cache): {self._yt_cached_channel_title} ({self._yt_cached_channel_id})"
                )
            else:
                self._var_yt_channel_status.set("No conectado.")
            self._yt_update_cache_status_label()
            if not silent:
                self._log(f"[YouTube] {exc}")
        except Exception as exc:
            if self._yt_cached_channel_title and self._yt_cached_channel_id:
                self._var_yt_channel_status.set(
                    f"Conectado (cache): {self._yt_cached_channel_title} ({self._yt_cached_channel_id})"
                )
            else:
                self._var_yt_channel_status.set("No conectado.")
            self._yt_update_cache_status_label()
            if not silent:
                self._log(f"[YouTube] Error inesperado al refrescar canal: {exc}")

    def _yt_connect_channel(self) -> None:
        """Run OAuth flow and update channel status in UI."""
        if self._yt_auth_in_progress:
            return

        self._yt_auth_in_progress = True
        self._yt_open_auth_dialog(
            "Conectando con YouTube...",
            "Se abrira el navegador para completar OAuth.",
        )
        self._log("[YouTube] Iniciando autenticacion OAuth...")
        threading.Thread(target=self._yt_connect_channel_worker, daemon=True).start()

    def _yt_open_auth_dialog(self, headline: str, detail: str) -> None:
        if self._yt_auth_dialog and self._yt_auth_dialog.winfo_exists():
            self._yt_auth_dialog.close()
        self._yt_auth_dialog = BusyDialog(
            self,
            title="YouTube Publisher",
            headline=headline,
            detail=detail,
        )

    def _yt_close_auth_dialog(self) -> None:
        dialog = self._yt_auth_dialog
        self._yt_auth_dialog = None
        if dialog and dialog.winfo_exists():
            dialog.close()

    def _yt_connect_channel_worker(self) -> None:
        service = self._yt_get_auth_service()
        try:
            service.authenticate_interactive()
        except Exception as exc:
            self.after(0, self._yt_finish_connect_channel, exc)
            return

        self.after(0, self._yt_finish_connect_channel, None)

    def _yt_finish_connect_channel(self, error: Exception | None) -> None:
        self._yt_close_auth_dialog()
        self._yt_auth_in_progress = False

        try:
            self.deiconify()
            self.lift()
            self.focus_force()
        except tk.TclError:
            pass

        if error is None:
            self._log("[YouTube] Autenticacion completada. Verificando canal...")
            self._yt_refresh_channel_status(silent=False)
            return

        if isinstance(error, YouTubeAuthError):
            msg = str(error)
        else:
            msg = f"Error durante la autenticacion de YouTube: {error}"

        self._var_yt_channel_status.set("No conectado.")
        self._yt_update_cache_status_label()
        self._log(f"[YouTube] {msg}")
        messagebox.showerror("YouTube Publisher", msg)

    def _yt_fetch_drafts(self) -> None:
        """Load private videos without publishAt from YouTube into queue preview."""
        self._yt_fetch_drafts_with_merge(source_label="manual")

    def _yt_open_bulk_modal(self) -> None:
        self._yt_restore_playlists_cache_from_settings()
        modal = __import__('customtkinter').CTkToplevel(self)
        modal.title('Metadatos en lote')
        modal.geometry('600x620')
        modal.resizable(False, False)
        modal.grab_set()
        modal.focus_force()
        _center_window_on_screen(modal)
        modal.configure(fg_color=C_BG)
        inner = __import__('customtkinter').CTkFrame(modal, fg_color='transparent')
        inner.pack(fill='both', expand=True, padx=20, pady=(16, 8))
        inner.grid_columnconfigure(0, weight=1)
        import tkinter as _tk2
        import customtkinter as _ctk2
        _ctk2.CTkLabel(inner, text='Metadatos en lote', anchor='w',
            text_color=C_TEXT, font=_ctk2.CTkFont(size=self._fs(14), weight='bold'),
        ).grid(row=0, column=0, sticky='ew', pady=(0, 12))
        _lbl = dict(text_color=C_MUTED, anchor='w', font=_ctk2.CTkFont(size=self._fs(11)))
        _opt = dict(fg_color=C_INPUT, button_color=C_ACCENT_YT, button_hover_color=C_ACCENT_YT_H,
            text_color=C_TEXT, dropdown_fg_color=C_CARD, dropdown_text_color=C_TEXT, dropdown_hover_color=C_HOVER)
        _ctk2.CTkLabel(inner, text='Titulo (mismo para todos, opcional)', **_lbl).grid(row=1, column=0, sticky='ew', pady=(0,4))
        _var_title_all = _tk2.StringVar()
        _ctk2.CTkEntry(
            inner,
            textvariable=_var_title_all,
            placeholder_text='Ej: Deep Focus Session',
            fg_color=C_INPUT,
            border_color=C_BORDER,
            text_color=C_TEXT,
            height=34,
        ).grid(row=2, column=0, sticky='ew', pady=(0,10))

        playlist_options = self._yt_playlist_options()
        _ctk2.CTkLabel(inner, text='Playlist (opcional)', **_lbl).grid(row=3, column=0, sticky='ew', pady=(0,4))
        _var_playlist = _tk2.StringVar(value='Sin playlist (no asignar)')
        _ctk2.CTkOptionMenu(
            inner,
            variable=_var_playlist,
            values=playlist_options,
            **_opt,
        ).grid(row=4, column=0, sticky='ew', pady=(0,10))

        _ctk2.CTkLabel(inner, text='Categoria', **_lbl).grid(row=5, column=0, sticky='ew', pady=(0,4))
        _var_cat = _tk2.StringVar(value=self._var_yt_default_category.get() if hasattr(self,'_var_yt_default_category') else 'Music')
        _ctk2.CTkOptionMenu(inner, variable=_var_cat,
            values=['Music','Entertainment','People & Blogs','Education','Film & Animation','Howto & Style','Gaming','Science & Technology','News & Politics','Sports'],
            **_opt).grid(row=6, column=0, sticky='ew', pady=(0,10))
        _var_kids = _tk2.BooleanVar(value=False)
        _ctk2.CTkCheckBox(inner, text='Hecho para ninos', variable=_var_kids,
            fg_color=C_ACCENT_YT, hover_color=C_ACCENT_YT_H, text_color=C_TEXT,
            font=_ctk2.CTkFont(size=self._fs(11))).grid(row=7, column=0, sticky='w', pady=(0,10))
        _ctk2.CTkLabel(inner, text='Descripcion (se aplica a todos los videos)', **_lbl).grid(row=8, column=0, sticky='ew', pady=(0,4))
        _txt_desc = _ctk2.CTkTextbox(inner, height=120, fg_color=C_INPUT,
            border_width=1, border_color=C_BORDER, text_color=C_TEXT, font=_ctk2.CTkFont(size=self._fs(11)))
        _txt_desc.grid(row=9, column=0, sticky='ew', pady=(0,10))
        _ctk2.CTkLabel(inner, text='Tags (separados por coma)', **_lbl).grid(row=10, column=0, sticky='ew', pady=(0,4))
        _var_tags = _tk2.StringVar()
        _ctk2.CTkEntry(inner, textvariable=_var_tags, placeholder_text='lofi, music, chill...',
            fg_color=C_INPUT, border_color=C_BORDER, text_color=C_TEXT, height=45).grid(row=11, column=0, sticky='ew', pady=(0,4))
        btns = _ctk2.CTkFrame(modal, fg_color='transparent')
        btns.pack(fill='x', padx=20, pady=(0,16))
        def _apply_bulk():
            title_all = _var_title_all.get().strip()
            desc = _txt_desc.get('1.0','end').strip()
            cat = _var_cat.get()
            kids = _var_kids.get()
            tags_raw = _var_tags.get().strip()
            selected_playlist_id, selected_playlist_title = self._yt_playlist_label_to_data(_var_playlist.get())
            for row in self._yt_video_rows:
                if title_all:
                    row['title'] = title_all
                row['category'] = cat
                row['kids'] = 'Si' if kids else 'No'
                row['playlist_id'] = selected_playlist_id
                row['playlist_title'] = selected_playlist_title
                if desc: row['description'] = desc
                if tags_raw: row['tags'] = tags_raw
            self._yt_save_drafts_cache()
            self._yt_render_queue_preview()
            self._log(f"[YouTube] Metadatos en lote aplicados a {len(self._yt_video_rows)} video(s).")
            modal.destroy()
        _ctk2.CTkButton(btns, text='Aplicar a cola', fg_color=C_ACCENT_YT, hover_color=C_ACCENT_YT_H,
            text_color='#FFFFFF', command=_apply_bulk).pack(side='left', padx=(0,8))
        _ctk2.CTkButton(btns, text='Cancelar', fg_color='transparent', hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER, text_color=C_TEXT, command=modal.destroy).pack(side='left')

    def _yt_open_schedule_modal(self) -> None:
        import calendar as _cal
        import datetime as _dt
        import tkinter as _tk3
        import customtkinter as _ctk3
        modal = _ctk3.CTkToplevel(self)
        modal.title('Programar publicacion')
        modal.geometry('440x360')
        modal.resizable(False, False)
        modal.grab_set()
        modal.focus_force()
        _center_window_on_screen(modal)
        modal.configure(fg_color=C_BG)
        inner = _ctk3.CTkFrame(modal, fg_color='transparent')
        inner.pack(fill='both', expand=True, padx=20, pady=(16, 8))
        inner.grid_columnconfigure(1, weight=1)
        _ctk3.CTkLabel(inner, text='Programar publicacion', anchor='w',
            text_color=C_TEXT, font=_ctk3.CTkFont(size=self._fs(14), weight='bold'),
        ).grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0,12))
        _lbl = dict(text_color=C_MUTED, anchor='w', font=_ctk3.CTkFont(size=self._fs(11)))
        _ent = dict(fg_color=C_INPUT, border_color=C_BORDER, text_color=C_TEXT, height=30)
        tz_val = self._var_yt_timezone.get() if hasattr(self,'_var_yt_timezone') else 'America/Los_Angeles'
        _ctk3.CTkLabel(inner, text='Zona horaria', **_lbl).grid(row=1, column=0, sticky='w', padx=(0,10), pady=(0,6))
        _ctk3.CTkLabel(inner, text=tz_val, text_color=C_TEXT, anchor='w', font=_ctk3.CTkFont(size=self._fs(11))).grid(row=1, column=1, sticky='ew', pady=(0,6))
        vpd_val = self._var_yt_videos_per_day.get() if hasattr(self,'_var_yt_videos_per_day') else '3'
        _var_vpd = _tk3.StringVar(value=vpd_val)
        _ctk3.CTkLabel(inner, text='Videos por dia', **_lbl).grid(row=2, column=0, sticky='w', padx=(0,10), pady=(0,6))
        _ctk3.CTkOptionMenu(inner, variable=_var_vpd, values=['1','2','3','4','5','6'],
            fg_color=C_INPUT, button_color=C_ACCENT_YT, button_hover_color=C_ACCENT_YT_H,
            text_color=C_TEXT, dropdown_fg_color=C_CARD, dropdown_text_color=C_TEXT, dropdown_hover_color=C_HOVER,
        ).grid(row=2, column=1, sticky='ew', pady=(0,6))
        today = _dt.date.today()
        _var_year = _tk3.StringVar(value=str(today.year))
        _var_month = _tk3.StringVar(value=f"{today.month:02d}")
        _var_day = _tk3.StringVar(value=f"{today.day:02d}")
        _years = [str(y) for y in range(today.year, today.year + 6)]
        _months = [f"{m:02d}" for m in range(1, 13)]

        _ctk3.CTkLabel(inner, text='Fecha inicial', **_lbl).grid(row=3, column=0, sticky='w', padx=(0,10), pady=(0,6))
        _date_row = _ctk3.CTkFrame(inner, fg_color='transparent')
        _date_row.grid(row=3, column=1, sticky='ew', pady=(0,6))
        _om_year = _ctk3.CTkOptionMenu(
            _date_row,
            variable=_var_year,
            values=_years,
            width=92,
            fg_color=C_INPUT,
            button_color=C_ACCENT_YT,
            button_hover_color=C_ACCENT_YT_H,
            text_color=C_TEXT,
            dropdown_fg_color=C_CARD,
            dropdown_text_color=C_TEXT,
            dropdown_hover_color=C_HOVER,
            dynamic_resizing=False,
        )
        _om_year.pack(side='left')
        _ctk3.CTkLabel(_date_row, text='-', text_color=C_TEXT_DIM).pack(side='left', padx=4)
        _om_month = _ctk3.CTkOptionMenu(
            _date_row,
            variable=_var_month,
            values=_months,
            width=72,
            fg_color=C_INPUT,
            button_color=C_ACCENT_YT,
            button_hover_color=C_ACCENT_YT_H,
            text_color=C_TEXT,
            dropdown_fg_color=C_CARD,
            dropdown_text_color=C_TEXT,
            dropdown_hover_color=C_HOVER,
            dynamic_resizing=False,
        )
        _om_month.pack(side='left')
        _ctk3.CTkLabel(_date_row, text='-', text_color=C_TEXT_DIM).pack(side='left', padx=4)
        _om_day = _ctk3.CTkOptionMenu(
            _date_row,
            variable=_var_day,
            values=[f"{d:02d}" for d in range(1, 32)],
            width=72,
            fg_color=C_INPUT,
            button_color=C_ACCENT_YT,
            button_hover_color=C_ACCENT_YT_H,
            text_color=C_TEXT,
            dropdown_fg_color=C_CARD,
            dropdown_text_color=C_TEXT,
            dropdown_hover_color=C_HOVER,
            dynamic_resizing=False,
        )
        _om_day.pack(side='left')

        def _refresh_day_values(_: str | None = None) -> None:
            try:
                yy = int(_var_year.get())
                mm = int(_var_month.get())
                max_day = _cal.monthrange(yy, mm)[1]
            except Exception:
                return

            day_values = [f"{d:02d}" for d in range(1, max_day + 1)]
            _om_day.configure(values=day_values)
            try:
                dd = int(_var_day.get())
                if dd > max_day:
                    _var_day.set(f"{max_day:02d}")
            except Exception:
                _var_day.set(day_values[0])

        _om_year.configure(command=_refresh_day_values)
        _om_month.configure(command=_refresh_day_values)
        _refresh_day_values()

        st = self._var_yt_window_start.get() if hasattr(self,'_var_yt_window_start') else '09:00'
        try:
            _default_h, _default_m = [int(x) for x in st.split(':', 1)]
        except Exception:
            _default_h, _default_m = 9, 0
        _var_hour = _tk3.StringVar(value=f"{_default_h:02d}")
        _var_minute = _tk3.StringVar(value=f"{_default_m:02d}")

        _ctk3.CTkLabel(inner, text='Hora de inicio', **_lbl).grid(row=4, column=0, sticky='w', padx=(0,10), pady=(0,6))
        _time_row = _ctk3.CTkFrame(inner, fg_color='transparent')
        _time_row.grid(row=4, column=1, sticky='w', pady=(0,10))
        _ctk3.CTkOptionMenu(
            _time_row,
            variable=_var_hour,
            values=[f"{h:02d}" for h in range(0, 24)],
            width=72,
            fg_color=C_INPUT,
            button_color=C_ACCENT_YT,
            button_hover_color=C_ACCENT_YT_H,
            text_color=C_TEXT,
            dropdown_fg_color=C_CARD,
            dropdown_text_color=C_TEXT,
            dropdown_hover_color=C_HOVER,
            dynamic_resizing=False,
        ).pack(side='left')
        _ctk3.CTkLabel(_time_row, text=':', text_color=C_TEXT, font=_ctk3.CTkFont(size=self._fs(12), weight='bold')).pack(side='left', padx=4)
        _ctk3.CTkOptionMenu(
            _time_row,
            variable=_var_minute,
            values=[f"{m:02d}" for m in range(0, 60)],
            width=72,
            fg_color=C_INPUT,
            button_color=C_ACCENT_YT,
            button_hover_color=C_ACCENT_YT_H,
            text_color=C_TEXT,
            dropdown_fg_color=C_CARD,
            dropdown_text_color=C_TEXT,
            dropdown_hover_color=C_HOVER,
            dynamic_resizing=False,
        ).pack(side='left')
        n_v = len(self._yt_video_rows) if hasattr(self,'_yt_video_rows') else 0
        _ctk3.CTkLabel(inner, text=f'{n_v} video(s) en cola.', text_color=C_TEXT_DIM,
            anchor='w', font=_ctk3.CTkFont(size=self._fs(10))).grid(row=5, column=0, columnspan=2, sticky='ew')
        btns = _ctk3.CTkFrame(modal, fg_color='transparent')
        btns.pack(fill='x', padx=20, pady=(0,16))
        def _apply_sch():
            try:
                if not self._yt_video_rows:
                    messagebox.showwarning("YouTube Publisher", "No hay videos en cola para programar.")
                    return

                start_date = _dt.date(int(_var_year.get()), int(_var_month.get()), int(_var_day.get()))
                videos_per_day = max(1, int(_var_vpd.get()))
                start_h = int(_var_hour.get())
                start_m = int(_var_minute.get())
                end_h, end_m = [int(x) for x in self._var_yt_window_end.get().split(":", 1)]
            except Exception:
                messagebox.showwarning(
                    "YouTube Publisher",
                    "Valores de programacion invalidos. Revisa fecha, hora y ventana horaria.",
                )
                return

            start_min = start_h * 60 + start_m
            end_min = end_h * 60 + end_m
            if end_min <= start_min:
                messagebox.showwarning(
                    "YouTube Publisher",
                    "La hora final debe ser mayor que la hora inicial en la ventana horaria.",
                )
                return

            if videos_per_day == 1:
                slot_minutes = [start_min]
            else:
                span = end_min - start_min
                step = span / (videos_per_day - 1)
                slot_minutes = [int(round(start_min + i * step)) for i in range(videos_per_day)]

            for idx, row in enumerate(self._yt_video_rows):
                day_offset = idx // videos_per_day
                slot_idx = idx % videos_per_day
                mins = slot_minutes[slot_idx]
                hh = mins // 60
                mm = mins % 60
                d = start_date + dt.timedelta(days=day_offset)
                row["schedule"] = f"{d.strftime('%Y-%m-%d')} {hh:02d}:{mm:02d}"

            self._yt_save_drafts_cache()
            self._yt_render_queue_preview()
            self._log(
                f"[YouTube] Programacion aplicada a {len(self._yt_video_rows)} video(s) "
                f"desde {start_date.isoformat()} ({tz_val})."
            )
            modal.destroy()
        _ctk3.CTkButton(btns, text='Aplicar', fg_color=C_ACCENT_YT, hover_color=C_ACCENT_YT_H,
            text_color='#FFFFFF', command=_apply_sch).pack(side='left', padx=(0,8))
        _ctk3.CTkButton(btns, text='Cancelar', fg_color='transparent', hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER, text_color=C_TEXT, command=modal.destroy).pack(side='left')

    def _yt_open_row_schedule_picker(self, row: dict[str, str]) -> None:
        """Open a compact date/time picker to edit a single row schedule safely."""
        import calendar as _cal
        import datetime as _dt
        import tkinter as _tk4
        import customtkinter as _ctk4

        modal = _ctk4.CTkToplevel(self)
        modal.title('Seleccionar fecha y hora')
        modal.geometry('420x260')
        modal.resizable(False, False)
        modal.grab_set()
        modal.focus_force()
        modal.update_idletasks()
        _center_window_on_screen(modal)
        modal.configure(fg_color=C_BG)

        now = _dt.datetime.now()
        current_schedule = (row.get("schedule") or "").strip()
        if current_schedule:
            try:
                parsed = _dt.datetime.strptime(current_schedule, "%Y-%m-%d %H:%M")
            except Exception:
                parsed = now
        else:
            parsed = now

        inner = _ctk4.CTkFrame(modal, fg_color='transparent')
        inner.pack(fill='both', expand=True, padx=20, pady=(16, 8))
        inner.grid_columnconfigure(1, weight=1)

        _lbl = dict(text_color=C_MUTED, anchor='w', font=_ctk4.CTkFont(size=self._fs(11)))
        _opt = dict(
            fg_color=C_INPUT,
            button_color=C_ACCENT_YT,
            button_hover_color=C_ACCENT_YT_H,
            text_color=C_TEXT,
            dropdown_fg_color=C_CARD,
            dropdown_text_color=C_TEXT,
            dropdown_hover_color=C_HOVER,
            dynamic_resizing=False,
        )

        _ctk4.CTkLabel(
            inner,
            text='Fecha y hora de publicacion',
            text_color=C_TEXT,
            anchor='w',
            font=_ctk4.CTkFont(size=self._fs(13), weight='bold'),
        ).grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0, 12))

        _var_year = _tk4.StringVar(value=str(parsed.year))
        _var_month = _tk4.StringVar(value=f"{parsed.month:02d}")
        _var_day = _tk4.StringVar(value=f"{parsed.day:02d}")
        _var_hour = _tk4.StringVar(value=f"{parsed.hour:02d}")
        _var_minute = _tk4.StringVar(value=f"{parsed.minute:02d}")

        _years = [str(y) for y in range(now.year, now.year + 6)]
        if str(parsed.year) not in _years:
            _years = [str(parsed.year)] + _years

        _ctk4.CTkLabel(inner, text='Fecha', **_lbl).grid(row=1, column=0, sticky='w', padx=(0, 10), pady=(0, 6))
        _date_row = _ctk4.CTkFrame(inner, fg_color='transparent')
        _date_row.grid(row=1, column=1, sticky='w', pady=(0, 6))

        _om_year = _ctk4.CTkOptionMenu(_date_row, variable=_var_year, values=_years, width=92, **_opt)
        _om_year.pack(side='left')
        _ctk4.CTkLabel(_date_row, text='-', text_color=C_TEXT_DIM).pack(side='left', padx=4)
        _om_month = _ctk4.CTkOptionMenu(
            _date_row,
            variable=_var_month,
            values=[f"{m:02d}" for m in range(1, 13)],
            width=72,
            **_opt,
        )
        _om_month.pack(side='left')
        _ctk4.CTkLabel(_date_row, text='-', text_color=C_TEXT_DIM).pack(side='left', padx=4)
        _om_day = _ctk4.CTkOptionMenu(
            _date_row,
            variable=_var_day,
            values=[f"{d:02d}" for d in range(1, 32)],
            width=72,
            **_opt,
        )
        _om_day.pack(side='left')

        def _refresh_day_values(_: str | None = None) -> None:
            try:
                yy = int(_var_year.get())
                mm = int(_var_month.get())
                max_day = _cal.monthrange(yy, mm)[1]
            except Exception:
                return

            day_values = [f"{d:02d}" for d in range(1, max_day + 1)]
            _om_day.configure(values=day_values)
            try:
                dd = int(_var_day.get())
                if dd > max_day:
                    _var_day.set(f"{max_day:02d}")
            except Exception:
                _var_day.set(day_values[0])

        _om_year.configure(command=_refresh_day_values)
        _om_month.configure(command=_refresh_day_values)
        _refresh_day_values()

        _ctk4.CTkLabel(inner, text='Hora', **_lbl).grid(row=2, column=0, sticky='w', padx=(0, 10), pady=(0, 10))
        _time_row = _ctk4.CTkFrame(inner, fg_color='transparent')
        _time_row.grid(row=2, column=1, sticky='w', pady=(0, 10))
        _ctk4.CTkOptionMenu(
            _time_row,
            variable=_var_hour,
            values=[f"{h:02d}" for h in range(0, 24)],
            width=72,
            **_opt,
        ).pack(side='left')
        _ctk4.CTkLabel(_time_row, text=':', text_color=C_TEXT, font=_ctk4.CTkFont(size=self._fs(12), weight='bold')).pack(side='left', padx=4)
        _ctk4.CTkOptionMenu(
            _time_row,
            variable=_var_minute,
            values=[f"{m:02d}" for m in range(0, 60)],
            width=72,
            **_opt,
        ).pack(side='left')

        btns = _ctk4.CTkFrame(modal, fg_color='transparent')
        btns.pack(fill='x', padx=20, pady=(0, 16))

        def _apply() -> None:
            try:
                d = _dt.date(int(_var_year.get()), int(_var_month.get()), int(_var_day.get()))
                hh = int(_var_hour.get())
                mm = int(_var_minute.get())
                row["schedule"] = f"{d.strftime('%Y-%m-%d')} {hh:02d}:{mm:02d}"
            except Exception:
                messagebox.showwarning("YouTube Publisher", "Fecha/hora invalida.")
                return

            self._yt_save_drafts_cache()
            self._yt_render_queue_preview()
            modal.destroy()

        _ctk4.CTkButton(
            btns,
            text='Aplicar',
            fg_color=C_ACCENT_YT,
            hover_color=C_ACCENT_YT_H,
            text_color='#FFFFFF',
            command=_apply,
        ).pack(side='left', padx=(0, 8))
        _ctk4.CTkButton(
            btns,
            text='Cancelar',
            fg_color='transparent',
            hover_color=C_HOVER,
            border_width=2,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=modal.destroy,
        ).pack(side='left')

    def _yt_open_row_description_modal(self, row: dict[str, str]) -> None:
        """Open modal to inspect/edit description for a single queue row."""
        import customtkinter as _ctk5
        import tkinter as _tk5

        self._yt_restore_playlists_cache_from_settings()

        modal = _ctk5.CTkToplevel(self)
        modal.title('Descripcion del video')
        modal.geometry('640x470')
        modal.resizable(True, True)
        modal.grab_set()
        modal.focus_force()
        modal.configure(fg_color=C_BG)
        _center_window_on_screen(modal)

        inner = _ctk5.CTkFrame(modal, fg_color='transparent')
        inner.pack(fill='both', expand=True, padx=20, pady=(16, 8))
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(3, weight=1)

        _ctk5.CTkLabel(
            inner,
            text=f"Editar descripcion: {(row.get('title') or 'Sin titulo')}",
            text_color=C_TEXT,
            anchor='w',
            font=_ctk5.CTkFont(size=self._fs(13), weight='bold'),
        ).grid(row=0, column=0, sticky='ew', pady=(0, 8))

        _lbl = dict(text_color=C_MUTED, anchor='w', font=_ctk5.CTkFont(size=self._fs(11)))
        _ctk5.CTkLabel(inner, text='Playlist (opcional)', **_lbl).grid(row=1, column=0, sticky='ew', pady=(0,4))
        playlist_options = self._yt_playlist_options()
        current_playlist_label = self._yt_playlist_data_to_label(
            row.get('playlist_id', ''),
            row.get('playlist_title', ''),
        )
        if current_playlist_label not in playlist_options:
            playlist_options.append(current_playlist_label)
        _var_playlist = _tk5.StringVar(value=current_playlist_label)
        _ctk5.CTkOptionMenu(
            inner,
            variable=_var_playlist,
            values=playlist_options,
            fg_color=C_INPUT,
            button_color=C_ACCENT_YT,
            button_hover_color=C_ACCENT_YT_H,
            text_color=C_TEXT,
            dropdown_fg_color=C_CARD,
            dropdown_text_color=C_TEXT,
            dropdown_hover_color=C_HOVER,
        ).grid(row=2, column=0, sticky='ew', pady=(0,10))

        _ctk5.CTkLabel(inner, text='Descripcion', **_lbl).grid(row=3, column=0, sticky='ew', pady=(0,4))

        txt = _ctk5.CTkTextbox(
            inner,
            fg_color=C_INPUT,
            border_width=1,
            border_color=C_BORDER,
            text_color=C_TEXT,
            font=_ctk5.CTkFont(size=self._fs(11)),
        )
        txt.grid(row=4, column=0, sticky='nsew')
        txt.insert('1.0', row.get('description', ''))

        btns = _ctk5.CTkFrame(modal, fg_color='transparent')
        btns.pack(fill='x', padx=20, pady=(8, 16))

        def _apply() -> None:
            playlist_id, playlist_title = self._yt_playlist_label_to_data(_var_playlist.get())
            row['description'] = txt.get('1.0', 'end').strip()
            row['playlist_id'] = playlist_id
            row['playlist_title'] = playlist_title
            self._yt_save_drafts_cache()
            self._yt_render_queue_preview()
            modal.destroy()

        _ctk5.CTkButton(
            btns,
            text='Guardar',
            fg_color=C_ACCENT_YT,
            hover_color=C_ACCENT_YT_H,
            text_color='#FFFFFF',
            command=_apply,
        ).pack(side='left', padx=(0, 8))
        _ctk5.CTkButton(
            btns,
            text='Cancelar',
            fg_color='transparent',
            hover_color=C_HOVER,
            border_width=2,
            border_color=C_BORDER,
            text_color=C_TEXT,
            command=modal.destroy,
        ).pack(side='left')

    def _yt_row_sync_checks(self, row: dict[str, str]) -> list[tuple[bool, str]]:
        """Return per-rule validation checks for sync eligibility."""
        checks: list[tuple[bool, str]] = []

        video_id = (row.get('video_id') or '').strip()
        checks.append((bool(video_id), 'Video con ID valido.'))

        title = (row.get('title') or '').strip()
        checks.append((bool(title), 'Titulo no vacio.'))

        schedule_local = (row.get('schedule') or '').strip()
        checks.append((bool(schedule_local), 'Fecha/hora configurada.'))

        if not schedule_local:
            return checks

        tz_name = self._var_yt_timezone.get() if hasattr(self, '_var_yt_timezone') else 'America/Los_Angeles'
        try:
            tz = ZoneInfo(tz_name)
            checks.append((True, f'Zona horaria valida ({tz_name}).'))
        except Exception:
            checks.append((False, f'Zona horaria invalida ({tz_name}).'))
            return checks

        try:
            local_dt = dt.datetime.strptime(schedule_local, '%Y-%m-%d %H:%M')
            local_dt = local_dt.replace(tzinfo=tz)
            utc_dt = local_dt.astimezone(dt.timezone.utc)
            checks.append((True, 'Formato de fecha/hora valido (YYYY-MM-DD HH:MM).'))
        except Exception:
            checks.append((False, f"Formato invalido ('{schedule_local}')."))
            return checks

        if utc_dt <= dt.datetime.now(dt.timezone.utc):
            checks.append((False, 'Fecha/hora en futuro.'))
            return checks

        checks.append((True, 'Fecha/hora en futuro.'))
        return checks

    def _yt_row_sync_eligibility(self, row: dict[str, str]) -> tuple[bool, str]:
        """Return eligibility and summary detail for a queue row before sync."""
        checks = self._yt_row_sync_checks(row)
        first_failed = next((msg for ok, msg in checks if not ok), None)
        if first_failed:
            return False, f'No elegible: {first_failed}'
        return True, 'Elegible para Sync.'

    def _yt_open_row_eligibility_modal(self, row: dict[str, str]) -> None:
        """Open checklist modal showing row readiness for sync."""
        import customtkinter as _ctk6

        checks = self._yt_row_sync_checks(row)
        eligible = all(ok for ok, _ in checks)

        modal = _ctk6.CTkToplevel(self)
        modal.title('Estado de elegibilidad')
        w, h = 520, 360
        modal.geometry(f'{w}x{h}')
        modal.resizable(True, True)
        modal.grab_set()
        modal.focus_force()
        modal.configure(fg_color=C_BG)
        _center_window_on_screen(modal)

        inner = _ctk6.CTkFrame(modal, fg_color='transparent')
        inner.pack(fill='both', expand=True, padx=20, pady=(16, 12))
        inner.grid_columnconfigure(0, weight=1)
        inner.grid_rowconfigure(2, weight=1)

        video_title = (row.get('title') or '').strip() or 'Sin titulo'
        _ctk6.CTkLabel(
            inner,
            text=f'Video: {video_title}',
            text_color=C_TEXT,
            anchor='w',
            font=_ctk6.CTkFont(size=self._fs(13), weight='bold'),
        ).grid(row=0, column=0, sticky='ew', pady=(0, 6))

        summary_txt = 'Elegible para Sync' if eligible else 'No elegible para Sync'
        summary_color = C_SUCCESS if eligible else C_ERROR
        _ctk6.CTkLabel(
            inner,
            text=summary_txt,
            text_color=summary_color,
            anchor='w',
            font=_ctk6.CTkFont(size=self._fs(12), weight='bold'),
        ).grid(row=1, column=0, sticky='ew', pady=(0, 10))

        checks_box = _ctk6.CTkScrollableFrame(inner, fg_color=C_CARD, height=210)
        checks_box.grid(row=2, column=0, sticky='nsew')
        checks_box.grid_columnconfigure(1, weight=1)

        for idx, (ok, msg) in enumerate(checks):
            icon = FA_CHECK if ok else FA_WARNING
            color = C_SUCCESS if ok else C_ERROR
            _ctk6.CTkLabel(
                checks_box,
                text=icon,
                text_color=color,
                font=_ctk6.CTkFont(family=_FA_FAMILY, size=self._fs(12)),
            ).grid(row=idx, column=0, sticky='nw', padx=(8, 8), pady=4)
            _ctk6.CTkLabel(
                checks_box,
                text=msg,
                text_color=C_TEXT,
                anchor='w',
                justify='left',
                wraplength=420,
                font=_ctk6.CTkFont(size=self._fs(11)),
            ).grid(row=idx, column=1, sticky='ew', pady=4)

        btns = _ctk6.CTkFrame(modal, fg_color='transparent')
        btns.pack(fill='x', padx=20, pady=(8, 16))
        _ctk6.CTkButton(
            btns,
            text='Cerrar',
            fg_color='transparent',
            hover_color=C_HOVER,
            border_width=2,
            border_color=C_BORDER,
            text_color=C_TEXT,
            width=120,
            height=34,
            font=_ctk6.CTkFont(size=self._fs(11), weight='bold'),
            command=modal.destroy,
        ).pack(anchor='center')


    def _yt_render_queue_preview(self) -> None:
        if not hasattr(self, "_yt_queue_frame"):
            return
        for w in self._yt_queue_frame.winfo_children():
            w.destroy()

        headers = ["Archivo", "Titulo", "Categoria", "Ninos", "Fecha", "Acciones"]
        for c, title in enumerate(headers):
            ctk.CTkLabel(
                self._yt_queue_frame,
                text=title,
                text_color=C_MUTED,
                font=ctk.CTkFont(size=self._fs(10), weight="bold"),
                anchor="w",
            ).grid(row=0, column=c, sticky="ew", padx=(2, 8), pady=(0, 8))

        if not self._yt_video_rows:
            ctk.CTkLabel(
                self._yt_queue_frame,
                text="Pulsa 'Obtener borradores' para cargar tus videos privados sin fecha de publicacion.",
                text_color=C_TEXT_DIM,
                anchor="w",
                font=ctk.CTkFont(size=self._fs(11)),
            ).grid(row=1, column=0, columnspan=5, sticky="ew", pady=(4, 8))
            return

        for i, row in enumerate(self._yt_video_rows, start=1):
            path_name = Path(row["path"]).name
            ctk.CTkLabel(
                self._yt_queue_frame,
                text=path_name,
                text_color=C_TEXT,
                anchor="w",
                font=ctk.CTkFont(size=self._fs(10)),
            ).grid(row=i, column=0, sticky="ew", padx=(2, 4), pady=2)

            title_var = tk.StringVar(value=row["title"])
            title_entry = ctk.CTkEntry(
                self._yt_queue_frame,
                textvariable=title_var,
                fg_color=C_INPUT,
                border_color=C_BORDER,
                text_color=C_TEXT,
                height=30,
            )
            title_entry.grid(row=i, column=1, sticky="ew", padx=(0, 8), pady=4)

            def _save_title(_e: Any = None, *, _row: dict[str, str] = row, _var: tk.StringVar = title_var) -> None:
                _row["title"] = _var.get().strip()
                self._yt_save_drafts_cache()

            title_entry.bind("<FocusOut>", _save_title)
            title_entry.bind("<Return>", _save_title)

            ctk.CTkLabel(
                self._yt_queue_frame,
                text=row["category"],
                text_color=C_TEXT,
                anchor="w",
                font=ctk.CTkFont(size=self._fs(10)),
            ).grid(row=i, column=2, sticky="ew", padx=(0, 8), pady=4)

            ctk.CTkLabel(
                self._yt_queue_frame,
                text=row["kids"],
                text_color=C_TEXT,
                anchor="w",
                font=ctk.CTkFont(size=self._fs(10)),
            ).grid(row=i, column=3, sticky="ew", padx=(0, 8), pady=4)

            schedule_text = row["schedule"] if row["schedule"] else "Seleccionar fecha y hora"
            ctk.CTkButton(
                self._yt_queue_frame,
                text=schedule_text,
                height=30,
                anchor="w",
                fg_color=C_INPUT,
                hover_color=C_HOVER,
                border_width=1,
                border_color=C_BORDER,
                text_color=C_TEXT,
                command=lambda _row=row: self._yt_open_row_schedule_picker(_row),
            ).grid(row=i, column=4, sticky="ew", padx=(0, 2), pady=4)

            actions = ctk.CTkFrame(self._yt_queue_frame, fg_color="transparent")
            actions.grid(row=i, column=5, sticky="e", padx=(6, 2), pady=4)

            desc_btn = ctk.CTkButton(
                actions,
                text=FA_EDIT,
                width=30,
                height=30,
                corner_radius=6,
                fg_color="transparent",
                hover_color=C_HOVER,
                border_width=1,
                border_color=C_BORDER,
                text_color=C_TEXT,
                font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(12)),
                command=lambda _row=row: self._yt_open_row_description_modal(_row),
            )
            desc_btn.pack(side="left", padx=(0, 6))

            desc_preview = (row.get("description") or "").strip()
            if not desc_preview:
                desc_tip = "Descripcion vacia. Clic para editar este video."
            else:
                compact = " ".join(desc_preview.split())
                desc_tip = f"Descripcion actual: {compact[:260]}"
                if len(compact) > 260:
                    desc_tip += "..."
            _Tooltip(desc_btn, desc_tip)

            eligible, eligibility_detail = self._yt_row_sync_eligibility(row)
            status_icon = FA_CHECK if eligible else FA_WARNING
            status_color = C_SUCCESS if eligible else C_ERROR
            status_btn = ctk.CTkButton(
                actions,
                text=status_icon,
                width=30,
                height=30,
                corner_radius=6,
                fg_color="transparent",
                hover_color=C_HOVER,
                border_width=1,
                border_color=status_color,
                text_color=status_color,
                font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(12)),
                command=lambda _row=row: self._yt_open_row_eligibility_modal(_row),
            )
            status_btn.pack(side="left")
            _Tooltip(status_btn, eligibility_detail)

    def _on_generate_youtube(self) -> None:
        """Apply scheduled metadata updates to YouTube using videos.update."""
        if self._yt_sync_in_progress:
            messagebox.showinfo("YouTube Publisher", "Ya hay un Sync en progreso.")
            return

        if not self._yt_require_channel_link(show_message=True):
            return

        if not self._yt_video_rows:
            messagebox.showwarning("YouTube Publisher", "No hay videos en cola.")
            return

        if self._yt_is_drafts_cache_stale():
            decision = messagebox.askyesnocancel(
                "YouTube Publisher",
                "La cola cache esta vencida.\n\n"
                "Si: refrescar ahora manteniendo tu progreso local por video.\n"
                "No: continuar con la cola actual.\n"
                "Cancelar: detener Sync.",
            )
            if decision is None:
                return
            if decision is True:
                ok_refresh = self._yt_fetch_drafts_with_merge(source_label="pre-sync")
                if not ok_refresh:
                    return
                if not self._yt_video_rows:
                    messagebox.showwarning("YouTube Publisher", "No hay videos en cola despues del refresco.")
                    return

        tz_name = self._var_yt_timezone.get() if hasattr(self, "_var_yt_timezone") else "America/Los_Angeles"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:
            messagebox.showwarning("YouTube Publisher", f"Zona horaria invalida: {tz_name}")
            return

        pending: list[dict[str, Any]] = []
        for row in self._yt_video_rows:
            video_id = (row.get("video_id") or "").strip()
            title = (row.get("title") or "").strip()
            schedule_local = (row.get("schedule") or "").strip()

            if not video_id:
                self._log("[YouTube] Fila omitida: video sin ID.")
                continue
            if not title:
                self._log(f"[YouTube] Fila omitida ({video_id}): titulo vacio.")
                continue
            if not schedule_local:
                self._log(f"[YouTube] Fila omitida ({video_id}): fecha vacia.")
                continue

            try:
                local_dt = dt.datetime.strptime(schedule_local, "%Y-%m-%d %H:%M")
                local_dt = local_dt.replace(tzinfo=tz)
                utc_dt = local_dt.astimezone(dt.timezone.utc)
                if utc_dt <= dt.datetime.now(dt.timezone.utc):
                    self._log(f"[YouTube] Fila omitida ({video_id}): fecha no es futura.")
                    continue
                publish_at_utc = utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                self._log(f"[YouTube] Fila omitida ({video_id}): fecha invalida '{schedule_local}'.")
                continue

            tags_raw = (row.get("tags") or "").strip()
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            pending.append({
                "video_id": video_id,
                "title": title,
                "description": (row.get("description") or "").strip(),
                "tags": tags,
                "category": row.get("category", "Music"),
                "made_for_kids": (row.get("kids", "No") == "Si"),
                "playlist_id": (row.get("playlist_id") or "").strip(),
                "playlist_title": (row.get("playlist_title") or "").strip(),
                "publish_at_utc": publish_at_utc,
            })

        if not pending:
            messagebox.showwarning(
                "YouTube Publisher",
                "No hay filas validas para enviar. Revisa titulo y fecha (YYYY-MM-DD HH:MM).",
            )
            return

        if not messagebox.askyesno(
            "YouTube Publisher",
            f"Se enviaran {len(pending)} actualizacion(es) a YouTube. Continuar?",
        ):
            return

        self._yt_sync_in_progress = True
        self._set_processing_state(True)
        self._yt_open_sync_modal(len(pending))
        self._log(f"[YouTube] Enviando {len(pending)} actualizacion(es) a YouTube...")
        threading.Thread(
            target=self._yt_sync_worker,
            args=(pending,),
            daemon=True,
        ).start()

    def _yt_sync_worker(self, pending: list[dict[str, Any]]) -> None:
        total = len(pending)
        ok = 0
        fail = 0
        successful_video_ids: set[str] = set()

        try:
            svc = self._yt_get_auth_service()
            for idx, item in enumerate(pending, start=1):
                vid = item.get("video_id", "")
                self.after(
                    0,
                    self._yt_update_sync_modal,
                    idx - 1,
                    total,
                    ok,
                    fail,
                    f"Procesando {idx}/{total}: {vid}",
                )

                try:
                    svc.update_video_metadata_and_schedule(
                        video_id=item["video_id"],
                        title=item["title"],
                        description=item["description"],
                        tags=item["tags"],
                        category_name=item["category"],
                        made_for_kids=item["made_for_kids"],
                        publish_at_utc=item["publish_at_utc"],
                    )
                    playlist_id = (item.get("playlist_id") or "").strip()
                    if playlist_id:
                        try:
                            svc.add_video_to_playlist(
                                video_id=item["video_id"],
                                playlist_id=playlist_id,
                            )
                            playlist_title = (item.get("playlist_title") or "").strip() or playlist_id
                            self._log(
                                f"[YouTube] Playlist asignada: {item['video_id']} -> {playlist_title}"
                            )
                        except YouTubeAuthError as exc:
                            self._log(
                                f"[YouTube] Aviso playlist {item['video_id']}: {exc}"
                            )

                    ok += 1
                    successful_video_ids.add(item["video_id"])
                    self._log(f"[YouTube] Programado: {item['video_id']} -> {item['publish_at_utc']}")
                except YouTubeAuthError as exc:
                    fail += 1
                    self._log(f"[YouTube] Error {item['video_id']}: {exc}")
                except Exception as exc:
                    fail += 1
                    self._log(f"[YouTube] Error inesperado {item['video_id']}: {exc}")

                self.after(
                    0,
                    self._yt_update_sync_modal,
                    idx,
                    total,
                    ok,
                    fail,
                    f"Completado {idx}/{total}: {vid}",
                )
        except Exception as exc:
            fail += max(0, total - ok - fail)
            self._log(f"[YouTube] Error fatal durante Sync: {exc}")

        self.after(
            0,
            self._yt_finish_sync,
            ok,
            fail,
            total,
            successful_video_ids,
        )

    def _yt_finish_sync(
        self,
        ok: int,
        fail: int,
        total: int,
        successful_video_ids: set[str],
    ) -> None:
        if successful_video_ids:
            before_count = len(self._yt_video_rows)
            self._yt_video_rows = [
                row for row in self._yt_video_rows
                if (row.get("video_id") or "").strip() not in successful_video_ids
            ]
            removed_count = before_count - len(self._yt_video_rows)
            self._yt_save_drafts_cache()
            self._yt_render_queue_preview()
            self._log(f"[YouTube] Cola actualizada: {removed_count} video(s) exitosos removidos.")

        self._log(f"[YouTube] Resultado envio -> OK: {ok}, Error: {fail}")
        self._yt_finish_sync_modal(ok=ok, fail=fail, total=total)
        self._yt_sync_in_progress = False
        self._set_processing_state(False)
    # --- Footer -------------------------------------------------------

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0, height=56)
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_propagate(False)
        footer.grid_columnconfigure(2, weight=1)
        self._footer_frame = footer

        _pad = 10
        _sec_kw: dict = dict(
            height=40, fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, corner_radius=6,
            font=ctk.CTkFont(size=self._fs(11)),
        )

        self._btn_test = ctk.CTkButton(
            footer, text="PROBAR FFMPEG",
            command=self._on_test_ffmpeg, **_sec_kw)
        self._btn_test.grid(row=0, column=0, padx=(32, 4), pady=_pad)
        _apply_sec_hover(self._btn_test)

        _btn_save = ctk.CTkButton(
            footer, text="GUARDAR CONFIG",
            command=self._save_settings, **_sec_kw,
        )
        _btn_save.grid(row=0, column=1, padx=4, pady=_pad)
        _apply_sec_hover(_btn_save)

        # ABRIR CARPETA — abre la carpeta de salida del modo activo
        self._btn_open_folder = ctk.CTkButton(
            footer, text=f"CARPETA DE SALIDA",
            command=self._on_open_output_folder, **_sec_kw)
        self._btn_open_folder.grid(row=0, column=2, padx=4, pady=_pad, sticky="w")
        _apply_sec_hover(self._btn_open_folder)

        # CANCELAR — junto al botón principal
        self._btn_cancel = ctk.CTkButton(
            footer, text="CANCELAR", state="disabled",
            command=self._on_cancel, **_sec_kw)
        self._btn_cancel.grid(row=0, column=3, padx=(4, 4), pady=_pad)
        _apply_sec_hover(self._btn_cancel)

        # Primary CTA — right side
        self._btn_generate = ctk.CTkButton(
            footer, text="\u25b6  GENERAR VIDEOS",
            fg_color=C_BTN_PRIMARY, hover_color=C_ACCENT_H,
            text_color="#ffffff", corner_radius=6,
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
            height=38, width=220, command=self._on_generate)
        self._btn_generate.grid(row=0, column=4, padx=(4, 32), pady=_pad, sticky="e")

    # ------------------------------------------------------------------
    # HELPERS DE CONSTRUCCIÓN DE WIDGETS
    # ------------------------------------------------------------------

    def _section_label(self, parent: Any, text: str, row: int) -> int:
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
            text_color=C_TEXT,
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", padx=12, pady=(14, 2))
        ctk.CTkFrame(parent, height=1, fg_color=C_BORDER).grid(
            row=row + 1, column=0, sticky="ew", padx=12, pady=(0, 6)
        )
        return row + 2

    def _collapsible_section(
        self,
        parent: Any,
        title: str,
        row: int,
        default_open: bool = True,
        fa_icon: str | None = None,
    ) -> tuple[ctk.CTkFrame, int]:
        """Crea una sección colapsable con tarjeta. Retorna (content_frame, siguiente_row)."""
        _open = [default_open]
        _title = title
        _fa_lbl = None

        # -- tab-style header container ------------------------------
        _tab_wrap = ctk.CTkFrame(parent, fg_color="transparent")
        _tab_wrap.grid(row=row, column=0, sticky="ew", padx=12, pady=(6, 0))
        _tab_wrap.grid_columnconfigure(0 if not fa_icon else 1, weight=1)

        if fa_icon:
            _fa_lbl = ctk.CTkLabel(
                _tab_wrap, text=fa_icon, width=22,
                font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(13)),
                text_color=C_TEXT,
            )
            _fa_lbl.grid(row=0, column=0, padx=(6, 0))
            _tab_wrap.grid_columnconfigure(1, weight=1)

        _btn_col = 1 if fa_icon else 0

        # Tab button — active look when open
        _fg_open   = C_INPUT   # #262626 — Surface High
        _fg_closed = "transparent"
        _tc_open   = C_TEXT
        _tc_closed = C_TEXT_DIM

        btn = ctk.CTkButton(
            _tab_wrap,
            text=title,
            anchor="w",
            fg_color=_fg_open if default_open else _fg_closed,
            hover_color=C_HOVER,
            text_color=_tc_open if default_open else _tc_closed,
            font=ctk.CTkFont(size=self._fs(12), weight="bold"),
            height=38,
            corner_radius=8,
        )
        btn.grid(row=0, column=_btn_col, sticky="ew", padx=(0, 0))

        # Accent bottom indicator line (active only)
        _indicator = ctk.CTkFrame(
            _tab_wrap,
            height=2,
            fg_color=C_ACCENT if default_open else "transparent",
            corner_radius=0,
        )
        _indicator.grid(row=1, column=_btn_col, sticky="ew", padx=4)

        card = ctk.CTkFrame(
            parent,
            fg_color=C_CARD,
            corner_radius=8,
            border_width=1,
            border_color=C_BORDER,
        )
        card.grid_columnconfigure(0, weight=1)
        card.grid(row=row + 1, column=0, sticky="ew", padx=12, pady=(0, 0))
        ctk.CTkFrame(card, height=8, fg_color="transparent").grid(row=0, column=0, sticky="ew")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=1, column=0, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)
        ctk.CTkFrame(card, height=8, fg_color="transparent").grid(row=2, column=0, sticky="ew")

        def _toggle() -> None:
            if _open[0]:
                card.grid_remove()
                btn.configure(fg_color=_fg_closed, text_color=_tc_closed)
                _indicator.configure(fg_color="transparent")
                _open[0] = False
            else:
                card.grid()
                btn.configure(fg_color=_fg_open, text_color=_tc_open)
                _indicator.configure(fg_color=C_ACCENT)
                _open[0] = True

        if not default_open:
            card.grid_remove()
        btn.configure(command=_toggle)
        if _fa_lbl:
            _fa_lbl.bind("<Button-1>", lambda e: _toggle())
        return inner, row + 2

    # -- custom underline tab panel ------------------------------------
    def _make_tab_panel(
        self,
        parent: ctk.CTkFrame,
        tabs: list,
        accent: str,
        on_before_activate: Any | None = None,
    ) -> tuple:
        """
        Creates an underline-style tab panel.
        Returns: (outer_frame, dict[name -> content_frame])
        """
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        # -- Tab header bar --------------------------------------------
        bar = ctk.CTkFrame(
            outer, fg_color=C_CARD, corner_radius=10,
            border_width=1, border_color=C_BORDER, height=46,
        )
        bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 8))
        bar.grid_propagate(False)
        for i in range(len(tabs)):
            bar.grid_columnconfigure(i, weight=1, uniform="tab")

        # -- Content area ----------------------------------------------
        content = ctk.CTkFrame(
            outer, fg_color="transparent",
            corner_radius=0, border_width=0,
        )
        content.grid(row=1, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        tab_data: dict = {}

        for i, (label, name) in enumerate(tabs):
            # Content frame – all stacked at row=0; only one visible at a time
            tf = ctk.CTkFrame(content, fg_color="transparent")
            tf.grid(row=0, column=0, sticky="nsew")
            tf.grid_columnconfigure(0, weight=1)
            tf.grid_rowconfigure(0, weight=1)
            if i > 0:
                tf.grid_remove()

            # Tab button frame
            btn = ctk.CTkFrame(bar, fg_color="transparent", cursor="hand2")
            btn.grid(row=0, column=i, sticky="nsew")
            btn.grid_rowconfigure(0, weight=1)
            btn.grid_columnconfigure(0, weight=1)

            is_first = i == 0
            lbl = ctk.CTkLabel(
                btn, text=label, cursor="hand2",
                font=ctk.CTkFont(size=self._fs(12), weight="bold" if is_first else "normal"),
                text_color=accent if is_first else C_TEXT_DIM,
            )
            lbl.grid(row=0, column=0, pady=(8, 0))

            # 2-px underline indicator
            ul = ctk.CTkFrame(
                btn,
                fg_color=accent if is_first else "transparent",
                height=2, corner_radius=0,
            )
            ul.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 6))

            tab_data[name] = {"frame": tf, "label": lbl, "underline": ul, "btn": btn}

        def _activate(name: str) -> None:
            if on_before_activate is not None:
                try:
                    allowed = on_before_activate(name)
                except Exception:
                    allowed = True
                if allowed is False:
                    return
            for k, d in tab_data.items():
                active = k == name
                if active:
                    d["frame"].grid()
                else:
                    d["frame"].grid_remove()
                d["label"].configure(
                    text_color=accent if active else C_TEXT_DIM,
                    font=ctk.CTkFont(
                        size=self._fs(12),
                        weight="bold" if active else "normal",
                    ),
                )
                d["underline"].configure(fg_color=accent if active else "transparent")

        for name, d in tab_data.items():
            for w in (d["btn"], d["label"]):
                w.bind("<Button-1>", lambda e, n=name: _activate(n))

        # Optional external access (e.g., force back to first tab after guard).
        setattr(outer, "_activate_tab", _activate)

        return outer, {n: d["frame"] for n, d in tab_data.items()}

    def _section_header(
        self,
        parent: Any,
        text: str,
        *,
        collapse_on_startup: bool = True,
    ) -> ctk.CTkFrame:
        """Collapsible section header with chevron toggle.

        Clicking the header or chevron toggles visibility of all sibling
        widgets inside *parent* (everything except the header itself).
        """
        hdr = ctk.CTkFrame(parent, fg_color=C_INPUT, corner_radius=0)

        # Inner row: title on left, chevron on right
        row = ctk.CTkFrame(hdr, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=(10, 8))
        row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            row, text=text, text_color=C_TEXT,
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")

        chevron = ctk.CTkLabel(
            row, text=FA_CHEVRON_DOWN,
            text_color=C_ACCENT,
            font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(11)),
            cursor="hand2",
        )
        chevron.grid(row=0, column=1, sticky="e")

        accent_line = ctk.CTkFrame(hdr, height=2, fg_color=C_ACCENT, corner_radius=0)
        accent_line.pack(fill="x")

        # State kept in a mutable container so the closure can update it
        state: dict = {"collapsed": False, "pack_info": {}}

        def _toggle(_event=None):
            state["collapsed"] = not state["collapsed"]
            chevron.configure(
                text=FA_CHEVRON_RIGHT if state["collapsed"] else FA_CHEVRON_DOWN
            )
            for child in parent.winfo_children():
                if child is hdr:
                    continue
                if state["collapsed"]:
                    mgr = child.winfo_manager()
                    if mgr == "grid":
                        child.grid_remove()
                    elif mgr == "pack":
                        try:
                            state["pack_info"][id(child)] = child.pack_info()
                        except Exception:
                            pass
                        child.pack_forget()
                else:
                    pid = id(child)
                    if pid in state["pack_info"]:
                        info = state["pack_info"].pop(pid)
                        info.pop("in", None)
                        child.pack(**info)
                    else:
                        child.grid()

        # Make header and chevron clickable
        for w in (hdr, row, chevron):
            w.bind("<Button-1>", _toggle)
        # Also bind the title label
        for w in row.winfo_children():
            w.bind("<Button-1>", _toggle)

        # Register for initial collapse
        if collapse_on_startup and hasattr(self, "_section_toggles"):
            self._section_toggles.append(_toggle)

        return hdr

    def _file_row(
        self,
        parent: Any,
        label: str,
        var: tk.StringVar,
        command: Any,
        row: int,
        icon: str = FA_FOLDER,
    ) -> int:
        ctk.CTkLabel(parent, text=label, text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), anchor="w").grid(
            row=row, column=0, sticky="ew", padx=12, pady=(10, 2)
        )
        container = ctk.CTkFrame(parent, fg_color=C_INPUT, corner_radius=6,
                                 border_width=1, border_color=C_BORDER)
        container.grid(row=row + 1, column=0, sticky="ew", padx=12, pady=(2, 6))
        container.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(container, text=icon, width=28,
                     font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(11)),
                     text_color=C_TEXT_DIM).grid(row=0, column=0, padx=(8, 0), pady=5)
        ctk.CTkEntry(container, textvariable=var, height=28,
                     fg_color="transparent", border_width=0,
                     text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11))).grid(
            row=0, column=1, sticky="ew", padx=4, pady=3)
        _browse_btn = ctk.CTkButton(
            container, text="Browse", width=65, height=26,
            fg_color="transparent", hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER,
            text_color=C_TEXT, corner_radius=4,
            font=ctk.CTkFont(size=self._fs(10)),
            command=command,
        )
        _browse_btn.grid(row=0, column=2, padx=(0, 5), pady=4)
        _apply_sec_hover(_browse_btn)
        return row + 2

    def _get_range(self, *keys: str, default_min: float = 0, default_max: float = 1) -> tuple[float, float]:
        """Lookup slider range from slider_ranges.json by nested keys.
        Returns (min, max) from config, or defaults if key path not found."""
        d: Any = self._slider_ranges
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default_min, default_max
        if isinstance(d, dict):
            return d.get("min", default_min), d.get("max", default_max)
        return default_min, default_max

    def _collapse_all_sections(self) -> None:
        """Collapse every section registered during _build_ui."""
        for toggle_fn in self._section_toggles:
            try:
                toggle_fn()
            except Exception:
                pass

    def _slider_row(
        self,
        parent: Any,
        label: str,
        var: tk.Variable,
        from_: float,
        to: float,
        row: int,
        fmt: str = "{:.2f}",
        tooltip_text: str = "",
        number_of_steps: int | None = None,
        pct: bool = False,
    ) -> int:
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.grid(row=row, column=0, sticky="ew", padx=12, pady=(8, 8))
        inner.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(inner, text=label, text_color=C_TEXT,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(
            row=0, column=0, sticky="w"
        )

        _lo, _hi = from_, to

        def _to_pct(v: float) -> str:
            rng = _hi - _lo
            if rng == 0:
                return "0%"
            return f"{int(round((v - _lo) / rng * 100))}%"

        init_text = _to_pct(var.get()) if pct else fmt.format(var.get())
        val_label = ctk.CTkLabel(inner, text=init_text,
                                 text_color=C_TEXT, font=ctk.CTkFont(size=self._fs(11)), width=50)
        val_label.grid(row=0, column=2, padx=(4, 0))

        def _update(v: str) -> None:
            try:
                fv = float(v)
                val_label.configure(text=_to_pct(fv) if pct else fmt.format(fv))
            except ValueError:
                pass

        slider_kwargs: dict = dict(
            from_=from_, to=to, variable=var, command=_update,
            fg_color=C_INPUT, progress_color=C_ACCENT, button_color=C_ACCENT,
            button_hover_color=C_ACCENT_H,
        )
        if number_of_steps is not None:
            slider_kwargs["number_of_steps"] = number_of_steps
        ctk.CTkSlider(inner, **slider_kwargs).grid(
            row=0, column=1, sticky="ew", padx=4
        )

        if tooltip_text:
            _info_btn = ctk.CTkButton(
                inner, text="?", width=22, height=22,
                fg_color=C_ACCENT, hover_color=C_ACCENT_H,
                text_color="#ffffff",
                font=ctk.CTkFont(size=self._fs(11), weight="bold"),
                corner_radius=4,
            )
            _info_btn.grid(row=0, column=3, padx=(4, 0))
            _Tooltip(_info_btn, tooltip_text)

        return row + 1

    def _check_row(
        self,
        parent: Any,
        label: str,
        var: tk.BooleanVar,
        row: int,
        command: Any = None,
    ) -> int:
        cb = ctk.CTkCheckBox(
            parent,
            text=label,
            variable=var,
            font=ctk.CTkFont(size=self._fs(11)),
            text_color=C_TEXT,
            fg_color=C_ACCENT,
            hover_color=C_ACCENT_H,
            border_color=C_BORDER,
            checkmark_color="#ffffff",
            command=command,
        )
        cb.grid(row=row, column=0, sticky="w", padx=16, pady=(6, 6))
        return row + 1

    # ------------------------------------------------------------------
    # TEMA, FUENTE Y HELPERS
    # ------------------------------------------------------------------

    def _fs(self, base: int) -> int:
        """Devuelve el tamaño de fuente escalado a la preferencia del usuario."""
        return max(8, int(base * self._font_scale))

    def _toggle_theme(self) -> None:
        """Alterna entre tema Dark y Light, reconstruye toda la UI con los nuevos colores."""
        if self._runner and self._runner.is_running():
            messagebox.showwarning("Tema", "No es posible cambiar el tema mientras se generan videos.")
            return
        self._collect_settings()
        new_theme = "Light" if self._current_theme == "Dark" else "Dark"
        self.settings.update({"theme": new_theme})
        self._current_theme = new_theme
        _TM.set_current_mode(new_theme)
        _apply_theme(new_theme)
        ctk.set_appearance_mode(new_theme)
        self.configure(fg_color=C_BG)
        for w in self.winfo_children():
            if isinstance(w, tk.Toplevel):
                continue
            w.destroy()
        self._build_ui()
        self.after_idle(self._collapse_all_sections)
        self._load_settings_to_ui()
        self.after(200, self._run_validation)

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def _handle_callback_exception(self, exc, val, tb):
        """Override Tk's default exception reporter.

        Silently discards TclErrors caused by CTk internal after() callbacks
        that fire on widgets already destroyed during a UI rebuild (e.g. after
        a theme change). All other exceptions are printed to stderr as usual.
        """
        import _tkinter
        if isinstance(val, _tkinter.TclError) and "bad window path name" in str(val):
            return
        import traceback
        traceback.print_exception(exc, val, tb)

    def _open_theme_settings(self) -> None:
        """Abre el modal de configuración de tema."""
        # Avoid opening duplicate dialogs
        for w in self.winfo_children():
            if isinstance(w, ThemeSettingsDialog):
                w.focus_force()
                return
        ThemeSettingsDialog(self)

    def _apply_theme_color_change(self, caller: "ThemeSettingsDialog | None" = None) -> None:
        """Aplica un cambio de color desde ThemeSettingsDialog reconstruyendo la UI principal."""
        self._collect_settings()
        _apply_theme(self._current_theme)
        ctk.set_appearance_mode(self._current_theme)
        self.configure(fg_color=C_BG)
        # Destroy only non-toplevel children (leave the dialog open)
        for w in self.winfo_children():
            if isinstance(w, tk.Toplevel):
                continue
            w.destroy()
        self._build_ui()
        self.after_idle(self._collapse_all_sections)
        self._load_settings_to_ui()
        self.after(200, self._run_validation)

    def _on_font_size(self, size: str) -> None:
        """Cambia la escala de fuente y reconstruye el panel izquierdo."""
        self._collect_settings()
        self._font_scale = _FONT_SIZE_SCALE.get(size, 1.0)
        self.settings.update({"font_size": size})
        # Actualizar aspecto de botones de tamaño
        for s, btn in self._font_btns.items():
            active = (s == size)
            btn.configure(
                fg_color=C_ACCENT if active else "transparent",
                text_color=C_TEXT if active else C_TEXT_DIM,
            )
        if hasattr(self, "_scroll_frame"):
            self._scroll_frame.destroy()
        self._build_left_panel(self._main_panel)
        # Rebuild slideshow panel too
        if hasattr(self, "_sl_scroll_frame"):
            self._sl_scroll_frame.destroy()
        self._build_slideshow_left_panel(self._main_panel)
        # Rebuild shorts panel too
        if hasattr(self, "_sho_scroll_frame"):
            self._sho_scroll_frame.destroy()
        self._build_shorts_left_panel(self._main_panel)
        # Rebuild YouTube panel too
        if hasattr(self, "_yt_scroll_frame"):
            self._yt_scroll_frame.destroy()
        self._build_youtube_left_panel(self._main_panel)
        # Rebuild Prompt Lab panel too
        if hasattr(self, "_pl_scroll_frame"):
            self._pl_scroll_frame.destroy()
        self._build_prompt_lab_left_panel(self._main_panel)
        # Collapse all new sections
        self.after_idle(self._collapse_all_sections)
        if self._current_mode == "Slideshow":
            self._sl_scroll_frame.grid()
            self._scroll_frame.grid_remove()
        elif self._current_mode == "Shorts":
            if hasattr(self, "_sho_scroll_frame"):
                self._sho_scroll_frame.grid()
            self._scroll_frame.grid_remove()
        elif self._current_mode == "YouTube Publisher":
            if hasattr(self, "_yt_scroll_frame"):
                self._yt_scroll_frame.grid()
            self._scroll_frame.grid_remove()
        elif self._current_mode == "Prompt Lab":
            if hasattr(self, "_pl_scroll_frame"):
                self._pl_scroll_frame.grid()
            self._scroll_frame.grid_remove()
        self._load_settings_to_ui()
        if hasattr(self, "_log_text"):
            self._log_text.configure(font=ctk.CTkFont(family="Consolas", size=self._fs(11)))

    # ------------------------------------------------------------------
    # MODO SLIDESHOW — switch + acciones
    # ------------------------------------------------------------------

    def _update_mode_buttons(self) -> None:
        """Actualiza el color activo/inactivo de los botones de modo del header."""
        for prefix in ("atv", "slide", "shorts", "yt", "pl"):
            if not hasattr(self, f"_frame_mode_{prefix}"):
                continue
            active = (
                (prefix == "atv" and self._current_mode == "Audio \u2192 Video")
                or (prefix == "slide" and self._current_mode == "Slideshow")
                or (prefix == "shorts" and self._current_mode == "Shorts")
                or (prefix == "yt" and self._current_mode == "YouTube Publisher")
                or (prefix == "pl" and self._current_mode == "Prompt Lab")
            )
            accent = getattr(self, f"_mode_{prefix}_accent")
            bg = C_INPUT if active else "transparent"
            txt = C_TEXT if active else C_TEXT_DIM
            ind = accent if active else "transparent"
            setattr(self, f"_mode_{prefix}_base", bg)
            getattr(self, f"_frame_mode_{prefix}").configure(fg_color=bg)
            getattr(self, f"_bar_mode_{prefix}").configure(fg_color=ind)
            getattr(self, f"_lbl_mode_{prefix}_icon").configure(text_color=txt)
            getattr(self, f"_lbl_mode_{prefix}_text").configure(text_color=txt)

    def _configure_preview_for_mode(self, mode: str) -> None:
        """Ajusta el ancho, alto y disposición del frame de preview según el modo activo."""
        if mode == "Shorts":
            # Marco vertical 9:16 con strip lateral derecho
            self._preview_frame.configure(width=255, height=360)
            self._preview_frame.grid_configure(sticky="n", padx=0)
            self._preview_frame.grid_columnconfigure(0, weight=0)
            self._preview_frame.grid_columnconfigure(1, weight=0)
            self._preview_frame.grid_rowconfigure(0, weight=1)
            self._lbl_preview.grid_configure(row=0, column=0, sticky="nsew", rowspan=2)
            # Mostrar strip vertical, ocultar horizontal
            self._thumb_strip.grid_remove()
        else:
            # Marco horizontal 16:9 con strip debajo
            self._preview_frame.configure(width=0, height=270)
            self._preview_frame.grid_configure(sticky="ew", padx=16)
            self._preview_frame.grid_columnconfigure(0, weight=1)
            self._preview_frame.grid_columnconfigure(1, weight=0)
            self._preview_frame.grid_rowconfigure(0, weight=1)
            self._preview_frame.grid_rowconfigure(1, weight=0)
            self._lbl_preview.grid_configure(row=0, column=0, sticky="nsew", rowspan=1)
            # Ocultar strip vertical (el horizontal lo gestiona rebuild_thumb_strip)
            if hasattr(self, "_thumb_strip_vert"):
                self._thumb_strip_vert.grid_remove()

    def _switch_mode(self, mode: str) -> None:
        """Alterna entre los paneles Audio?Video, Slideshow, Shorts, YouTube y Prompt Lab."""
        self._current_mode = mode
        self._configure_preview_for_mode(mode)
        self._update_mode_buttons()
        if hasattr(self, "_footer_frame"):
            if mode == "Prompt Lab":
                self._footer_frame.grid_remove()
            else:
                self._footer_frame.grid()
        # Flush pending geometry events so the preview frame has its correct size
        # before loading images (avoids canvas being 0px wide after Shorts?ATV)
        self.update_idletasks()
        # Show/hide the right panel depending on the active mode.
        # YouTube Publisher uses the full window width; all other modes keep
        # the normal 60/40 split with the preview + logs column.
        if mode in ("YouTube Publisher", "Prompt Lab"):
            if hasattr(self, "_right_panel_frame"):
                self._right_panel_frame.grid_remove()
            self._main_panel.grid_columnconfigure(0, weight=1, minsize=380)
            self._main_panel.grid_columnconfigure(1, weight=0, minsize=0)
        else:
            if hasattr(self, "_right_panel_frame"):
                self._right_panel_frame.grid()
            self._main_panel.grid_columnconfigure(0, weight=3, minsize=380)
            self._main_panel.grid_columnconfigure(1, weight=2, minsize=300)
        # Hide all left panels first
        self._scroll_frame.grid_remove()
        if hasattr(self, "_sl_scroll_frame"):
            self._sl_scroll_frame.grid_remove()
        if hasattr(self, "_sho_scroll_frame"):
            self._sho_scroll_frame.grid_remove()
        if hasattr(self, "_yt_scroll_frame"):
            self._yt_scroll_frame.grid_remove()
        if hasattr(self, "_pl_scroll_frame"):
            self._pl_scroll_frame.grid_remove()

        if mode == "Audio \u2192 Video":
            self._scroll_frame.grid()
            self._btn_generate.configure(
                text="\u25b6  GENERAR VIDEOS", command=self._on_generate)
            # Siempre re-derivar la preview desde las variables ATV
            if hasattr(self, "_var_multi_image") and self._var_multi_image.get():
                imgs_folder = self._var_images_folder.get() if hasattr(self, "_var_images_folder") else ""
                if imgs_folder and Path(imgs_folder).is_dir():
                    imgs = get_image_files(imgs_folder)
                    if imgs:
                        self._load_preview(str(imgs[0]))
            elif hasattr(self, "_var_image"):
                img = self._var_image.get()
                if img and Path(img).is_file():
                    self._load_preview(img)
            self._rebuild_thumb_strip()
            if hasattr(self, "_var_audio_folder"):
                self._update_audio_count(self._var_audio_folder.get())

        elif mode == "Slideshow":
            if hasattr(self, "_sl_scroll_frame"):
                self._sl_scroll_frame.grid()
            self._btn_generate.configure(
                text="\u25b6  GENERAR VIDEO", command=self._on_generate_slideshow)
            # Siempre re-derivar la preview desde las variables Slideshow
            if hasattr(self, "_var_sl_images_folder"):
                folder = self._var_sl_images_folder.get()
                if folder and Path(folder).is_dir():
                    imgs = get_image_files(folder)
                    if imgs:
                        self._load_preview(str(imgs[0]))
            self._rebuild_thumb_strip_sl()
            # Audio label para Slideshow
            if hasattr(self, "_var_sl_audio_enabled") and self._var_sl_audio_enabled.get():
                mode = self._var_sl_audio_mode.get() if hasattr(self, "_var_sl_audio_mode") else "file"
                if mode == "folder":
                    folder = self._var_sl_audio_folder.get() if hasattr(self, "_var_sl_audio_folder") else ""
                    if folder and Path(folder).is_dir():
                        n = len(get_audio_files(folder))
                        self._lbl_audio_count.configure(
                            text=f"\u266b Audios: {n} archivo(s)",
                            text_color=C_ACCENT_SLIDE if n > 0 else C_MUTED)
                    else:
                        self._lbl_audio_count.configure(text="Audios: \u2014", text_color=C_MUTED)
                else:
                    af = self._var_sl_audio_file.get() if hasattr(self, "_var_sl_audio_file") else ""
                    if af and Path(af).is_file():
                        _sl_name = Path(af).stem
                        _sl_label = (_sl_name[:48] + "\u2026") if len(_sl_name) > 48 else _sl_name
                        self._lbl_audio_count.configure(
                            text=f"\u266b Audio: {_sl_label}", text_color=C_ACCENT_SLIDE)
                    else:
                        self._lbl_audio_count.configure(text="Audios: \u2014", text_color=C_MUTED)
            else:
                self._lbl_audio_count.configure(text="Audios: \u2014", text_color=C_MUTED)

        elif mode == "Shorts":
            if hasattr(self, "_sho_scroll_frame"):
                self._sho_scroll_frame.grid()
            self._btn_generate.configure(
                text="\u25b6  GENERAR SHORTS", command=self._on_generate_shorts)
            # Siempre re-derivar la preview desde las variables Shorts
            if hasattr(self, "_var_sho_multi_image") and self._var_sho_multi_image.get():
                folder = self._var_sho_images_folder.get() if hasattr(self, "_var_sho_images_folder") else ""
                if folder and Path(folder).is_dir():
                    imgs = get_image_files(folder)
                    if imgs:
                        self._load_preview(str(imgs[0]))
            elif hasattr(self, "_var_sho_image"):
                img = self._var_sho_image.get()
                if img and Path(img).is_file():
                    self._load_preview(img)
            self._rebuild_thumb_strip_sho()
            self._lbl_audio_count.configure(text="Audios: \u2014", text_color=C_MUTED)

        elif mode == "YouTube Publisher":
            if hasattr(self, "_yt_scroll_frame"):
                self._yt_scroll_frame.grid()
            self._thumb_strip.grid_remove()
            if hasattr(self, "_thumb_strip_vert"):
                self._thumb_strip_vert.grid_remove()
            self._lbl_audio_count.configure(text="YouTube Publisher", text_color=C_ACCENT_YT)
            self._yt_update_cache_status_label()
            self._yt_update_queue_cache_status_label()
            self._btn_generate.configure(text="SYNC BORRADORES", command=self._on_generate_youtube)
        else:  # Prompt Lab
            if hasattr(self, "_pl_scroll_frame"):
                self._pl_scroll_frame.grid()
            self._pl_refresh_available_models()
            self._thumb_strip.grid_remove()
            if hasattr(self, "_thumb_strip_vert"):
                self._thumb_strip_vert.grid_remove()
            self._lbl_audio_count.configure(text="Prompt Lab", text_color=C_ACCENT_LAB)
            self._btn_generate.configure(text=FA_WAND + "  GENERAR RESPUESTA", command=self._on_generate_prompt_lab)

    def _sl_browse_images_folder(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta de im\u00e1genes")
        if path:
            self._var_sl_images_folder.set(path)
            self._sl_update_count()
            self._rebuild_thumb_strip_sl()
            imgs = get_image_files(path)
            if imgs:
                self._load_preview(str(imgs[0]))

    def _sl_browse_audio_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar archivo de audio",
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.aac *.ogg *.m4a"), ("Todos", "*.*")],
        )
        if path:
            self._var_sl_audio_file.set(path)

    def _sl_browse_audio_folder(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta de audios")
        if path:
            self._var_sl_audio_folder.set(path)
            self._sl_update_audio_folder_count()

    def _sl_toggle_audio_mode(self) -> None:
        if self._var_sl_audio_mode.get() == "file":
            self._sl_single_audio_frame.grid()
            self._sl_folder_audio_frame.grid_remove()
        else:
            self._sl_single_audio_frame.grid_remove()
            self._sl_folder_audio_frame.grid()
            self._sl_update_audio_folder_count()

    def _sl_update_audio_folder_count(self) -> None:
        if not hasattr(self, "_sl_audio_folder_lbl"):
            return
        folder = self._var_sl_audio_folder.get()
        if folder and Path(folder).is_dir():
            n = len(get_audio_files(folder))
            self._sl_audio_folder_lbl.configure(
                text=f"\u25a3 Audios detectados: {n} archivo(s)",
                text_color=C_ACCENT_SLIDE if n > 0 else C_MUTED,
            )
        else:
            self._sl_audio_folder_lbl.configure(text="", text_color=C_MUTED)

    def _sl_browse_output_folder(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if path:
            self._var_sl_output_folder.set(path)

    def _sl_toggle_audio(self) -> None:
        if self._var_sl_audio_enabled.get():
            self._sl_audio_wrapper.grid()
        else:
            self._sl_audio_wrapper.grid_remove()

    def _sl_update_count(self) -> None:
        if not hasattr(self, "_sl_lbl_count"):
            return
        folder = self._var_sl_images_folder.get()
        if folder and Path(folder).is_dir():
            try:
                n = len(get_image_files(folder))
                self._sl_lbl_count.configure(
                    text=f"\u25a3 Im\u00e1genes detectadas: {n} archivo(s)",
                    text_color=C_SUCCESS if n else C_WARN,
                )
            except Exception:
                pass
        else:
            self._sl_lbl_count.configure(text="\u266b Im\u00e1genes: \u2014", text_color=C_MUTED)

    def _sl_reload(self) -> None:
        self._sl_update_count()
        self._rebuild_thumb_strip_sl()
        imgs_folder = self._var_sl_images_folder.get()
        if imgs_folder and Path(imgs_folder).is_dir():
            imgs = get_image_files(imgs_folder)
            if imgs:
                self._load_preview(str(imgs[0]))

    def _rebuild_thumb_strip_sho(self) -> None:
        """Repobla el filmstrip vertical con imágenes de la carpeta de Shorts (miniaturas 9:16)."""
        if not hasattr(self, "_thumb_strip_vert"):
            return
        # Only show the vertical strip when actually in Shorts mode
        if getattr(self, "_current_mode", "") != "Shorts":
            self._thumb_strip_vert.grid_remove()
            return
        for w in self._thumb_strip_vert.winfo_children():
            w.destroy()
        self._thumb_strip_vert_imgs.clear()
        if not getattr(self, "_var_sho_multi_image", tk.BooleanVar(value=False)).get():
            self._thumb_strip_vert.grid_remove()
            return
        folder = self._var_sho_images_folder.get() if hasattr(self, "_var_sho_images_folder") else ""
        if not folder or not Path(folder).is_dir():
            self._thumb_strip_vert.grid_remove()
            return
        imgs = get_image_files(folder)
        if not imgs:
            self._thumb_strip_vert.grid_remove()
            return
        TW, TH = 36, 64  # 9:16 thumbnail
        for i, img_path in enumerate(imgs):
            try:
                thumb = Image.open(str(img_path))
                thumb = self._crop_img_to_9_16(thumb, TW, TH)
                ctk_thumb = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=(TW, TH))
                self._thumb_strip_vert_imgs.append(ctk_thumb)
                btn = ctk.CTkButton(
                    self._thumb_strip_vert,
                    image=ctk_thumb, text="",
                    width=TW + 4, height=TH + 8,
                    fg_color=C_CARD, hover_color=C_HOVER,
                    border_width=1, border_color=C_BORDER,
                    corner_radius=3,
                    command=lambda p=str(img_path): self._load_preview(p),
                )
                btn.grid(row=i, column=0, padx=2, pady=2)
            except Exception:
                pass
        self._thumb_strip_vert.grid()

    def _rebuild_thumb_strip_sl(self) -> None:
        """Repobla el filmstrip con imágenes de la carpeta de slideshow."""
        if not hasattr(self, "_thumb_strip"):
            return
        for w in self._thumb_strip.winfo_children():
            w.destroy()
        self._thumb_strip_imgs.clear()
        folder = self._var_sl_images_folder.get() if hasattr(self, "_var_sl_images_folder") else ""
        if not folder or not Path(folder).is_dir():
            self._thumb_strip.grid_remove()
            self._preview_frame.configure(height=270)
            return
        imgs = get_image_files(folder)
        if not imgs:
            self._thumb_strip.grid_remove()
            self._preview_frame.configure(height=270)
            return
        TW, TH = 56, 32
        for i, img_path in enumerate(imgs):
            try:
                thumb = Image.open(str(img_path))
                thumb = self._crop_img_to_16_9(thumb, TW, TH)
                ctk_thumb = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=(TW, TH))
                self._thumb_strip_imgs.append(ctk_thumb)
                btn = ctk.CTkButton(
                    self._thumb_strip,
                    image=ctk_thumb, text="",
                    width=TW + 4, height=TH + 4,
                    fg_color=C_CARD, hover_color=C_HOVER,
                    border_width=1, border_color=C_BORDER,
                    corner_radius=3,
                    command=lambda p=str(img_path): self._load_preview(p),
                )
                btn.grid(row=0, column=i, padx=2, pady=2)
            except Exception:
                pass
        self._preview_frame.configure(height=320)
        self._thumb_strip.grid()

    def _validate_slideshow_inputs(self) -> bool:
        errors: list[str] = []
        folder = self._var_sl_images_folder.get()
        if not folder or not Path(folder).is_dir():
            errors.append("• Selecciona una carpeta de im\u00e1genes v\u00e1lida.")
        else:
            imgs = get_image_files(folder)
            if len(imgs) < 2:
                errors.append("• Se necesitan al menos 2 im\u00e1genes para generar un slideshow.")
        out_folder = self._var_sl_output_folder.get()
        if not out_folder:
            errors.append("• Selecciona una carpeta de salida.")
        out_name = self._var_sl_output_name.get().strip()
        if not out_name:
            errors.append("• Ingresa un nombre para el archivo de salida.")
        if self._var_sl_audio_enabled.get():
            if self._var_sl_audio_mode.get() == "file":
                af = self._var_sl_audio_file.get()
                if not af or not Path(af).is_file():
                    errors.append("• Selecciona un archivo de audio v\u00e1lido.")
            else:
                af = self._var_sl_audio_folder.get()
                if not af or not Path(af).is_dir():
                    errors.append("• Selecciona una carpeta de audios v\u00e1lida.")
                elif not get_audio_files(af):
                    errors.append("• La carpeta de audios no contiene archivos soportados.")
        if errors:
            messagebox.showerror("Campos requeridos", "\n".join(errors))
            return False
        return True

    def _collect_slideshow_settings(self) -> None:
        self.settings.update({
            "sl_images_folder": self._var_sl_images_folder.get(),
            "sl_audio_enabled": self._var_sl_audio_enabled.get(),
            "sl_audio_mode": self._var_sl_audio_mode.get(),
            "sl_audio_file": self._var_sl_audio_file.get()
                if (self._var_sl_audio_enabled.get() and self._var_sl_audio_mode.get() == "file") else "",
            "sl_audio_folder": self._var_sl_audio_folder.get()
                if (self._var_sl_audio_enabled.get() and self._var_sl_audio_mode.get() == "folder") else "",
            "sl_crossfade": round(self._var_sl_crossfade.get(), 1),
            "sl_output_folder": self._var_sl_output_folder.get(),
            "sl_output_name": self._var_sl_output_name.get().strip() or "slideshow",
            "sl_duration": round(self._var_sl_duration.get(), 1),
            "sl_transition": self._var_sl_transition.get(),
            "sl_resolution": self._var_sl_resolution.get(),
            "sl_crf": int(self._var_sl_crf.get()),
            "sl_cpu_mode": self._var_sl_cpu_mode.get(),
            "sl_encode_preset": self._var_sl_encode_preset.get(),
            "sl_gpu_encoding": self._var_sl_gpu_encoding.get(),
            "sl_enable_breath": self._var_sl_breath.get(),
            "sl_breath_intensity": round(self._var_sl_breath_intensity.get(), 3),
            "sl_breath_speed": round(self._var_sl_breath_speed.get(), 1),
            "sl_enable_light_zoom": self._var_sl_light_zoom.get(),
            "sl_light_zoom_max": round(self._var_sl_light_zoom_max.get(), 3),
            "sl_light_zoom_speed": round(self._var_sl_light_zoom_speed.get(), 1),
            "sl_enable_vignette": self._var_sl_vignette.get(),
            "sl_vignette_intensity": round(self._var_sl_vignette_intensity.get(), 1),
            "sl_enable_color_shift": self._var_sl_color_shift.get(),
            "sl_color_shift_amount": round(self._var_sl_color_shift_amount.get(), 0),
            "sl_color_shift_speed": round(self._var_sl_color_shift_speed.get(), 1),
            # Text overlay estático (Slideshow)
            "sl_enable_text_overlay":    self._var_sl_text_overlay.get() if hasattr(self, "_var_sl_text_overlay") else False,
            "sl_text_content":           self._var_sl_text_content.get() if hasattr(self, "_var_sl_text_content") else "",
            "sl_text_position":          self._var_sl_text_position.get() if hasattr(self, "_var_sl_text_position") else "Bottom",
            "sl_text_margin":            int(self._var_sl_text_margin.get()) if hasattr(self, "_var_sl_text_margin") else 40,
            "sl_text_font_size":         int(self._var_sl_text_font_size.get()) if hasattr(self, "_var_sl_text_font_size") else 36,
            "sl_text_font":              self._var_sl_text_font.get() if hasattr(self, "_var_sl_text_font") else "Arial",
            "sl_text_color":             self._var_sl_text_color.get() if hasattr(self, "_var_sl_text_color") else "Blanco",
            "sl_text_glitch_intensity":  int(self._var_sl_text_glitch_intensity.get()) if hasattr(self, "_var_sl_text_glitch_intensity") else 3,
            "sl_text_glitch_speed":      round(self._var_sl_text_glitch_speed.get(), 1) if hasattr(self, "_var_sl_text_glitch_speed") else 4.0,
            # Text overlay dinámico (Slideshow)
            "sl_enable_dyn_text_overlay": self._var_sl_dyn_text_overlay.get() if hasattr(self, "_var_sl_dyn_text_overlay") else False,
            "sl_dyn_text_mode":          self._var_sl_dyn_text_mode.get() if hasattr(self, "_var_sl_dyn_text_mode") else "Texto fijo",
            "sl_dyn_text_content":       self._var_sl_dyn_text_content.get() if hasattr(self, "_var_sl_dyn_text_content") else "",
            "sl_dyn_text_position":      self._var_sl_dyn_text_position.get() if hasattr(self, "_var_sl_dyn_text_position") else "Bottom",
            "sl_dyn_text_margin":        int(self._var_sl_dyn_text_margin.get()) if hasattr(self, "_var_sl_dyn_text_margin") else 40,
            "sl_dyn_text_font_size":     int(self._var_sl_dyn_text_font_size.get()) if hasattr(self, "_var_sl_dyn_text_font_size") else 36,
            "sl_dyn_text_font":          self._var_sl_dyn_text_font.get() if hasattr(self, "_var_sl_dyn_text_font") else "Arial",
            "sl_dyn_text_color":         self._var_sl_dyn_text_color.get() if hasattr(self, "_var_sl_dyn_text_color") else "Blanco",
            "sl_dyn_text_glitch_intensity": int(self._var_sl_dyn_text_glitch_intensity.get()) if hasattr(self, "_var_sl_dyn_text_glitch_intensity") else 3,
            "sl_dyn_text_glitch_speed":  round(self._var_sl_dyn_text_glitch_speed.get(), 1) if hasattr(self, "_var_sl_dyn_text_glitch_speed") else 4.0,
        })

    def _on_generate_slideshow(self) -> None:
        if not self._validate_slideshow_inputs():
            return

        self._collect_slideshow_settings()
        self._set_processing_state(True)
        self._clear_log()

        imgs = get_image_files(self._var_sl_images_folder.get())
        audio_path: Path | None = None
        if self._var_sl_audio_enabled.get():
            if self._var_sl_audio_mode.get() == "file":
                af = self._var_sl_audio_file.get()
                if af and Path(af).is_file():
                    audio_path = Path(af)
            # folder mode: audio_path stays None; SlideshowRunner handles the merge

        out_name = self._var_sl_output_name.get().strip() or "slideshow"
        out_path = Path(self._var_sl_output_folder.get()) / f"{out_name}.mp4"

        self._slideshow_runner = SlideshowRunner(
            settings=self.settings.all(),
            on_log=self._queue_log,
            on_finished=self._on_slideshow_finished,
        )
        self._slideshow_runner.start(imgs, audio_path, out_path)

    def _on_slideshow_finished(self, success: bool) -> None:
        self.after(0, self._set_processing_state, False)
        self.after(0, self._play_notify_sound)

    # ------------------------------------------------------------------
    # MODO SHORTS — acciones de UI
    # ------------------------------------------------------------------

    def _sho_browse_audio(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar archivo de audio",
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.aac *.ogg *.m4a"), ("Todos", "*.*")],
        )
        if path:
            self._var_sho_audio.set(path)
            if not self._var_sho_output_folder.get():
                self._var_sho_output_folder.set(str(Path(path).parent))

    def _sho_on_audio_selected(self) -> None:
        """Called when audio file changes — update duration label and suggestion."""
        path = self._var_sho_audio.get()
        if path and Path(path).is_file():
            dur = get_audio_duration(path)
            if dur and dur > 0:
                m, s = divmod(int(dur), 60)
                if hasattr(self, "_sho_lbl_duration"):
                    self._sho_lbl_duration.configure(
                        text=f"Duración: {m}:{s:02d} ({dur:.1f}s)")
                self._sho_update_fragment_suggestion()
                return
        if hasattr(self, "_sho_lbl_duration"):
            self._sho_lbl_duration.configure(text="Duración: —")

    def _sho_update_fragment_suggestion(self) -> None:
        """Update suggested quantity label based on audio duration and short duration."""
        if not hasattr(self, "_sho_lbl_suggestion"):
            return
        path = self._var_sho_audio.get() if hasattr(self, "_var_sho_audio") else ""
        if not (path and Path(path).is_file()):
            self._sho_lbl_suggestion.configure(text="Sugerencia: —")
            return
        dur = get_audio_duration(path)
        if not dur or dur <= 0:
            self._sho_lbl_suggestion.configure(text="Sugerencia: —")
            return
        short_s = self._var_sho_duration.get() if hasattr(self, "_var_sho_duration") else 45
        suggested = suggest_quantity(dur, short_s)
        self._sho_lbl_suggestion.configure(
            text=f"Sugerencia: {suggested} shorts para este audio")

    def _sho_browse_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar imagen de fondo",
            filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.bmp *.webp"), ("Todos", "*.*")],
        )
        if path:
            self._var_sho_image.set(path)

    def _on_sho_image_change(self) -> None:
        if getattr(self, "_current_mode", "") != "Shorts":
            return
        path = self._var_sho_image.get()
        if path and Path(path).is_file():
            self._load_preview(path)

    def _sho_browse_images_folder(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta de imágenes")
        if path:
            self._var_sho_images_folder.set(path)
            imgs = get_image_files(path)
            n = len(imgs)
            if hasattr(self, "_sho_lbl_img_count"):
                self._sho_lbl_img_count.configure(text=f"\u266b Imágenes: {n}")
            if imgs:
                self._load_preview(str(imgs[0]))
            self._sho_image_paths = imgs
            self._rebuild_thumb_strip_sho()

    def _sho_toggle_multi_image(self) -> None:
        multi = self._var_sho_multi_image.get()
        if multi:
            self._sho_single_img_wrapper.grid_remove()
            self._sho_multi_img_wrapper.grid()
            self._rebuild_thumb_strip_sho()
        else:
            self._sho_multi_img_wrapper.grid_remove()
            self._sho_single_img_wrapper.grid()
            for w in self._thumb_strip_vert.winfo_children():
                w.destroy()
            self._thumb_strip_vert_imgs.clear()
            self._thumb_strip_vert.grid_remove()
            if getattr(self, "_current_mode", "") == "Shorts":
                path = self._var_sho_image.get()
                if path and Path(path).is_file():
                    self._load_preview(path)

    def _sho_browse_output(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if path:
            self._var_sho_output_folder.set(path)

    def _sho_toggle_text_overlay(self) -> None:
        if self._var_sho_text_overlay.get():
            self._sho_text_overlay_frame.grid()
        else:
            self._sho_text_overlay_frame.grid_remove()
        if getattr(self, "_current_mode", "") == "Shorts":
            self._update_preview_overlay()

    def _on_sho_naming_mode_change(self, mode: str) -> None:
        needs_name   = mode == "Nombre"
        show_prefix  = mode in ("Prefijo", "Prefijo + Lista personalizada")
        show_list    = mode in ("Lista personalizada", "Prefijo + Lista personalizada")

        if hasattr(self, "_sho_naming_name_frame"):
            if needs_name:
                self._sho_naming_name_frame.grid()
            else:
                self._sho_naming_name_frame.grid_remove()
        if hasattr(self, "_sho_naming_prefix_frame"):
            if show_prefix:
                self._sho_naming_prefix_frame.grid()
            else:
                self._sho_naming_prefix_frame.grid_remove()
        if hasattr(self, "_sho_naming_list_frame"):
            if show_list:
                self._sho_naming_list_frame.grid()
            else:
                self._sho_naming_list_frame.grid_remove()

        # "Nombre": auto-number es obligatorio y no se puede desactivar
        if hasattr(self, "_cb_sho_naming_autonumber"):
            if needs_name:
                self._var_sho_naming_autonumber.set(True)
                self._cb_sho_naming_autonumber.configure(state="disabled")
            else:
                self._cb_sho_naming_autonumber.configure(state="normal")

    def _refresh_sho_names_count(self) -> None:
        if not hasattr(self, "_txt_sho_naming_list"):
            return
        _p = NamesListDialog._USED_PREFIX
        raw = [l.strip() for l in self._txt_sho_naming_list.get("1.0", "end").splitlines()
               if l.strip()]
        count = len(raw)
        if hasattr(self, "_lbl_sho_names_count"):
            self._lbl_sho_names_count.configure(
                text=f"{count} nombre{'s' if count != 1 else ''}")

    def _open_sho_names_list_dialog(self) -> None:
        if not hasattr(self, "_txt_sho_naming_list"):
            return
        _p = NamesListDialog._USED_PREFIX
        raw = [l.strip() for l in self._txt_sho_naming_list.get("1.0", "end").splitlines()
               if l.strip()]
        current = [(n[len(_p):] if n.startswith(_p) else n) for n in raw]
        used: set[str] = set(self._sho_used_names) if hasattr(self, "_sho_used_names") else set()
        dlg = NamesListDialog(self, current, used_names=used)
        self.wait_window(dlg)
        if dlg.result is not None:
            self._txt_sho_naming_list.delete("1.0", "end")
            if dlg.result:
                self._txt_sho_naming_list.insert("1.0", "\n".join(dlg.result))
            self._refresh_sho_names_count()

    def _validate_shorts_inputs(self) -> bool:
        audio = self._var_sho_audio.get() if hasattr(self, "_var_sho_audio") else ""
        if not audio or not Path(audio).is_file():
            self._log("ERROR: Selecciona un archivo de audio válido.")
            return False
        multi = self._var_sho_multi_image.get() if hasattr(self, "_var_sho_multi_image") else False
        if multi:
            folder = self._var_sho_images_folder.get() if hasattr(self, "_var_sho_images_folder") else ""
            imgs = get_image_files(folder) if folder and Path(folder).is_dir() else []
            if not imgs:
                self._log("ERROR: La carpeta de imágenes está vacía o no existe.")
                return False
        else:
            img = self._var_sho_image.get() if hasattr(self, "_var_sho_image") else ""
            if not img or not Path(img).is_file():
                self._log("ERROR: Selecciona una imagen de fondo válida.")
                return False
        out = self._var_sho_output_folder.get() if hasattr(self, "_var_sho_output_folder") else ""
        if not out:
            self._log("ERROR: Selecciona una carpeta de salida.")
            return False
        dur = get_audio_duration(audio)
        qty = int(self._var_sho_quantity.get()) if hasattr(self, "_var_sho_quantity") else 1
        short_s = int(self._var_sho_duration.get()) if hasattr(self, "_var_sho_duration") else 45
        ok, msg = validate_request(dur or 0.0, short_s, qty)
        if not ok:
            self._log(f"ERROR: {msg}")
            return False
        if msg:
            self._log(f"Advertencia: {msg}")
        return True

    def _collect_shorts_settings(self) -> None:
        if not hasattr(self, "_var_sho_audio"):
            return
        multi = self._var_sho_multi_image.get()
        self.settings.update({
            "sho_audio_file":       self._var_sho_audio.get(),
            "sho_background_image": self._var_sho_image.get() if hasattr(self, "_var_sho_image") else "",
            "sho_images_folder":    self._var_sho_images_folder.get() if hasattr(self, "_var_sho_images_folder") else "",
            "sho_multi_image":      multi,
            "sho_output_folder":    self._var_sho_output_folder.get() if hasattr(self, "_var_sho_output_folder") else "",
            "sho_duration":         int(self._var_sho_duration.get()) if hasattr(self, "_var_sho_duration") else 45,
            "sho_quantity":         int(self._var_sho_quantity.get()) if hasattr(self, "_var_sho_quantity") else 3,
            "sho_resolution":       self._var_sho_resolution.get() if hasattr(self, "_var_sho_resolution") else "1080p",
            "sho_enable_breath":    self._var_sho_breath.get() if hasattr(self, "_var_sho_breath") else False,
            "sho_breath_intensity": round(self._var_sho_breath_intensity.get(), 3) if hasattr(self, "_var_sho_breath_intensity") else 0.04,
            "sho_breath_speed":     round(self._var_sho_breath_speed.get(), 1) if hasattr(self, "_var_sho_breath_speed") else 1.0,
            "sho_enable_light_zoom": self._var_sho_light_zoom.get() if hasattr(self, "_var_sho_light_zoom") else False,
            "sho_light_zoom_max":   round(self._var_sho_light_zoom_max.get(), 3) if hasattr(self, "_var_sho_light_zoom_max") else 1.04,
            "sho_light_zoom_speed": round(self._var_sho_light_zoom_speed.get(), 1) if hasattr(self, "_var_sho_light_zoom_speed") else 0.5,
            "sho_enable_vignette":  self._var_sho_vignette.get() if hasattr(self, "_var_sho_vignette") else False,
            "sho_vignette_intensity": round(self._var_sho_vignette_intensity.get(), 1) if hasattr(self, "_var_sho_vignette_intensity") else 0.4,
            "sho_enable_color_shift": self._var_sho_color_shift.get() if hasattr(self, "_var_sho_color_shift") else False,
            "sho_color_shift_amount": round(self._var_sho_color_shift_amount.get(), 0) if hasattr(self, "_var_sho_color_shift_amount") else 15.0,
            "sho_color_shift_speed": round(self._var_sho_color_shift_speed.get(), 1) if hasattr(self, "_var_sho_color_shift_speed") else 0.5,
            "sho_enable_glitch":    self._var_sho_glitch.get() if hasattr(self, "_var_sho_glitch") else False,
            "sho_glitch_intensity": int(self._var_sho_glitch_intensity.get()) if hasattr(self, "_var_sho_glitch_intensity") else 4,
            "sho_glitch_speed":     int(self._var_sho_glitch_speed_fx.get()) if hasattr(self, "_var_sho_glitch_speed_fx") else 90,
            "sho_glitch_pulse":     int(self._var_sho_glitch_pulse.get()) if hasattr(self, "_var_sho_glitch_pulse") else 3,
            "sho_normalize_audio":  self._var_sho_normalize.get() if hasattr(self, "_var_sho_normalize") else False,
            "sho_fade_in":          round(self._var_sho_fade_in.get(), 2) if hasattr(self, "_var_sho_fade_in") else 0.5,
            "sho_fade_out":         round(self._var_sho_fade_out.get(), 2) if hasattr(self, "_var_sho_fade_out") else 0.5,
            "sho_enable_text_overlay": self._var_sho_text_overlay.get() if hasattr(self, "_var_sho_text_overlay") else False,
            "sho_text_content":     self._var_sho_text_content.get() if hasattr(self, "_var_sho_text_content") else "",
            "sho_text_position":    self._var_sho_text_position.get() if hasattr(self, "_var_sho_text_position") else "Bottom",
            "sho_text_margin":      int(self._var_sho_text_margin.get()) if hasattr(self, "_var_sho_text_margin") else 40,
            "sho_text_font_size":   int(self._var_sho_text_font_size.get()) if hasattr(self, "_var_sho_text_font_size") else 36,
            "sho_text_font":        self._var_sho_text_font.get() if hasattr(self, "_var_sho_text_font") else "Arial",
            "sho_text_color":       self._var_sho_text_color.get() if hasattr(self, "_var_sho_text_color") else "Blanco",
            "sho_text_glitch_intensity": int(self._var_sho_text_glitch_intensity.get()) if hasattr(self, "_var_sho_text_glitch_intensity") else 3,
            "sho_text_glitch_speed": float(self._var_sho_text_glitch_speed.get()) if hasattr(self, "_var_sho_text_glitch_speed") else 4.0,
            # Text overlay dinámico (Shorts)
            "sho_enable_dyn_text_overlay": self._var_sho_dyn_text_overlay.get() if hasattr(self, "_var_sho_dyn_text_overlay") else False,
            "sho_dyn_text_mode":          self._var_sho_dyn_text_mode.get() if hasattr(self, "_var_sho_dyn_text_mode") else "Texto fijo",
            "sho_dyn_text_content":       self._var_sho_dyn_text_content.get() if hasattr(self, "_var_sho_dyn_text_content") else "",
            "sho_dyn_text_position":      self._var_sho_dyn_text_position.get() if hasattr(self, "_var_sho_dyn_text_position") else "Bottom",
            "sho_dyn_text_margin":        int(self._var_sho_dyn_text_margin.get()) if hasattr(self, "_var_sho_dyn_text_margin") else 40,
            "sho_dyn_text_font_size":     int(self._var_sho_dyn_text_font_size.get()) if hasattr(self, "_var_sho_dyn_text_font_size") else 36,
            "sho_dyn_text_font":          self._var_sho_dyn_text_font.get() if hasattr(self, "_var_sho_dyn_text_font") else "Arial",
            "sho_dyn_text_color":         self._var_sho_dyn_text_color.get() if hasattr(self, "_var_sho_dyn_text_color") else "Blanco",
            "sho_dyn_text_glitch_intensity": int(self._var_sho_dyn_text_glitch_intensity.get()) if hasattr(self, "_var_sho_dyn_text_glitch_intensity") else 3,
            "sho_dyn_text_glitch_speed":  round(self._var_sho_dyn_text_glitch_speed.get(), 1) if hasattr(self, "_var_sho_dyn_text_glitch_speed") else 4.0,
            "sho_naming_mode":      self._var_sho_naming_mode.get() if hasattr(self, "_var_sho_naming_mode") else "Default",
            "sho_naming_name":       self._var_sho_naming_name.get() if hasattr(self, "_var_sho_naming_name") else "",
            "sho_naming_prefix":    self._var_sho_naming_prefix.get() if hasattr(self, "_var_sho_naming_prefix") else "",
            "sho_naming_custom_list": "\n".join(
                [l.strip() for l in (self._txt_sho_naming_list.get("1.0", "end").splitlines()
                                     if hasattr(self, "_txt_sho_naming_list") else [])
                 if l.strip()]
            ),
            "sho_naming_auto_number": self._var_sho_naming_autonumber.get() if hasattr(self, "_var_sho_naming_autonumber") else True,
            "sho_crf":              int(self._var_sho_crf.get()) if hasattr(self, "_var_sho_crf") else 18,
            "sho_cpu_mode":         self._var_sho_cpu_mode.get() if hasattr(self, "_var_sho_cpu_mode") else "Medium",
            "sho_encode_preset":    self._var_sho_encode_preset.get() if hasattr(self, "_var_sho_encode_preset") else "slow",
            "sho_gpu_encoding":     self._var_sho_gpu_encoding.get() if hasattr(self, "_var_sho_gpu_encoding") else False,
        })

    def _on_generate_shorts(self) -> None:
        self._collect_settings()
        if not self._validate_shorts_inputs():
            return
        s = self.settings.all()
        audio = s["sho_audio_file"]
        multi = s["sho_multi_image"]
        if multi:
            folder = s["sho_images_folder"]
            image_paths = get_image_files(folder) if folder and Path(folder).is_dir() else []
        else:
            img = s["sho_background_image"]
            image_paths = [Path(img)] if img and Path(img).is_file() else []
        if not image_paths:
            self._log("ERROR: No se encontraron imágenes válidas.")
            return

        audio_dur  = get_audio_duration(audio) or 0.0
        short_s    = int(s["sho_duration"])
        qty        = int(s["sho_quantity"])
        starts     = distribute_fragments(audio_dur, short_s, qty)
        out_folder = Path(s["sho_output_folder"])

        # Build output names via NamingManager
        custom_list = [ln.strip() for ln in s.get("sho_naming_custom_list", "").splitlines()
                       if ln.strip()]
        sho_nm_mode = s["sho_naming_mode"]
        nm = _NamingManager(
            mode=sho_nm_mode,
            prefix=(
                s.get("sho_naming_name", "")
                if sho_nm_mode == "Nombre"
                else s["sho_naming_prefix"]
            ),
            custom_names=custom_list,
            auto_number=s["sho_naming_auto_number"],
        )
        audio_path   = Path(audio)
        output_names = nm.generate_names([audio_path] * qty)

        self._set_processing_state(True)
        self._log(f"Generando {qty} short(s) desde: {audio_path.name}")

        self._shorts_runner = ShortsRunner(
            settings=s,
            on_log=lambda msg: self.after(0, self._log, msg),
            on_progress=lambda done, tot, label: self.after(
                0, self._update_progress_ui, done, tot, label),
            on_job_done=lambda r: self.after(0, self._on_sho_result, r),
            on_finished=lambda results: self.after(0, self._on_shorts_finished, results),
        )
        self._shorts_runner.start(
            audio_path=audio_path,
            image_paths=image_paths,
            output_folder=out_folder,
            starts=starts,
            short_duration=float(short_s),
            output_names=output_names,
        )

    def _on_sho_result(self, result: "ShortsJobResult") -> None:
        status = "\u2713" if result.success else "\u2717"
        name = result.output_path.name if result.output_path else f"short_{result.index}"
        elapsed = f"{result.elapsed:.1f}s"
        if result.success:
            self._log(f"  [{status}] {name}  ({elapsed})")
        else:
            self._log(f"  [{status}] {name}  ERROR: {result.error}")

    def _on_shorts_finished(self, results: list) -> None:
        self._set_processing_state(False)
        n_ok  = sum(1 for r in results if r.success)
        n_tot = len(results)
        if n_ok == n_tot:
            self._log(f"\u2713 {n_ok}/{n_tot} shorts generados correctamente.")
        else:
            self._log(f"\u26a0 {n_ok}/{n_tot} shorts generados. Revisa los errores.")
        self._play_notify_sound()

    # ------------------------------------------------------------------
    # ACCIONES DE UI
    # ------------------------------------------------------------------

    def _browse_audio_folder(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta de audios")
        if path:
            self._var_audio_folder.set(path)
            self._update_audio_count(path)

    def _browse_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar imagen de fondo",
            filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.bmp *.webp"), ("Todos", "*.*")],
        )
        if path:
            self._var_image.set(path)
            self._load_preview(path)

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if path:
            self._var_output.set(path)

    def _browse_overlay(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar video overlay",
            filetypes=[("Videos", "*.mp4 *.mov *.avi *.mkv *.webm"), ("Todos", "*.*")],
        )
        if path:
            self._var_overlay_path.set(path)

    def _toggle_multi_image(self) -> None:
        if self._var_multi_image.get():
            self._single_image_wrapper.grid_remove()
            self._multi_image_wrapper.grid()
            self._load_preview_from_images_folder()
        else:
            self._multi_image_wrapper.grid_remove()
            self._single_image_wrapper.grid()
            single = self._var_image.get()
            if single and Path(single).is_file():
                self._load_preview(single)
        self._rebuild_thumb_strip()
        # Refresh count display
        audio = self._var_audio_folder.get()
        if audio and Path(audio).is_dir():
            self._update_audio_count(audio)

    def _browse_images_folder(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta de imágenes")
        if path:
            self._var_images_folder.set(path)
            self._image_assignment = {}  # reset assignment when folder changes
            self._load_preview_from_images_folder()
            self._rebuild_thumb_strip()
            audio = self._var_audio_folder.get()
            if audio and Path(audio).is_dir():
                self._update_audio_count(audio)

    def _load_preview_from_images_folder(self) -> None:
        """Carga el preview con la primera imagen de la carpeta de imágenes."""
        folder = self._var_images_folder.get()
        if not folder or not Path(folder).is_dir():
            return
        imgs = get_image_files(folder)
        if imgs:
            self._load_preview(str(imgs[0]))

    def _rebuild_thumb_strip(self) -> None:
        """Repobla el filmstrip de miniaturas con las imágenes de la carpeta activa."""
        for w in self._thumb_strip.winfo_children():
            w.destroy()
        self._thumb_strip_imgs.clear()
        if not self._var_multi_image.get():
            self._thumb_strip.grid_remove()
            self._preview_frame.configure(height=270)
            return
        folder = self._var_images_folder.get()
        if not folder or not Path(folder).is_dir():
            self._thumb_strip.grid_remove()
            self._preview_frame.configure(height=270)
            return
        imgs = get_image_files(folder)
        if not imgs:
            self._thumb_strip.grid_remove()
            self._preview_frame.configure(height=270)
            return
        TW, TH = 56, 32  # 16:9 thumbnail size
        for i, img_path in enumerate(imgs):
            try:
                thumb = Image.open(str(img_path))
                thumb = self._crop_img_to_16_9(thumb, TW, TH)
                ctk_thumb = ctk.CTkImage(light_image=thumb, dark_image=thumb, size=(TW, TH))
                self._thumb_strip_imgs.append(ctk_thumb)
                btn = ctk.CTkButton(
                    self._thumb_strip,
                    image=ctk_thumb, text="",
                    width=TW + 4, height=TH + 4,
                    fg_color=C_CARD, hover_color=C_HOVER,
                    border_width=1, border_color=C_BORDER,
                    corner_radius=3,
                    command=lambda p=str(img_path): self._load_preview(p),
                )
                btn.grid(row=0, column=i, padx=2, pady=2)
            except Exception:
                pass
        self._preview_frame.configure(height=320)
        self._thumb_strip.grid()

    def _open_image_assignment(self) -> None:
        audio_folder = self._var_audio_folder.get()
        images_folder = self._var_images_folder.get()
        if not audio_folder or not Path(audio_folder).is_dir():
            messagebox.showwarning("Asignación", "Selecciona primero una carpeta de audios válida.")
            return
        if not images_folder or not Path(images_folder).is_dir():
            messagebox.showwarning("Asignación", "Selecciona primero una carpeta de imágenes válida.")
            return
        audio_files = get_audio_files(audio_folder)
        image_files = get_image_files(images_folder)
        if not audio_files:
            messagebox.showwarning("Asignación", "No se encontraron audios en la carpeta seleccionada.")
            return
        if not image_files:
            messagebox.showwarning("Asignación", "No se encontraron imágenes en la carpeta seleccionada.")
            return
        current = getattr(self, "_image_assignment", {})
        dlg = ImageAssignmentDialog(self, audio_files, image_files, current)
        self.wait_window(dlg)
        if dlg.result is not None:
            self._image_assignment = dlg.result
            self._log(f"? Asignación guardada: {len(dlg.result)} audio(s).")

    def _open_names_list_dialog(self) -> None:
        _p = NamesListDialog._USED_PREFIX
        raw = [l.strip() for l in self._txt_naming_list.get("1.0", "end").splitlines() if l.strip()]
        # Strip ¦ prefix to get clean names for passing as current_names
        current = [(n[len(_p):] if n.startswith(_p) else n) for n in raw]
        dlg = NamesListDialog(self, current, used_names=self._used_names)
        self.wait_window(dlg)
        if dlg.result is not None:
            self._txt_naming_list.delete("1.0", "end")
            if dlg.result:
                self._txt_naming_list.insert("1.0", "\n".join(dlg.result))
            self._refresh_names_count()

    def _refresh_names_count(self) -> None:
        if not hasattr(self, "_lbl_names_count"):
            return
        _p = NamesListDialog._USED_PREFIX
        raw = [l.strip() for l in self._txt_naming_list.get("1.0", "end").splitlines() if l.strip()]
        clean_names = [(n[len(_p):] if n.startswith(_p) else n) for n in raw]
        n = len(clean_names)
        used = sum(1 for name in clean_names if name in self._used_names)
        label = f"{n} nombre{'s' if n != 1 else ''}"
        if used:
            label += f" ({used} usados)"
        self._lbl_names_count.configure(text=label)

    def _reload_folders(self) -> None:
        """Revalida carpetas y actualiza conteos de audios e imágenes."""
        audio = self._var_audio_folder.get()
        if audio and Path(audio).is_dir():
            self._update_audio_count(audio)
        elif hasattr(self, "_lbl_audio_count"):
            self._lbl_audio_count.configure(text="Audios: —", text_color=C_MUTED)
        # Si multi-imagen, recontar imágenes (ya incluido en _update_audio_count)
        # Si no hay carpeta de audio pero sí de imágenes en modo multi, actualizar igual
        if (getattr(self, "_var_multi_image", None) and self._var_multi_image.get()
                and not (audio and Path(audio).is_dir())):
            imgs_folder = self._var_images_folder.get()
            if imgs_folder and Path(imgs_folder).is_dir():
                try:
                    n_imgs = len(get_image_files(imgs_folder))
                    self._lbl_audio_count.configure(
                        text=f"Audios: —  |  Imágenes: {n_imgs}",
                        text_color=C_MUTED,
                    )
                except Exception:
                    pass
        # Reconstruir el filmstrip con las imágenes actuales de la carpeta
        self._rebuild_thumb_strip()

    def _toggle_overlay_widgets(self) -> None:
        if self._var_overlay.get():
            self._overlay_frame.grid()
        else:
            self._overlay_frame.grid_remove()

    def _toggle_text_overlay_widgets(self) -> None:
        if self._var_text_overlay.get():
            self._text_overlay_frame.grid()
        else:
            self._text_overlay_frame.grid_remove()

    def _toggle_dyn_text_overlay_widgets(self) -> None:
        if self._var_dyn_text_overlay.get():
            self._dyn_text_overlay_frame.grid()
        else:
            self._dyn_text_overlay_frame.grid_remove()
        if getattr(self, "_current_mode", "") == "Audio \u2192 Video":
            self._update_preview_overlay()

    def _on_dyn_text_mode_change(self) -> None:
        mode = self._var_dyn_text_mode.get() if hasattr(self, "_var_dyn_text_mode") else "Texto fijo"
        if hasattr(self, "_dyn_text_fixed_frame"):
            if mode == "Texto fijo":
                self._dyn_text_fixed_frame.grid()
            else:
                self._dyn_text_fixed_frame.grid_remove()
        if getattr(self, "_current_mode", "") == "Audio \u2192 Video":
            self._update_preview_overlay()

    def _sl_toggle_text_overlay_widgets(self) -> None:
        if self._var_sl_text_overlay.get():
            self._sl_text_overlay_frame.grid()
        else:
            self._sl_text_overlay_frame.grid_remove()

    def _sl_toggle_dyn_text_overlay_widgets(self) -> None:
        if self._var_sl_dyn_text_overlay.get():
            self._sl_dyn_text_overlay_frame.grid()
        else:
            self._sl_dyn_text_overlay_frame.grid_remove()

    def _on_sl_dyn_text_mode_change(self) -> None:
        mode = self._var_sl_dyn_text_mode.get() if hasattr(self, "_var_sl_dyn_text_mode") else "Texto fijo"
        if hasattr(self, "_sl_dyn_text_fixed_frame"):
            if mode == "Texto fijo":
                self._sl_dyn_text_fixed_frame.grid()
            else:
                self._sl_dyn_text_fixed_frame.grid_remove()

    def _sho_toggle_dyn_text_overlay(self) -> None:
        if self._var_sho_dyn_text_overlay.get():
            self._sho_dyn_text_overlay_frame.grid()
        else:
            self._sho_dyn_text_overlay_frame.grid_remove()
        if getattr(self, "_current_mode", "") == "Shorts":
            self._update_preview_overlay()

    def _on_sho_dyn_text_mode_change(self) -> None:
        mode = self._var_sho_dyn_text_mode.get() if hasattr(self, "_var_sho_dyn_text_mode") else "Texto fijo"
        if hasattr(self, "_sho_dyn_text_fixed_frame"):
            if mode == "Texto fijo":
                self._sho_dyn_text_fixed_frame.grid()
            else:
                self._sho_dyn_text_fixed_frame.grid_remove()
        if getattr(self, "_current_mode", "") == "Shorts":
            self._update_preview_overlay()

    def _on_naming_mode_change(self, mode: str) -> None:
        """Muestra u oculta el campo de prefijo y/o la lista según el modo elegido."""
        needs_name   = mode == "Nombre"
        needs_prefix = mode in ("Prefijo", "Prefijo + Lista personalizada")
        needs_list   = mode in ("Lista personalizada", "Prefijo + Lista personalizada")

        if hasattr(self, "_naming_name_frame"):
            if needs_name:
                self._naming_name_frame.grid()
            else:
                self._naming_name_frame.grid_remove()

        if needs_prefix:
            self._naming_prefix_frame.grid()
        else:
            self._naming_prefix_frame.grid_remove()

        if needs_list:
            self._naming_list_frame.grid()
        else:
            self._naming_list_frame.grid_remove()

        # "Nombre": auto-number es obligatorio y no se puede desactivar
        if hasattr(self, "_cb_naming_autonumber"):
            if needs_name:
                self._var_naming_autonumber.set(True)
                self._cb_naming_autonumber.configure(state="disabled")
            else:
                self._cb_naming_autonumber.configure(state="normal")

    def _apply_preset(self, name: str) -> None:
        self.settings.apply_preset(name)
        self._load_settings_to_ui()
        self._log(f"?? Preset '{name}' aplicado.")

    # ------------------------------------------------------------------
    # Preset management — tiles
    # ------------------------------------------------------------------

    def _open_presets_dialog(self) -> None:
        """Abre (o enfoca) el diálogo global de gestión de presets."""
        if self._presets_dialog and self._presets_dialog.winfo_exists():
            self._presets_dialog.focus()
            return
        self._presets_dialog = PresetsDialog(self)

    def _rebuild_preset_tiles(self) -> None:
        """Reconstruye los tiles de presets en grid de 2 columnas."""
        if (
            self._preset_tiles_frame is None
            or not self._preset_tiles_frame.winfo_exists()
        ):
            return
        for w in self._preset_tiles_frame.winfo_children():
            w.destroy()
        self._preset_tiles_frame.grid_columnconfigure(0, weight=1)
        self._preset_tiles_frame.grid_columnconfigure(1, weight=1)

        names = self.settings.available_presets()
        for i, name in enumerate(names):
            r, col = divmod(i, 2)
            tile = ctk.CTkFrame(
                self._preset_tiles_frame, fg_color=C_BTN_SECONDARY,
                corner_radius=8, border_width=1, border_color=C_BORDER,
            )
            tile.grid(row=r, column=col, sticky="ew", padx=4, pady=4)
            tile.grid_columnconfigure(0, weight=1)

            # Nombre del preset — clic para cargar
            name_row = ctk.CTkFrame(tile, fg_color="transparent")
            name_row.grid(row=0, column=0, sticky="ew", padx=(6, 0), pady=(6, 0))
            name_row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                name_row, text=FA_PLAY, width=20,
                font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(10)),
                text_color=C_TEXT_DIM,
            ).grid(row=0, column=0, padx=(2, 0))
            ctk.CTkButton(
                name_row, text=name, anchor="w", height=32,
                fg_color="transparent", hover_color=C_HOVER,
                text_color=C_TEXT, corner_radius=6,
                font=ctk.CTkFont(size=self._fs(12), weight="bold"),
                command=lambda n=name: self._apply_preset(n),
            ).grid(row=0, column=1, sticky="ew")

            # Botones de acción — Font Awesome icons, grandes y separados
            actions = ctk.CTkFrame(tile, fg_color="transparent")
            actions.grid(row=1, column=0, sticky="e", padx=6, pady=(2, 6))

            _fa_btn_font = ctk.CTkFont(family=_FA_FAMILY, size=self._fs(13))
            for icon, color, hover, cmd in [
                (FA_SAVE, C_BTN_OK, "#3aad6a", lambda n=name: self._overwrite_preset(n)),
                (FA_DOWNLOAD, "#4a6a8a", "#5a7a9a", lambda n=name: self._export_preset(n)),
                (FA_EDIT, C_ACCENT, C_ACCENT_H, lambda n=name: self._rename_preset(n)),
                (FA_TRASH, C_BTN_DANGER, "#e05050", lambda n=name: self._delete_preset(n)),
            ]:
                ctk.CTkButton(
                    actions, text=icon, width=36, height=32,
                    fg_color=color, hover_color=hover,
                    text_color="#ffffff", corner_radius=6,
                    font=_fa_btn_font,
                    command=cmd,
                ).pack(side="left", padx=4)

    def _create_new_preset(self) -> None:
        """Crea un nuevo preset con las configuraciones actuales."""
        dialog = ctk.CTkInputDialog(
            text="Nombre del nuevo preset:", title="Nuevo Preset",
        )
        _center_window_on_screen(dialog)
        name = dialog.get_input()
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.settings.available_presets():
            messagebox.showwarning("Nombre duplicado", f"Ya existe un preset '{name}'.")
            return
        self._collect_settings()
        self.settings.save_preset(name, self.settings.all())
        self._rebuild_preset_tiles()
        self._log(f"? Preset '{name}' creado.")

    def _overwrite_preset(self, name: str) -> None:
        """Sobrescribe un preset existente con las configuraciones actuales."""
        if not messagebox.askyesno(
            "Sobrescribir preset",
            f"¿Reemplazar '{name}' con la configuración actual?",
        ):
            return
        self._collect_settings()
        self.settings.save_preset(name, self.settings.all())
        self._log(f"?? Preset '{name}' actualizado.")

    def _delete_preset(self, name: str) -> None:
        """Elimina un preset."""
        if not messagebox.askyesno("Eliminar preset", f"¿Eliminar el preset '{name}'?"):
            return
        try:
            self.settings.delete_preset(name)
            self._rebuild_preset_tiles()
            self._log(f"??? Preset '{name}' eliminado.")
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def _rename_preset(self, old_name: str) -> None:
        """Renombra un preset."""
        dialog = ctk.CTkInputDialog(
            text=f"Nuevo nombre para '{old_name}':", title="Renombrar Preset",
        )
        _center_window_on_screen(dialog)
        new_name = dialog.get_input()
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()
        try:
            self.settings.rename_preset(old_name, new_name)
            self._rebuild_preset_tiles()
            self._log(f"?? Preset '{old_name}' ? '{new_name}'.")
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def _export_preset(self, name: str) -> None:
        """Exporta un preset individual a un archivo JSON."""
        path = filedialog.asksaveasfilename(
            title=f"Exportar preset '{name}'",
            initialfile=f"{name}.json",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Todos los archivos", "*.*")],
        )
        if not path:
            return
        try:
            self.settings.export_preset(name, path)
            self._log(f"?? Preset '{name}' exportado ? {path}")
        except RuntimeError as e:
            messagebox.showerror("Error al exportar", str(e))

    def _import_presets(self) -> None:
        """Importa uno o más presets desde un archivo JSON."""
        path = filedialog.askopenfilename(
            title="Importar presets",
            filetypes=[("JSON", "*.json"), ("Todos los archivos", "*.*")],
        )
        if not path:
            return
        try:
            imported = self.settings.import_presets(path)
            if imported:
                self._rebuild_preset_tiles()
                names_str = ", ".join(f"'{n}'" for n in imported)
                self._log(f"?? Preset(s) importado(s): {names_str}")
            else:
                messagebox.showwarning("Sin datos", "El archivo no contenía presets válidos.")
        except (RuntimeError, ValueError) as e:
            messagebox.showerror("Error al importar", str(e))

    def _update_audio_count(self, folder: str) -> None:
        try:
            files = get_audio_files(folder)
            text = f"\u266b Audios detectados: {len(files)} archivo(s)"
            # Añadir conteo de imágenes en segunda línea si modo multi activo
            if getattr(self, "_var_multi_image", None) and self._var_multi_image.get():
                imgs_folder = self._var_images_folder.get()
                if imgs_folder and Path(imgs_folder).is_dir():
                    try:
                        n_imgs = len(get_image_files(imgs_folder))
                        text += f"\n\u25a3 Im\xe1genes detectadas: {n_imgs} archivo(s)"
                    except Exception:
                        pass
            self._lbl_audio_count.configure(
                text=text,
                text_color=C_SUCCESS if files else C_WARN,
            )
        except Exception:
            self._lbl_audio_count.configure(text="Audios: error leyendo carpeta",
                                             text_color=C_ERROR)

    def _load_preview(self, path: str) -> None:
        """Carga la preview y la guarda en la ranura del modo activo."""
        mode = getattr(self, "_current_mode", "Audio \u2192 Video")
        if mode == "Slideshow":
            self._sl_preview_path = path
        elif mode == "Shorts":
            self._sho_preview_path = path
        else:
            self._atv_preview_path = path
        self._preview_img_path = path
        self._update_preview_overlay()

    @staticmethod
    def _crop_img_to_16_9(img: Image.Image, target_w: int = 480,
                          target_h: int = 270) -> Image.Image:
        """Crop + resize a 16:9 replicando el scale-to-fill + center-crop de FFmpeg."""
        src_w, src_h = img.size
        scale = max(target_w / src_w, target_h / src_h)
        new_w = max(target_w, round(src_w * scale))
        new_h = max(target_h, round(src_h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        return img.crop((left, top, left + target_w, top + target_h))

    @staticmethod
    def _crop_img_to_9_16(img: Image.Image, target_w: int = 203,
                          target_h: int = 360) -> Image.Image:
        """Crop + resize a 9:16 (vertical) replicando el scale-to-fill + center-crop."""
        src_w, src_h = img.size
        scale = max(target_w / src_w, target_h / src_h)
        new_w = max(target_w, round(src_w * scale))
        new_h = max(target_h, round(src_h * scale))
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        return img.crop((left, top, left + target_w, top + target_h))

    def _open_fullscreen_preview(self) -> None:
        """Abre el preview en pantalla completa con los overlays de texto aplicados."""
        mode = getattr(self, "_current_mode", "Audio \u2192 Video")
        if mode == "Shorts":
            path = getattr(self, "_sho_preview_path", "")
        elif mode == "Slideshow":
            path = getattr(self, "_sl_preview_path", "")
        else:
            path = getattr(self, "_atv_preview_path", "")
        if not path:
            return
        try:
            from PIL import Image as _Image
            img_raw = _Image.open(path)
        except Exception:
            return

        # Compute the largest image that fits 90 % of screen
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        if mode == "Shorts":
            max_h = int(sh * 0.9)
            max_w = int(max_h * 9 / 16)
            if max_w > int(sw * 0.9):
                max_w = int(sw * 0.9)
                max_h = int(max_w * 16 / 9)
            img = self._crop_img_to_9_16(img_raw, target_w=max_w, target_h=max_h)
        else:
            max_w = int(sw * 0.9)
            max_h = int(max_w * 9 / 16)
            if max_h > int(sh * 0.9):
                max_h = int(sh * 0.9)
                max_w = int(max_h * 16 / 9)
            img = self._crop_img_to_16_9(img_raw, target_w=max_w, target_h=max_h)

        # Draw overlays at the large size (scaling is image-width-based, auto-correct)
        is_shorts = mode == "Shorts"
        is_slideshow = mode == "Slideshow"
        if is_shorts:
            static_active = (hasattr(self, "_var_sho_text_overlay")
                             and self._var_sho_text_overlay.get()
                             and hasattr(self, "_var_sho_text_content")
                             and self._var_sho_text_content.get().strip())
            dyn_active = (hasattr(self, "_var_sho_dyn_text_overlay")
                          and self._var_sho_dyn_text_overlay.get())
        elif is_slideshow:
            static_active = (hasattr(self, "_var_sl_text_overlay")
                             and self._var_sl_text_overlay.get()
                             and hasattr(self, "_var_sl_text_content")
                             and self._var_sl_text_content.get().strip())
            dyn_active = (hasattr(self, "_var_sl_dyn_text_overlay")
                          and self._var_sl_dyn_text_overlay.get())
        else:
            static_active = (hasattr(self, "_var_text_overlay")
                             and self._var_text_overlay.get()
                             and hasattr(self, "_var_text_content")
                             and self._var_text_content.get().strip())
            dyn_active = (hasattr(self, "_var_dyn_text_overlay")
                          and self._var_dyn_text_overlay.get())
        if static_active:
            self._draw_text_on_preview(img, dynamic=False)
        if dyn_active:
            self._draw_text_on_preview(img, dynamic=True)

        ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)

        dlg = ctk.CTkToplevel(self)
        dlg.title("Preview")
        dlg.configure(fg_color="#000000")
        dlg.resizable(False, False)
        dlg.grab_set()

        lbl = ctk.CTkLabel(dlg, image=ctk_img, text="")
        lbl.image = ctk_img  # avoid GC
        lbl.pack()

        hint = ctk.CTkLabel(
            dlg, text="Doble clic o Esc para cerrar",
            text_color="#888888", font=ctk.CTkFont(size=11),
        )
        hint.pack(pady=(0, 6))

        def _close(_e=None):
            dlg.grab_release()
            dlg.destroy()

        dlg.bind("<Escape>", _close)
        lbl.bind("<Double-Button-1>", _close)

        _center_window_on_screen(dlg)

    def _update_preview_overlay(self) -> None:
        """Re-renderiza el preview con overlay de texto si está activo."""
        # Usar siempre la ruta del modo activo, no la compartida
        mode = getattr(self, "_current_mode", "Audio \u2192 Video")
        if mode == "Slideshow":
            path = getattr(self, "_sl_preview_path", "")
        elif mode == "Shorts":
            path = getattr(self, "_sho_preview_path", "")
        else:
            path = getattr(self, "_atv_preview_path", "")
        if not path:
            return
        try:
            img = Image.open(path)
            is_shorts = getattr(self, "_current_mode", "") == "Shorts"
            if is_shorts:
                img = self._crop_img_to_9_16(img, target_w=203, target_h=360)
            else:
                img = self._crop_img_to_16_9(img)  # preview horizontal 16:9

            # Dibujar overlays de texto (estático y dinámico)
            is_slideshow = mode == "Slideshow"
            if is_shorts:
                static_active = (hasattr(self, "_var_sho_text_overlay")
                                 and self._var_sho_text_overlay.get()
                                 and hasattr(self, "_var_sho_text_content")
                                 and self._var_sho_text_content.get().strip())
                dyn_active = (hasattr(self, "_var_sho_dyn_text_overlay")
                              and self._var_sho_dyn_text_overlay.get())
            elif is_slideshow:
                static_active = (hasattr(self, "_var_sl_text_overlay")
                                 and self._var_sl_text_overlay.get()
                                 and hasattr(self, "_var_sl_text_content")
                                 and self._var_sl_text_content.get().strip())
                dyn_active = (hasattr(self, "_var_sl_dyn_text_overlay")
                              and self._var_sl_dyn_text_overlay.get())
            else:
                static_active = (hasattr(self, "_var_text_overlay")
                                 and self._var_text_overlay.get()
                                 and hasattr(self, "_var_text_content")
                                 and self._var_text_content.get().strip())
                dyn_active = (hasattr(self, "_var_dyn_text_overlay")
                              and self._var_dyn_text_overlay.get())
            if static_active:
                self._draw_text_on_preview(img, dynamic=False)
            if dyn_active:
                self._draw_text_on_preview(img, dynamic=True)

            display_size = img.size
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=display_size)
            self._lbl_preview.configure(image=ctk_img, text="")
            self._lbl_preview.image = ctk_img  # evitar GC
        except Exception as exc:
            self._lbl_preview.configure(image=None, text=f"No se pudo cargar: {exc}")

    def _play_notify_sound(self) -> None:
        """Reproduce NotifySound.mp3 en segundo plano usando Windows MCI (sin dependencias extras)."""
        import threading, ctypes
        from pathlib import Path
        sound_path = str(_BUNDLE_DIR / "NotifySound.mp3").replace("/", "\\")
        if not Path(sound_path).is_file():
            return
        def _play() -> None:
            try:
                winmm = ctypes.windll.winmm
                alias = "atv_notify"
                winmm.mciSendStringW(f'open "{sound_path}" type mpegvideo alias {alias}', None, 0, None)
                winmm.mciSendStringW(f'play {alias} wait', None, 0, None)
                winmm.mciSendStringW(f'close {alias}', None, 0, None)
            except Exception:
                pass
        threading.Thread(target=_play, daemon=True).start()

    def _draw_text_on_preview(self, img: Image.Image, dynamic: bool = False) -> None:
        """Dibuja el texto overlay sobre la imagen de preview."""
        draw = ImageDraw.Draw(img)
        mode = getattr(self, "_current_mode", "Audio \u2192 Video")
        is_shorts = mode == "Shorts"
        is_slideshow = mode == "Slideshow"

        if dynamic:
            if is_shorts:
                text_raw   = self._var_sho_dyn_text_content.get().strip() if hasattr(self, "_var_sho_dyn_text_content") else ""
                dyn_mode   = self._var_sho_dyn_text_mode.get() if hasattr(self, "_var_sho_dyn_text_mode") else "Texto fijo"
                prefix     = self._var_sho_naming_prefix.get() if hasattr(self, "_var_sho_naming_prefix") else ""
                font_size  = self._var_sho_dyn_text_font_size.get() if hasattr(self, "_var_sho_dyn_text_font_size") else 36
                font_name  = self._var_sho_dyn_text_font.get() if hasattr(self, "_var_sho_dyn_text_font") else "Arial"
                margin_val = self._var_sho_dyn_text_margin.get() if hasattr(self, "_var_sho_dyn_text_margin") else 40
                pos        = self._var_sho_dyn_text_position.get() if hasattr(self, "_var_sho_dyn_text_position") else "Bottom"
                color_name = self._var_sho_dyn_text_color.get() if hasattr(self, "_var_sho_dyn_text_color") else "Blanco"
                # Canvas directo 203×360 ? misma relación proporcional que el export 1080×1920
                ref_w, ref_h_margin = 1080.0, 1920.0
            elif is_slideshow:
                text_raw   = self._var_sl_dyn_text_content.get().strip() if hasattr(self, "_var_sl_dyn_text_content") else ""
                dyn_mode   = self._var_sl_dyn_text_mode.get() if hasattr(self, "_var_sl_dyn_text_mode") else "Texto fijo"
                prefix     = ""
                font_size  = self._var_sl_dyn_text_font_size.get() if hasattr(self, "_var_sl_dyn_text_font_size") else 36
                font_name  = self._var_sl_dyn_text_font.get() if hasattr(self, "_var_sl_dyn_text_font") else "Arial"
                margin_val = self._var_sl_dyn_text_margin.get() if hasattr(self, "_var_sl_dyn_text_margin") else 40
                pos        = self._var_sl_dyn_text_position.get() if hasattr(self, "_var_sl_dyn_text_position") else "Bottom"
                color_name = self._var_sl_dyn_text_color.get() if hasattr(self, "_var_sl_dyn_text_color") else "Blanco"
                ref_w, ref_h_margin = 1920.0, 1080.0
            else:
                text_raw   = self._var_dyn_text_content.get().strip() if hasattr(self, "_var_dyn_text_content") else ""
                dyn_mode   = self._var_dyn_text_mode.get() if hasattr(self, "_var_dyn_text_mode") else "Texto fijo"
                nm_mode    = self._var_naming_mode.get() if hasattr(self, "_var_naming_mode") else "Default"
                prefix     = (self._var_naming_name.get() if nm_mode == "Nombre"
                              else self._var_naming_prefix.get()) if hasattr(self, "_var_naming_prefix") else ""
                font_size  = self._var_dyn_text_font_size.get() if hasattr(self, "_var_dyn_text_font_size") else 36
                font_name  = self._var_dyn_text_font.get() if hasattr(self, "_var_dyn_text_font") else "Arial"
                margin_val = self._var_dyn_text_margin.get() if hasattr(self, "_var_dyn_text_margin") else 40
                pos        = self._var_dyn_text_position.get() if hasattr(self, "_var_dyn_text_position") else "Bottom"
                color_name = self._var_dyn_text_color.get() if hasattr(self, "_var_dyn_text_color") else "Blanco"
                ref_w, ref_h_margin = 1920.0, 1080.0

            if dyn_mode == "Texto fijo":
                text = text_raw
            elif dyn_mode == "Nombre de canci\u00f3n":
                text = "\u266a Nombre de canci\u00f3n"
            else:  # Prefijo + Nombre de canción
                text = f"{prefix} \u266a Nombre" if prefix else "\u266a Prefijo + Nombre"
        else:
            if is_shorts:
                text       = self._var_sho_text_content.get().strip()
                font_size  = self._var_sho_text_font_size.get()
                font_name  = self._var_sho_text_font.get()
                margin_val = self._var_sho_text_margin.get()
                pos        = self._var_sho_text_position.get()
                color_name = self._var_sho_text_color.get() if hasattr(self, "_var_sho_text_color") else "Blanco"
                # Canvas directo 203×360 ? misma relación proporcional que el export 1080×1920
                ref_w, ref_h_margin = 1080.0, 1920.0
            elif is_slideshow:
                text       = self._var_sl_text_content.get().strip() if hasattr(self, "_var_sl_text_content") else ""
                font_size  = self._var_sl_text_font_size.get() if hasattr(self, "_var_sl_text_font_size") else 36
                font_name  = self._var_sl_text_font.get() if hasattr(self, "_var_sl_text_font") else "Arial"
                margin_val = self._var_sl_text_margin.get() if hasattr(self, "_var_sl_text_margin") else 40
                pos        = self._var_sl_text_position.get() if hasattr(self, "_var_sl_text_position") else "Bottom"
                color_name = self._var_sl_text_color.get() if hasattr(self, "_var_sl_text_color") else "Blanco"
                ref_w, ref_h_margin = 1920.0, 1080.0
            else:
                text       = self._var_text_content.get().strip()
                font_size  = self._var_text_font_size.get()
                font_name  = self._var_text_font.get()
                margin_val = self._var_text_margin.get()
                pos        = self._var_text_position.get()
                color_name = self._var_text_color.get() if hasattr(self, "_var_text_color") else "Blanco"
                ref_w, ref_h_margin = 1920.0, 1080.0

        if not text:
            return

        w, h = img.size
        scale   = w / ref_w           # escala de fuente basada en ancho de referencia
        scale_h = h / ref_h_margin    # escala de margen basada en alto de referencia
        fs = max(8, int(font_size * scale))
        font = None
        for ext in (".ttf", ".otf"):
            fp = _BUNDLE_DIR / "fonts" / f"{font_name}{ext}"
            if fp.exists():
                try:
                    font = ImageFont.truetype(str(fp), fs)
                except Exception:
                    pass
                break
        if font is None:
            try:
                font = ImageFont.truetype("arial.ttf", fs)
            except Exception:
                font = ImageFont.load_default()

        # Medir texto
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

        # Posición X centrada
        x = (w - tw) // 2

        # Posición Y según configuración
        margin = int(margin_val * scale_h)
        if pos == "Top":
            y = margin
        elif pos == "Middle":
            y = (h - th) // 2
        else:  # Bottom
            y = h - th - margin

        # Color del texto
        _hex_map = {
            "Blanco": "#FFFFFF", "Gris claro": "#D0D0D0",
            "Gris": "#808080", "Gris oscuro": "#404040", "Negro": "#000000",
        }
        fill = _hex_map.get(color_name, "#FFFFFF")

        # Sombra
        sc = "#FFFFFF" if color_name in ("Negro", "Gris oscuro") else "#000000"
        sh = max(1, int(2 * scale))
        draw.text((x + sh, y + sh), text, font=font, fill=sc + "B3")  # sombra 70%
        draw.text((x, y), text, font=font, fill=fill)

    # ------------------------------------------------------------------
    # ACCIONES PRINCIPALES
    # ------------------------------------------------------------------

    def _on_generate(self) -> None:
        if not self._validate_inputs():
            return

        self._collect_settings()
        self._set_processing_state(True)
        self._clear_log()

        # Capture custom names that will be consumed in this run (for used-tracking)
        naming_mode = self._var_naming_mode.get()
        if naming_mode in ("Lista personalizada", "Prefijo + Lista personalizada",
                           "Custom List", "Prefix + Custom List"):
            try:
                n_audios = len(get_audio_files(self._var_audio_folder.get()))
                raw_names = [l.strip() for l in self._txt_naming_list.get("1.0", "end").splitlines() if l.strip()]
                _p = NamesListDialog._USED_PREFIX
                clean = [(n[len(_p):] if n.startswith(_p) else n) for n in raw_names]
                self._last_run_names = clean[:n_audios]
            except Exception:
                self._last_run_names = []
        else:
            self._last_run_names = []

        # Build per-audio image assignment if multi-image mode is active
        image_path = self._var_image.get()
        image_assignment = None
        if self._var_multi_image.get():
            audio_files = get_audio_files(self._var_audio_folder.get())
            img_files = get_image_files(self._var_images_folder.get())
            assignment = getattr(self, "_image_assignment", {})
            if not assignment:
                assignment = {
                    a.name: img_files[i % len(img_files)]
                    for i, a in enumerate(audio_files)
                }
            image_assignment = assignment
            image_path = str(img_files[0]) if img_files else ""

        runner = Runner(
            settings=self.settings.all(),
            on_log=self._queue_log,
            on_progress=self._on_progress_update,
            on_job_done=self._on_job_done,
            on_finished=self._on_finished,
        )
        self._runner = runner
        runner.start(
            audio_folder=self._var_audio_folder.get(),
            image_path=image_path,
            output_folder=self._var_output.get(),
            image_assignment=image_assignment,
        )

    def _on_cancel(self) -> None:
        if self._runner:
            self._runner.cancel()
        if self._slideshow_runner:
            self._slideshow_runner.cancel()
        if self._shorts_runner:
            self._shorts_runner.cancel()
        self._btn_cancel.configure(state="disabled")

    def _on_preview(self) -> None:
        # Resolve image path: single or first from folder
        preview_image = self._var_image.get()
        if self._var_multi_image.get():
            imgs_folder = self._var_images_folder.get()
            if imgs_folder and Path(imgs_folder).is_dir():
                imgs = get_image_files(imgs_folder)
                preview_image = str(imgs[0]) if imgs else ""

        if not preview_image or not self._var_audio_folder.get():
            messagebox.showwarning(
                "Preview",
                "Selecciona una carpeta de audios y una imagen de fondo primero.",
            )
            return

        from core.utils import get_audio_files
        files = get_audio_files(self._var_audio_folder.get())
        if not files:
            messagebox.showwarning("Preview", "No hay archivos de audio en la carpeta.")
            return

        output = Path(self._var_output.get() or ".") / "_preview.mp4"
        self._collect_settings()
        self._log(f"?? Generando preview de 10s ? {output}")

        from core.ffmpeg_builder import FFmpegBuilder
        from core.utils import get_audio_duration

        def _run() -> None:
            try:
                dur = get_audio_duration(files[0])
                builder = FFmpegBuilder(self.settings.all())
                cmd = builder.build_preview_command(
                    audio_path=files[0],
                    image_path=preview_image,
                    output_path=output,
                    duration=dur,
                )
                import subprocess, os
                _si = None
                if os.name == "nt":
                    _si = subprocess.STARTUPINFO()
                    _si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                try:
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120, startupinfo=_si)
                finally:
                    builder.cleanup()
                if r.returncode == 0:
                    self._queue_log(f"? Preview guardado: {output}")
                else:
                    self._queue_log(f"? Preview falló:\n{r.stderr[-300:]}")
            except Exception as exc:
                self._queue_log(f"? Error en preview: {exc}")

        threading.Thread(target=_run, daemon=True).start()

    def _on_test_ffmpeg(self) -> None:
        output = Path(self._var_output.get() or ".") / "_ffmpeg_test.mp4"
        self._log(f"?? Probando FFmpeg ? {output}")

        runner = Runner(
            settings={},
            on_log=self._queue_log,
            on_progress=lambda *_: None,
            on_job_done=lambda *_: None,
            on_finished=lambda *_: None,
        )

        def _run() -> None:
            ok, msg = runner.test_ffmpeg(output)
            self._queue_log(msg)

        threading.Thread(target=_run, daemon=True).start()

    # -- Abrir carpeta de salida --------------------------------------

    def _get_active_output_folder(self) -> str:
        """Return the output folder path for the active mode (may be empty)."""
        mode = getattr(self, "_current_mode", "Audio \u2192 Video")
        if mode == "Slideshow":
            return self._var_sl_output_folder.get() if hasattr(self, "_var_sl_output_folder") else ""
        if mode == "Shorts":
            return self._var_sho_output_folder.get() if hasattr(self, "_var_sho_output_folder") else ""
        if mode == "YouTube Publisher":
            return ""
        return self._var_output.get() if hasattr(self, "_var_output") else ""

    def _update_open_folder_btn(self, *_args: object) -> None:
        """Enable/disable the open-folder button based on the active output path."""
        if not hasattr(self, "_btn_open_folder"):
            return
        folder = self._get_active_output_folder()
        state = "normal" if folder.strip() else "disabled"
        self._btn_open_folder.configure(state=state)

    def _on_open_output_folder(self) -> None:
        """Open the active mode's output folder in the system file explorer."""
        folder = self._get_active_output_folder()
        if not folder or not folder.strip():
            return
        p = Path(folder)
        if not p.is_dir():
            # Create folder if needed so the explorer can open it
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError:
                return
        os.startfile(str(p))

    # ------------------------------------------------------------------
    # CALLBACKS DEL RUNNER (llamados desde hilo secundario)
    # ------------------------------------------------------------------

    def _on_progress_update(self, done: int, total: int, current_file: str) -> None:
        """Enviado desde el hilo de procesamiento; usamos after() para thread-safety."""
        self.after(0, self._update_progress_ui, done, total, current_file)

    def _update_progress_ui(self, done: int, total: int, current_file: str) -> None:
        if total > 0:
            self._progress_global.set(done / total)
            self._lbl_progress_global.configure(
                text=f"Global: {done}/{total} archivos"
            )
        if current_file:
            self._lbl_progress_file.configure(text=f"Procesando: {current_file}")
            self._progress_file.start()
        else:
            self._progress_file.stop()
            self._progress_file.set(0)
            self._lbl_progress_file.configure(text="")

    def _on_job_done(self, result: JobResult) -> None:
        pass  # El log ya se emite desde el runner

    def _on_finished(self, results: list[JobResult]) -> None:
        self.after(0, self._on_finished_ui, results)

    def _on_finished_ui(self, results: list[JobResult]) -> None:
        self._set_processing_state(False)
        if self._last_run_names:
            self._used_names.update(self._last_run_names)
            self._last_run_names = []
        self._play_notify_sound()

    # ------------------------------------------------------------------
    # LOGS (thread-safe via cola)
    # ------------------------------------------------------------------

    def _queue_log(self, msg: str) -> None:
        """Llamado desde cualquier hilo; encola el mensaje."""
        with self._log_lock:
            self._log_queue.append(msg)

    def _flush_log_queue(self) -> None:
        """Procesado regularmente en el hilo principal de Tkinter."""
        with self._log_lock:
            messages = self._log_queue[:]
            self._log_queue.clear()

        for msg in messages:
            self._log(msg)

        self.after(100, self._flush_log_queue)

    def _log(self, msg: str) -> None:
        """Escribe un mensaje en el área de logs (debe llamarse desde el hilo principal)."""
        self._log_text.configure(state="normal")
        self._log_text.insert("end", msg + "\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # VALIDACIONES
    # ------------------------------------------------------------------

    def _run_validation(self) -> None:
        if self._validation_in_progress:
            return

        self._validation_in_progress = True
        self._startup_cancel_requested.clear()
        self._startup_last_status_message = ""
        self._lbl_status.configure(text="Verificando entorno...", text_color=C_WARN)
        if hasattr(self, "_lbl_status_dot"):
            self._lbl_status_dot.configure(text_color=C_WARN)
        self._open_startup_dependency_dialog()
        threading.Thread(target=self._run_validation_worker, daemon=True).start()

    def _open_startup_dependency_dialog(self) -> None:
        if self._startup_dependency_dialog and self._startup_dependency_dialog.winfo_exists():
            self._startup_dependency_dialog.close()
        self._startup_dependency_dialog = StartupDependencyDialog(self)
        self._startup_dependency_dialog.set_cancel_handler(self._on_startup_dependency_cancel_request)
        self._startup_dependency_dialog.set_cancel_enabled(True)

    def _on_startup_dependency_cancel_request(self) -> None:
        if self._startup_cancel_requested.is_set():
            return

        confirm = ThemedConfirmDialog(
            self,
            "Cancelar preparacion",
            "Estas seguro de cancelar?",
            "Se detendra la instalacion/descarga de Ollama en curso.\n"
            "Prompt Lab puede quedar no disponible hasta completar dependencias.",
        ).run_modal()
        if not confirm:
            return

        self._startup_cancel_requested.set()
        self._set_startup_dependency_status(
            "Cancelando...",
            "Deteniendo tareas de instalacion en curso.",
            None,
        )
        dialog = self._startup_dependency_dialog
        if dialog and dialog.winfo_exists():
            dialog.set_cancel_enabled(False)

    def _set_startup_dependency_status(self, title: str, detail: str, progress: float | None = None) -> None:
        dialog = self._startup_dependency_dialog
        if dialog and dialog.winfo_exists():
            dialog.set_status(title, detail, progress)

    def _close_startup_dependency_dialog(self) -> None:
        dialog = self._startup_dependency_dialog
        self._startup_dependency_dialog = None
        if dialog and dialog.winfo_exists():
            dialog.close()

    def _on_ffmpeg_progress(self, message: str, progress: float | None = None) -> None:
        if message != self._startup_last_status_message:
            self._startup_last_status_message = message
            self.after(0, self._log, message)
        self.after(
            0,
            self._set_startup_dependency_status,
            "Instalando dependencias...",
            message,
            progress,
        )

    def _on_ollama_progress(self, message: str, progress: float | None = None) -> None:
        if message != self._startup_last_status_message:
            self._startup_last_status_message = message
            self.after(0, self._log, message)
        self.after(
            0,
            self._set_startup_dependency_status,
            "Preparando Prompt Lab IA...",
            message,
            progress,
        )

    def _ask_yes_no_main_thread(self, title: str, headline: str, detail: str) -> bool:
        result = {"value": False}
        done = threading.Event()

        def _ask() -> None:
            try:
                dlg = ThemedConfirmDialog(self, title, headline, detail)
                result["value"] = dlg.run_modal()
            except Exception:
                result["value"] = False
            finally:
                done.set()

        self.after(0, _ask)
        done.wait()
        return bool(result["value"])

    def _ask_model_selection_main_thread(self, missing_models: list[str]) -> list[str]:
        result = {"value": []}
        done = threading.Event()

        def _ask() -> None:
            try:
                dlg = ModelSelectionDialog(
                    self,
                    title="Prompt Lab IA",
                    missing_models=missing_models,
                    estimate_cb=estimate_models_size_gb,
                )
                result["value"] = dlg.run_modal()
            except Exception:
                result["value"] = []
            finally:
                done.set()

        self.after(0, _ask)
        done.wait()
        out = result.get("value")
        if not isinstance(out, list):
            return []
        return [str(v).strip() for v in out if str(v).strip()]

    def _collect_required_ollama_models(self) -> list[str]:
        models: list[str] = []

        if hasattr(self, "_var_pl_model_quality"):
            quality = self._var_pl_model_quality.get().strip()
            if quality and quality not in models:
                models.append(quality)
        if hasattr(self, "_var_pl_model_fast"):
            fast = self._var_pl_model_fast.get().strip()
            if fast and fast not in models:
                models.append(fast)

        if not models:
            for fallback in (
                str(self.settings.get("pl_model_quality", "")).strip(),
                str(self.settings.get("pl_model_fast", "")).strip(),
            ):
                if fallback and fallback not in models:
                    models.append(fallback)

        return models

    def _ensure_ollama_dependencies(self) -> None:
        if self._startup_cancel_requested.is_set():
            self.after(0, self._log, "Prompt Lab IA: preparacion cancelada por el usuario.")
            return

        base_url = "http://127.0.0.1:11434"
        if hasattr(self, "_var_pl_backend_url"):
            base_url = self._var_pl_backend_url.get().strip() or base_url
        else:
            base_url = str(self.settings.get("pl_backend_url", base_url) or base_url).strip()

        required_models = self._collect_required_ollama_models()
        if not required_models:
            self.after(0, self._log, "Prompt Lab IA: no hay modelos configurados para validar en arranque.")
            return

        status = collect_ollama_status(base_url, required_models)

        if not status.supported_os:
            self.after(0, self._log, "Prompt Lab IA: Ollama no es compatible con este sistema operativo.")
            return

        if not status.installed:
            if self._startup_cancel_requested.is_set():
                self.after(0, self._log, "Prompt Lab IA: preparacion cancelada por el usuario.")
                return

            wants_install = self._ask_yes_no_main_thread(
                "Prompt Lab IA",
                "No se detecto Ollama en este equipo.",
                "Ollama permite usar la generacion IA local de Prompt Lab.\n"
                "Si no lo instalas, la seccion Prompt Lab no podra generar respuestas.\n\n"
                "Quieres instalarlo automaticamente ahora?\n"
                "Peso estimado: 300 MB.",
            )
            if not wants_install:
                self.after(0, self._log, "Prompt Lab IA: instalacion de Ollama omitida por el usuario.")
                return

            ok, detail = install_ollama_windows(
                on_progress=self._on_ollama_progress,
                cancel_event=self._startup_cancel_requested,
            )
            if not ok:
                if "cancelada" in detail.lower():
                    self.after(0, self._log, "Prompt Lab IA: instalacion cancelada por el usuario.")
                else:
                    self.after(0, self._log, f"Prompt Lab IA: no se pudo instalar Ollama. {detail}")
                return

            # Give the OS a short window to refresh PATH/process registrations.
            time.sleep(1.0)

        status = collect_ollama_status(base_url, required_models)
        if not status.running:
            if self._startup_cancel_requested.is_set():
                self.after(0, self._log, "Prompt Lab IA: preparacion cancelada por el usuario.")
                return

            wants_start = self._ask_yes_no_main_thread(
                "Prompt Lab IA",
                "Ollama esta instalado, pero su servicio local no responde.",
                "Sin el servicio activo, Prompt Lab no podra consultar modelos.\n\n"
                "Quieres iniciarlo automaticamente ahora?",
            )
            if wants_start:
                started = try_start_ollama_server(base_url, on_progress=self._on_ollama_progress)
                if not started:
                    self.after(0, self._log, "Prompt Lab IA: no se pudo iniciar el servicio local de Ollama.")
                    return
            else:
                self.after(0, self._log, "Prompt Lab IA: inicio del servicio Ollama omitido por el usuario.")
                return

        status = collect_ollama_status(base_url, required_models)
        if not status.missing_models:
            self.after(0, self._log, "Prompt Lab IA: modelos requeridos ya disponibles.")
            return

        if self._startup_cancel_requested.is_set():
            self.after(0, self._log, "Prompt Lab IA: preparacion cancelada por el usuario.")
            return

        selected_models = self._ask_model_selection_main_thread(status.missing_models)
        if not selected_models:
            self.after(0, self._log, "Prompt Lab IA: descarga de modelos omitida por el usuario.")
            return

        ok, detail = pull_ollama_models(
            selected_models,
            on_progress=self._on_ollama_progress,
            cancel_event=self._startup_cancel_requested,
        )
        if ok:
            self.after(0, self._log, "Prompt Lab IA: modelos seleccionados descargados correctamente.")

            # Ajustar fallback ligero si el usuario eligio solo el modelo alternativo.
            lowered = {m.lower() for m in selected_models}
            if "llama3.2:1b" in lowered and "llama3.2:3b" not in lowered:
                if hasattr(self, "_var_pl_model_fast"):
                    self._var_pl_model_fast.set("llama3.2:1b")
                self.settings.set("pl_model_fast", "llama3.2:1b")
                try:
                    self.settings.save()
                except Exception:
                    pass
                self.after(
                    0,
                    self._log,
                    "Prompt Lab IA: modo rapido ajustado a llama3.2:1b (alternativa ligera).",
                )
        else:
            if "cancelada" in detail.lower():
                self.after(0, self._log, "Prompt Lab IA: descarga de modelos cancelada por el usuario.")
            else:
                self.after(0, self._log, f"Prompt Lab IA: error descargando modelos. {detail}")

    def _run_validation_worker(self) -> None:
        self.after(
            0,
            self._set_startup_dependency_status,
            "Verificando dependencias...",
            "Comprobando FFmpeg, Ollama y herramientas del sistema.",
            None,
        )

        ffmpeg_dir = ensure_ffmpeg(on_progress=self._on_ffmpeg_progress)
        if ffmpeg_dir is None:
            self.after(0, self._log, "? No se pudo localizar ni instalar FFmpeg.")

        try:
            self._ensure_ollama_dependencies()
        except Exception as exc:
            self.after(0, self._log, f"Prompt Lab IA: error en preparacion de Ollama: {exc}")

        result = validate_environment()
        self.after(0, self._apply_validation_result, result)

    def _apply_validation_result(self, result: ValidationResult) -> None:
        for msg in result.messages:
            self._log(msg)

        if result.ok:
            self._set_startup_dependency_status(
                "Entorno listo",
                "Todo esta preparado. La aplicacion ya puede usarse.",
                100.0,
            )
            self._lbl_status.configure(text="Entorno OK", text_color=C_SUCCESS)
            if hasattr(self, "_lbl_status_dot"):
                self._lbl_status_dot.configure(text_color=C_SUCCESS)
            self._btn_generate.configure(state="normal")
            self.after(350, self._close_startup_dependency_dialog)
        else:
            self._set_startup_dependency_status(
                "Faltan dependencias",
                "No fue posible completar la preparacion inicial del entorno.",
                100.0,
            )
            self._lbl_status.configure(text="Dependencias faltantes", text_color=C_ERROR)
            if hasattr(self, "_lbl_status_dot"):
                self._lbl_status_dot.configure(text_color=C_ERROR)
            self._btn_generate.configure(state="disabled")
            self._close_startup_dependency_dialog()
            messagebox.showerror(
                "Dependencias faltantes",
                "Se encontraron problemas con las dependencias del sistema.\n"
                "Revisa el area de logs para mas detalles.",
            )

        self._validation_in_progress = False

    def _validate_inputs(self) -> bool:
        errors: list[str] = []

        audio_folder = self._var_audio_folder.get()
        if not audio_folder or not Path(audio_folder).is_dir():
            errors.append("• Carpeta de audios no válida.")

        if not self._var_multi_image.get():
            image_path = self._var_image.get()
            if not image_path or not Path(image_path).is_file():
                errors.append("• Imagen de fondo no válida.")
        else:
            images_folder = self._var_images_folder.get()
            if not images_folder or not Path(images_folder).is_dir():
                errors.append("• Carpeta de imágenes no válida.")
            else:
                imgs = get_image_files(images_folder)
                if not imgs:
                    errors.append("• La carpeta de imágenes no contiene imágenes válidas.")

        output_folder = self._var_output.get()
        if not output_folder:
            errors.append("• Selecciona una carpeta de salida.")

        if self._var_overlay.get():
            overlay_path = self._var_overlay_path.get()
            if not overlay_path or not Path(overlay_path).is_file():
                errors.append("• Video de overlay no válido (o no seleccionado).")

        if self._var_text_overlay.get():
            if not self._var_text_content.get().strip():
                errors.append("• El texto overlay está activado pero el texto está vacío.")

        # -- Validación de nombres de salida --
        naming_mode = self._var_naming_mode.get()
        if naming_mode in ("Custom List", "Prefix + Custom List",
                           "Lista personalizada", "Prefijo + Lista personalizada"):
            names_raw = self._txt_naming_list.get("1.0", "end").strip()
            if not names_raw:
                errors.append("• La lista de nombres personalizados está vacía.")
            else:
                custom_names = [n.strip() for n in names_raw.splitlines() if n.strip()]
                # Validar contra número de audios si ya hay carpeta elegida
                af = self._var_audio_folder.get()
                if af and Path(af).is_dir():
                    try:
                        audio_count = len(get_audio_files(af))
                        if audio_count > 0 and len(custom_names) < audio_count:
                            errors.append(
                                f"• La lista tiene {len(custom_names)} nombre(s) "
                                f"pero hay {audio_count} audio(s). "
                                f"Se necesitan al menos {audio_count} nombres."
                            )
                    except Exception:
                        pass

        if errors:
            messagebox.showerror("Validación", "\n".join(errors))
            return False
        return True

    # ------------------------------------------------------------------
    # SINCRONIZACIÓN SETTINGS ? UI
    # ------------------------------------------------------------------

    def _collect_settings(self) -> None:
        """Lee los valores de la UI y los escribe en SettingsManager."""
        names_raw = self._txt_naming_list.get("1.0", "end")
        custom_names = [n.strip() for n in names_raw.splitlines() if n.strip()]

        self.settings.update({
            "audio_folder": self._var_audio_folder.get(),
            "background_image": self._var_image.get(),
            "output_folder": self._var_output.get(),
            "multi_image": self._var_multi_image.get(),
            "images_folder": self._var_images_folder.get(),
            "fade_in": round(self._var_fade_in.get(), 2),
            "fade_out": round(self._var_fade_out.get(), 2),
            "crf": int(self._var_crf.get()),
            "resolution": self._var_resolution.get(),
            "enable_breath": self._var_breath.get(),
            "breath_intensity": round(self._var_breath_intensity.get(), 3),
            "breath_speed": round(self._var_breath_speed.get(), 1),
            "enable_light_zoom": self._var_light_zoom.get(),
            "light_zoom_max": round(self._var_light_zoom_max.get(), 3),
            "light_zoom_speed": round(self._var_light_zoom_speed.get(), 1),
            "enable_vignette": self._var_vignette.get(),
            "vignette_intensity": round(self._var_vignette_intensity.get(), 1),
            "enable_color_shift": self._var_color_shift.get(),
            "color_shift_amount": round(self._var_color_shift_amount.get(), 0),
            "color_shift_speed": round(self._var_color_shift_speed.get(), 1),
            "enable_glitch": self._var_glitch.get(),
            "glitch_intensity": int(self._var_glitch_intensity.get()),
            "glitch_speed": int(self._var_glitch_speed.get()),
            "glitch_pulse": int(self._var_glitch_pulse.get()),
            "enable_overlay": self._var_overlay.get(),
            "overlay_path": self._var_overlay_path.get(),
            "overlay_opacity": round(self._var_overlay_opacity.get(), 2),
            "normalize_audio": self._var_normalize.get(),
            # Naming
            "naming_mode": self._var_naming_mode.get(),
            "naming_name": self._var_naming_name.get() if hasattr(self, "_var_naming_name") else "",
            "naming_prefix": self._var_naming_prefix.get(),
            "naming_custom_list": custom_names,
            "naming_auto_number": self._var_naming_autonumber.get(),
            # Performance
            "cpu_mode": self._var_cpu_mode.get(),
            "encode_preset": self._var_encode_preset.get(),
            "gpu_encoding": self._var_gpu_encoding.get(),
            # Text overlay (estático)
            "enable_text_overlay": self._var_text_overlay.get(),
            "text_content": self._var_text_content.get(),
            "text_position": self._var_text_position.get(),
            "text_margin": int(self._var_text_margin.get()),
            "text_font_size": int(self._var_text_font_size.get()),
            "text_font": self._var_text_font.get(),
            "text_color": self._var_text_color.get(),
            "text_glitch_intensity": int(self._var_text_glitch_intensity.get()),
            "text_glitch_speed": round(self._var_text_glitch_speed.get(), 1),
            # Text overlay (dinámico)
            "enable_dyn_text_overlay": self._var_dyn_text_overlay.get() if hasattr(self, "_var_dyn_text_overlay") else False,
            "dyn_text_mode":           self._var_dyn_text_mode.get() if hasattr(self, "_var_dyn_text_mode") else "Texto fijo",
            "dyn_text_content":        self._var_dyn_text_content.get() if hasattr(self, "_var_dyn_text_content") else "",
            "dyn_text_position":       self._var_dyn_text_position.get() if hasattr(self, "_var_dyn_text_position") else "Bottom",
            "dyn_text_margin":         int(self._var_dyn_text_margin.get()) if hasattr(self, "_var_dyn_text_margin") else 40,
            "dyn_text_font_size":      int(self._var_dyn_text_font_size.get()) if hasattr(self, "_var_dyn_text_font_size") else 36,
            "dyn_text_font":           self._var_dyn_text_font.get() if hasattr(self, "_var_dyn_text_font") else "Arial",
            "dyn_text_color":          self._var_dyn_text_color.get() if hasattr(self, "_var_dyn_text_color") else "Blanco",
            "dyn_text_glitch_intensity": int(self._var_dyn_text_glitch_intensity.get()) if hasattr(self, "_var_dyn_text_glitch_intensity") else 3,
            "dyn_text_glitch_speed":   round(self._var_dyn_text_glitch_speed.get(), 1) if hasattr(self, "_var_dyn_text_glitch_speed") else 4.0,
            # UI
            "theme": self._current_theme,
            "font_size": next(
                (k for k, v in _FONT_SIZE_SCALE.items() if abs(v - self._font_scale) < 0.01),
                "Medium",
            ),
            # YouTube Publisher (UI scaffold state)
            "yt_timezone": self._var_yt_timezone.get() if hasattr(self, "_var_yt_timezone") else "America/Los_Angeles",
            "yt_videos_per_day": int(self._var_yt_videos_per_day.get()) if hasattr(self, "_var_yt_videos_per_day") else 3,
            "yt_window_start": self._var_yt_window_start.get() if hasattr(self, "_var_yt_window_start") else "09:00",
            "yt_window_end": self._var_yt_window_end.get() if hasattr(self, "_var_yt_window_end") else "21:00",
            "yt_default_category": self._var_yt_default_category.get() if hasattr(self, "_var_yt_default_category") else "Music",
            "yt_default_made_for_kids": self._var_yt_default_made_for_kids.get() if hasattr(self, "_var_yt_default_made_for_kids") else False,
            # Prompt Lab
            "pl_workspace": self._var_pl_workspace.get() if hasattr(self, "_var_pl_workspace") else "General",
            "pl_category": self._var_pl_category.get() if hasattr(self, "_var_pl_category") else "General",
            "pl_skill": self._var_pl_skill.get() if hasattr(self, "_var_pl_skill") else "Skill General",
            "pl_model_mode": self._var_pl_model_mode.get() if hasattr(self, "_var_pl_model_mode") else "Calidad alta",
            "pl_prompt_text": self._txt_pl_prompt.get("1.0", "end").strip() if hasattr(self, "_txt_pl_prompt") else "",
            "pl_backend_url": self._var_pl_backend_url.get() if hasattr(self, "_var_pl_backend_url") else "http://127.0.0.1:11434",
            "pl_model_quality": self._var_pl_model_quality.get() if hasattr(self, "_var_pl_model_quality") else "llama3.1:8b",
            "pl_model_fast": self._var_pl_model_fast.get() if hasattr(self, "_var_pl_model_fast") else "llama3.2:3b",
            "pl_active_skills": list(self._pl_active_skills),
            "pl_template_insert_mode_by_category": dict(self._pl_template_insert_mode_by_category),
        })
        # Save slideshow settings if panel exists
        if hasattr(self, "_var_sl_images_folder"):
            self._collect_slideshow_settings()
        # Save Shorts settings if panel exists
        if hasattr(self, "_var_sho_audio"):
            self._collect_shorts_settings()

    def _load_settings_to_ui(self) -> None:
        """Carga la configuración guardada en los widgets de la UI."""
        s = self.settings.all()
        self._var_audio_folder.set(s.get("audio_folder", ""))
        self._var_image.set(s.get("background_image", ""))
        self._var_output.set(s.get("output_folder", ""))
        self._var_multi_image.set(s.get("multi_image", False))
        self._var_images_folder.set(s.get("images_folder", ""))
        self._image_assignment = {}
        self._toggle_multi_image()
        self._var_fade_in.set(s.get("fade_in", 2.0))
        self._var_fade_out.set(s.get("fade_out", 2.0))
        self._var_crf.set(s.get("crf", 18))
        self._var_resolution.set(s.get("resolution", "1080p"))
        self._var_breath.set(s.get("enable_breath", False))
        self._var_breath_intensity.set(s.get("breath_intensity", 0.04))
        self._var_breath_speed.set(s.get("breath_speed", 1.0))
        self._var_light_zoom.set(s.get("enable_light_zoom", False))
        self._var_light_zoom_max.set(s.get("light_zoom_max", 1.04))
        self._var_light_zoom_speed.set(s.get("light_zoom_speed", 0.5))
        self._var_vignette.set(s.get("enable_vignette", False))
        self._var_vignette_intensity.set(s.get("vignette_intensity", 0.4))
        self._var_color_shift.set(s.get("enable_color_shift", False))
        self._var_color_shift_amount.set(s.get("color_shift_amount", 15.0))
        self._var_color_shift_speed.set(s.get("color_shift_speed", 0.5))
        self._var_glitch.set(s.get("enable_glitch", False))
        self._var_glitch_intensity.set(s.get("glitch_intensity", 4))
        self._var_glitch_speed.set(s.get("glitch_speed", 90))
        self._var_glitch_pulse.set(s.get("glitch_pulse", 3))
        self._var_overlay.set(s.get("enable_overlay", False))
        self._var_overlay_path.set(s.get("overlay_path", ""))
        self._var_overlay_opacity.set(s.get("overlay_opacity", 0.5))
        self._var_normalize.set(s.get("normalize_audio", False))

        # Naming
        self._var_naming_mode.set(s.get("naming_mode", "Default"))
        if hasattr(self, "_var_naming_name"):
            self._var_naming_name.set(s.get("naming_name", ""))
        self._var_naming_prefix.set(s.get("naming_prefix", ""))
        custom_names: list[str] = s.get("naming_custom_list", [])
        self._txt_naming_list.delete("1.0", "end")
        if custom_names:
            self._txt_naming_list.insert("1.0", "\n".join(custom_names))
        self._refresh_names_count()
        self._var_naming_autonumber.set(s.get("naming_auto_number", True))
        self._on_naming_mode_change(self._var_naming_mode.get())

        # Performance
        self._var_cpu_mode.set(s.get("cpu_mode", "Medium"))
        self._var_encode_preset.set(s.get("encode_preset", "slow"))
        self._var_gpu_encoding.set(s.get("gpu_encoding", False))

        # Text overlay
        self._var_text_overlay.set(s.get("enable_text_overlay", False))
        self._var_text_content.set(s.get("text_content", ""))
        self._var_text_position.set(s.get("text_position", "Bottom"))
        self._var_text_margin.set(s.get("text_margin", 40))
        self._var_text_font_size.set(s.get("text_font_size", 36))
        self._var_text_font.set(s.get("text_font", "Arial"))
        self._var_text_color.set(s.get("text_color", "Blanco"))
        self._text_color_preview.configure(fg_color={
            "Blanco": "#FFFFFF", "Gris claro": "#D0D0D0",
            "Gris": "#808080", "Gris oscuro": "#404040", "Negro": "#000000",
        }.get(s.get("text_color", "Blanco"), "#FFFFFF"))
        self._var_text_glitch_intensity.set(s.get("text_glitch_intensity", 3))
        self._var_text_glitch_speed.set(s.get("text_glitch_speed", 4.0))
        self._toggle_text_overlay_widgets()
        # Dynamic text overlay (ATV)
        if hasattr(self, "_var_dyn_text_overlay"):
            self._var_dyn_text_overlay.set(s.get("enable_dyn_text_overlay", False))
            self._var_dyn_text_mode.set(s.get("dyn_text_mode", "Texto fijo"))
            self._var_dyn_text_content.set(s.get("dyn_text_content", ""))
            self._var_dyn_text_position.set(s.get("dyn_text_position", "Bottom"))
            self._var_dyn_text_margin.set(s.get("dyn_text_margin", 40))
            self._var_dyn_text_font_size.set(s.get("dyn_text_font_size", 36))
            self._var_dyn_text_font.set(s.get("dyn_text_font", "Arial"))
            self._var_dyn_text_color.set(s.get("dyn_text_color", "Blanco"))
            if hasattr(self, "_dyn_text_color_preview"):
                self._dyn_text_color_preview.configure(fg_color={
                    "Blanco": "#FFFFFF", "Gris claro": "#D0D0D0",
                    "Gris": "#808080", "Gris oscuro": "#404040", "Negro": "#000000",
                }.get(s.get("dyn_text_color", "Blanco"), "#FFFFFF"))
            self._var_dyn_text_glitch_intensity.set(s.get("dyn_text_glitch_intensity", 3))
            self._var_dyn_text_glitch_speed.set(s.get("dyn_text_glitch_speed", 4.0))
            self._on_dyn_text_mode_change()
            self._toggle_dyn_text_overlay_widgets()
        # theme/font_size se cargan en __init__ antes de construir la UI

        # Cargar preview: imagen única o primera imagen de la carpeta si modo multi
        if s.get("multi_image", False):
            imgs_folder = s.get("images_folder", "")
            if imgs_folder and Path(imgs_folder).is_dir():
                imgs = get_image_files(imgs_folder)
                if imgs:
                    self._load_preview(str(imgs[0]))
        else:
            img = s.get("background_image", "")
            if img and Path(img).is_file():
                self._load_preview(img)

        # Actualizar conteo de audios
        audio = s.get("audio_folder", "")
        if audio and Path(audio).is_dir():
            self._update_audio_count(audio)

        # Slideshow settings
        if hasattr(self, "_var_sl_images_folder"):
            self._var_sl_images_folder.set(s.get("sl_images_folder", ""))
            self._var_sl_audio_file.set(s.get("sl_audio_file", ""))
            if hasattr(self, "_var_sl_audio_mode"):
                self._var_sl_audio_mode.set(s.get("sl_audio_mode", "file"))
                self._var_sl_audio_folder.set(s.get("sl_audio_folder", ""))
                self._var_sl_crossfade.set(s.get("sl_crossfade", 2.0))
                self._sl_toggle_audio_mode()
                self._sl_update_audio_folder_count()
            # Restore audio-enabled state (infer from paths if key absent)
            audio_enabled = bool(s.get("sl_audio_enabled", False))
            if not audio_enabled:
                audio_enabled = bool(s.get("sl_audio_file") or s.get("sl_audio_folder"))
            self._var_sl_audio_enabled.set(audio_enabled)
            self._sl_toggle_audio()
            self._var_sl_output_folder.set(s.get("sl_output_folder", ""))
            self._var_sl_output_name.set(s.get("sl_output_name", "slideshow"))
            self._var_sl_duration.set(s.get("sl_duration", 5.0))
            self._var_sl_transition.set(s.get("sl_transition", "Crossfade"))
            self._var_sl_resolution.set(s.get("sl_resolution", "1080p"))
            self._var_sl_crf.set(s.get("sl_crf", 18))
            self._var_sl_cpu_mode.set(s.get("sl_cpu_mode", "Medium"))
            self._var_sl_encode_preset.set(s.get("sl_encode_preset", "slow"))
            self._var_sl_gpu_encoding.set(s.get("sl_gpu_encoding", False))
            if hasattr(self, "_var_sl_breath"):
                self._var_sl_breath.set(s.get("sl_enable_breath", False))
                self._var_sl_breath_intensity.set(s.get("sl_breath_intensity", 0.04))
                self._var_sl_breath_speed.set(s.get("sl_breath_speed", 1.0))
            if hasattr(self, "_var_sl_light_zoom"):
                self._var_sl_light_zoom.set(s.get("sl_enable_light_zoom", False))
                self._var_sl_light_zoom_max.set(s.get("sl_light_zoom_max", 1.04))
                self._var_sl_light_zoom_speed.set(s.get("sl_light_zoom_speed", 0.5))
            if hasattr(self, "_var_sl_vignette"):
                self._var_sl_vignette.set(s.get("sl_enable_vignette", False))
                self._var_sl_vignette_intensity.set(s.get("sl_vignette_intensity", 0.4))
            if hasattr(self, "_var_sl_color_shift"):
                self._var_sl_color_shift.set(s.get("sl_enable_color_shift", False))
                self._var_sl_color_shift_amount.set(s.get("sl_color_shift_amount", 15.0))
                self._var_sl_color_shift_speed.set(s.get("sl_color_shift_speed", 0.5))
            self._sl_update_count()
            # Static text overlay (Slideshow)
            if hasattr(self, "_var_sl_text_overlay"):
                self._var_sl_text_overlay.set(s.get("sl_enable_text_overlay", False))
                self._var_sl_text_content.set(s.get("sl_text_content", ""))
                self._var_sl_text_position.set(s.get("sl_text_position", "Bottom"))
                self._var_sl_text_margin.set(s.get("sl_text_margin", 40))
                self._var_sl_text_font_size.set(s.get("sl_text_font_size", 36))
                self._var_sl_text_font.set(s.get("sl_text_font", "Arial"))
                self._var_sl_text_color.set(s.get("sl_text_color", "Blanco"))
                if hasattr(self, "_sl_text_color_preview"):
                    self._sl_text_color_preview.configure(fg_color={
                        "Blanco": "#FFFFFF", "Gris claro": "#D0D0D0",
                        "Gris": "#808080", "Gris oscuro": "#404040", "Negro": "#000000",
                    }.get(s.get("sl_text_color", "Blanco"), "#FFFFFF"))
                self._var_sl_text_glitch_intensity.set(s.get("sl_text_glitch_intensity", 3))
                self._var_sl_text_glitch_speed.set(s.get("sl_text_glitch_speed", 4.0))
                self._sl_toggle_text_overlay_widgets()
            # Dynamic text overlay (Slideshow)
            if hasattr(self, "_var_sl_dyn_text_overlay"):
                self._var_sl_dyn_text_overlay.set(s.get("sl_enable_dyn_text_overlay", False))
                self._var_sl_dyn_text_mode.set(s.get("sl_dyn_text_mode", "Texto fijo"))
                self._var_sl_dyn_text_content.set(s.get("sl_dyn_text_content", ""))
                self._var_sl_dyn_text_position.set(s.get("sl_dyn_text_position", "Bottom"))
                self._var_sl_dyn_text_margin.set(s.get("sl_dyn_text_margin", 40))
                self._var_sl_dyn_text_font_size.set(s.get("sl_dyn_text_font_size", 36))
                self._var_sl_dyn_text_font.set(s.get("sl_dyn_text_font", "Arial"))
                self._var_sl_dyn_text_color.set(s.get("sl_dyn_text_color", "Blanco"))
                if hasattr(self, "_sl_dyn_text_color_preview"):
                    self._sl_dyn_text_color_preview.configure(fg_color={
                        "Blanco": "#FFFFFF", "Gris claro": "#D0D0D0",
                        "Gris": "#808080", "Gris oscuro": "#404040", "Negro": "#000000",
                    }.get(s.get("sl_dyn_text_color", "Blanco"), "#FFFFFF"))
                self._var_sl_dyn_text_glitch_intensity.set(s.get("sl_dyn_text_glitch_intensity", 3))
                self._var_sl_dyn_text_glitch_speed.set(s.get("sl_dyn_text_glitch_speed", 4.0))
                self._on_sl_dyn_text_mode_change()
                self._sl_toggle_dyn_text_overlay_widgets()

        # Shorts settings
        if hasattr(self, "_var_sho_audio"):
            self._var_sho_audio.set(s.get("sho_audio_file", ""))
            if hasattr(self, "_var_sho_image"):
                self._var_sho_image.set(s.get("sho_background_image", ""))
            if hasattr(self, "_var_sho_images_folder"):
                self._var_sho_images_folder.set(s.get("sho_images_folder", ""))
            if hasattr(self, "_var_sho_multi_image"):
                self._var_sho_multi_image.set(s.get("sho_multi_image", False))
                self._sho_toggle_multi_image()
            if hasattr(self, "_var_sho_output_folder"):
                self._var_sho_output_folder.set(s.get("sho_output_folder", ""))
            if hasattr(self, "_var_sho_duration"):
                self._var_sho_duration.set(s.get("sho_duration", 45))
            if hasattr(self, "_var_sho_quantity"):
                self._var_sho_quantity.set(s.get("sho_quantity", 3))
            if hasattr(self, "_var_sho_resolution"):
                self._var_sho_resolution.set(s.get("sho_resolution", "1080p"))
            if hasattr(self, "_var_sho_breath"):
                self._var_sho_breath.set(s.get("sho_enable_breath", False))
                self._var_sho_breath_intensity.set(s.get("sho_breath_intensity", 0.04))
                self._var_sho_breath_speed.set(s.get("sho_breath_speed", 1.0))
            if hasattr(self, "_var_sho_light_zoom"):
                self._var_sho_light_zoom.set(s.get("sho_enable_light_zoom", False))
                self._var_sho_light_zoom_max.set(s.get("sho_light_zoom_max", 1.04))
                self._var_sho_light_zoom_speed.set(s.get("sho_light_zoom_speed", 0.5))
            if hasattr(self, "_var_sho_vignette"):
                self._var_sho_vignette.set(s.get("sho_enable_vignette", False))
                self._var_sho_vignette_intensity.set(s.get("sho_vignette_intensity", 0.4))
            if hasattr(self, "_var_sho_color_shift"):
                self._var_sho_color_shift.set(s.get("sho_enable_color_shift", False))
                self._var_sho_color_shift_amount.set(s.get("sho_color_shift_amount", 15.0))
                self._var_sho_color_shift_speed.set(s.get("sho_color_shift_speed", 0.5))
            if hasattr(self, "_var_sho_glitch"):
                self._var_sho_glitch.set(s.get("sho_enable_glitch", False))
            if hasattr(self, "_var_sho_glitch_intensity"):
                self._var_sho_glitch_intensity.set(s.get("sho_glitch_intensity", 4))
            if hasattr(self, "_var_sho_glitch_speed_fx"):
                self._var_sho_glitch_speed_fx.set(s.get("sho_glitch_speed", 90))
            if hasattr(self, "_var_sho_glitch_pulse"):
                self._var_sho_glitch_pulse.set(s.get("sho_glitch_pulse", 3))
            if hasattr(self, "_var_sho_normalize"):
                self._var_sho_normalize.set(s.get("sho_normalize_audio", False))
            if hasattr(self, "_var_sho_fade_in"):
                self._var_sho_fade_in.set(s.get("sho_fade_in", 0.5))
            if hasattr(self, "_var_sho_fade_out"):
                self._var_sho_fade_out.set(s.get("sho_fade_out", 0.5))
            if hasattr(self, "_var_sho_text_overlay"):
                self._var_sho_text_overlay.set(s.get("sho_enable_text_overlay", False))
                self._sho_toggle_text_overlay()
            if hasattr(self, "_var_sho_text_content"):
                self._var_sho_text_content.set(s.get("sho_text_content", ""))
            if hasattr(self, "_var_sho_text_position"):
                self._var_sho_text_position.set(s.get("sho_text_position", "Bottom"))
            if hasattr(self, "_var_sho_text_margin"):
                self._var_sho_text_margin.set(s.get("sho_text_margin", 40))
            if hasattr(self, "_var_sho_text_font_size"):
                self._var_sho_text_font_size.set(s.get("sho_text_font_size", 36))
            if hasattr(self, "_var_sho_text_font"):
                self._var_sho_text_font.set(s.get("sho_text_font", "Arial"))
            if hasattr(self, "_var_sho_text_color"):
                self._var_sho_text_color.set(s.get("sho_text_color", "Blanco"))
            if hasattr(self, "_var_sho_text_glitch_intensity"):
                self._var_sho_text_glitch_intensity.set(s.get("sho_text_glitch_intensity", 3))
            if hasattr(self, "_var_sho_text_glitch_speed"):
                self._var_sho_text_glitch_speed.set(s.get("sho_text_glitch_speed", 4.0))
            # Dynamic text overlay (Shorts)
            if hasattr(self, "_var_sho_dyn_text_overlay"):
                self._var_sho_dyn_text_overlay.set(s.get("sho_enable_dyn_text_overlay", False))
                self._var_sho_dyn_text_mode.set(s.get("sho_dyn_text_mode", "Texto fijo"))
                self._var_sho_dyn_text_content.set(s.get("sho_dyn_text_content", ""))
                self._var_sho_dyn_text_position.set(s.get("sho_dyn_text_position", "Bottom"))
                self._var_sho_dyn_text_margin.set(s.get("sho_dyn_text_margin", 40))
                self._var_sho_dyn_text_font_size.set(s.get("sho_dyn_text_font_size", 36))
                self._var_sho_dyn_text_font.set(s.get("sho_dyn_text_font", "Arial"))
                self._var_sho_dyn_text_color.set(s.get("sho_dyn_text_color", "Blanco"))
                if hasattr(self, "_sho_dyn_text_color_preview"):
                    self._sho_dyn_text_color_preview.configure(fg_color={
                        "Blanco": "#FFFFFF", "Gris claro": "#D0D0D0",
                        "Gris": "#808080", "Gris oscuro": "#404040", "Negro": "#000000",
                    }.get(s.get("sho_dyn_text_color", "Blanco"), "#FFFFFF"))
                self._var_sho_dyn_text_glitch_intensity.set(s.get("sho_dyn_text_glitch_intensity", 3))
                self._var_sho_dyn_text_glitch_speed.set(s.get("sho_dyn_text_glitch_speed", 4.0))
                self._on_sho_dyn_text_mode_change()
                self._sho_toggle_dyn_text_overlay()
            if hasattr(self, "_var_sho_naming_mode"):
                self._var_sho_naming_mode.set(s.get("sho_naming_mode", "Default"))
                self._on_sho_naming_mode_change(self._var_sho_naming_mode.get())
            if hasattr(self, "_var_sho_naming_name"):
                self._var_sho_naming_name.set(s.get("sho_naming_name", ""))
            if hasattr(self, "_var_sho_naming_prefix"):
                self._var_sho_naming_prefix.set(s.get("sho_naming_prefix", ""))
            if hasattr(self, "_txt_sho_naming_list"):
                self._txt_sho_naming_list.delete("1.0", "end")
                custom = s.get("sho_naming_custom_list", "")
                if custom:
                    self._txt_sho_naming_list.insert("1.0", custom)
                self._refresh_sho_names_count()
            if hasattr(self, "_var_sho_naming_autonumber"):
                self._var_sho_naming_autonumber.set(s.get("sho_naming_auto_number", True))
            if hasattr(self, "_var_sho_crf"):
                self._var_sho_crf.set(s.get("sho_crf", 18))
            if hasattr(self, "_var_sho_cpu_mode"):
                self._var_sho_cpu_mode.set(s.get("sho_cpu_mode", "Medium"))
            if hasattr(self, "_var_sho_encode_preset"):
                self._var_sho_encode_preset.set(s.get("sho_encode_preset", "slow"))
            if hasattr(self, "_var_sho_gpu_encoding"):
                self._var_sho_gpu_encoding.set(s.get("sho_gpu_encoding", False))
            self._sho_on_audio_selected()

        # YouTube Publisher settings (UI scaffold)
        if hasattr(self, "_var_yt_timezone"):
            self._var_yt_timezone.set(s.get("yt_timezone", "America/Los_Angeles"))
            self._var_yt_videos_per_day.set(str(s.get("yt_videos_per_day", 3)))
            self._var_yt_window_start.set(s.get("yt_window_start", "09:00"))
            self._var_yt_window_end.set(s.get("yt_window_end", "21:00"))
            self._var_yt_default_category.set(s.get("yt_default_category", "Music"))
            self._var_yt_default_made_for_kids.set(bool(s.get("yt_default_made_for_kids", False)))

        # Prompt Lab settings
        if hasattr(self, "_var_pl_workspace"):
            self._var_pl_workspace.set(s.get("pl_workspace", "General"))
            self._var_pl_category.set(s.get("pl_category", "General"))
            self._var_pl_skill.set(s.get("pl_skill", "Skill General"))
            self._var_pl_model_mode.set(s.get("pl_model_mode", "Calidad alta"))
            self._var_pl_backend_url.set(s.get("pl_backend_url", "http://127.0.0.1:11434"))
            self._var_pl_model_quality.set(s.get("pl_model_quality", "llama3.1:8b"))
            self._var_pl_model_fast.set(s.get("pl_model_fast", "llama3.2:3b"))
            loaded_active = s.get("pl_active_skills", [])
            self._pl_active_skills = []
            if isinstance(loaded_active, list):
                for item in loaded_active:
                    if not isinstance(item, dict):
                        continue
                    cat = str(item.get("category", "")).strip()
                    sk = str(item.get("skill", "")).strip()
                    if cat and sk:
                        self._pl_active_skills.append({"category": cat, "skill": sk})
            loaded_insert_mode = s.get("pl_template_insert_mode_by_category", {})
            self._pl_template_insert_mode_by_category = (
                dict(loaded_insert_mode)
                if isinstance(loaded_insert_mode, dict)
                else {}
            )
            self._pl_last_ws_for_preload = self._var_pl_workspace.get().strip() or "General"
            self._pl_last_category_for_preload = self._var_pl_category.get().strip() or "General"
            if hasattr(self, "_txt_pl_prompt"):
                self._txt_pl_prompt.delete("1.0", "end")
                self._txt_pl_prompt.insert("1.0", s.get("pl_prompt_text", ""))
            self._pl_refresh_workspace_menu(select=self._var_pl_workspace.get())
            self._pl_refresh_available_models()

        # Ensure slider knobs visually reflect loaded variable values.
        self.after_idle(self._sync_slider_visuals)

    def _sync_slider_visuals(self) -> None:
        """Force CTkSlider widgets to redraw knob positions from linked tk variables."""

        def _walk(widget: Any) -> None:
            try:
                children = widget.winfo_children()
            except Exception:
                return

            for child in children:
                try:
                    if isinstance(child, ctk.CTkSlider):
                        var_name = child.cget("variable")
                        if var_name:
                            raw = self.getvar(str(var_name))
                            value = float(raw)
                            child.set(value)
                except Exception:
                    # Non-blocking: keep walking even if one slider cannot be synced.
                    pass

                _walk(child)

        _walk(self)

    def _save_settings(self) -> None:
        self._collect_settings()
        try:
            self.settings.save()
            self._log("?? Configuración guardada.")
        except RuntimeError as exc:
            messagebox.showerror("Error", str(exc))

    # ------------------------------------------------------------------
    # ESTADO DE PROCESAMIENTO
    # ------------------------------------------------------------------

    def _set_processing_state(self, processing: bool) -> None:
        if processing:
            self._btn_generate.configure(state="disabled")
            self._btn_cancel.configure(state="normal")
        else:
            self._btn_cancel.configure(state="disabled")
            # Restore correct generate button label per mode
            if self._current_mode == "Audio \u2192 Video":
                self._btn_generate.configure(
                    state="normal", text="\u25b6  GENERAR VIDEOS",
                    command=self._on_generate)
            elif self._current_mode == "Slideshow":
                self._btn_generate.configure(
                    state="normal", text="\u25b6  GENERAR VIDEO",
                    command=self._on_generate_slideshow)
            elif self._current_mode == "Shorts":
                self._btn_generate.configure(
                    state="normal", text="\u25b6  GENERAR SHORTS",
                    command=self._on_generate_shorts)
            elif self._current_mode == "Prompt Lab":
                self._btn_generate.configure(
                    state="normal", text=FA_WAND + "  GENERAR RESPUESTA",
                    command=self._on_generate_prompt_lab)
            else:
                self._btn_generate.configure(
                    state="normal", text="SYNC BORRADORES",
                    command=self._on_generate_youtube)
            self._progress_file.stop()
            self._progress_file.set(0)
            self._lbl_progress_file.configure(text="")

    # ------------------------------------------------------------------
    # CIERRE
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        running = (
            (self._runner and self._runner.is_running())
            or (self._slideshow_runner and self._slideshow_runner.is_running())
            or (self._shorts_runner and self._shorts_runner.is_running())
        )
        if running:
            if not messagebox.askyesno(
                "Salir",
                "Hay un proceso en ejecuci\u00f3n. \u00bfDeseas cancelarlo y salir?",
            ):
                return
            if self._runner:
                self._runner.cancel()
            if self._slideshow_runner:
                self._slideshow_runner.cancel()
            if self._shorts_runner:
                self._shorts_runner.cancel()

        self._collect_settings()
        try:
            self.settings.save()
        except Exception:
            pass
        self.destroy()




