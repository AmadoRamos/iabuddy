"""Pronunciación (Fase 4): compara tu audio con los fonemas esperados de la frase (S5).

1. eSpeak da los fonemas `en-us` de cada palabra del texto.
2. wav2vec2 (ONNX, CPU) da la probabilidad de cada fonema en cada momento del audio.
3. Alineación forzada (CTC, Viterbi): dónde está cada fonema y cuánta confianza tiene → nota por palabra.
4. Para los errores típicos de un hispanohablante (`rules.py`), se compara la versión correcta de la
   palabra con la versión con ese error. Solo se marca si el error gana con margen claro: un modelo no
   es un profesor, y en margen pequeño es ambiguo (S5).
"""

import json
import re
import threading
from functools import lru_cache
from pathlib import Path

import numpy as np

from .rules import is_function_word, pronunciations, variants

RATE = 16000
MIN_MARGIN = 3.0  # en nats: el error debe explicar el audio claramente mejor que lo correcto (calibrado, S5)
# Sin errores típicos no basta: leer otra frase tampoco los tiene (nota ~7). Tu voz diciendo bien una frase da 40-70
MIN_CLEAR = 25
# Una frase por debajo seguramente no es lo que dijiste (Whisper transcribió otra cosa). Con el texto correcto tus
# frases dan 17 o más; con el equivocado casi siempre menos de 15, y hasta 8 avisos falsos. En palabras sueltas no
# vale: chair puede dar 0 y ser un error real
MIN_MATCH = 15
MIN_MATCH_WORDS = 4
MIN_WORD = 10  # una palabra con contenido por debajo no se oyó bien, aunque la frase saque buena nota (calibrado)
PAD_FRAMES = 5  # ~100 ms alrededor de cada palabra: ahí cae una «e-» añadida o un final alargado
WORD = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")


def trust(result: dict) -> dict:
    """Si el texto no parece ser lo que sonó, sus avisos no valen: mejor callar que acusar sin base."""
    if len(result["words"]) >= MIN_MATCH_WORDS and result["score"] < MIN_MATCH:
        result["mismatch"] = True
        for w in result["words"]:
            w["issues"], w["unclear"] = [], False
    return result


def align(logp: np.ndarray, tokens: list[int], blank: int) -> tuple[float, list[int]]:
    """Mejor camino CTC de `tokens` por `logp` (frames × vocabulario) → (log-prob., frame inicial de cada token)."""
    frames, n = len(logp), len(tokens)
    if frames < n or not n:
        return -np.inf, []
    ids = np.array(tokens)
    best = np.full(n + 1, -np.inf)
    best[0] = 0.0
    moved = np.zeros((frames, n + 1), dtype=bool)
    stay, move = np.empty(n + 1), np.empty(n + 1)
    move[0] = -np.inf
    for t, row in enumerate(logp):
        emit = row[ids]
        stay[0] = best[0] + row[blank]
        stay[1:] = best[1:] + np.maximum(row[blank], emit)  # silencio, o el mismo fonema que sigue sonando
        move[1:] = best[:-1] + emit
        moved[t] = move > stay
        best = np.maximum(stay, move)
    starts, j = [0] * n, n
    for t in range(frames - 1, -1, -1):
        if j and moved[t, j]:
            j -= 1
            starts[j] = t
    return float(best[n]), starts


class Phonemes:
    """Texto → fonemas del vocabulario del modelo. Tiene su propia copia de eSpeak: no choca con Kokoro."""

    def __init__(self, vocab: dict[str, int]):
        import espeakng_loader
        from phonemizer.backend import EspeakBackend
        from phonemizer.backend.espeak.wrapper import EspeakWrapper
        from phonemizer.separator import Separator

        EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
        EspeakWrapper.set_library(espeakng_loader.get_library_path())
        self.vocab = vocab
        self.backend = EspeakBackend("en-us", language_switch="remove-flags", with_stress=False)
        self.separator = Separator(phone=" ", word=" | ", syllable="")
        self.lock = threading.Lock()  # eSpeak no admite dos llamadas a la vez
        self.sentence = lru_cache(maxsize=4096)(self._sentence)

    def _groups(self, text: str) -> list[tuple[str, ...]]:
        with self.lock:
            raw = self.backend.phonemize([text.replace("’", "'")], separator=self.separator, strip=True)[0]
        return [tuple(p for p in g.split() if p in self.vocab) for g in raw.split(" | ")]

    def _sentence(self, text: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """(palabra, fonemas). La frase entera, no palabra por palabra: en contexto eSpeak acierta
        I live /lɪv/ y las formas reducidas (to → /tə/). Un número puede ser varias palabras (2019)."""
        words = WORD.findall(text)
        spans = [len(self._groups(w)) for w in words]  # cuántos grupos da cada palabra por sí sola
        groups = self._groups(text)
        if sum(spans) != len(groups):  # no se pueden repartir: palabra por palabra es peor, pero seguro
            out = [(w, tuple(p for g in self._groups(w) for p in g)) for w in words]
        else:
            out, i = [], 0
            for w, n in zip(words, spans, strict=True):
                out.append((w, tuple(p for g in groups[i:i + n] for p in g)))
                i += n
        return tuple((w, p) for w, p in out if p)


class Scorer:
    def __init__(self, model_dir: Path, threads: int = 4):
        import onnxruntime as ort

        self.vocab: dict[str, int] = json.loads((model_dir / "vocab.json").read_text(encoding="utf-8"))
        self.blank = self.vocab["<pad>"]
        self.phonemes = Phonemes(self.vocab)
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads  # sin todos los núcleos: Kokoro también corre en CPU
        self.session = ort.InferenceSession(model_dir / "model.onnx", options, providers=["CPUExecutionProvider"])
        self.lock = threading.Lock()  # un análisis a la vez

    def log_probs(self, pcm: bytes) -> np.ndarray:
        """PCM int16 a 16 kHz → log-probabilidades (frames × vocabulario, ~50 frames/s)."""
        x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        x = (x - x.mean()) / (x.std() + 1e-7)  # la normalización del preprocesador del modelo
        logits = self.session.run(None, {"input_values": x[None]})[0][0]
        logits -= logits.max(-1, keepdims=True)
        return logits - np.log(np.exp(logits).sum(-1, keepdims=True))

    def _ids(self, phones) -> list[int]:
        return [self.vocab[p] for p in phones]

    def analyze(self, pcm: bytes, text: str) -> dict:
        """Bloquea: llamar con asyncio.to_thread. → {"score", "words": [{word, score, phones, issues}]}."""
        words = self.phonemes.sentence(text)
        with self.lock:
            logp = self.log_probs(pcm)
        flat = [p for _, phones in words for p in phones]
        _, starts = align(logp, self._ids(flat), self.blank)
        if not starts:  # audio demasiado corto para esta frase
            return {"score": 0, "words": [{"word": w, "score": 0, "phones": list(p), "unclear": True, "issues": []}
                                          for w, p in words]}
        ends = [*starts[1:], len(logp)]
        out, i = [], 0
        for word, phones in words:
            j = i + len(phones)
            base = max(0, starts[i] - PAD_FRAMES)
            segment = logp[base:ends[j - 1] + PAD_FRAMES]
            spans = list(zip(starts[i:j], ends[i:j], strict=True))
            options = pronunciations(word, phones)
            if len(options) > 1:  # se escribe igual y suena distinto: vale la que mejor encaje con el audio
                aligned = [(align(segment, self._ids(o), self.blank), o) for o in options if all(p in self.vocab for p in o)]
                (_, seg_starts), phones = max(aligned, key=lambda a: a[0][0])
                spans = [(base + s, base + e) for s, e in zip(seg_starts, [*seg_starts[1:], len(segment)], strict=True)]
            confidence = [float(np.exp(logp[s:e, self.vocab[p]].max())) for p, (s, e) in zip(phones, spans, strict=True)]
            score = round(100 * sum(confidence) / len(confidence))
            out.append({"word": word, "score": score, "phones": list(phones),
                        "unclear": score < MIN_WORD and not is_function_word(word),
                        "issues": self._issues(word, phones, segment)})
            i = j
        # La nota no cuenta las palabras funcionales: se reducen tanto que su confianza no dice nada
        content = [w["score"] for w in out if not is_function_word(w["word"])] or [w["score"] for w in out]
        return trust({"score": round(sum(content) / len(content)) if content else 0, "words": out})

    def _issues(self, word: str, phones: tuple[str, ...], segment: np.ndarray) -> list[dict]:
        """Errores típicos que explican el audio claramente mejor que la pronunciación correcta."""
        correct, _ = align(segment, self._ids(phones), self.blank)
        best: dict[str, dict] = {}  # como mucho uno por sonido: el de más margen
        for v in variants(word, phones):
            score, _ = align(segment, self._ids(v["phones"]), self.blank)
            margin = score - correct
            if margin >= MIN_MARGIN and margin > best.get(v["phone"], {}).get("margin", 0):
                best[v["phone"]] = {"phone": v["phone"], "heard": v["heard"], "tip": v["tip"],
                                    "margin": round(margin, 1)}
        return sorted(best.values(), key=lambda b: -b["margin"])
