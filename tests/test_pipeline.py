"""Los adaptadores del loop de voz contra servidores y modelos de mentira: lo que envían y cómo leen la respuesta."""

import io
import json
import logging
import wave

import httpx
import numpy as np
import pytest

from backend.pipeline import tts as tts_module
from backend.pipeline import vad as vad_module
from backend.pipeline.llm import OllamaLLM
from backend.pipeline.stt import WhisperSTT, pcm_to_wav
from backend.pipeline.tts import KokoroTTS
from backend.pipeline.vad import CTX, SR, WIN, StreamingVad


def server(answer) -> httpx.AsyncClient:
    """`answer(request)` da el texto de la respuesta, o una httpx.Response."""
    def handler(request):
        got = answer(request)
        return got if isinstance(got, httpx.Response) else httpx.Response(200, text=got)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def lines(*objects) -> str:
    return "\n\n".join(json.dumps(o) for o in objects)  # con líneas vacías, como puede llegar


# ── Whisper ──────────────────────────────────────────────────────────────────


def test_pcm_becomes_a_mono_16_bit_wav():
    with wave.open(io.BytesIO(pcm_to_wav(b"\1\0\2\0"))) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.readframes(2)) == (1, 2, 16000, b"\1\0\2\0")


async def test_whisper_receives_the_wav_and_its_text_comes_back_tidy():
    seen = {}

    def answer(request):
        seen["url"], seen["body"] = str(request.url), request.read()
        return json.dumps({"text": "  Hello \n  world  "})

    async with server(answer) as client:
        assert await WhisperSTT("http://w/inference", client).transcribe(b"\1\0") == "Hello world"
    assert seen["url"] == "http://w/inference"
    assert pcm_to_wav(b"\1\0") in seen["body"] and b'name="file"; filename="turn.wav"' in seen["body"]
    assert b'name="response_format"\r\n\r\njson' in seen["body"] and b'name="temperature"\r\n\r\n0' in seen["body"]


async def test_a_whisper_error_is_not_read_as_silence():
    async with server(lambda _: httpx.Response(500)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await WhisperSTT("http://w/inference", client).transcribe(b"\1\0")


# ── Ollama ───────────────────────────────────────────────────────────────────


def requests_to(answer):
    sent = []

    def handler(request):
        sent.append((str(request.url), json.loads(request.read())))
        return answer

    return server(handler), sent


async def test_stream_yields_each_piece_and_asks_for_the_right_model():
    client, sent = requests_to(lines({"message": {"content": "Hi"}}, {"message": {"content": ""}},
                                     {"message": {"content": " there"}}, {"done": True}))
    messages = [{"role": "user", "content": "x"}]
    async with client:
        assert [p async for p in OllamaLLM("http://o", "m", client).stream(messages)] == ["Hi", " there"]
    url, body = sent[0]
    assert url == "http://o/api/chat" and body["model"] == "m" and body["messages"] == messages
    assert body["stream"] is True and body["think"] is False and body["keep_alive"] == "30m"
    assert body["options"] == {"num_ctx": 4096, "temperature": 0.7}


async def test_an_error_inside_the_stream_stops_the_reply():
    client, _ = requests_to(lines({"message": {"content": "Hi"}}, {"error": "sin memoria"}, {"message": {"content": "no"}}))
    got = []
    async with client:
        with pytest.raises(RuntimeError, match="sin memoria"):
            async for piece in OllamaLLM("http://o", "m", client).stream([]):
                got.append(piece)
    assert got == ["Hi"]


@pytest.mark.parametrize("call", [
    lambda llm: llm.warm(),
    lambda llm: llm.chat_json([], {}),
    lambda llm: anext(llm.stream([])),
])
async def test_an_http_error_from_ollama_is_raised(call):
    async with server(lambda _: httpx.Response(500)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await call(OllamaLLM("http://o", "m", client))


async def test_chat_json_forces_the_schema_with_no_creativity_and_parses_the_answer(caplog):
    client, sent = requests_to(json.dumps({"message": {"content": '{"ok": true}'}, "eval_count": 7}))
    schema = {"type": "object"}
    async with client:
        with caplog.at_level(logging.INFO, logger="iabuddy"):
            assert await OllamaLLM("http://o", "m", client).chat_json([{"role": "user", "content": "x"}], schema) == {"ok": True}
    assert "LLM json" in caplog.text and "respuesta 7 tokens" in caplog.text
    body = sent[0][1]
    assert body["format"] == schema and body["stream"] is False and body["options"]["temperature"] == 0
    assert body["options"]["num_ctx"] == 4096


async def test_warm_loads_the_model_without_asking_anything():
    client, sent = requests_to("{}")
    async with client:
        await OllamaLLM("http://o", "m", client).warm()
    assert sent[0][0] == "http://o/api/chat" and sent[0][1]["messages"] == [] and sent[0][1]["stream"] is False


# ── Kokoro ───────────────────────────────────────────────────────────────────


def test_tts_clips_to_int16_with_the_current_voice_and_speed(monkeypatch):
    calls = []

    class FakeKokoro:
        def __init__(self, model, voices):
            calls.append((model, voices))

        def create(self, text, voice, speed, lang):
            calls.append((text, voice, speed, lang))
            return np.array([-2.0, -1.0, 0.0, 0.5, 2.0], np.float32), 24000

    monkeypatch.setattr(tts_module, "Kokoro", FakeKokoro)
    tts = KokoroTTS("model.onnx", "voices.bin", "af_heart", 0.9)
    tts.speed = 1.1  # Ajustes la cambia en caliente
    pcm = np.frombuffer(tts.synth("Hi."), "<i2")
    assert pcm.tolist() == [-32767, -32767, 0, 16383, 32767]
    assert calls == [("model.onnx", "voices.bin"), ("Hi.", "af_heart", 1.1, "en-us")]


# ── Silero ───────────────────────────────────────────────────────────────────


class FakeSilero:
    """Da la probabilidad de voz que dicta el test y anota lo que recibe."""

    def __init__(self, *probabilities):
        self.probabilities, self.inputs = list(probabilities), []

    def run(self, _, inputs):
        self.inputs.append(inputs)
        return np.array([[self.probabilities.pop(0)]]), inputs["state"] + 1


@pytest.fixture
def vad(monkeypatch):
    def build(*probabilities):
        silero = FakeSilero(*probabilities)
        monkeypatch.setattr(vad_module.ort, "InferenceSession", lambda path, providers: silero)
        return StreamingVad("silero.onnx"), silero

    return build


def window(n: int = WIN, value: int = 0) -> bytes:
    return np.full(n, value, np.int16).tobytes()


def test_vad_waits_for_a_complete_window_and_keeps_the_rest(vad):
    v, silero = vad(0.9, 0.9, 0.9)
    assert v.feed(window(WIN - 1)) == [] and silero.inputs == []
    assert v.feed(window(1)) == [True]
    assert v.feed(window(WIN * 2 + 10)) == [True, True] and len(v.pending) == 10


def test_vad_hysteresis_starts_at_0_5_and_only_stops_below_0_35(vad):
    v, _ = vad(0.4, 0.5, 0.4, 0.35, 0.34, 0.4)
    assert v.feed(window(WIN * 6)) == [False, True, True, True, False, False]


def test_vad_feeds_each_window_with_the_context_and_state_of_the_last_one(vad):
    v, silero = vad(0.1, 0.1)
    v.feed(np.arange(WIN, dtype=np.int16).tobytes() + window())
    a, b = silero.inputs
    assert a["input"].shape == (1, CTX + WIN) and a["sr"] == SR
    assert a["input"][0, 0] == 0 and a["input"][0, CTX + 1] == pytest.approx(1 / 32768)
    assert np.array_equal(b["input"][0, :CTX], a["input"][0, -CTX:])
    assert (b["state"] == a["state"] + 1).all()


def test_vad_reset_forgets_everything(vad):
    v, silero = vad(0.9, 0.1)
    assert v.feed(window(WIN + 3, 1000)) == [True]
    v.reset()
    assert v.speaking is False and len(v.pending) == 0
    assert v.feed(window()) == [False]
    assert (silero.inputs[1]["state"] == 0).all() and (silero.inputs[1]["input"] == 0).all()
