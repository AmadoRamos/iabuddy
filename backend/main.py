"""Backend de IABuddy: FastAPI + WebSocket de audio.

    uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000

Necesita whisper-server y Ollama levantados (iabuddy.bat se encarga). Si existe
frontend/dist (npm run build), también sirve la app en http://127.0.0.1:8000.
"""

import asyncio
import io
import json
import logging
import mimetypes
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import httpx
import yaml
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import MODELS, settings
from .partner import scenarios
from .partner.prompts import GREETING, SYSTEMS
from .pipeline.llm import OllamaLLM
from .pipeline.stt import WhisperSTT
from .pipeline.tts import RATE as TTS_RATE
from .pipeline.tts import KokoroTTS
from .pipeline.turn_manager import Session
from .pipeline.vad import StreamingVad
from .pronunciation.scorer import Scorer
from .session_log import SessionLog, setup_file_logging
from .storage.db import Store
from .tutor.tutor import Tutor

log = logging.getLogger("iabuddy")
DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"
DRILLS = yaml.safe_load((Path(__file__).parent / "pronunciation" / "drills.yaml").read_text(encoding="utf-8"))
SCENARIOS = scenarios.load()  # un YAML mal escrito falla al arrancar, no a mitad de sesión


def load_scorer() -> Scorer | None:
    if not (settings.phoneme_model / "model.onnx").exists():
        log.warning("Sin modelo de fonemas en %s: no habrá pronunciación", settings.phoneme_model)
        return None
    scorer = Scorer(settings.phoneme_model)
    scorer.log_probs(bytes(32000))  # calienta: el primer análisis no tarda de más
    return scorer


def current_settings() -> dict:
    """Lo guardado en Ajustes; sin guardar, las variables de entorno de siempre."""
    defaults = {"silence_ms": settings.silence_ms, "speed": settings.speed, "feedback": "voz"}
    return {**defaults, **app.state.store.settings()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_file_logging(settings.log_dir)
    app.state.http = httpx.AsyncClient(timeout=120)
    app.state.stt = WhisperSTT(settings.whisper_url, app.state.http)
    app.state.llm = OllamaLLM(settings.ollama_url, settings.llm_model, app.state.http)
    app.state.tutor = Tutor(app.state.llm)
    app.state.store = Store(settings.db_path)
    app.state.tts = KokoroTTS(settings.kokoro_model, settings.kokoro_voices, settings.voice, current_settings()["speed"])
    await asyncio.to_thread(app.state.tts.synth, "Warm up.")
    app.state.scorer = await asyncio.to_thread(load_scorer)
    try:
        await app.state.llm.warm()
    except httpx.HTTPError as e:  # /api/health lo reporta; la UI muestra el aviso
        log.warning("No se pudo cargar el LLM al arrancar: %s", e)
    yield
    await app.state.http.aclose()


app = FastAPI(title="IABuddy", lifespan=lifespan)


@app.get("/api/health")
async def health() -> dict:
    async def up(url: str) -> bool:
        try:
            return (await app.state.http.get(url, timeout=2)).status_code < 500
        except httpx.HTTPError:
            return False

    whisper_base = settings.whisper_url.rsplit("/", 1)[0] + "/"
    whisper, ollama = await asyncio.gather(up(whisper_base), up(f"{settings.ollama_url}/api/version"))
    return {"whisper": whisper, "ollama": ollama, "model": settings.llm_model,
            "pronunciation": app.state.scorer is not None, "voice": settings.voice, "models_dir": str(MODELS)}


class SettingsPatch(BaseModel):
    silence_ms: int | None = Field(None, ge=400, le=2000)
    speed: float | None = Field(None, ge=0.8, le=1.1)
    feedback: Literal["silencioso", "panel", "voz"] | None = None


@app.get("/api/settings")
async def get_settings() -> dict:
    return current_settings()


@app.put("/api/settings")
async def put_settings(patch: SettingsPatch) -> dict:
    app.state.store.save_settings(patch.model_dump(exclude_none=True))
    current = current_settings()
    app.state.tts.speed = current["speed"]  # desde la próxima frase; el silencio lo aplica cada sesión
    return current


@app.get("/api/voice-sample")
async def voice_sample() -> Response:
    """La voz de Buddy a la velocidad actual, para oírla sin abrir el micrófono."""
    pcm = await asyncio.to_thread(app.state.tts.synth, "Hi! This is how I sound at this speed. Tell me about your day.")
    wav = io.BytesIO()
    with wave.open(wav, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(TTS_RATE)
        f.writeframes(pcm)
    return Response(wav.getvalue(), media_type="audio/wav", headers={"Cache-Control": "no-store"})


@app.get("/api/topics")
async def topics() -> list[dict]:
    return app.state.store.topics()


@app.get("/api/scenarios")
async def scenario_list() -> list[dict]:
    stars = app.state.store.scenario_stars()
    return [{**scenarios.public(sc), "stars": stars.get(sc["id"], 0)} for sc in SCENARIOS.values()]


@app.get("/api/drills")
async def drills() -> dict:
    counts = app.state.store.sound_counts()
    sounds = [{**d, "errors": sum(counts.get(p, 0) for p in d["phones"])} for d in DRILLS]
    sounds.sort(key=lambda d: -d["errors"])  # primero lo que más fallas
    return {"sounds": sounds, "failed": app.state.store.failed_phrases(), "review": app.state.store.review_items()}


@app.get("/api/progress")
async def progress() -> dict:
    data = app.state.store.progress()
    for s in data["sessions"]:  # el título del escenario vive en su YAML, no en la base de datos
        scenario = SCENARIOS.get(s["scenario"])
        s["title"] = scenario["title"] if scenario else s["topic"] or "Conversación libre"
    return data


class ReviewAnswer(BaseModel):
    key: str
    known: bool


@app.post("/api/review")
async def review(answer: ReviewAnswer) -> dict:
    app.state.store.answer_review(answer.key, answer.known)
    return app.state.store.review_status()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    session_log = SessionLog(settings.log_dir / "sessions", settings.log_audio)
    session = Session(
        send_json=ws.send_json, send_bytes=ws.send_bytes,
        vad=StreamingVad(settings.vad_model), stt=app.state.stt, llm=app.state.llm, tts=app.state.tts,
        tutor=app.state.tutor, store=app.state.store, scenarios=SCENARIOS, scorer=app.state.scorer, log=session_log,
        silence_ms=current_settings()["silence_ms"], systems=SYSTEMS, greeting=GREETING,
    )
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes"):
                await session.on_audio(msg["bytes"])
            elif msg.get("text"):
                await session.on_control(json.loads(msg["text"]))
    except WebSocketDisconnect:
        pass
    finally:
        await session.close()
        session_log.close()


if DIST.exists():  # al final: las rutas de arriba tienen prioridad
    # Windows puede asociar .js a text/plain en el registro y el navegador rechaza el módulo.
    # init() primero: lee el registro; si fuera después, pisaría el add_type.
    mimetypes.init()
    mimetypes.add_type("text/javascript", ".js")
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
