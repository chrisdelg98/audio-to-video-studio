"""
NamingManager — Sistema configurable de nombres de salida para videos.

Modos soportados:
  - Default:            usa el stem del archivo de audio.
  - Prefix:             prefijo + stem del archivo de audio.
  - Custom List:        lista personalizada (consumida en orden).
  - Prefix + Custom:    prefijo + lista personalizada.

Reglas:
  - Si la lista tiene menos nombres que audios → error de validación.
  - Si la lista tiene más → se ignoran los sobrantes (con advertencia).
  - Nombres duplicados → se auto-corrigen añadiendo (2), (3)…
  - Caracteres inválidos para nombres de archivo → se reemplazan por "_".
  - Numeración automática opcional: prefija "01 - ", "02 - ", …
"""

from __future__ import annotations

import re
from enum import Enum
from pathlib import Path


# ── Constantes de modo ──────────────────────────────────────────────────────

class NamingMode(str, Enum):
    DEFAULT = "default"
    NAME = "name"
    PREFIX = "prefix"
    CUSTOM = "custom"
    PREFIX_CUSTOM = "prefix_custom"


# Mapeo de etiquetas UI → clave interna (acepta ambas formas)
_LABEL_TO_MODE: dict[str, NamingMode] = {
    # Etiquetas de la UI (dropdown) — inglés
    "Default": NamingMode.DEFAULT,
    "Prefix": NamingMode.PREFIX,
    "Custom List": NamingMode.CUSTOM,
    "Prefix + Custom List": NamingMode.PREFIX_CUSTOM,
    # Etiquetas de la UI (dropdown) — español
    "Nombre": NamingMode.NAME,
    "Prefijo": NamingMode.PREFIX,
    "Lista personalizada": NamingMode.CUSTOM,
    "Prefijo + Lista personalizada": NamingMode.PREFIX_CUSTOM,
    # Claves internas (para compatibilidad con JSON guardado antes)
    "default": NamingMode.DEFAULT,
    "name": NamingMode.NAME,
    "prefix": NamingMode.PREFIX,
    "custom": NamingMode.CUSTOM,
    "prefix_custom": NamingMode.PREFIX_CUSTOM,
}

# Caracteres no permitidos en nombres de archivo (Windows + Unix)
_INVALID_CHARS = re.compile(r'[\\/:*?"<>|]')


# ── Función de saneamiento ───────────────────────────────────────────────────

def sanitize_filename(name: str) -> str:
    """
    Elimina o sustituye caracteres no permitidos en nombres de archivo.
    También recorta espacios al inicio/final.
    """
    return _INVALID_CHARS.sub("_", name).strip()


# ── NamingManager ────────────────────────────────────────────────────────────

class NamingManager:
    """
    Genera nombres de salida para los videos según el modo configurado.

    Uso típico:
        nm = NamingManager(mode="Custom List", prefix="", custom_names=[...], auto_number=True)
        errors = nm.validate(len(audio_files))
        if errors:
            ...
        warnings = nm.get_warnings(len(audio_files))
        names = nm.generate_names(audio_files)          # list[str] — sin extensión
        path  = nm.build_output_path(names[0], output_folder)
    """

    def __init__(
        self,
        mode: str = "Default",
        prefix: str = "",
        custom_names: list[str] | None = None,
        auto_number: bool = True,
    ) -> None:
        """
        Args:
            mode:         Modo de nombrado (etiqueta UI o clave interna).
            prefix:       Prefijo opcional para los modos que lo requieren.
            custom_names: Lista de nombres personalizados (para modos Custom).
            auto_number:  Si True, antepone numeración "01 - ", "02 - ", …
        """
        self.mode: NamingMode = _LABEL_TO_MODE.get(mode, NamingMode.DEFAULT)
        self.prefix: str = prefix or ""
        self.custom_names: list[str] = [n.strip() for n in (custom_names or []) if n.strip()]
        self.auto_number: bool = auto_number

    # ------------------------------------------------------------------
    # Validación
    # ------------------------------------------------------------------

    def validate(self, audio_count: int) -> list[str]:
        """
        Comprueba que la configuración es válida para la cantidad de audios.

        Returns:
            Lista de mensajes de error. Vacía = configuración válida.
        """
        errors: list[str] = []

        if self.mode in (NamingMode.CUSTOM, NamingMode.PREFIX_CUSTOM):
            if not self.custom_names:
                errors.append(
                    "La lista de nombres personalizados está vacía. "
                    "Añade al menos un nombre por línea."
                )
            elif len(self.custom_names) < audio_count:
                errors.append(
                    f"La lista tiene {len(self.custom_names)} nombre(s) "
                    f"pero hay {audio_count} audio(s). "
                    f"Se necesitan al menos {audio_count} nombres."
                )

        return errors

    def get_warnings(self, audio_count: int) -> list[str]:
        """
        Devuelve advertencias no bloqueantes (nombres sobrantes, duplicados).
        """
        warnings: list[str] = []

        if self.mode in (NamingMode.CUSTOM, NamingMode.PREFIX_CUSTOM):
            surplus = len(self.custom_names) - audio_count
            if surplus > 0:
                warnings.append(
                    f"La lista tiene {surplus} nombre(s) de más; "
                    f"solo se usarán los primeros {audio_count}."
                )

            # Detectar duplicados en los nombres que se usarán
            slice_ = self.custom_names[:audio_count]
            seen: dict[str, int] = {}
            dupes: list[str] = []
            for name in slice_:
                seen[name] = seen.get(name, 0) + 1
            dupes = [n for n, c in seen.items() if c > 1]
            if dupes:
                warnings.append(
                    f"Nombres duplicados detectados (se auto-corregirán): "
                    + ", ".join(f'"{d}"' for d in dupes)
                )

        return warnings

    # ------------------------------------------------------------------
    # Generación de nombres
    # ------------------------------------------------------------------

    def generate_names(self, audio_paths: list[Path]) -> list[str]:
        """
        Genera la lista final de nombres limpios (sin extensión .mp4).

        - Los nombres se consumen en orden desde custom_names.
        - Los duplicados se auto-corrigen: "Name", "Name (2)", "Name (3)"…
        - Los caracteres inválidos se sustituyen por "_".

        Args:
            audio_paths: Lista ordenada de rutas de audio.

        Returns:
            Lista de strings lista para usar como nombre de archivo.
        """
        raw_names = [
            self._raw_name(idx, audio_path)
            for idx, audio_path in enumerate(audio_paths)
        ]

        # Aplicar numeración antes de deduplicar
        if self.auto_number:
            total = len(raw_names)
            pad = len(str(total))  # ancho de cero: 2 dígitos para <100, 3 para <1000
            pad = max(pad, 2)
            raw_names = [
                f"{(i + 1):0{pad}d} - {n}" for i, n in enumerate(raw_names)
            ]

        # Sanitizar caracteres inválidos
        sanitized = [sanitize_filename(n) for n in raw_names]

        # Auto-fix de duplicados
        final = self._deduplicate(sanitized)
        return final

    def build_output_path(self, name: str, output_folder: str | Path) -> Path:
        """Retorna la ruta completa del archivo de salida (.mp4)."""
        return Path(output_folder) / f"{name}.mp4"

    # ------------------------------------------------------------------
    # Helpers privados
    # ------------------------------------------------------------------

    def _raw_name(self, idx: int, audio_path: Path) -> str:
        """Genera el nombre crudo (sin numeración ni saneamiento) para un audio."""
        stem = audio_path.stem
        mode = self.mode

        if mode == NamingMode.DEFAULT:
            return stem
        elif mode == NamingMode.NAME:
            return self.prefix  # fixed name for all outputs
        elif mode == NamingMode.PREFIX:
            return f"{self.prefix}{stem}"
        elif mode == NamingMode.CUSTOM:
            return self.custom_names[idx]
        elif mode == NamingMode.PREFIX_CUSTOM:
            return f"{self.prefix}{self.custom_names[idx]}"
        return stem  # fallback

    @staticmethod
    def _deduplicate(names: list[str]) -> list[str]:
        """
        Hace únicos los nombres duplicados añadiendo " (2)", " (3)", …
        Mutación in-place sobre una copia.
        """
        result: list[str] = []
        count: dict[str, int] = {}

        for name in names:
            if name not in count:
                count[name] = 1
                result.append(name)
            else:
                count[name] += 1
                unique = f"{name} ({count[name]})"
                result.append(unique)

        return result
