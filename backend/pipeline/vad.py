"""Silero VAD en streaming (ONNX, CPU). Mismos parámetros que el spike S4."""

from pathlib import Path

import numpy as np
import onnxruntime as ort

SR, WIN, CTX = 16000, 512, 64  # Silero v5+: ventana de 512 muestras + 64 de contexto a 16 kHz
FRAME_MS = WIN / SR * 1000  # 32 ms
ON, OFF = 0.5, 0.35  # histéresis como en el VADIterator oficial


class StreamingVad:
    def __init__(self, model: Path):
        self.sess = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
        self.reset()

    def reset(self) -> None:
        self.state = np.zeros((2, 1, 128), np.float32)
        self.ctx = np.zeros((1, CTX), np.float32)
        self.pending = np.zeros(0, np.float32)
        self.speaking = False

    def feed(self, pcm: bytes) -> list[bool]:
        """PCM int16 a 16 kHz → un bool (¿hay voz?) por cada ventana completa de 32 ms."""
        audio = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        self.pending = np.concatenate([self.pending, audio])
        flags = []
        while len(self.pending) >= WIN:
            x = np.concatenate([self.ctx, self.pending[None, :WIN]], axis=1)
            out, self.state = self.sess.run(
                None, {"input": x, "state": self.state, "sr": np.array(SR, np.int64)})
            self.ctx = x[:, -CTX:]
            self.pending = self.pending[WIN:]
            p = float(out[0, 0])
            self.speaking = p >= ON or (self.speaking and p >= OFF)
            flags.append(self.speaking)
        return flags
