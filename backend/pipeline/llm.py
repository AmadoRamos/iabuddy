"""LLM: Ollama en streaming (`gemma4:12b-it-qat`, S2). Cancelar la tarea cierra la petición."""

import json
import logging
from collections.abc import AsyncIterator

import httpx

log = logging.getLogger("iabuddy")


def _log_stats(kind: str, obj: dict) -> None:
    """Lo que cuenta Ollama de cada petición, para saber dónde se va el tiempo (data/logs/iabuddy.log)."""
    ms = {k: round(obj.get(k, 0) / 1e6) for k in ("load_duration", "prompt_eval_duration", "eval_duration")}
    log.info("LLM %s: prompt %s tokens en %d ms, respuesta %s tokens en %d ms, carga %d ms", kind,
             obj.get("prompt_eval_count"), ms["prompt_eval_duration"], obj.get("eval_count"), ms["eval_duration"],
             ms["load_duration"])


class OllamaLLM:
    def __init__(self, url: str, model: str, client: httpx.AsyncClient):
        self.url, self.model, self.client = url, model, client

    def _payload(self, messages: list[dict], stream: bool) -> dict:
        return {"model": self.model, "messages": messages, "stream": stream, "think": False,
                "keep_alive": "30m", "options": {"num_ctx": 4096, "temperature": 0.7}}

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        async with self.client.stream("POST", f"{self.url}/api/chat",
                                      json=self._payload(messages, True)) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line:
                    continue
                obj = json.loads(line)
                if "error" in obj:
                    raise RuntimeError(obj["error"])
                if piece := obj.get("message", {}).get("content"):
                    yield piece
                if obj.get("done"):
                    _log_stats("respuesta", obj)

    async def chat_json(self, messages: list[dict], schema: dict) -> dict:
        """Respuesta completa forzada a un esquema JSON (lo usa el tutor)."""
        payload = self._payload(messages, False) | {"format": schema}
        payload["options"] = payload["options"] | {"temperature": 0}
        r = await self.client.post(f"{self.url}/api/chat", json=payload)
        r.raise_for_status()
        _log_stats("json", r.json())
        return json.loads(r.json()["message"]["content"])

    async def warm(self) -> None:
        """Carga el modelo en VRAM para que el primer turno no pague la carga."""
        r = await self.client.post(f"{self.url}/api/chat", json=self._payload([], False))
        r.raise_for_status()
