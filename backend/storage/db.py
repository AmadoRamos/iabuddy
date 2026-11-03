"""Persistencia en SQLite (stdlib): sesiones, turnos, correcciones, temas y mensajes de inicio.

Configurable editando la base de datos (data/iabuddy.db):
- `topics`: temas sugeridos. `active = 0` oculta uno; `position` los ordena.
- `openers`: primer mensaje de Buddy. Varios por tema (`topic_id`) y para la conversación libre
  (`topic_id` NULL). Se elige uno al azar sin repetir el de la última sesión de ese tema.
La primera vez se siembran SEED_TOPICS y SEED_FREE_OPENERS; los temas de topics.yaml se añaden
en cada arranque si su título no existe.
"""

import random
import sqlite3
import time
from collections import Counter
from pathlib import Path

import yaml

TOPICS_FILE = Path(__file__).with_name("topics.yaml")

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,          -- en español, para la UI
    active INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS openers (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,  -- NULL = conversación libre
    text TEXT NOT NULL            -- en inglés: saludo + pregunta con la que Buddy abre
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    topic_id INTEGER REFERENCES topics(id),
    opener_id INTEGER REFERENCES openers(id),
    scenario TEXT,                -- id del escenario de roleplay (nombre del .yaml), si lo hay
    scenario_opener INTEGER,      -- índice del inicio del escenario que se usó
    goals_met INTEGER,            -- objetivos del escenario cumplidos / totales
    goals_total INTEGER,
    started_at REAL NOT NULL,
    ended_at REAL
);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY,
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    speaker TEXT NOT NULL CHECK (speaker IN ('user', 'buddy')),
    text TEXT NOT NULL,
    corrected TEXT,               -- versión corregida del tutor (solo turnos del usuario)
    intent TEXT,                  -- lo que el usuario escribió que quería decir (español o inglés)
    seconds REAL,                 -- duración de tu audio, para palabras por minuto
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS sound_issues (
    id INTEGER PRIMARY KEY,
    session_id INTEGER REFERENCES sessions(id),  -- NULL = práctica de pronunciación
    turn_id INTEGER REFERENCES turns(id) ON DELETE CASCADE,
    text TEXT NOT NULL,           -- la frase que se analizó
    word TEXT NOT NULL,
    phone TEXT NOT NULL,          -- el sonido correcto
    heard TEXT NOT NULL,          -- lo que sonó en su lugar
    tip TEXT NOT NULL,            -- en español
    margin REAL NOT NULL,
    resolved INTEGER NOT NULL DEFAULT 0,  -- ya la dijiste bien en la práctica
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
    ("Tu fin de semana", [
        "Hey! Good to see you. What did you do last weekend?",
        "Hi there! So, how was your weekend? Anything fun?",
        "Hey! I always love hearing about weekends. Did you rest, or were you busy?",
        "Welcome back! If you could describe your last weekend in three words, what would they be?",
    ]),
    ("Trabajo y proyectos", [
        "Hey! Good to see you. What are you working on these days?",
        "Hi! How's work going lately? Anything interesting happening?",
        "Hey there! Tell me about a project you're excited about right now.",
        "Welcome back! What was the most challenging part of your work this week?",
    ]),
    ("Viajes", [
        "Hey! Good to see you. What's the best trip you've ever taken?",
        "Hi there! If you could travel anywhere next month, where would you go?",
        "Hey! Do you prefer beach trips, city trips or nature trips? Why?",
        "Welcome back! Tell me about a place you visited that surprised you.",
    ]),
    ("Comida", [
        "Hey! Good to see you. What's your favorite food to cook or eat?",
        "Hi there! What did you have for lunch today? Was it good?",
        "Hey! Is there a typical dish from your country that everyone should try?",
        "Welcome back! Do you like cooking, or do you prefer eating out?",
    ]),
    ("Series y libros", [
        "Hey! Good to see you. Have you watched or read anything good lately?",
        "Hi there! What's a series or book you'd recommend to a friend?",
        "Hey! Do you prefer reading books or watching series? Why?",
        "Welcome back! Tell me about a story that stayed in your head for a long time.",
    ]),
    ("Tecnología", [
        "Hey! Good to see you. What piece of tech could you not live without?",
        "Hi there! What app do you use the most every day?",
        "Hey! What do you think about AI tools? Do you use any of them?",
        "Welcome back! Is there a gadget you'd really like to buy this year?",
    ]),
    ("Planes y metas", [
        "Hey! Good to see you. What's something you want to achieve this year?",
        "Hi there! Do you have any plans for the next few months?",
        "Hey! Why are you learning English? What's your big goal?",
        "Welcome back! What's a new habit you'd like to start?",
    ]),
    ("Tu ciudad", [
        "Hey! Good to see you. What do you like most about the city where you live?",
        "Hi there! If I visited your city, where should I go first?",
        "Hey! What's the weather like in your city these days?",
        "Welcome back! Is there anything you would change about your neighborhood?",
    ]),
]
SEED_FREE_OPENERS = [
    "Hey! Good to see you. How has your day been so far?",
    "Hi there! What's new with you today?",
    "Hey! How are you feeling today? Anything interesting happen?",
    "Welcome back! What have you been up to since we last talked?",
]


class Store:
    def __init__(self, path: Path | str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)
        self._migrate()
        if not self.db.execute("SELECT 1 FROM topics LIMIT 1").fetchone():
            self.db.executemany("INSERT INTO topics (title, position) VALUES (?, ?)",
                                [(t, i) for i, (t, _) in enumerate(SEED_TOPICS)])
        if not self.db.execute("SELECT 1 FROM openers LIMIT 1").fetchone():
            ids = {r["title"]: r["id"] for r in self.db.execute("SELECT id, title FROM topics")}
            rows = [(ids[t], o) for t, ops in SEED_TOPICS if t in ids for o in ops]
            rows += [(None, o) for o in SEED_FREE_OPENERS]
            self.db.executemany("INSERT INTO openers (topic_id, text) VALUES (?, ?)", rows)
        self._add_file_topics()
        self.db.commit()

    def _add_file_topics(self) -> None:
        """Temas de topics.yaml cuyo título aún no está en la base (también en bases ya creadas)."""
        known = {r["title"] for r in self.db.execute("SELECT title FROM topics")}
        pos = self.db.execute("SELECT coalesce(max(position), -1) FROM topics").fetchone()[0]
        for title, ops in (yaml.safe_load(TOPICS_FILE.read_text(encoding="utf-8")) or {}).items():
            if title in known:
                continue
            pos += 1
            tid = self.db.execute("INSERT INTO topics (title, position) VALUES (?, ?)", (title, pos)).lastrowid
            self.db.executemany("INSERT INTO openers (topic_id, text) VALUES (?, ?)", [(tid, o) for o in ops])

    def _migrate(self) -> None:
        """Bases creadas con versiones anteriores del esquema."""
        def cols(table: str) -> set[str]:
            return {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}
        if "intent" not in cols("turns"):
            self.db.execute("ALTER TABLE turns ADD COLUMN intent TEXT")
        sessions = cols("sessions")
        if "opener_id" not in sessions:
            self.db.execute("ALTER TABLE sessions ADD COLUMN opener_id INTEGER REFERENCES openers(id)")
        for col, kind in (("scenario", "TEXT"), ("scenario_opener", "INTEGER"), ("goals_met", "INTEGER"),
                          ("goals_total", "INTEGER")):
            if col not in sessions:
                self.db.execute(f"ALTER TABLE sessions ADD COLUMN {col} {kind}")
        if "opener" in cols("topics"):  # un solo inicio por tema → tabla openers
            self.db.execute("ALTER TABLE topics DROP COLUMN opener")

    def _write(self, sql: str, args: tuple = ()) -> int:
        cur = self.db.execute(sql, args)
        self.db.commit()
        return cur.lastrowid

    # ── Temas ──
    def topics(self) -> list[dict]:
        rows = self.db.execute("SELECT id, title FROM topics WHERE active ORDER BY position, id")
        return [dict(r) for r in rows]

    def topic(self, topic_id: int | None) -> dict | None:
        row = self.db.execute("SELECT id, title FROM topics WHERE id = ?", (topic_id,)).fetchone()
        return dict(row) if row else None

    def pick_opener(self, topic_id: int | None) -> dict | None:
        """Un inicio al azar del tema (NULL = libre), sin repetir el de la última sesión de ese tema."""
        rows = self.db.execute("SELECT id, text FROM openers WHERE topic_id IS ?", (topic_id,)).fetchall()
        last = self.db.execute("SELECT opener_id FROM sessions WHERE topic_id IS ? AND opener_id IS NOT NULL "
                               "ORDER BY id DESC LIMIT 1", (topic_id,)).fetchone()
        fresh = [r for r in rows if not last or r["id"] != last[0]] or rows
        return dict(random.choice(fresh)) if fresh else None

    def pick_scenario_opener(self, scenario: str, count: int) -> int:
        """Índice de uno de los `count` inicios del escenario, sin repetir el de su última sesión."""
        last = self.db.execute("SELECT scenario_opener FROM sessions WHERE scenario = ? "
                               "ORDER BY id DESC LIMIT 1", (scenario,)).fetchone()
        return random.choice([i for i in range(count) if not last or i != last[0]] or [0])

    # ── Sesiones y turnos ──
    def start_session(self, topic_id: int | None, opener_id: int | None = None,
                      scenario: str | None = None, scenario_opener: int | None = None) -> int:
        return self._write("INSERT INTO sessions (topic_id, opener_id, scenario, scenario_opener, started_at) "
                           "VALUES (?, ?, ?, ?, ?)", (topic_id, opener_id, scenario, scenario_opener, time.time()))

    def set_goals(self, session_id: int, met: int, total: int) -> None:
        self._write("UPDATE sessions SET goals_met = ?, goals_total = ? WHERE id = ?", (met, total, session_id))

    def add_turn(self, session_id: int, speaker: str, text: str, seconds: float | None = None) -> int:
        return self._write("INSERT INTO turns (session_id, speaker, text, seconds, created_at) VALUES (?, ?, ?, ?, ?)",
                           (session_id, speaker, text, seconds, time.time()))

    def delete_turn(self, turn_id: int) -> None:
        self._write("DELETE FROM turns WHERE id = ?", (turn_id,))

    def add_feedback(self, turn_id: int, corrected: str, issues: list[dict], intent: str | None = None) -> None:
        """Guarda el análisis del turno. Si ya había uno (p. ej. antes de escribir la intención), lo sustituye."""
        self.db.execute("DELETE FROM corrections WHERE turn_id = ?", (turn_id,))
        self.db.execute("UPDATE turns SET corrected = ?, intent = coalesce(?, intent) WHERE id = ?",
                        (corrected, intent, turn_id))
        self.db.executemany(
            "INSERT INTO corrections (turn_id, type, original, fix, explanation, severity) VALUES (?, ?, ?, ?, ?, ?)",
            [(turn_id, i["type"], i["original"], i["fix"], i["explanation_es"], i["severity"]) for i in issues])
        self.db.commit()

    # ── Pronunciación ──
    def add_sound_issues(self, text: str, words: list[dict], session_id: int | None = None,
                         turn_id: int | None = None) -> None:
        self.db.executemany(
            "INSERT INTO sound_issues (session_id, turn_id, text, word, phone, heard, tip, margin, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(session_id, turn_id, text, w["word"], i["phone"], i["heard"], i["tip"], i["margin"], time.time())
             for w in words for i in w["issues"]])
        self.db.commit()

    def failed_phrases(self, limit: int = 10) -> list[dict]:
        """Tus frases con sonidos pendientes, ya corregidas si el tutor las corrigió, para repetirlas."""
        rows = self.db.execute(
            "SELECT coalesce(t.corrected, s.text) AS phrase, group_concat(DISTINCT s.word) AS words "
            "FROM sound_issues s LEFT JOIN turns t ON t.id = s.turn_id WHERE NOT s.resolved "
            "GROUP BY phrase ORDER BY max(s.id) DESC").fetchall()
        # Una frase muy larga no se puede repetir de memoria ni leyendo con calma
        return [{"text": r["phrase"], "words": r["words"].split(",")} for r in rows
                if len(r["phrase"].split()) <= 20][:limit]

    def resolve_phrase(self, phrase: str) -> None:
        self._write("UPDATE sound_issues SET resolved = 1 WHERE id IN (SELECT s.id FROM sound_issues s "
                    "LEFT JOIN turns t ON t.id = s.turn_id WHERE coalesce(t.corrected, s.text) = ?)", (phrase,))

    def _session_sounds(self, session_id: int) -> list[dict]:
        rows = self.db.execute(
            "SELECT phone, heard, tip, count(*) AS count, group_concat(DISTINCT word) AS words FROM sound_issues "
            "WHERE session_id = ? GROUP BY phone, heard ORDER BY count DESC LIMIT 5", (session_id,)).fetchall()
        return [{**dict(r), "words": r["words"].split(",")} for r in rows]

    def finish_session(self, session_id: int) -> dict:
        """Cierra la sesión y devuelve su resumen."""
        now = time.time()
        self._write("UPDATE sessions SET ended_at = ? WHERE id = ?", (now, session_id))
        started = self.db.execute("SELECT started_at FROM sessions WHERE id = ?", (session_id,)).fetchone()[0]
        turns = self.db.execute(
            "SELECT id, text, corrected, intent, seconds FROM turns WHERE session_id = ? AND speaker = 'user' ORDER BY id",
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
            "sounds": self._session_sounds(session_id),
            "recurring": recurring,
            "review": [{"text": t["text"], "corrected": t["corrected"]} for t in turns
                       if t["id"] in with_errors and t["corrected"] and not t["intent"]],
            # Cuaderno de frases: lo que querías decir y cómo se dice
            "phrases": [{"said": t["text"], "intent": t["intent"], "english": t["corrected"]}
                        for t in turns if t["intent"] and t["corrected"]],
        }
