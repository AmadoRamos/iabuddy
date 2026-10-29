"""Spike S2 — LLM: latencia del compañero con y sin el tutor compitiendo por la GPU.

    # 1) Ollama con 2 peticiones en paralelo (en otra terminal; no toca el Ollama de la bandeja):
    $env:OLLAMA_HOST="127.0.0.1:11435"; $env:OLLAMA_NUM_PARALLEL="2"; ollama serve
    # 2) whisper-server con large-v3 cargado (para medir la VRAM real del stack):
    C:\\Tools\\whisper.cpp\\build\\bin\\Release\\whisper-server.exe -m C:\\Models\\whisper\\ggml-large-v3.bin -l en --port 8179
    # 3) el spike:
    uv run python spikes/s2_llm.py --models gemma4:12b-it-qat qwen3.5:9b llama3.1:8b

Por modelo mide, en streaming: tiempo a primer token (TTFT), tiempo a la primera frase
completa (lo que espera el TTS), tokens/s de generación y VRAM. Escenario "solo" = solo el
compañero; "con tutor" = el tutor (JSON con esquema) ya está generando cuando llega el
compañero. Guarda respuestas y métricas en data/s2/.
"""

import argparse
import csv
import json
import re
import statistics
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NUM_CTX = 4096

SYSTEM = (
    "You are Sam, a friendly American conversation partner. The user is a Spanish speaker "
    "practicing spoken English at B1-B2 level. Reply in 1-3 short, natural spoken sentences, "
    "then ask one follow-up question. Never explain grammar. If the user makes a mistake, "
    "simply use the correct form naturally in your reply."
)
HISTORY = [
    {"role": "assistant", "content": "Hey! Good to see you. How has your week been so far?"},
    {"role": "user", "content": "Is been very busy, I have many work in the office."},
    {"role": "assistant", "content": "Sounds like you've had a lot of work! What's keeping you so busy?"},
]
TUTOR_SYSTEM = (
    "You are an English tutor for a Spanish-speaking learner (B1-B2). Find the grammar and "
    "vocabulary errors in the learner's sentence. Only real errors, not style. Explanations "
    "in Spanish, one short sentence each."
)
TUTOR_SCHEMA = {
    "type": "object",
    "properties": {"errors": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "original": {"type": "string"},
            "correction": {"type": "string"},
            "type": {"type": "string", "enum": ["grammar", "vocabulary", "word_order", "other"]},
            "explanation_es": {"type": "string"},
        },
        "required": ["original", "correction", "type", "explanation_es"],
    }}},
    "required": ["errors"],
}
SENTENCE_END = re.compile(r"[.!?](\s|$)")


def post(url: str, payload: dict):
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=300)


def chat(host: str, model: str, messages: list, fmt: dict | None = None) -> dict:
    """Una petición /api/chat en streaming con métricas de latencia."""
    payload = {"model": model, "messages": messages, "stream": True, "think": False,
               "keep_alive": "10m", "options": {"num_ctx": NUM_CTX, "temperature": 0.7}}
    if fmt:
        payload["format"] = fmt
    t0 = time.perf_counter()
    ttft = first_sentence = None
    text = ""
    with post(f"{host}/api/chat", payload) as resp:
        for line in resp:
            obj = json.loads(line)
            if "error" in obj:
                raise RuntimeError(obj["error"])
            piece = obj.get("message", {}).get("content", "")
            if piece and ttft is None:
                ttft = time.perf_counter() - t0
            text += piece
            if first_sentence is None and SENTENCE_END.search(text):
                first_sentence = time.perf_counter() - t0
            if obj.get("done"):
                last = obj
    total = time.perf_counter() - t0
    return {"ttft_ms": round((ttft or total) * 1000), "sentence_ms": round((first_sentence or total) * 1000),
            "total_ms": round(total * 1000), "tokens": last.get("eval_count", 0),
            "tps": last.get("eval_count", 0) / max(1e-9, last.get("eval_duration", 0) / 1e9),
            "text": text.strip()}


def companion(host, model, user_text):
    msgs = [{"role": "system", "content": SYSTEM}, *HISTORY, {"role": "user", "content": user_text}]
    return chat(host, model, msgs)


def tutor(host, model, user_text):
    msgs = [{"role": "system", "content": TUTOR_SYSTEM}, {"role": "user", "content": user_text}]
    return chat(host, model, msgs, TUTOR_SCHEMA)


def gpu_dedicated_gb() -> float:
    """VRAM dedicada en uso en todo el sistema (contador de Windows), en GB."""
    cmd = ("(Get-Counter '\\GPU Adapter Memory(*)\\Dedicated Usage').CounterSamples"
           " | Measure-Object CookedValue -Sum | ForEach-Object Sum")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, check=False)
    return float(out.stdout.strip() or 0) / 1e9


def model_vram_gb(host: str, model: str) -> float:
    with urllib.request.urlopen(f"{host}/api/ps") as resp:
        ps = json.loads(resp.read())["models"]
    return sum(m.get("size_vram", 0) for m in ps if m["name"] == model) / 1e9


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--host", default="http://127.0.0.1:11435")
    ap.add_argument("--runs", type=int, default=6)
    args = ap.parse_args()

    prompts = csv.DictReader(Path(__file__).with_name("dataset_prompts.csv").open(encoding="utf-8"))
    turns = [p["prompt"] for p in prompts if p["kind"] == "error"][: args.runs]
    out = ROOT / "data" / "s2"
    out.mkdir(parents=True, exist_ok=True)

    base_gb = gpu_dedicated_gb()
    print(f"VRAM en uso antes de cargar LLMs (whisper incluido si está levantado): {base_gb:.1f} GB")
    summary, samples = [], []
    for model in args.models:
        print(f"\n== {model}")
        companion(args.host, model, "Hi!")  # carga el modelo + calentamiento
        tutor(args.host, model, "Hi!")
        vram_model, vram_total = model_vram_gb(args.host, model), gpu_dedicated_gb()

        solo, busy, tutors = [], [], []
        for turn in turns:
            r = companion(args.host, model, turn)
            solo.append(r)
            samples.append({"model": model, "role": "companion", "user": turn, "reply": r["text"]})
            print(f"  solo       ttft {r['ttft_ms']:4} ms  frase {r['sentence_ms']:4} ms  {r['tps']:5.1f} tok/s")
        for turn in turns:
            t = {}
            th = threading.Thread(target=lambda d, *a: d.update(tutor(*a)), args=(t, args.host, model, turn))
            th.start()
            time.sleep(0.3)  # el tutor ya está generando cuando llega el compañero
            r = companion(args.host, model, turn)
            th.join()
            busy.append(r)
            tutors.append(t)
            samples.append({"model": model, "role": "tutor", "user": turn, "reply": t["text"]})
            print(f"  con tutor  ttft {r['ttft_ms']:4} ms  frase {r['sentence_ms']:4} ms  {r['tps']:5.1f} tok/s"
                  f"  | tutor {t['total_ms']} ms")

        def med(rs, k):
            return statistics.median(x[k] for x in rs)

        summary.append({
            "model": model, "vram_model_gb": round(vram_model, 1), "vram_total_gb": round(vram_total, 1),
            "solo_ttft": med(solo, "ttft_ms"), "solo_sentence": med(solo, "sentence_ms"), "solo_tps": med(solo, "tps"),
            "busy_ttft": med(busy, "ttft_ms"), "busy_sentence": med(busy, "sentence_ms"), "busy_tps": med(busy, "tps"),
            "tutor_ms": med(tutors, "total_ms"),
            "tutor_json_ok": sum(_valid_tutor(t["text"]) for t in tutors), "n": len(tutors),
        })
        post(f"{args.host}/api/generate", {"model": model, "keep_alive": 0}).close()  # libera VRAM

    with (out / "samples.json").open("w", encoding="utf-8") as f:
        json.dump(samples, f, ensure_ascii=False, indent=1)
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(summary[0]))
        w.writeheader()
        w.writerows(summary)

    print("\n| Modelo | VRAM modelo / total | TTFT solo | 1.ª frase solo | tok/s solo "
          "| TTFT con tutor | 1.ª frase con tutor | tok/s con tutor | Tutor (total) | JSON tutor OK |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for s in summary:
        print(f"| {s['model']} | {s['vram_model_gb']} / {s['vram_total_gb']} GB | {s['solo_ttft']:.0f} ms "
              f"| {s['solo_sentence']:.0f} ms | {s['solo_tps']:.0f} | {s['busy_ttft']:.0f} ms "
              f"| {s['busy_sentence']:.0f} ms | {s['busy_tps']:.0f} | {s['tutor_ms']:.0f} ms "
              f"| {s['tutor_json_ok']}/{s['n']} |")
    print(f"\nRespuestas: {out / 'samples.json'}")


def _valid_tutor(text: str) -> bool:
    try:
        return isinstance(json.loads(text).get("errors"), list)
    except (ValueError, AttributeError):
        return False


if __name__ == "__main__":
    main()
