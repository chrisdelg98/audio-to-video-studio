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

_DEFAULT_DATA: dict[str, Any] = {
    "version": 1,
    "workspaces": [
        {
            "name": "General",
            "description": "Workspace base para ideas y prompts.",
            "categories": [
                {
                    "name": "General",
                    "skills": [
                        {
                            "name": "Asistente General",
                            "instructions": "Responde en espanol claro y con foco en ejecucion.",
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

    def get_skill(self, workspace_name: str, category_name: str, skill_name: str) -> PromptSkill | None:
        cat = self._find_category(workspace_name, category_name)
        if not cat:
            return None
        for skill in cat.get("skills", []):
            if isinstance(skill, dict) and str(skill.get("name", "")).strip() == skill_name:
                return PromptSkill(
                    name=str(skill.get("name", "")).strip(),
                    instructions=str(skill.get("instructions", "")).strip(),
                )
        return None

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
                "categories": [{"name": "General", "skills": []}],
            }
        )
        self.save()

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
        ws.setdefault("categories", []).append({"name": nm, "skills": []})
        self.save()

    def upsert_skill(
        self,
        workspace_name: str,
        category_name: str,
        skill_name: str,
        instructions: str,
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
                skill["updated_at"] = now
                self.save()
                return

        cat.setdefault("skills", []).append(
            {
                "name": nm,
                "instructions": instructions.strip(),
                "updated_at": now,
            }
        )
        self.save()

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
                        raw_skills = cat.get("skills", [])
                        skills: list[dict[str, str]] = []
                        if isinstance(raw_skills, list):
                            for skill in raw_skills:
                                if not isinstance(skill, dict):
                                    continue
                                sk_name = str(skill.get("name", "")).strip()
                                if not sk_name:
                                    continue
                                skills.append(
                                    {
                                        "name": sk_name,
                                        "instructions": str(skill.get("instructions", "")).strip(),
                                        "updated_at": str(skill.get("updated_at", "")).strip(),
                                    }
                                )
                        categories.append({"name": cat_name, "skills": skills})
                if not categories:
                    categories = [{"name": "General", "skills": []}]
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
