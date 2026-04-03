"""UI builder for the YouTube Publisher mode.

This module only builds interface controls (no API calls yet).
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

import customtkinter as ctk

# IANA timezone names accepted by the YouTube Data API.
# Default is America/Los_Angeles — the same default used by YouTube Studio.
_YT_TIMEZONES: list[str] = [
    # ── Americas ──────────────────────────────────────────────────────────
    "America/Los_Angeles",       # PT  — YouTube Studio default
    "America/Denver",            # MT
    "America/Chicago",           # CT
    "America/New_York",          # ET
    "America/Anchorage",         # AK
    "Pacific/Honolulu",          # HT
    "America/Toronto",           # ET (Canada)
    "America/Vancouver",         # PT (Canada)
    "America/Mexico_City",       # CST (MX)
    "America/El_Salvador",       # CST (SV)
    "America/Guatemala",
    "America/Costa_Rica",
    "America/Panama",
    "America/Bogota",            # COT
    "America/Lima",              # PET
    "America/Caracas",           # VET
    "America/Santiago",          # CLT
    "America/Sao_Paulo",         # BRT
    "America/Argentina/Buenos_Aires",  # ART
    # ── Europe ────────────────────────────────────────────────────────────
    "Europe/London",             # GMT/BST
    "Europe/Lisbon",             # WET/WEST
    "Europe/Madrid",             # CET
    "Europe/Paris",              # CET
    "Europe/Berlin",             # CET
    "Europe/Rome",               # CET
    "Europe/Amsterdam",          # CET
    "Europe/Warsaw",             # CET
    "Europe/Stockholm",          # CET
    "Europe/Athens",             # EET
    "Europe/Helsinki",           # EET
    "Europe/Bucharest",          # EET
    "Europe/Kiev",               # EET
    "Europe/Moscow",             # MSK
    # ── Africa / Middle East ──────────────────────────────────────────────
    "Africa/Cairo",              # EET
    "Africa/Johannesburg",       # SAST
    "Africa/Lagos",              # WAT
    "Africa/Nairobi",            # EAT
    "Asia/Dubai",                # GST
    "Asia/Riyadh",               # AST
    "Asia/Tehran",               # IRST
    # ── Asia / Pacific ────────────────────────────────────────────────────
    "Asia/Kolkata",              # IST
    "Asia/Dhaka",                # BST
    "Asia/Bangkok",              # ICT
    "Asia/Ho_Chi_Minh",          # ICT
    "Asia/Jakarta",              # WIB
    "Asia/Singapore",            # SGT
    "Asia/Kuala_Lumpur",         # MYT
    "Asia/Manila",               # PHT
    "Asia/Hong_Kong",            # HKT
    "Asia/Shanghai",             # CST
    "Asia/Taipei",               # CST
    "Asia/Seoul",                # KST
    "Asia/Tokyo",                # JST
    "Australia/Perth",           # AWST
    "Australia/Darwin",          # ACST
    "Australia/Sydney",          # AEST
    "Australia/Melbourne",       # AEST
    "Australia/Brisbane",        # AEST
    "Pacific/Auckland",          # NZST
    "Pacific/Fiji",
    # ── Universal ─────────────────────────────────────────────────────────
    "UTC",
]


def build_youtube_publisher_panel(
    app: Any,
    parent: ctk.CTkFrame,
    *,
    accent: str,
    colors: dict[str, str],
    icons: dict[str, str],
) -> ctk.CTkFrame:
    panel, tabs = app._make_tab_panel(
        parent,
        [
            ("Canal", "channel"),
            ("Cola", "queue"),
        ],
        accent=accent,
        on_before_activate=app._yt_on_subtab_activate,
    )
    app._yt_activate_subtab = getattr(panel, "_activate_tab", None)
    panel.grid(row=0, column=0, sticky="nsew", padx=0)
    panel.grid_remove()

    tab_channel = tabs["channel"]
    tab_queue = tabs["queue"]

    # TAB: CANAL
    ch = ctk.CTkScrollableFrame(tab_channel, fg_color="transparent")
    ch.pack(fill="both", expand=True, padx=16, pady=(8, 12))
    ch.grid_columnconfigure(0, weight=1)

    card_auth = ctk.CTkFrame(
        ch, fg_color=colors["C_CARD"], corner_radius=10,
        border_width=1, border_color=colors["C_BORDER"],
    )
    card_auth.grid(row=0, column=0, sticky="ew", pady=(0, 10))
    card_auth.grid_columnconfigure(0, weight=1)
    app._section_header(
        card_auth,
        "Conexion del canal",
        collapse_on_startup=False,
    ).grid(row=0, column=0, sticky="ew")

    auth_inner = ctk.CTkFrame(card_auth, fg_color="transparent")
    auth_inner.grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 14))
    auth_inner.grid_columnconfigure(0, weight=1)

    app._var_yt_channel_status = tk.StringVar(value="No conectado.")
    ctk.CTkLabel(
        auth_inner, textvariable=app._var_yt_channel_status,
        text_color=colors["C_TEXT_DIM"], anchor="w", justify="left",
        font=ctk.CTkFont(size=app._fs(11)),
    ).grid(row=0, column=0, sticky="ew", pady=(0, 8))

    app._var_yt_cache_status = tk.StringVar(
        value="Cache: sin datos. Pulsa 'Refrescar estado' para consultar."
    )
    ctk.CTkLabel(
        auth_inner,
        textvariable=app._var_yt_cache_status,
        text_color=colors["C_MUTED"],
        anchor="w",
        justify="left",
        wraplength=620,
        font=ctk.CTkFont(size=app._fs(10)),
    ).grid(row=1, column=0, sticky="ew", pady=(0, 8))

    ctk.CTkLabel(
        auth_inner,
        text=(
            "Como funciona:\n"
            "1. Sube tus videos a YouTube Studio como Oculto (privado) y SIN fecha de publicacion.\n"
            "2. Haz clic en \u00abObtener borradores\u00bb para cargar esos videos en la cola de abajo.\n"
            "3. Edita el titulo, descripcion, categoria y etiquetas de cada video si lo necesitas.\n"
            "4. Usa \u00abProgramar\u00bb para distribuir automaticamente las fechas de publicacion.\n"
            "5. Haz clic en \u00abGenerar\u00bb para aplicar los cambios en YouTube \u2014 los videos se publicaran en la fecha indicada.\n\n"
            "Nota: esta pestana no sube archivos nuevos. Solo gestiona videos que ya estan en tu canal como borradores privados sin fecha."
        ),
        text_color=colors["C_TEXT_DIM"],
        anchor="w",
        justify="left",
        wraplength=620,
        font=ctk.CTkFont(size=app._fs(10)),
    ).grid(row=2, column=0, sticky="ew", pady=(0, 10))

    auth_btns = ctk.CTkFrame(auth_inner, fg_color="transparent")
    auth_btns.grid(row=3, column=0, sticky="ew")
    ctk.CTkButton(
        auth_btns,
        text=icons["FA_UPLOAD"] + "  Conectar canal",
        width=150, fg_color=accent, hover_color=accent, text_color="#FFFFFF",
        command=app._yt_connect_channel,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        auth_btns, text="Refrescar estado", width=140,
        fg_color="transparent", hover_color=colors["C_HOVER"],
        border_width=2, border_color=colors["C_BORDER"], text_color=colors["C_TEXT"],
        command=app._yt_refresh_channel_status,
    ).pack(side="left")

    card_cfg = ctk.CTkFrame(
        ch, fg_color=colors["C_CARD"], corner_radius=10,
        border_width=1, border_color=colors["C_BORDER"],
    )
    card_cfg.grid(row=1, column=0, sticky="ew")
    card_cfg.grid_columnconfigure(0, weight=1)
    app._section_header(card_cfg, "Configuracion global").grid(row=0, column=0, sticky="ew")

    cfg = ctk.CTkFrame(card_cfg, fg_color="transparent")
    cfg.grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 14))
    cfg.grid_columnconfigure(1, weight=1)

    app._var_yt_timezone = tk.StringVar(value="America/Los_Angeles")
    app._var_yt_videos_per_day = tk.StringVar(value="3")
    app._var_yt_schedule_frequency = tk.StringVar(value="Diario")
    app._var_yt_window_start = tk.StringVar(value="09:00")
    app._var_yt_window_end = tk.StringVar(value="21:00")
    app._var_yt_default_category = tk.StringVar(value="Music")
    app._var_yt_default_made_for_kids = tk.BooleanVar(value=False)

    _lbl_kw = dict(text_color=colors["C_MUTED"], anchor="w", font=ctk.CTkFont(size=app._fs(11)))
    _opt_kw = dict(
        fg_color=colors["C_INPUT"], button_color=accent, button_hover_color=accent,
        text_color=colors["C_TEXT"], dropdown_fg_color=colors["C_CARD"],
        dropdown_text_color=colors["C_TEXT"], dropdown_hover_color=colors["C_HOVER"],
    )
    _ent_kw = dict(fg_color=colors["C_INPUT"], border_color=colors["C_BORDER"],
                   text_color=colors["C_TEXT"], height=30)

    r = 0
    ctk.CTkLabel(cfg, text="Zona horaria", **_lbl_kw).grid(
        row=r, column=0, sticky="w", padx=(0, 10), pady=(0, 6))
    ctk.CTkOptionMenu(
        cfg, variable=app._var_yt_timezone, values=_YT_TIMEZONES,
        dynamic_resizing=False, width=220, **_opt_kw,
    ).grid(row=r, column=1, sticky="ew", pady=(0, 6))
    r += 1

    ctk.CTkLabel(cfg, text="Ventana horaria", **_lbl_kw).grid(
        row=r, column=0, sticky="w", padx=(0, 10), pady=(0, 6))
    tw = ctk.CTkFrame(cfg, fg_color="transparent")
    tw.grid(row=r, column=1, sticky="ew", pady=(0, 6))
    ctk.CTkEntry(tw, textvariable=app._var_yt_window_start, width=72, **_ent_kw).pack(side="left")
    ctk.CTkLabel(tw, text=u"\u2013", text_color=colors["C_TEXT_DIM"]).pack(side="left", padx=6)
    ctk.CTkEntry(tw, textvariable=app._var_yt_window_end, width=72, **_ent_kw).pack(side="left")
    r += 1

    ctk.CTkLabel(cfg, text="Videos por dia", **_lbl_kw).grid(
        row=r, column=0, sticky="w", padx=(0, 10), pady=(0, 6))
    ctk.CTkOptionMenu(
        cfg, variable=app._var_yt_videos_per_day, values=["1", "2", "3", "4", "5", "6"],
        **_opt_kw,
    ).grid(row=r, column=1, sticky="ew", pady=(0, 6))
    r += 1

    ctk.CTkLabel(cfg, text="Frecuencia", **_lbl_kw).grid(
        row=r, column=0, sticky="w", padx=(0, 10), pady=(0, 6))
    ctk.CTkOptionMenu(
        cfg,
        variable=app._var_yt_schedule_frequency,
        values=["Diario", "Dia por medio"],
        **_opt_kw,
    ).grid(row=r, column=1, sticky="ew", pady=(0, 6))
    r += 1

    ctk.CTkLabel(cfg, text="Categoria por defecto", **_lbl_kw).grid(
        row=r, column=0, sticky="w", padx=(0, 10), pady=(0, 6))
    ctk.CTkOptionMenu(
        cfg, variable=app._var_yt_default_category,
        values=["Music", "Entertainment", "People & Blogs", "Education",
                "Film & Animation", "Howto & Style", "Gaming",
                "Science & Technology", "News & Politics", "Sports"],
        **_opt_kw,
    ).grid(row=r, column=1, sticky="ew", pady=(0, 6))
    r += 1

    ctk.CTkCheckBox(
        cfg, text="Hecho para ninos (por defecto NO)",
        variable=app._var_yt_default_made_for_kids,
        fg_color=accent, hover_color=accent, text_color=colors["C_TEXT"],
        font=ctk.CTkFont(size=app._fs(11)),
    ).grid(row=r, column=0, columnspan=2, sticky="w", pady=(4, 0))

    # TAB: COLA
    toolbar = ctk.CTkFrame(tab_queue, fg_color="transparent")
    toolbar.pack(fill="x", padx=16, pady=(12, 4))

    ctk.CTkButton(
        toolbar, text="Obtener borradores",
        fg_color=accent, hover_color=accent, text_color="#FFFFFF",
        command=app._yt_fetch_drafts,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        toolbar, text="Playlists", width=100,
        fg_color="transparent", hover_color=colors["C_HOVER"],
        border_width=2, border_color=colors["C_BORDER"], text_color=colors["C_TEXT"],
        command=app._yt_open_playlists_modal,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        toolbar, text="Metadatos en lote", width=140,
        fg_color="transparent", hover_color=colors["C_HOVER"],
        border_width=2, border_color=colors["C_BORDER"], text_color=colors["C_TEXT"],
        command=app._yt_open_bulk_modal,
    ).pack(side="left", padx=(0, 8))
    ctk.CTkButton(
        toolbar, text="Programar", width=100,
        fg_color="transparent", hover_color=colors["C_HOVER"],
        border_width=2, border_color=colors["C_BORDER"], text_color=colors["C_TEXT"],
        command=app._yt_open_schedule_modal,
    ).pack(side="left")

    app._var_yt_queue_cache_status = tk.StringVar(
        value="Cola: sin cache. Pulsa 'Obtener borradores'."
    )
    ctk.CTkLabel(
        tab_queue,
        textvariable=app._var_yt_queue_cache_status,
        text_color=colors["C_MUTED"],
        anchor="w",
        justify="left",
        wraplength=760,
        font=ctk.CTkFont(size=app._fs(10)),
    ).pack(fill="x", padx=16, pady=(0, 4))

    ctk.CTkFrame(tab_queue, fg_color=colors["C_BORDER"], height=1).pack(
        fill="x", padx=0, pady=(6, 0))

    app._yt_queue_frame = ctk.CTkScrollableFrame(tab_queue, fg_color="transparent")
    app._yt_queue_frame.pack(fill="both", expand=True, padx=10, pady=(4, 8))
    app._yt_queue_frame.grid_columnconfigure(0, weight=1)
    app._yt_queue_frame.grid_columnconfigure(1, weight=3)
    app._yt_queue_frame.grid_columnconfigure(2, weight=1)
    app._yt_queue_frame.grid_columnconfigure(3, weight=1)
    app._yt_queue_frame.grid_columnconfigure(4, weight=2)
    app._yt_queue_frame.grid_columnconfigure(5, weight=0)

    return panel