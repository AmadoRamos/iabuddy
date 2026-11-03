"""Backend de IABuddy: FastAPI + WebSocket de audio.

    uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000

Necesita whisper-server y Ollama levantados (iabuddy.bat se encarga). Si existe
frontend/dist (npm run build), también sirve la app en http://127.0.0.1:8000.
"""

import asyncio
import json
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .config import settings
from .partner.prompts import GREETING, SYSTEMS
from .pipeline.llm import OllamaLLM
from .pipeline.stt import WhisperSTT
from .pipeline.tts import KokoroTTS
from .pipeline.turn_manager import Session
from .pipeline.vad import StreamingVad
from .storage.db import Store
from .tutor.tutor import Tutor

log = logging.getLogger("iabuddy")
DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(timeout=120)
    app.state.stt = WhisperSTT(settings.whisper_url, app.state.http)
    app.state.llm = OllamaLLM(settings.ollama_url, settings.llm_model, app.state.http)
    app.state.tutor = Tutor(app.state.llm)
    app.state.store = Store(settings.db_path)
    app.state.tts = KokoroTTS(settings.kokoro_model, settings.kokoro_voices, settings.voice, settings.speed)
    await asyncio.to_thread(app.state.tts.synth, "Warm up.")
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
            "silence_ms": settings.silence_ms}


@app.get("/api/topics")
async def topics() -> list[dict]:
    return app.state.store.topics()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    session = Session(
        send_json=ws.send_json, send_bytes=ws.send_bytes,
        vad=StreamingVad(settings.vad_model), stt=app.state.stt, llm=app.state.llm, tts=app.state.tts,
        tutor=app.state.tutor, store=app.state.store,
        silence_ms=settings.silence_ms, systems=SYSTEMS, greeting=GREETING,
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


if DIST.exists():  # al final: las rutas de arriba tienen prioridad
    # Windows puede asociar .js a text/plain en el registro y el navegador rechaza el módulo.
    # init() primero: lee el registro; si fuera después, pisaría el add_type.
    mimetypes.init()
    mimetypes.add_type("text/javascript", ".js")
    app.mount("/", StaticFiles(directory=DIST, html=True), name="frontend")
