"""El tutor real con un LLM falso: qué le pide al modelo y qué hace con su respuesta."""

from backend.tutor.tutor import Tutor


class FakeLLM:
    def __init__(self, answer: dict):
        self.answer, self.user = answer, None

    async def chat_json(self, messages, schema):
        self.user = messages[-1]["content"]
        return self.answer


def issue(original, fix, severity=2):
    return {"type": "grammar", "original": original, "fix": fix, "explanation_es": "Porque sí.", "severity": severity}


async def test_analyze_gives_the_model_what_buddy_said_and_cleans_its_answer():
    llm = FakeLLM({"issues": [issue("I go", "I went", 9), issue("since", "Since."), issue("a", "an", 0)],
                   "corrected": "I went.", "better": "I hit the gym."})
    r = await Tutor(llm).analyze("I go", "How was it?")
    assert '"How was it?"' in llm.user and '"I go"' in llm.user
    assert [(i["fix"], i["severity"]) for i in r["issues"]] == [("I went", 3), ("an", 1)]  # sin «since → Since.»
    assert r["corrected"] == "I went." and r["better"] == "I hit the gym."
    await Tutor(llm).analyze("I go")
    assert "Partner said" not in llm.user


async def test_analyze_intent_compares_what_you_said_with_what_you_meant():
    llm = FakeLLM({"issues": [issue("", "for myself"), issue("", "")], "english": "I did it for myself.", "better": "x"})
    r = await Tutor(llm).analyze_intent("for my five cell", "para mí")
    assert '"for my five cell"' in llm.user and '"para mí"' in llm.user
    assert r["corrected"] == "I did it for myself." and r["better"] == "x"
    assert [i["fix"] for i in r["issues"]] == ["for myself"]  # lo que faltó vale sin original; lo vacío, no


async def test_define_cleans_the_answer_and_keeps_your_word_if_the_model_gives_none():
    llm = FakeLLM({"term": " run out of ", "meaning_es": " quedarse sin ", "example": " We ran out. ",
                   "forms": [" ran out of ", " "]})
    assert await Tutor(llm).define("ran", "We ran out of time") == {
        "term": "run out of", "meaning": "quedarse sin", "example": "We ran out.", "forms": ["ran out of"]}
    assert '"ran"' in llm.user and '"We ran out of time"' in llm.user
    llm.answer = {**llm.answer, "term": "  "}
    assert (await Tutor(llm).define("ran", "We ran"))["term"] == "ran"


async def test_check_usage_gives_the_verdict_and_a_correction_only_if_it_changes_something():
    llm = FakeLLM({"used_well": False, "comment_es": " No encaja. ", "corrected": " My data is stale. "})
    r = await Tutor(llm).check_usage("stale", "pasado", "My brother is stale")
    assert r == {"ok": False, "comment": "No encaja.", "corrected": "My data is stale."}
    assert '"stale"' in llm.user and "pasado" in llm.user and '"My brother is stale"' in llm.user
    llm.answer = {"used_well": True, "comment_es": "Bien.", "corrected": "my data is stale"}
    r = await Tutor(llm).check_usage("stale", "pasado", "My data is stale.")
    assert r == {"ok": True, "comment": "Bien.", "corrected": ""}  # solo cambiaban la mayúscula y el punto
