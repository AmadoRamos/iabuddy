"""Turn Manager: el estado de una conversación (una por WebSocket).

Estados: idle → listening → thinking → speaking → idle.

- `start` (tecla) abre tu turno; se cierra con `stop` (tecla) o tras `silence_ms` de silencio.
- Fusión de turno (S4): si vuelves a hablar —o pulsas la tecla— antes de que suene la
  respuesta, se cancela y lo nuevo se une al mismo turno. Así un corte por silencio no molesta.
- Barge-in: `start` mientras el compañero habla cancela la generación y abre un turno nuevo.
  Lo que ya se envió a sonar queda en el historial; el navegador corta el audio por su cuenta.
- Un turno sin voz no llega al STT (S6: whisper alucina "Thank you." con silencio).

Al navegador: JSON {"type": ...} para estado y texto; binario = PCM int16 a 24 kHz.
"""

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from .chunker import Chunker

MIN_VOICE_FRAMES = 8  # ~250 ms de voz para que el turno cuente
RESUME_FRAMES = 3  # ~100 ms de voz seguida reabren un turno que aún no ha respondido


class Session:
    def __init__(self, *, send_json: Callable[[dict], Awaitable], send_bytes: Callable[[bytes], Awaitable],
                 vad, stt, llm, tts, silence_ms: int, system: str, greeting: str,
                 clock: Callable[[], float] = time.perf_counter):
        self.send_json, self.send_bytes = send_json, send_bytes
        self.vad, self.stt, self.llm, self.tts = vad, stt, llm, tts
        self.silence_s, self.greeting, self.clock = silence_ms / 1000, greeting, clock
        self.messages: list[dict] = [{"role": "system", "content": system}]
        self.state = "idle"
        self.task: asyncio.Task | None = None
        self.spoken: list[str] = []
        self.closed_at = clock()
        self._reset_turn()

    # ── Entradas desde el WebSocket ──────────────────────────────────────────────

    async def on_control(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "hello" and self.state == "idle" and len(self.messages) == 1:
            self.task = asyncio.create_task(self._run(self._greet()))
        elif kind == "start":
            await self._start()
        elif kind == "stop" and self.state == "listening":
            await self._close("tecla")

    async def on_audio(self, pcm: bytes) -> None:
        if self.state == "listening":
            self.pcm += pcm
            now = self.clock()
            for voiced in self.vad.feed(pcm):
                if voiced:
                    self.voice_frames, self.last_voice = self.voice_frames + 1, now
            if self.voice_frames >= MIN_VOICE_FRAMES and now - self.last_voice >= self.silence_s:
                await self._close("silencio")
        elif self.state == "thinking" and self.close_reason == "silencio":
            self.pcm += pcm  # por si hay fusión: sigue siendo tu turno
            for voiced in self.vad.feed(pcm):
                self.resume_run = self.resume_run + 1 if voiced else 0
                if self.resume_run >= RESUME_FRAMES:
                    await self._resume()
                    return

    async def close(self) -> None:
        await self._cancel()

    # ── Turno ────────────────────────────────────────────────────────────────────

    def _reset_turn(self) -> None:
        self.pcm = bytearray()
        self.voice_frames, self.last_voice, self.resume_run = 0, self.clock(), 0
        self.close_reason: str | None = None
        self.audio_started = False
        self.turn_index = len(self.messages)
        self.vad.reset()

    async def _set_state(self, state: str, **extra) -> None:
        self.state = state
        await self.send_json({"type": "state", "state": state, **extra})

    async def _start(self) -> None:
        if self.state == "thinking" and not self.audio_started:
            await self._resume()  # aún no sonó nada: sigues en el mismo turno
            return
        barge = self.task is not None and not self.task.done()
        await self._cancel()
        if barge:
            await self.send_json({"type": "barge_in"})
        self._reset_turn()
        await self._set_state("listening")

    async def _close(self, reason: str) -> None:
        if self.voice_frames < MIN_VOICE_FRAMES:
            self._reset_turn()
            await self.send_json({"type": "turn_discarded"})
            await self._set_state("idle")
            return
        self.close_reason, self.closed_at = reason, self.clock()
        self.turn_index, self.resume_run = len(self.messages), 0
        await self._set_state("thinking", reason=reason)
        self.task = asyncio.create_task(self._run(self._reply(bytes(self.pcm))))

    async def _resume(self) -> None:
        await self._cancel()
        del self.messages[self.turn_index:]  # quita tu mensaje si ya se había añadido
        self.close_reason, self.last_voice, self.resume_run = None, self.clock(), 0
        await self.send_json({"type": "turn_resumed"})
        await self._set_state("listening")

    async def _cancel(self) -> None:
        task, self.task = self.task, None
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    # ── Respuesta ────────────────────────────────────────────────────────────────

    def _ms(self) -> int:
        return round((self.clock() - self.closed_at) * 1000)

    async def _run(self, coro) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — cualquier fallo se muestra en la UI y la sesión sigue viva
            await self.send_json({"type": "error", "message": f"{type(e).__name__}: {e}"})
            await self._set_state("idle")

    async def _reply(self, pcm: bytes) -> None:
        marks: dict = {"reason": self.close_reason}
        text = await self.stt.transcribe(pcm)
        marks["stt"] = self._ms()
        if not text:
            await self.send_json({"type": "turn_discarded"})
            await self._set_state("idle")
            return
        await self.send_json({"type": "user_text", "text": text})
        self.messages.append({"role": "user", "content": text})
        await self._speak(self.llm.stream(self.messages), marks)
        await self.send_json({"type": "metrics", **marks})

    async def _greet(self) -> None:
        async def once() -> AsyncIterator[str]:
            yield self.greeting
        self.closed_at = self.clock()
        await self._speak(once(), {})

    async def _speak(self, pieces: AsyncIterator[str], marks: dict) -> None:
        chunker = Chunker()
        self.spoken = []
        try:
            async for piece in pieces:
                marks.setdefault("llm_token", self._ms())
                for chunk in chunker.feed(piece):
                    await self._say(chunk, marks)
            if rest := chunker.flush():
                await self._say(rest, marks)
        finally:  # también al cancelar: lo que ya se envió a sonar queda en el historial
            if self.spoken:
                self.messages.append({"role": "assistant", "content": " ".join(self.spoken)})
            self.spoken = []
        await self.send_json({"type": "partner_done"})
        await self._set_state("idle")

    async def _say(self, chunk: str, marks: dict) -> None:
        marks.setdefault("first_chunk", self._ms())
        audio = await asyncio.to_thread(self.tts.synth, chunk)
        if not self.audio_started:
            self.audio_started = True
            marks["first_audio"] = self._ms()
            await self._set_state("speaking")
        self.spoken.append(chunk)
        await self.send_json({"type": "partner_text", "text": chunk})
        await self.send_bytes(audio)
