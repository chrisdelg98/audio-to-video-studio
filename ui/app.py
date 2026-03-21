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


# ── Tema ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Paleta de colores
C_BG = "#1a1a2e"
C_PANEL = "#16213e"
C_ACCENT = "#0f3460"
C_BTN_PRIMARY = "#e94560"
C_BTN_SECONDARY = "#0f3460"
C_BTN_OK = "#2d6a4f"
C_TEXT = "#e0e0e0"
C_MUTED = "#888"
C_SUCCESS = "#52b788"
C_ERROR = "#e63946"
C_WARN = "#f4a261"


class _Tooltip:
    """Ventana flotante que aparece al pasar el mouse sobre un widget."""

    _BG = "#1e2a3a"
    _FG = "#dce8f5"

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._win: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show)
        widget.bind("<Leave>", self._hide)

    def _show(self, _event: object = None) -> None:
        if self._win:
            return
        wx = self._widget.winfo_rootx() + self._widget.winfo_width() + 8
        wy = self._widget.winfo_rooty()
        self._win = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.configure(bg=self._BG)
        tw.wm_geometry(f"+{wx}+{wy}")
        tk.Label(
            tw,
            text=self._text,
            justify="left",
            bg=self._BG,
            fg=self._FG,
            font=("Segoe UI", 10),
            wraplength=300,
            padx=10,
            pady=8,
            relief="flat",
            bd=0,
        ).pack()
        # Borde exterior
        tw.configure(highlightbackground="#3a5a7a", highlightthickness=1)

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

    # ──────────────────────────────────────────────────────────────────
    # BUILD UI
    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_header()
        self._build_main_area()
        self._build_footer()

    # --- Header -------------------------------------------------------

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=C_ACCENT, corner_radius=0)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="🎬  Audio to Video Studio",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=C_TEXT,
        ).grid(row=0, column=0, padx=20, pady=12, sticky="w")

        self._lbl_status = ctk.CTkLabel(
            header,
            text="Verificando entorno...",
            font=ctk.CTkFont(size=12),
            text_color=C_WARN,
        )
        self._lbl_status.grid(row=0, column=1, padx=20, sticky="e")

    # --- Main area ----------------------------------------------------

    def _build_main_area(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=8, pady=4)
        main.grid_columnconfigure(0, weight=2, minsize=360)
        main.grid_columnconfigure(1, weight=3)
        main.grid_rowconfigure(0, weight=1)

        self._build_left_panel(main)
        self._build_right_panel(main)

    # --- Left panel ---------------------------------------------------

    def _build_left_panel(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkScrollableFrame(parent, fg_color=C_PANEL, corner_radius=8)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        frame.grid_columnconfigure(0, weight=1)
        row = 0

        # ── Archivos ──
        c, row = self._collapsible_section(frame, "📁  Archivos", row)
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
        c, row = self._collapsible_section(frame, "📐  Resolución", row)
        self._var_resolution = tk.StringVar(value="1080p")
        res_frame = ctk.CTkFrame(c, fg_color="transparent")
        res_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=4)
        ctk.CTkRadioButton(res_frame, text="1080p", variable=self._var_resolution,
                           value="1080p").pack(side="left", padx=8)
        ctk.CTkRadioButton(res_frame, text="4K", variable=self._var_resolution,
                           value="4K").pack(side="left", padx=8)

        # ── Parámetros ──
        c, row = self._collapsible_section(frame, "⚙️  Parámetros", row)
        ar = 0
        self._var_zoom_max = tk.DoubleVar(value=1.05)
        ar = self._slider_row(c, "Zoom máximo:", self._var_zoom_max, 1.0, 1.2, ar,
                              fmt="{:.3f}")
        self._var_zoom_speed = tk.IntVar(value=300)
        ar = self._slider_row(c, "Velocidad zoom:", self._var_zoom_speed, 50, 1000, ar,
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
        c, row = self._collapsible_section(frame, "✨  Efectos visuales", row)
        ar = 0
        self._var_zoom = tk.BooleanVar(value=True)
        self._var_glitch = tk.BooleanVar(value=False)
        self._var_overlay = tk.BooleanVar(value=False)
        self._var_normalize = tk.BooleanVar(value=False)
        ar = self._check_row(c, "Zoom dinámico", self._var_zoom, ar)
        ar = self._check_row(c, "Glitch effect (video)", self._var_glitch, ar)
        ar = self._check_row(c, "Overlay animado (video)", self._var_overlay,
                             ar, command=self._toggle_overlay_widgets)
        ar = self._check_row(c, "Normalizar audio", self._var_normalize, ar)

        # Sub-frame overlay: visible solo cuando se activa
        self._overlay_frame = ctk.CTkFrame(c, fg_color="transparent")
        self._overlay_frame.grid(row=ar, column=0, sticky="ew", padx=12)
        self._var_overlay_path = tk.StringVar()
        ctk.CTkLabel(self._overlay_frame, text="Video overlay:",
                     text_color=C_MUTED, font=ctk.CTkFont(size=11)).pack(side="left", padx=4)
        ctk.CTkEntry(self._overlay_frame, textvariable=self._var_overlay_path,
                     width=140).pack(side="left", padx=4)
        ctk.CTkButton(self._overlay_frame, text="...", width=30,
                      command=self._browse_overlay).pack(side="left")
        self._var_overlay_opacity = tk.DoubleVar(value=0.5)
        ctk.CTkLabel(self._overlay_frame, text="Opacidad:",
                     text_color=C_MUTED, font=ctk.CTkFont(size=11)).pack(side="left", padx=(8, 2))
        ctk.CTkSlider(self._overlay_frame, from_=0.0, to=1.0,
                      variable=self._var_overlay_opacity, width=80).pack(side="left")
        self._overlay_frame.grid_remove()

        # ── Texto overlay ──
        c, row = self._collapsible_section(frame, "🔤  Texto overlay", row, default_open=False)
        ar = 0
        self._var_text_overlay = tk.BooleanVar(value=False)
        ar = self._check_row(c, "Activar texto overlay", self._var_text_overlay,
                             ar, command=self._toggle_text_overlay_widgets)

        # Contenedor interior con fondo sutil
        self._text_overlay_frame = ctk.CTkFrame(c, fg_color="#0d1b2a", corner_radius=6)
        self._text_overlay_frame.grid(row=ar, column=0, sticky="ew", padx=8, pady=(0, 6))
        self._text_overlay_frame.grid_columnconfigure(0, weight=1)
        tof = 0

        # Texto
        ctk.CTkLabel(self._text_overlay_frame, text="Texto:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=11), anchor="w").grid(
            row=tof, column=0, sticky="w", padx=10, pady=(8, 0))
        tof += 1
        self._var_text_content = tk.StringVar()
        ctk.CTkEntry(self._text_overlay_frame, textvariable=self._var_text_content,
                     placeholder_text="Ej: Lo-Fi Beats ♪", height=28).grid(
            row=tof, column=0, sticky="ew", padx=10, pady=(2, 6))
        tof += 1

        # Posición
        pos_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        pos_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        ctk.CTkLabel(pos_f, text="Posición:", text_color=C_MUTED,
                     font=ctk.CTkFont(size=11), width=70, anchor="w").pack(side="left")
        self._var_text_position = tk.StringVar(value="Bottom")
        for _pos in ("Top", "Middle", "Bottom"):
            ctk.CTkRadioButton(pos_f, text=_pos, variable=self._var_text_position,
                               value=_pos, font=ctk.CTkFont(size=11)).pack(side="left", padx=6)
        tof += 1

        # Margen desde el borde
        m_f = ctk.CTkFrame(self._text_overlay_frame, fg_color="transparent")
        m_f.grid(row=tof, column=0, sticky="ew", padx=10, pady=2)
        m_f.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(m_f, text="Margen (px):", text_color=C_MUTED,
                     font=ctk.CTkFont(size=11), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_margin = tk.IntVar(value=40)
        _m_lbl = ctk.CTkLabel(m_f, text="40", text_color=C_TEXT,
                              font=ctk.CTkFont(size=11), width=40)
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
                     font=ctk.CTkFont(size=11), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_font_size = tk.IntVar(value=36)
        _fs_lbl = ctk.CTkLabel(fs_f, text="36", text_color=C_TEXT,
                               font=ctk.CTkFont(size=11), width=40)
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
                     font=ctk.CTkFont(size=11), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_glitch_intensity = tk.IntVar(value=3)
        _gi_lbl = ctk.CTkLabel(gi_f, text="3", text_color=C_TEXT,
                               font=ctk.CTkFont(size=11), width=40)
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
                     font=ctk.CTkFont(size=11), width=120, anchor="w").grid(row=0, column=0)
        self._var_text_glitch_speed = tk.DoubleVar(value=4.0)
        _gs_lbl = ctk.CTkLabel(gs_f, text="4.0", text_color=C_TEXT,
                               font=ctk.CTkFont(size=11), width=40)
        _gs_lbl.grid(row=0, column=2, padx=(4, 0))
        ctk.CTkSlider(gs_f, from_=0.5, to=20.0, variable=self._var_text_glitch_speed,
                      command=lambda v: _gs_lbl.configure(text=f"{float(v):.1f}")).grid(
            row=0, column=1, sticky="ew", padx=4)

        self._text_overlay_frame.grid_remove()

        # ── Presets ──
        c, row = self._collapsible_section(frame, "🎛️  Presets", row)
        preset_frame = ctk.CTkFrame(c, fg_color="transparent")
        preset_frame.grid(row=0, column=0, sticky="ew", padx=12, pady=6)
        for preset in SettingsManager.available_presets():
            ctk.CTkButton(
                preset_frame,
                text=preset.capitalize(),
                width=80,
                fg_color=C_BTN_SECONDARY,
                command=lambda p=preset: self._apply_preset(p),
            ).pack(side="left", padx=4)

        # ── Output Naming ──
        c, row = self._collapsible_section(frame, "🏷️  Output Naming", row, default_open=False)
        ar = 0
        inner_mode = ctk.CTkFrame(c, fg_color="transparent")
        inner_mode.grid(row=ar, column=0, sticky="ew", padx=12, pady=4)
        inner_mode.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            inner_mode, text="Modo:", text_color=C_MUTED,
            font=ctk.CTkFont(size=11), width=60, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._var_naming_mode = tk.StringVar(value="Default")
        ctk.CTkOptionMenu(
            inner_mode,
            values=["Default", "Prefix", "Custom List", "Prefix + Custom List"],
            variable=self._var_naming_mode,
            command=self._on_naming_mode_change,
            fg_color=C_ACCENT,
            button_color=C_BTN_SECONDARY,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ar += 1

        self._naming_prefix_frame = ctk.CTkFrame(c, fg_color="transparent")
        self._naming_prefix_frame.grid(row=ar, column=0, sticky="ew", padx=12, pady=(2, 0))
        self._naming_prefix_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            self._naming_prefix_frame, text="Prefijo:", text_color=C_MUTED,
            font=ctk.CTkFont(size=11), width=60, anchor="w",
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
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 2))
        self._txt_naming_list = ctk.CTkTextbox(
            self._naming_list_frame,
            height=90,
            fg_color="#0d1117",
            text_color=C_TEXT,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self._txt_naming_list.grid(row=1, column=0, sticky="ew")
        self._naming_list_frame.grid_remove()
        ar += 1

        self._var_naming_autonumber = tk.BooleanVar(value=True)
        ar = self._check_row(c, "Numeración automática (01, 02…)",
                             self._var_naming_autonumber, ar)

        # ── Performance ──
        c, row = self._collapsible_section(frame, "⚡  Performance", row, default_open=False)
        inner_perf = ctk.CTkFrame(c, fg_color="transparent")
        inner_perf.grid(row=0, column=0, sticky="ew", padx=12, pady=4)
        inner_perf.grid_columnconfigure(1, weight=1)
        inner_perf.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(
            inner_perf, text="CPU:", text_color=C_MUTED,
            font=ctk.CTkFont(size=11), width=40, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._var_cpu_mode = tk.StringVar(value="Medium")
        ctk.CTkOptionMenu(
            inner_perf,
            values=["Low", "Medium", "High", "Max"],
            variable=self._var_cpu_mode,
            fg_color=C_ACCENT,
            button_color=C_BTN_SECONDARY,
            width=100,
        ).grid(row=0, column=1, sticky="ew", padx=(4, 2))
        _cpu_btn = ctk.CTkButton(
            inner_perf, text="?", width=22, height=22,
            fg_color=C_ACCENT, hover_color=C_BTN_SECONDARY,
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=11,
        )
        _cpu_btn.grid(row=0, column=2, padx=(0, 10))
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
            font=ctk.CTkFont(size=11), width=50, anchor="w",
        ).grid(row=0, column=3, sticky="w")
        self._var_encode_preset = tk.StringVar(value="slow")
        ctk.CTkOptionMenu(
            inner_perf,
            values=["ultrafast", "superfast", "veryfast",
                    "faster", "fast", "medium", "slow", "slower", "veryslow"],
            variable=self._var_encode_preset,
            fg_color=C_ACCENT,
            button_color=C_BTN_SECONDARY,
            width=100,
        ).grid(row=0, column=4, sticky="ew", padx=(4, 2))
        _preset_btn = ctk.CTkButton(
            inner_perf, text="?", width=22, height=22,
            fg_color=C_ACCENT, hover_color=C_BTN_SECONDARY,
            font=ctk.CTkFont(size=11, weight="bold"),
            corner_radius=11,
        )
        _preset_btn.grid(row=0, column=5)
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
        _cpu_total = os.cpu_count() or 2
        ctk.CTkLabel(
            c,
            text=f"CPU detectados: {_cpu_total} núcleos",
            text_color=C_MUTED,
            font=ctk.CTkFont(size=10),
            anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 6))

    # --- Right panel --------------------------------------------------

    def _build_right_panel(self, parent: ctk.CTkFrame) -> None:
        frame = ctk.CTkFrame(parent, fg_color=C_PANEL, corner_radius=8)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        # Preview imagen
        preview_frame = ctk.CTkFrame(frame, fg_color=C_ACCENT, corner_radius=6, height=180)
        preview_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
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

        # Info de audios detectados
        self._lbl_audio_count = ctk.CTkLabel(
            frame,
            text="Audios: —",
            font=ctk.CTkFont(size=11),
            text_color=C_MUTED,
        )
        self._lbl_audio_count.grid(row=1, column=0, sticky="w", padx=14, pady=(2, 0))

        # Logs
        log_label = ctk.CTkLabel(frame, text="📋  Logs", font=ctk.CTkFont(size=13, weight="bold"),
                                 text_color=C_TEXT)
        log_label.grid(row=2, column=0, sticky="w", padx=12, pady=(8, 2))

        self._log_text = ctk.CTkTextbox(
            frame,
            fg_color="#0d1117",
            text_color="#a6e3a1",
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word",
            state="disabled",
        )
        self._log_text.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 6))
        frame.grid_rowconfigure(3, weight=1)

        # Progreso global
        self._lbl_progress_global = ctk.CTkLabel(
            frame, text="Progreso: —", font=ctk.CTkFont(size=11), text_color=C_MUTED
        )
        self._lbl_progress_global.grid(row=4, column=0, sticky="w", padx=12)

        self._progress_global = ctk.CTkProgressBar(frame, mode="determinate")
        self._progress_global.set(0)
        self._progress_global.grid(row=5, column=0, sticky="ew", padx=10, pady=(2, 2))

        # Progreso por archivo
        self._lbl_progress_file = ctk.CTkLabel(
            frame, text="", font=ctk.CTkFont(size=10), text_color=C_MUTED
        )
        self._lbl_progress_file.grid(row=6, column=0, sticky="w", padx=12)

        self._progress_file = ctk.CTkProgressBar(frame, mode="indeterminate", height=8)
        self._progress_file.grid(row=7, column=0, sticky="ew", padx=10, pady=(0, 6))
        self._progress_file.stop()

    # --- Footer -------------------------------------------------------

    def _build_footer(self) -> None:
        footer = ctk.CTkFrame(self, fg_color=C_ACCENT, corner_radius=0, height=56)
        footer.grid(row=2, column=0, sticky="ew")
        footer.grid_propagate(False)
        footer.grid_columnconfigure(4, weight=1)

        self._btn_generate = ctk.CTkButton(
            footer,
            text="▶  Generar videos",
            fg_color=C_BTN_PRIMARY,
            hover_color="#c1121f",
            font=ctk.CTkFont(size=13, weight="bold"),
            width=160,
            command=self._on_generate,
        )
        self._btn_generate.grid(row=0, column=0, padx=12, pady=10)

        self._btn_cancel = ctk.CTkButton(
            footer,
            text="⏹  Cancelar",
            fg_color=C_ACCENT,
            hover_color="#6c757d",
            width=120,
            state="disabled",
            command=self._on_cancel,
        )
        self._btn_cancel.grid(row=0, column=1, padx=4, pady=10)

        self._btn_preview = ctk.CTkButton(
            footer,
            text="👁  Preview efecto",
            fg_color=C_BTN_SECONDARY,
            width=140,
            command=self._on_preview,
        )
        self._btn_preview.grid(row=0, column=2, padx=4, pady=10)

        self._btn_test = ctk.CTkButton(
            footer,
            text="🔧  Probar FFmpeg",
            fg_color=C_BTN_SECONDARY,
            width=140,
            command=self._on_test_ffmpeg,
        )
        self._btn_test.grid(row=0, column=3, padx=4, pady=10)

        ctk.CTkButton(
            footer,
            text="💾  Guardar config",
            fg_color="transparent",
            border_width=1,
            width=130,
            command=self._save_settings,
        ).grid(row=0, column=5, padx=(4, 12), pady=10, sticky="e")

    # ──────────────────────────────────────────────────────────────────
    # HELPERS DE CONSTRUCCIÓN DE WIDGETS
    # ──────────────────────────────────────────────────────────────────

    def _section_label(self, parent: Any, text: str, row: int) -> int:
        ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=C_TEXT,
            anchor="w",
        ).grid(row=row, column=0, sticky="ew", padx=12, pady=(14, 2))
        ctk.CTkFrame(parent, height=1, fg_color=C_ACCENT).grid(
            row=row + 1, column=0, sticky="ew", padx=12, pady=(0, 6)
        )
        return row + 2

    def _collapsible_section(
        self,
        parent: Any,
        title: str,
        row: int,
        default_open: bool = True,
    ) -> tuple[ctk.CTkFrame, int]:
        """Crea una sección colapsable. Retorna (content_frame, siguiente_row)."""
        _open = [default_open]
        _title = title

        btn = ctk.CTkButton(
            parent,
            text=f"{'\u25bc' if default_open else '\u25b6'}  {title}",
            anchor="w",
            fg_color="transparent",
            hover_color=C_ACCENT,
            text_color=C_TEXT,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=30,
            corner_radius=4,
        )
        btn.grid(row=row, column=0, sticky="ew", padx=6, pady=(12, 0))

        ctk.CTkFrame(parent, height=1, fg_color=C_ACCENT).grid(
            row=row + 1, column=0, sticky="ew", padx=12, pady=(0, 4),
        )

        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.grid_columnconfigure(0, weight=1)
        content.grid(row=row + 2, column=0, sticky="ew")
        if not default_open:
            content.grid_remove()

        def _toggle() -> None:
            if _open[0]:
                content.grid_remove()
                btn.configure(text=f"\u25b6  {_title}")
                _open[0] = False
            else:
                content.grid()
                btn.configure(text=f"\u25bc  {_title}")
                _open[0] = True

        btn.configure(command=_toggle)
        return content, row + 3

    def _file_row(
        self,
        parent: Any,
        label: str,
        var: tk.StringVar,
        command: Any,
        row: int,
    ) -> int:
        ctk.CTkLabel(parent, text=label, text_color=C_MUTED,
                     font=ctk.CTkFont(size=11), anchor="w").grid(
            row=row, column=0, sticky="ew", padx=12, pady=(2, 0)
        )
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.grid(row=row + 1, column=0, sticky="ew", padx=12, pady=(0, 4))
        inner.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(inner, textvariable=var, height=28).grid(
            row=0, column=0, sticky="ew", padx=(0, 4)
        )
        ctk.CTkButton(inner, text="...", width=36, height=28, command=command).grid(
            row=0, column=1
        )
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
    ) -> int:
        inner = ctk.CTkFrame(parent, fg_color="transparent")
        inner.grid(row=row, column=0, sticky="ew", padx=12, pady=3)
        inner.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(inner, text=label, text_color=C_MUTED,
                     font=ctk.CTkFont(size=11), width=120, anchor="w").grid(
            row=0, column=0, sticky="w"
        )

        val_label = ctk.CTkLabel(inner, text=fmt.format(var.get()),
                                 text_color=C_TEXT, font=ctk.CTkFont(size=11), width=50)
        val_label.grid(row=0, column=2, padx=(4, 0))

        def _update(v: str) -> None:
            try:
                val_label.configure(text=fmt.format(float(v)))
            except ValueError:
                pass

        ctk.CTkSlider(
            inner,
            from_=from_,
            to=to,
            variable=var,
            command=_update,
        ).grid(row=0, column=1, sticky="ew", padx=4)

        if tooltip_text:
            _info_btn = ctk.CTkButton(
                inner, text="?", width=22, height=22,
                fg_color=C_ACCENT, hover_color=C_BTN_SECONDARY,
                font=ctk.CTkFont(size=11, weight="bold"),
                corner_radius=11,
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
            font=ctk.CTkFont(size=11),
            text_color=C_TEXT,
            command=command,
        )
        cb.grid(row=row, column=0, sticky="w", padx=16, pady=2)
        return row + 1

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
            img.thumbnail((400, 175))
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
            # Text overlay
            "enable_text_overlay": self._var_text_overlay.get(),
            "text_content": self._var_text_content.get(),
            "text_position": self._var_text_position.get(),
            "text_margin": int(self._var_text_margin.get()),
            "text_font_size": int(self._var_text_font_size.get()),
            "text_glitch_intensity": int(self._var_text_glitch_intensity.get()),
            "text_glitch_speed": round(self._var_text_glitch_speed.get(), 1),
        })

    def _load_settings_to_ui(self) -> None:
        """Carga la configuración guardada en los widgets de la UI."""
        s = self.settings.all()
        self._var_audio_folder.set(s.get("audio_folder", ""))
        self._var_image.set(s.get("background_image", ""))
        self._var_output.set(s.get("output_folder", ""))
        self._var_zoom_max.set(s.get("zoom_max", 1.05))
        self._var_zoom_speed.set(s.get("zoom_speed", 300))
        self._var_fade_in.set(s.get("fade_in", 2.0))
        self._var_fade_out.set(s.get("fade_out", 2.0))
        self._var_crf.set(s.get("crf", 18))
        self._var_resolution.set(s.get("resolution", "1080p"))
        self._var_zoom.set(s.get("enable_zoom", True))
        self._var_glitch.set(s.get("enable_glitch", False))
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

        # Text overlay
        self._var_text_overlay.set(s.get("enable_text_overlay", False))
        self._var_text_content.set(s.get("text_content", ""))
        self._var_text_position.set(s.get("text_position", "Bottom"))
        self._var_text_margin.set(s.get("text_margin", 40))
        self._var_text_font_size.set(s.get("text_font_size", 36))
        self._var_text_glitch_intensity.set(s.get("text_glitch_intensity", 3))
        self._var_text_glitch_speed.set(s.get("text_glitch_speed", 4.0))
        self._toggle_text_overlay_widgets()

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
