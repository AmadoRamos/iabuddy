"""TTS: Kokoro fp32 en CPU, voz `af_heart` a 0,9× (S3)."""

import threading
from pathlib import Path

import numpy as np
from kokoro_onnx import Kokoro

RATE = 24000


class KokoroTTS:
    def __init__(self, model: Path, voices: Path, voice: str, speed: float):
        self.kokoro = Kokoro(str(model), str(voices))
        self.voice, self.speed = voice, speed
        self.lock = threading.Lock()  # una síntesis a la vez: ya usa todos los núcleos

    def synth(self, text: str) -> bytes:
        """Texto → PCM int16 mono a 24 kHz. Bloquea: llamar con asyncio.to_thread."""
        with self.lock:
            samples, _ = self.kokoro.create(text, voice=self.voice, speed=self.speed, lang="en-us")
        return (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
