# TODO — IABuddy

> Referencia: [docs/DISENO.md](docs/DISENO.md) · Última actualización: 2026-10-28
>
> Leyenda: 🔴 bloquea el inicio del código · 🟡 bloquea una fase concreta · 🟢 se puede decidir sobre la marcha

---

## 1. Decisiones pendientes antes de escribir código

### 1.1 Entorno y herramientas 🔴
- [x] **Windows nativo vs. WSL2** → **Windows 11 nativo**. (Bonus: habilita la opción secundaria PyTorch+ROCm, que exige Windows 11.)
- [x] **Versión de Python** → **Python 3.12** + **`uv`** como gestor de paquetes.
- [x] **Dónde guardar los modelos** → **`C:\Models`** (fuera del repo; ruta configurable por variable de entorno `IABUDDY_MODELS_DIR`). Ollama mantiene su propio almacén (`OLLAMA_MODELS` si se quiere moverlo ahí).
- [x] **Control de versiones** → **repositorio público en GitHub**.
- [x] **Licencia** → **MIT**. Los modelos no se suben al repo (cada uno conserva su licencia); solo se documenta cómo descargarlos.
- [x] **Nombre del repositorio** → **IABuddy** (`github.com/AmadoRamos/IABuddy`).

### 1.2 Audio y experiencia de voz 🔴
- [x] **Micrófono y salida** → **audífonos**. El MVP asume audífonos; la cancelación de eco queda como mejora opcional.
- [x] **Estrategia de turno** → **tecla para empezar a hablar + fin de turno por silencio configurable**.
  - Pulsar la tecla abre tu turno; el turno se cierra tras N ms de silencio (configurable en la UI) o al volver a pulsar la tecla.
  - Pulsar la tecla mientras habla el compañero = **interrupción** (barge-in explícito, sin falsos positivos).
  - Pendiente: valor por defecto del silencio (se fija en el spike S4) y qué tecla (propuesta: **Espacio**).
- [x] **Acento del compañero** → **US**. Voces Kokoro en inglés americano y fonemas de referencia `en-us` para pronunciación.
- [ ] **Velocidad de habla por defecto** del compañero (normal o 0,9× para B1–B2).

### 1.3 Comportamiento pedagógico 🟡 (Fase 2)
- [ ] **Modo de corrección por defecto:** silencioso (solo resumen al final) / panel lateral en vivo / el compañero corrige en voz.
- [ ] **Idioma de las explicaciones:** español, inglés, o según el nivel.
- [ ] **Qué corregir:** ¿solo errores que impiden entender, o también naturalidad/estilo? (Corregir todo abruma en B1–B2.)
- [ ] **Persona:** un único compañero fijo o varias personalidades seleccionables.
- [ ] **Temas de conversación libre:** totalmente libre, lista de temas sugeridos, o temas ligados a tus intereses (tecnología, entrevistas, etc.).

### 1.4 Modelos 🟡 (se cierran con los spikes de la Fase 0)
- [x] **STT:** whisper.cpp `large-v3-turbo` (Vulkan) vs. Parakeet TDT 0.6B (ONNX, CPU). Criterio principal: **transcripción literal de tus errores**, luego latencia. → **whisper.cpp `large-v3-q5_0` (v3 cuantizado, sin turbo), GPU por Vulkan, greedy y sin prompt** ([S1](docs/SPIKES.md#s1--stt-literal-2026-10-28)). Tiene la misma precisión que v3 con 1,8 GB de VRAM.
- [x] **Cómo integrar whisper.cpp:** como proceso `whisper-server` (HTTP) o con bindings de Python compilados con Vulkan. → **Proceso aparte con `whisper-server` (HTTP)**: probado en S1, unos 160 ms por frase.
- [x] **LLM:** elegir entre 2–3 candidatos de 8–14B en Q4. → **`gemma4:12b-it-qat`** en Ollama con `OLLAMA_NUM_PARALLEL=2` ([S2](docs/SPIKES.md#s2--llm-2026-10-28)).
- [x] **Un modelo o dos:** el mismo LLM para compañero y tutor, o un modelo más pequeño solo para el tutor. Depende de la contención de GPU que salga en el spike. → **Un solo modelo.** Con el tutor activo, el compañero sigue cumpliendo: 248 ms de primer token y 50 tok/s.
- [ ] **Voz TTS concreta** dentro de Kokoro (escuchar 3–4 voces y escoger).

### 1.5 Datos y privacidad 🟢
- [ ] **¿Guardar grabaciones de audio?** Sí / no / solo los turnos con errores de pronunciación.
- [ ] **Retención:** ¿borrar sesiones viejas automáticamente?
- [ ] **Duración típica de una sesión** (10, 20, 30 min). Define cómo resumir el historial para no llenar el contexto del LLM.

### 1.6 Frontend 🟢
- [ ] **Tecnología:** HTML + JS vanilla (propuesta para el MVP) vs. htmx vs. un framework ligero (Svelte/Preact) cuando la UI crezca.
- [ ] **Exposición de red:** solo `127.0.0.1` (propuesta) o también accesible desde otros equipos de la red local (p. ej. practicar desde el portátil o el móvil; requiere HTTPS para que el navegador permita el micrófono).

---

## 2. Preparación del entorno 🔴

- [x] Actualizar drivers AMD Adrenalin y verificar Vulkan (`vulkaninfo --summary`). → Driver 26.10.1 (17/10/2026), Vulkan 1.4.359, RX 9070 detectada.
- [x] Instalar Ollama para Windows y confirmar que usa la RX 9070 (`ollama ps` → 100 % GPU). → Ollama 0.40.12 usa **ROCm** (no Vulkan) en la RX 9070. En S2, comparar con `OLLAMA_VULKAN=1`.
- [x] Descargar o compilar whisper.cpp con Vulkan para Windows y probar `whisper-cli` con un audio. → No hay binario oficial con Vulkan para Windows: se compiló v1.9.5 en `C:\Tools\whisper.cpp` (VS 2022 + CMake + Vulkan SDK 1.4.363). Ejecutables en `build\bin\Release\` (`whisper-cli`, `whisper-server`). Modelo `large-v3-turbo` en `C:\Models\whisper`. `jfk.wav` se transcribe bien, con encode de 823 ms.
- [x] Instalar Python 3.12, `uv`, `git`. (Python 3.12 gestionado por `uv`, fijado en `.python-version`.)
- [x] Instalar **espeak-ng** para Windows (lo necesitan `phonemizer` y Kokoro para fonemas). → 1.52.0 en `C:\Program Files\eSpeak NG`.
- [x] Instalar `ffmpeg` (conversión de audios de prueba). → 9.0.2.
- [x] Crear estructura base del repo (`backend/`, `frontend/`, `spikes/`, `tests/`) + `pyproject.toml` + `.gitignore` (excluye `models/`, `data/`, audios y pesos). Los modelos viven en `C:\Models`, no en el repo.

---

## 3. Fase 0 — Spikes de validación

### 3.1 Dataset de prueba (lo graba Amado) 🔴
> Grabador listo: doble clic en `grabar_dataset.bat` o `uv run --group spikes python spikes/record_dataset.py` (opcional `--only error|pair|free`). Las frases están en [spikes/dataset_prompts.csv](spikes/dataset_prompts.csv) y se pueden editar o sustituir por errores tuyos. La salida va a `data/dataset/` (fuera del repo), con WAV y `manifest.csv`. El script se puede cortar y retomar.
- [x] **20–30 frases con errores reales** típicos (tiempos verbales, preposiciones, artículos, orden de palabras). Guardar también el texto *exacto* que dijiste, con los errores. → 28 (`e01`–`e28`).
- [x] **10–15 pares mínimos** de pronunciación: *ship/sheep*, *very/berry*, *watch/wash*, *think/sink*, *walked* (-ed), *school* (s inicial), etc. → 9 pares + 6 palabras sueltas (`p01a`–`p11c`).
- [x] 3–4 grabaciones largas (30–60 s) hablando libremente, con pausas naturales. → 4 (`f01`–`f04`): 44, 21, 14 y 20 s.
- [x] Formato: WAV 16 kHz mono, nombre + transcripción en un `manifest.csv`. → `data/dataset/` (56 archivos, fuera del repo).
- Pasada previa con whisper `large-v3-turbo`: conserva la mayoría de los errores, pero corrige algunas preposiciones y artículos (*interested on*, *arrived to*, *explain me*, *a engineer*, *informations*). Con palabras sueltas falla mucho, así que para S5 hace falta el modelo de fonemas.

### 3.2 Spikes
- [x] **S1 — STT literal.** Transcribir el dataset con whisper.cpp y Parakeet; medir WER contra tu texto literal, y en particular **cuántos de tus errores se conservan** vs. cuántos "corrige" el modelo. Medir latencia por frase.
  - ✅ Criterio: conserva ≥ 80 % de los errores y < 500 ms por frase corta.
  - → [Resultados](docs/SPIKES.md#s1--stt-literal-2026-10-28): gana **whisper `large-v3` (sin turbo)**. Conserva el 68 % de los errores, que es el **86 % si no se cuentan los fallos de pronunciación** ✅, y tarda unos 160 ms por frase en GPU ✅. Turbo conserva el 54 % (71 %), Parakeet el 46 % (72 %), y *beam search* no ayuda.
- [x] **S2 — LLM.** Con 2–3 modelos: tiempo a primer token, tokens/s, VRAM; repetir con una petición del tutor en paralelo (`OLLAMA_NUM_PARALLEL`).
  - ✅ Criterio: primer token < 500 ms y ≥ 30 tok/s con el tutor activo.
  - → [Resultados](docs/SPIKES.md#s2--llm-2026-10-28): **gemma4:12b-it-qat** cumple con el tutor activo (266 ms y 46 tok/s) y es el mejor en *recasting* y como tutor. Pero la VRAM total llega a 15,7 GB con whisper v3. qwen3.5 no procesa en paralelo y llama3.1 es rápido pero pobre. Con whisper `large-v3-q5_0` (los mismos errores conservados que v3), el stack ocupa **10,4 GB** ✅, con 248 ms de primer token y 50 tok/s con el tutor activo ✅.
- [ ] **S3 — TTS.** Kokoro ONNX en CPU: latencia de la primera frase y factor de tiempo real.
  - ✅ Criterio: < 200 ms para una frase de ~10 palabras.
- [ ] **S4 — Fin de turno.** Pasar las grabaciones largas por Silero VAD con distintos umbrales de silencio y ver dónde te corta; fijar el valor por defecto.
- [ ] **S5 — Pronunciación.** wav2vec2 de fonemas sobre los pares mínimos: ¿distingue *ship* de *sheep* en tu voz?
- [ ] **S6 — Ida y vuelta por terminal.** Micrófono → VAD → STT → LLM → TTS → altavoz; medir la latencia total por etapa.
  - ✅ Criterio: < 1,5 s del fin de tu frase al primer audio.
- [ ] Documentar resultados en `docs/SPIKES.md` y cerrar las decisiones del punto 1.4.

---

## 4. Fases de implementación (después de la Fase 0)

### Fase 1 — Loop de voz (MVP)
- [ ] Interfaces `VAD`, `STT`, `LLM`, `TTS` + implementaciones elegidas.
- [ ] Turn Manager: máquina de estados (escuchando → procesando → hablando), barge-in, cancelación.
- [ ] WebSocket de audio bidireccional + AudioWorklet en el navegador.
- [ ] Streaming LLM → corte por frases → TTS → reproducción encadenada.
- [ ] Prompt de persona para conversación libre B1–B2 con *recasting*.
- [ ] Instrumentación de latencia por etapa desde el día 1 (logs + panel de depuración en la UI).
- [ ] Script de arranque único (levanta/verifica Ollama, whisper-server y el backend).

### Fase 2 — Feedback
- [ ] Tutor asíncrono con salida JSON con esquema + cola de prioridad compañero > tutor.
- [ ] Panel de correcciones en la UI.
- [ ] Resumen de sesión.
- [ ] SQLite: `sessions`, `turns`, `corrections`.

### Fase 3 — Escenarios
- [ ] Formato YAML y cargador de escenarios.
- [ ] 5 escenarios iniciales (entrevista backend Python, daily standup, restaurante, hotel, small talk).
- [ ] Seguimiento de objetivos y evaluación final.

### Fase 4 — Pronunciación
- [ ] Puntuación por palabra/fonema (modo pasivo en conversación).
- [ ] Modo drill con frases propuestas y repetición de las falladas.

### Fase 5 — Progreso
- [ ] Historial de sesiones y métricas en el tiempo.
- [ ] Errores recurrentes y repaso de vocabulario.

---

## 5. Orden sugerido para cerrar lo que bloquea

1. ~~Decidir 1.1 (entorno) y 1.2 (audio)~~ ✅
2. ~~Diseño de la UI~~ ✅ — 7 pantallas con gamificación, guardadas en [docs/ui/](docs/ui/README.md).
3. ~~Preparación del entorno (sección 2)~~ ✅
4. ~~Grabar el dataset (3.1)~~ ✅
5. Ejecutar los **spikes** y cerrar **1.4** con datos.
6. Arrancar la **Fase 1**. Las decisiones 1.3, 1.5 y 1.6 se pueden tomar durante la Fase 1.
