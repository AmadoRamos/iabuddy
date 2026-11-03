"""Exporta el modelo de fonemas de S5 a ONNX para que la app no dependa de PyTorch.

    uv run --group spikes --with onnx --with onnxscript python spikes/export_wav2vec2_onnx.py

Escribe model.onnx y vocab.json en C:/Models/wav2vec2-phonemes y comprueba que ONNX da lo mismo
que PyTorch con una grabación del dataset.
"""

import json
import shutil
import time
import wave
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch
from huggingface_hub import hf_hub_download
from transformers import Wav2Vec2ForCTC

ROOT = Path(__file__).resolve().parents[1]
MODEL = "facebook/wav2vec2-lv-60-espeak-cv-ft"
CACHE = "C:/Models/hf"
OUT = Path("C:/Models/wav2vec2-phonemes")


class Logits(torch.nn.Module):
    """El exportador necesita tensores a la salida, no el objeto de transformers."""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, input_values):
        return self.model(input_values).logits


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
    return (x - x.mean()) / (x.std() + 1e-7)  # la normalización del preprocesador del modelo


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    model = Wav2Vec2ForCTC.from_pretrained(MODEL, cache_dir=CACHE, attn_implementation="eager").eval()
    audio = read_wav(ROOT / "data" / "dataset" / "e01.wav")
    x = torch.from_numpy(audio)[None]
    with torch.no_grad():
        ref = model(x).logits.numpy()

    t = time.perf_counter()
    torch.onnx.export(Logits(model).eval(), (x,), OUT / "model.onnx", input_names=["input_values"], output_names=["logits"],
                      dynamic_axes={"input_values": {0: "batch", 1: "samples"}, "logits": {0: "batch", 1: "frames"}},
                      opset_version=17, dynamo=False)
    print(f"exportado en {time.perf_counter() - t:.0f} s: {(OUT / 'model.onnx').stat().st_size / 1e9:.2f} GB")
    shutil.copy(hf_hub_download(MODEL, "vocab.json", cache_dir=CACHE), OUT / "vocab.json")

    session = ort.InferenceSession(OUT / "model.onnx", providers=["CPUExecutionProvider"])
    t = time.perf_counter()
    got = session.run(None, {"input_values": audio[None]})[0]
    took = time.perf_counter() - t
    assert got.shape == ref.shape, (got.shape, ref.shape)
    print(f"ONNX {took:.2f} s para {len(audio) / 16000:.1f} s de audio · diferencia máxima con PyTorch: "
          f"{np.abs(got - ref).max():.5f} · mismos fonemas: {(got.argmax(-1) == ref.argmax(-1)).mean():.1%}")
    print("vocabulario:", len(json.loads((OUT / "vocab.json").read_text(encoding="utf-8"))), "tokens")


if __name__ == "__main__":
    main()
