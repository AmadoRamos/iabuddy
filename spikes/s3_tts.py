"""Spike S3 — TTS: Kokoro ONNX en CPU.

    uv run --group spikes python spikes/s3_tts.py

Mide la latencia de síntesis de una frase corta (lo que tarda el primer audio del
compañero) y el factor de tiempo real, con el modelo fp32 y el int8. Además genera
muestras de varias voces US a velocidad 1.0 y 0.9 en data/s3/voices/ para elegir de oído.
"""

import argparse
import statistics
import time
import wave
from pathlib import Path

import numpy as np
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parents[1]
SHORT = [  # ~10 palabras: lo típico de la primera frase del compañero
    "That sounds great! What did you do after the meeting?",
    "Oh, you went to the office very early yesterday.",
    "I love that idea. How long have you been working there?",
    "Nice! Do you usually cook at home on weekends?",
    "Thirty is a great age. Do you enjoy your job?",
]
SAMPLE = ("Hey! Good to see you again. So, you went to the office very early yesterday? "
          "That sounds like a long day. What kept you so busy?")
VOICES = ["af_heart", "af_bella", "af_nicole", "af_sarah", "am_michael", "am_fenrir", "am_puck", "am_adam"]


def save_wav(path: Path, samples: np.ndarray, sr: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--models", type=Path, default=Path("C:/Models/kokoro"))
    args = ap.parse_args()
    voices_bin = args.models / "voices-v1.0.bin"

    print("| Modelo | Frase corta (mediana / máx) | RTF |")
    print("|---|---|---|")
    for name in ["kokoro-v1.0.onnx", "kokoro-v1.0.int8.onnx"]:
        tts = Kokoro(str(args.models / name), str(voices_bin))
        tts.create("Warm up.", voice="af_heart", lang="en-us")  # calentamiento
        times, audio_s = [], 0.0
        for _ in range(3):
            for text in SHORT:
                t = time.perf_counter()
                samples, sr = tts.create(text, voice="af_heart", speed=1.0, lang="en-us")
                times.append((time.perf_counter() - t) * 1000)
                audio_s += len(samples) / sr
        rtf = sum(times) / 1000 / audio_s
        print(f"| {name} | {statistics.median(times):.0f} / {max(times):.0f} ms | {rtf:.3f} |")

    out = ROOT / "data" / "s3" / "voices"
    out.mkdir(parents=True, exist_ok=True)
    tts = Kokoro(str(args.models / "kokoro-v1.0.onnx"), str(voices_bin))
    for voice in VOICES:
        for speed in (1.0, 0.9):
            samples, sr = tts.create(SAMPLE, voice=voice, speed=speed, lang="en-us")
            save_wav(out / f"{voice}_{speed:.1f}.wav", samples, sr)
    print(f"\nMuestras de voz: {out}")


if __name__ == "__main__":
    main()
