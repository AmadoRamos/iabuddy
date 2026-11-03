"""Fase 4: alineación, reglas de errores típicos y su integración (con dobles, sin el modelo)."""

import asyncio
from pathlib import Path

import numpy as np
import yaml
from test_feedback import run_turn
from test_turn_manager import VOICE, first, make, types

from backend.pronunciation.rules import SWAPS, pronunciations, variants
from backend.pronunciation.scorer import Phonemes, align, trust
from backend.storage.db import Store

BLANK, A, B = 0, 1, 2


def frames(*ids) -> np.ndarray:
    """Log-probabilidades donde cada frame apunta con claridad a un token."""
    logp = np.full((len(ids), 3), np.log(0.01))
    logp[np.arange(len(ids)), ids] = np.log(0.98)
    return logp


def test_align_finds_where_each_token_starts_and_prefers_what_was_said():
    logp = frames(BLANK, A, A, BLANK, BLANK, B, BLANK)
    score, starts = align(logp, [A, B], BLANK)
    assert starts == [1, 5]
    assert score > align(logp, [B, A], BLANK)[0] + 3  # el orden contrario lo explica mucho peor


def test_align_needs_enough_audio():
    assert align(frames(A), [A, B], BLANK) == (-np.inf, [])


def test_variants_swap_typical_sounds_but_not_in_function_words():
    swapped = {v["heard"]: v["phones"] for v in variants("three", ("θ", "ɹ", "iː"))}
    assert swapped["t"] == ("t", "ɹ", "iː") and swapped["ɪ"] == ("θ", "ɹ", "ɪ")
    assert not [v for v in variants("to", ("t", "uː")) if v["phone"] == "uː"]  # un nativo también dice /tə/
    assert [v["heard"] for v in variants("the", ("ð", "ə"))] == ["d"]  # the → /də/ sí es un error


def test_variants_add_e_before_s_cluster_and_ed_syllable():
    assert {v["phones"][0] for v in variants("speak", ("s", "p", "iː", "k")) if v["phone"] == "s-"} == {"ɛ", "e"}
    walked = next(v for v in variants("walked", ("w", "ɔː", "k", "t")) if v["phone"] == "-ed")
    assert walked["phones"] == ("w", "ɔː", "k", "ɪ", "d")
    assert not [v for v in variants("wanted", ("w", "ɔ", "n", "t", "ᵻ", "d")) if v["phone"] == "-ed"]


def test_every_swap_has_a_tip_and_drills_are_well_formed():
    assert all(tip for options in SWAPS.values() for _, tip in options)
    drills = yaml.safe_load((Path("backend/pronunciation/drills.yaml")).read_text(encoding="utf-8"))
    assert len(drills) >= 10 and all(d["title"] and len(d["sentences"]) >= 3 for d in drills)


ISSUE = {"phone": "θ", "heard": "t", "tip": "Lengua entre los dientes.", "margin": 6.0}


class FakeScorer:
    def __init__(self, issues=(ISSUE,)):
        self.issues, self.calls = list(issues), []

    def analyze(self, pcm, text):
        self.calls.append(text)
        return {"score": 70, "words": [{"word": "three", "score": 40, "phones": ["θ"], "unclear": False, "issues": self.issues},
                                       {"word": "days", "score": 90, "phones": ["d"], "unclear": False, "issues": []}]}


async def test_passive_analysis_runs_after_buddy_speaks_and_reaches_the_summary():
    s, events, _ = make()
    s.scorer, s.store = FakeScorer(), Store(":memory:")
    await s.on_control({"type": "hello"})
    await s.task
    await run_turn(s)
    await asyncio.gather(*s.tutor_tasks)
    assert types(events).index("pronunciation") > types(events).index("audio")
    assert first(events, "pronunciation")["issues"] == [{"word": "three", **ISSUE}]
    await s.on_control({"type": "end"})
    sounds = first(events, "summary")["sounds"]
    assert sounds[0]["phone"] == "θ" and sounds[0]["words"] == ["three"] and sounds[0]["count"] == 1
    assert s.store.failed_phrases()[0]["words"] == ["three"]


async def test_each_sound_gets_one_notice_so_a_repeated_word_does_not_hide_another_error():
    def word(name, phone, margin):
        return {"word": name, "score": 30, "phones": [], "unclear": False,
                "issues": [{"phone": phone, "heard": "x", "tip": "t", "margin": margin}]}

    s, events, _ = make()
    s.store = Store(":memory:")
    s.scorer = FakeScorer()
    s.scorer.analyze = lambda pcm, text: {"score": 40, "words": [word("Natural", "æ", 7.8), word("natural", "æ", 7.7),
                                                                 word("very", "v", 4.0)]}
    await s.on_control({"type": "hello"})
    await s.task
    await run_turn(s)
    await asyncio.gather(*s.tutor_tasks)
    assert [(i["word"], i["phone"]) for i in first(events, "pronunciation")["issues"]] == [("Natural", "æ"), ("very", "v")]
    await s.on_control({"type": "end"})
    assert first(events, "summary")["sounds"][0]["words"] == ["natural"]  # sin repetir por las mayúsculas
    assert first(events, "summary")["sounds"][0]["count"] == 2


async def test_silent_mode_records_sounds_without_showing_them():
    s, events, _ = make()
    s.scorer, s.store = FakeScorer(), Store(":memory:")
    await s.on_control({"type": "hello", "feedback": "silencioso"})
    await s.task
    await run_turn(s)
    await asyncio.gather(*s.tutor_tasks)
    assert "pronunciation" not in types(events)
    assert s.store.failed_phrases()


async def test_turn_resumed_before_any_audio_is_not_analyzed():
    s, _, _ = make(llm_pieces=("Oh", " you went? Nice!"))  # "Oh" aún no es un trozo: no suena nada
    s.scorer = FakeScorer()
    s.llm.gate.clear()
    await s.on_control({"type": "hello"})
    await s.task
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    for _ in range(10):
        await asyncio.sleep(0)
    await s.on_control({"type": "start"})  # sigues hablando: mismo turno
    assert s.scorer.calls == [] and not s.tutor_tasks


async def drill(s, text):
    await s.on_control({"type": "drill", "text": text})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    await s.task


async def test_drill_scores_known_text_without_stt_or_llm_and_saying_it_right_resolves_it():
    s, events, _ = make()
    s.scorer, s.store = FakeScorer(), Store(":memory:")
    await drill(s, "Three days.")
    assert s.stt.calls == 0 and len(s.messages) == 1 and s.state == "idle" and s.drill_text is None
    assert first(events, "drill_result")["score"] == 70
    assert s.store.failed_phrases() == [{"text": "Three days.", "words": ["three"]}]
    s.scorer.issues = []
    await drill(s, "Three days.")
    assert s.store.failed_phrases() == []


async def test_reading_something_else_is_not_a_pass_even_without_typical_errors():
    s, events, _ = make()
    s.scorer, s.store = FakeScorer(), Store(":memory:")
    await drill(s, "Three days.")
    s.scorer.issues = []
    s.scorer.analyze = lambda pcm, text: {"score": 7, "words": [{"word": "three", "score": 7, "phones": ["θ"], "unclear": True,
                                                                 "issues": []}]}
    await drill(s, "Three days.")
    assert [e["passed"] for e in events if isinstance(e, dict) and e["type"] == "drill_result"] == [False, False]
    assert s.store.failed_phrases()  # sigue pendiente


async def test_one_word_nobody_could_hear_blocks_the_pass_even_with_a_good_average():
    s, events, _ = make()
    s.scorer, s.store = FakeScorer(issues=()), Store(":memory:")
    s.scorer.analyze = lambda pcm, text: {"score": 70, "words": [{"word": "live", "score": 7, "phones": ["l"], "unclear": True,
                                                                  "issues": []}]}
    await drill(s, "We live here.")
    assert first(events, "drill_result")["passed"] is False


class AnyVocab(dict):
    def __contains__(self, _):
        return True


def test_phonemes_use_the_whole_sentence_and_keep_words_apart():
    phonemes = Phonemes(AnyVocab())
    words = dict(phonemes.sentence("I live here and go to work."))
    assert words["live"] == ("l", "ɪ", "v")  # a solas, eSpeak diría /laɪv/ (a live concert)
    assert words["to"] == ("t", "ə")  # forma reducida
    numbers = phonemes.sentence("I work since 2019.")
    assert [w for w, _ in numbers] == ["I", "work", "since", "2019"] and len(dict(numbers)["2019"]) > 6  # varias palabras
    assert next(w for w, _ in phonemes.sentence("I\u2019ve been here.")) == "I\u2019ve"  # apóstrofo curvo


def test_homographs_accept_both_pronunciations():
    assert set(pronunciations("live", ("l", "aɪ", "v"))) == {("l", "aɪ", "v"), ("l", "ɪ", "v")}
    assert pronunciations("ship", ("ʃ", "ɪ", "p")) == [("ʃ", "ɪ", "p")]


def test_a_very_low_score_on_a_sentence_means_the_text_is_not_what_was_said():
    def word(name):
        return {"word": name, "score": 5, "unclear": True, "issues": [ISSUE]}

    sentence = trust({"score": 7, "words": [word(w) for w in ("view", "videos", "on", "youtube")]})
    assert sentence["mismatch"] and not any(w["issues"] or w["unclear"] for w in sentence["words"])
    single = trust({"score": 0, "words": [word("chair")]})  # una palabra suelta sí puede ser un error real
    assert "mismatch" not in single and single["words"][0]["issues"]
    good = trust({"score": 40, "words": [word(w) for w in ("view", "videos", "on", "youtube")]})
    assert "mismatch" not in good and good["words"][0]["issues"]


async def test_drill_without_voice_does_not_leak_into_the_next_turn():
    s, events, _ = make()
    s.scorer = FakeScorer()
    await s.on_control({"type": "drill", "text": "Three days."})
    await s.on_control({"type": "stop"})  # sin voz: se descarta
    assert s.drill_text is None and "turn_discarded" in types(events)
    await run_turn(s)
    assert s.stt.calls == 1  # el siguiente turno es normal


async def test_deleting_a_turn_removes_its_sounds():
    s = Store(":memory:")
    row = s.add_turn(s.start_session(None), "user", "Three days.", seconds=1.0)
    s.add_sound_issues("Three days.", [{"word": "three", "issues": [ISSUE]}], turn_id=row)
    s.delete_turn(row)
    assert s.failed_phrases() == []
