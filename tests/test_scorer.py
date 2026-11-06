"""Scorer sin el modelo: un wav2vec2 de mentira «oye» los fonemas que dicta cada test; el resto es el código real."""

import threading
from types import SimpleNamespace

import numpy as np

from backend.pronunciation.rules import EPENTHESIS, SWAPS
from backend.pronunciation.scorer import Phonemes, Scorer

SOUNDS = {*SWAPS, *(heard for options in SWAPS.values() for heard, _ in options),
          "ɹ", "d", "k", "l", "m", "n", "p", "s", "t", "v", "w", "ə", "e", "ɛ", "aɪ", "eɪ", "ɔː"}
VOCAB = {"<pad>": 0, **{p: i for i, p in enumerate(sorted(SOUNDS), start=1)}}
SURE = 12.0  # logit de lo que suena; el resto de fonemas, 0: casi toda la probabilidad para él
THREE = ("three", ("θ", "ɹ", "iː"))


def heard(*frames) -> np.ndarray:
    """Cada frame es un fonema, "" para silencio, o {fonema: logit} si el modelo duda."""
    logits = np.zeros((len(frames), len(VOCAB)), np.float32)
    for t, frame in enumerate(frames):
        for phone, value in (frame if isinstance(frame, dict) else {frame or "<pad>": SURE}).items():
            logits[t, VOCAB[phone]] = value
    return logits


def scorer(logits: np.ndarray, *words) -> Scorer:
    s = Scorer.__new__(Scorer)  # __init__ solo carga el modelo y eSpeak
    s.vocab, s.blank, s.lock = VOCAB, 0, threading.Lock()
    s.phonemes = SimpleNamespace(sentence=lambda text: words)
    s.session = SimpleNamespace(run=lambda _, inputs: [logits[None].copy()])
    return s


def analyze(logits, *words) -> dict:
    return scorer(logits, *words).analyze(bytes(3200), "")


def test_a_word_said_well_scores_high_without_issues():
    r = analyze(heard("", "θ", "", "ɹ", "", "iː", ""), THREE)
    word = r["words"][0]
    assert word["word"] == "three" and word["phones"] == ["θ", "ɹ", "iː"]
    assert 95 <= word["score"] <= 100 and r["score"] == word["score"]
    assert word["issues"] == [] and word["unclear"] is False and "mismatch" not in r


def test_a_typical_error_is_flagged_with_its_tip():
    issues = analyze(heard("", "t", "", "ɹ", "", "iː", ""), THREE)["words"][0]["issues"]
    assert [(i["phone"], i["heard"]) for i in issues] == [("θ", "t")]
    assert issues[0]["tip"] == dict(SWAPS["θ"])["t"] and issues[0]["margin"] > 3
    assert issues[0]["margin"] == round(issues[0]["margin"], 1)


def test_a_typical_error_needs_a_clear_margin_because_the_model_can_be_wrong():
    def issues_when_it_wins_by(extra):
        return analyze(heard({"θ": SURE, "t": SURE + extra}, "ɹ", "iː"), THREE)["words"][0]["issues"]

    assert issues_when_it_wins_by(0) == []
    assert issues_when_it_wins_by(2) == []
    assert [i["heard"] for i in issues_when_it_wins_by(4)] == ["t"]


def test_each_sound_keeps_its_clearest_error_and_the_clearest_sound_comes_first():
    # θ → t y θ → f ganan a la correcta, y /ɪ/ gana a /iː/ por más
    r = analyze(heard({"t": SURE - 1, "f": SURE, "θ": SURE - 6}, "ɹ", {"ɪ": SURE, "iː": SURE - 9}), THREE)
    assert [(i["phone"], i["heard"]) for i in r["words"][0]["issues"]] == [("iː", "ɪ"), ("θ", "f")]


def test_an_added_e_just_before_the_word_is_heard_even_in_mid_sentence():
    speak = ("speak", ("s", "p", "iː", "k"))
    to = ("to", ("t", "ə"))
    issues = analyze(heard("t", "ə", "", "", "", "", "e", "s", "p", "iː", "k"), to, speak)["words"][1]["issues"]
    assert issues and issues[0]["phone"] == "s-" and issues[0]["tip"] == EPENTHESIS


def test_a_syllable_added_just_after_the_word_is_heard():
    walked = ("walked", ("w", "ɔː", "k", "t"))
    issues = analyze(heard("w", "ɔː", "k", "ɪ", "d", "", ""), walked)["words"][0]["issues"]
    assert [i["phone"] for i in issues] == ["-ed"]


def test_too_little_audio_scores_zero_and_marks_every_word_unclear():
    r = analyze(heard("θ", "ɹ"), THREE)
    assert r == {"score": 0, "words": [{"word": "three", "score": 0, "phones": ["θ", "ɹ", "iː"], "unclear": True, "issues": []}]}


def test_a_homograph_is_graded_by_the_pronunciation_that_fits_the_audio():
    # eSpeak dijo /laɪv/; el audio es /lɪv/, tras otra palabra: los frames deben contarse desde el inicio de la frase
    live = ("live", ("l", "aɪ", "v"))
    word = analyze(heard("θ", "ɹ", "iː", "", "", "", "", "", "", "", "l", "ɪ", "v", ""), THREE, live)["words"][1]
    assert word["phones"] == ["l", "ɪ", "v"] and word["score"] >= 95 and word["issues"] == []


def test_function_words_do_not_count_because_natives_reduce_them_too():
    to = ("to", ("t", "ə"))
    r = analyze(heard("", "", "", "", "", "", "θ", "ɹ", "iː", ""), to, THREE)
    low, high = r["words"]
    assert low["score"] < 10 and low["unclear"] is False  # no se oyó, y aun así no se acusa
    assert high["score"] >= 95 and r["score"] == high["score"]
    alone = analyze(heard("", "", ""), to)  # si solo hay funcionales, cuentan ellas
    assert alone["score"] == alone["words"][0]["score"]


def test_the_sentence_scores_the_average_of_its_content_words():
    r = analyze(heard("θ", "ɹ", "iː", "", "", "", "", "", "", "", ""), THREE, ("tree", ("t", "ɹ", "iː")))
    high, low = (w["score"] for w in r["words"])
    assert high >= 95 and low < 20 and r["score"] == round((high + low) / 2)


def test_a_content_word_nobody_could_hear_is_unclear():
    word = analyze(heard("", "", "", ""), THREE)["words"][0]
    assert word["score"] < 10 and word["unclear"] is True


def test_when_the_sentence_is_not_what_sounded_its_notices_are_dropped():
    words = [(w, ("t", "iː")) for w in ("tea", "tree", "team", "teen")]
    r = analyze(heard(*[""] * 12), *words)
    assert r["mismatch"] is True and not any(w["issues"] or w["unclear"] for w in r["words"])


def test_log_probs_normalize_the_audio_and_return_probabilities():
    seen = {}

    def run(_, inputs):
        seen.update(inputs)
        return [np.array([[[2.0, 0.0, -1.0], [0.0, 0.0, 0.0]]], np.float32)]

    s = Scorer.__new__(Scorer)
    s.session = SimpleNamespace(run=run)
    logp = s.log_probs(np.array([1000, 2000, 3000, 6000], np.int16).tobytes())
    x = seen["input_values"]
    assert x.shape == (1, 4) and abs(x.mean()) < 1e-5 and abs(x.std() - 1) < 1e-3
    assert np.allclose(np.exp(logp).sum(-1), 1) and np.allclose(np.exp(logp[1]), 1 / 3)
    assert logp[0].argmax() == 0


def test_a_word_sounds_like_its_phonemes_or_a_symbol_like_its_spelling():
    s = scorer(heard(""), THREE)
    assert s.sound_of("three") == ("θ", "ɹ", "iː")
    s.phonemes = SimpleNamespace(sentence=lambda text: ())
    assert s.sound_of("C++") == "c++"


def phonemes(raw) -> Phonemes:
    p = Phonemes.__new__(Phonemes)
    p.vocab, p.lock, p.separator, p.asked = {"t": 1, "ə": 2}, threading.Lock(), None, []

    def phonemize(texts, separator, strip):
        p.asked += texts
        return [raw(texts[0])]

    p.backend = SimpleNamespace(phonemize=phonemize)
    return p


def test_groups_keep_only_what_the_model_knows_and_straighten_the_apostrophe():
    p = phonemes(lambda text: "t ə | x | t")
    assert p._groups("I’m") == [("t", "ə"), (), ("t",)]
    assert p.asked == ["I'm"]


def test_if_the_sentence_cannot_be_split_each_word_is_phonemized_alone():
    answers = {"to the": "t ə", "to": "t", "the": "ə"}  # 2 palabras, 1 grupo
    assert phonemes(answers.get)._sentence("to the") == (("to", ("t",)), ("the", ("ə",)))


def test_a_word_without_phonemes_is_dropped_and_a_number_keeps_all_its_groups():
    answers = {"x 20": "x | t | ə", "x": "x", "20": "t | ə"}
    assert phonemes(answers.get)._sentence("x 20") == (("20", ("t", "ə")),)
