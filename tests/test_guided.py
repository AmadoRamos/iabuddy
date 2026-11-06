"""Conversación guiada: diálogos de los escenarios, nota de cada frase y mejor resultado."""

import asyncio
import re

from fastapi.testclient import TestClient

from backend.partner import scenarios
from backend.pipeline.turn_manager import MIN_VOICE_FRAMES, Session
from backend.pronunciation.scorer import grade_reading
from backend.storage.db import Store
from tests.test_turn_manager import FakeLLM, FakeSTT, FakeTTS, FakeVad, first

ISSUE = {"phone": "θ", "heard": "t", "tip": "Saca la lengua.", "margin": 6.0}


def word(text, issues=(), unclear=False):
    return {"word": text, "score": 50, "phones": ["a"], "unclear": unclear, "issues": list(issues)}


def result(*words):
    return {"score": 50, "words": list(words)}


def test_every_scenario_has_a_dialog_that_can_be_read_and_graded():
    for sc in scenarios.load().values():
        guided = sc["guided"]
        assert guided, sc["id"]
        for t in guided["turns"]:
            # Whisper escribe los números en cifras y la nota compara palabra por palabra
            assert not re.search(r"\d", t["you"]), t["you"]
            assert len(t["you"].split()) <= 22, t["you"]


def test_a_dialog_with_a_missing_field_fails_at_startup(tmp_path):
    (tmp_path / "x.yaml").write_text(
        "title: t\ndescription: d\npartner_role: p\nuser_role: u\ncontext: c\nopeners: [o]\ngoals: [g]\n"
        "guided:\n  closing: bye\n  turns:\n    - {buddy: hi, you: hello}\n", encoding="utf-8")
    try:
        scenarios.load(tmp_path)
    except ValueError as e:
        assert "guided" in str(e)
    else:
        raise AssertionError("debía fallar")


def test_a_sentence_said_clean_gets_full_marks():
    r = grade_reading(result(word("I'm"), word("on"), word("track")), "I'm on track.")
    assert r["grade"] == 100 and not any(w["missing"] for w in r["words"])


def test_missing_words_count_zero_and_sound_errors_half():
    r = grade_reading(result(word("I"), word("think"), word("we"), word("won")), "I we won")
    assert r["grade"] == 75 and [w["missing"] for w in r["words"]] == [False, True, False, False]
    r = grade_reading(result(word("I"), word("think", [ISSUE]), word("we"), word("won", unclear=True)), "I think we won")
    assert r["grade"] == 75


def test_a_different_sentence_or_nothing_heard_scores_low():
    assert grade_reading(result(word("good"), word("morning")), "the cat sleeps")["grade"] == 0
    assert grade_reading(result(word("good"), word("morning")), "")["grade"] == 0
    assert grade_reading(result(), "good morning")["grade"] == 0


def test_case_does_not_matter():
    assert grade_reading(result(word("I'm"), word("Fine")), "i'm fine")["grade"] == 100


def test_words_that_sound_the_same_count_as_said():
    sound = {"by": "bai", "buy": "bai", "card": "kard"}.get
    assert grade_reading(result(word("by"), word("card")), "buy card", sound)["grade"] == 100


class FakeScorer:
    def __init__(self, score=60):
        self.score = score

    def sound_of(self, w):
        return w.lower()

    def analyze(self, pcm, text):
        return {"score": self.score, "words": [word(w) for w in text.split()]}


def make(store, heard):
    events = []

    async def send_json(m):
        events.append(m)

    async def send_bytes(b):
        events.append(b)

    return Session(send_json=send_json, send_bytes=send_bytes, vad=FakeVad(), stt=FakeSTT(heard), llm=FakeLLM([]), tts=FakeTTS(),
                   silence_ms=900, systems={"voz": "c", "panel": "r", "silencioso": "r"}, greeting="Hi!", store=store,
                   scorer=FakeScorer()), events


async def read(s, **extra):
    await s.on_control({"type": "drill", "text": "good morning team", **extra})
    await s.on_audio(b"\x01" * MIN_VOICE_FRAMES)
    await s.on_control({"type": "stop"})
    await s.task


def test_a_graded_reading_goes_through_whisper_and_says_what_was_missing():
    async def run():
        s, events = make(Store(":memory:"), "good morning")
        await read(s, grade=True)
        r = first(events, "drill_result")
        assert r["heard"] == "good morning" and r["grade"] == 67 and r["passed"] is False
        assert [w["missing"] for w in r["words"]] == [False, False, True]
        assert s.state == "idle" and s.drill_text is None
    asyncio.run(run())


def test_a_reading_whisper_understood_passes_even_with_low_model_confidence():
    async def run():
        s, events = make(Store(":memory:"), "good morning team")
        s.scorer = FakeScorer(score=20)
        await read(s, grade=True)
        r = first(events, "drill_result")
        assert r["grade"] == 100 and r["passed"] is True
    asyncio.run(run())


def test_a_normal_drill_does_not_use_whisper():
    async def run():
        s, events = make(Store(":memory:"), "good morning team")
        await read(s)
        assert s.stt.calls == 0 and "grade" not in first(events, "drill_result")
    asyncio.run(run())


def test_best_result_per_scenario_is_kept_and_the_api_validates_it(monkeypatch, tmp_path):
    from backend import main
    store = Store(tmp_path / "t.db")
    monkeypatch.setattr(main.app.state, "store", store, raising=False)
    c = TestClient(main.app)
    assert c.post("/api/guided", json={"scenario": "restaurant", "grade": 70}).json() == {"best": 70}
    assert c.post("/api/guided", json={"scenario": "restaurant", "grade": 60}).json() == {"best": 70}
    assert c.post("/api/guided", json={"scenario": "nope", "grade": 60}).status_code == 404
    assert c.post("/api/guided", json={"scenario": "restaurant", "grade": 101}).status_code == 422
    listed = {s["id"]: s for s in c.get("/api/scenarios").json()}
    assert listed["restaurant"]["guided_best"] == 70 and listed["hotel_checkin"]["guided_best"] is None
    assert listed["restaurant"]["guided"]["closing"]
