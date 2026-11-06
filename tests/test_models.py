"""Los modelos de verdad: lo único que los dobles no prueban, como los nombres de sus entradas. Sin ellos, se salta."""

import numpy as np
import pytest

from backend.config import settings
from backend.pipeline.tts import RATE, KokoroTTS
from backend.pipeline.vad import SR, StreamingVad
from backend.pronunciation.scorer import Scorer

MODELS = (settings.kokoro_model, settings.kokoro_voices, settings.vad_model, settings.phoneme_model / "model.onnx")
pytestmark = pytest.mark.skipif(not all(p.exists() for p in MODELS), reason="sin los modelos en C:\\Models")
SENTENCE = "I think the weather is better than yesterday."


@pytest.fixture(scope="module")
def voice() -> bytes:
    """Kokoro, llevado a los 16 kHz del micrófono."""
    pcm = KokoroTTS(settings.kokoro_model, settings.kokoro_voices, "af_heart", 0.9).synth(SENTENCE)
    x = np.frombuffer(pcm, "<i2").astype(float)
    return np.interp(np.arange(0, len(x), RATE / SR), np.arange(len(x)), x).astype("<i2").tobytes()


def test_silero_tells_voice_from_silence(voice):
    vad = StreamingVad(settings.vad_model)
    assert not any(vad.feed(bytes(SR * 2)))
    assert sum(vad.feed(voice)) > 20  # ventanas de 32 ms: más de 0,6 s de voz


def test_the_scorer_hears_a_native_voice_and_doubts_another_sentence(voice):
    scorer = Scorer(settings.phoneme_model)
    logp = scorer.log_probs(voice)
    assert logp.shape[1] == len(scorer.vocab) and np.allclose(np.exp(logp).sum(-1), 1, atol=1e-3)
    right = scorer.analyze(voice, SENTENCE)
    assert [w["word"] for w in right["words"]] == SENTENCE.rstrip(".").split()
    assert right["score"] >= 40 and "mismatch" not in right
    wrong = scorer.analyze(voice, "Purple monkeys dance quietly around big green umbrellas.")
    assert wrong["score"] < right["score"] - 20
