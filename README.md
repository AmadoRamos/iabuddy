# IABuddy

Compañero local de conversación en inglés (B1–B2) con correcciones de gramática y pronunciación. Todo corre en local: STT, LLM y TTS.

- Diseño: [docs/DISENO.md](docs/DISENO.md)
- UI: [docs/ui/](docs/ui/README.md)
- Pendientes: [TODO.md](TODO.md)

## Requisitos

- Windows 11, GPU con Vulkan
- Python 3.12 + [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com), whisper.cpp (Vulkan), espeak-ng, ffmpeg

## Puesta en marcha

```bash
uv sync
```

Los modelos no van en el repo. Se descargan en `C:\Models` (o en la ruta de `IABUDDY_MODELS_DIR`).

## Estructura

```
backend/   servidor Python (pipeline de voz, tutor, API)
frontend/  UI web
spikes/    pruebas de la Fase 0
tests/
docs/
```

## Licencia

MIT. Cada modelo conserva su propia licencia.
