"""Persistencia en SQLite (stdlib): sesiones, turnos, correcciones, temas y mensajes de inicio.

Configurable editando la base de datos (data/iabuddy.db):
- `topics`: temas sugeridos. `active = 0` oculta uno; `position` los ordena.
- `openers`: primer mensaje de Buddy. Varios por tema (`topic_id`) y para la conversación libre
  (`topic_id` NULL). Se elige uno al azar sin repetir el de la última sesión de ese tema.
La primera vez se siembran SEED_TOPICS y SEED_FREE_OPENERS; los temas de topics.yaml se añaden
en cada arranque si su título no existe.
"""

import json
import random
import sqlite3
import time
from collections import Counter
from datetime import date, datetime, timedelta
from itertools import groupby
from pathlib import Path

import yaml

from ..vocabulary.words import find_use

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
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL           -- en JSON
);
CREATE TABLE IF NOT EXISTS reviews (
    key TEXT PRIMARY KEY,         -- la frase correcta, en minúsculas
    box INTEGER NOT NULL DEFAULT 0,  -- caja de Leitner: cuanto más alta, más tarda en volver
    due REAL NOT NULL,
    hidden INTEGER NOT NULL DEFAULT 0  -- descartada: «Esto no lo dije» (fallo de Whisper) o quitada del banco
);
CREATE TABLE IF NOT EXISTS words (
    key TEXT PRIMARY KEY,         -- la palabra, en minúsculas
    term TEXT NOT NULL,
    meaning TEXT NOT NULL,        -- en español
    example TEXT NOT NULL,        -- en inglés
    forms TEXT NOT NULL DEFAULT '[]',  -- JSON: formas irregulares, para detectarla al hablar
    source TEXT NOT NULL,         -- pack (paquete de la misión) | buddy (la guardaste del chat)
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS guided_results (
    id INTEGER PRIMARY KEY,
    scenario TEXT NOT NULL,       -- id del escenario
    grade INTEGER NOT NULL,       -- 0-100, la media de sus frases
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

def goal_stars(done: int, total: int) -> int:
    """1–3 estrellas de un escenario: terminarlo / la mitad de los objetivos / todos (DISENO §7.5)."""
    return 3 if done == total else 2 if done * 2 >= total else 1


REVIEW_DAYS = (1, 3, 7, 21, 60)  # cuándo vuelve una frase que sabías, según su caja
REVIEW_AGAIN_S = 600  # la que no sabías vuelve enseguida
MISSION_SIZE = 4  # palabras por sesión
MISSION_FROM_BANK = 2  # el resto son nuevas del paquete del tema, para no quedarse siempre en lo mismo
OWN_SENTENCE_ROUND = 5  # palabras por tanda de «Tu propia frase» y de «Buddy adivina»
GAME_TERM_WORDS = 3  # más larga, describirla y adivinarla deja de ser un juego
MISSION_TERM_WORDS = 4  # más larga ya es una frase: no se puede meter de forma natural en la conversación

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
        if "hidden" not in cols("reviews"):
            self.db.execute("ALTER TABLE reviews ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
        if "opener" in cols("topics"):  # un solo inicio por tema → tabla openers
            self.db.execute("ALTER TABLE topics DROP COLUMN opener")

    def _write(self, sql: str, args: tuple = ()) -> int:
        cur = self.db.execute(sql, args)
        self.db.commit()
        return cur.lastrowid

    # ── Temas ──
    def settings(self) -> dict:
        """Solo lo que cambiaste en Ajustes; lo demás usa los valores por defecto de config.py."""
        return {r["key"]: json.loads(r["value"]) for r in self.db.execute("SELECT key, value FROM settings")}

    def save_settings(self, values: dict) -> None:
        self.db.executemany("INSERT INTO settings (key, value) VALUES (?, ?) "
                            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                            [(k, json.dumps(v)) for k, v in values.items()])
        self.db.commit()

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

    def scenario_stars(self) -> dict[str, int]:
        """Tu mejor resultado en cada escenario. Una sesión en la que no hablaste no cuenta."""
        best: dict[str, int] = {}
        for r in self.db.execute("SELECT scenario, goals_met, goals_total FROM sessions s WHERE scenario IS NOT NULL "
                                 "AND goals_total IS NOT NULL AND EXISTS (SELECT 1 FROM turns t "
                                 "WHERE t.session_id = s.id AND t.speaker = 'user')"):
            best[r["scenario"]] = max(best.get(r["scenario"], 0), goal_stars(r["goals_met"], r["goals_total"]))
        return best

    def add_guided_result(self, scenario: str, grade: int) -> None:
        self._write("INSERT INTO guided_results (scenario, grade, created_at) VALUES (?, ?, ?)",
                    (scenario, grade, time.time()))

    def guided_best(self) -> dict[str, int]:
        """Tu mejor nota en la conversación guiada de cada escenario."""
        return dict(self.db.execute("SELECT scenario, max(grade) FROM guided_results GROUP BY scenario").fetchall())

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

    def sound_counts(self) -> dict[str, int]:
        """Cuántas veces se oyó cada error de sonido, en conversación y en práctica."""
        return dict(self.db.execute("SELECT phone, count(*) FROM sound_issues GROUP BY phone").fetchall())

    def failed_phrases(self, limit: int = 10) -> list[dict]:
        """Tus frases con sonidos pendientes, ya corregidas si el tutor las corrigió, para repetirlas."""
        rows = self.db.execute(
            "SELECT coalesce(t.corrected, s.text) AS phrase, group_concat(DISTINCT lower(s.word)) AS words "
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
            "SELECT phone, heard, tip, count(*) AS count, group_concat(DISTINCT lower(word)) AS words FROM sound_issues "
            "WHERE session_id = ? GROUP BY phone, heard ORDER BY count DESC LIMIT 5", (session_id,)).fetchall()
        return [{**dict(r), "words": r["words"].split(",")} for r in rows]

    # ── Progreso ──
    def progress(self, days: int = 14) -> dict:
        """Historial y métricas, calculados de lo guardado. Una sesión sin turnos tuyos no cuenta."""
        rows = self.db.execute(
            "SELECT s.id, s.started_at, s.scenario, s.goals_met, s.goals_total, tp.title AS topic, t.text, t.seconds, "
            "(SELECT count(*) FROM corrections c WHERE c.turn_id = t.id) AS errors FROM sessions s "
            "JOIN turns t ON t.session_id = s.id AND t.speaker = 'user' "
            "LEFT JOIN topics tp ON tp.id = s.topic_id ORDER BY s.id, t.id").fetchall()
        sessions = []
        for _, group in groupby(rows, key=lambda r: r["id"]):
            turns = list(group)
            first = turns[0]
            words = sum(len(t["text"].split()) for t in turns)
            speaking = sum(t["seconds"] or 0 for t in turns)
            sessions.append({
                "id": first["id"], "date": datetime.fromtimestamp(first["started_at"]).isoformat(timespec="minutes"),
                "topic": first["topic"], "scenario": first["scenario"], "goals_met": first["goals_met"],
                "goals_total": first["goals_total"], "turns": len(turns), "words": words,
                "minutes": round(speaking / 60, 1), "wpm": round(words / (speaking / 60)) if speaking >= 1 else 0,
                "errors": sum(t["errors"] for t in turns),
                "clean_pct": round(100 * sum(not t["errors"] for t in turns) / len(turns)),
            })
        today = date.today()
        minutes = Counter()
        for s in sessions:
            minutes[s["date"][:10]] += s["minutes"]
        return {
            "totals": {"sessions": len(sessions), "minutes": round(sum(s["minutes"] for s in sessions), 1),
                       "turns": sum(s["turns"] for s in sessions), "words": sum(s["words"] for s in sessions)},
            "days": [{"date": d, "minutes": round(minutes[d], 1)} for d in
                     ((today - timedelta(days=n)).isoformat() for n in range(days - 1, -1, -1))],
            "minutes_by_day": {d: round(m, 1) for d, m in minutes.items()},  # toda la historia, para el calendario
            "sessions": sessions[::-1][:50],
            "recurring": self._recurring_errors(),
            "sounds": self._recurring_sounds(),
            "review_due": len(self.review_items(limit=None)),
        }

    def _recurring_errors(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT c.type, min(c.original) AS original, min(c.fix) AS fix, min(c.explanation) AS explanation, "
            "count(*) AS count, count(DISTINCT t.session_id) AS sessions, max(t.created_at) AS last "
            "FROM corrections c JOIN turns t ON t.id = c.turn_id WHERE trim(c.original) <> '' "
            "GROUP BY c.type, lower(trim(c.original)), lower(trim(c.fix)) HAVING count(*) >= 2 "
            "ORDER BY count(*) DESC, last DESC LIMIT 10").fetchall()
        return [dict(r) for r in rows]

    def _recurring_sounds(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT phone, heard, min(tip) AS tip, count(*) AS count, group_concat(DISTINCT lower(word)) AS words "
            "FROM sound_issues GROUP BY phone, heard ORDER BY count(*) DESC LIMIT 8").fetchall()
        return [{**dict(r), "words": r["words"].split(",")[:6]} for r in rows]

    # ── Banco de palabras y repaso (cajas de Leitner) ──
    def add_word(self, term: str, meaning: str, example: str, forms: list[str], source: str) -> str:
        """Guarda una palabra. Si la habías quitado del banco y la guardas otra vez, vuelve."""
        key = term.strip().lower()
        self.db.execute("INSERT OR IGNORE INTO words (key, term, meaning, example, forms, source, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (key, term.strip(), meaning, example, json.dumps(forms), source, time.time()))
        self.db.execute("UPDATE reviews SET hidden = 0 WHERE key = ?", (key,))
        self.db.commit()
        return key

    def _bank(self) -> dict[str, dict]:
        """Tu banco: palabras guardadas, frases que escribiste que querías decir y palabras que corrigió el tutor."""
        words = self.db.execute("SELECT key, term, meaning, example, forms FROM words "
                                "ORDER BY created_at DESC, key").fetchall()
        fixes = self.db.execute(
            "SELECT c.original, c.fix, c.explanation, t.corrected FROM corrections c JOIN turns t ON t.id = c.turn_id "
            "WHERE c.type IN ('vocabulary', 'naturalness') AND trim(c.original) <> '' AND trim(c.fix) <> '' "
            "AND t.intent IS NULL ORDER BY c.id DESC").fetchall()
        phrases = self.db.execute("SELECT text, corrected, intent FROM turns WHERE intent IS NOT NULL "
                                  "AND trim(coalesce(corrected, '')) <> '' ORDER BY id DESC").fetchall()
        items: dict[str, dict] = {}
        for r in words:
            items[r["key"]] = {"kind": "word", "term": r["term"], "meaning": r["meaning"], "said": None, "intent": None,
                               "explanation": "", "text": r["example"], "forms": json.loads(r["forms"])}
        for r in phrases:
            t = r["corrected"].rstrip(" .…")
            items.setdefault(r["corrected"].strip().lower(), {
                "kind": "phrase", "term": t, "meaning": r["intent"], "said": r["text"], "intent": r["intent"],
                "explanation": "", "text": t + ("" if t.endswith(("?", "!")) else "."), "forms": []})
        for r in fixes:
            # Se lee la frase entera si contiene la corrección y se puede leer de un tirón; si no, solo la corrección
            whole = r["corrected"] or ""
            usable = (r["fix"].lower() in whole.lower() and len(whole.split()) <= 20
                      and not whole.rstrip().endswith(("...", "…")))  # una frase a medias no se puede repetir
            items.setdefault(r["fix"].strip().lower(), {
                "kind": "fix", "term": r["fix"].strip(), "meaning": r["explanation"], "said": r["original"], "intent": None,
                "explanation": r["explanation"], "text": whole if usable else r["fix"], "forms": []})
        hidden = {r["key"] for r in self.db.execute("SELECT key FROM reviews WHERE hidden")}
        return {k: {**v, "target": find_use(v["text"], v["term"], v["forms"])}  # cómo aparece en su frase, para destacarla
                for k, v in items.items() if k not in hidden}

    def review_items(self, limit: int | None = 10, now: float | None = None) -> list[dict]:
        """Lo que toca repasar hoy: primero lo atrasado, luego lo nuevo."""
        now = time.time() if now is None else now
        due = {r["key"]: r["due"] for r in self.db.execute("SELECT key, due FROM reviews")}
        pending = [{"key": k, **v, "speakable": len(v["term"].split()) <= MISSION_TERM_WORDS}
                   for k, v in self._bank().items() if due.get(k, 0) <= now]
        pending.sort(key=lambda i: (i["key"] not in due, due.get(i["key"], 0)))
        return pending[:limit]

    def _practicable(self, bank: dict[str, dict], reviews: dict) -> list[dict]:
        """Lo del banco con lo que se puede hablar. Una corrección o frase solo entra si ya la respondiste
        en el repaso: sin eso podría ser un fallo de Whisper (*Wispit → Whisper*)."""
        return [{"key": k, **v} for k, v in bank.items() if len(v["term"].split()) <= MISSION_TERM_WORDS
                and (v["kind"] == "word" or (k in reviews and reviews[k]["box"] >= 1))]

    def own_sentence_items(self, limit: int = OWN_SENTENCE_ROUND) -> list[dict]:
        """Una tanda de «Tu propia frase», al azar. No toca las cajas: con la palabra a la vista no demuestra que la recuerdes."""
        reviews = {r["key"]: r for r in self.db.execute("SELECT key, box FROM reviews")}
        pool = self._practicable(self._bank(), reviews)
        return random.sample(pool, min(limit, len(pool)))

    def _guessable(self, bank: dict[str, dict]) -> list[dict]:
        """Lo que se puede describir: palabras con significado propio, no correcciones ni frases tuyas."""
        return [{"key": k, **v} for k, v in bank.items() if v["kind"] == "word" and len(v["term"].split()) <= GAME_TERM_WORDS]

    def game_items(self, limit: int = OWN_SENTENCE_ROUND) -> list[dict]:
        """Una partida de «Buddy adivina», al azar. Como en «Tu propia frase», las cajas no se tocan."""
        pool = self._guessable(self._bank())
        return random.sample(pool, min(limit, len(pool)))

    def bank_item(self, key: str) -> dict | None:
        return self._bank().get(key)

    def word_bank(self, now: float | None = None) -> dict:
        """Todo el banco, con cuándo vuelve cada cosa, para la sección «Palabras»."""
        now = time.time() if now is None else now
        due = {r["key"]: r["due"] for r in self.db.execute("SELECT key, due FROM reviews")}
        items = [{"key": k, **v, "due": due.get(k, 0)} for k, v in self._bank().items()]
        reviews = {r["key"]: r for r in self.db.execute("SELECT key, box FROM reviews")}
        return {"items": items, "review_due": sum(i["due"] <= now for i in items), "now": now,
                "practicable": len(self._practicable(self._bank(), reviews)), "guessable": len(self._guessable(self._bank()))}

    def discard_review(self, key: str) -> None:
        self._write("INSERT INTO reviews (key, due, hidden) VALUES (?, 0, 1) "
                    "ON CONFLICT(key) DO UPDATE SET hidden = 1", (key,))

    def pick_mission(self, pack: list[dict], now: float | None = None) -> list[dict]:
        """Las palabras de una sesión: algunas de tu banco que tocan hoy y otras nuevas del paquete.

        Si no usas una palabra no pasa nada: vuelve la próxima vez.
        """
        now = time.time() if now is None else now
        reviews = {r["key"]: r for r in self.db.execute("SELECT key, box, due FROM reviews")}
        bank = self._bank()

        def when(key: str) -> float:
            return reviews[key]["due"] if key in reviews else 0

        due = sorted((i for i in self._practicable(bank, reviews) if when(i["key"]) <= now), key=lambda i: when(i["key"]))
        # También fuera lo descartado (está en reviews) y lo repetido entre el paquete del tema y el general
        fresh = list({w["key"]: w for w in pack if w["key"] not in bank and w["key"] not in reviews}.values())
        picked = due[:MISSION_FROM_BANK]
        picked += fresh[:MISSION_SIZE - len(picked)]
        picked += due[MISSION_FROM_BANK:][:MISSION_SIZE - len(picked)]
        return [{"key": w["key"], "term": w["term"], "meaning": w["meaning"], "example": w.get("example") or w["text"],
                 "forms": w["forms"], "source": w.get("source", "bank")} for w in picked]

    def finish_mission(self, mission: list[dict], used: set[str]) -> None:
        """Hablaste en la sesión: sus palabras entran en tu banco y las que usaste cuentan como acierto."""
        for w in mission:
            if w["source"] == "pack":
                self.add_word(w["term"], w["meaning"], w["example"], w["forms"], "pack")
        for key in used:
            self.answer_review(key, True)

    def answer_review(self, key: str, known: bool, now: float | None = None) -> None:
        now = time.time() if now is None else now
        row = self.db.execute("SELECT box FROM reviews WHERE key = ?", (key,)).fetchone()
        box = (row["box"] + 1 if row else 1) if known else 0
        wait = REVIEW_DAYS[min(box, len(REVIEW_DAYS)) - 1] * 86400 if known else REVIEW_AGAIN_S
        self._write("INSERT INTO reviews (key, box, due) VALUES (?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET box = excluded.box, due = excluded.due", (key, box, now + wait))

    def review_status(self, now: float | None = None) -> dict:
        """Cuántas frases quedan por repasar hoy y cuándo vuelve la siguiente que ya respondiste."""
        now = time.time() if now is None else now
        next_due = self.db.execute("SELECT MIN(due) FROM reviews WHERE due > ?", (now,)).fetchone()[0]
        return {"pending": len(self.review_items(limit=None, now=now)), "next_due": next_due}

    def finish_session(self, session_id: int) -> dict:
        """Cierra la sesión y devuelve su resumen."""
        now = time.time()
        self._write("UPDATE sessions SET ended_at = ? WHERE id = ?", (now, session_id))
        session = self.db.execute("SELECT s.started_at, s.topic_id, t.title AS topic FROM sessions s "
                                  "LEFT JOIN topics t ON t.id = s.topic_id WHERE s.id = ?", (session_id,)).fetchone()
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
            "topic": session["topic"],
            "topic_id": session["topic_id"],
            "duration_s": round(now - session["started_at"]),
            "turns": len(turns),
            "words": words,
            "speaking_s": round(speaking),
            "wpm": round(words / (speaking / 60)) if speaking >= 1 else 0,
            "clean_turns": len(turns) - len(with_errors),
            "by_type": dict(Counter(f["type"] for f in fixes)),
            "sounds": self._session_sounds(session_id),
            "recurring": recurring,
            "review": [{"text": t["text"], "corrected": t["corrected"],
                        "wrong": [f["original"] for f in fixes if f["turn_id"] == t["id"]],
                        "fixes": [f["fix"] for f in fixes if f["turn_id"] == t["id"]]} for t in turns
                       if t["id"] in with_errors and t["corrected"] and not t["intent"]],
            # Cuaderno de frases: lo que querías decir y cómo se dice
            "phrases": [{"said": t["text"], "intent": t["intent"], "english": t["corrected"]}
                        for t in turns if t["intent"] and t["corrected"]],
        }
