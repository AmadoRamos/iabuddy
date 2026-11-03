"""Persistencia en SQLite (stdlib): sesiones, turnos, correcciones y temas sugeridos.

Los temas viven en la tabla `topics`: para añadir, editar u ocultar uno, cambia la fila
(`active = 0` lo oculta). La primera vez se siembran los de SEED_TOPICS.
"""

import sqlite3
import time
from collections import Counter
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,          -- en español, para la UI
    opener TEXT NOT NULL,         -- pregunta en inglés con la que Buddy abre el tema
    active INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id),
    started_at REAL NOT NULL,
    ended_at REAL
);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    speaker TEXT NOT NULL CHECK (speaker IN ('user', 'buddy')),
    text TEXT NOT NULL,
    corrected TEXT,               -- versión corregida del tutor (solo turnos del usuario)
    seconds REAL,                 -- duración de tu audio, para palabras por minuto
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY,
    turn_id INTEGER NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    type TEXT NOT NULL,           -- grammar | vocabulary | naturalness
    original TEXT NOT NULL,
    fix TEXT NOT NULL,
    explanation TEXT NOT NULL,    -- en español
    severity INTEGER NOT NULL
);
"""

SEED_TOPICS = [
    ("Tu fin de semana", "What did you do last weekend?"),
    ("Trabajo y proyectos", "What are you working on these days?"),
    ("Viajes", "What's the best trip you've ever taken?"),
    ("Comida", "What's your favorite food to cook or eat?"),
    ("Series y libros", "Have you watched or read anything good lately?"),
    ("Tecnología", "What piece of tech could you not live without?"),
    ("Planes y metas", "What's something you want to achieve this year?"),
    ("Tu ciudad", "What do you like most about the city where you live?"),
]


class Store:
    def __init__(self, path: Path | str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        if not self.db.execute("SELECT 1 FROM topics LIMIT 1").fetchone():
            self.db.executemany("INSERT INTO topics (title, opener, position) VALUES (?, ?, ?)",
                                [(t, o, i) for i, (t, o) in enumerate(SEED_TOPICS)])
        self.db.commit()

    def _write(self, sql: str, args: tuple = ()) -> int:
        cur = self.db.execute(sql, args)
        self.db.commit()
        return cur.lastrowid

    # ── Temas ──
    def topics(self) -> list[dict]:
        rows = self.db.execute("SELECT id, title, opener FROM topics WHERE active ORDER BY position, id")
        return [dict(r) for r in rows]

    def topic(self, topic_id: int | None) -> dict | None:
        row = self.db.execute("SELECT id, title, opener FROM topics WHERE id = ?", (topic_id,)).fetchone()
        return dict(row) if row else None

    # ── Sesiones y turnos ──
    def start_session(self, topic_id: int | None) -> int:
        return self._write("INSERT INTO sessions (topic_id, started_at) VALUES (?, ?)", (topic_id, time.time()))

    def add_turn(self, session_id: int, speaker: str, text: str, seconds: float | None = None) -> int:
        return self._write("INSERT INTO turns (session_id, speaker, text, seconds, created_at) VALUES (?, ?, ?, ?, ?)",
                           (session_id, speaker, text, seconds, time.time()))

    def delete_turn(self, turn_id: int) -> None:
        self._write("DELETE FROM turns WHERE id = ?", (turn_id,))

    def add_feedback(self, turn_id: int, corrected: str, issues: list[dict]) -> None:
        self.db.execute("UPDATE turns SET corrected = ? WHERE id = ?", (corrected, turn_id))
        self.db.executemany(
            "INSERT INTO corrections (turn_id, type, original, fix, explanation, severity) VALUES (?, ?, ?, ?, ?, ?)",
            [(turn_id, i["type"], i["original"], i["fix"], i["explanation_es"], i["severity"]) for i in issues])
        self.db.commit()

    def finish_session(self, session_id: int) -> dict:
        """Cierra la sesión y devuelve su resumen."""
        now = time.time()
        self._write("UPDATE sessions SET ended_at = ? WHERE id = ?", (now, session_id))
        started = self.db.execute("SELECT started_at FROM sessions WHERE id = ?", (session_id,)).fetchone()[0]
        turns = self.db.execute(
            "SELECT id, text, corrected, seconds FROM turns WHERE session_id = ? AND speaker = 'user' ORDER BY id",
            (session_id,)).fetchall()
        fixes = self.db.execute(
            "SELECT c.turn_id, c.type, c.original, c.fix, c.explanation FROM corrections c "
            "JOIN turns t ON t.id = c.turn_id WHERE t.session_id = ? ORDER BY c.id", (session_id,)).fetchall()

        words = sum(len(t["text"].split()) for t in turns)
        speaking = sum(t["seconds"] or 0 for t in turns)
        with_errors = {f["turn_id"] for f in fixes}
        # Recurrente = el mismo arreglo (sin distinguir mayúsculas) dos veces o más
        counts = Counter((f["type"], f["original"].lower(), f["fix"].lower()) for f in fixes)
        first = {(f["type"], f["original"].lower(), f["fix"].lower()): f for f in reversed(fixes)}
        recurring = [{"type": k[0], "original": first[k]["original"], "fix": first[k]["fix"],
                      "explanation": first[k]["explanation"], "count": n}
                     for k, n in counts.most_common(3) if n >= 2]
        return {
            "duration_s": round(now - started),
            "turns": len(turns),
            "words": words,
            "speaking_s": round(speaking),
            "wpm": round(words / (speaking / 60)) if speaking >= 1 else 0,
            "clean_turns": len(turns) - len(with_errors),
            "by_type": dict(Counter(f["type"] for f in fixes)),
            "recurring": recurring,
            "review": [{"text": t["text"], "corrected": t["corrected"]} for t in turns
                       if t["id"] in with_errors and t["corrected"]],
        }
