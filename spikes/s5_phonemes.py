"""Spike S5 — Pronunciación: ¿wav2vec2 de fonemas distingue ship de sheep en tu voz?

    $env:PHONEMIZER_ESPEAK_LIBRARY = "C:\\Program Files\\eSpeak NG\\libespeak-ng.dll"
    uv run --group spikes python spikes/s5_phonemes.py

Para cada grabación de pares mínimos (p*) del dataset:
  1. transcribe los fonemas que oye el modelo (CTC greedy, IPA de eSpeak);
  2. puntúa candidatos —la palabra que querías decir y su "error" típico (la otra del par,
     -ed como /ɪd/, e- delante de s+consonante)— con la verosimilitud CTC del audio
     bajo cada secuencia de fonemas. Gana el candidato con menor pérdida.

Lo que se mide es si el modelo *separa* las dos palabras de cada par en tu voz, no si las
pronunciaste bien: eso solo lo sabes tú escuchando los casos marcados.
"""

import argparse
import csv
import wave
from pathlib import Path

import numpy as np
import torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

ROOT = Path(__file__).resolve().parents[1]
MODEL = "facebook/wav2vec2-lv-60-espeak-cv-ft"
# id -> fonemas del "error" típico. Para los pares, el error es la otra palabra del par.
ALT_IPA = {
    "p10a": "w ɔː k ɪ d",      # walked → "walk-ed"
    "p10b": "w ɜː k ɪ d",      # worked → "work-ed"
    "p10c": "w ɑː n t",        # wanted → "want"
    "p11a": "ɛ s k uː l",      # school → "eschool"
    "p11b": "ɛ s p iː k",      # speak → "espeak"
    "p11c": "ɛ s t ʌ d i",     # study → "estudy"
}


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "dataset")
    ap.add_argument("--cache", default="C:/Models/hf")
    args = ap.parse_args()

    proc = Wav2Vec2Processor.from_pretrained(MODEL, cache_dir=args.cache)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL, cache_dir=args.cache).eval()
    tok = proc.tokenizer
    rows = {r["id"]: r for r in csv.DictReader((args.data / "manifest.csv").open(encoding="utf-8"))
            if r["kind"] == "pair"}

    def ipa_ids(ipa: str) -> list[int]:
        return tok.convert_tokens_to_ids(ipa.split())

    def candidates(pid: str) -> dict[str, str]:
        """{etiqueta: fonemas} con la palabra pretendida primero."""
        word = rows[pid]["text"]
        cands = {word: tok.phonemize(word)}
        if pid in ALT_IPA:
            cands["(" + ALT_IPA[pid].replace(" ", "") + ")"] = ALT_IPA[pid]
        else:  # par mínimo: la otra palabra del par
            other = pid[:-1] + ("b" if pid.endswith("a") else "a")
            cands[rows[other]["text"]] = tok.phonemize(rows[other]["text"])
        return cands

    print(f"{'id':5} {'quería':8} {'oye el modelo':18} {'gana':10} {'margen':>7}")
    ok = 0
    for pid, r in rows.items():
        audio = read_wav(args.data / r["file"])
        inputs = proc(audio, sampling_rate=16000, return_tensors="pt")
        with torch.no_grad():
            logp = model(inputs.input_values).logits.log_softmax(-1)[0]
        heard = proc.decode(logp.argmax(-1))
        losses = {}
        for label, ipa in candidates(pid).items():
            target = torch.tensor([ipa_ids(ipa)])
            losses[label] = torch.nn.functional.ctc_loss(
                logp[:, None, :], target, torch.tensor([logp.shape[0]]), torch.tensor([target.shape[1]]),
                blank=tok.pad_token_id, reduction="sum").item()
        best = min(losses, key=losses.get)
        intended = r["text"]
        margin = sorted(losses.values())[1] - losses[best]  # en nats; > ~2 = preferencia clara
        ok += best == intended
        flag = "" if best == intended else "  ← revisar"
        print(f"{pid:5} {intended:8} {heard:18} {best:10} {margin:7.1f}{flag}")
    print(f"\nGana la palabra pretendida en {ok}/{len(rows)} grabaciones.")


if __name__ == "__main__":
    main()
