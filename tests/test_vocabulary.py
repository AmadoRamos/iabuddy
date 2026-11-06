"""Fase 6: banco de palabras, misión y su detección al hablar."""

import asyncio

import yaml
from fastapi.testclient import TestClient

from backend.partner import scenarios
from backend.pipeline.turn_manager import MIN_VOICE_FRAMES, Session
from backend.storage.db import SEED_TOPICS, TOPICS_FILE, Store
from backend.vocabulary.words import GENERAL, PACKS, find_use, pack_for, uses
from tests.test_turn_manager import FakeLLM, FakeSTT, FakeTTS, FakeVad, first

DAY = 86400
ISSUE = {"type": "vocabulary", "original": "Wispit", "fix": "Whisper", "explanation_es": "Se dice Whisper.", "severity": 2}
PACK = [{"key": k, "term": k, "meaning": f"es {k}", "example": f"I {k}.", "forms": [], "source": "pack"}
        for k in ("one", "two", "three", "four", "five")]


def test_every_pack_belongs_to_a_topic_or_scenario_and_its_examples_use_the_word():
    known = {GENERAL, *(t for t, _ in SEED_TOPICS), *yaml.safe_load(TOPICS_FILE.read_text(encoding="utf-8")), *scenarios.load()}
    assert set(PACKS) == known
    for words in PACKS.values():
        for w in words:
            assert uses(w["ex"], w["term"], w.get("forms", [])), w["term"]
            assert w["es"].strip()


def test_uses_finds_regular_and_irregular_forms_and_not_other_words():
    assert uses("I struggled with it", "struggle with")
    assert uses("we keep planning it", "plan")
    assert uses("she carried it", "carry")
    assert uses("I ran out of time", "run out of", ["ran out of"])
    assert uses("that's a tradeoff", "trade-off") and uses("that's a trade off", "trade-off")
    assert uses("Deadlines, deadlines.", "deadline")
    assert not uses("I ran out of time", "run out of")  # la irregular hay que declararla
    assert not uses("the planet is big", "plan")
    assert not uses("I struggle a lot with it", "struggle with")
    assert uses("It was a week so I left", "a week, so")  # Whisper puntúa a su manera
    assert uses("It was a week, so I left", "a week so")
    assert find_use("Yesterday We Ran Out of coffee", "run out of", ["ran out of"]) == "Ran Out of"
    assert find_use("nothing here", "run out of") == ""
    assert find_use("Yesterday We Ran Out of coffee", "run out of", ["ran out of"]) == "Ran Out of"
    assert find_use("nothing here", "run out of") == ""


def test_mission_mixes_due_bank_words_with_new_ones_from_the_pack():
    s = Store(":memory:")
    assert [w["key"] for w in s.pick_mission(PACK)] == ["one", "two", "three", "four"]
    for k in ("a", "b", "c"):
        s.add_word(k, f"es {k}", f"I {k}.", [], "buddy")
    picked = [w["key"] for w in s.pick_mission(PACK)]
    assert len(picked) == 4 and picked[2:] == ["one", "two"] and set(picked[:2]) <= {"a", "b", "c"}


def test_mission_fills_with_the_bank_when_the_pack_runs_out():
    s = Store(":memory:")
    for k in ("a", "b", "c"):
        s.add_word(k, "es", "ex", [], "buddy")
    assert len(s.pick_mission(PACK[:1])) == 4


def test_a_correction_enters_a_mission_only_after_you_answered_it_in_review():
    s = Store(":memory:")
    sid = s.start_session(None)
    s.add_feedback(s.add_turn(sid, "user", "I use Wispit"), "I use Whisper", [ISSUE])
    assert "whisper" not in [w["key"] for w in s.pick_mission(PACK)]  # podría ser un fallo de Whisper
    s.answer_review("whisper", True, now=0.0)
    assert "whisper" not in [w["key"] for w in s.pick_mission(PACK, now=1.0)]  # aún no le toca
    assert "whisper" in [w["key"] for w in s.pick_mission(PACK, now=2.0 * DAY)]


def test_finishing_a_mission_banks_the_pack_words_and_credits_only_the_used_ones():
    s = Store(":memory:")
    s.finish_mission(s.pick_mission(PACK), {"one"})
    items = {i["key"]: i for i in s.word_bank()["items"]}
    assert set(items) == {"one", "two", "three", "four"} and items["two"]["meaning"] == "es two"
    pending = [i["key"] for i in s.review_items()]
    assert "one" not in pending  # la usaste: vuelve dentro de un día
    assert "two" in pending  # sin castigo: sigue pendiente, como nueva
    # Las nuevas del paquete no se repiten, y lo que no usaste vuelve antes que lo que ya usaste
    picked = [w["key"] for w in s.pick_mission(PACK)]
    assert "five" in picked and "one" not in picked and len(picked) == 4


def test_a_discarded_correction_stays_out_until_you_save_that_word_yourself():
    s = Store(":memory:")
    sid = s.start_session(None)
    s.add_feedback(s.add_turn(sid, "user", "I use Wispit"), "I use Whisper", [ISSUE])
    assert s.progress()["review_due"] == 1
    s.discard_review("whisper")
    assert s.review_items() == [] and s.word_bank()["items"] == [] and s.progress()["review_due"] == 0
    s.add_word("Whisper", "un modelo", "I use Whisper.", [], "buddy")
    assert [i["key"] for i in s.review_items()] == ["whisper"]


def test_review_items_say_how_the_word_appears_in_their_sentence():
    s = bank(Store(":memory:"))
    assert s.review_items()[0]["target"] == "ran out of"


def test_review_marks_what_can_be_said_from_memory():
    s = Store(":memory:")
    s.add_word("deadline", "fecha límite", "A tight deadline.", [], "pack")
    s.add_word("a very long expression to say", "algo largo", "Ex.", [], "buddy")
    assert {i["key"]: i["speakable"] for i in s.review_items()} == {"deadline": True, "a very long expression to say": False}


def test_a_discarded_pack_word_is_not_offered_again():
    s = Store(":memory:")
    s.discard_review("one")
    assert "one" not in [w["key"] for w in s.pick_mission(PACK)]


def test_a_database_without_the_hidden_column_is_migrated(tmp_path):
    path = tmp_path / "old.db"
    s = Store(path)
    s.db.execute("ALTER TABLE reviews DROP COLUMN hidden")
    s.db.commit()
    s.db.close()
    assert Store(path).review_items() == []


class SpyLLM(FakeLLM):
    def __init__(self):
        super().__init__(["Nice! ", "What else?"])
        self.system = None

    async def stream(self, messages):
        self.system = messages[0]["content"]
        async for p in super().stream(messages):
            yield p


def session(store, text):
    events = []

    async def send_json(m):
        events.append(m)

    async def send_bytes(b):
        events.append(b)

    llm = SpyLLM()
    s = Session(send_json=send_json, send_bytes=send_bytes, vad=FakeVad(), stt=FakeSTT(text), llm=llm, tts=FakeTTS(),
                silence_ms=900, systems={"voz": "coach", "panel": "recast", "silencioso": "recast"}, greeting="Hi!",
                store=store)
    return s, events, llm


async def talk(s):
    await s.on_control({"type": "start"})
    await s.on_audio(b"\x01" * MIN_VOICE_FRAMES)
    await s.on_control({"type": "stop"})
    await s.task


def test_a_word_you_say_is_marked_live_and_counts_in_the_summary():
    async def run():
        store = Store(":memory:")
        s, events, llm = session(store, "I need to figure it out")
        await s.on_control({"type": "hello"})
        await s.task
        mission = first(events, "session")["mission"]
        assert mission[0]["term"] == pack_for(None)[0]["term"] and "forms" not in mission[0]
        await talk(s)
        assert first(events, "mission")["used"] == ["figure out"]
        assert '"figure out"' in llm.system  # Buddy sabe qué palabras practicas
        await s.on_control({"type": "end"})
        summary = first(events, "summary")
        assert [w["key"] for w in summary["mission"]["used"]] == ["figure out"] and len(summary["mission"]["unused"]) == 3
        assert "figure out" not in [i["key"] for i in store.review_items()]
        assert s.mission == [] and "figure out" not in s.messages[0]["content"]
    asyncio.run(run())


def test_a_session_where_you_did_not_speak_does_not_spend_the_words():
    async def run():
        store = Store(":memory:")
        s, events, _ = session(store, "")
        await s.on_control({"type": "hello"})
        await s.task
        before = first(events, "session")["mission"]
        await s.on_control({"type": "end"})
        assert store.word_bank()["items"] == []
        assert store.pick_mission(pack_for(None))[0]["key"] == before[0]["key"]
    asyncio.run(run())


async def recall(s, key):
    await s.on_control({"type": "recall", "key": key})
    await s.on_audio(b"\x01" * MIN_VOICE_FRAMES)
    await s.on_control({"type": "stop"})
    await s.task


def bank(store):
    store.add_word("run out of", "quedarse sin", "We ran out of time.", ["ran out of"], "pack")
    return store


def test_recalling_a_word_in_a_sentence_says_it_was_used_without_the_llm_or_the_conversation():
    async def run():
        s, events, llm = session(bank(Store(":memory:")), "Yesterday we ran out of coffee")
        await recall(s, "run out of")
        assert first(events, "recall_result") == {"type": "recall_result", "key": "run out of", "too_short": False,
                                                  "text": "Yesterday we ran out of coffee", "used": True, "match": "ran out of",
                                                  "checking": False}
        assert llm.system is None and len(s.messages) == 1 and s.state == "idle" and s.recall_item is None
    asyncio.run(run())


def test_recall_says_when_the_word_was_not_there_or_the_sentence_is_too_short():
    async def run():
        for text, used, short in (("We have no more coffee", False, False), ("Run out", False, True)):
            s, events, _ = session(bank(Store(":memory:")), text)
            await recall(s, "run out of")
            r = first(events, "recall_result")
            assert (r["used"], r["too_short"]) == (used, short)
    asyncio.run(run())


def test_recall_of_something_not_in_the_bank_or_without_speech_gives_no_result():
    async def run():
        s, _, _ = session(bank(Store(":memory:")), "We ran out of coffee")
        await s.on_control({"type": "recall", "key": "nope"})
        assert s.state == "idle" and s.recall_item is None
        s, events, _ = session(bank(Store(":memory:")), "")
        await recall(s, "run out of")
        assert first(events, "turn_discarded")
        assert not [e for e in events if isinstance(e, dict) and e["type"] == "recall_result"]
    asyncio.run(run())


class UsageTutor:
    def __init__(self, fails=False):
        self.calls, self.fails = [], fails

    async def check_usage(self, term, meaning, text):
        self.calls.append((term, meaning, text))
        if self.fails:
            raise ValueError("sin respuesta")
        return {"ok": False, "comment": "Aquí significa otra cosa.", "corrected": "We ran out of coffee."}


async def own_sentence(s):
    await s.on_control({"type": "recall", "key": "run out of", "check": True})
    await s.on_audio(b"\x01" * MIN_VOICE_FRAMES)
    await s.on_control({"type": "stop"})
    await s.task


def test_with_check_the_tutor_reviews_how_you_used_the_word():
    async def run():
        s, events, _ = session(bank(Store(":memory:")), "Yesterday we ran out of coffee")
        s.tutor = UsageTutor()
        await own_sentence(s)
        assert s.tutor.calls == [("run out of", "quedarse sin", "Yesterday we ran out of coffee")]
        assert first(events, "recall_result")["checking"] is True
        assert first(events, "usage_result") == {"type": "usage_result", "key": "run out of", "ok": False,
                                                 "comment": "Aquí significa otra cosa.", "corrected": "We ran out of coffee."}
        assert s.state == "idle" and s.recall_item is None
    asyncio.run(run())


def test_without_the_word_or_without_check_the_tutor_is_not_asked():
    async def run():
        s, events, _ = session(bank(Store(":memory:")), "We have no more coffee")
        s.tutor = UsageTutor()
        await own_sentence(s)
        assert first(events, "recall_result")["checking"] is False and s.tutor.calls == []
        s, _, _ = session(bank(Store(":memory:")), "Yesterday we ran out of coffee")
        s.tutor = UsageTutor()
        await recall(s, "run out of")
        assert s.tutor.calls == []
    asyncio.run(run())


def test_when_the_tutor_fails_the_session_goes_on_and_says_so():
    async def run():
        s, events, _ = session(bank(Store(":memory:")), "Yesterday we ran out of coffee")
        s.tutor = UsageTutor(fails=True)
        await own_sentence(s)
        assert first(events, "usage_result")["failed"] is True and s.state == "idle"
    asyncio.run(run())


def test_own_sentence_rounds_use_your_words_and_leave_the_review_boxes_alone():
    s = Store(":memory:")
    sid = s.start_session(None)
    s.add_feedback(s.add_turn(sid, "user", "I use Wispit"), "I use Whisper", [ISSUE])
    assert s.own_sentence_items() == []  # podría ser un fallo de Whisper
    for n in range(7):
        s.add_word(f"word{n}", "es", "ex", [], "pack")
    round_ = s.own_sentence_items()
    assert len(round_) == 5 and all(i["kind"] == "word" for i in round_) and s.word_bank()["practicable"] == 7
    s.answer_review("whisper", True)
    assert s.word_bank()["practicable"] == 8
    assert len(s.own_sentence_items(limit=20)) == 8


def game_session(guess="Is it a deadline?", said="It is the last day to finish your work", words=("deadline",)):
    store = Store(":memory:")
    for w in words:
        store.add_word(w, f"es {w}", f"Example of {w}.", [], "pack")
    s, events, llm = session(store, said)
    llm.pieces = [guess]
    return s, events, llm, store


def game_events(events):
    return [e for e in events if isinstance(e, dict) and e["type"] == "game"]


def test_game_words_are_your_words_short_enough_to_describe():
    s = Store(":memory:")
    sid = s.start_session(None)
    s.add_feedback(s.add_turn(sid, "user", "I use Wispit"), "I use Whisper", [ISSUE])
    s.answer_review("whisper", True)
    s.add_word("deadline", "es", "ex", [], "pack")
    s.add_word("off the beaten path", "es", "ex", [], "pack")
    assert [w["key"] for w in s.game_items()] == ["deadline"] and s.word_bank()["guessable"] == 1


def test_buddy_guesses_without_knowing_the_word_and_the_next_one_starts_clean():
    async def run():
        s, events, llm, store = game_session(words=("deadline", "workload"))
        s.store.game_items = lambda: [{**store.bank_item(k), "key": k} for k in ("deadline", "workload")]
        await s.on_control({"type": "hello", "game": True})
        await s.task
        assert "deadline" not in s.messages[0]["content"] and "guessing game" in s.messages[0]["content"]
        assert [w["key"] for w in first(events, "session")["game"]] == ["deadline", "workload"]
        await talk(s)
        assert "deadline" not in llm.system and "workload" not in llm.system  # no le chivamos la palabra
        assert game_events(events)[-1]["index"] == 1 and game_events(events)[-1]["solved"] == ["deadline"]
        assert len(s.messages) == 1  # la siguiente palabra empieza de cero
        await s.on_control({"type": "end"})
        summary = first(events, "summary")
        assert summary["topic"] == "Buddy adivina"
        assert [w["key"] for w in summary["game"]["solved"]] == ["deadline"]
        assert [w["key"] for w in summary["game"]["skipped"]] == ["workload"]
        assert s.game is None and "guessing game" not in s.messages[0]["content"]
        assert store.review_items()[0]["key"] in ("deadline", "workload") and len(store.review_items()) == 2  # no toca las cajas
    asyncio.run(run())


def test_a_wrong_guess_stays_on_the_same_word_and_keeps_the_history():
    async def run():
        s, events, _, _ = game_session(guess="Is it a holiday?")
        await s.on_control({"type": "hello", "game": True})
        await s.task
        await talk(s)
        assert game_events(events) == [] and s._game_word()["key"] == "deadline"
        assert [m["role"] for m in s.messages] == ["system", "user", "assistant"]
    asyncio.run(run())


def test_saying_the_word_does_not_count_and_buddy_never_hears_it():
    async def run():
        s, events, llm, _ = game_session(said="It is a deadline for the project")
        await s.on_control({"type": "hello", "game": True})
        await s.task
        await talk(s)
        assert game_events(events)[-1]["taboo"] is True and s._game_word()["key"] == "deadline"
        assert llm.system is None  # el modelo ni se llamó
        assert len(s.messages) == 1
        assert "you said the word" in " ".join(e["text"] for e in events if isinstance(e, dict) and e["type"] == "partner_text")
    asyncio.run(run())


def test_skipping_the_last_word_ends_the_game_and_buddy_goes_back_to_chatting():
    async def run():
        s, events, _, _ = game_session()
        await s.on_control({"type": "hello", "game": True})
        await s.task
        await s.on_control({"type": "game_skip"})
        await s.task
        assert game_events(events)[-1]["skipped"] == ["deadline"] and s._game_word() is None
        assert s.messages[0]["content"] == "coach"
        assert "last word" in " ".join(e["text"] for e in events if isinstance(e, dict) and e["type"] == "partner_text")
        await s.on_control({"type": "game_skip"})  # ya no queda nada que pasar
        assert len(game_events(events)) == 1
    asyncio.run(run())


def test_you_can_give_a_close_guess_as_solved():
    async def run():
        s, events, _, _ = game_session()
        await s.on_control({"type": "hello", "game": True})
        await s.task
        await s.on_control({"type": "game_skip", "solved": True})
        await s.task
        assert game_events(events)[-1]["solved"] == ["deadline"] and game_events(events)[-1]["skipped"] == []
    asyncio.run(run())


def test_a_game_without_words_is_a_normal_conversation():
    async def run():
        s, events, _ = session(Store(":memory:"), "Hello there my friend")
        await s.on_control({"type": "hello", "game": True})
        await s.task
        assert s.game is None and "game" not in first(events, "session")
    asyncio.run(run())


class FakeTutor:
    def __init__(self, result=None):
        self.result = result

    async def define(self, word, context):
        if self.result is None:
            raise ValueError("sin respuesta")
        return self.result


def client(monkeypatch, tmp_path, tutor):
    from backend import main
    store = Store(tmp_path / "t.db")
    monkeypatch.setattr(main.app.state, "store", store, raising=False)
    monkeypatch.setattr(main.app.state, "tutor", tutor, raising=False)
    return TestClient(main.app), store


def test_api_saves_a_word_with_its_meaning_and_can_remove_it(monkeypatch, tmp_path):
    word = {"term": "go", "meaning": "ir", "example": "I go home.", "forms": ["went"]}
    c, _ = client(monkeypatch, tmp_path, FakeTutor(word))
    assert c.post("/api/words", json={"term": "went", "context": "I went home."}).json()["key"] == "go"
    item = c.get("/api/words").json()["items"][0]
    assert item["term"] == "go" and item["meaning"] == "ir" and item["forms"] == ["went"] and item["kind"] == "word"
    assert c.post("/api/review/discard", json={"key": "go"}).json()["pending"] == 0
    data = c.get("/api/words").json()
    assert data["items"] == [] and data["review_due"] == 0


def test_api_says_so_when_the_model_cannot_define_a_word(monkeypatch, tmp_path):
    c, store = client(monkeypatch, tmp_path, FakeTutor())
    assert c.post("/api/words", json={"term": "went"}).status_code == 502
    assert c.post("/api/words", json={"term": ""}).status_code == 422
    assert store.word_bank()["items"] == []


def test_when_you_spoke_the_mission_enters_your_bank_and_the_word_you_used_counts_as_a_hit():
    async def run():
        store = Store(":memory:")
        s, _, _ = session(store, "I need to figure it out")
        await s.on_control({"type": "hello"})
        await s.task
        terms = {w["term"] for w in s.mission}
        await talk(s)
        await s.on_control({"type": "end"})
        assert {r["term"] for r in store.db.execute("SELECT term FROM words")} == terms
        assert [tuple(r) for r in store.db.execute("SELECT key, box FROM reviews")] == [("figure out", 1)]
    asyncio.run(run())
