"""Escenarios de roleplay (Fase 3): uno por archivo en backend/scenarios/*.yaml; el id es el nombre del archivo.

Campos: title, description (español, UI) · partner_role, user_role, context, openers (inglés, para Buddy)
· goals (español: lo que debes lograr) · key_phrases (inglés, opcional: frases útiles para la escena).
Para añadir uno basta con soltar otro .yaml y reiniciar.
"""

from pathlib import Path

import yaml

from .prompts import scenario_systems

DIR = Path(__file__).resolve().parents[1] / "scenarios"
REQUIRED = ("title", "description", "partner_role", "user_role", "context", "openers", "goals")


def load(directory: Path = DIR) -> dict[str, dict]:
    scenarios = {}
    for f in sorted(directory.glob("*.yaml")):
        sc = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if missing := [k for k in REQUIRED if not sc.get(k)]:
            raise ValueError(f"Escenario {f.name}: faltan {', '.join(missing)}")
        sc["id"] = f.stem
        sc.setdefault("key_phrases", [])
        sc["systems"] = scenario_systems(sc)
        scenarios[f.stem] = sc
    return scenarios


def public(sc: dict) -> dict:
    """Lo que ve la UI."""
    return {k: sc[k] for k in ("id", "title", "description", "goals", "key_phrases")}
