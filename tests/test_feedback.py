"""Fase 2: tutor, base de datos y su integración con el Turn Manager (con dobles, sin modelos)."""

import asyncio
import contextlib

from test_turn_manager import VOICE, first, make, types

from backend.storage.db import SEED_FREE_OPENERS, SEED_TOPICS, Store
from backend.tutor.tutor import clean

ISSUE = {"type": "grammar", "original": "I go", "fix": "I went", "explanation_es": "Pasado con «yesterday».",
         "severity": 2}


class FakeTutor:
    def __init__(self, delay: float = 0):
        self.delay, self.calls = delay, []

    async def analyze(self, text, partner_said=""):
        self.calls.append((text, partner_said))
        await asyncio.sleep(self.delay)
        return {"issues": [ISSUE], "corrected": "Yesterday I went to the gym.", "better": "I hit the gym yesterday."}

    async def analyze_intent(self, said, intent):
        self.calls.append((said, intent))
        return {"issues": [ISSUE], "corrected": "I went to the gym after work.", "better": "I hit the gym after work."}


class StubbornTutor(FakeTutor):
    """Como httpx a veces: la cancelación no llega y la llamada termina con su resultado."""

    def __init__(self):
        super().__init__()
        self.release = asyncio.Event()

    async def _wait(self):
        while not self.release.is_set():
            with contextlib.suppress(asyncio.CancelledError):
                await self.release.wait()

    async def analyze(self, text, partner_said=""):
        await self._wait()
        return await super().analyze(text, partner_said)

    async def analyze_intent(self, said, intent):
        await self._wait()
        return await super().analyze_intent(said, intent)


def test_clean_drops_no_op_fixes():
    r = clean({"issues": [{**ISSUE, "original": "since", "fix": "since."}, ISSUE], "corrected": "x", "better": "x"})
    assert r["issues"] == [ISSUE]


def test_store_summary_counts_words_errors_and_recurring():
    s = Store(":memory:")
    assert len(s.topics()) == len(SEED_TOPICS) + 3  # + los de topics.yaml
    sid = s.start_session(s.topics()[0]["id"])
    for text in ["Yesterday I go to the gym.", "Today I go to work.", "I like it."]:
        row = s.add_turn(sid, "user", text, seconds=3.0)
        if "go" in text:
            s.add_feedback(row, text.replace("go", "went"), [ISSUE])
    s.add_turn(sid, "buddy", "Nice!")
    summary = s.finish_session(sid)
    assert summary["turns"] == 3 and summary["words"] == 14 and summary["wpm"] == 93  # 14 palabras en 9 s
    assert summary["clean_turns"] == 1 and summary["by_type"] == {"grammar": 2}
    assert summary["recurring"][0]["count"] == 2 and len(summary["review"]) == 2


def test_opener_never_repeats_the_last_one_of_the_same_topic():
    s = Store(":memory:")
    topic = s.topics()[0]["id"]
    last = None
    for _ in range(20):
        o = s.pick_opener(topic)
        assert o["id"] != last
        s.start_session(topic, o["id"])
        last = o["id"]
    assert s.pick_opener(None)["text"] in SEED_FREE_OPENERS  # conversación libre


def test_old_database_is_migrated_to_several_openers(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    old = sqlite3.connect(db)
    old.executescript("CREATE TABLE topics (id INTEGER PRIMARY KEY, title TEXT NOT NULL, opener TEXT NOT NULL,"
                      " active INTEGER NOT NULL DEFAULT 1, position INTEGER NOT NULL DEFAULT 0);"
                      "CREATE TABLE sessions (id INTEGER PRIMARY KEY, topic_id INTEGER, started_at REAL NOT NULL,"
                      " ended_at REAL);"
                      "INSERT INTO topics (title, opener) VALUES ('Viajes', 'Old single opener?');")
    old.commit()
    old.close()
    s = Store(db)
    assert s.topics()[0] == {"id": 1, "title": "Viajes"}
    texts = {r[0] for r in s.db.execute("SELECT text FROM openers WHERE topic_id = 1")}
    assert texts == set(dict(SEED_TOPICS)["Viajes"])
    assert any(t["title"] == "Entrevista · Python" for t in s.topics())  # topics.yaml llega a bases viejas


def test_file_topics_are_added_once_with_their_openers(tmp_path):
    Store(tmp_path / "a.db")
    s = Store(tmp_path / "a.db")  # segundo arranque: no duplica
    titles = [t["title"] for t in s.topics()]
    assert titles.count("Entrevista · Backend y APIs") == 1
    tid = next(t["id"] for t in s.topics() if t["title"] == "Entrevista · Backend y APIs")
    assert len(s.db.execute("SELECT 1 FROM openers WHERE topic_id = ?", (tid,)).fetchall()) == 12


async def run_turn(s):
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    await s.task


async def test_feedback_is_sent_and_stored_and_mode_changes_buddys_prompt():
    s, events, _ = make()
    s.tutor, s.store = FakeTutor(), Store(":memory:")
    await s.on_control({"type": "hello", "topic_id": 1})
    await s.task
    title, openers = SEED_TOPICS[0]
    assert first(events, "session")["topic"] == title
    assert s.messages[0]["content"].startswith("coach") and title in s.messages[0]["content"]
    assert s.messages[1]["content"] in openers  # Buddy abre con uno de los inicios del tema
    await run_turn(s)
    await asyncio.gather(*s.tutor_tasks)
    assert first(events, "feedback")["issues"] == [ISSUE]
    await s.on_control({"type": "settings", "feedback": "panel"})
    assert s.messages[0]["content"].startswith("recast") and title in s.messages[0]["content"]
    await s.on_control({"type": "end"})
    summary = first(events, "summary")
    assert summary["turns"] == 1 and summary["by_type"] == {"grammar": 1}


async def test_silent_mode_hides_feedback_but_still_records():
    s, events, _ = make()
    s.tutor, s.store = FakeTutor(), Store(":memory:")
    await s.on_control({"type": "hello", "feedback": "silencioso"})
    await s.task
    await run_turn(s)
    await asyncio.gather(*s.tutor_tasks)
    assert "feedback" not in types(events)
    await s.on_control({"type": "end"})
    assert first(events, "summary")["by_type"] == {"grammar": 1}


async def test_written_intent_gets_analyzed_spoken_by_buddy_and_summarized():
    s, events, _ = make()
    s.tutor, s.store = FakeTutor(delay=0.05), Store(":memory:")  # el análisis automático llega tarde
    await s.on_control({"type": "hello"})
    await s.task
    await run_turn(s)
    await s.on_control({"type": "intent", "turn": 1, "text": "Fui al gimnasio después del trabajo"})
    await s.on_control({"type": "intent", "turn": 99, "text": "turno que no existe"})  # se ignora
    await asyncio.gather(*s.tutor_tasks)
    await s.task  # Buddy dice cómo decirlo
    fb = [e for e in events if isinstance(e, dict) and e["type"] == "feedback"]
    assert len(fb) == 1 and fb[0]["intent"] == "Fui al gimnasio después del trabajo"  # el automático se descarta
    assert "You can say: I went to the gym after work." in s.messages[-1]["content"]
    assert s.messages[-2]["role"] == "user" and "Fui al gimnasio" in s.messages[-2]["content"]
    await s.on_control({"type": "end"})
    assert first(events, "summary")["phrases"] == [{"said": "Yesterday I go to the gym.",
                                                    "intent": "Fui al gimnasio después del trabajo",
                                                    "english": "I went to the gym after work."}]


async def test_written_intent_without_final_stop_still_sounds_like_two_sentences():
    class NoStop(FakeTutor):
        async def analyze_intent(self, said, intent):
            return {"issues": [], "corrected": "for myself", "better": "for myself"}

    s, _, _ = make()
    s.tutor = NoStop()
    await s.on_control({"type": "hello"})
    await s.task
    await run_turn(s)
    await s.on_control({"type": "intent", "turn": 1, "text": "para mí"})
    await asyncio.gather(*s.tutor_tasks)
    await s.task
    assert "You can say: for myself. Want to try saying it?" in s.messages[-1]["content"]


class HeldLLM:
    """Retiene el primer token hasta que el test lo suelte."""

    def __init__(self):
        self.release = asyncio.Event()

    async def stream(self, messages):
        await self.release.wait()
        yield "Oh, you went to the gym? Nice!"


async def test_tutor_waits_for_buddys_first_audio():
    s, events, _ = make()
    s.tutor, s.llm = FakeTutor(), HeldLLM()
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    for _ in range(10):
        await asyncio.sleep(0)
    assert first(events, "user_text") and s.tutor.calls == []  # ya hay texto, pero Buddy aún no empezó
    s.llm.release.set()
    await s.task
    await asyncio.gather(*s.tutor_tasks)
    assert len(s.tutor.calls) == 1 and first(events, "feedback")["turn"] == 1


async def test_resuming_before_the_first_token_gives_back_the_turn_number():
    s, events, _ = make()
    s.tutor, s.llm, s.store = FakeTutor(), HeldLLM(), Store(":memory:")
    await s.on_control({"type": "hello"})
    s.llm.release.set()  # el saludo no usa el LLM, pero por si acaso
    await s.task
    s.llm.release.clear()
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    for _ in range(10):
        await asyncio.sleep(0)
    assert s.user_turns == 1
    await s.on_control({"type": "start"})  # sigues hablando antes de que Buddy empiece
    assert s.user_turns == 0 and first(events, "turn_resumed")["turn"] == 1 and s.turns == {}
    assert s.tutor.calls == []  # ese análisis ya no hacía falta
    assert s.store.db.execute("SELECT COUNT(*) FROM turns WHERE speaker = 'user'").fetchone()[0] == 0


async def test_listen_button_speaks_without_touching_history():
    s, events, _ = make()
    await s.on_control({"type": "say", "text": "I went to the gym."})
    await s.task
    assert types(events)[-3:] == ["audio", "partner_done", "state"] and len(s.messages) == 1


async def test_resuming_a_turn_drops_its_analysis_and_stored_row():
    s, events, _ = make(llm_pieces=("Oh", " you went? Nice!"))  # "Oh" aún no es un trozo: no suena nada
    s.tutor, s.store = FakeTutor(delay=10), Store(":memory:")
    s.llm.gate.clear()
    await s.on_control({"type": "hello"})
    await s.task
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    for _ in range(10):  # deja que llegue el texto y arranque el tutor
        await asyncio.sleep(0)
    assert s.state == "thinking" and s.user_turns == 1
    await s.on_control({"type": "start"})  # tecla antes de que suene: mismo turno
    assert first(events, "turn_resumed")["turn"] == 1 and s.user_turns == 0
    assert s.store.db.execute("SELECT COUNT(*) FROM turns WHERE speaker = 'user'").fetchone()[0] == 0


async def test_analyses_that_outlive_a_resumed_turn_are_dropped():
    s, events, _ = make(llm_pieces=("Oh", " you went? Nice!"))
    s.tutor, s.store = StubbornTutor(), Store(":memory:")
    s.llm.gate.clear()
    await s.on_control({"type": "hello"})
    await s.task
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    for _ in range(10):
        await asyncio.sleep(0)
    await s.on_control({"type": "intent", "turn": 1, "text": "Fui al gimnasio"})
    await asyncio.sleep(0)
    pending = list(s.tutor_tasks)
    assert len(pending) == 1  # solo la intención: el análisis automático espera al primer audio, que no llegó
    await s.on_control({"type": "start"})  # borra la fila; el análisis no se entera
    s.tutor.release.set()
    await asyncio.gather(*pending)  # sin la comprobación: IntegrityError (FOREIGN KEY)
    assert "feedback" not in types(events)
    assert s.store.db.execute("SELECT COUNT(*) FROM corrections").fetchone()[0] == 0
