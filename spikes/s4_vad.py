"""Spike S4 — Fin de turno: ¿cuánto silencio esperar antes de cerrar tu turno?

    uv run --group spikes python spikes/s4_vad.py

Pasa el dataset por Silero VAD (ONNX, ventanas de 32 ms) y mide las pausas *dentro* de
cada grabación. Un umbral de silencio menor que una pausa interna = te cortaría a mitad de
frase. El umbral se suma entero a la latencia (fin de tu frase → respuesta), así que se
busca el menor que no corte.
"""

import argparse
import csv
import itertools
import wave
from pathlib import Path

import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[1]
SR, WIN, CTX = 16000, 512, 64  # Silero v5+: ventana de 512 muestras + 64 de contexto a 16 kHz
FRAME_MS = WIN / SR * 1000
ON, OFF = 0.5, 0.35  # histéresis como en el VADIterator oficial
MIN_SPEECH_MS = 250  # ignora chasquidos y respiraciones sueltas
TIMEOUTS = [300, 500, 700, 900, 1200, 1500]


def speech_probs(sess: ort.InferenceSession, audio: np.ndarray) -> np.ndarray:
    state = np.zeros((2, 1, 128), np.float32)
    ctx = np.zeros((1, CTX), np.float32)
    sr = np.array(SR, np.int64)
    probs = []
    for i in range(0, len(audio) - WIN + 1, WIN):
        x = np.concatenate([ctx, audio[None, i:i + WIN]], axis=1)
        out, state = sess.run(None, {"input": x, "state": state, "sr": sr})
        ctx = x[:, -CTX:]
        probs.append(float(out[0, 0]))
    return np.array(probs)


def segments(probs: np.ndarray) -> list[tuple[float, float]]:
    """Tramos de voz (inicio, fin) en ms, con histéresis y duración mínima."""
    segs, start, on = [], 0, False
    for i, p in enumerate(probs):
        if not on and p >= ON:
            on, start = True, i
        elif on and p < OFF:
            on = False
            segs.append((start * FRAME_MS, i * FRAME_MS))
    if on:
        segs.append((start * FRAME_MS, len(probs) * FRAME_MS))
    return [s for s in segs if s[1] - s[0] >= MIN_SPEECH_MS]


def pauses(segs: list[tuple[float, float]]) -> list[float]:
    return [b[0] - a[1] for a, b in itertools.pairwise(segs)]


def _selfcheck() -> None:
    p = np.array([0, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.1, 0.1, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9, 0])
    s = segments(p)
    assert len(s) == 2 and pauses(s) == [2 * FRAME_MS], s
    assert segments(np.array([0, 0.9, 0.9, 0])) == []  # 64 ms: demasiado corto


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2, path
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "dataset")
    ap.add_argument("--model", type=Path, default=Path("C:/Models/silero/silero_vad.onnx"))
    args = ap.parse_args()
    _selfcheck()

    sess = ort.InferenceSession(str(args.model), providers=["CPUExecutionProvider"])
    rows = list(csv.DictReader((args.data / "manifest.csv").open(encoding="utf-8")))
    per_kind: dict[str, list[float]] = {}
    print(f"{'id':6}{'voz (s)':>8}{'tramos':>7}  pausas internas (ms)")
    for r in rows:
        segs = segments(speech_probs(sess, read_wav(args.data / r["file"])))
        ps = pauses(segs)
        per_kind.setdefault(r["kind"], []).extend(ps)
        if r["kind"] == "free" or ps:
            voiced = sum(b - a for a, b in segs) / 1000
            print(f"{r['id']:6}{voiced:8.1f}{len(segs):7}  {', '.join(f'{p:.0f}' for p in sorted(ps, reverse=True))}")

    print("\nCortes a mitad de turno según el silencio de fin de turno:")
    print("| Silencio | " + " | ".join(f"Cortes en `{k}` ({len(v)} pausas)" for k, v in per_kind.items()) + " |")
    print("|---|" + "---|" * len(per_kind))
    for t in TIMEOUTS:
        print(f"| {t} ms | " + " | ".join(str(sum(p >= t for p in v)) for v in per_kind.values()) + " |")
    allp = sorted(p for v in per_kind.values() for p in v)
    if allp:
        print(f"\nPausas internas: n={len(allp)}, mediana {np.median(allp):.0f} ms, "
              f"p90 {np.percentile(allp, 90):.0f} ms, máx {allp[-1]:.0f} ms")


if __name__ == "__main__":
    main()
