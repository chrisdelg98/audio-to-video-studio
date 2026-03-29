"""Persistence manager for Prompt Lab workspaces, categories and skills."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from core.utils import get_app_dir

_APP_DIR = get_app_dir()
CONFIG_DIR = _APP_DIR / "config"
PROMPT_LAB_FILE = CONFIG_DIR / "prompt_lab.json"
PROMPT_LAB_CATALOG_FILE = CONFIG_DIR / "prompt_lab_catalog.json"

DEFAULT_SKILL_GENERAL_INSTRUCTIONS = """Rol:
Eres un arquitecto de prompts profesional capaz de generar prompts optimizados tanto para música (Suno) como para arte visual (covers). Transformas cualquier input en resultados técnicos, coherentes y listos para producción. No explicas, no agregas contexto, solo entregas prompts finales.

Objetivo:
Convertir descripciones, ideas o prompts existentes en nuevos prompts optimizados, manteniendo coherencia estilística, control técnico y calidad profesional.

Formato de salida:

Entregar únicamente el prompt final
Sin explicaciones, sin encabezados, sin texto adicional
Principios universales
Consistencia de sistema
Todos los outputs deben pertenecer a una misma identidad visual/sonora.
Menos es más
Evitar saturación. Priorizar espacio, claridad y enfoque.
Control técnico explícito
Definir siempre comportamiento, no solo elementos.
No ambigüedad
Usar términos concretos (warm, soft, controlled, minimal).
Optimización automática
Siempre mejorar calidad aunque no se solicite.
Adaptabilidad multimodal
Capacidad de interpretar cualquier input (texto, prompt, idea) y transformarlo coherentemente a otro tipo de prompt (ej: musical -> visual, visual -> musical), manteniendo esencia, mood y estilo.
Interpretación inteligente

Extraer siempre del input:

Mood (emoción principal)
Energía
Estética (ej: cyberpunk, ambient, jazz)
Nivel de complejidad
Intención (focus, sleep, groove, etc.)

Y reconstruirlo en el nuevo dominio manteniendo coherencia.

Para prompts de MÚSICA

Estructura obligatoria:

Tipo de track + estilo
Duración
Tempo
Mood
Sound design
Estructura
Restricciones
Mezcla

Reglas:

Máx 1000 caracteres
Lenguaje técnico
Sin redundancia

Siempre incluir:

no harsh highs
no muddiness
clean mids
controlled reverb (no wash)
balanced low end
clarity

Correcciones automáticas:

Ruido -> no noise, no hiss
Percusión molesta -> avoid noisy percussion
Reverb excesivo -> controlled decay
Sonido agresivo -> soft, controlled

Estructura:

Ambient/sleep -> plana
Groove -> evolución sutil
Sin cambios bruscos
Para prompts de ARTWORK

Estructura obligatoria:

Tipo (square cover)
Contexto musical
Identidad visual
Paleta de color (clave principal)
Elemento visual (abstracto o interpretativo)
Composición
Detalles sutiles
Tipografía
Restricciones
Mood
Calidad

Reglas:

Minimalismo obligatorio
No clutter
No ilustraciones complejas
No estilo cartoon
No stock look

Color:

Elemento principal de variación y coherencia.
Siempre cinematográfico, con gradientes suaves.

Detalles:

grain
partículas
fog
light streaks
glow

Siempre sutiles.

Tipografía:

pequeña/media
consistente
no dominante
Sistema de transformación (clave)

Capacidad de:

Convertir descripciones en prompts
Refinar prompts existentes
Traducir intención entre dominios (sonido <-> imagen)
Mantener coherencia estética entre outputs
Preservar mood, energía y estilo sin copiar estructura literal
Sistema de coherencia

Todos los prompts deben:

Sentirse parte de una misma marca
Variar sin romper identidad
Ser reutilizables en series
Sistema anti-errores

Nunca permitir:

Saturación
Ruido
Falta de claridad
Inconsistencia

Siempre forzar:

limpieza
balance
elegancia
intención clara
Resultado esperado

Prompts:

Profesionales
Consistentes
Reutilizables
Técnicamente correctos
Adaptables entre formatos
Optimizados para generación real de contenido"""


_DEFAULT_DATA: dict[str, Any] = {
    "version": 1,
    "workspaces": [
        {
            "name": "General",
            "description": "Workspace base para ideas y prompts.",
            "categories": [
                {
                    "name": "General",
                    "preload_skills": ["Skill General"],
                    "skills": [
                        {
                            "name": "Skill General",
                            "description": "",
                            "prompt_template": "",
                            "instructions": DEFAULT_SKILL_GENERAL_INSTRUCTIONS,
                            "updated_at": "",
                        }
                    ],
                }
            ],
        }
    ],
}


@dataclass
class PromptSkill:
    name: str
    instructions: str
    description: str = ""
    prompt_template: str = ""


@dataclass
class SkillRevision:
    version: int
    updated_at: str
    instructions: str


class PromptLabManager:
    """CRUD JSON for Prompt Lab entities."""

    def __init__(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if PROMPT_LAB_FILE.exists():
            try:
                raw = json.loads(PROMPT_LAB_FILE.read_text(encoding="utf-8"))
                self._data = self._normalize(raw)
                return
            except Exception:
                pass
        self._data = self._normalize(_DEFAULT_DATA)
        self.save()

    def save(self) -> None:
        PROMPT_LAB_FILE.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def app_version(self) -> int:
        return int(self._data.get("version", 1))

    def workspaces(self) -> list[str]:
        return [w["name"] for w in self._data.get("workspaces", []) if isinstance(w, dict)]

    def categories(self, workspace_name: str) -> list[str]:
        ws = self._find_workspace(workspace_name)
        if not ws:
            return []
        return [c["name"] for c in ws.get("categories", []) if isinstance(c, dict)]

    def skills(self, workspace_name: str, category_name: str) -> list[str]:
        cat = self._find_category(workspace_name, category_name)
        if not cat:
            return []
        return [s["name"] for s in cat.get("skills", []) if isinstance(s, dict)]

    def skill_objects(self, workspace_name: str, category_name: str) -> list[PromptSkill]:
        cat = self._find_category(workspace_name, category_name)
        if not cat:
            return []
        out: list[PromptSkill] = []
        for skill in cat.get("skills", []):
            if isinstance(skill, dict):
                nm = str(skill.get("name", "")).strip()
                if not nm:
                    continue
                out.append(
                    PromptSkill(
                        name=nm,
                        instructions=str(skill.get("instructions", "")).strip(),
                        description=str(skill.get("description", "")).strip(),
                        prompt_template=str(skill.get("prompt_template", "")).strip(),
                    )
                )
        return out

    def category_preload_skills(self, workspace_name: str, category_name: str) -> list[str]:
        cat = self._find_category(workspace_name, category_name)
        if not cat:
            return []

        available = set(self.skills(workspace_name, category_name))
        raw = cat.get("preload_skills", [])
        out: list[str] = []
        if isinstance(raw, list):
            for item in raw:
                nm = str(item).strip()
                if not nm or nm not in available or nm in out:
                    continue
                out.append(nm)
        return out

    def set_category_preload_skills(
        self,
        workspace_name: str,
        category_name: str,
        skill_names: list[str],
    ) -> None:
        cat = self._find_category(workspace_name, category_name)
        if not cat:
            raise ValueError("Categoria no encontrada.")

        available = set(self.skills(workspace_name, category_name))
        cleaned: list[str] = []
        for item in skill_names:
            nm = str(item).strip()
            if not nm or nm not in available or nm in cleaned:
                continue
            cleaned.append(nm)

        cat["preload_skills"] = cleaned
        self.save()

    def get_skill(self, workspace_name: str, category_name: str, skill_name: str) -> PromptSkill | None:
        cat = self._find_category(workspace_name, category_name)
        if not cat:
            return None
        for skill in cat.get("skills", []):
            if isinstance(skill, dict) and str(skill.get("name", "")).strip() == skill_name:
                return PromptSkill(
                    name=str(skill.get("name", "")).strip(),
                    instructions=str(skill.get("instructions", "")).strip(),
                    description=str(skill.get("description", "")).strip(),
                    prompt_template=str(skill.get("prompt_template", "")).strip(),
                )
        return None

    def skill_versions(self, workspace_name: str, category_name: str, skill_name: str) -> list[SkillRevision]:
        cat = self._find_category(workspace_name, category_name)
        if not cat:
            return []
        for skill in cat.get("skills", []):
            if isinstance(skill, dict) and str(skill.get("name", "")).strip() == skill_name:
                revisions = skill.get("revisions", [])
                if not isinstance(revisions, list):
                    return []
                out: list[SkillRevision] = []
                for rev in revisions:
                    if not isinstance(rev, dict):
                        continue
                    try:
                        out.append(
                            SkillRevision(
                                version=int(rev.get("version", 1)),
                                updated_at=str(rev.get("updated_at", "")).strip(),
                                instructions=str(rev.get("instructions", "")),
                            )
                        )
                    except Exception:
                        continue
                return sorted(out, key=lambda r: r.version)
        return []

    def restore_skill_version(
        self,
        workspace_name: str,
        category_name: str,
        skill_name: str,
        version: int,
    ) -> None:
        cat = self._find_category(workspace_name, category_name)
        if not cat:
            raise ValueError("Categoria no encontrada.")
        for skill in cat.get("skills", []):
            if isinstance(skill, dict) and str(skill.get("name", "")).strip() == skill_name:
                revisions = skill.get("revisions", [])
                if not isinstance(revisions, list):
                    raise ValueError("La skill no tiene historial.")
                for rev in revisions:
                    if not isinstance(rev, dict):
                        continue
                    if int(rev.get("version", -1)) == int(version):
                        self.upsert_skill(
                            workspace_name=workspace_name,
                            category_name=category_name,
                            skill_name=skill_name,
                            instructions=str(rev.get("instructions", "")),
                        )
                        return
                raise ValueError("Version no encontrada.")
        raise ValueError("Skill no encontrada.")

    def create_workspace(self, name: str) -> None:
        nm = name.strip()
        if not nm:
            raise ValueError("Nombre de workspace vacio.")
        if self._find_workspace(nm):
            raise ValueError("Ya existe un workspace con ese nombre.")
        self._data.setdefault("workspaces", []).append(
            {
                "name": nm,
                "description": "",
                "categories": [{"name": "General", "skills": [], "preload_skills": []}],
            }
        )
        self.save()

    def export_workspace(self, workspace_name: str, output_file: Path) -> None:
        ws = self._find_workspace(workspace_name)
        if not ws:
            raise ValueError("Workspace no encontrado.")
        payload = {
            "schema": "prompt-lab-workspace",
            "version": self.app_version(),
            "exported_at": datetime.utcnow().isoformat(timespec="seconds"),
            "workspace": ws,
        }
        output_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    def import_workspace(self, input_file: Path, *, replace_if_exists: bool = True) -> str:
        try:
            raw = json.loads(input_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"No se pudo leer el archivo: {exc}") from exc

        if not isinstance(raw, dict):
            raise ValueError("Formato invalido de importacion.")

        ws = raw.get("workspace")
        if not isinstance(ws, dict):
            raise ValueError("El archivo no contiene un workspace valido.")

        ws_name = str(ws.get("name", "")).strip()
        if not ws_name:
            raise ValueError("El workspace importado no tiene nombre.")

        normalized_ws = self._normalize({"workspaces": [ws]}).get("workspaces", [])[0]
        existing = self._find_workspace(ws_name)

        if existing and not replace_if_exists:
            raise ValueError("Ya existe un workspace con ese nombre.")

        if existing and replace_if_exists:
            self._data["workspaces"] = [
                w for w in self._data.get("workspaces", [])
                if str(w.get("name", "")).strip() != ws_name
            ]

        self._data.setdefault("workspaces", []).append(normalized_ws)
        self.save()
        return ws_name

    def delete_workspace(self, name: str) -> None:
        items = self._data.get("workspaces", [])
        if len(items) <= 1:
            raise ValueError("Debe existir al menos un workspace.")
        kept = [w for w in items if str(w.get("name", "")).strip() != name]
        if len(kept) == len(items):
            raise ValueError("Workspace no encontrado.")
        self._data["workspaces"] = kept
        self.save()

    def ensure_category(self, workspace_name: str, category_name: str) -> None:
        ws = self._find_workspace(workspace_name)
        if not ws:
            raise ValueError("Workspace no encontrado.")
        nm = category_name.strip()
        if not nm:
            raise ValueError("Nombre de categoria vacio.")
        for cat in ws.get("categories", []):
            if str(cat.get("name", "")).strip() == nm:
                return
        ws.setdefault("categories", []).append({"name": nm, "skills": [], "preload_skills": []})
        self.save()

    def delete_category(self, workspace_name: str, category_name: str) -> None:
        ws = self._find_workspace(workspace_name)
        if not ws:
            raise ValueError("Workspace no encontrado.")
        nm = category_name.strip()
        if not nm:
            raise ValueError("Nombre de categoria vacio.")
        if nm.lower() == "general":
            raise ValueError("La categoria General no se puede eliminar.")

        categories = [c for c in ws.get("categories", []) if isinstance(c, dict)]
        kept = [c for c in categories if str(c.get("name", "")).strip() != nm]
        if len(kept) == len(categories):
            raise ValueError("Categoria no encontrada.")
        if not kept:
            kept = [{"name": "General", "skills": [], "preload_skills": []}]
        ws["categories"] = kept
        self.save()

    def delete_skill(self, workspace_name: str, category_name: str, skill_name: str) -> None:
        cat = self._find_category(workspace_name, category_name)
        if not cat:
            raise ValueError("Categoria no encontrada.")

        target = skill_name.strip()
        if not target:
            raise ValueError("Nombre de skill vacio.")

        skills = [s for s in cat.get("skills", []) if isinstance(s, dict)]
        kept = [s for s in skills if str(s.get("name", "")).strip() != target]
        if len(kept) == len(skills):
            raise ValueError("Skill no encontrada.")
        if not kept:
            raise ValueError("Debe quedar al menos una skill en la categoria.")

        cat["skills"] = kept
        self.save()

    def upsert_skill(
        self,
        workspace_name: str,
        category_name: str,
        skill_name: str,
        instructions: str,
        description: str = "",
        prompt_template: str | None = None,
    ) -> None:
        self.ensure_category(workspace_name, category_name)
        cat = self._find_category(workspace_name, category_name)
        if not cat:
            raise ValueError("Categoria no encontrada.")

        nm = skill_name.strip()
        if not nm:
            raise ValueError("Nombre de skill vacio.")

        now = datetime.utcnow().isoformat(timespec="seconds")
        for skill in cat.get("skills", []):
            if str(skill.get("name", "")).strip() == nm:
                skill["instructions"] = instructions.strip()
                skill["description"] = description.strip()
                if prompt_template is not None:
                    skill["prompt_template"] = prompt_template.strip()
                skill["updated_at"] = now
                revisions = skill.setdefault("revisions", [])
                if not isinstance(revisions, list):
                    revisions = []
                    skill["revisions"] = revisions
                next_version = 1
                if revisions:
                    next_version = max(int(r.get("version", 0)) for r in revisions if isinstance(r, dict)) + 1
                revisions.append(
                    {
                        "version": next_version,
                        "updated_at": now,
                        "instructions": instructions.strip(),
                    }
                )
                self.save()
                return

        first_revision = {
            "version": 1,
            "updated_at": now,
            "instructions": instructions.strip(),
        }
        cat.setdefault("skills", []).append(
            {
                "name": nm,
                "instructions": instructions.strip(),
                "description": description.strip(),
                "prompt_template": (prompt_template or "").strip(),
                "updated_at": now,
                "revisions": [first_revision],
            }
        )
        self.save()

    def edit_skill(
        self,
        workspace_name: str,
        source_category_name: str,
        source_skill_name: str,
        target_category_name: str,
        target_skill_name: str,
        instructions: str,
        description: str = "",
        prompt_template: str | None = None,
    ) -> None:
        ws = self._find_workspace(workspace_name)
        if not ws:
            raise ValueError("Workspace no encontrado.")

        source_category = self._find_category(workspace_name, source_category_name)
        if not source_category:
            raise ValueError("Categoria de origen no encontrada.")

        src_name = source_skill_name.strip()
        dst_name = target_skill_name.strip()
        dst_category_name = target_category_name.strip()
        if not src_name:
            raise ValueError("Nombre de skill origen vacio.")
        if not dst_name:
            raise ValueError("Nombre de skill destino vacio.")
        if not dst_category_name:
            raise ValueError("Categoria destino vacia.")

        source_skill: dict[str, Any] | None = None
        source_index = -1
        source_skills = source_category.get("skills", [])
        if not isinstance(source_skills, list):
            raise ValueError("Categoria de origen invalida.")
        for idx, item in enumerate(source_skills):
            if isinstance(item, dict) and str(item.get("name", "")).strip() == src_name:
                source_skill = item
                source_index = idx
                break

        if source_skill is None or source_index < 0:
            raise ValueError("Skill origen no encontrada.")

        self.ensure_category(workspace_name, dst_category_name)
        target_category = self._find_category(workspace_name, dst_category_name)
        if not target_category:
            raise ValueError("Categoria destino no encontrada.")

        target_skills = target_category.get("skills", [])
        if not isinstance(target_skills, list):
            target_skills = []
            target_category["skills"] = target_skills

        if source_category_name.strip() == dst_category_name and src_name == dst_name:
            self.upsert_skill(
                workspace_name=workspace_name,
                category_name=dst_category_name,
                skill_name=dst_name,
                instructions=instructions,
                description=description,
                prompt_template=prompt_template,
            )
            return

        for item in target_skills:
            if not isinstance(item, dict):
                continue
            existing_name = str(item.get("name", "")).strip()
            if existing_name != dst_name:
                continue
            # Skip self-match when source and target are the same list item.
            if source_category is target_category and item is source_skill:
                continue
            raise ValueError("Ya existe una skill con ese nombre en la categoria destino.")

        now = datetime.utcnow().isoformat(timespec="seconds")
        revisions = source_skill.get("revisions", [])
        if not isinstance(revisions, list):
            revisions = []
        next_version = 1
        if revisions:
            next_version = max(int(r.get("version", 0)) for r in revisions if isinstance(r, dict)) + 1
        revisions.append(
            {
                "version": next_version,
                "updated_at": now,
                "instructions": instructions.strip(),
            }
        )

        updated_skill = {
            "name": dst_name,
            "instructions": instructions.strip(),
            "description": description.strip(),
            "prompt_template": (
                prompt_template.strip()
                if prompt_template is not None
                else str(source_skill.get("prompt_template", "")).strip()
            ),
            "updated_at": now,
            "revisions": revisions,
        }

        # Remove source entry before inserting destination if category or name changed.
        del source_skills[source_index]
        target_skills.append(updated_skill)
        self.save()

    def catalog_file(self) -> Path:
        return PROMPT_LAB_CATALOG_FILE

    def write_initial_catalog_template(self, workspace_name: str) -> Path:
        ws_name = workspace_name.strip() or "General"
        categories = self.categories(ws_name) or ["General"]
        payload = {
            "schema": "prompt-lab-catalog",
            "version": 1,
            "workspace": ws_name,
            "notes": (
                "Completa las instrucciones para cada skill. "
                "La instalacion no modifica skills existentes con el mismo nombre."
            ),
            "categories": [],
        }

        for cat in categories:
            clean = str(cat).strip() or "General"
            payload["categories"].append(
                {
                    "name": clean,
                    "preload_skills": [f"{clean} Base"],
                    "skills": [
                        {
                            "name": f"{clean} Base",
                            "description": f"Skill principal propuesta para {clean}.",
                            "prompt_template": "",
                            "instructions": "",
                        }
                    ],
                }
            )

        PROMPT_LAB_CATALOG_FILE.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return PROMPT_LAB_CATALOG_FILE

    def install_catalog(
        self,
        workspace_name: str,
        catalog_file: Path,
        *,
        overwrite_existing: bool = False,
    ) -> dict[str, int]:
        ws_name = workspace_name.strip() or "General"
        ws = self._find_workspace(ws_name)
        if not ws:
            raise ValueError("Workspace no encontrado.")

        try:
            raw = json.loads(catalog_file.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"No se pudo leer catalogo: {exc}") from exc

        if not isinstance(raw, dict):
            raise ValueError("Catalogo invalido.")

        categories_raw = raw.get("categories", [])
        if not isinstance(categories_raw, list):
            raise ValueError("Catalogo invalido: categories debe ser lista.")

        created = 0
        updated = 0
        skipped = 0

        for cat in categories_raw:
            if not isinstance(cat, dict):
                continue
            cat_name = str(cat.get("name", "")).strip()
            if not cat_name:
                continue
            self.ensure_category(ws_name, cat_name)

            skills_raw = cat.get("skills", [])
            if not isinstance(skills_raw, list):
                continue

            for item in skills_raw:
                if not isinstance(item, dict):
                    continue
                skill_name = str(item.get("name", "")).strip()
                instructions = str(item.get("instructions", "")).strip()
                description = str(item.get("description", "")).strip()
                prompt_template = str(item.get("prompt_template", "")).strip()
                preload_flag = bool(item.get("preload", False))
                if not skill_name or not instructions:
                    skipped += 1
                    continue

                existing = self.get_skill(ws_name, cat_name, skill_name)
                if existing and not overwrite_existing:
                    skipped += 1
                    continue

                self.upsert_skill(
                    workspace_name=ws_name,
                    category_name=cat_name,
                    skill_name=skill_name,
                    instructions=instructions,
                    description=description,
                    prompt_template=prompt_template,
                )
                if existing:
                    updated += 1
                else:
                    created += 1

                if preload_flag:
                    current_preload = self.category_preload_skills(ws_name, cat_name)
                    if skill_name not in current_preload:
                        current_preload.append(skill_name)
                    self.set_category_preload_skills(ws_name, cat_name, current_preload)

            cat_preload_raw = cat.get("preload_skills", [])
            if isinstance(cat_preload_raw, list):
                preload_names = [str(v).strip() for v in cat_preload_raw if str(v).strip()]
                if preload_names:
                    self.set_category_preload_skills(ws_name, cat_name, preload_names)

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
        }

    def _find_workspace(self, name: str) -> dict[str, Any] | None:
        target = name.strip()
        for ws in self._data.get("workspaces", []):
            if isinstance(ws, dict) and str(ws.get("name", "")).strip() == target:
                return ws
        return None

    def _find_category(self, workspace_name: str, category_name: str) -> dict[str, Any] | None:
        ws = self._find_workspace(workspace_name)
        if not ws:
            return None
        target = category_name.strip()
        for cat in ws.get("categories", []):
            if isinstance(cat, dict) and str(cat.get("name", "")).strip() == target:
                return cat
        return None

    def _normalize(self, raw: Any) -> dict[str, Any]:
        data = dict(_DEFAULT_DATA)
        if not isinstance(raw, dict):
            return data

        raw_workspaces = raw.get("workspaces", [])
        normalized_workspaces: list[dict[str, Any]] = []
        if isinstance(raw_workspaces, list):
            for ws in raw_workspaces:
                if not isinstance(ws, dict):
                    continue
                ws_name = str(ws.get("name", "")).strip()
                if not ws_name:
                    continue
                raw_categories = ws.get("categories", [])
                categories: list[dict[str, Any]] = []
                if isinstance(raw_categories, list):
                    for cat in raw_categories:
                        if not isinstance(cat, dict):
                            continue
                        cat_name = str(cat.get("name", "")).strip()
                        if not cat_name:
                            continue
                        preload_raw = cat.get("preload_skills", [])
                        preload_skills: list[str] = []
                        if isinstance(preload_raw, list):
                            for item in preload_raw:
                                nm = str(item).strip()
                                if nm and nm not in preload_skills:
                                    preload_skills.append(nm)
                        raw_skills = cat.get("skills", [])
                        skills: list[dict[str, Any]] = []
                        if isinstance(raw_skills, list):
                            for skill in raw_skills:
                                if not isinstance(skill, dict):
                                    continue
                                sk_name = str(skill.get("name", "")).strip()
                                if not sk_name:
                                    continue
                                sk_instructions = str(skill.get("instructions", "")).strip()
                                sk_description = str(skill.get("description", "")).strip()
                                sk_prompt_template = str(skill.get("prompt_template", "")).strip()
                                sk_updated_at = str(skill.get("updated_at", "")).strip()
                                revisions_raw = skill.get("revisions", [])
                                revisions: list[dict[str, Any]] = []
                                if isinstance(revisions_raw, list):
                                    for rev in revisions_raw:
                                        if not isinstance(rev, dict):
                                            continue
                                        try:
                                            rev_version = int(rev.get("version", 1))
                                        except Exception:
                                            rev_version = 1
                                        revisions.append(
                                            {
                                                "version": rev_version,
                                                "updated_at": str(rev.get("updated_at", "")).strip(),
                                                "instructions": str(rev.get("instructions", "")),
                                            }
                                        )
                                if not revisions:
                                    revisions = [
                                        {
                                            "version": 1,
                                            "updated_at": sk_updated_at,
                                            "instructions": sk_instructions,
                                        }
                                    ]
                                skills.append(
                                    {
                                        "name": sk_name,
                                        "instructions": sk_instructions,
                                        "description": sk_description,
                                        "prompt_template": sk_prompt_template,
                                        "updated_at": sk_updated_at,
                                        "revisions": revisions,
                                    }
                                )
                        # Keep only preload names that still exist in the category.
                        available_names = {str(s.get("name", "")).strip() for s in skills if isinstance(s, dict)}
                        preload_skills = [nm for nm in preload_skills if nm in available_names]
                        categories.append({"name": cat_name, "skills": skills, "preload_skills": preload_skills})
                if not categories:
                    categories = [{"name": "General", "skills": [], "preload_skills": []}]
                normalized_workspaces.append(
                    {
                        "name": ws_name,
                        "description": str(ws.get("description", "")).strip(),
                        "categories": categories,
                    }
                )

        if not normalized_workspaces:
            normalized_workspaces = _DEFAULT_DATA["workspaces"]

        data["version"] = 1
        data["workspaces"] = normalized_workspaces
        return data
