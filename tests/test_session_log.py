"""Los registros guardan lo necesario para analizar una sesión, también lo que la pantalla no muestra."""

import asyncio
import json
import logging
import wave

import httpx
from test_feedback import FakeTutor, run_turn
from test_pronunciation import FakeScorer, drill
from test_turn_manager import make

from backend.pipeline.llm import OllamaLLM
from backend.session_log import SessionLog, setup_file_logging
from backend.storage.db import Store


def lines(log) -> list[dict]:
    log.close()
    return [json.loads(x) for x in log.path.read_text(encoding="utf-8").splitlines()]


def kinds(rows, kind):
    return [r["data"] for r in rows if r["kind"] == kind]


async def test_records_controls_events_and_full_analyses_even_in_silent_mode(tmp_path):
    s, _, _ = make()
    s.tutor, s.scorer, s.store = FakeTutor(), FakeScorer(), Store(":memory:")
    s.log = log = SessionLog(tmp_path)
    await s.on_control({"type": "hello", "feedback": "silencioso"})
    await s.task
    await run_turn(s)
    await asyncio.gather(*s.tutor_tasks)
    await s.on_control({"type": "client_error", "message": "Boom"})  # lo manda el navegador
    await s.on_control({"type": "end"})
    rows = lines(log)
    assert {"hello", "start", "stop", "client_error", "end"} <= {r["type"] for r in kinds(rows, "in")}
    out = {r["type"] for r in kinds(rows, "out")}
    assert {"user_text", "partner_text", "metrics", "summary"} <= out and "feedback" not in out
    assert kinds(rows, "tutor")[0]["corrected"] == "Yesterday I went to the gym."  # no salió por pantalla
    analysis = kinds(rows, "pronunciation_analysis")[0]
    assert analysis["text"] == "Yesterday I go to the gym." and analysis["words"][1]["score"] == 90  # palabras sin error
    assert kinds(rows, "turn_closed")[0]["reason"] == "tecla"


async def test_saves_the_audio_of_each_turn_and_drill_as_wav(tmp_path):
    s, _, _ = make()
    s.scorer, s.log = FakeScorer(issues=()), SessionLog(tmp_path)
    await drill(s, "Three days.")
    rows = lines(s.log)
    assert kinds(rows, "out")[-2]["type"] == "drill_result"  # los aciertos también quedan
    info = kinds(rows, "audio")[0]
    assert info["text"] == "Three days."
    with wave.open(str(tmp_path / info["file"])) as w:
        assert w.getframerate() == 16000 and w.getnframes() == 5  # 10 bytes de prueba


async def test_audio_can_be_turned_off(tmp_path):
    log = SessionLog(tmp_path, save_audio=False)
    log.audio("turn1", b"\0\0")
    rows = lines(log)
    assert kinds(rows, "audio")[0]["seconds"] == 0 and "file" not in kinds(rows, "audio")[0]
    assert not list(tmp_path.glob("*/*.wav"))


async def test_what_happens_after_the_tab_closes_is_recorded(tmp_path):
    s, events, _ = make()
    s.tutor, s.store, s.log = FakeTutor(), Store(":memory:"), SessionLog(tmp_path)
    await s.on_control({"type": "hello"})
    await s.task
    await run_turn(s)
    sent = len(events)
    await s.close()
    assert len(events) == sent  # ya no hay a quién enviarle nada…
    assert kinds(lines(s.log), "closed_without_end")[0]["turns"] == 1  # …pero el resumen queda


async def test_a_failing_log_never_breaks_the_conversation(tmp_path):
    (tmp_path / "taken").write_text("no soy una carpeta")
    s, events, _ = make()
    s.log = SessionLog(tmp_path / "taken")  # no se puede crear
    s.log.audio("turn1", b"\0\0")
    await run_turn(s)
    assert any(isinstance(e, dict) and e["type"] == "partner_done" for e in events)


def test_backend_errors_go_to_the_log_file(tmp_path):
    logger = logging.getLogger("iabuddy")
    before = list(logger.handlers)
    setup_file_logging(tmp_path)
    try:
        try:
            raise ValueError("fallo de prueba")
        except ValueError:
            logger.exception("Algo falló")
    finally:
        for name in ("iabuddy", "uvicorn", "uvicorn.access", "asyncio"):
            for h in [h for h in logging.getLogger(name).handlers if h not in before]:
                logging.getLogger(name).removeHandler(h)
                h.close()
    text = (tmp_path / "iabuddy.log").read_text(encoding="utf-8")
    assert "Algo falló" in text and "ValueError: fallo de prueba" in text


async def test_ollama_timings_of_each_answer_are_logged(caplog):
    def answer(_):
        lines = [{"message": {"content": "Hi"}}, {"done": True, "prompt_eval_count": 900, "prompt_eval_duration": 1_200_000_000,
                                                  "eval_count": 30, "eval_duration": 600_000_000, "load_duration": 0}]
        return httpx.Response(200, text="\n".join(json.dumps(x) for x in lines))

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        llm = OllamaLLM("http://x", "m", client)
        with caplog.at_level(logging.INFO, logger="iabuddy"):
            assert [p async for p in llm.stream([])] == ["Hi"]
    assert "prompt 900 tokens en 1200 ms" in caplog.text
