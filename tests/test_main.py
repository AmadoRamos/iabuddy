"""backend/main.py: el arranque, /api/health y el bucle de /ws, con dobles en lugar de modelos y servidores."""

import asyncio
import json
import os
import time
from dataclasses import replace

import httpx
import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient
from test_turn_manager import VOICE, FakeLLM, FakeSTT, FakeTTS, FakeVad

from backend import main
from backend.storage.db import Store


@pytest.fixture
def state(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "settings", replace(main.settings, log_dir=tmp_path / "logs", db_path=tmp_path / "db",
                                                  phoneme_model=tmp_path / "sin-modelo",
                                                  whisper_url="http://w/inference", ollama_url="http://o"))
    s = main.app.state
    for name, value in {"store": Store(":memory:"), "scorer": None, "tutor": None, "stt": FakeSTT(),
                        "llm": FakeLLM(["Nice. ", "Tell me more."]), "tts": FakeTTS()}.items():
        monkeypatch.setattr(s, name, value, raising=False)
    return s


# ── /api/health ──────────────────────────────────────────────────────────────


async def test_health_says_what_is_up(state, monkeypatch):
    urls = []

    def handler(request):
        urls.append(str(request.url))
        if request.url.host == "w":
            return httpx.Response(404)  # whisper-server responde: está vivo, aunque esa ruta no exista
        raise httpx.ConnectError("apagado")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(state, "http", client, raising=False)
        data = await main.health()
    assert sorted(urls) == ["http://o/api/version", "http://w/"]
    assert data["whisper"] is True and data["ollama"] is False and data["pronunciation"] is False
    assert data["model"] == main.settings.llm_model and data["voice"] == main.settings.voice


async def test_health_counts_a_server_error_as_down_and_reports_the_scorer(state, monkeypatch):
    transport = httpx.MockTransport(lambda r: httpx.Response(500 if r.url.host == "o" else 200))
    async with httpx.AsyncClient(transport=transport) as client:
        monkeypatch.setattr(state, "http", client, raising=False)
        state.scorer = object()
        data = await main.health()
    assert data["whisper"] is True and data["ollama"] is False and data["pronunciation"] is True


def test_health_is_served_at_its_route(state, monkeypatch):
    transport = httpx.MockTransport(lambda r: httpx.Response(200))
    monkeypatch.setattr(state, "http", httpx.AsyncClient(transport=transport), raising=False)
    assert TestClient(main.app).get("/api/health").json()["ollama"] is True


def test_topics_are_served_from_the_store(state):
    assert TestClient(main.app).get("/api/topics").json() == state.store.topics() != []


# ── Arranque ─────────────────────────────────────────────────────────────────


class Startup:
    """Lo que el arranque cargaría de verdad: la voz, el modelo en VRAM y los registros en disco."""

    def __init__(self, monkeypatch):
        self.tts, self.warmed, self.logs, self.warm_error = [], [], [], None
        startup = self

        class FakeKokoroTTS:
            def __init__(self, model, voices, voice, speed):
                startup.tts.append({"voice": voice, "speed": speed})
                self.said = []

            def synth(self, text):
                self.said.append(text)

        async def warm(_):
            startup.warmed.append(True)
            if startup.warm_error:
                raise startup.warm_error

        monkeypatch.setattr(main, "KokoroTTS", FakeKokoroTTS)
        monkeypatch.setattr(main, "setup_file_logging", self.logs.append)
        monkeypatch.setattr(main.OllamaLLM, "warm", warm)


async def test_startup_prepares_everything_and_closes_the_http_client(state, monkeypatch):
    startup = Startup(monkeypatch)
    state.scorer = "el de antes"
    store = Store(main.settings.db_path)
    store.save_settings({"speed": 1.05})  # lo guardado en Ajustes manda
    store.db.close()
    async with main.lifespan(main.app):
        assert startup.logs == [main.settings.log_dir] and startup.warmed == [True]
        assert startup.tts == [{"voice": main.settings.voice, "speed": 1.05}] and state.tts.said == ["Warm up."]
        assert state.stt.url == "http://w/inference" and state.llm.url == "http://o" and state.tutor.llm is state.llm
        assert state.scorer is None and state.store.settings() == {"speed": 1.05}
        assert not state.http.is_closed
    assert state.http.is_closed
    state.store.db.close()


async def test_startup_survives_an_ollama_that_is_not_there_yet(state, monkeypatch, caplog):
    startup = Startup(monkeypatch)
    startup.warm_error = httpx.ConnectError("apagado")
    async with main.lifespan(main.app):
        assert startup.warmed == [True]
    assert "No se pudo cargar el LLM" in caplog.text
    state.store.db.close()


async def test_startup_deletes_the_old_analyzed_sessions(state, monkeypatch):
    Startup(monkeypatch)
    sessions = main.settings.log_dir / "sessions"
    sessions.mkdir(parents=True)
    old = sessions / "vieja.jsonl"
    old.write_text("")
    os.utime(old, (time.time() - 31 * 86400,) * 2)
    async with main.lifespan(main.app):
        assert not old.exists()
    state.store.db.close()


def test_without_the_phoneme_model_there_is_no_pronunciation_but_the_app_works(state, caplog):
    assert main.load_scorer() is None
    assert "Sin modelo de fonemas" in caplog.text


def test_with_the_phoneme_model_the_scorer_is_warmed_up(state, monkeypatch):
    folder = main.settings.phoneme_model
    folder.mkdir()
    (folder / "model.onnx").write_bytes(b"")
    warmed = []

    class FakeScorer:
        def __init__(self, path):
            self.path = path

        def log_probs(self, pcm):
            warmed.append(len(pcm))

    monkeypatch.setattr(main, "Scorer", FakeScorer)
    assert main.load_scorer().path == folder and warmed == [32000]


# ── /ws ──────────────────────────────────────────────────────────────────────


def control(until: str | None = None, **msg) -> dict:
    return {"type": "websocket.receive", "text": json.dumps(msg), "until": until}


class FakeSocket:
    """Entrega su guion. `until` espera ese mensaje de la app antes de seguir, como haría quien la usa."""

    def __init__(self, *script):
        self.script, self.json, self.audio, self.accepted = list(script), [], [], False

    async def accept(self):
        self.accepted = True

    async def send_json(self, msg):
        self.json.append(msg)

    async def send_bytes(self, data):
        self.audio.append(data)

    async def receive(self):
        step = self.script.pop(0)
        if isinstance(step, Exception):
            await self.wait_for("metrics")
            raise step
        if step.get("until"):
            await self.wait_for(step["until"])
        return step

    async def wait_for(self, kind):
        async with asyncio.timeout(5):
            while kind not in [m["type"] for m in self.json]:
                await asyncio.sleep(0.005)


@pytest.fixture
def logs(state, monkeypatch):
    made = []

    class SpyLog(main.SessionLog):
        def __init__(self, *args):
            super().__init__(*args)
            made.append(self)

    monkeypatch.setattr(main, "SessionLog", SpyLog)
    monkeypatch.setattr(main, "StreamingVad", lambda path: FakeVad())
    return made


CONVERSATION = (control(type="hello"),
                control(type="start", until="partner_done"),
                {"type": "websocket.receive", "bytes": VOICE * 10},
                control(type="stop"))


@pytest.mark.parametrize("hang_up", [{"type": "websocket.disconnect", "until": "metrics"}, WebSocketDisconnect()],
                         ids=["mensaje", "excepcion"])
async def test_ws_carries_a_whole_turn_and_closes_the_session_when_the_tab_closes(logs, hang_up):
    socket = FakeSocket(*CONVERSATION, hang_up)
    await main.ws_endpoint(socket)
    assert socket.accepted and socket.script == []
    said = [m["text"] for m in socket.json if m["type"] == "user_text"]
    assert said == ["Yesterday I go to the gym."] and socket.audio  # oyó, respondió y sonó
    log = logs[0]
    assert log.file is None and log.path.parent == main.settings.log_dir / "sessions"
    kinds = [json.loads(line)["kind"] for line in log.path.read_text(encoding="utf-8").splitlines()]
    assert "turn_closed" in kinds and "closed_without_end" in kinds  # se cerró aunque nadie pulsó «Terminar»


async def test_ws_gives_the_session_what_it_needs_and_the_silence_you_saved(logs, state, monkeypatch):
    state.store.save_settings({"silence_ms": 1500})
    made = []
    real = main.Session

    def spy(**kwargs):
        made.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(main, "Session", spy)
    await main.ws_endpoint(FakeSocket({"type": "websocket.disconnect"}))
    args = made[0]
    assert args["silence_ms"] == 1500 and args["log"] is logs[0] and args["scenarios"] is main.SCENARIOS
    for name in ("stt", "llm", "tts", "tutor", "store", "scorer"):
        assert args[name] is getattr(state, name), name


async def test_ws_closes_the_log_even_if_a_message_breaks_the_loop(logs):
    with pytest.raises(json.JSONDecodeError):
        await main.ws_endpoint(FakeSocket({"type": "websocket.receive", "text": "{no es json"}))
    assert logs[0].file is None
