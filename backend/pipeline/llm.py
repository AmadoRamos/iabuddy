"""LLM: Ollama en streaming (`gemma4:12b-it-qat`, S2). Cancelar la tarea cierra la petición."""

import json
from collections.abc import AsyncIterator

import httpx


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

    async def warm(self) -> None:
        """Carga el modelo en VRAM para que el primer turno no pague la carga."""
        r = await self.client.post(f"{self.url}/api/chat", json=self._payload([], False))
        r.raise_for_status()
