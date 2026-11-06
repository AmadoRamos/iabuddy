"""Vocabulario (Fase 6): paquetes de palabras por tema y cómo saber si usaste una al hablar.

Los paquetes viven en packs.yaml, uno por título de tema o id de escenario; «General» es para la
conversación libre y para cuando se acaba el paquete del tema.
"""

import re
from pathlib import Path

import yaml

GENERAL = "General"
SEPARATOR = r"[\s,.;:!?-]"  # entre las palabras de una expresión: Whisper puntúa a su manera
# Un YAML mal escrito falla al arrancar, no a mitad de sesión
PACKS: dict[str, list[dict]] = yaml.safe_load(Path(__file__).with_name("packs.yaml").read_text(encoding="utf-8"))


def pack_for(name: str | None) -> list[dict]:
    """Las palabras del tema o escenario y, detrás, las generales."""
    own = PACKS.get(name, []) if name else []
    return [{"key": w["term"].lower(), "term": w["term"], "meaning": w["es"], "example": w["ex"],
             "forms": w.get("forms", []), "source": "pack"} for w in [*own, *PACKS[GENERAL]]]


def _inflected(word: str) -> str:
    """Una palabra con sus terminaciones regulares. Las irregulares van en `forms`."""
    if word.endswith("e"):
        return f"{re.escape(word[:-1])}(?:e|es|ed|ing)"
    if re.search(r"[^aeiou]y$", word):
        return f"{re.escape(word[:-1])}(?:y|ies|ied|ying)"
    last = re.escape(word[-1])
    return f"{re.escape(word)}(?:s|es|ed|ing|{last}ed|{last}ing)?"


def uses(text: str, term: str, forms: list[str] = ()) -> bool:
    return bool(find_use(text, term, forms))


def find_use(text: str, term: str, forms: list[str] = ()) -> str:
    """Cómo aparece la palabra en lo que dijiste, o "". Whisper escribe igual trade-off, trade off o tradeoff."""
    # ponytail: sin lematizador; una irregular que falte en `forms` no se detecta (no castiga: solo no suma)
    variants = [f"{SEPARATOR}*".join(_inflected(w) for w in re.split(f"{SEPARATOR}+", v.lower()) if w) for v in (term, *forms)]
    found = re.search(rf"(?<!\w)(?:{'|'.join(variants)})(?!\w)", text, re.IGNORECASE)
    return found.group() if found else ""
