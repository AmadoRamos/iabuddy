"""Graba el dataset de la Fase 0 (TODO 3.1).

    uv run --group spikes python spikes/record_dataset.py [--only error|pair|free] [--out DIR]

Recorre spikes/dataset_prompts.csv, graba cada frase del micrófono por defecto
(WAV 16 kHz mono, int16) y mantiene DIR/manifest.csv con el texto *literal* dicho.
Se puede cortar en cualquier momento y retomar: salta lo que ya está grabado.
"""

import argparse
import csv
import wave
from pathlib import Path

import sounddevice as sd

RATE = 16000
ROOT = Path(__file__).resolve().parents[1]
PROMPTS = Path(__file__).with_name("dataset_prompts.csv")
FIELDS = ["id", "kind", "file", "text", "seconds"]


def record() -> bytes:
    chunks = []
    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                           callback=lambda data, *_: chunks.append(bytes(data))):
        input("  [REC] Grabando... Enter para parar ")
    return b"".join(chunks)


def play(pcm: bytes) -> None:
    with sd.RawOutputStream(samplerate=RATE, channels=1, dtype="int16") as out:
        out.write(pcm)


def save_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)


def take() -> bytes | None:
    """Graba hasta que el usuario acepta la toma. None = saltar."""
    while True:
        cmd = input("  Enter = grabar · s = saltar · q = salir > ").strip().lower()
        if cmd == "q":
            raise KeyboardInterrupt
        if cmd == "s":
            return None
        pcm = record()
        secs = len(pcm) / 2 / RATE
        while (cmd := input(f"  {secs:.1f} s · Enter = guardar · p = escuchar · r = repetir > ")
               .strip().lower()) == "p":
            play(pcm)
        if cmd != "r":
            return pcm


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "dataset")
    ap.add_argument("--only", choices=["error", "pair", "free"])
    args = ap.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    manifest = args.out / "manifest.csv"
    prompts = list(csv.DictReader(PROMPTS.open(encoding="utf-8")))
    done = {}
    if manifest.exists():
        done = {r["id"]: r for r in csv.DictReader(manifest.open(encoding="utf-8"))}
    todo = [p for p in prompts if p["id"] not in done and args.only in (None, p["kind"])]

    print(f"Micrófono: {sd.query_devices(kind='input')['name']}")
    print(f"{len(done)} grabadas, {len(todo)} pendientes. Salida: {args.out}")
    print("Di la frase TAL CUAL, con sus errores. Si dices otra cosa, escribe lo que dijiste.")

    try:
        for i, p in enumerate(todo, 1):
            print(f"\n[{i}/{len(todo)}] {p['id']} ({p['kind']})\n  » {p['prompt']}")
            pcm = take()
            if pcm is None:
                continue
            default = "" if p["kind"] == "free" else p["prompt"]
            text = input(f"  Texto literal (Enter = {default!r}{' — rellenar después' if not default else ''}): ")
            save_wav(args.out / f"{p['id']}.wav", pcm)
            done[p["id"]] = {"id": p["id"], "kind": p["kind"], "file": f"{p['id']}.wav",
                             "text": text.strip() or default, "seconds": f"{len(pcm) / 2 / RATE:.2f}"}
            # Reescribe el manifest entero en el orden de prompts: barato y deja el CSV siempre válido.
            order = {q["id"]: n for n, q in enumerate(prompts)}
            with manifest.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, FIELDS)
                w.writeheader()
                w.writerows(sorted(done.values(), key=lambda r: order.get(r["id"], len(order))))
    except (KeyboardInterrupt, EOFError):
        print()
    print(f"\n{len(done)}/{len(prompts)} grabadas. Manifest: {manifest}")


if __name__ == "__main__":
    main()
