"""Spike S6 — Ida y vuelta por terminal: micrófono → VAD → STT → LLM → TTS → audífonos.

    # whisper-server con el modelo elegido en S1 (Ollama de la bandeja ya sirve gemma4):
    C:\\Tools\\whisper.cpp\\build\\bin\\Release\\whisper-server.exe -m C:\\Models\\whisper\\ggml-large-v3-q5_0.bin -l en --port 8182
    uv run --group spikes python spikes/s6_roundtrip.py      (o hablar_s6.bat)

Espacio = empezar a hablar · Espacio otra vez = terminar (o 1,5 s de silencio) · q = salir.
Por turno mide cada etapa y la latencia que importa: del fin de tu voz al primer audio.
Prueba sin micrófono: --file data/dataset/e01.wav
"""

import argparse
import csv
import json
import msvcrt
import queue
import re
import threading
import time
import wave
from pathlib import Path

import numpy as np
import onnxruntime as ort
import sounddevice as sd
from kokoro_onnx import Kokoro
from s1_stt import whisper
from s2_llm import HISTORY, SYSTEM, post
from s4_vad import CTX, OFF, ON, SR, WIN

ROOT = Path(__file__).resolve().parents[1]
SILENCE_MS = 1500  # red de seguridad (S4); el fin de turno normal es la tecla
FIRST_CUT = re.compile(r"^(.+?\w.*?[,.!?;:])(\s|$)")  # primer trozo: hasta la 1.ª puntuación
SENTENCE = re.compile(r"^(.+?[.!?])(\s|$)")


class Vad:
    """Silero VAD en streaming (mismos parámetros que S4)."""

    def __init__(self, model: Path):
        self.sess = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
        self.state = np.zeros((2, 1, 128), np.float32)
        self.ctx = np.zeros((1, CTX), np.float32)
        self.speaking = False

    def step(self, frame: np.ndarray) -> bool:
        x = np.concatenate([self.ctx, frame[None]], axis=1)
        out, self.state = self.sess.run(None, {"input": x, "state": self.state, "sr": np.array(SR, np.int64)})
        self.ctx = x[:, -CTX:]
        p = float(out[0, 0])
        self.speaking = p >= ON or (self.speaking and p >= OFF)
        return self.speaking


def record_turn(vad: Vad) -> tuple[bytes, float, float, str]:
    """Graba hasta Espacio o silencio. Devuelve (pcm, t_fin_voz, t_cierre, motivo)."""
    chunks: queue.Queue[bytes] = queue.Queue()
    pcm, pending = b"", np.zeros(0, np.float32)
    last_voice = heard = None
    with sd.RawInputStream(samplerate=SR, channels=1, dtype="int16",
                           callback=lambda d, *_: chunks.put(bytes(d))):
        print("  [REC] habla... (Espacio para terminar)", flush=True)
        while True:
            while not chunks.empty():
                data = chunks.get()
                pcm += data
                pending = np.concatenate([pending, np.frombuffer(data, np.int16).astype(np.float32) / 32768])
                while len(pending) >= WIN:
                    if vad.step(pending[:WIN]):
                        heard, last_voice = True, time.perf_counter()
                    pending = pending[WIN:]
            now = time.perf_counter()
            if msvcrt.kbhit() and msvcrt.getwch() == " ":
                return pcm, last_voice or now, now, "tecla"
            if heard and now - last_voice >= SILENCE_MS / 1000:
                return pcm, last_voice, now, "silencio"
            time.sleep(0.01)


def to_wav(pcm: bytes) -> Path:
    path = ROOT / "data" / "s6" / "last_turn.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return path


def speak(tts: Kokoro, texts: "queue.Queue[str | None]", marks: dict, voice: str, speed: float) -> None:
    """Hilo: sintetiza cada trozo en cuanto llega y lo reproduce en cola."""
    with sd.OutputStream(samplerate=24000, channels=1, dtype="float32") as out:
        while (text := texts.get()) is not None:
            t = time.perf_counter()
            samples, _ = tts.create(text, voice=voice, speed=speed, lang="en-us")
            marks.setdefault("tts_first", time.perf_counter() - t)
            marks.setdefault("audio", time.perf_counter())
            out.write(samples.astype(np.float32)[:, None])


def respond(args, tts, messages: list, marks: dict) -> str:
    """LLM en streaming → trozos → hilo de TTS. Devuelve el texto completo."""
    texts: queue.Queue[str | None] = queue.Queue()
    speaker = threading.Thread(target=speak, args=(tts, texts, marks, args.voice, args.speed))
    speaker.start()
    payload = {"model": args.model, "messages": messages, "stream": True, "think": False,
               "keep_alive": "30m", "options": {"num_ctx": 4096, "temperature": 0.7}}
    full = buf = ""
    with post(f"{args.ollama}/api/chat", payload) as resp:
        for line in resp:
            piece = json.loads(line).get("message", {}).get("content", "")
            if piece:
                marks.setdefault("llm_token", time.perf_counter())
            full += piece
            buf += piece
            while m := (SENTENCE if "llm_chunk" in marks else FIRST_CUT).match(buf.lstrip()):
                marks.setdefault("llm_chunk", time.perf_counter())
                texts.put(m.group(1).strip())
                buf = buf.lstrip()[m.end():]
    if buf.strip():
        marks.setdefault("llm_chunk", time.perf_counter())
        texts.put(buf.strip())
    texts.put(None)
    speaker.join()
    return full.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--whisper", default="http://127.0.0.1:8182/inference")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    ap.add_argument("--model", default="gemma4:12b-it-qat")
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--speed", type=float, default=0.9)
    ap.add_argument("--file", type=Path, help="usa este WAV como tu turno (prueba sin micrófono)")
    args = ap.parse_args()
    out = ROOT / "data" / "s6"
    out.mkdir(parents=True, exist_ok=True)

    print("Cargando modelos...", flush=True)
    stt = whisper(args.whisper, None)
    tts = Kokoro("C:/Models/kokoro/kokoro-v1.0.onnx", "C:/Models/kokoro/voices-v1.0.bin")
    tts.create("Warm up.", voice=args.voice, lang="en-us")
    vad = Vad(Path("C:/Models/silero/silero_vad.onnx"))
    messages = [{"role": "system", "content": SYSTEM}, *HISTORY[:1]]
    post(f"{args.ollama}/api/chat", {"model": args.model, "messages": messages, "stream": False,
                                    "think": False, "keep_alive": "30m"}).close()  # carga gemma
    print(f"\nSam: {HISTORY[0]['content']}")

    log = out / "turns.csv"
    new = not log.exists()
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["fin", "espera_fin_ms", "stt_ms", "llm_token_ms", "llm_trozo_ms", "tts_ms",
                        "total_desde_voz_ms", "total_desde_cierre_ms", "tu", "sam"])
        while True:
            if args.file:
                with wave.open(str(args.file)) as wf:
                    pcm = wf.readframes(wf.getnframes())
                t_voice = t_close = time.perf_counter()
                reason = "archivo"
            else:
                print("\n[Espacio] hablar · [q] salir", flush=True)
                key = msvcrt.getwch()
                if key.lower() == "q":
                    break
                if key != " ":
                    continue
                pcm, t_voice, t_close, reason = record_turn(vad)
            marks: dict = {}
            text = stt(to_wav(pcm)).strip()
            t_stt = time.perf_counter()
            print(f"Tú:  {text}")
            if not text:
                continue
            messages.append({"role": "user", "content": text})
            print("Sam: ", end="", flush=True)
            reply = respond(args, tts, messages, marks)
            print(reply)
            messages.append({"role": "assistant", "content": reply})

            def ms(a, b):
                return round((b - a) * 1000)

            row = [reason, ms(t_voice, t_close), ms(t_close, t_stt), ms(t_stt, marks["llm_token"]),
                   ms(t_stt, marks["llm_chunk"]), round(marks["tts_first"] * 1000),
                   ms(t_voice, marks["audio"]), ms(t_close, marks["audio"]), text, reply]
            w.writerow(row)
            f.flush()
            print(f"  [tiempos] fin por {reason} (esperó {row[1]} ms) · STT {row[2]} · LLM 1.er token {row[3]} "
                  f"/ 1.er trozo {row[4]} · TTS {row[5]} → primer audio a {row[7]} ms del cierre, "
                  f"{row[6]} ms del fin de tu voz")
            if args.file:
                break
    print(f"\nTurnos registrados en {log}")


if __name__ == "__main__":
    main()
