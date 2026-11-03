"""Configuración del backend. Cada valor se puede cambiar con una variable de entorno IABUDDY_*.

Los valores por defecto son los que eligieron los spikes de la Fase 0 (docs/SPIKES.md).
"""

import os
from dataclasses import dataclass
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"IABUDDY_{name}", default)


MODELS = Path(_env("MODELS_DIR", "C:/Models"))


@dataclass(frozen=True)
class Settings:
    whisper_url: str = _env("WHISPER_URL", "http://127.0.0.1:8182/inference")
    # Ollama propio de la app (iabuddy.bat) con OLLAMA_NUM_PARALLEL=2: el tutor corre a la vez
    # que el compañero (S2). Puerto aparte para no tocar la configuración del Ollama de la bandeja.
    ollama_url: str = _env("OLLAMA_URL", "http://127.0.0.1:11435")
    llm_model: str = _env("LLM_MODEL", "gemma4:12b-it-qat")
    kokoro_model: Path = MODELS / "kokoro" / "kokoro-v1.0.onnx"
    kokoro_voices: Path = MODELS / "kokoro" / "voices-v1.0.bin"
    voice: str = _env("VOICE", "af_heart")
    speed: float = float(_env("SPEED", "0.9"))
    vad_model: Path = MODELS / "silero" / "silero_vad.onnx"
    # S4: en habla libre hay pausas de hasta 2,5 s. Con la fusión de turno un corte es
    # inofensivo (si sigues hablando se une al turno), así que se puede esperar menos.
    silence_ms: int = int(_env("SILENCE_MS", "900"))
    db_path: Path = Path(_env("DB_PATH", str(Path(__file__).resolve().parents[1] / "data" / "iabuddy.db")))


settings = Settings()
