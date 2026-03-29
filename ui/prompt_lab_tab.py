"""UI builder for Prompt Lab mode."""

from __future__ import annotations

from typing import Any

import customtkinter as ctk


def build_prompt_lab_panel(
    app: Any,
    parent: ctk.CTkFrame,
    *,
    accent: str,
    colors: dict[str, str],
    icons: dict[str, str],
) -> ctk.CTkFrame:
    panel = ctk.CTkFrame(parent, fg_color="transparent")
    panel.grid(row=0, column=0, sticky="nsew", padx=0)
    panel.grid_columnconfigure(0, weight=3)
    panel.grid_columnconfigure(1, weight=4)
    panel.grid_rowconfigure(0, weight=0)
    panel.grid_rowconfigure(1, weight=0)
    panel.grid_rowconfigure(2, weight=0)
    panel.grid_rowconfigure(3, weight=1)
    panel.grid_remove()

    card_workspace = ctk.CTkFrame(
        panel,
        fg_color=colors["C_CARD"],
        corner_radius=10,
        border_width=1,
        border_color=colors["C_BORDER"],
    )
    card_workspace.grid(row=0, column=0, sticky="ew", pady=(8, 10))
    card_workspace.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(
        card_workspace,
        text=icons["FA_WAND"] + "  Prompt Lab",
        text_color=colors["C_TEXT"],
        font=ctk.CTkFont(size=app._fs(13), weight="bold"),
    ).grid(row=0, column=0, columnspan=3, sticky="w", padx=14, pady=(12, 8))

    ctk.CTkLabel(
        card_workspace,
        text="Workspace",
        text_color=colors["C_MUTED"],
        font=ctk.CTkFont(size=app._fs(11)),
    ).grid(row=1, column=0, sticky="w", padx=(14, 8), pady=(0, 10))

    app._var_pl_workspace = getattr(app, "_var_pl_workspace")
    app._pl_workspace_menu = ctk.CTkOptionMenu(
        card_workspace,
        variable=app._var_pl_workspace,
        values=["General"],
        fg_color=colors["C_INPUT"],
        button_color=accent,
        button_hover_color=accent,
        text_color=colors["C_TEXT"],
        dropdown_fg_color=colors["C_CARD"],
        dropdown_hover_color=colors["C_HOVER"],
        dropdown_text_color=colors["C_TEXT"],
        command=lambda _: app._pl_on_workspace_selected(),
    )
    app._pl_workspace_menu.grid(row=1, column=1, sticky="ew", pady=(0, 10))

    btns = ctk.CTkFrame(card_workspace, fg_color="transparent")
    btns.grid(row=1, column=2, sticky="e", padx=(8, 14), pady=(0, 10))

    ctk.CTkButton(
        btns,
        text="+ Workspace",
        width=110,
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        command=app._pl_new_workspace_dialog,
    ).pack(side="left", padx=(0, 6))

    ctk.CTkButton(
        btns,
        text="Eliminar",
        width=90,
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT_DIM"],
        command=app._pl_delete_workspace,
    ).pack(side="left")

    ctk.CTkButton(
        btns,
        text="Exportar",
        width=90,
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        command=app._pl_export_workspace,
    ).pack(side="left", padx=(6, 0))

    ctk.CTkButton(
        btns,
        text="Importar",
        width=90,
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        command=app._pl_import_workspace,
    ).pack(side="left", padx=(6, 0))

    card_skill = ctk.CTkFrame(
        panel,
        fg_color=colors["C_CARD"],
        corner_radius=10,
        border_width=1,
        border_color=colors["C_BORDER"],
    )
    card_skill.grid(row=1, column=0, sticky="ew", pady=(0, 10))
    card_skill.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(
        card_skill,
        text="Categoria",
        text_color=colors["C_MUTED"],
        font=ctk.CTkFont(size=app._fs(11)),
    ).grid(row=0, column=0, sticky="w", padx=(14, 8), pady=(12, 8))

    app._pl_category_menu = ctk.CTkOptionMenu(
        card_skill,
        variable=app._var_pl_category,
        values=["General"],
        fg_color=colors["C_INPUT"],
        button_color=accent,
        button_hover_color=accent,
        text_color=colors["C_TEXT"],
        dropdown_fg_color=colors["C_CARD"],
        dropdown_hover_color=colors["C_HOVER"],
        dropdown_text_color=colors["C_TEXT"],
        command=lambda _: app._pl_on_category_selected(),
    )
    app._pl_category_menu.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=(12, 8))

    ctk.CTkButton(
        card_skill,
        text="Categorias",
        width=110,
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        command=app._pl_open_categories_modal,
    ).grid(row=0, column=2, sticky="e", padx=(8, 14), pady=(12, 8))

    ctk.CTkLabel(
        card_skill,
        text="Skills",
        text_color=colors["C_MUTED"],
        font=ctk.CTkFont(size=app._fs(11)),
    ).grid(row=1, column=0, sticky="w", padx=(14, 8), pady=(0, 8))

    skill_btns = ctk.CTkFrame(card_skill, fg_color="transparent")
    skill_btns.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 14), pady=(0, 8))

    ctk.CTkButton(
        skill_btns,
        text="+ Skill",
        width=90,
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        command=app._pl_new_skill_dialog,
    ).pack(side="left", padx=(0, 6))

    ctk.CTkButton(
        skill_btns,
        text="Gestionar skills",
        width=130,
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        command=app._pl_open_skills_manager_modal,
    ).pack(side="left")

    ctk.CTkButton(
        skill_btns,
        text="Aplicar multiples",
        width=130,
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        command=app._pl_open_skill_selector_modal,
    ).pack(side="left", padx=(6, 0))

    app._pl_skill_tiles = ctk.CTkFrame(
        card_skill,
        fg_color=colors["C_INPUT"],
        corner_radius=8,
        border_width=1,
        border_color=colors["C_BORDER"],
    )
    app._pl_skill_tiles.grid(row=2, column=0, columnspan=3, sticky="ew", padx=14, pady=(0, 10))
    app._pl_skill_tiles.grid_columnconfigure(0, weight=1)

    card_model = ctk.CTkFrame(
        panel,
        fg_color=colors["C_CARD"],
        corner_radius=10,
        border_width=1,
        border_color=colors["C_BORDER"],
    )
    card_model.grid(row=2, column=0, sticky="ew", pady=(0, 10))
    card_model.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(
        card_model,
        text="Modo de modelo",
        text_color=colors["C_MUTED"],
        font=ctk.CTkFont(size=app._fs(11)),
    ).grid(row=0, column=0, sticky="w", padx=(14, 8), pady=12)

    app._pl_model_menu = ctk.CTkOptionMenu(
        card_model,
        variable=app._var_pl_model_mode,
        values=["Calidad alta", "Respuesta rapida"],
        fg_color=colors["C_INPUT"],
        button_color=accent,
        button_hover_color=accent,
        text_color=colors["C_TEXT"],
        dropdown_fg_color=colors["C_CARD"],
        dropdown_hover_color=colors["C_HOVER"],
        dropdown_text_color=colors["C_TEXT"],
        command=lambda _: app._pl_update_model_hints(),
    )
    app._pl_model_menu.grid(row=0, column=1, sticky="ew", padx=(0, 14), pady=12)

    ctk.CTkLabel(
        card_model,
        text="Modelo calidad",
        text_color=colors["C_MUTED"],
        font=ctk.CTkFont(size=app._fs(11)),
    ).grid(row=1, column=0, sticky="w", padx=(14, 8), pady=(0, 8))

    app._pl_quality_model_menu = ctk.CTkOptionMenu(
        card_model,
        values=[app._var_pl_model_quality_display.get() or "llama3.1:8b (Pesado)"],
        fg_color=colors["C_INPUT"],
        button_color=accent,
        button_hover_color=accent,
        text_color=colors["C_TEXT"],
        dropdown_fg_color=colors["C_CARD"],
        dropdown_hover_color=colors["C_HOVER"],
        dropdown_text_color=colors["C_TEXT"],
        variable=app._var_pl_model_quality_display,
        command=app._pl_on_quality_model_selected,
    )
    app._pl_quality_model_menu.grid(row=1, column=1, sticky="ew", padx=(0, 14), pady=(0, 8))

    ctk.CTkLabel(
        card_model,
        text="Modelo rapido",
        text_color=colors["C_MUTED"],
        font=ctk.CTkFont(size=app._fs(11)),
    ).grid(row=2, column=0, sticky="w", padx=(14, 8), pady=(0, 8))

    app._pl_fast_model_menu = ctk.CTkOptionMenu(
        card_model,
        values=[app._var_pl_model_fast_display.get() or "llama3.2:3b (Medio)"],
        fg_color=colors["C_INPUT"],
        button_color=accent,
        button_hover_color=accent,
        text_color=colors["C_TEXT"],
        dropdown_fg_color=colors["C_CARD"],
        dropdown_hover_color=colors["C_HOVER"],
        dropdown_text_color=colors["C_TEXT"],
        variable=app._var_pl_model_fast_display,
        command=app._pl_on_fast_model_selected,
    )
    app._pl_fast_model_menu.grid(row=2, column=1, sticky="ew", padx=(0, 14), pady=(0, 8))

    app._lbl_pl_model_hint = ctk.CTkLabel(
        card_model,
        text="",
        text_color=colors["C_TEXT_DIM"],
        anchor="w",
        justify="left",
        wraplength=650,
        font=ctk.CTkFont(size=app._fs(10)),
    )
    app._lbl_pl_model_hint.grid(row=3, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 8))

    model_btns = ctk.CTkFrame(card_model, fg_color="transparent")
    model_btns.grid(row=4, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 12))
    model_btns.grid_columnconfigure(0, weight=1)
    model_btns.grid_columnconfigure(1, weight=1)

    ctk.CTkButton(
        model_btns,
        text="Actualizar modelos disponibles",
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        command=app._pl_refresh_available_models,
    ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

    ctk.CTkButton(
        model_btns,
        text="Gestionar almacenamiento IA",
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        command=app._pl_open_model_manager_modal,
    ).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    card_prompt = ctk.CTkFrame(
        panel,
        fg_color=colors["C_CARD"],
        corner_radius=10,
        border_width=1,
        border_color=colors["C_BORDER"],
    )
    card_prompt.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=(12, 0), pady=(8, 10))
    card_prompt.grid_columnconfigure(0, weight=1)
    card_prompt.grid_rowconfigure(1, weight=1)
    card_prompt.grid_rowconfigure(4, weight=2)

    ctk.CTkLabel(
        card_prompt,
        text="Prompt",
        text_color=colors["C_TEXT"],
        font=ctk.CTkFont(size=app._fs(12), weight="bold"),
    ).grid(row=0, column=0, sticky="w", padx=14, pady=(12, 6))

    app._lbl_pl_prompt_helper = ctk.CTkLabel(
        card_prompt,
        text="Guia disponible: usa 'Insertar plantilla'",
        text_color=colors["C_TEXT_DIM"],
        anchor="e",
        justify="left",
        wraplength=320,
        font=ctk.CTkFont(size=app._fs(10)),
    )
    app._lbl_pl_prompt_helper.grid(row=0, column=0, sticky="e", padx=(14, 14), pady=(12, 6))

    app._txt_pl_prompt = ctk.CTkTextbox(
        card_prompt,
        height=150,
        fg_color=colors["C_INPUT"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        font=ctk.CTkFont(size=app._fs(11)),
    )
    app._txt_pl_prompt.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))

    mid = ctk.CTkFrame(card_prompt, fg_color="transparent")
    mid.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))

    ctk.CTkButton(
        mid,
        text=icons["FA_WAND"] + "  Generar respuesta",
        fg_color=accent,
        hover_color=accent,
        text_color="#FFFFFF",
        command=app._on_generate_prompt_lab,
    ).pack(side="left")

    ctk.CTkButton(
        mid,
        text="Insertar plantilla",
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        command=app._pl_insert_prompt_template,
    ).pack(side="left", padx=(8, 0))

    ctk.CTkButton(
        mid,
        text="Copiar salida",
        fg_color="transparent",
        hover_color=colors["C_HOVER"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        command=app._pl_copy_output,
    ).pack(side="left", padx=(8, 0))

    app._lbl_pl_status = ctk.CTkLabel(
        mid,
        text="Listo",
        text_color=colors["C_TEXT_DIM"],
        width=220,
        anchor="e",
        font=ctk.CTkFont(size=app._fs(10)),
    )
    app._lbl_pl_status.pack(side="right")

    ctk.CTkLabel(
        card_prompt,
        text="Salida",
        text_color=colors["C_TEXT"],
        font=ctk.CTkFont(size=app._fs(12), weight="bold"),
    ).grid(row=3, column=0, sticky="w", padx=14, pady=(2, 6))

    app._txt_pl_output = ctk.CTkTextbox(
        card_prompt,
        height=450,
        fg_color=colors["C_INPUT"],
        border_width=1,
        border_color=colors["C_BORDER"],
        text_color=colors["C_TEXT"],
        font=ctk.CTkFont(size=app._fs(11)),
    )
    app._txt_pl_output.grid(row=4, column=0, sticky="nsew", padx=14, pady=(0, 14))

    return panel
