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
import os
import threading
import tkinter as tk
import tkinter.filedialog as filedialog
import tkinter.messagebox as messagebox
from pathlib import Path
from typing import Any

import customtkinter as ctk
from PIL import Image

from config.settings_manager import SettingsManager
from core.runner import JobResult, Runner
from core.utils import get_audio_files
from core.validator import ValidationResult, validate_environment
from effects.text_overlay_effect import available_fonts

# ── Font Awesome ────────────────────────────────────────────────────────────
_FA_FONT_PATH = str(Path(__file__).resolve().parent.parent / "fonts" / "Font Awesome 6 Free-Solid-900.otf")
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


# ── Tema ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ── Design system (dark defaults) ──────────────────────────────────────────
C_BG          = "#0c0c11"   # Root background
C_PANEL       = "#111118"   # Panel / sidebar background
C_CARD        = "#1a1a26"   # Section card background
C_BORDER      = "#26263c"   # Card borders & separators
C_ACCENT      = "#4361ee"   # Primary brand blue
C_ACCENT_H    = "#3451d1"   # Accent hover
C_BTN_PRIMARY = "#4361ee"   # Generate / primary CTA
C_BTN_SECONDARY = "#1e1e32" # Secondary button bg
C_BTN_OK      = "#2d8f5a"   # OK / success action
C_BTN_DANGER  = "#d64040"   # Danger / destructive
C_TEXT        = "#e0e0ee"   # Primary text
C_TEXT_DIM    = "#9090b8"   # Secondary / dimmed text
C_MUTED       = "#5a5a7a"   # Muted labels
C_HOVER       = "#22223a"   # Generic hover surface
C_SUCCESS     = "#40c880"
C_ERROR       = "#e05050"
C_WARN        = "#e8a030"
C_INPUT       = "#0a0a10"   # Input field background
C_LOG         = "#080810"   # Log textarea background

# ── Paletas ─────────────────────────────────────────────────────────────────
_DARK_PALETTE: dict[str, str] = {
    "BG": "#0c0c11", "PANEL": "#111118", "CARD": "#1a1a26", "BORDER": "#26263c",
    "ACCENT": "#4361ee", "ACCENT_H": "#3451d1",
    "BTN_PRIMARY": "#4361ee", "BTN_SECONDARY": "#1e1e32",
    "BTN_OK": "#2d8f5a", "BTN_DANGER": "#d64040",
    "TEXT": "#e0e0ee", "TEXT_DIM": "#9090b8", "MUTED": "#8d8d9c",
    "HOVER": "#22223a",
    "SUCCESS": "#40c880", "ERROR": "#e05050", "WARN": "#e8a030",
    "INPUT": "#0a0a10", "LOG": "#080810",
}
_LIGHT_PALETTE: dict[str, str] = {
    "BG": "#f0f2f8", "PANEL": "#e6e9f4", "CARD": "#ffffff", "BORDER": "#cdd2e8",
    "ACCENT": "#4361ee", "ACCENT_H": "#3451d1",
    "BTN_PRIMARY": "#4361ee", "BTN_SECONDARY": "#dde2f0",
    "BTN_OK": "#2d8f5a", "BTN_DANGER": "#d64040",
    "TEXT": "#18182e", "TEXT_DIM": "#50507a", "MUTED": "#8888aa",
    "HOVER": "#dde2f0",
    "SUCCESS": "#2d8f5a", "ERROR": "#c83030", "WARN": "#b87020",
    "INPUT": "#f4f6ff", "LOG": "#111128",
}

_FONT_SIZE_SCALE = {"Small": 0.82, "Medium": 1.0, "Large": 1.22}


def _apply_theme(mode: str) -> None:
    """Actualiza las variables globales de color según el tema indicado."""
    global C_BG, C_PANEL, C_CARD, C_BORDER, C_ACCENT, C_ACCENT_H
    global C_BTN_PRIMARY, C_BTN_SECONDARY, C_BTN_OK, C_BTN_DANGER
    global C_TEXT, C_TEXT_DIM, C_MUTED, C_HOVER
    global C_SUCCESS, C_ERROR, C_WARN, C_INPUT, C_LOG
    t = _DARK_PALETTE if mode == "Dark" else _LIGHT_PALETTE
    C_BG = t["BG"]; C_PANEL = t["PANEL"]; C_CARD = t["CARD"]; C_BORDER = t["BORDER"]
    C_ACCENT = t["ACCENT"]; C_ACCENT_H = t["ACCENT_H"]
    C_BTN_PRIMARY = t["BTN_PRIMARY"]; C_BTN_SECONDARY = t["BTN_SECONDARY"]
    C_BTN_OK = t["BTN_OK"]; C_BTN_DANGER = t["BTN_DANGER"]
    C_TEXT = t["TEXT"]; C_TEXT_DIM = t["TEXT_DIM"]; C_MUTED = t["MUTED"]
    C_HOVER = t["HOVER"]
    C_SUCCESS = t["SUCCESS"]; C_ERROR = t["ERROR"]; C_WARN = t["WARN"]
    C_INPUT = t["INPUT"]; C_LOG = t["LOG"]


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


class AudioToVideoApp(ctk.CTk):
    """Ventana principal de la aplicación."""

    WINDOW_TITLE = "Audio to Video Studio"
    WINDOW_SIZE = "1280x800"
    MIN_SIZE = (1100, 700)

    def __init__(self) -> None:
        super().__init__()

        self.settings = SettingsManager()
        self._runner: Runner | None = None
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
        self._build_ui()
        self._load_settings_to_ui()

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
        self.configure(fg_color=C_BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(0, lambda: self.state("zoomed"))

    # ──────────────────────────────────────────────────────────────────
    # BUILD UI
    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_main_area()
        # Thin separator between main and footer
        ctk.CTkFrame(self, height=1, fg_color=C_BORDER, corner_radius=0).grid(
            row=2, column=0, sticky="ew"
        )
        self._build_footer()

    # --- Header -------------------------------------------------------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0, height=48)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=0)
        header.grid_columnconfigure(1, weight=0)
        header.grid_columnconfigure(2, weight=1)
        header.grid_columnconfigure(3, weight=0)
        header.grid_rowconfigure(0, weight=1)   # content row fills the fixed height
        header.grid_rowconfigure(1, weight=0)   # separator row stays 1px

        # Barra de acento vertical izquierda (decorativa)
        ctk.CTkFrame(header, width=3, fg_color=C_ACCENT, corner_radius=1).grid(
            row=0, column=0, padx=(14, 0), pady=8, sticky="ns"
        )

        _title_frame = ctk.CTkFrame(header, fg_color="transparent")
        _title_frame.grid(row=0, column=1, padx=(8, 0), sticky="w")
        ctk.CTkLabel(
            _title_frame, text=FA_FILM,
            font=ctk.CTkFont(family=_FA_FAMILY, size=16),
            text_color=C_TEXT,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            _title_frame,
            text="Audio to Video Studio",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=C_TEXT,
        ).pack(side="left")

        self._lbl_status = ctk.CTkLabel(
            header,
            text="Verificando entorno...",
            font=ctk.CTkFont(size=11),
            text_color=C_WARN,
        )
        self._lbl_status.grid(row=0, column=2, padx=12, sticky="e")

        # ── Controles de UI en su propio contenedor visible ──
        ctrl = ctk.CTkFrame(
            header, fg_color=C_CARD, corner_radius=6,
            border_width=1, border_color=C_BORDER,
        )
        ctrl.grid(row=0, column=3, padx=(4, 14))

        # Botón tema (FA sun / moon)
        _theme_icon = FA_SUN if self._current_theme == "Dark" else FA_MOON
        self._btn_theme = ctk.CTkButton(
            ctrl, text=_theme_icon, width=30, height=26,
            fg_color="transparent",
            hover_color=C_HOVER,
            text_color=C_TEXT,
            font=ctk.CTkFont(family=_FA_FAMILY, size=14),
            corner_radius=4,
            command=self._toggle_theme,
        )
        self._btn_theme.pack(side="left", padx=(4, 0), pady=4)

        # Divisor
        ctk.CTkFrame(ctrl, width=1, height=18, fg_color=C_BORDER).pack(side="left", padx=5, pady=4)

        # Botones tamaño de fuente
        for _label, _size in (("A⁻", "Small"), ("A", "Medium"), ("A⁺", "Large")):
            _active = (self._font_scale == _FONT_SIZE_SCALE[_size])
            ctk.CTkButton(
                ctrl,
                text=_label,
                width=30, height=26,
                fg_color=C_ACCENT if _active else "transparent",
                hover_color=C_HOVER,
                text_color=C_TEXT if _active else C_TEXT_DIM,
                border_width=0,
                font=ctk.CTkFont(size=12 if _label == "A" else (10 if _label == "A⁻" else 14)),
                corner_radius=4,
                command=lambda s=_size: self._on_font_size(s),
            ).pack(side="left", padx=2, pady=4)

        # Separador inferior del header
        ctk.CTkFrame(header, height=1, fg_color=C_BORDER, corner_radius=0).grid(
            row=1, column=0, columnspan=4, sticky="ew"
        )

    # --- Main area ----------------------------------------------------

    def _build_main_area(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        main.grid_columnconfigure(0, weight=3, minsize=380)  # 60%
        main.grid_columnconfigure(1, weight=2, minsize=300)  # 40%
        main.grid_rowconfigure(0, weight=1)
        self._main_panel = main

        self._build_left_panel(main)
        self._build_right_panel(main)

    # --- Left panel ---------------------------------------------------

    def _build_left_panel(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkScrollableFrame(parent, fg_color=C_PANEL, corner_radius=8)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        frame.grid_columnconfigure(0, weight=1)
        self._scroll_frame = frame
        row = 0

        # ── Archivos (abierto por defecto) ──
        c, row = self._collapsible_section(frame, "Archivos", row, default_open=True, fa_icon=FA_FOLDER)
        ar = 0
        self._var_audio_folder = tk.StringVar()
        ar = self._file_row(c, "Carpeta de audios:", self._var_audio_folder,
                            self._browse_audio_folder, ar)
        self._var_image = tk.StringVar()
        ar = self._file_row(c, "Imagen de fondo:", self._var_image,
                            self._browse_image, ar)
        self._var_output = tk.StringVar()
        ar = self._file_row(c, "Carpeta de salida:", self._var_output,
                            self._browse_output, ar)

        # ── Resolución ──
        c, row = self._collapsible_section(frame, "Resolución", row, default_open=False, fa_icon=FA_EXPAND)
        self._var_resolution = tk.StringVar(value="1080p")
        res_frame = ctk.CTkFrame(c, fg_color="transparent")
        res_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=4)
        ctk.CTkRadioButton(res_frame, text="720p", variable=self._var_resolution,
                           value="720p").pack(side="left", padx=8)
        ctk.CTkRadioButton(res_frame, text="1080p", variable=self._var_resolution,
                           value="1080p").pack(side="left", padx=8)
        ctk.CTkRadioButton(res_frame, text="4K", variable=self._var_resolution,
                           value="4K").pack(side="left", padx=8)

        # ── Parámetros ──
        c, row = self._collapsible_section(frame, "Parámetros", row, default_open=False, fa_icon=FA_GEAR)
        ar = 0
        self._var_zoom_max = tk.DoubleVar(value=1.02)
        ar = self._slider_row(c, "Zoom máximo:", self._var_zoom_max, 1.0, 1.2, ar,
                              fmt="{:.3f}", number_of_steps=200)
        self._var_zoom_speed = tk.IntVar(value=300)
        ar = self._slider_row(c, "Velocidad zoom:", self._var_zoom_speed, 100, 800, ar,
                              fmt="{:.0f}")
        self._var_fade_in = tk.DoubleVar(value=2.0)
        ar = self._slider_row(c, "Fade in (s):", self._var_fade_in, 0, 10, ar, fmt="{:.1f}")
        self._var_fade_out = tk.DoubleVar(value=2.0)
        ar = self._slider_row(c, "Fade out (s):", self._var_fade_out, 0, 10, ar, fmt="{:.1f}")
        self._var_crf = tk.IntVar(value=18)
        ar = self._slider_row(
            c, "Calidad CRF:", self._var_crf, 0, 51, ar, fmt="{:.0f}",
            tooltip_text=(
                "CRF (Constant Rate Factor) — controla la calidad del video.\n\n"
                "• 0  → Lossless (sin pérdida). Archivo enorme.\n"
                "• 18 → Alta calidad (recomendado). Buen balance.\n"
                "• 23 → Calidad media. Archivo más liviano.\n"
                "• 28 → Baja calidad. Solo para pruebas.\n"
                "• 51 → La peor calidad posible.\n\n"
                "Menor número = mejor imagen, archivo más grande.\n"
                "Mayor número = imagen peor, archivo más pequeño."
            ),
        )

        # ── Efectos visuales ──
        c, row = self._collapsible_section(frame, "Efectos visuales", row, default_open=False, fa_icon=FA_WAND)
        ar = 0
        self._var_zoom = tk.BooleanVar(value=True)
        self._var_glitch = tk.BooleanVar(value=False)
        self._var_overlay = tk.BooleanVar(value=False)
        self._var_normalize = tk.BooleanVar(value=False)
        ar = self._check_row(c, "Zoom dinámico", self._var_zoom, ar)
        ar = self._check_row(c, "Glitch effect (video)", self._var_glitch, ar)

        # Sub-frame glitch: sliders de intensidad y velocidad
        self._glitch_settings_frame = ctk.CTkFrame(c, fg_color="transparent")
        self._glitch_settings_frame.grid(row=ar, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._glitch_settings_frame.grid_columnconfigure(0, weight=1)
        self._var_glitch_intensity = tk.IntVar(value=4)
        self._var_glitch_speed = tk.IntVar(value=90)
        self._var_glitch_pulse = tk.IntVar(value=3)
        ar_g = 0
        ar_g = self._slider_row(self._glitch_settings_frame, "Intensidad:",
                                self._var_glitch_intensity, 1, 20, ar_g, fmt="{:.0f}")
        ar_g = self._slider_row(self._glitch_settings_frame, "Frecuencia (frames):",
                                self._var_glitch_speed, 20, 300, ar_g, fmt="{:.0f}")
        ar_g = self._slider_row(self._glitch_settings_frame, "Duración pulso:",
                                self._var_glitch_pulse, 1, 10, ar_g, fmt="{:.0f}")
        if not self._var_glitch.get():
            self._glitch_settings_frame.grid_remove()
        self._var_glitch.trace_add("write", lambda *_: (
            self._glitch_settings_frame.grid() if self._var_glitch.get()
            else self._glitch_settings_frame.grid_remove()
        ))
        ar += 1  # ya contado el row del checkbox
        ar = self._check_row(c, "Overlay animado (video)", self._var_overlay,
                             ar, command=self._toggle_overlay_widgets)
        ar = self._check_row(c, "Normalizar audio", self._var_normalize, ar)

        # Sub-frame overlay: visible solo cuando se activa
        self._overlay_frame = ctk.CTkFrame(c, fg_color="transparent")
        self._overlay_frame.grid(row=ar, column=0, sticky="ew", padx=12)
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
                      variable=self._var_overlay_opacity, width=80).pack(side="left")
        self._overlay_frame.grid_remove()

        # ── Texto overlay ──
        c, row = self._collapsible_section(frame, "Texto overlay", row, default_open=False, fa_icon=FA_FONT_IC)
        ar = 0
        self._var_text_overlay = tk.BooleanVar(value=False)
        ar = self._check_row(c, "Activar texto overlay", self._var_text_overlay,
                             ar, command=self._toggle_text_overlay_widgets)

        # Contenedor interior con fondo sutil
        self._text_overlay_frame = ctk.CTkFrame(
            c, fg_color=C_PANEL, corner_radius=6,
            border_width=1, border_color=C_BORDER,
        )
        self._text_overlay_frame.grid(row=ar, column=0, sticky="ew", padx=8, pady=(0, 6))
        self._text_overlay_frame.grid_columnconfigure(0, weight=1)
        tof = 0

        # Texto
        ctk.CTkLabel(self._text_overlay_frame, text="Texto:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), anchor="w").grid(
            row=tof, column=0, sticky="w", padx=10, pady=(8, 0))
        tof += 1
        self._var_text_content = tk.StringVar()
        ctk.CTkEntry(self._text_overlay_frame, textvariable=self._var_text_content,
                     placeholder_text="Ej: Lo-Fi Beats ♪", height=28).grid(
            row=tof, column=0, sticky="ew", padx=10, pady=(2, 6))
        tof += 1

        # Fuente
        font_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        font_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        font_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(font_f, text="Fuente:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").grid(row=0, column=0)
        _fonts = available_fonts() or ["Arial"]
        self._var_text_font = tk.StringVar(value=_fonts[0])
        ctk.CTkOptionMenu(font_f, variable=self._var_text_font, values=_fonts,
                          width=160, height=28,
                          font=ctk.CTkFont(size=self._fs(11))).grid(
            row=0, column=1, sticky="w", padx=4)
        tof += 1

        # Posición
        pos_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        pos_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(pos_f, text="Posición:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=70, anchor="w").pack(side="left")
        self._var_text_position = tk.StringVar(value="Bottom")
        for _pos in ("Top", "Middle", "Bottom"):
            ctk.CTkRadioButton(pos_f, text=_pos, variable=self._var_text_position,
                               value=_pos, font=ctk.CTkFont(size=self._fs(11))).pack(side="left", padx=6)
        tof += 1

        # Margen desde el borde
        m_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        m_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        m_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(m_f, text="Margen (px):", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_margin = tk.IntVar(value=40)
        _m_lbl = ctk.CTkLabel(m_f, text="40", text_color=C_TEXT,
                              font=ctk.CTkFont(size=self._fs(11)), width=40)
        _m_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(m_f, from_=10, to=200, variable=self._var_text_margin,
                      command=lambda v: _m_lbl.configure(text=f"{int(float(v))}")).grid(
            row=0, column=1, sticky="ew", padx=4)
        tof += 1

        # Tamaño de fuente
        fs_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        fs_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        fs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(fs_f, text="Tamaño fuente:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_font_size = tk.IntVar(value=36)
        _fs_lbl = ctk.CTkLabel(fs_f, text="36", text_color=C_TEXT,
                               font=ctk.CTkFont(size=self._fs(11)), width=40)
        _fs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(fs_f, from_=12, to=120, variable=self._var_text_font_size,
                      command=lambda v: _fs_lbl.configure(text=f"{int(float(v))}")).grid(
            row=0, column=1, sticky="ew", padx=4)
        tof += 1

        # Intensidad glitch (píxeles de desplazamiento, 0 = sin glitch)
        gi_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        gi_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        gi_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(gi_f, text="Glitch (px):", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_glitch_intensity = tk.IntVar(value=3)
        _gi_lbl = ctk.CTkLabel(gi_f, text="3", text_color=C_TEXT,
                               font=ctk.CTkFont(size=self._fs(11)), width=40)
        _gi_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(gi_f, from_=0, to=20, variable=self._var_text_glitch_intensity,
                      command=lambda v: _gi_lbl.configure(text=f"{int(float(v))}")).grid(
            row=0, column=1, sticky="ew", padx=4)
        tof += 1

        # Velocidad de la animación glitch
        gs_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        gs_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=(2, 8))
        gs_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(gs_f, text="Velocidad glitch:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_glitch_speed = tk.DoubleVar(value=4.0)
        _gs_lbl = ctk.CTkLabel(gs_f, text="4.0", text_color=C_TEXT,
                               font=ctk.CTkFont(size=self._fs(11)), width=40)
        _gs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(gs_f, from_=0.5, to=20.0, variable=self._var_text_glitch_speed,
                      command=lambda v: _gs_lbl.configure(text=f"{float(v):.1f}")).grid(
            row=0, column=1, sticky="ew", padx=4)

        self._text_overlay_frame.grid_remove()

        # ── Presets ──
        c, row = self._collapsible_section(frame, "Presets", row, default_open=False, fa_icon=FA_SLIDERS)
        self._preset_container = ctk.CTkFrame(c, fg_color="transparent")
        self._preset_container.grid(row=0, column=0, sticky="ew", padx=6, pady=2)
        self._preset_container.grid_columnconfigure(0, weight=1)

        # Tiles grid
        self._preset_tiles_frame = ctk.CTkFrame(
            self._preset_container, fg_color="transparent",
        )
        self._preset_tiles_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        # "+ Nuevo preset" button
        _plus_frame = ctk.CTkFrame(self._preset_container, fg_color=C_BTN_SECONDARY, corner_radius=6)
        _plus_frame.grid(row=1, column=0, sticky="ew", padx=6)
        _plus_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            _plus_frame, text=FA_PLUS, width=24,
            font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(12)),
            text_color=C_TEXT,
        ).grid(row=0, column=0, padx=(10, 0), pady=6)
        ctk.CTkButton(
            _plus_frame, text="Nuevo preset", height=30,
            fg_color="transparent", hover_color=C_HOVER,
            text_color=C_TEXT, corner_radius=6, anchor="w",
            font=ctk.CTkFont(size=self._fs(11)),
            command=self._create_new_preset,
        ).grid(row=0, column=1, sticky="ew", padx=(0, 4), pady=2)

        self._rebuild_preset_tiles()

        # ── Output Naming ──
        c, row = self._collapsible_section(frame, "Nombre de salida", row, default_open=False, fa_icon=FA_TAG)
        ar = 0
        inner_mode = ctk.CTkFrame(c, fg_color="transparent")
        inner_mode.grid(row=ar, column=0, sticky="ew", padx=12, pady=4)
        inner_mode.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            inner_mode, text="Modo:", text_color=C_MUTED,
            font=ctk.CTkFont(size=self._fs(11)), width=60, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._var_naming_mode = tk.StringVar(value="Default")
        ctk.CTkOptionMenu(
            inner_mode,
            values=["Default", "Prefijo", "Lista personalizada", "Prefijo + Lista personalizada"],
            variable=self._var_naming_mode,
            command=self._on_naming_mode_change,
            fg_color=C_CARD,
            button_color=C_ACCENT if self._current_theme == "Dark" else C_BORDER,
            text_color=C_TEXT,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ar += 1

        self._naming_prefix_frame = ctk.CTkFrame(c, fg_color="transparent")
        self._naming_prefix_frame.grid(row=ar, column=0, sticky="ew", padx=12, pady=(2, 0))
        self._naming_prefix_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self._naming_prefix_frame, text="Prefijo:", text_color=C_MUTED,
            font=ctk.CTkFont(size=self._fs(11)), width=60, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._var_naming_prefix = tk.StringVar()
        ctk.CTkEntry(
            self._naming_prefix_frame,
            textvariable=self._var_naming_prefix,
            placeholder_text="Ej: Lofi - ",
            height=28,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self._naming_prefix_frame.grid_remove()
        ar += 1

        self._naming_list_frame = ctk.CTkFrame(c, fg_color="transparent")
        self._naming_list_frame.grid(row=ar, column=0, sticky="ew", padx=12, pady=(4, 0))
        self._naming_list_frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self._naming_list_frame,
            text="Nombres personalizados (uno por línea):",
            text_color=C_MUTED,
            font=ctk.CTkFont(size=self._fs(11)),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 2))
        self._txt_naming_list = ctk.CTkTextbox(
            self._naming_list_frame,
            height=90,
            fg_color=C_INPUT,
            text_color=C_TEXT,
            font=ctk.CTkFont(family="Consolas", size=self._fs(11)),
        )
        self._txt_naming_list.grid(row=1, column=0, sticky="ew")
        self._naming_list_frame.grid_remove()
        ar += 1

        self._var_naming_autonumber = tk.BooleanVar(value=True)
        ar = self._check_row(c, "Numeración automática (01, 02…)",
                             self._var_naming_autonumber, ar)

        # ── Rendimiento ──
        c, row = self._collapsible_section(frame, "Rendimiento", row, default_open=False, fa_icon=FA_BOLT)
        inner_perf = ctk.CTkFrame(c, fg_color="transparent")
        inner_perf.grid(row=0, column=0, sticky="ew", padx=12, pady=4)
        inner_perf.grid_columnconfigure(1, weight=1)
        inner_perf.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(
            inner_perf, text="CPU:", text_color=C_MUTED,
            font=ctk.CTkFont(size=self._fs(11)), width=40, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._var_cpu_mode = tk.StringVar(value="Medium")
        ctk.CTkOptionMenu(
            inner_perf,
            values=["Low", "Medium", "High", "Max"],
            variable=self._var_cpu_mode,
            fg_color=C_CARD,
            button_color=C_ACCENT if self._current_theme == "Dark" else C_BORDER,
            text_color=C_TEXT,
            width=100,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 2))
        _cpu_btn = ctk.CTkButton(
            inner_perf, text="?", width=28, height=28,
            fg_color=C_ACCENT, hover_color=C_ACCENT_H,
            text_color="#ffffff",
            font=ctk.CTkFont(size=self._fs(11), weight="bold"),
            corner_radius=4,
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
        ctk.CTkLabel(
            inner_perf, text="Preset:", text_color=C_MUTED,
            font=ctk.CTkFont(size=self._fs(11)), width=50, anchor="w",
        ).grid(row=0, column=3, sticky="w")
        self._var_encode_preset = tk.StringVar(value="slow")
        ctk.CTkOptionMenu(
            inner_perf,
            values=["ultrafast", "superfast", "veryfast",
                    "faster", "fast", "medium", "slow", "slower", "veryslow"],
            variable=self._var_encode_preset,
            fg_color=C_CARD,
            button_color=C_ACCENT if self._current_theme == "Dark" else C_BORDER,
            text_color=C_TEXT,
            width=100,
        ).grid(row=0, column=4, sticky="ew", padx=(4, 2))
        _preset_btn = ctk.CTkButton(
            inner_perf, text="?", width=28, height=28,
            fg_color=C_ACCENT, hover_color=C_ACCENT_H,
            text_color="#ffffff",
            font=ctk.CTkFont(size=self._fs(11), weight="bold"),
            corner_radius=4,
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
        # --- Fila 2: GPU encoding toggle ---
        inner_gpu = ctk.CTkFrame(c, fg_color="transparent")
        inner_gpu.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 4))
        inner_gpu.grid_columnconfigure(1, weight=1)

        self._var_gpu_encoding = tk.BooleanVar(value=False)
        ctk.CTkSwitch(
            inner_gpu,
            text="GPU Encoding (NVENC)",
            variable=self._var_gpu_encoding,
            font=ctk.CTkFont(size=self._fs(11)),
            text_color=C_TEXT,
            progress_color=C_ACCENT,
            button_color=C_BORDER,
            button_hover_color=C_ACCENT_H,
        ).grid(row=0, column=0, sticky="w")
        _gpu_btn = ctk.CTkButton(
            inner_gpu, text="?", width=28, height=28,
            fg_color=C_ACCENT, hover_color=C_ACCENT_H,
            text_color="#ffffff",
            font=ctk.CTkFont(size=self._fs(11), weight="bold"),
            corner_radius=4,
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
            c,
            text=f"CPU detectados: {_cpu_total} núcleos",
            text_color=C_MUTED,
            font=ctk.CTkFont(size=self._fs(10)),
            anchor="w",
        ).grid(row=2, column=0, sticky="w", padx=14, pady=(0, 6))

    # --- Right panel --------------------------------------------------

    def _build_right_panel(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(parent, fg_color=C_PANEL, corner_radius=8)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)

        # Preview imagen
        preview_frame = ctk.CTkFrame(
            frame, fg_color=C_CARD, corner_radius=6, height=280,
            border_width=1, border_color=C_BORDER,
        )
        preview_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        preview_frame.grid_propagate(False)
        preview_frame.grid_columnconfigure(0, weight=1)
        preview_frame.grid_rowconfigure(0, weight=1)

        self._lbl_preview = ctk.CTkLabel(
            preview_frame,
            text="Sin imagen seleccionada",
            text_color=C_MUTED,
            font=ctk.CTkFont(size=12),
        )
        self._lbl_preview.grid(row=0, column=0, sticky="nsew")

        # Info de audios detectados (pegado justo debajo del preview)
        self._lbl_audio_count = ctk.CTkLabel(
            frame,
            text="Audios: —",
            font=ctk.CTkFont(size=self._fs(11)),
            text_color=C_MUTED,
        )
        self._lbl_audio_count.grid(row=1, column=0, sticky="w", padx=14, pady=(2, 0))

        # Logs
        _logs_hdr = ctk.CTkFrame(frame, fg_color="transparent")
        _logs_hdr.grid(row=2, column=0, sticky="w", padx=12, pady=(8, 2))
        ctk.CTkLabel(
            _logs_hdr, text=FA_LIST,
            font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(13)),
            text_color=C_TEXT,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkLabel(
            _logs_hdr, text="Logs",
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
            text_color=C_TEXT,
        ).pack(side="left")

        self._log_text = ctk.CTkTextbox(
            frame,
            fg_color=C_LOG,
            text_color="#b0efc0",
            font=ctk.CTkFont(family="Consolas", size=self._fs(11)),
            wrap="word",
            state="disabled",
        )
        self._log_text.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 6))
        frame.grid_rowconfigure(3, weight=1)

        # Progreso global
        self._lbl_progress_global = ctk.CTkLabel(
            frame, text="Progreso: —", font=ctk.CTkFont(size=self._fs(11)), text_color=C_MUTED
        )
        self._lbl_progress_global.grid(row=4, column=0, sticky="w", padx=12)

        self._progress_global = ctk.CTkProgressBar(frame, mode="determinate")
        self._progress_global.set(0)
        self._progress_global.grid(row=5, column=0, sticky="ew", padx=10, pady=(2, 2))

        # Progreso por archivo
        self._lbl_progress_file = ctk.CTkLabel(
            frame, text="", font=ctk.CTkFont(size=self._fs(10)), text_color=C_MUTED
        )
        self._lbl_progress_file.grid(row=6, column=0, sticky="w", padx=12)

        self._progress_file = ctk.CTkProgressBar(frame, mode="indeterminate", height=8)
        self._progress_file.grid(row=7, column=0, sticky="ew", padx=10, pady=(0, 6))
        self._progress_file.stop()

    # --- Footer -------------------------------------------------------

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=C_PANEL, corner_radius=0, height=64)
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_propagate(False)
        footer.grid_columnconfigure(4, weight=1)

        _gen_frame = ctk.CTkFrame(footer, fg_color=C_BTN_PRIMARY, corner_radius=6)
        _gen_frame.grid(row=0, column=0, padx=12, pady=14)
        ctk.CTkLabel(
            _gen_frame, text=FA_PLAY, width=20,
            font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(12)),
            text_color="#ffffff",
        ).pack(side="left", padx=(10, 0), pady=6)
        self._btn_generate = ctk.CTkButton(
            _gen_frame,
            text="Generar videos",
            fg_color="transparent",
            hover_color=C_ACCENT_H,
            text_color="#ffffff",
            font=ctk.CTkFont(size=self._fs(13), weight="bold"),
            corner_radius=6,
            height=36,
            command=self._on_generate,
        )
        self._btn_generate.pack(side="left", padx=(2, 6), pady=4)

        _can_frame = ctk.CTkFrame(footer, fg_color=C_BTN_SECONDARY, corner_radius=6)
        _can_frame.grid(row=0, column=1, padx=4, pady=14)
        ctk.CTkLabel(
            _can_frame, text=FA_STOP, width=20,
            font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(12)),
            text_color=C_TEXT_DIM,
        ).pack(side="left", padx=(10, 0), pady=6)
        self._btn_cancel = ctk.CTkButton(
            _can_frame,
            text="Cancelar",
            fg_color="transparent",
            hover_color=C_HOVER,
            text_color=C_TEXT,
            corner_radius=6,
            height=36,
            state="disabled",
            command=self._on_cancel,
        )
        self._btn_cancel.pack(side="left", padx=(2, 6), pady=4)

        _prev_frame = ctk.CTkFrame(footer, fg_color=C_BTN_SECONDARY, corner_radius=6)
        _prev_frame.grid(row=0, column=2, padx=4, pady=14)
        ctk.CTkLabel(
            _prev_frame, text=FA_EYE, width=20,
            font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(12)),
            text_color=C_TEXT,
        ).pack(side="left", padx=(10, 0), pady=6)
        self._btn_preview = ctk.CTkButton(
            _prev_frame,
            text="Preview efecto",
            fg_color="transparent",
            hover_color=C_HOVER,
            text_color=C_TEXT,
            corner_radius=6,
            height=36,
            command=self._on_preview,
        )
        self._btn_preview.pack(side="left", padx=(2, 6), pady=4)

        _test_frame = ctk.CTkFrame(footer, fg_color=C_BTN_SECONDARY, corner_radius=6)
        _test_frame.grid(row=0, column=3, padx=4, pady=14)
        ctk.CTkLabel(
            _test_frame, text=FA_WRENCH, width=20,
            font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(12)),
            text_color=C_TEXT,
        ).pack(side="left", padx=(10, 0), pady=6)
        self._btn_test = ctk.CTkButton(
            _test_frame,
            text="Probar FFmpeg",
            fg_color="transparent",
            hover_color=C_HOVER,
            text_color=C_TEXT,
            corner_radius=6,
            height=36,
            command=self._on_test_ffmpeg,
        )
        self._btn_test.pack(side="left", padx=(2, 6), pady=4)

        _save_frame = ctk.CTkFrame(
            footer, fg_color="transparent", corner_radius=6,
            border_width=1, border_color=C_BORDER,
        )
        _save_frame.grid(row=0, column=5, padx=(4, 12), pady=14, sticky="e")
        ctk.CTkLabel(
            _save_frame, text=FA_SAVE, width=20,
            font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(12)),
            text_color=C_TEXT,
        ).pack(side="left", padx=(10, 0), pady=6)
        ctk.CTkButton(
            _save_frame,
            text="Guardar config",
            fg_color="transparent",
            hover_color=C_HOVER,
            text_color=C_TEXT,
            corner_radius=6,
            height=36,
            command=self._save_settings,
        ).pack(side="left", padx=(2, 6), pady=4)

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

        if fa_icon:
            _hdr = ctk.CTkFrame(parent, fg_color="transparent")
            _hdr.grid(row=row, column=0, sticky="ew", padx=8, pady=(2, 0))
            _hdr.grid_columnconfigure(1, weight=1)
            _fa_lbl = ctk.CTkLabel(
                _hdr, text=fa_icon, width=22,
                font=ctk.CTkFont(family=_FA_FAMILY, size=self._fs(13)),
                text_color=C_TEXT,
            )
            _fa_lbl.grid(row=0, column=0, padx=(6, 0))
            btn = ctk.CTkButton(
                _hdr,
                text=f"{'\u25bc' if default_open else '\u25b6'}  {title}",
                anchor="w",
                fg_color="transparent",
                hover_color=C_HOVER,
                text_color=C_TEXT,
                font=ctk.CTkFont(size=self._fs(12), weight="bold"),
                height=34,
                corner_radius=6,
            )
            btn.grid(row=0, column=1, sticky="ew")
        else:
            btn = ctk.CTkButton(
                parent,
                text=f"{'\u25bc' if default_open else '\u25b6'}  {title}",
                anchor="w",
                fg_color="transparent",
                hover_color=C_HOVER,
                text_color=C_TEXT,
                font=ctk.CTkFont(size=self._fs(12), weight="bold"),
                height=34,
                corner_radius=6,
            )
            btn.grid(row=row, column=0, sticky="ew", padx=8, pady=(2, 0))

        card = ctk.CTkFrame(
            parent,
            fg_color=C_CARD,
            corner_radius=8,
            border_width=1,
            border_color=C_BORDER,
        )
        card.grid_columnconfigure(0, weight=1)
        card.grid(row=row + 1, column=0, sticky="ew", padx=8, pady=(0, 0))
        ctk.CTkFrame(card, height=8, fg_color="transparent").grid(row=0, column=0, sticky="ew")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.grid(row=1, column=0, sticky="ew")
        inner.grid_columnconfigure(0, weight=1)
        ctk.CTkFrame(card, height=8, fg_color="transparent").grid(row=2, column=0, sticky="ew")

        def _toggle() -> None:
            if _open[0]:
                card.grid_remove()
                btn.configure(text=f"\u25b6  {_title}")
                _open[0] = False
            else:
                card.grid()
                btn.configure(text=f"\u25bc  {_title}")
                _open[0] = True

        if not default_open:
            card.grid_remove()
        btn.configure(command=_toggle)
        if _fa_lbl:
            _fa_lbl.bind("<Button-1>", lambda e: _toggle())
        return inner, row + 2

    def _file_row(
        self,
        parent: Any,
        label: str,
        var: tk.StringVar,
        command: Any,
        row: int,
    ) -> int:
        ctk.CTkLabel(parent, text=label, text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), anchor="w").grid(
            row=row, column=0, sticky="ew", padx=12, pady=(10, 2)
        )
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.grid(row=row + 1, column=0, sticky="ew", padx=12, pady=(2, 10))
        inner.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(inner, textvariable=var, height=30).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ctk.CTkButton(
            inner, text="...", width=40, height=30,
            fg_color=C_ACCENT, hover_color=C_ACCENT_H,
            text_color="#ffffff", corner_radius=4,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=command,
        ).grid(row=0, column=1)
        return row + 2

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
    ) -> int:
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.grid(row=row, column=0, sticky="ew", padx=12, pady=(8, 8))
        inner.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(inner, text=label, text_color=C_MUTED,
                     font=ctk.CTkFont(size=self._fs(11)), width=120, anchor="w").grid(
            row=0, column=0, sticky="w"
        )

        val_label = ctk.CTkLabel(inner, text=fmt.format(var.get()),
                                 text_color=C_TEXT, font=ctk.CTkFont(size=self._fs(11)), width=50)
        val_label.grid(row=0, column=2, padx=(4, 0))

        def _update(v: str) -> None:
            try:
                val_label.configure(text=fmt.format(float(v)))
            except ValueError:
                pass

        slider_kwargs: dict = dict(
            from_=from_, to=to, variable=var, command=_update,
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
        _apply_theme(new_theme)
        ctk.set_appearance_mode(new_theme)
        self.configure(fg_color=C_BG)
        for w in self.winfo_children():
            w.destroy()
        self._build_ui()
        self._load_settings_to_ui()
        self.after(200, self._run_validation)

    def _on_font_size(self, size: str) -> None:
        """Cambia la escala de fuente y reconstruye el panel izquierdo."""
        self._collect_settings()
        self._font_scale = _FONT_SIZE_SCALE.get(size, 1.0)
        self.settings.update({"font_size": size})
        if hasattr(self, "_scroll_frame"):
            self._scroll_frame.destroy()
        self._build_left_panel(self._main_panel)
        self._load_settings_to_ui()
        if hasattr(self, "_log_text"):
            self._log_text.configure(font=ctk.CTkFont(family="Consolas", size=self._fs(11)))

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

    def _on_naming_mode_change(self, mode: str) -> None:
        """Muestra u oculta el campo de prefijo y/o la lista según el modo elegido."""
        needs_prefix = mode in ("Prefix", "Prefix + Custom List")
        needs_list = mode in ("Custom List", "Prefix + Custom List")

        if needs_prefix:
            self._naming_prefix_frame.grid()
        else:
            self._naming_prefix_frame.grid_remove()

        if needs_list:
            self._naming_list_frame.grid()
        else:
            self._naming_list_frame.grid_remove()

    def _apply_preset(self, name: str) -> None:
        self.settings.apply_preset(name)
        self._load_settings_to_ui()
        self._log(f"🎛 Preset '{name}' aplicado.")

    # ------------------------------------------------------------------
    # Preset management — tiles
    # ------------------------------------------------------------------

    def _rebuild_preset_tiles(self) -> None:
        """Reconstruye los tiles de presets en grid de 2 columnas."""
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

    def _update_audio_count(self, folder: str) -> None:
        try:
            files = get_audio_files(folder)
            self._lbl_audio_count.configure(
                text=f"Audios detectados: {len(files)} archivo(s)",
                text_color=C_SUCCESS if files else C_WARN,
            )
        except Exception:
            self._lbl_audio_count.configure(text="Audios: error leyendo carpeta",
                                             text_color=C_ERROR)

    def _load_preview(self, path: str) -> None:
        try:
            img = Image.open(path)
            img.thumbnail((500, 270))
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self._lbl_preview.configure(image=ctk_img, text="")
            self._lbl_preview.image = ctk_img  # evitar GC
        except Exception as exc:
            self._lbl_preview.configure(image=None, text=f"No se pudo cargar: {exc}")

    # ──────────────────────────────────────────────────────────────────
    # ACCIONES PRINCIPALES
    # ──────────────────────────────────────────────────────────────────

    def _on_generate(self) -> None:
        if not self._validate_inputs():
            return

        self._collect_settings()
        self._set_processing_state(True)
        self._clear_log()

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
            image_path=self._var_image.get(),
            output_folder=self._var_output.get(),
        )

    def _on_cancel(self) -> None:
        if self._runner:
            self._runner.cancel()
        self._btn_cancel.configure(state="disabled")

    def _on_preview(self) -> None:
        if not self._var_image.get() or not self._var_audio_folder.get():
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
                    image_path=self._var_image.get(),
                    output_path=output,
                    duration=dur,
                )
                import subprocess
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
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
        self.after(0, self._set_processing_state, False)

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
        result = validate_environment()
        for msg in result.messages:
            self._log(msg)

        if result.ok:
            self._lbl_status.configure(text="✔ Entorno OK", text_color=C_SUCCESS)
        else:
            self._lbl_status.configure(text="✘ Dependencias faltantes", text_color=C_ERROR)
            self._btn_generate.configure(state="disabled")
            self._btn_preview.configure(state="disabled")
            messagebox.showerror(
                "Dependencias faltantes",
                "Se encontraron problemas con las dependencias del sistema.\n"
                "Revisa el área de logs para más detalles.",
            )

    def _validate_inputs(self) -> bool:
        errors: list[str] = []

        audio_folder = self._var_audio_folder.get()
        if not audio_folder or not Path(audio_folder).is_dir():
            errors.append("• Carpeta de audios no válida.")

        image_path = self._var_image.get()
        if not image_path or not Path(image_path).is_file():
            errors.append("• Imagen de fondo no válida.")

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
        if naming_mode in ("Custom List", "Prefix + Custom List"):
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
            "zoom_max": round(self._var_zoom_max.get(), 4),
            "zoom_speed": int(self._var_zoom_speed.get()),
            "fade_in": round(self._var_fade_in.get(), 2),
            "fade_out": round(self._var_fade_out.get(), 2),
            "crf": int(self._var_crf.get()),
            "resolution": self._var_resolution.get(),
            "enable_zoom": self._var_zoom.get(),
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
            "naming_prefix": self._var_naming_prefix.get(),
            "naming_custom_list": custom_names,
            "naming_auto_number": self._var_naming_autonumber.get(),
            # Performance
            "cpu_mode": self._var_cpu_mode.get(),
            "encode_preset": self._var_encode_preset.get(),
            "gpu_encoding": self._var_gpu_encoding.get(),
            # Text overlay
            "enable_text_overlay": self._var_text_overlay.get(),
            "text_content": self._var_text_content.get(),
            "text_position": self._var_text_position.get(),
            "text_margin": int(self._var_text_margin.get()),
            "text_font_size": int(self._var_text_font_size.get()),
            "text_font": self._var_text_font.get(),
            "text_glitch_intensity": int(self._var_text_glitch_intensity.get()),
            "text_glitch_speed": round(self._var_text_glitch_speed.get(), 1),
            # UI
            "theme": self._current_theme,
            "font_size": next(
                (k for k, v in _FONT_SIZE_SCALE.items() if abs(v - self._font_scale) < 0.01),
                "Medium",
            ),
        })

    def _load_settings_to_ui(self) -> None:
        """Carga la configuración guardada en los widgets de la UI."""
        s = self.settings.all()
        self._var_audio_folder.set(s.get("audio_folder", ""))
        self._var_image.set(s.get("background_image", ""))
        self._var_output.set(s.get("output_folder", ""))
        self._var_zoom_max.set(s.get("zoom_max", 1.02))
        self._var_zoom_speed.set(s.get("zoom_speed", 300))
        self._var_fade_in.set(s.get("fade_in", 2.0))
        self._var_fade_out.set(s.get("fade_out", 2.0))
        self._var_crf.set(s.get("crf", 18))
        self._var_resolution.set(s.get("resolution", "1080p"))
        self._var_zoom.set(s.get("enable_zoom", True))
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
        self._var_naming_prefix.set(s.get("naming_prefix", ""))
        custom_names: list[str] = s.get("naming_custom_list", [])
        self._txt_naming_list.delete("1.0", "end")
        if custom_names:
            self._txt_naming_list.insert("1.0", "\n".join(custom_names))
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
        self._var_text_glitch_intensity.set(s.get("text_glitch_intensity", 3))
        self._var_text_glitch_speed.set(s.get("text_glitch_speed", 4.0))
        self._toggle_text_overlay_widgets()
        # theme/font_size se cargan en __init__ antes de construir la UI

        # Cargar preview si hay imagen
        img = s.get("background_image", "")
        if img and Path(img).is_file():
            self._load_preview(img)

        # Actualizar conteo de audios
        audio = s.get("audio_folder", "")
        if audio and Path(audio).is_dir():
            self._update_audio_count(audio)

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
            self._btn_preview.configure(state="disabled")
        else:
            self._btn_generate.configure(state="normal")
            self._btn_cancel.configure(state="disabled")
            self._btn_preview.configure(state="normal")
            self._progress_file.stop()
            self._progress_file.set(0)
            self._lbl_progress_file.configure(text="")

    # ──────────────────────────────────────────────────────────────────
    # CIERRE
    # ──────────────────────────────────────────────────────────────────

    def _on_close(self) -> None:
        if self._runner and self._runner.is_running():
            if not messagebox.askyesno(
                "Salir",
                "Hay un proceso en ejecución. ¿Deseas cancelarlo y salir?",
            ):
                return
            self._runner.cancel()

        self._collect_settings()
        try:
            self.settings.save()
        except Exception:
            pass
        self.destroy()


