"""Spike S1 — STT literal: whisper.cpp vs Parakeet sobre el dataset de la Fase 0.

    # 1) un whisper-server por configuración whisper (puertos en WHISPER), p. ej.:
    C:\\Tools\\whisper.cpp\\build\\bin\\Release\\whisper-server.exe -m C:\\Models\\whisper\\ggml-large-v3-turbo.bin -l en --port 8178
    #    (+beam5: añadir -bs 5; v3: ggml-large-v3.bin)
    # 2) el spike (por defecto todos los sistemas; --systems para elegir):
    uv run --group spikes python spikes/s1_stt.py --systems whisper-turbo parakeet-tdt-v2

Mide por sistema: WER contra tu texto literal, cuántos errores gramaticales conserva
(vs. "corrige"), acierto en pares mínimos y latencia por frase. Guarda el detalle en
data/s1/results.csv.
"""

import argparse
import csv
import json
import re
import statistics
import time
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHISPER_PROMPT = "Um, so I goes to the office yesterday and he don't know nothing about it."
# sistema -> (puerto de whisper-server, prompt)
WHISPER = {
    "whisper-turbo": (8178, None),
    "whisper-turbo+prompt": (8178, WHISPER_PROMPT),
    "whisper-v3": (8179, None),
    "whisper-turbo+beam5": (8180, None),
    "whisper-v3+beam5": (8181, None),
}


def norm(text: str) -> str:
    text = text.lower().replace("\u2019", "'").replace("\u2014", " ")
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", text).split())


def wer_counts(ref: str, hyp: str) -> tuple[int, int]:
    """(ediciones, palabras de la referencia) por distancia de Levenshtein entre palabras."""
    r, h = ref.split(), hyp.split()
    prev = list(range(len(h) + 1))
    for i, rw in enumerate(r, 1):
        cur = [i]
        for j, hw in enumerate(h, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw)))
        prev = cur
    return prev[-1], len(r)


def has(hyp: str, options: str) -> bool:
    return any(f" {o} " in f" {hyp} " for o in options.split("|"))


def classify(hyp: str, error: str, correct: str) -> str:
    if has(hyp, error):
        return "conserva"
    return "corrige" if has(hyp, correct) else "otro"


def _selfcheck() -> None:
    assert norm("I’ve — got IT!") == "i've got it"
    assert wer_counts("a b c", "a x c") == (1, 3)
    assert wer_counts("a b c", "a c") == (1, 3)
    assert classify("she don't like it", "she don't", "she doesn't") == "conserva"
    assert classify("she doesn't like it", "she don't", "she doesn't") == "corrige"
    assert classify("life in the city", "the life in the city", "life in the city") == "corrige"
    assert classify("the life in the city", "the life in the city", "life in the city") == "conserva"


def whisper(url: str, prompt: str | None):
    def run(path: Path) -> str:
        boundary = uuid.uuid4().hex
        fields = {"response_format": "json", "temperature": "0"}
        if prompt:
            fields["prompt"] = prompt
        body = b"".join(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
            for k, v in fields.items()
        )
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                 f'filename="{path.name}"\r\nContent-Type: audio/wav\r\n\r\n').encode()
        body += path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())["text"]
    return run


def parakeet(model_dir: Path):
    import onnx_asr

    model = onnx_asr.load_model("nemo-parakeet-tdt-0.6b-v2", model_dir)
    return lambda path: model.recognize(str(path))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "dataset")
    ap.add_argument("--parakeet-dir", type=Path, default=Path("C:/Models/parakeet-tdt-0.6b-v2"))
    ap.add_argument("--systems", nargs="+", choices=[*WHISPER, "parakeet-tdt-v2"],
                    default=[*WHISPER, "parakeet-tdt-v2"])
    args = ap.parse_args()
    _selfcheck()

    rows = list(csv.DictReader((args.data / "manifest.csv").open(encoding="utf-8")))
    errors = {r["id"]: r for r in csv.DictReader(Path(__file__).with_name("s1_errors.csv").open(encoding="utf-8"))}
    systems = {
        name: parakeet(args.parakeet_dir) if name == "parakeet-tdt-v2"
        else whisper(f"http://127.0.0.1:{WHISPER[name][0]}/inference", WHISPER[name][1])
        for name in args.systems
    }

    # Conserva los resultados de sistemas que no se vuelven a ejecutar.
    out = ROOT / "data" / "s1"
    old = list(csv.DictReader((out / "results.csv").open(encoding="utf-8"))) if (out / "results.csv").exists() else []
    results = [x for x in old if x["system"] not in systems]
    for name, stt in systems.items():
        stt(args.data / rows[0]["file"])  # calentamiento, no cuenta
        for r in rows:
            t = time.perf_counter()
            hyp = stt(args.data / r["file"])
            ms = (time.perf_counter() - t) * 1000
            ref, h = norm(r["text"]), norm(hyp)
            edits, n = wer_counts(ref, h)
            status = ""
            if r["kind"] == "error" and r["id"] in errors:
                if not has(ref, errors[r["id"]]["error"]):
                    status = "sin-error-en-ref"  # dijiste otra cosa: no cuenta
                else:
                    status = classify(h, errors[r["id"]]["error"], errors[r["id"]]["correct"])
            elif r["kind"] == "pair":
                status = "ok" if h == ref else "falla"
            results.append({"system": name, "id": r["id"], "kind": r["kind"], "ms": round(ms),
                            "seconds": r["seconds"], "edits": edits, "words": n,
                            "status": status, "ref": r["text"], "hyp": hyp.strip()})
            print(f"{name:22}{r['id']:6}{ms:7.0f} ms  {status:9} {hyp.strip()[:70]}")

    out.mkdir(parents=True, exist_ok=True)
    with (out / "results.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(results[0]))
        w.writeheader()
        w.writerows(results)

    print("\n| Sistema | WER frases | WER libre | Errores conservados | Corregidos | Otro | Pares OK "
          "| Latencia frase (mediana / p90) | RTF libre |")
    print("|---|---|---|---|---|---|---|---|---|")
    for name in dict.fromkeys(x["system"] for x in results):
        mine = [x for x in results if x["system"] == name]
        for x in mine:  # las filas leídas del CSV vienen como texto
            x["edits"], x["words"], x["ms"] = int(x["edits"]), int(x["words"]), int(x["ms"])

        def wer(kind, mine=mine):
            sel = [x for x in mine if x["kind"] == kind]
            return sum(x["edits"] for x in sel) / max(1, sum(x["words"] for x in sel))

        st = [x["status"] for x in mine if x["kind"] == "error" and x["status"] != "sin-error-en-ref"]
        pairs = [x for x in mine if x["kind"] == "pair"]
        lat = sorted(x["ms"] for x in mine if x["kind"] == "error")
        free = [x for x in mine if x["kind"] == "free"]
        rtf = sum(x["ms"] for x in free) / 1000 / max(1e-9, sum(float(x["seconds"]) for x in free))
        print(f"| {name} | {wer('error'):.1%} | {wer('free'):.1%} "
              f"| {st.count('conserva')}/{len(st)} ({st.count('conserva') / max(1, len(st)):.0%}) "
              f"| {st.count('corrige')} | {st.count('otro')} "
              f"| {sum(x['status'] == 'ok' for x in pairs)}/{len(pairs)} "
              f"| {statistics.median(lat):.0f} / {lat[int(len(lat) * 0.9) - 1]:.0f} ms | {rtf:.3f} |")
    print(f"\nDetalle: {out / 'results.csv'}")


if __name__ == "__main__":
    main()
