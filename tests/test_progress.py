"""Fase 5: historial, métricas, errores recurrentes y repaso de vocabulario."""

from datetime import date, datetime, timedelta

from fastapi.testclient import TestClient

from backend.storage.db import REVIEW_AGAIN_S, Store

DAY = 86400
ISSUE = {"type": "vocabulary", "original": "proponent", "fix": "prompt", "explanation_es": "Se dice prompt.", "severity": 2}


def session(s, text="I like it.", issues=(), started=None, topic=None, seconds=6.0, corrected=None, intent=None):
    sid = s.start_session(topic)
    if started:
        s.db.execute("UPDATE sessions SET started_at = ? WHERE id = ?", (started, sid))
    row = s.add_turn(sid, "user", text, seconds=seconds)
    if issues or corrected or intent:
        s.add_feedback(row, corrected or text, list(issues), intent=intent)
    return sid


def test_history_counts_only_sessions_where_you_spoke_with_their_metrics():
    s = Store(":memory:")
    s.start_session(None)  # abriste y no hablaste
    topic = s.topics()[0]
    sid = session(s, "Three words here.", topic=topic["id"], seconds=6.0, issues=[ISSUE])
    s.add_turn(sid, "user", "And three more.", seconds=6.0)
    data = s.progress()
    assert data["totals"] == {"sessions": 1, "minutes": 0.2, "turns": 2, "words": 6}
    h = data["sessions"][0]
    assert h["topic"] == topic["title"] and h["wpm"] == 30 and h["clean_pct"] == 50 and h["errors"] == 1


def test_sessions_are_newest_first_and_days_without_practice_count_as_zero():
    s = Store(":memory:")
    today = datetime.combine(date.today(), datetime.min.time()).timestamp() + 3600
    old = session(s, started=today - 3 * DAY, seconds=60.0)
    new = session(s, started=today, seconds=120.0)
    data = s.progress(days=5)
    assert [h["id"] for h in data["sessions"]] == [new, old]
    assert [d["minutes"] for d in data["days"]] == [0, 1.0, 0, 0, 2.0]
    assert data["days"][-1]["date"] == date.today().isoformat()
    assert data["days"][0]["date"] == (date.today() - timedelta(days=4)).isoformat()


def test_recurring_errors_ignore_case_and_need_two_occurrences():
    s = Store(":memory:")
    session(s, issues=[{**ISSUE, "original": "Proponent"}])
    session(s, issues=[ISSUE])
    session(s, issues=[{**ISSUE, "original": "once", "fix": "one time"}])
    session(s, issues=[{**ISSUE, "original": "", "fix": "something added"}])
    session(s, issues=[{**ISSUE, "original": "", "fix": "something added"}])  # no es un error tuyo: no dijiste nada
    recurring = s.progress()["recurring"]
    assert len(recurring) == 1 and recurring[0]["count"] == 2 and recurring[0]["sessions"] == 2


def test_recurring_sounds_are_grouped_with_their_words():
    s = Store(":memory:")
    tip = {"phone": "æ", "heard": "a", "tip": "Abre más.", "margin": 6.0}
    s.add_sound_issues("Natural natural", [{"word": "Natural", "issues": [tip]}, {"word": "natural", "issues": [tip]}])
    sounds = s.progress()["sounds"]
    assert sounds[0]["count"] == 2 and sounds[0]["words"] == ["natural"] and sounds[0]["phone"] == "æ"


def test_review_includes_vocabulary_and_written_intents_but_not_grammar():
    s = Store(":memory:")
    session(s, "a better proponent", issues=[ISSUE], corrected="a better prompt")
    session(s, issues=[{**ISSUE, "type": "grammar", "original": "I go", "fix": "I went"}])
    session(s, "for my five cell", corrected="for myself", intent="para mí")
    items = {i["key"]: i for i in s.review_items()}
    assert set(items) == {"prompt", "for myself"}
    assert items["prompt"]["text"] == "a better prompt" and items["prompt"]["said"] == "proponent"
    assert items["for myself"]["intent"] == "para mí"


def test_review_reads_only_the_fix_when_the_sentence_does_not_contain_it_or_is_too_long():
    s = Store(":memory:")
    session(s, "x", issues=[ISSUE], corrected="something else entirely")
    assert s.review_items()[0]["text"] == "prompt"


def test_unfinished_sentences_are_not_practiced_whole():
    s = Store(":memory:")
    session(s, "x", issues=[ISSUE], corrected="I wrote a better prompt on my...")
    session(s, "a week so", corrected="a week, so..", intent="una semana")
    items = {i["key"]: i["text"] for i in s.review_items()}
    assert items["prompt"] == "prompt" and items["a week, so.."] == "a week, so."


def test_a_written_question_keeps_its_own_punctuation():
    s = Store(":memory:")
    session(s, "Did you went?", corrected="Did you go?", intent="¿Fuiste?")
    assert s.review_items()[0]["text"] == "Did you go?"


def test_known_items_come_back_later_and_later_and_unknown_ones_soon():
    s = Store(":memory:")
    session(s, issues=[ISSUE])
    now = 1_000_000.0
    s.answer_review("prompt", True, now=now)
    assert s.review_items(now=now + DAY - 1) == []
    assert s.review_items(now=now + DAY)[0]["key"] == "prompt"
    s.answer_review("prompt", True, now=now + DAY)
    assert s.review_items(now=now + 3 * DAY) == []
    assert s.review_items(now=now + 4 * DAY)
    s.answer_review("prompt", False, now=now + 4 * DAY)  # se te olvidó: vuelve enseguida
    assert s.review_items(now=now + 4 * DAY + 1) == []
    assert s.review_items(now=now + 4 * DAY + REVIEW_AGAIN_S)
    s.answer_review("prompt", True, now=now + 5 * DAY)  # y vuelve a empezar por el intervalo corto
    assert s.review_items(now=now + 6 * DAY)


def test_overdue_items_come_before_new_ones():
    s = Store(":memory:")
    session(s, issues=[ISSUE])
    session(s, issues=[{**ISSUE, "original": "x", "fix": "new word"}])
    s.answer_review("prompt", True, now=0.0)
    assert [i["key"] for i in s.review_items(now=2.0 * DAY)] == ["prompt", "new word"]


def test_the_count_of_pending_reviews_is_not_capped_by_the_size_of_a_round():
    s = Store(":memory:")
    for n in range(12):
        session(s, issues=[{**ISSUE, "original": f"w{n}", "fix": f"word {n}"}])
    assert len(s.review_items()) == 10 and s.progress()["review_due"] == 12


def test_interval_stops_growing_at_the_last_box():
    s = Store(":memory:")
    session(s, issues=[ISSUE])
    for n in range(8):
        s.answer_review("prompt", True, now=float(n))
    assert s.review_items(now=8.0 + 59 * DAY) == []
    assert s.review_items(now=8.0 + 60 * DAY)


def test_api_titles_sessions_and_records_review_answers():
    from backend.main import SCENARIOS, app

    store = Store(":memory:")
    app.state.store = store
    session(store, issues=[ISSUE])
    scenario = next(iter(SCENARIOS))
    sid = session(store)
    store.db.execute("UPDATE sessions SET scenario = ? WHERE id = ?", (scenario, sid))
    client = TestClient(app)  # sin `with`: no carga los modelos
    data = client.get("/api/progress").json()
    assert [h["title"] for h in data["sessions"]] == [SCENARIOS[scenario]["title"], "Conversación libre"]
    assert data["review_due"] == 1
    assert client.post("/api/review", json={"key": "prompt", "known": True}).status_code == 200
    assert client.get("/api/progress").json()["review_due"] == 0
    assert client.post("/api/review", json={"key": "prompt"}).status_code == 422


def test_review_status_says_how_many_remain_and_when_the_next_one_returns():
    s = Store(":memory:")
    session(s, "a better proponent", issues=[ISSUE], corrected="a better prompt")
    session(s, "for my five cell", corrected="for myself", intent="para mí")
    assert s.review_status(now=0.0) == {"pending": 2, "next_due": None}
    s.answer_review("prompt", True, now=0.0)
    assert s.review_status(now=0.0) == {"pending": 1, "next_due": DAY}


def test_api_drills_put_the_sounds_you_fail_most_first():
    from backend.main import app

    class Phonemes:  # lo mínimo de eSpeak: cada palabra con /æ/, para ver qué se destaca
        def sentence(self, text):
            return (("cat", ("k", "æ", "t")),)

    class FakeScorer:
        phonemes = Phonemes()

    store = Store(":memory:")
    app.state.store, app.state.scorer = store, FakeScorer()
    words = [{"word": "cat", "issues": [{"phone": "æ", "heard": "a", "tip": "t", "margin": 5.0}]},
             {"word": "ship", "issues": [{"phone": "ɪ", "heard": "iː", "tip": "t", "margin": 5.0}]},
             {"word": "sheep", "issues": [{"phone": "iː", "heard": "ɪ", "tip": "t", "margin": 5.0}]}]
    store.add_sound_issues("frase", words)
    sounds = TestClient(app).get("/api/drills").json()["sounds"]
    assert [(s["phones"], s["errors"]) for s in sounds[:2]] == [(["ɪ", "iː"], 2), (["æ"], 1)]
    assert sounds[2]["errors"] == 0
    cat = next(s for s in sounds if s["phones"] == ["æ"])
    sentence = cat["sentences"][0]
    assert cat["targets"][sentence] == ["cat"]
    app.state.scorer = None  # sin el modelo de fonemas, las frases salen igual, sin destacar nada
    assert TestClient(app).get("/api/drills").json()["sounds"][0]["targets"] == {}


def test_api_scenarios_show_your_best_stars_and_ignore_sessions_where_you_did_not_speak():
    from backend.main import SCENARIOS, app

    store = Store(":memory:")
    app.state.store = store
    first, second = list(SCENARIOS)[:2]
    for met, scenario, speak in ((1, first, True), (4, first, True), (2, first, True), (4, second, False)):
        sid = store.start_session(None, scenario=scenario)
        if speak:
            store.add_turn(sid, "user", "Hello.")
        store.set_goals(sid, met, 4)
    data = {s["id"]: s for s in TestClient(app).get("/api/scenarios").json()}
    assert data[first]["stars"] == 3 and data[second]["stars"] == 0
    assert data[first]["partner_role"] and data[first]["user_role"]


def test_session_summary_says_which_topic_it_was():
    s = Store(":memory:")
    topic = s.topics()[0]
    summary = s.finish_session(session(s, topic=topic["id"]))
    assert summary["topic"] == topic["title"] and summary["topic_id"] == topic["id"]
    assert s.finish_session(session(s))["topic"] is None


def test_api_settings_are_validated_saved_and_applied_to_the_voice():
    from types import SimpleNamespace

    from backend.main import app

    store = Store(":memory:")
    app.state.store = store
    app.state.tts = SimpleNamespace(speed=0.9, synth=lambda text: b"\0\0" * 2400)
    client = TestClient(app)
    assert client.get("/api/settings").json()["feedback"] == "voz"
    saved = client.put("/api/settings", json={"speed": 1.1, "silence_ms": 1200}).json()
    assert saved["speed"] == 1.1 and saved["silence_ms"] == 1200 and app.state.tts.speed == 1.1
    assert store.settings() == {"speed": 1.1, "silence_ms": 1200}
    client.put("/api/settings", json={"feedback": "panel"})
    assert client.get("/api/settings").json() == {"speed": 1.1, "silence_ms": 1200, "feedback": "panel"}
    for bad in ({"silence_ms": 100}, {"speed": 5}, {"feedback": "gritando"}):
        assert client.put("/api/settings", json=bad).status_code == 422
    sample = client.get("/api/voice-sample")
    assert sample.headers["content-type"] == "audio/wav" and sample.content[:4] == b"RIFF"


def test_progress_gives_minutes_for_every_day_with_practice_even_old_ones():
    s = Store(":memory:")
    old = (datetime.now() - timedelta(days=90)).replace(hour=12)
    session(s, started=old.timestamp(), seconds=60)
    session(s, started=old.timestamp() + 60, seconds=30)
    session(s, seconds=120)
    assert s.progress()["minutes_by_day"] == {old.date().isoformat(): 1.5, date.today().isoformat(): 2.0}
