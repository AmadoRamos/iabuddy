"""Turn Manager: el estado de una conversación (una por WebSocket).

Estados: idle → listening → thinking → speaking → idle.

- `hello` empieza la sesión (con tema opcional) y Buddy saluda. `end` la cierra y devuelve el resumen.
- `start` (tecla) abre tu turno; se cierra con `stop` (tecla) o tras `silence_ms` de silencio.
- Fusión de turno (S4): si vuelves a hablar —o pulsas la tecla— antes de que suene la
  respuesta, se cancela y lo nuevo se une al mismo turno. Así un corte por silencio no molesta.
- Barge-in: `start` mientras el compañero habla cancela la generación y abre un turno nuevo.
  Lo que ya se envió a sonar queda en el historial; el navegador corta el audio por su cuenta.
- Un turno sin voz no llega al STT (S6: whisper alucina "Thank you." con silencio).
- Modo de corrección: el prompt de Buddy cambia con él (partner/prompts.py). En «voz» Buddy
  corrige dentro de su respuesta, como instructor; en «panel»/«silencioso» solo hace recasting.
- Tutor (Fase 2): analiza tu turno en paralelo con la respuesta. Sus correcciones, todas y
  explicadas en español, van al panel (`feedback`) y a la base de datos.
- `intent`: escribes lo que querías decir en un turno ya dicho. El tutor lo compara con lo que
  dijiste y, en modo «voz», Buddy te dice cómo decirlo y te invita a repetirlo.
- `say`: 🔊 escuchar una frase con la voz de Buddy (no entra en la conversación).

Al navegador: JSON {"type": ...} para estado y texto; binario = PCM int16 a 24 kHz.
"""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable

from .chunker import Chunker

log = logging.getLogger("iabuddy")

MIN_VOICE_FRAMES = 8  # ~250 ms de voz para que el turno cuente
RESUME_FRAMES = 3  # ~100 ms de voz seguida reabren un turno que aún no ha respondido
MAX_TEXT = 500  # límite para el texto que llega del navegador (intención, «escuchar»)


class Session:
    def __init__(self, *, send_json: Callable[[dict], Awaitable], send_bytes: Callable[[bytes], Awaitable],
                 vad, stt, llm, tts, silence_ms: int, systems: dict[str, str], greeting: str,
                 tutor=None, store=None, clock: Callable[[], float] = time.perf_counter):
        self.send_json, self.send_bytes = send_json, send_bytes
        self.vad, self.stt, self.llm, self.tts = vad, stt, llm, tts
        self.tutor, self.store = tutor, store
        self.silence_s, self.systems, self.clock = silence_ms / 1000, systems, clock
        self.greeting = greeting  # solo si no hay base de datos (los inicios viven en la tabla openers)
        self.feedback, self.topic_line = "voz", ""
        self.messages: list[dict] = [{"role": "system", "content": self._system()}]
        self.state = "idle"
        self.task: asyncio.Task | None = None
        self.tutor_tasks: set[asyncio.Task] = set()
        self.session_id: int | None = None
        self.user_turns = 0
        self.turns: dict[int, dict] = {}  # n.º de turno tuyo → {"text", "row"}, para la intención escrita
        self.intent_turns: set[int] = set()
        self.pending_line: tuple[str, str] | None = None  # reacción a una intención, si Buddy estaba ocupado
        self.spoken: list[str] = []
        self.closed_at = clock()
        self._reset_turn()

    # ── Entradas desde el WebSocket ──────────────────────────────────────────────

    async def on_control(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "hello" and self.state == "idle" and len(self.messages) == 1:
            self._set_feedback(msg.get("feedback"))
            self.task = asyncio.create_task(self._run(self._begin(msg.get("topic_id"))))
        elif kind == "settings":
            self._set_feedback(msg.get("feedback"))
        elif kind == "start":
            await self._start()
        elif kind == "stop" and self.state == "listening":
            await self._close("tecla")
        elif kind == "end":
            await self._end()
        elif kind == "intent":
            self._intent(msg.get("turn"), str(msg.get("text", "")).strip()[:MAX_TEXT])
        elif kind == "say" and self.state == "idle" and not self._busy():
            if text := str(msg.get("text", "")).strip()[:MAX_TEXT]:
                self.task = asyncio.create_task(self._run(self._say_only(text)))

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
        for t in self.tutor_tasks:
            t.cancel()

    def _system(self) -> str:
        return self.systems[self.feedback] + self.topic_line

    def _set_feedback(self, mode: str | None) -> None:
        if mode in self.systems:  # también a mitad de sesión: cambia cómo corrige Buddy desde ya
            self.feedback = mode
            self.messages[0]["content"] = self._system()

    def _busy(self) -> bool:
        return self.task is not None and not self.task.done()

    # ── Lo que querías decir (intención escrita) ─────────────────────────────────

    def _intent(self, turn, text: str) -> None:
        if not (self.tutor and text and turn in self.turns):
            return
        self.intent_turns.add(turn)  # a partir de aquí manda este análisis, no el automático
        task = asyncio.create_task(self._analyze_intent(turn, text))
        self.tutor_tasks.add(task)
        task.add_done_callback(self.tutor_tasks.discard)

    async def _analyze_intent(self, turn: int, intent: str) -> None:
        said, row = self.turns[turn]["text"], self.turns[turn]["row"]
        try:
            result = await self.tutor.analyze_intent(said, intent)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Fallo del tutor (intención)")
            await self.send_json({"type": "intent_failed", "turn": turn})
            return
        if self.store and row:
            self.store.add_feedback(row, result["corrected"], result["issues"], intent=intent)
        # Lo pediste tú: se muestra también en modo silencioso
        await self.send_json({"type": "feedback", "turn": turn, "text": said, "intent": intent, **result})
        english = result["corrected"]
        if self.feedback != "voz" or not english:
            return
        # Buddy, como instructor, te dice cómo decirlo y te invita a repetirlo
        note = f'(I could not say it well. What I meant: "{intent}". How do I say it?)'
        line = f"Oh, I see what you mean! You can say: {english} Want to try saying it?"
        if self.state == "idle" and not self._busy():
            self.task = asyncio.create_task(self._run(self._speak_line(note, line)))
        else:
            self.pending_line = (note, line)  # lo dirá al terminar lo que esté diciendo

    async def _speak_line(self, note: str, line: str) -> None:
        self.messages.append({"role": "user", "content": note})

        async def once() -> AsyncIterator[str]:
            yield line
        self.closed_at, self.audio_started = self.clock(), False
        await self._speak(once(), {})

    async def _say_only(self, text: str) -> None:
        """🔊 Escuchar: Buddy lee una frase. No entra en la conversación."""
        audio = await asyncio.to_thread(self.tts.synth, text)
        await self._set_state("speaking")
        await self.send_bytes(audio)
        await self.send_json({"type": "partner_done"})
        await self._set_state("idle")

    # ── Sesión ───────────────────────────────────────────────────────────────────

    async def _begin(self, topic_id: int | None) -> None:
        topic = self.store.topic(topic_id) if self.store and topic_id else None
        # Primer mensaje: uno de los varios de la tabla openers, para que no se repita siempre igual
        opener = self.store.pick_opener(topic and topic["id"]) if self.store else None
        greeting = opener["text"] if opener else self.greeting
        if topic:
            self.topic_line = (f"\n\nToday's topic, chosen by the user (title in Spanish): {topic['title']}. "
                               "Start there, but follow the user if they change topic.")
            self.messages[0]["content"] = self._system()
        if self.store:
            self.session_id = self.store.start_session(topic and topic["id"], opener and opener["id"])
        await self.send_json({"type": "session", "id": self.session_id, "topic": topic and topic["title"]})

        async def once() -> AsyncIterator[str]:
            yield greeting
        self.closed_at = self.clock()
        await self._speak(once(), {})

    async def _end(self) -> None:
        await self._cancel()
        if self.tutor_tasks:  # que terminen los análisis pendientes para que salgan en el resumen
            await asyncio.wait(self.tutor_tasks, timeout=15)
        summary = self.store.finish_session(self.session_id) if self.store and self.session_id else {}
        await self.send_json({"type": "summary", **summary})
        self.topic_line = ""
        self.messages = [{"role": "system", "content": self._system()}]
        self.session_id, self.user_turns, self.pending_line = None, 0, None
        self.turns, self.intent_turns = {}, set()
        self._reset_turn()
        await self._set_state("idle")

    # ── Turno ────────────────────────────────────────────────────────────────────

    def _reset_turn(self) -> None:
        self.pcm = bytearray()
        self.voice_frames, self.last_voice, self.resume_run = 0, self.clock(), 0
        self.close_reason: str | None = None
        self.audio_started = False
        self.turn_index = len(self.messages)
        self.turn_row: int | None = None  # fila del turno en la base de datos
        self.turn_tutor: asyncio.Task | None = None
        self.vad.reset()

    async def _set_state(self, state: str, **extra) -> None:
        self.state = state
        await self.send_json({"type": "state", "state": state, **extra})

    async def _start(self) -> None:
        if self.state == "thinking" and not self.audio_started:
            await self._resume()  # aún no sonó nada: sigues en el mismo turno
            return
        barge = self._busy()
        await self._cancel()
        self.pending_line = None  # ya estás hablando de otra cosa
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
        if self.turn_tutor:  # el texto va a cambiar: ese análisis ya no vale
            self.turn_tutor.cancel()
            self.turns.pop(self.user_turns, None)
            self.user_turns -= 1
        if self.turn_row and self.store:
            self.store.delete_turn(self.turn_row)
        self.turn_row = self.turn_tutor = None
        self.close_reason, self.last_voice, self.resume_run = None, self.clock(), 0
        await self.send_json({"type": "turn_resumed", "turn": self.user_turns + 1})
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
        except Exception as e:
            log.exception("Fallo en la respuesta")
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
        self.user_turns += 1
        await self.send_json({"type": "user_text", "text": text, "turn": self.user_turns})
        if self.store and self.session_id:
            self.turn_row = self.store.add_turn(self.session_id, "user", text, seconds=len(pcm) / 32000)
        self.turns[self.user_turns] = {"text": text, "row": self.turn_row}
        if self.tutor:
            partner_said = next((m["content"] for m in reversed(self.messages) if m["role"] == "assistant"), "")
            self.turn_tutor = asyncio.create_task(self._analyze(self.user_turns, text, partner_said, self.turn_row))
            self.tutor_tasks.add(self.turn_tutor)
            self.turn_tutor.add_done_callback(self.tutor_tasks.discard)
        self.messages.append({"role": "user", "content": text})
        await self._speak(self.llm.stream(self.messages), marks)
        await self.send_json({"type": "metrics", **marks})

    async def _analyze(self, turn: int, text: str, partner_said: str, row: int | None) -> None:
        """Tarea aparte: un barge-in no la cancela (el análisis sigue valiendo)."""
        try:
            result = await self.tutor.analyze(text, partner_said)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Fallo del tutor")
            return
        if turn in self.intent_turns:  # ya escribiste lo que querías decir: manda ese análisis
            return
        if self.store and row:
            self.store.add_feedback(row, result["corrected"], result["issues"])
        if self.feedback != "silencioso":
            await self.send_json({"type": "feedback", "turn": turn, "text": text, **result})

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
                said = " ".join(self.spoken)
                self.messages.append({"role": "assistant", "content": said})
                if self.store and self.session_id:
                    self.store.add_turn(self.session_id, "buddy", said)
            self.spoken = []
        await self.send_json({"type": "partner_done"})
        await self._set_state("idle")
        if self.pending_line:  # una intención que llegó mientras Buddy hablaba
            note, line = self.pending_line
            self.pending_line = None
            self.task = asyncio.create_task(self._run(self._speak_line(note, line)))

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
