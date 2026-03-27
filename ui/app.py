"""
App — Interfaz gráfica principal con CustomTkinter.

Layout:
  ┌─────────────────────────────────────────────┐
  │  Header (título + validación de entorno)    │
  ├──────────────┬──────────────────────────────┤
  │  Panel Izq.  │  Panel Der.                  │
  │  - Inputs    │  - Preview imagen            │
  │  - Parámetros│  - Área de logs              │
  │  - Efectos   │  - Barra de progreso global  │
  │  - Presets   │  - Barra de progreso archivo │
  ├──────────────┴──────────────────────────────┤
  │  Botones de acción                          │
  └─────────────────────────────────────────────┘

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
import tkinter as tk
import tkinter.colorchooser as colorchooser
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

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
from core.youtube_auth import YouTubeAuthError, YouTubeAuthService
from core.validator import ValidationResult, validate_environment
from effects.text_overlay_effect import available_fonts
from ui.youtube_tab import build_youtube_publisher_panel

_BUNDLE_DIR = get_bundle_dir()

# ── Theme manager (singleton) ───────────────────────────────────────────────
_TM = _ThemeManager(
    theme_path=_BUNDLE_DIR / "theme.json",
    default_path=_BUNDLE_DIR / "theme_default.json",
)

# ── Font Awesome ────────────────────────────────────────────────────────────
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


# ── Tema ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ── Design system (dark defaults — Obsidian Curator) ─────────────────────
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

# ── Paletas ─────────────────────────────────────────────────────────────────
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
    C_BTN_PRIMARY = t["C_BTN_PRIMARY"]; C_BTN_PRIMARY_TEXT = t["C_BTN_PRIMARY_TEXT"]; C_BTN_SECONDARY = t["C_BTN_SECONDARY"]
    C_BTN_OK = t["C_BTN_OK"]; C_BTN_DANGER = t["C_BTN_DANGER"]
    C_TEXT = t["C_TEXT"]; C_TEXT_DIM = t["C_TEXT_DIM"]; C_MUTED = t["C_MUTED"]
    C_HOVER = t["C_HOVER"]
    C_SUCCESS = t["C_SUCCESS"]; C_ERROR = t["C_ERROR"]; C_WARN = t["C_WARN"]
    C_INPUT = t["C_INPUT"]; C_LOG = t["C_LOG"]; C_LOG_TEXT = t["C_LOG_TEXT"]


# ── Hover-transition animation helpers ──────────────────────────────────────
_ANIM_JOBS:  dict = {}   # widget id → pending animation after-job id
_LEAVE_JOBS: dict = {}   # widget id → pending leave-debounce after-job id


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"


def _animate_widget(widget, props: dict, steps: int = 10, delay: int = 14, _step: int = 0) -> None:
    """Smoothly interpolate colour properties on a CTk widget.
    props = {attribute_name: (from_hex, to_hex)}
    Total duration ≈ steps × delay ms  (default ~140 ms).
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


# ──────────────────────────────────────────────────────────────────────────────
# DIÁLOGO DE ASIGNACIÓN MULTI-IMAGEN
# ──────────────────────────────────────────────────────────────────────────────

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
        self.update_idletasks()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        px = self.master.winfo_x()
        py = self.master.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        x = px + (pw - w) // 2
        y = py + (ph - h) // 2
        self.geometry(f"+{x}+{y}")

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


# ──────────────────────────────────────────────────────────────────────────────
# DIÁLOGO DE LISTA DE NOMBRES PERSONALIZADOS
# ──────────────────────────────────────────────────────────────────────────────

class NamesListDialog(ctk.CTkToplevel):
    """Modal para editar la lista de nombres personalizados de canciones."""

    _USED_PREFIX = "\u25a0 "  # ■ + space

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
        self.update_idletasks()
        pw = self.master.winfo_width()
        ph = self.master.winfo_height()
        px = self.master.winfo_x()
        py = self.master.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

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


# ──────────────────────────────────────────────────────────────────────────────
# DIÁLOGO DE CONFIGURACIÓN DE TEMA
# ──────────────────────────────────────────────────────────────────────────────

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
        self.update_idletasks()
        px, py = self.master.winfo_x(), self.master.winfo_y()
        pw, ph = self.master.winfo_width(), self.master.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    # ── Build ──────────────────────────────────────────────────────────────

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Header (title | spacer | badge | toggle button) ──────────
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
            self._mode_badge, text=f"● {self._app._current_theme}",
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

        # ── Search bar ──
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

        # ── Scrollable list ──
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
        )
        self._scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=(10, 0))
        self._scroll.grid_columnconfigure(0, weight=1)
        _init_scrollbar(self._scroll, width=8)

        self._build_color_list()

        # ── Footer ──
        footer = ctk.CTkFrame(self, fg_color=C_CARD, corner_radius=0,
                               border_width=1, border_color=C_BORDER)
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        footer.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            footer, text="⟳  Restablecer por defecto",
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
                    btns_f, text="⧉", width=30, height=30,
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
                    btns_f, text="✎", width=30, height=30,
                    fg_color=C_ACCENT, hover_color=C_ACCENT_H,
                    text_color="#ffffff", corner_radius=6,
                    font=ctk.CTkFont(size=13),
                    command=lambda k=key: self._pick_color(k),
                ).pack(side="left")

                r += 1

    # ── Actions ────────────────────────────────────────────────────────────

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
            btn.configure(text="✓", fg_color=C_SUCCESS, text_color="#ffffff")
            self.after(1200, lambda: btn.configure(text="⧉", fg_color="transparent",
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
        self._mode_lbl.configure(text=f"● {new_mode}", text_color=_c)
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
        self.update_idletasks()
        pw = self._app.winfo_width()
        ph = self._app.winfo_height()
        px = self._app.winfo_x()
        py = self._app.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"{w}x{h}+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # ── Header ──────────────────────────────────────────────────
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

        # ── Scrollable tiles area ────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=16, pady=(12, 4))
        scroll.grid_columnconfigure(0, weight=1)
        _init_scrollbar(scroll)

        self._tiles_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        self._tiles_frame.grid(row=0, column=0, sticky="ew")
        self._tiles_frame.grid_columnconfigure(0, weight=1)
        self._tiles_frame.grid_columnconfigure(1, weight=1)

        # ── Footer actions ───────────────────────────────────────────
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
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        self.configure(fg_color=C_CARD)

        self._progress_mode = "indeterminate"
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

        self.geometry("460x160")
        self.after(60, self._center)

    def _center(self) -> None:
        self.update_idletasks()
        parent = self.master
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

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
        self.update_idletasks()
        parent = self.master
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

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


class AudioToVideoApp(ctk.CTk):
    """Ventana principal de la aplicación."""

    WINDOW_TITLE = "CreatorFlow Studio"
    WINDOW_SIZE = "1280x800"
    MIN_SIZE = (1100, 700)
    SCROLL_SPEED = 3.75   # Multiplicador de velocidad del scroll con rueda del ratón

    def __init__(self) -> None:
        # Desactivar manipulación de título antes de que CTk la aplique
        self._deactivate_windows_window_header_manipulation = True
        super().__init__()

        self.settings = SettingsManager()
        self._runner: Runner | None = None
        self._image_assignment: dict[str, Path] = {}
        self._used_names: set[str] = set()
        self._last_run_names: list[str] = []
        self._current_mode: str = "Audio → Video"
        self._slideshow_runner: SlideshowRunner | None = None
        self._shorts_runner: ShortsRunner | None = None
        self._sho_image_paths: list[Path] = []
        self._sho_used_names: set[str] = set()
        self._sho_last_run_names: list[str] = []
        self._yt_video_rows: list[dict[str, str]] = []  # filled when drafts are fetched
        self._yt_auth_service: YouTubeAuthService | None = None
        self._yt_auth_dialog: BusyDialog | None = None
        self._yt_auth_in_progress = False
        self._presets_dialog: PresetsDialog | None = None
        self._preset_tiles_frame: ctk.CTkFrame | None = None
        self._startup_dependency_dialog: StartupDependencyDialog | None = None
        self._startup_last_status_message = ""
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

    # ──────────────────────────────────────────────────────────────────
    # VENTANA
    # ──────────────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.title(self.WINDOW_TITLE)
        self.geometry(self.WINDOW_SIZE)
        self.minsize(*self.MIN_SIZE)
        self.state("zoomed")
        self.configure(fg_color=C_BG)
        self.protocol("WM_D`ELETE_WINDOW", self._on_close)
        # Icono de la ventana (title bar + taskbar)
        ico = _BUNDLE_DIR / "logoAtV.ico"
        if ico.is_file():
            self.after(10, lambda: self.iconbitmap(str(ico)))

    # ──────────────────────────────────────────────────────────────────
    # BUILD UI
    # ──────────────────────────────────────────────────────────────────

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

        # ── Barra de acento vertical izquierda ──
        ctk.CTkFrame(header, width=3, fg_color=C_ACCENT, corner_radius=1).grid(
            row=0, column=0, padx=(14, 0), pady=8, sticky="ns"
        )

        # ── Título ──
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

        # ── Botones de modo: ATV y SLIDE ────────────────────────────
        mode_grp = ctk.CTkFrame(
            header, fg_color=C_CARD, corner_radius=8,
            border_width=1, border_color=C_BORDER,
        )
        mode_grp.grid(row=0, column=2, padx=(20, 0))

        def _create_mode_btn(icon, acronym, is_active, accent, cmd, prefix):
            # Outer wrapper: fixed 110×42px, placed children for precise layout
            wrap = ctk.CTkFrame(mode_grp, fg_color="transparent",
                                corner_radius=0, width=110, height=42)
            wrap.pack(side="left", padx=2, pady=(4, 0))
            wrap.pack_propagate(False)

            bg  = C_INPUT if is_active else "transparent"
            txt = C_TEXT  if is_active else C_TEXT_DIM
            ind = accent  if is_active else "transparent"

            # Content area (40px tall) — fills wrap, bar sits beneath it
            inner = ctk.CTkFrame(wrap, fg_color=bg, corner_radius=6,
                                 cursor="hand2", width=110, height=40)
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


        # ── Badge de estado del entorno ──────────────────────────────
        self._status_badge = ctk.CTkFrame(
            header, fg_color=C_CARD, corner_radius=20,
            border_width=1, border_color=C_BORDER,
        )
        self._status_badge.grid(row=0, column=4, padx=(8, 4))
        self._lbl_status_dot = ctk.CTkLabel(
            self._status_badge, text="●",
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

        # ── Controles (tema + tamaño de fuente) ─────────────────────
        ctrl = ctk.CTkFrame(
            header, fg_color=C_CARD, corner_radius=6,
            border_width=1, border_color=C_BORDER,
        )
        ctrl.grid(row=0, column=5, padx=(4, 14))

        # ── Presets button ────────────────────────────────────────
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
        for _label, _size in (("A⁻", "Small"), ("A", "Medium"), ("A⁺", "Large")):
            _active = (self._font_scale == _FONT_SIZE_SCALE[_size])
            btn = ctk.CTkButton(
                ctrl, text=_label,
                width=30, height=26,
                fg_color=C_ACCENT if _active else "transparent",
                hover_color=C_HOVER,
                text_color=C_TEXT if _active else C_TEXT_DIM,
                border_width=0,
                font=ctk.CTkFont(
                    size=12 if _label == "A" else (10 if _label == "A⁻" else 14)
                ),
                corner_radius=4,
                command=lambda s=_size: self._on_font_size(s),
            )
            btn.pack(side="left", padx=2, pady=4)
            self._font_btns[_size] = btn

        # ── Divisor + Botón de configuración de tema ─────────────────
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

        # ── Separador inferior del header ────────────────────────────
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

        # ══════════════════════════════════════════════════════════════
        # TAB: ARCHIVOS
        # ══════════════════════════════════════════════════════════════
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

        # ══════════════════════════════════════════════════════════════
        # TAB: VISUAL
        # ══════════════════════════════════════════════════════════════
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
                "• 0  → Lossless (sin pérdida). Archivo enorme.\n"
                "• 18 → Alta calidad (recomendado). Buen balance.\n"
                "• 23 → Calidad media. Archivo más liviano.\n"
                "• 28 → Baja calidad. Solo para pruebas.\n"
                "• 51 → La peor calidad posible.\n\n"
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
                     placeholder_text="Ej: Lo-Fi Beats ♪", height=28).grid(
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

        # ══════════════════════════════════════════════════════════════
        # TAB: SALIDA
        # ══════════════════════════════════════════════════════════════
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
            "• Low   (25%)  →  El sistema sigue libre, encoding lento.\n"
            "• Medium (50%) →  Balance recomendado para uso diario.\n"
            "• High  (75%)  →  Más rápido, el sistema puede sentirse pesado.\n"
            "• Max  (100%)  →  Usa todos los núcleos. Máxima velocidad.",
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
            "• ultrafast / superfast → Solo para pruebas rápidas.\n"
            "• fast / medium         → Buena calidad, uso general.\n"
            "• slow                  → Calidad óptima (recomendado).\n"
            "• veryslow              → Máxima compresión, muy lento.",
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

        # ══════════════════════════════════════════════════════════════
        # TAB: ARCHIVOS
        # ══════════════════════════════════════════════════════════════
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

        # ── Mode radio: Un archivo / Carpeta de audios ───────────────
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

        # ── Single-file sub-frame ─────────────────────────────────────
        self._sl_single_audio_frame = ctk.CTkFrame(self._sl_audio_wrapper, fg_color="transparent")
        self._sl_single_audio_frame.grid(row=1, column=0, sticky="ew")
        self._sl_single_audio_frame.grid_columnconfigure(0, weight=1)
        self._var_sl_audio_file = tk.StringVar()
        self._file_row(self._sl_single_audio_frame, "Archivo de audio:", self._var_sl_audio_file,
                       self._sl_browse_audio_file, 0)

        # ── Folder sub-frame ──────────────────────────────────────────
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

        # ── Crossfade slider ──────────────────────────────────────────
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

        # ══════════════════════════════════════════════════════════════
        # TAB: SECUENCIA
        # ══════════════════════════════════════════════════════════════
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
                     placeholder_text="Ej: Lo-Fi Beats ♪", height=28).grid(
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
                     placeholder_text="Ej: Lo-Fi Beats ♪", height=28).grid(
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

        # ══════════════════════════════════════════════════════════════
        # TAB: RENDIMIENTO
        # ══════════════════════════════════════════════════════════════
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

        # ══════════════════════════════════════════════════════════════
        # TAB: CONFIG
        # ══════════════════════════════════════════════════════════════
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

        # ══════════════════════════════════════════════════════════════
        # TAB: VISUAL
        # ══════════════════════════════════════════════════════════════
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
                     placeholder_text="Ej: Lo-Fi Beats ♪", height=28).grid(
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

        # ══════════════════════════════════════════════════════════════
        # TAB: SALIDA
        # ══════════════════════════════════════════════════════════════
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
        self._yt_render_queue_preview()
        self._yt_refresh_channel_status(silent=True)

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

    def _yt_refresh_channel_status(self, silent: bool = False) -> None:
        """Refresh channel status label using stored OAuth credentials if available."""
        if not hasattr(self, "_var_yt_channel_status"):
            return

        service = self._yt_get_auth_service()
        try:
            if not service.has_stored_credentials():
                self._var_yt_channel_status.set("No conectado.")
                if not silent:
                    self._log("[YouTube] No hay sesion guardada. Pulsa 'Conectar canal'.")
                return

            info = service.get_channel_info()
            self._var_yt_channel_status.set(
                f"Conectado: {info.title} ({info.channel_id})"
            )
            if not silent:
                self._log(f"[YouTube] Canal activo: {info.title}")
        except YouTubeAuthError as exc:
            self._var_yt_channel_status.set("No conectado.")
            if not silent:
                self._log(f"[YouTube] {exc}")
        except Exception as exc:
            self._var_yt_channel_status.set("No conectado.")
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
        self._log(f"[YouTube] {msg}")
        messagebox.showerror("YouTube Publisher", msg)

    def _yt_fetch_drafts(self) -> None:
        """Load private videos without publishAt from YouTube into queue preview."""
        self._log("[YouTube] Consultando borradores privados sin fecha...")
        try:
            rows = self._yt_get_auth_service().list_private_unscheduled_drafts(limit=200)
        except YouTubeAuthError as exc:
            self._log(f"[YouTube] {exc}")
            messagebox.showwarning("YouTube Publisher", str(exc))
            return
        except Exception as exc:
            self._log(f"[YouTube] Error al cargar borradores: {exc}")
            messagebox.showwarning("YouTube Publisher", f"Error al cargar borradores: {exc}")
            return

        self._yt_video_rows = rows
        self._yt_render_queue_preview()
        self._log(f"[YouTube] Borradores listos para programar: {len(rows)} video(s).")

    def _yt_open_bulk_modal(self) -> None:
        modal = __import__('customtkinter').CTkToplevel(self)
        modal.title('Metadatos en lote')
        modal.geometry('600x510')
        modal.resizable(False, False)
        modal.grab_set()
        modal.focus_force()
        # centered on screen        modal.update_idletasks()
        x = (modal.winfo_screenwidth() - modal.winfo_width()) // 2
        y = (modal.winfo_screenheight() - modal.winfo_height()) // 2
        modal.geometry(f"+{x}+{y}")
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
        _ctk2.CTkLabel(inner, text='Categoria', **_lbl).grid(row=1, column=0, sticky='ew', pady=(0,4))
        _var_cat = _tk2.StringVar(value=self._var_yt_default_category.get() if hasattr(self,'_var_yt_default_category') else 'Music')
        _ctk2.CTkOptionMenu(inner, variable=_var_cat,
            values=['Music','Entertainment','People & Blogs','Education','Film & Animation','Howto & Style','Gaming','Science & Technology','News & Politics','Sports'],
            **_opt).grid(row=2, column=0, sticky='ew', pady=(0,10))
        _var_kids = _tk2.BooleanVar(value=False)
        _ctk2.CTkCheckBox(inner, text='Hecho para ninos', variable=_var_kids,
            fg_color=C_ACCENT_YT, hover_color=C_ACCENT_YT_H, text_color=C_TEXT,
            font=_ctk2.CTkFont(size=self._fs(11))).grid(row=3, column=0, sticky='w', pady=(0,10))
        _ctk2.CTkLabel(inner, text='Descripcion (se aplica a todos los videos)', **_lbl).grid(row=4, column=0, sticky='ew', pady=(0,4))
        _txt_desc = _ctk2.CTkTextbox(inner, height=120, fg_color=C_INPUT,
            border_width=1, border_color=C_BORDER, text_color=C_TEXT, font=_ctk2.CTkFont(size=self._fs(11)))
        _txt_desc.grid(row=5, column=0, sticky='ew', pady=(0,10))
        _ctk2.CTkLabel(inner, text='Tags (separados por coma)', **_lbl).grid(row=6, column=0, sticky='ew', pady=(0,4))
        _var_tags = _tk2.StringVar()
        _ctk2.CTkEntry(inner, textvariable=_var_tags, placeholder_text='lofi, music, chill...',
            fg_color=C_INPUT, border_color=C_BORDER, text_color=C_TEXT, height=45).grid(row=7, column=0, sticky='ew', pady=(0,4))
        btns = _ctk2.CTkFrame(modal, fg_color='transparent')
        btns.pack(fill='x', padx=20, pady=(0,16))
        def _apply_bulk():
            desc = _txt_desc.get('1.0','end').strip()
            cat = _var_cat.get()
            kids = _var_kids.get()
            tags_raw = _var_tags.get().strip()
            for row in self._yt_video_rows:
                row['category'] = cat
                row['kids'] = 'Si' if kids else 'No'
                if desc: row['description'] = desc
                if tags_raw: row['tags'] = tags_raw
            self._yt_render_queue_preview()
            self._log(f"[YouTube] Metadatos en lote aplicados a {len(self._yt_video_rows)} video(s).")
            modal.destroy()
        _ctk2.CTkButton(btns, text='Aplicar a cola', fg_color=C_ACCENT_YT, hover_color=C_ACCENT_YT_H,
            text_color='#FFFFFF', command=_apply_bulk).pack(side='left', padx=(0,8))
        _ctk2.CTkButton(btns, text='Cancelar', fg_color='transparent', hover_color=C_HOVER,
            border_width=2, border_color=C_BORDER, text_color=C_TEXT, command=modal.destroy).pack(side='left')

    def _yt_open_schedule_modal(self) -> None:
        import datetime as _dt
        import tkinter as _tk3
        import customtkinter as _ctk3
        modal = _ctk3.CTkToplevel(self)
        modal.title('Programar publicacion')
        modal.geometry('440x360')
        modal.resizable(False, False)
        modal.grab_set()
        modal.focus_force()
        # centered on screen        modal.update_idletasks()
        x = (modal.winfo_screenwidth() - modal.winfo_width()) // 2 
        y = (modal.winfo_screenheight() - modal.winfo_height()) // 2
        modal.geometry(f"+{x}+{y}")
        modal.configure(fg_color=C_BG)
        inner = _ctk3.CTkFrame(modal, fg_color='transparent')
        inner.pack(fill='both', expand=True, padx=20, pady=(16, 8))
        inner.grid_columnconfigure(1, weight=1)
        _ctk3.CTkLabel(inner, text='Programar publicacion', anchor='w',
            text_color=C_TEXT, font=_ctk3.CTkFont(size=self._fs(14), weight='bold'),
        ).grid(row=0, column=0, columnspan=2, sticky='ew', pady=(0,12))
        _lbl = dict(text_color=C_MUTED, anchor='w', font=_ctk3.CTkFont(size=self._fs(11)))
        _ent = dict(fg_color=C_INPUT, border_color=C_BORDER, text_color=C_TEXT, height=30)
        tz_val = self._var_yt_timezone.get() if hasattr(self,'_var_yt_timezone') else 'America/El_Salvador'
        _ctk3.CTkLabel(inner, text='Zona horaria', **_lbl).grid(row=1, column=0, sticky='w', padx=(0,10), pady=(0,6))
        _ctk3.CTkLabel(inner, text=tz_val, text_color=C_TEXT, anchor='w', font=_ctk3.CTkFont(size=self._fs(11))).grid(row=1, column=1, sticky='ew', pady=(0,6))
        vpd_val = self._var_yt_videos_per_day.get() if hasattr(self,'_var_yt_videos_per_day') else '3'
        _var_vpd = _tk3.StringVar(value=vpd_val)
        _ctk3.CTkLabel(inner, text='Videos por dia', **_lbl).grid(row=2, column=0, sticky='w', padx=(0,10), pady=(0,6))
        _ctk3.CTkOptionMenu(inner, variable=_var_vpd, values=['1','2','3','4','5','6'],
            fg_color=C_INPUT, button_color=C_ACCENT_YT, button_hover_color=C_ACCENT_YT_H,
            text_color=C_TEXT, dropdown_fg_color=C_CARD, dropdown_text_color=C_TEXT, dropdown_hover_color=C_HOVER,
        ).grid(row=2, column=1, sticky='ew', pady=(0,6))
        _var_sd = _tk3.StringVar(value=_dt.date.today().strftime('%Y-%m-%d'))
        _ctk3.CTkLabel(inner, text='Fecha inicial', **_lbl).grid(row=3, column=0, sticky='w', padx=(0,10), pady=(0,6))
        _ctk3.CTkEntry(inner, textvariable=_var_sd, placeholder_text='YYYY-MM-DD', **_ent).grid(row=3, column=1, sticky='ew', pady=(0,6))
        st = self._var_yt_window_start.get() if hasattr(self,'_var_yt_window_start') else '09:00'
        _var_st = _tk3.StringVar(value=st)
        _ctk3.CTkLabel(inner, text='Hora de inicio', **_lbl).grid(row=4, column=0, sticky='w', padx=(0,10), pady=(0,6))
        _ctk3.CTkEntry(inner, textvariable=_var_st, placeholder_text='HH:MM', **_ent).grid(row=4, column=1, sticky='ew', pady=(0,10))
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

                start_date = dt.datetime.strptime(_var_sd.get().strip(), "%Y-%m-%d").date()
                videos_per_day = max(1, int(_var_vpd.get()))
                start_h, start_m = [int(x) for x in self._var_yt_window_start.get().split(":", 1)]
                end_h, end_m = [int(x) for x in self._var_yt_window_end.get().split(":", 1)]
            except Exception:
                messagebox.showwarning(
                    "YouTube Publisher",
                    "Valores de programacion invalidos. Revisa fecha y ventana horaria (HH:MM).",
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


    def _yt_render_queue_preview(self) -> None:
        if not hasattr(self, "_yt_queue_frame"):
            return
        for w in self._yt_queue_frame.winfo_children():
            w.destroy()

        headers = ["Archivo", "Titulo", "Categoria", "Ninos", "Fecha"]
        for c, title in enumerate(headers):
            ctk.CTkLabel(
                self._yt_queue_frame,
                text=title,
                text_color=C_MUTED,
                font=ctk.CTkFont(size=self._fs(10), weight="bold"),
                anchor="w",
            ).grid(row=0, column=c, sticky="ew", padx=(2, 4), pady=(0, 6))

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
                height=26,
            )
            title_entry.grid(row=i, column=1, sticky="ew", padx=(0, 4), pady=2)

            def _save_title(_e: Any = None, *, _row: dict[str, str] = row, _var: tk.StringVar = title_var) -> None:
                _row["title"] = _var.get().strip()

            title_entry.bind("<FocusOut>", _save_title)
            title_entry.bind("<Return>", _save_title)

            ctk.CTkLabel(
                self._yt_queue_frame,
                text=row["category"],
                text_color=C_TEXT,
                anchor="w",
                font=ctk.CTkFont(size=self._fs(10)),
            ).grid(row=i, column=2, sticky="ew", padx=(0, 4), pady=2)

            ctk.CTkLabel(
                self._yt_queue_frame,
                text=row["kids"],
                text_color=C_TEXT,
                anchor="w",
                font=ctk.CTkFont(size=self._fs(10)),
            ).grid(row=i, column=3, sticky="ew", padx=(0, 4), pady=2)

            schedule_var = tk.StringVar(value=row["schedule"])
            schedule_entry = ctk.CTkEntry(
                self._yt_queue_frame,
                textvariable=schedule_var,
                placeholder_text="YYYY-MM-DD HH:MM",
                fg_color=C_INPUT,
                border_color=C_BORDER,
                text_color=C_TEXT,
                height=26,
            )
            schedule_entry.grid(row=i, column=4, sticky="ew", padx=(0, 2), pady=2)

            def _save_schedule(_e: Any = None, *, _row: dict[str, str] = row, _var: tk.StringVar = schedule_var) -> None:
                _row["schedule"] = _var.get().strip()

            schedule_entry.bind("<FocusOut>", _save_schedule)
            schedule_entry.bind("<Return>", _save_schedule)

    def _on_generate_youtube(self) -> None:
        """Apply scheduled metadata updates to YouTube using videos.update."""
        if not self._yt_video_rows:
            messagebox.showwarning("YouTube Publisher", "No hay videos en cola.")
            return

        tz_name = self._var_yt_timezone.get() if hasattr(self, "_var_yt_timezone") else "America/El_Salvador"
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

        ok = 0
        fail = 0
        svc = self._yt_get_auth_service()
        self._log(f"[YouTube] Enviando {len(pending)} actualizacion(es) a YouTube...")
        for item in pending:
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
                ok += 1
                self._log(f"[YouTube] Programado: {item['video_id']} -> {item['publish_at_utc']}")
            except YouTubeAuthError as exc:
                fail += 1
                self._log(f"[YouTube] Error {item['video_id']}: {exc}")
            except Exception as exc:
                fail += 1
                self._log(f"[YouTube] Error inesperado {item['video_id']}: {exc}")

        self._log(f"[YouTube] Resultado envio -> OK: {ok}, Error: {fail}")
        if fail == 0:
            messagebox.showinfo("YouTube Publisher", f"Programacion enviada. Videos OK: {ok}")
        else:
            messagebox.showwarning("YouTube Publisher", f"Proceso finalizado. OK: {ok}, Error: {fail}")
    # --- Footer -------------------------------------------------------

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0, height=56)
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_propagate(False)
        footer.grid_columnconfigure(2, weight=1)

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

    # ──────────────────────────────────────────────────────────────────
    # HELPERS DE CONSTRUCCIÓN DE WIDGETS
    # ──────────────────────────────────────────────────────────────────

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

        # ── tab-style header container ──────────────────────────────
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

    # ── custom underline tab panel ────────────────────────────────────
    def _make_tab_panel(
        self,
        parent: ctk.CTkFrame,
        tabs: list,
        accent: str,
    ) -> tuple:
        """
        Creates an underline-style tab panel.
        Returns: (outer_frame, dict[name -> content_frame])
        """
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)

        # ── Tab header bar ────────────────────────────────────────────
        bar = ctk.CTkFrame(
            outer, fg_color=C_CARD, corner_radius=10,
            border_width=1, border_color=C_BORDER, height=46,
        )
        bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 8))
        bar.grid_propagate(False)
        for i in range(len(tabs)):
            bar.grid_columnconfigure(i, weight=1, uniform="tab")

        # ── Content area ──────────────────────────────────────────────
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

        return outer, {n: d["frame"] for n, d in tab_data.items()}

    def _section_header(self, parent: Any, text: str) -> ctk.CTkFrame:
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
        if hasattr(self, "_section_toggles"):
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

    # ──────────────────────────────────────────────────────────────────
    # TEMA, FUENTE Y HELPERS
    # ──────────────────────────────────────────────────────────────────

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
        self._load_settings_to_ui()
        if hasattr(self, "_log_text"):
            self._log_text.configure(font=ctk.CTkFont(family="Consolas", size=self._fs(11)))

    # ──────────────────────────────────────────────────────────────────
    # MODO SLIDESHOW — switch + acciones
    # ──────────────────────────────────────────────────────────────────

    def _update_mode_buttons(self) -> None:
        """Actualiza el color activo/inactivo de los botones de modo del header."""
        for prefix in ("atv", "slide", "shorts", "yt"):
            if not hasattr(self, f"_frame_mode_{prefix}"):
                continue
            active = (
                (prefix == "atv" and self._current_mode == "Audio \u2192 Video")
                or (prefix == "slide" and self._current_mode == "Slideshow")
                or (prefix == "shorts" and self._current_mode == "Shorts")
                or (prefix == "yt" and self._current_mode == "YouTube Publisher")
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
        """Alterna entre los paneles Audio→Video, Slideshow y Shorts."""
        self._current_mode = mode
        self._configure_preview_for_mode(mode)
        self._update_mode_buttons()
        # Flush pending geometry events so the preview frame has its correct size
        # before loading images (avoids canvas being 0px wide after Shorts→ATV)
        self.update_idletasks()
        # Show/hide the right panel depending on the active mode.
        # YouTube Publisher uses the full window width; all other modes keep
        # the normal 60/40 split with the preview + logs column.
        if mode == "YouTube Publisher":
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

        else:  # YouTube Publisher
            if hasattr(self, "_yt_scroll_frame"):
                self._yt_scroll_frame.grid()
            self._thumb_strip.grid_remove()
            if hasattr(self, "_thumb_strip_vert"):
                self._thumb_strip_vert.grid_remove()
            self._lbl_audio_count.configure(text="YouTube Publisher", text_color=C_ACCENT_YT)
            self._btn_generate.configure(text="SYNC BORRADORES", command=self._on_generate_youtube)

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

    # ──────────────────────────────────────────────────────────────────
    # MODO SHORTS — acciones de UI
    # ──────────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────────
    # ACCIONES DE UI
    # ──────────────────────────────────────────────────────────────────

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
            self._log(f"✅ Asignación guardada: {len(dlg.result)} audio(s).")

    def _open_names_list_dialog(self) -> None:
        _p = NamesListDialog._USED_PREFIX
        raw = [l.strip() for l in self._txt_naming_list.get("1.0", "end").splitlines() if l.strip()]
        # Strip ■ prefix to get clean names for passing as current_names
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
        self._log(f"🎛 Preset '{name}' aplicado.")

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
        self._log(f"✅ Preset '{name}' creado.")

    def _overwrite_preset(self, name: str) -> None:
        """Sobrescribe un preset existente con las configuraciones actuales."""
        if not messagebox.askyesno(
            "Sobrescribir preset",
            f"¿Reemplazar '{name}' con la configuración actual?",
        ):
            return
        self._collect_settings()
        self.settings.save_preset(name, self.settings.all())
        self._log(f"💾 Preset '{name}' actualizado.")

    def _delete_preset(self, name: str) -> None:
        """Elimina un preset."""
        if not messagebox.askyesno("Eliminar preset", f"¿Eliminar el preset '{name}'?"):
            return
        try:
            self.settings.delete_preset(name)
            self._rebuild_preset_tiles()
            self._log(f"🗑️ Preset '{name}' eliminado.")
        except ValueError as e:
            messagebox.showerror("Error", str(e))

    def _rename_preset(self, old_name: str) -> None:
        """Renombra un preset."""
        dialog = ctk.CTkInputDialog(
            text=f"Nuevo nombre para '{old_name}':", title="Renombrar Preset",
        )
        new_name = dialog.get_input()
        if not new_name or not new_name.strip():
            return
        new_name = new_name.strip()
        try:
            self.settings.rename_preset(old_name, new_name)
            self._rebuild_preset_tiles()
            self._log(f"✏️ Preset '{old_name}' → '{new_name}'.")
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
            self._log(f"📤 Preset '{name}' exportado → {path}")
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
                self._log(f"📥 Preset(s) importado(s): {names_str}")
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

        # Center on screen
        dlg.update_idletasks()
        dw = dlg.winfo_reqwidth()
        dh = dlg.winfo_reqheight()
        x = (sw - dw) // 2
        y = (sh - dh) // 2
        dlg.geometry(f"+{x}+{y}")

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
                # Canvas directo 203×360 → misma relación proporcional que el export 1080×1920
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
                # Canvas directo 203×360 → misma relación proporcional que el export 1080×1920
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

    # ──────────────────────────────────────────────────────────────────
    # ACCIONES PRINCIPALES
    # ──────────────────────────────────────────────────────────────────

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
        self._log(f"👁 Generando preview de 10s → {output}")

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
                    self._queue_log(f"✔ Preview guardado: {output}")
                else:
                    self._queue_log(f"✘ Preview falló:\n{r.stderr[-300:]}")
            except Exception as exc:
                self._queue_log(f"✘ Error en preview: {exc}")

        threading.Thread(target=_run, daemon=True).start()

    def _on_test_ffmpeg(self) -> None:
        output = Path(self._var_output.get() or ".") / "_ffmpeg_test.mp4"
        self._log(f"🔧 Probando FFmpeg → {output}")

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

    # ── Abrir carpeta de salida ──────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────────
    # CALLBACKS DEL RUNNER (llamados desde hilo secundario)
    # ──────────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────────
    # LOGS (thread-safe via cola)
    # ──────────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────────
    # VALIDACIONES
    # ──────────────────────────────────────────────────────────────────

    def _run_validation(self) -> None:
        if self._validation_in_progress:
            return

        self._validation_in_progress = True
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

    def _run_validation_worker(self) -> None:
        self.after(
            0,
            self._set_startup_dependency_status,
            "Verificando dependencias...",
            "Comprobando FFmpeg y herramientas del sistema.",
            None,
        )

        ffmpeg_dir = ensure_ffmpeg(on_progress=self._on_ffmpeg_progress)
        if ffmpeg_dir is None:
            self.after(0, self._log, "✘ No se pudo localizar ni instalar FFmpeg.")

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

        # ── Validación de nombres de salida ──
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

    # ──────────────────────────────────────────────────────────────────
    # SINCRONIZACIÓN SETTINGS ↔ UI
    # ──────────────────────────────────────────────────────────────────

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
            "yt_timezone": self._var_yt_timezone.get() if hasattr(self, "_var_yt_timezone") else "America/El_Salvador",
            "yt_videos_per_day": int(self._var_yt_videos_per_day.get()) if hasattr(self, "_var_yt_videos_per_day") else 3,
            "yt_window_start": self._var_yt_window_start.get() if hasattr(self, "_var_yt_window_start") else "09:00",
            "yt_window_end": self._var_yt_window_end.get() if hasattr(self, "_var_yt_window_end") else "21:00",
            "yt_default_category": self._var_yt_default_category.get() if hasattr(self, "_var_yt_default_category") else "Music",
            "yt_default_made_for_kids": self._var_yt_default_made_for_kids.get() if hasattr(self, "_var_yt_default_made_for_kids") else False,
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
            self._var_yt_timezone.set(s.get("yt_timezone", "America/El_Salvador"))
            self._var_yt_videos_per_day.set(str(s.get("yt_videos_per_day", 3)))
            self._var_yt_window_start.set(s.get("yt_window_start", "09:00"))
            self._var_yt_window_end.set(s.get("yt_window_end", "21:00"))
            self._var_yt_default_category.set(s.get("yt_default_category", "Music"))
            self._var_yt_default_made_for_kids.set(bool(s.get("yt_default_made_for_kids", False)))

    def _save_settings(self) -> None:
        self._collect_settings()
        try:
            self.settings.save()
            self._log("💾 Configuración guardada.")
        except RuntimeError as exc:
            messagebox.showerror("Error", str(exc))

    # ──────────────────────────────────────────────────────────────────
    # ESTADO DE PROCESAMIENTO
    # ──────────────────────────────────────────────────────────────────

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
            else:
                self._btn_generate.configure(
                    state="normal", text="SYNC BORRADORES",
                    command=self._on_generate_youtube)
            self._progress_file.stop()
            self._progress_file.set(0)
            self._lbl_progress_file.configure(text="")

    # ──────────────────────────────────────────────────────────────────
    # CIERRE
    # ──────────────────────────────────────────────────────────────────

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



