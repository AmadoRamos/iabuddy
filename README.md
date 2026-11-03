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

Los modelos no van en el repo. Se descargan en `C:\Models` (o en la ruta de `IABUDDY_MODELS_DIR`). Qué modelo usa cada etapa y por qué está en [docs/SPIKES.md](docs/SPIKES.md).

### Usar la app

Doble clic en **`iabuddy.bat`**. Arranca whisper-server y Ollama si hacen falta, compila el frontend la primera vez, levanta el backend y abre http://127.0.0.1:8000 (Chrome o Edge).

Para hablar, pulsa **Espacio** para abrir tu turno y otra vez para cerrarlo. Si haces una pausa, el turno se cierra solo y, si sigues hablando, se reabre. Pulsar Espacio mientras habla Buddy lo interrumpe.

### Desarrollo

```bash
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

En otra terminal, el frontend con recarga en caliente, en http://127.0.0.1:5173. Hace de proxy de `/ws` y `/api` al backend:

```bash
cd frontend && npm run dev
```

Tests del backend:

```bash
uv run pytest
```

Si cambias el frontend y usas `iabuddy.bat`, vuelve a compilar con `npm run build` dentro de `frontend/`.

## Estructura

```
backend/   servidor FastAPI: pipeline de voz (VAD, STT, LLM, TTS) y Turn Manager
frontend/  UI en React + Vite, con el sistema de diseño (css/, design-system.html)
spikes/    pruebas de la Fase 0
tests/
docs/
```

## Licencia

MIT. Cada modelo conserva su propia licencia.
