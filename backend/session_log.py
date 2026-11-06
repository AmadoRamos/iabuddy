"""Registros para analizar después qué pasó. Todo queda en data/logs (fuera de git):

- `iabuddy.log`: errores y avisos del backend, con su traza. Rota a los 5 MB.
- `sessions/<fecha>.jsonl`: una línea JSON por cada evento de una conexión: lo que manda el navegador,
  lo que recibe, y los análisis completos (también lo que la pantalla no muestra).
- `sessions/<fecha>/*.wav`: el audio de cada turno y de cada lectura. IABUDDY_LOG_AUDIO=0 lo desactiva.

Al arrancar se borran el .jsonl y los WAV de las sesiones de más de 30 días ya analizadas.

Un fallo al escribir nunca debe cortar la conversación: se avisa una vez y se sigue.
"""

import json
import logging
import logging.handlers
import shutil
import time
import wave
from datetime import datetime
from pathlib import Path

log = logging.getLogger("iabuddy")


def setup_file_logging(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(directory / "iabuddy.log", maxBytes=5_000_000, backupCount=3,
                                                   encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.setLevel(logging.INFO)
    # uvicorn no propaga a la raíz; asyncio avisa ahí de las tareas que fallaron sin que nadie las espere
    for name in ("iabuddy", "uvicorn", "uvicorn.access", "asyncio"):
        logging.getLogger(name).addHandler(handler)


class NoLog:
    def event(self, kind: str, data: dict | None = None) -> None:
        pass

    def audio(self, label: str, pcm: bytes, **meta) -> None:
        pass


class SessionLog(NoLog):
    """El registro de una conexión."""

    def __init__(self, directory: Path, save_audio: bool = True):
        stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S_%f")
        self.audio_dir = directory / stamp
        self.path = directory / f"{stamp}.jsonl"
        self.save_audio, self.count, self.failed = save_audio, 0, False
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self.file = self.path.open("a", encoding="utf-8", buffering=1)
        except OSError:
            log.exception("No se pudo crear el registro de sesión")
            self.file, self.failed = None, True

    def event(self, kind: str, data: dict | None = None) -> None:
        if not self.file:
            return
        line = {"t": datetime.now().isoformat(timespec="milliseconds"), "mono": round(time.perf_counter(), 3),
                "kind": kind, **({"data": data} if data is not None else {})}
        try:
            self.file.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
        except OSError:
            self._failed()

    def audio(self, label: str, pcm: bytes, **meta) -> None:
        self.count += 1
        name = f"{self.count:04d}_{label}.wav"
        info = {"label": label, "seconds": round(len(pcm) / 32000, 2), **meta}
        if self.save_audio:
            try:
                self.audio_dir.mkdir(parents=True, exist_ok=True)
                with wave.open(str(self.audio_dir / name), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(16000)
                    w.writeframes(pcm)
                info["file"] = f"{self.audio_dir.name}/{name}"
            except (OSError, wave.Error):
                self._failed()
        self.event("audio", info)

    def _failed(self) -> None:
        if not self.failed:
            self.failed = True
            log.exception("No se pudo escribir en el registro de sesión")

    def close(self) -> None:
        if self.file:
            self.file.close()
            self.file = None


def analyzed(path: Path) -> bool:
    """Cada turno oído tiene su tutor y su pronunciación, y cada lectura su nota. Un turno reabierto sale dos veces."""
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    data = {kind: [r["data"] for r in rows if r["kind"] == kind] for kind in ("out", "audio", "tutor", "pronunciation_analysis")}
    turns = {m["turn"] for m in data["out"] if m["type"] == "user_text"}
    readings = sum(a["label"] in ("drill", "recall") for a in data["audio"])
    grades = sum(m["type"] in ("drill_result", "recall_result") for m in data["out"])
    return (turns <= {e["turn"] for e in data["tutor"]} and turns <= {e["turn"] for e in data["pronunciation_analysis"]}
            and readings <= grades)


def prune_sessions(directory: Path, days: int = 30) -> None:
    """Borra el .jsonl y los WAV de las sesiones viejas ya analizadas. No toca la base de datos: de ella leen
    Progreso, Repaso y Palabras. Lo que no se pudo analizar se queda, y limpiar nunca impide arrancar."""
    cutoff = time.time() - days * 86400
    for path in directory.glob("*.jsonl"):
        try:
            if path.stat().st_mtime < cutoff and analyzed(path):
                audio = path.with_suffix("")
                if audio.exists():
                    shutil.rmtree(audio)
                path.unlink()  # al final: si falló el audio, se reintenta en el próximo arranque
        except Exception:
            log.exception("No se pudo limpiar %s", path.name)
