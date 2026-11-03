"""Tutor: analiza cada turno del usuario y devuelve sus errores (TODO §1.3).

- Corrige todo: gramática, vocabulario y naturalidad/estilo.
- Explicaciones en español, para el panel y el resumen. En voz corrige Buddy dentro de su respuesta
  (partner/prompts.py); el tutor no espera a nadie ni retrasa la conversación.
- Mismo LLM que el compañero (S2), desde que suena su respuesta: si arranca antes, la retrasa.
"""

SYSTEM = """You are an English tutor for a Spanish-speaking learner at B1-B2 level. You get one \
sentence the learner just SAID (speech transcribed automatically: ignore punctuation, \
capitalization and filler words like "um"), plus what their conversation partner said before.

Report every real error in the learner's sentence:
- "grammar": tenses, agreement, articles, prepositions, word order...
- "vocabulary": wrong or invented word, false friends (Spanish-influenced words)
- "naturalness": correct but unnatural or un-idiomatic for a native speaker

Correct only HOW the learner said it, never WHAT they said: keep their ideas and words even if \
they seem odd or don't match the conversation. The partner's line is only context.

For each issue: "original" is the exact wrong fragment, "fix" its replacement, \
"explanation_es" ONE short sentence in Spanish, "severity" 1 (minor) to 3 (blocks understanding).
"corrected": the whole sentence fixed. "better": how a native would naturally say it.
If the sentence is fine, return no issues and copy it into "corrected" and "better"."""

SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["grammar", "vocabulary", "naturalness"]},
                "original": {"type": "string"},
                "fix": {"type": "string"},
                "explanation_es": {"type": "string"},
                "severity": {"type": "integer", "minimum": 1, "maximum": 3},
            },
            "required": ["type", "original", "fix", "explanation_es", "severity"],
        }},
        "corrected": {"type": "string"},
        "better": {"type": "string"},
    },
    "required": ["issues", "corrected", "better"],
}


INTENT_SYSTEM = """You are an English tutor for a Spanish-speaking learner at B1-B2 level. The learner \
tried to say something in English (speech transcribed automatically: ignore punctuation, \
capitalization and filler words) and then WROTE what they actually meant, in Spanish or English.

"english": the natural English sentence that says exactly what they meant, at B1-B2 level, \
reusing their own words where they were right. Keep their meaning; don't add ideas.
"issues": compare what they SAID with "english": each wrong, missing or Spanish-influenced \
fragment of what they said. "original" is the fragment they said (or "" if it was missing), "fix" \
what they should say, "explanation_es" ONE short sentence in Spanish, "severity" 1 to 3, "type" \
grammar | vocabulary | naturalness.
"better": an even more natural way a native would say it (may equal "english")."""

INTENT_SCHEMA = {
    "type": "object",
    "properties": {"english": {"type": "string"}, "issues": SCHEMA["properties"]["issues"],
                   "better": {"type": "string"}},
    "required": ["english", "issues", "better"],
}


GOALS_SYSTEM = """You evaluate a role-play where a Spanish-speaking learner at B1-B2 level practices \
spoken English with a partner. You get the scene, the learner's goals (written in Spanish) and the \
transcript (automatic speech transcription: ignore punctuation and filler words).

For EACH goal, in the same order: "met" is true only if the LEARNER clearly did it somewhere in the \
transcript (trying counts, even with grammar mistakes; the partner doing it does not count). \
"evidence": a short quote of the learner's own words that shows it, or "" if not met.
"comment_es": two short sentences in Spanish for the learner: what went well in this scene and one \
concrete thing to improve."""


def _goals_schema(n: int) -> dict:
    goal = {"type": "object", "properties": {"met": {"type": "boolean"}, "evidence": {"type": "string"}},
            "required": ["met", "evidence"]}
    return {"type": "object",
            "properties": {"goals": {"type": "array", "items": goal, "minItems": n, "maxItems": n},
                           "comment_es": {"type": "string"}},
            "required": ["goals", "comment_es"]}


def _same(a: str, b: str) -> bool:
    return a.strip(" .,!?").lower() == b.strip(" .,!?").lower()


def clean(result: dict) -> dict:
    """Quita el ruido del modelo: correcciones que no cambian nada (S2: «since → since»)."""
    # original vacío solo vale si falta algo (fix con contenido): pasa con la intención escrita
    issues = [i for i in result.get("issues", []) if (i["original"].strip() or i["fix"].strip())
              and not _same(i["original"], i["fix"])]
    for i in issues:
        i["severity"] = min(3, max(1, int(i["severity"])))
    return {"issues": issues, "corrected": result.get("corrected", ""), "better": result.get("better", "")}


class Tutor:
    def __init__(self, llm):
        self.llm = llm

    async def analyze(self, text: str, partner_said: str = "") -> dict:
        user = f'Partner said: "{partner_said}"\nLearner said: "{text}"' if partner_said else f'Learner said: "{text}"'
        msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        return clean(await self.llm.chat_json(msgs, SCHEMA))

    async def analyze_intent(self, said: str, intent: str) -> dict:
        """Lo que dijiste frente a lo que escribiste que querías decir → cómo decirlo en inglés."""
        user = f'Learner SAID: "{said}"\nLearner MEANT (written): "{intent}"'
        msgs = [{"role": "system", "content": INTENT_SYSTEM}, {"role": "user", "content": user}]
        r = await self.llm.chat_json(msgs, INTENT_SCHEMA)
        return clean({"issues": r.get("issues", []), "corrected": r.get("english", ""), "better": r.get("better", "")})

    async def check_goals(self, scenario: dict, transcript: str) -> dict:
        """Objetivos del escenario cumplidos en la conversación → {"met", "evidence", "comment_es"}."""
        goals = scenario["goals"]
        user = (f"Scene: {scenario['context']}\nLearner plays: {scenario['user_role']}\n"
                f"Partner plays: {scenario['partner_role']}\n\nGoals:\n"
                + "\n".join(f"{i + 1}. {g}" for i, g in enumerate(goals))
                + f"\n\nTranscript:\n{transcript}")
        msgs = [{"role": "system", "content": GOALS_SYSTEM}, {"role": "user", "content": user}]
        r = await self.llm.chat_json(msgs, _goals_schema(len(goals)))
        got = (r.get("goals") or [])[:len(goals)]
        got += [{"met": False, "evidence": ""}] * (len(goals) - len(got))  # por si el modelo devuelve menos
        met = [bool(g.get("met")) for g in got]
        # El modelo a veces cita algo aunque el objetivo no se haya cumplido: esa cita no demuestra nada
        evidence = [str(g.get("evidence", "")) if m else "" for g, m in zip(got, met, strict=True)]
        return {"met": met, "evidence": evidence, "comment_es": r.get("comment_es", "")}
