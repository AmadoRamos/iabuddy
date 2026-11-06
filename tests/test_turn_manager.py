"""Turn Manager con dobles: un byte de audio = una ventana de VAD (1 = voz, 0 = silencio)."""

import asyncio

from backend.pipeline.turn_manager import MIN_VOICE_FRAMES, RESUME_FRAMES, Session

VOICE, SILENCE = b"\x01", b"\x00"


class FakeVad:
    def feed(self, pcm: bytes) -> list[bool]:
        return [b == 1 for b in pcm]

    def reset(self) -> None:
        pass


class FakeSTT:
    def __init__(self, text: str = "Yesterday I go to the gym."):
        self.text, self.calls, self.gate = text, 0, asyncio.Event()
        self.gate.set()

    async def transcribe(self, pcm: bytes) -> str:
        self.calls += 1
        await self.gate.wait()
        return self.text


class FakeLLM:
    def __init__(self, pieces: list[str]):
        self.pieces, self.gate = pieces, asyncio.Event()
        self.gate.set()

    async def stream(self, messages):
        for i, p in enumerate(self.pieces):
            if i == 1:
                await self.gate.wait()  # permite parar a mitad de respuesta
            yield p


class FakeTTS:
    def synth(self, text: str) -> bytes:
        return text.encode()


def make(llm_pieces=("Oh, you went to the gym? ", "Nice! What did you do?"), stt=None):
    events: list = []
    now = [0.0]

    async def send_json(m):
        events.append(m)

    async def send_bytes(b):
        events.append(b)

    s = Session(send_json=send_json, send_bytes=send_bytes, vad=FakeVad(), stt=stt or FakeSTT(),
                llm=FakeLLM(list(llm_pieces)), tts=FakeTTS(), silence_ms=900,
                systems={"voz": "coach", "panel": "recast", "silencioso": "recast"},
                greeting="Hi!", clock=lambda: now[0])
    return s, events, now


def types(events):
    return [e["type"] if isinstance(e, dict) else "audio" for e in events]


def first(events, kind):
    return next(e for e in events if isinstance(e, dict) and e["type"] == kind)


async def test_key_turn_replies_and_records_history():
    s, events, _ = make()
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    await s.task
    assert first(events, "user_text")["text"] == "Yesterday I go to the gym."
    assert first(events, "user_text")["seconds"] == 0  # 10 bytes de prueba: la app suma estos segundos
    assert types(events).count("audio") == 3  # "Oh, you went to the gym?" · "Nice!" · "What did you do?"
    assert s.state == "idle"
    assert [m["role"] for m in s.messages] == ["system", "user", "assistant"]
    metrics = first(events, "metrics")
    assert metrics["reason"] == "tecla" and "first_audio" in metrics


async def test_turn_without_voice_is_discarded_without_stt():
    stt = FakeSTT()
    s, events, _ = make(stt=stt)
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * (MIN_VOICE_FRAMES - 1) + SILENCE * 5)
    await s.on_control({"type": "stop"})
    assert "turn_discarded" in types(events) and stt.calls == 0 and s.state == "idle"


async def test_silence_closes_turn_and_speaking_again_resumes_it():
    stt = FakeSTT()
    stt.gate.clear()  # el STT tarda: la respuesta aún no ha sonado
    s, events, now = make(stt=stt)
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    now[0] = 1.0
    await s.on_audio(SILENCE)
    assert s.state == "thinking"
    await asyncio.sleep(0)
    await s.on_audio(VOICE * RESUME_FRAMES)
    assert s.state == "listening" and "turn_resumed" in types(events)
    assert [m["role"] for m in s.messages] == ["system"]
    stt.gate.set()
    await s.on_control({"type": "stop"})
    await s.task
    assert stt.calls == 2 and [m["role"] for m in s.messages] == ["system", "user", "assistant"]


async def test_barge_in_cancels_reply_and_keeps_what_was_said():
    s, events, _ = make()
    s.llm.gate.clear()  # se queda tras el primer trozo
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    for _ in range(20):
        await asyncio.sleep(0)
        if s.state == "speaking":
            break
    assert s.state == "speaking" and "barge_in" not in types(events)  # abrir tu turno no es interrumpir
    await s.on_control({"type": "start"})
    assert "barge_in" in types(events) and s.state == "listening"
    assert s.messages[-1] == {"role": "assistant", "content": "Oh, you went to the gym?"}


async def test_changing_the_silence_setting_applies_to_the_open_session():
    s, _, _ = make()
    await s.on_control({"type": "settings", "silence_ms": 1500})
    assert s.silence_s == 1.5
    await s.on_control({"type": "settings", "silence_ms": "mucho"})
    assert s.silence_s == 1.5


async def test_a_short_noise_does_not_resume_a_turn_that_is_waiting_for_the_reply():
    stt = FakeSTT()
    stt.gate.clear()
    s, events, now = make(stt=stt)
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    now[0] = 1.0
    await s.on_audio(SILENCE)
    await asyncio.sleep(0)
    noise = VOICE * (RESUME_FRAMES - 1)
    await s.on_audio(noise + SILENCE + noise)  # el silencio corta la racha
    assert s.state == "thinking" and "turn_resumed" not in types(events)
    await s.on_audio(VOICE)  # esta completa RESUME_FRAMES seguidas
    assert s.state == "listening" and "turn_resumed" in types(events)


async def test_when_whisper_hears_nothing_the_turn_is_discarded_without_asking_the_llm():
    s, events, _ = make(stt=FakeSTT(""))
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    await s.task
    assert "turn_discarded" in types(events) and s.state == "idle"
    assert s.user_turns == 0 and len(s.messages) == 1 and "partner_text" not in types(events)


async def test_a_failing_reply_says_so_and_leaves_the_session_ready_for_another_turn():
    class BrokenLLM(FakeLLM):
        async def stream(self, messages):
            raise RuntimeError("sin modelo")
            yield

    s, events, _ = make()
    s.llm = BrokenLLM([])
    await s.on_control({"type": "start"})
    await s.on_audio(VOICE * 10)
    await s.on_control({"type": "stop"})
    await s.task
    assert first(events, "error")["message"] == "RuntimeError: sin modelo" and s.state == "idle"
