"""STT: whisper.cpp `large-v3-q5_0` servido por whisper-server (S1)."""

import io
import wave

import httpx


def pcm_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class WhisperSTT:
    def __init__(self, url: str, client: httpx.AsyncClient):
        self.url, self.client = url, client

    async def transcribe(self, pcm: bytes) -> str:
        r = await self.client.post(
            self.url,
            files={"file": ("turn.wav", pcm_to_wav(pcm), "audio/wav")},
            data={"response_format": "json", "temperature": "0"},
        )
        r.raise_for_status()
        return " ".join(r.json()["text"].split())
