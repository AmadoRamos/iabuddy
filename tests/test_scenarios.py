"""Fase 3: escenarios en YAML, objetivos durante la conversación y evaluación final."""

import asyncio

from test_feedback import FakeTutor, run_turn
from test_turn_manager import first, make

from backend.partner.scenarios import load
from backend.storage.db import Store
from backend.tutor.tutor import Tutor

SCENE = {"id": "cafe", "title": "En una cafetería", "description": "Pides un café.", "context": "A coffee shop.",
         "partner_role": "a barista", "user_role": "a customer", "openers": ["Hi! What can I get you?", "Hey there!"],
         "goals": ["Pide un café", "Pregunta el precio", "Despídete"],
         "key_phrases": ["I'd like", "How much is it?"],
         "systems": {"voz": "barista-coach", "panel": "barista", "silencioso": "barista"}}


class GoalsTutor(FakeTutor):
    async def check_goals(self, scenario, transcript):
        self.calls.append(("goals", transcript))
        checks = sum(c[0] == "goals" for c in self.calls)
        met = [True, False, False] if checks == 1 else [False, True, False]  # la final ya no repite el 1.º
        return {"met": met, "evidence": ["Yesterday I go", "", ""], "comment_es": "Bien pedido."}


def test_every_scenario_file_loads_with_a_prompt_per_mode():
    scenarios = load()
    assert len(scenarios) >= 5
    for sc in scenarios.values():
        assert sc["goals"] and sc["openers"] and set(sc["systems"]) == {"voz", "panel", "silencioso"}
        assert sc["partner_role"] in sc["systems"]["voz"]


def test_scenario_opener_never_repeats_the_last_one():
    s = Store(":memory:")
    last = None
    for _ in range(20):
        i = s.pick_scenario_opener("cafe", 3)
        assert i != last
        s.start_session(None, scenario="cafe", scenario_opener=i)
        last = i


async def test_check_goals_drops_quotes_of_unmet_goals_and_fills_missing_ones():
    class LLM:
        async def chat_json(self, messages, schema):
            return {"goals": [{"met": True, "evidence": "a latte"}, {"met": False, "evidence": "no prueba nada"}],
                    "comment_es": "Bien."}

    r = await Tutor(LLM()).check_goals(SCENE, "Learner: a latte")
    assert r == {"met": [True, False, False], "evidence": ["a latte", "", ""], "comment_es": "Bien."}


async def test_scenario_plays_a_role_tracks_goals_and_evaluates():
    s, events, _ = make()
    s.tutor, s.store, s.scenarios = GoalsTutor(), Store(":memory:"), {"cafe": SCENE}
    await s.on_control({"type": "hello", "scenario": "cafe"})
    await s.task
    assert first(events, "session")["scenario"]["goals"] == SCENE["goals"]
    assert s.messages[0]["content"].startswith("barista-coach") and s.messages[1]["content"] in SCENE["openers"]
    await run_turn(s)
    await asyncio.gather(*s.tutor_tasks)
    assert first(events, "goals")["met"] == [True, False, False]
    await s.on_control({"type": "end"})
    sc = first(events, "summary")["scenario"]
    assert [g["met"] for g in sc["goals"]] == [True, True, False]  # lo logrado antes se conserva
    assert sc["stars"] == 2 and sc["comment"] == "Bien pedido."
    assert sc["unused_phrases"] == SCENE["key_phrases"]
    assert tuple(s.store.db.execute("SELECT goals_met, goals_total FROM sessions").fetchone()) == (2, 3)
    assert s.scenario is None and s.messages[0]["content"] == "coach"  # la siguiente sesión vuelve a ser libre


async def test_closing_the_tab_still_finishes_and_evaluates_the_session():
    s, events, _ = make()
    s.tutor, s.store, s.scenarios = GoalsTutor(), Store(":memory:"), {"cafe": SCENE}
    await s.on_control({"type": "hello", "scenario": "cafe"})
    await s.task
    await run_turn(s)
    await s.close()
    row = s.store.db.execute("SELECT ended_at, goals_met, goals_total FROM sessions").fetchone()
    assert row["ended_at"] and (row["goals_met"], row["goals_total"]) == (2, 3)
    assert "summary" not in [e["type"] for e in events if isinstance(e, dict)]  # no hay a quién enviárselo
