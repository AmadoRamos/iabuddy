"""Corta el texto del LLM en trozos para el TTS.

Kokoro tiene un coste fijo de ~300 ms por llamada (S3), así que el *primer* trozo debe ser
corto para que suene pronto: se corta en la primera puntuación si cae en las primeras
FIRST_PUNCT_WORDS palabras (y hay 2+). Si no, en cuanto hay FIRST_PUNCT_WORDS palabras se corta
tras FIRST_MAX_WORDS; el margen evita colas sueltas de una palabra («yesterday?»), y esperar dos
palabras más cuesta ~30 ms. El resto va frase a frase.
"""

import re

FIRST_MAX_WORDS = 6
FIRST_PUNCT_WORDS = 8
_PUNCT = re.compile(r"[,.!?;:](?=\s)")
_SENTENCE = re.compile(r"[.!?](?=\s)")
_WORD = re.compile(r"\S+\s")  # palabra completa: ya llegó el espacio que la sigue


class Chunker:
    def __init__(self) -> None:
        self.buf = ""
        self.first = True

    def feed(self, piece: str) -> list[str]:
        self.buf += piece
        out = []
        while (chunk := self._cut()) is not None:
            out.append(chunk)
        return out

    def flush(self) -> str | None:
        rest, self.buf = self.buf.strip(), ""
        return rest or None

    def _cut(self) -> str | None:
        text = self.buf.lstrip()
        if self.first:
            for m in _PUNCT.finditer(text):
                n = len(text[:m.end()].split())
                if 2 <= n <= FIRST_PUNCT_WORDS:
                    return self._take(text, m.end())
                if n > FIRST_PUNCT_WORDS:
                    break
            words = _WORD.findall(text)
            if len(words) >= FIRST_PUNCT_WORDS:
                return self._take(text, sum(map(len, words[:FIRST_MAX_WORDS])))
            return None
        m = _SENTENCE.search(text)
        return self._take(text, m.end()) if m else None

    def _take(self, text: str, end: int) -> str:
        self.buf, self.first = text[end:], False
        return text[:end].strip()
