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
  - Valor por defecto del silencio: **900 ms** con fusión de turno (S4 proponía 1.500 ms sin fusión; se configura con `IABUDDY_SILENCE_MS`). Tecla: **Espacio**.
- [x] **Acento del compañero** → **US**. Voces Kokoro en inglés americano y fonemas de referencia `en-us` para pronunciación.
- [x] **Velocidad de habla por defecto** del compañero (normal o 0,9× para B1–B2). → **0,9×** (elegida de oído en S3).

### 1.3 Comportamiento pedagógico 🟡 (Fase 2)
- [x] **Modo de corrección por defecto:** silencioso (solo resumen al final) / panel lateral en vivo / el compañero corrige en voz. → **El compañero corrige en voz.**
- [x] **Idioma de las explicaciones:** español, inglés, o según el nivel. → **Español.**
- [x] **Qué corregir:** ¿solo errores que impiden entender, o también naturalidad/estilo? (Corregir todo abruma en B1–B2.) → **Todo** (gramática, vocabulario, naturalidad y estilo).
- [x] **Persona:** un único compañero fijo o varias personalidades seleccionables. → **Fijo: Buddy.**
- [x] **Temas de conversación libre:** totalmente libre, lista de temas sugeridos, o temas ligados a tus intereses (tecnología, entrevistas, etc.). → **Lista de temas sugeridos, configurable en la base de datos.**
- **Cómo encajan «en voz» y «en español»** (decidido por Amado el 2026-11-03): Buddy es amigo **e instructor**, y las correcciones son parte de la conversación.
  - **En voz:** en su propia respuesta, Buddy reacciona a lo que dijiste (y contesta si le preguntaste algo), señala **uno o dos errores** con la forma correcta y un porqué breve, y sigue con una pregunta (*"Just a small tip, since we are talking about yesterday, you should say I went…"*). Habla en inglés porque su voz (Kokoro `af_heart`) es inglesa. No añade latencia: lo genera el mismo LLM que conversa.
  - **En texto:** el tutor registra **todos** los errores con su explicación en español (panel y resumen de sesión).
  - En los modos «panel» y «silencioso», Buddy no interrumpe y solo hace *recasting*.

### 1.4 Modelos 🟡 (se cierran con los spikes de la Fase 0)
- [x] **STT:** whisper.cpp `large-v3-turbo` (Vulkan) vs. Parakeet TDT 0.6B (ONNX, CPU). Criterio principal: **transcripción literal de tus errores**, luego latencia. → **whisper.cpp `large-v3-q5_0` (v3 cuantizado, sin turbo), GPU por Vulkan, greedy y sin prompt** ([S1](docs/SPIKES.md#s1--stt-literal-2026-10-28)). Tiene la misma precisión que v3 con 1,8 GB de VRAM.
- [x] **Cómo integrar whisper.cpp:** como proceso `whisper-server` (HTTP) o con bindings de Python compilados con Vulkan. → **Proceso aparte con `whisper-server` (HTTP)**: probado en S1, unos 160 ms por frase.
- [x] **LLM:** elegir entre 2–3 candidatos de 8–14B en Q4. → **`gemma4:12b-it-qat`** en Ollama con `OLLAMA_NUM_PARALLEL=2` ([S2](docs/SPIKES.md#s2--llm-2026-10-28)).
- [x] **Un modelo o dos:** el mismo LLM para compañero y tutor, o un modelo más pequeño solo para el tutor. Depende de la contención de GPU que salga en el spike. → **Un solo modelo.** Con el tutor activo, el compañero sigue cumpliendo: 248 ms de primer token y 50 tok/s.
- [x] **Voz TTS concreta** dentro de Kokoro (escuchar 3–4 voces y escoger). → **`af_heart`** a velocidad 0,9.

### 1.5 Datos y privacidad 🟢
- [ ] **¿Guardar grabaciones de audio?** Sí / no / solo los turnos con errores de pronunciación.
- [ ] **Retención:** ¿borrar sesiones viejas automáticamente?
- [ ] **Duración típica de una sesión** (10, 20, 30 min). Define cómo resumir el historial para no llenar el contexto del LLM.

### 1.6 Frontend 🟢
- [x] **Tecnología:** HTML + JS vanilla (propuesta para el MVP) vs. htmx vs. un framework ligero (Svelte/Preact) cuando la UI crezca. → **React + Vite.** Reutiliza el CSS del sistema de diseño (`theme.css`, `components.css`). En producción, FastAPI sirve el build (`frontend/dist`); en desarrollo, Vite hace de proxy al backend.
- [x] **Exposición de red:** solo `127.0.0.1` (propuesta) o también accesible desde otros equipos de la red local (p. ej. practicar desde el portátil o el móvil; requiere HTTPS para que el navegador permita el micrófono). → **Solo `127.0.0.1`.**
- **Backend:** Python 3.12 + **FastAPI/Uvicorn**, un **WebSocket** para el audio y los eventos, y `httpx` para Ollama y whisper-server.

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
- [x] **S3 — TTS.** Kokoro ONNX en CPU: latencia de la primera frase y factor de tiempo real.
  - ✅ Criterio: < 200 ms para una frase de ~10 palabras.
  - → [Resultados](docs/SPIKES.md#s3--tts-2026-10-28): ❌ tarda 644 ms por frase y 372 ms cortando el primer trozo, con un coste fijo de unos 300 ms por llamada en CPU. RTF 0,23. DirectML falla. Se usa fp32 en CPU con el primer trozo corto, y se evalúa en S6 contra el presupuesto total de 1,5 s. Si no llega, Kokoro en GPU con PyTorch + ROCm.
- [x] **S4 — Fin de turno.** Pasar las grabaciones largas por Silero VAD con distintos umbrales de silencio y ver dónde te corta; fijar el valor por defecto.
  - → [Resultados](docs/SPIKES.md#s4--fin-de-turno-2026-10-29): en habla libre haces pausas de hasta 2,5 s. Con 900 ms te cortaría 10 veces en 63 s y con 1.500 ms, 2 veces. **El fin de turno principal es la tecla.** El silencio queda como red de seguridad con **1.500 ms** por defecto. En la Fase 1 se añade la *fusión de turno* (si sigues hablando tras un corte, se cancela la respuesta y se une al turno).
- [x] **S5 — Pronunciación.** wav2vec2 de fonemas sobre los pares mínimos: ¿distingue *ship* de *sheep* en tu voz?
  - → [Resultados](docs/SPIKES.md#s5--pronunciaci%C3%B3n-2026-10-29): **sí.** Gana la palabra que querías decir en 15/24. Los "fallos" con margen claro coinciden con rasgos típicos de hispanohablante (*ship → ʃi*, *three → tɹi*, *yet → dʒe*, *chair → ʃe*), así que probablemente es tu pronunciación real (**confírmalo escuchando**). Tarda unos 0,1 s por segundo de audio en CPU. Para producción hay que exportarlo a ONNX.
- [x] **S6 — Ida y vuelta por terminal.** Micrófono → VAD → STT → LLM → TTS → altavoz; medir la latencia total por etapa.
  - ✅ Criterio: < 1,5 s del fin de tu frase al primer audio.
  - → [Resultados](docs/SPIKES.md#s6--ida-y-vuelta-por-terminal-2026-11-03), 8 turnos reales:
    - **Desde el cierre del turno: 1,05 s de mediana y 1,37 s de máximo** ✅.
    - **Desde el fin de tu voz: 1,95 s** ❌, por tu reacción para pulsar la tecla (unos 0,45 s) o por el silencio de 1,5 s.
    - Mejoras para la Fase 1: fusión de turno con ~900 ms de silencio, primer trozo más corto y descartar turnos sin voz (alucinación *"Thank you."*).
- [x] Documentar resultados en `docs/SPIKES.md` y cerrar las decisiones del punto 1.4.

---

## 4. Fases de implementación (después de la Fase 0)

### Fase 1 — Loop de voz (MVP)
- [x] Interfaces `VAD`, `STT`, `LLM`, `TTS` + implementaciones elegidas → `backend/pipeline/` (una clase por etapa, intercambiables).
- [x] Turn Manager: máquina de estados (escuchando → procesando → hablando), barge-in, cancelación → `turn_manager.py`. Incluye las mejoras de S4/S6:
  - **fusión de turno**: si sigues hablando antes de que suene la respuesta, se reabre tu turno;
  - **silencio de 900 ms** gracias a la fusión;
  - **descarte de turnos sin voz**.
- [x] WebSocket de audio bidireccional + AudioWorklet en el navegador.
- [x] Streaming LLM → corte por frases → TTS → reproducción encadenada. El primer trozo se corta en la 1.ª puntuación o tras 6 palabras (`chunker.py`).
- [x] Prompt de persona para conversación libre B1–B2 con *recasting* (reforzado con un ejemplo, `partner/prompts.py`).
- [x] Instrumentación de latencia por etapa desde el día 1: panel «Tiempos» en la UI, con el tiempo del servidor y el que mide el navegador.
- [x] Script de arranque único (levanta/verifica Ollama, whisper-server y el backend) → `iabuddy.bat`.
- [x] **Probar con micrófono real** (Chrome/Edge) y ajustar. Probado en el navegador con una grabación del dataset como micrófono (1,67 s hasta el primer audio, con el prompt en frío) y por Amado con su micrófono el 2026-11-03: todo funciona.

### Fase 2 — Feedback
- [x] Tutor asíncrono con salida JSON con esquema + cola de prioridad compañero > tutor → `backend/tutor/tutor.py`.
  - Corre **en paralelo** con la respuesta (no después), porque el *tip* en voz tiene que estar listo antes de que Buddy termine. Necesita `OLLAMA_NUM_PARALLEL=2`.
  - Medido: compañero con el primer token a ~400–600 ms y tutor en ~3 s.
- [x] Panel de correcciones en la UI, con los modos silencioso / panel / en voz y el *tip* hablado al final de la respuesta.
- [x] Resumen de sesión: duración, turnos, palabras por minuto, turnos sin errores, errores que se repiten y frases para repasar.
- [x] SQLite: `sessions`, `turns`, `corrections` y `topics` (temas sugeridos, editables en la tabla) → `data/iabuddy.db`.
  - **Varios mensajes de inicio por tema** en la tabla `openers` (4 por tema y 4 para la conversación libre, editables). Se elige uno al azar sin repetir el de la última sesión de ese tema. Las bases antiguas se migran solas.
- [x] **Un solo servidor Ollama.** Con el de la bandeja (11434) y el de la app (11435) cargando gemma a la vez, la VRAM llega a 16,8 GB y todo se ralentiza (el tutor pasó de 3 s a 18 s).
  - → Se queda **solo el de la app** (11435, `OLLAMA_NUM_PARALLEL=2`). `iabuddy.bat` cierra el de la bandeja al arrancar, sin tocar su configuración.
  - Con todo cargado, la VRAM total queda en 13,8 GB.
  - Ojo: `hablar_s6.bat` (spike) usaba el de la bandeja.
- [x] **«¿Qué querías decir?»** (idea de Amado, 2026-11-03): al pulsar tu burbuja aparece un menú con «✎ ¿Qué querías decir?» y «🔊 Escuchar cómo se dice». Escribes, en español o inglés, lo que intentabas decir.
  - El tutor lo compara con lo que dijiste y devuelve cómo decirlo en inglés (*Así se dice*), qué faltó y por qué, en español.
  - En modo «voz», Buddy te lo dice y te invita a repetirlo. La conversación sigue el sentido de lo que querías decir.
  - 🔊 *Escuchar* lee cualquier frase con la voz de Buddy.
  - El resumen incluye **«Frases que querías decir»** (columna `turns.intent`).
  - Solo se puede escribir **después** de hablar, para que no se convierta en traducir en vez de practicar.
- [x] Probar la Fase 2 con micrófono real. Probado por Amado el 2026-11-03: funciona bien.

### Fase 3 — Escenarios
- [x] Formato YAML y cargador de escenarios: un archivo por escenario en `backend/scenarios/` (título y objetivos en español; papel, contexto, inicios y frases útiles en inglés). Se cargan al arrancar.
- [x] 5 escenarios iniciales (entrevista backend Python, daily standup, restaurante, hotel, small talk).
- [x] Seguimiento de objetivos y evaluación final.
  - Buddy interpreta el papel. En modo «voz» empieza con un *"Quick tip:"* corto cuando cometes un error y vuelve a la escena; en «panel» y «silencioso» hace *recasting* sin salir del papel.
  - Tras cada turno tuyo, el tutor revisa los objetivos (2–4 s, encadenado tras el análisis para no pasar de 2 peticiones al LLM). Lo cumplido se marca en vivo y ya no se pierde.
  - Al terminar: objetivos con la cita que lo demuestra, 1–3 estrellas (terminarlo / la mitad / todos), un comentario en español y las frases útiles que no usaste. Se guardan los objetivos cumplidos en `sessions` para la Fase 5.
  - Probado con gemma con un guion escrito de restaurante: 4 de 4 objetivos detectados en su turno.
  - Probado de punta a punta con voz (grabaciones del dataset por `/ws`): transcripción, papel, objetivos, resumen (7,6 s al cerrar) y base de datos.
  - Tips en modo «voz», medidos con 8 frases con error y 8 correctas en 2 escenarios: 16/16 errores con tip y 2/16 tips inventados, ambos en frases que no encajaban en la escena. Muestra pequeña: vigilarlo al usar la app.
  - Si se cierra la pestaña sin «Terminar sesión», la sesión se cierra y se evalúa igual (antes quedaba sin cerrar y sin evaluación).
- [x] Probar la Fase 3 con micrófono real. Probado por Amado el 2026-11-03 con el daily standup: sesión cerrada con «Terminar sesión» y 3 de 4 objetivos guardados.

### Fase 4 — Pronunciación
- [x] Exportar el modelo de fonemas de S5 a ONNX (`spikes/export_wav2vec2_onnx.py`, en `C:\Models\wav2vec2-phonemes`). Da lo mismo que PyTorch (diferencia máxima 0,0003): 0,17 s por segundo de audio con 4 núcleos, 1,26 GB.
- [x] Puntuación por palabra/fonema (modo pasivo en conversación). Se analiza al terminar de hablar Buddy, para no quitarle CPU a Kokoro. Bajo tu burbuja salen como mucho 2 sonidos, con su explicación en español; el resumen trae «Sonidos para practicar». En modo silencioso solo se guarda.
- [x] Modo drill con frases propuestas y repetición de las falladas: «Practicar pronunciación» tiene 11 grupos por sonido y «Tus frases», con las que fallaste (ya corregidas). Una frase se supera sin errores claros y con claridad de al menos 25/100.
- Calibración (margen mínimo 3 nats, sin buscar errores de vocal, /z/ ni /j/ en palabras funcionales):
  - Reproduce S5: *ship* 3,5 · *three* 8,0 · *yet* 6,2 · *chair* 5,7.
  - Kokoro como voz nativa: 2 de 320 palabras marcadas (0,6 %). Kokoro diciendo la palabra del par: detecta 9 de 10 (falla *espeak/speak*). Tu voz: 36 de 296 palabras, sobre todo *the → /də/*.
  - La referencia sale de la frase entera (formas reducidas, *I live*), y para las palabras que se escriben igual y suenan distinto (*live*, *read*, *close*…) vale la que mejor encaje con el audio. Una frase no se supera si una palabra con contenido queda por debajo de 10/100: en Kokoro ninguna baja de 20; en tu voz, el 8 % baja de 10.
  - **Límites:** la «e-» de *speak/start* ya se detecta en tu voz, pero tuvo 1 falso en 33 palabras de Kokoro (*school*). Si una frase de 4 o más palabras saca menos de 15/100 no se muestra ningún aviso, porque casi seguro Whisper transcribió otra cosa: también puede ocultar errores reales. La referencia del modo pasivo es lo que entendió Whisper, así que si transcribe mal una palabra, ahí no hay nada fiable. La nota de claridad es orientativa: Kokoro da 81 de media y tú, 40-70 en frases bien dichas.
- [x] Registros para analizar las sesiones, en `data/logs` (fuera de git): `iabuddy.log` (errores del backend) y `sessions/<fecha>.jsonl` con cada evento, análisis completos, intentos correctos y errores del navegador, más el audio de cada turno en WAV (unos 32 KB por segundo; `IABUDDY_LOG_AUDIO=0` lo desactiva).
- [x] Probar la Fase 4 con micrófono real. Probado por Amado el 2026-11-03: práctica (12 lecturas) y conversación (3 turnos con resumen). Los avisos encajan con lo que oye el modelo.

### Mejoras tras las fases
- [x] Conversación en 3 columnas (Sesión · Conversación · Tutor), según `O2Conversacion.dc.html`. La maqueta incluye XP, que la app aún no tiene.
- [x] Correcciones inventadas de Buddy en conversación libre (modo voz). En 15 sesiones reales corregía en 19 de 38 turnos, y en 5 de esos el tutor no veía error. Medido con 10 frases con error, 12 correctas y 4 garabateadas por Whisper, repetidas por la variación del modelo: errores corregidos 50/50; correcciones sobre frases correctas, de 5/36 a 4/60, las 4 en *call back API*, que el tutor también marca; errores de Whisper corregidos como tuyos, de 5/12 a 1/20.
  - Una plantilla fija (*"Quick tip: we say X, not Y"*) lo empeoró a 12/36: el modelo la rellena aunque no haya error. Los escenarios la siguen usando (3/16 falsos, frente a 2/16 antes: muestra pequeña).
  - Queda sin resolver: a veces cita algo que no dijiste (*viewing* por *view*), 1 de 20.
  - Con tu voz (sesión 16, 9 turnos): ninguna corrección inventada. Buddy corrigió en 5 turnos y en los 2 sin errores del tutor no corrigió nada. Una vez adivinó una palabra mal transcrita, aunque acertó (*proponent* → *prompt*).
- [x] El tiempo de respuesta crecía durante la sesión (1.er token del LLM de 720 a 1730 ms en 9 turnos). Causa: el tutor arrancaba a la vez que Buddy y competían por la GPU. Ahora arranca cuando suena el primer audio. App completa, 14 turnos con grabaciones: 1.er token de ~1,2 s a ~0,33 s; 1.er audio, mediana de 1311 ms y estable. Con micrófono real (sesión 19, 4 turnos): 1.er audio de 0,9 a 1,7 s y 1.er token de ~0,3 s desde el 2.º turno. Una sesión larga con voz aún no se ha medido. El análisis del tutor llega algo más tarde.

### Fase 5 — Progreso
- [x] Historial de sesiones y métricas en el tiempo: pantalla «Ver mi progreso», calculada de lo que ya se guarda (minutos por día, palabras por minuto y turnos sin errores por sesión, tabla de sesiones).
- [x] Errores recurrentes y repaso de vocabulario: errores y sonidos que se repiten entre sesiones, y «Repaso» con cajas de Leitner (1, 3, 7, 21 y 60 días) con las palabras que corrigió el tutor y las frases que escribiste que querías decir.
- [x] «Repaso» con flujo propio: pista, intento, frase con su porqué y «La sabía» / «Repasarla otra vez». Las que no sabías vuelven al final de la tanda, y al terminar ves el resultado y cuándo vuelve la siguiente. Comparte el estilo de `O2Pronunciacion`, sin su puntuación por fonema.
- [x] «Practicar pronunciación» según `O2Pronunciacion`: lista de sonidos (primero los que más fallas), progreso, palabras seleccionables, fonemas esperados y «Cómo mejorarlo». Sin notas por palabra o fonema, porque la confianza del modelo no es una calificación (bien dicha, una frase da 40-70), y sin niveles ni XP.
- [x] Navegación con 5 secciones (Hoy, Conversar, Escenarios, Sonidos, Progreso). «Hoy» y «Escenarios» siguen `InicioO2` y `O2Escenarios` con datos reales; sin XP, racha, filtros ni duración, que aún no existen.
- [x] Resumen según `O2Resumen`: cabecera con estrellas, cifras de la sesión, objetivos, errores por tipo, pronunciación y botones para repetir o practicar. Sin XP ni notas por sonido; sin vocabulario «usaste / para la próxima», porque ese dato no existe.
- [x] Ajustes (versión corta de `O2Ajustes`): silencio, velocidad con voz de prueba, modo de corrección y estado de los modelos. Se guardan en la base de datos y mandan sobre `IABUDDY_SILENCE_MS` e `IABUDDY_SPEED`. Sin metas ni XP, idioma de las explicaciones (decidido: español) ni umbral de confianza (la app no decide con él).
- [x] Progreso: calendario del mes con los días practicados y gráfica de esta semana, que sustituye a la de 14 días. El calendario solo muestra si hablaste, porque aún no hay meta diaria.
- [ ] Probar la Fase 5 con tus datos reales. Falta solo el micrófono en vivo.
  - Probado el 2026-11-05 sobre una copia de tu base, con tus grabaciones del dataset como micrófono: Hoy, Progreso, Repaso, Sonidos, Escenarios, Resumen y Ajustes funcionan y las cifras cuadran.
  - Sesión larga por `/ws` (14 turnos, 4,5 min, esperando lo que dura cada respuesta): 1.er audio con mediana de 1,2 s y máximo de 1,67 s; no crece como antes (mediana de 1,19 s en los 7 primeros turnos y 1,31 s en los 7 últimos). Una sesión de 20 min sigue sin medirse.
  - Corregido: las frases del repaso salían con `?.`, y los números se juzgaban en pronunciación (eSpeak lee 2019 como *two thousand nineteen*, lo que daba un aviso falso de /θ/).
  - Sin resolver:
    - Si escribes en inglés lo que querías decir, la pista del repaso ya trae la respuesta (7 de las 8 frases de ese tipo en la primera tanda). Se queda así: decisión de Amado.
    - El error más repetido, *Did you went* (×5), venía de grabaciones de prueba: Amado lo confirmó y se borraron las sesiones 1, 6, 8 y 10 (copia en `data/iabuddy.antes-de-borrar-sesiones.db`).
    - En «Tus frases» entran palabras mal transcritas (*Wispeth*).
    - El aviso de micrófono denegado sigue visible al cambiar de sección.
    - Los minutos totales suman redondeos: 7,7 frente a 7,54 reales.
- Sin hacer, porque no está en esta fase: XP, niveles, racha, retos y logros (DISENO §7.5, pantalla `AppProgreso`). Requieren decidir la meta diaria y si se quieren.

### Fase 6 — Vocabulario
Practicar vocabulario hablando y usar las palabras nuevas en una conversación real (decidido con Amado el 2026-11-05).
- [x] **Banco de palabras** (sección «Palabras», tabla `words`): se llena con tus frases de «¿Qué querías decir?», las correcciones del tutor (con «Esto no lo dije» para descartar fallos de Whisper), las palabras que pulses en una burbuja de Buddy y los paquetes de `backend/vocabulary/packs.yaml` (17 paquetes, uno por tema y escenario, más «General»). «Repaso» pasa de «Sonidos» a «Palabras».
- [x] **Misión de palabras:** 4 palabras por sesión (2 de tu banco que toquen hoy y el resto nuevas del tema). Buddy te da ocasiones de usarlas, se marcan en vivo al decirlas y cuentan como acierto en el repaso. El resumen trae «Usaste» y «Para la próxima». No usarlas no castiga: vuelven otro día.
  - Una corrección solo entra en una misión si ya la respondiste en el repaso: la mitad de las que había eran fallos de Whisper.
  - Probado el 2026-11-05 sobre una copia de tu base, con Whisper y gemma reales y la voz de Kokoro como micrófono (2 turnos): detectó *deadline*, *in charge of* y *fell behind*, y Buddy sacó *workload* por su cuenta. Guardar una palabra del chat tardó 1 s.
  - **Falta:** probarlo con tu micrófono, y medir si la línea de la misión en el prompt cambia cuánto corrige Buddy.
  - **Límites:** una forma irregular que falte en `forms` no se detecta. «Esto no lo dije» saca la corrección del repaso y del banco, pero sigue contando en los errores repetidos de «Progreso». En la lista de «Palabras» no hay botón de escuchar, porque la voz necesita una sesión abierta.
- [x] **Dilo en inglés** (dentro de «Repaso»): ves el significado o lo que dijiste mal y dices una frase con la palabra, de memoria. Si Whisper la encuentra, sale «¡La usaste!» y cuenta como acierto; si no, ves lo que oyó y puedes reintentar o mirar la frase. Vale para lo de 4 palabras o menos, y hace falta una frase de al menos 3 palabras. Lo más largo, o si Whisper no responde, sigue con «La sabía».
  - Probado el 2026-11-05 sobre una copia de tu base, con Whisper real y la voz de Kokoro como micrófono: acierta con *deadline* y *ran out of*, rechaza una palabra suelta y una frase sin la palabra.
  - **Falta:** probarlo con tu micrófono. Si Whisper no oye bien la palabra, «La sabía» sigue disponible tras ver la frase.
  - **Límites:** comprueba que la palabra aparece, no que esté bien usada (eso es «Tu propia frase»). Si escribiste en inglés lo que querías decir, la pista sigue dando la respuesta, como ya pasaba en el repaso.
- [x] **Tu propia frase** (botón en «Palabras»): tandas de 5 palabras al azar con la palabra a la vista. Inventas una frase, Whisper comprueba que la dijiste y el tutor dice si la usaste bien, por qué y cómo queda corregida. No mueve las cajas del repaso: con la palabra delante no demuestra que la recuerdes. Las frases no se guardan.
  - Medido el 2026-11-05 con gemma, con frases que escribí yo, 3 veces cada una: 30/30 bien usadas aceptadas (incluidas 2 con errores fuera de la palabra) y 24/24 mal usadas detectadas. Mediana de 1,3 s. Muestra pequeña y sin habla real: vigilarlo con tus frases.
  - Probado en la app sobre una copia de tu base, con Whisper y gemma reales y la voz de Kokoro como micrófono.
  - **Falta:** probarlo con tu micrófono.
  - **Límites:** a veces el comentario o la corrección suenan raros cuando la frase no tiene arreglo (*My brother is very stale* → *My brother's information is very stale*). Whisper puede haber oído mal: por eso se muestra «Te oí».
- [x] **Buddy adivina** (botón en «Palabras»): partidas de 5 palabras de tu banco, de 3 palabras como mucho. Las describes por voz sin decirlas y Buddy, que no las conoce, intenta adivinarlas: acierta si su respuesta contiene la palabra. Si la dices tú, no vale y Buddy no llega a oírla. Se puede pasar de palabra, o dar por buena una respuesta que casi acierta («Casi: ¡la adivinó!»). El tutor sigue revisando tus turnos en el panel y la sesión cuenta en «Progreso», pero no mueve las cajas del repaso.
  - Medido el 2026-11-05 con gemma, con descripciones que escribí yo, 3 veces cada una: adivinó las 30 de 30 (27 a la primera), y gemma tarda unos 0,4 s en escribir cada respuesta, sin contar Whisper ni la voz. Son descripciones claras: con las tuyas costará más.
  - Probado en la app sobre una copia de tu base, con Whisper y gemma reales y la voz de Kokoro como micrófono: palabra dicha rechazada, *deadline* adivinada, palabra pasada, resumen y título en «Progreso».
  - **Falta:** probarlo con tu micrófono.
  - **Límites:** Buddy puede nombrar la palabra sin querer en una pregunta y contaría como acierto; no se ha medido cuánto pasa. Una respuesta casi correcta (*run out* por *run out of*) no cuenta sola: para eso está el botón.
- [x] **Conversación guiada** (sección «Guiada» del menú; idea de Amado, 2026-11-05): un diálogo escrito en el YAML del escenario. Buddy dice su parte, ves la frase que te toca con su traducción, la dices y lleva nota. Se puede repetir y vale la mejor. Al final: nota total, 1–3 estrellas (90 y 75 %), la nota de cada frase y «Ahora sin guion» para pasar al escenario libre. No usa Ollama.
  - **La nota** es el % de palabras bien dichas: 0 si Whisper no la oyó, la mitad si tiene un error claro de sonido o no se oyó con claridad. No usa la confianza del modelo, porque bien dicha una frase da 40-70. Se compara cómo suena cada palabra, porque Whisper no distingue *by* de *buy*.
  - Medido el 2026-11-05: Kokoro leyendo los 29 turnos de los diálogos saca 96-100. Tus 28 grabaciones del dataset, contra lo que dijiste: mediana de 86 (11 con 90 o más, 12 entre 70 y 89, 5 por debajo). Contra la frase correcta, tus errores restan: *go* por *went* da 88.
  - Probado en la app sobre una copia de tu base, con Whisper real y la voz de Kokoro como micrófono: el diálogo del restaurante entero, con una frase equivocada (71 %) y su repetición (100 %).
  - **Falta:** probarlo con tu micrófono, y ver si las notas se sienten justas.
  - **Límites:** Whisper a veces arregla lo que dijiste, o entiende otra cosa aunque se te entienda (*He explained me* → *Please play meet*: 30 %). La nota mide leer en voz alta, no improvisar. Los errores de sonido de estas frases también entran en «Sonidos».
- [x] **Mismo subrayado en toda la app** (pedido de Amado, 2026-11-05): verde lo que está bien, ondulado lo que hay que revisar, punteado lo que no se oyó con claridad. Se usa en tus burbujas, el panel del tutor, el historial y el final de la conversación guiada, el repaso, «Palabras», «Hoy», «Progreso» y el resumen. Sustituye al tachado y al resaltado de `O2Conversacion` y `O2Resumen`.
- [x] **Lo que hay que practicar se ve de un vistazo** (pedido de Amado, 2026-11-05): fondo lima en la palabra dentro de la frase (repaso, «Tu propia frase» y las palabras que fallaste en «Tus frases», también tras leer), la palabra sola en grande y la pista más grande. En las frases por sonido de «Sonidos» se destacan las palabras donde se buscan esos errores, calculadas con eSpeak.
- [x] **Práctica centrada** (pedido de Amado, 2026-11-05): en Repaso, «Tu propia frase», «Sonidos» y Guiada, las palabras y frases van centradas a lo ancho; en las tres primeras, también a lo alto. En Guiada, el panel tiene el alto justo y la conversación se ve encima. Todos esos textos, y los de Hoy, Escenarios, el panel de la sesión y el del tutor, salen de un solo componente, `LabeledText`.
- Siempre con frases completas: Whisper falla mucho con palabras sueltas. Un acierto significa «la usaste», no que la hayas dicho perfecta.
- Sin hacer por ahora: XP y rachas, listas de frecuencia descargadas y las palabras que repites demasiado (con 69 turnos hay pocos datos).

---

## 5. Orden sugerido para cerrar lo que bloquea

1. ~~Decidir 1.1 (entorno) y 1.2 (audio)~~ ✅
2. ~~Diseño de la UI~~ ✅ — 7 pantallas con gamificación, guardadas en [docs/ui/](docs/ui/README.md).
3. ~~Preparación del entorno (sección 2)~~ ✅
4. ~~Grabar el dataset (3.1)~~ ✅
5. ~~Ejecutar los spikes y cerrar 1.4 con datos~~ ✅ ([docs/SPIKES.md](docs/SPIKES.md)).
6. Arrancar la **Fase 1**. Las decisiones 1.3, 1.5 y 1.6 se pueden tomar durante la Fase 1.
