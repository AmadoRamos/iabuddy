"""Fase 2: tutor, base de datos y su integración con el Turn Manager (con dobles, sin modelos)."""

import asyncio

from test_turn_manager import VOICE, first, make, types

from backend.storage.db import SEED_TOPICS, Store
from backend.tutor.tutor import clean

ISSUE = {"type": "grammar", "original": "I go", "fix": "I went", "explanation_es": "Pasado con «yesterday».",
         "severity": 2}


class FakeTutor:
    def __init__(self, delay: float = 0):
        self.delay, self.calls = delay, []

    async def analyze(self, text, partner_said=""):
        self.calls.append((text, partner_said))
        await asyncio.sleep(self.delay)
        return {"issues": [ISSUE], "corrected": "Yesterday I went to the gym.", "better": "I hit the gym yesterday.",
                "voice_tip": "Quick tip: say I went, not I go."}


def test_clean_drops_no_op_fixes_and_tip_without_issues():
    r = clean({"issues": [{**ISSUE, "original": "since", "fix": "since."}], "corrected": "x", "better": "x",
               "voice_tip": "Quick tip"})
    assert r["issues"] == [] and r["voice_tip"] == ""


def test_store_summary_counts_words_errors_and_recurring():
    s = Store(":memory:")
    assert len(s.topics()) == len(SEED_TOPICS)
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


async def run_turn(s):
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    await s.task


async def test_voice_mode_sends_feedback_stores_it_and_ends_with_tip():
    s, events, _ = make()
    s.tutor, s.store = FakeTutor(), Store(":memory:")
    await s.on_control({"type": "hello", "topic_id": 1})
    await s.task
    assert first(events, "session")["topic"] == SEED_TOPICS[0][0]
    await run_turn(s)
    assert first(events, "feedback")["issues"] == [ISSUE]
    assert types(events)[-5:] == ["tip", "audio", "partner_done", "state", "metrics"]
    await s.on_control({"type": "end"})
    summary = first(events, "summary")
    assert summary["turns"] == 1 and summary["by_type"] == {"grammar": 1}


async def test_silent_mode_hides_feedback_and_tip_but_still_records():
    s, events, _ = make()
    s.tutor, s.store = FakeTutor(), Store(":memory:")
    await s.on_control({"type": "hello", "feedback": "silencioso"})
    await s.task
    await run_turn(s)
    await asyncio.gather(*s.tutor_tasks)
    assert "feedback" not in types(events) and "tip" not in types(events)
    await s.on_control({"type": "end"})
    assert first(events, "summary")["by_type"] == {"grammar": 1}


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
