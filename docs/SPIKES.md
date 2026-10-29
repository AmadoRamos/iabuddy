# Spikes — Fase 0

Resultados de los spikes de validación ([TODO §3.2](../TODO.md)). Equipo: Windows 11, RX 9070 (16 GB) y driver 26.10.1.

---

## S1 — STT literal (2026-10-28)

**Pregunta:** ¿qué STT transcribe lo que *dices*, con tus errores, en lugar de corregirlo?

**Criterio:** conserva ≥ 80 % de los errores y tarda < 500 ms por frase corta.

### Montaje
| Sistema | Ejecución | Notas |
|---|---|---|
| `whisper-turbo` | whisper.cpp v1.9.5, `ggml-large-v3-turbo`, **GPU por Vulkan**, `whisper-server` (HTTP) | `temperature=0`, `-l en` |
| `whisper-turbo+prompt` | igual, con un *initial prompt* que contiene errores (*"so I goes… he don't know nothing"*) | Prueba si sesgarlo hacia el inglés no nativo ayuda |
| `parakeet-tdt-v2` | Parakeet TDT 0.6B v2, ONNX fp32 por `onnx-asr` 0.12, **CPU** | |
| `whisper-v3` | igual que turbo, con `ggml-large-v3` (sin turbo: decodificador de 32 capas en vez de 4) | 2.ª ronda |
| `…+beam5` | turbo / v3 con `whisper-server -bs 5` (beam search) | 2.ª ronda |
| `whisper-v3-q5_0` | `ggml-large-v3-q5_0` (v3 cuantizado, 1 GB en disco) | 3.ª ronda, para liberar VRAM (ver S2) |

Dataset: 28 frases con errores (`e*`), 24 palabras de pares mínimos (`p*`) y 4 grabaciones libres (`f*`, 98 s en total). Todas son de Amado y están en `data/dataset/`.

Script: [spikes/s1_stt.py](../spikes/s1_stt.py). Qué error tiene cada frase y cuál sería su forma corregida está en [spikes/s1_errors.csv](../spikes/s1_errors.csv).

Cada transcripción de una frase se clasifica así:
- **conserva:** aparece el error tal cual.
- **corrige:** aparece la forma corregida.
- **otro:** el STT entendió otra cosa en esa zona, por pronunciación o por audio.

### Resultados
| Sistema | WER frases | WER libre | Errores conservados | Corregidos | Otro | Pares OK | Latencia frase (mediana / p90) | RTF libre |
|---|---|---|---|---|---|---|---|---|
| **whisper-v3-q5_0** | **14,4 %** | 22,4 % | **19/28 (68 %)** | **3** | 6 | **8/24** | 170 / 231 ms | 0,024 |
| whisper-v3 | 16,1 % | 22,4 % | 19/28 (68 %) | 3 | 6 | 8/24 | 159 / 170 ms | 0,018 |
| whisper-v3+beam5 | 17,8 % | 18,1 % | 18/28 (64 %) | 3 | 7 | 7/24 | 206 / 314 ms | 0,027 |
| whisper-turbo | 17,2 % | 19,0 % | 15/28 (54 %) | 6 | 7 | 8/24 | 94 / 107 ms | 0,008 |
| whisper-turbo+beam5 | 17,2 % | 19,8 % | 15/28 (54 %) | 6 | 7 | 8/24 | 126 / 169 ms | 0,016 |
| whisper-turbo+prompt | 16,7 % | 18,1 % | 15/28 (54 %) | 7 | 6 | 8/24 | 98 / 104 ms | 0,008 |
| parakeet-tdt-v2 | 27,2 % | 23,3 % | 13/28 (46 %) | 5 | 10 | 5/24 | 180 / 235 ms | 0,046 |

Las latencias de whisper son de la 2.ª ronda, con los cinco sistemas medidos en las mismas condiciones. En la 1.ª ronda turbo dio 157 ms.

Si se ignoran los casos "otro" (que dependen de la pronunciación más que del modelo), los errores conservados quedan así:

| Sistema | Errores conservados (sin "otro") | Criterio ≥ 80 % |
|---|---|---|
| **whisper-v3 / v3-q5_0** | **19/22 (86 %)** | ✅ |
| whisper-turbo | 15/21 (71 %) | ❌ |
| Parakeet | 13/18 (72 %) | ❌ |

### Lectura
0. **2.ª ronda: `large-v3` (sin turbo) corrige mucho menos.** Conserva *arrived to*, *explain me*, *said me* y *used to work*, que turbo normalizaba.
   - Solo corrige tres errores: *interested on* → *in*, *Is very important* → *It's*, y *informations* → *information* (aunque deja *are*).
   - La latencia sigue siendo de unos 160 ms por frase.
   - En habla libre empeora un poco (22 % frente a 19 % de WER): se come el *"A normal day"* inicial de f01 y entiende mal *FastAPI*. Con 4 grabaciones, son unas 4 palabras de diferencia.
   - **Beam search no ayuda** en ninguno de los dos modelos: es igual o peor y más lento.

   **3.ª ronda: `large-v3-q5_0` da los mismos resultados que v3.** Conserva los mismos errores, tiene algo menos de WER en frases y la misma latencia (medida lado a lado). A cambio, ocupa **1,8 GB de VRAM frente a 3,8 GB** (medido con el contador de Windows, con el servidor cargado).

   Los puntos siguientes son de la 1.ª ronda (turbo frente a Parakeet).
1. **Whisper gana en todo lo medible:** menor WER, más errores conservados, más pares acertados y menor latencia. Parakeet en CPU no compensa: tiene más WER, alucina más con la pronunciación (e04 *"Ayanagli Queenju"*, e10 *"Ion is the rest of its own…"*) y es 4 veces más lento en audio largo.
2. **La latencia sobra:** unos 100–160 ms por frase corta en GPU, frente a los 500 ms del criterio.
3. **El criterio de errores no se cumple.** Whisper normaliza siempre ciertos errores:
   - **artículos:** *a engineer* → *an engineer*;
   - **plural incontable:** *informations are* → *information is*;
   - **preposición tras verbo:** *interested on* → *in*, *arrived to* → *at*, *explain me* → *explain to me*;
   - **sujeto omitido:** *Is very important* → *It's very important*.

   En cambio, conserva bien los errores de tiempos y concordancia: *she don't*, *didn't went*, *did you went*, *there is many*, *when I will arrive*, *have been in London last year*, *more taller*, *want that you*.
4. **El prompt no cambia la cantidad de errores conservados.** Arregla e21 (*said me*) pero estropea e18 (*Did you go to the bathroom?*). Que salga más rápido seguramente se debe al orden de ejecución (caché caliente), no al prompt.
5. **Pares mínimos:** un STT de palabras no sirve para esto. Ambos eligen la palabra real más probable (*very* → *Ready?*, *cat/cut* → *God/Could*). Para la pronunciación (S5) hace falta el modelo de fonemas, como ya preveía el diseño.
6. **Algunas frases las malinterpretan los tres sistemas igual** (e03 *thirty years* → *13 year*, e04, e09, e22 *used to* → *use it*). Más que un fallo del STT, son señal de pronunciación, y eso también es feedback útil.
7. **Habla libre:** en f01 los tres oyen *"If I **think** any log"* donde la referencia dice *find*. Parte del 19 % de WER en habla libre puede venir de que la referencia no es del todo literal.

### Decisión propuesta
- **STT: whisper.cpp `large-v3-q5_0` en GPU (Vulkan), greedy, sin prompt.** Es la misma precisión que v3, que es el único que cumple el criterio de errores. Tarda unos 170 ms por frase y ocupa unos 1,8 GB de VRAM, lo que permite que quepa con gemma4 (ver S2).
- **Integración: proceso aparte con `whisper-server` (HTTP).** Funciona y evita compilar bindings de Python.
- **Consecuencia para el tutor (Fase 2):** aun con v3, el STT puede normalizar preposiciones regidas (*interested on*), sujetos omitidos (*Is very important*) y plurales incontables. El tutor no debe dar por hecho que la transcripción recoge todos los errores.

Detalle por frase: `data/s1/results.csv` (local, no está en el repo).

---

## S2 — LLM (2026-10-28)

**Pregunta:** ¿qué LLM de 8–14B responde lo bastante rápido como compañero, incluso cuando el tutor está usando la GPU a la vez, y cabe junto a whisper?

**Criterio:** primer token < 500 ms y ≥ 30 tok/s con el tutor activo. VRAM total ≤ 13 GB ([diseño](DISENO.md)).

### Montaje
- Ollama 0.40.12 en GPU por **ROCm**. Para el spike se levantó un `ollama serve` aparte con `OLLAMA_NUM_PARALLEL=2` y `num_ctx` 4096.
- whisper-server con `large-v3` cargado durante toda la prueba, para medir la VRAM real de todo el stack.
- **Compañero:** prompt de persona B1–B2 que pide *recasting* (corregir usando la forma correcta en la respuesta, sin explicar), con 3 turnos de historial previo y *streaming*.
- **Tutor:** salida JSON con esquema (`original`, `correction`, `type`, `explanation_es`).
- Turnos del usuario: las 6 primeras frases con errores del dataset (`e01`–`e06`). Cada modelo hace 6 peticiones en solitario y 6 con el tutor ya generando 300 ms antes.
- Script: [spikes/s2_llm.py](../spikes/s2_llm.py).

### Resultados (medianas)
| Modelo | VRAM modelo / total | TTFT solo | 1.ª frase solo | tok/s solo | **TTFT con tutor** | **1.ª frase con tutor** | **tok/s con tutor** | Tutor (total) | JSON tutor válido |
|---|---|---|---|---|---|---|---|---|---|
| gemma4:12b-it-qat | 8,6 / **15,7 GB** | 142 ms | 281 ms | 62 | **266 ms** ✅ | 502 ms | **46** ✅ | 2,0 s | 6/6 |
| qwen3.5:9b | 5,6 / 13,3 GB | 127 ms | 226 ms | 74 | **1.495 ms** ❌ | 1.676 ms | 65 | 1,6 s | 6/6 |
| llama3.1:8b | 5,9 / 12,8 GB | 32 ms | 142 ms | 96 | **53 ms** ✅ | 156 ms | **68** ✅ | 0,9 s | 6/6 |

Reparto de VRAM: escritorio y otras apps ≈ 2,8 GB, whisper `large-v3` ≈ 3,8 GB, y el LLM lo indicado en la tabla.

**2.ª ronda: gemma4 con whisper `large-v3-q5_0`** (sale de S1, con unos 1,8 GB de VRAM):

| Modelo | VRAM modelo / total | TTFT solo | 1.ª frase solo | tok/s solo | TTFT con tutor | 1.ª frase con tutor | tok/s con tutor | Tutor | JSON |
|---|---|---|---|---|---|---|---|---|---|
| gemma4:12b-it-qat | 8,6 / **14,1 GB** | 138 ms | 294 ms | 64 | **248 ms** ✅ | **403 ms** ✅ | **50** ✅ | 2,0 s | 6/6 |

El stack de la app (whisper 1,8 GB y gemma 8,6 GB) ocupa **10,4 GB, dentro del presupuesto de 13 GB** ✅. Con el escritorio, el total es de 14,1 de 16 GB, unos 2 GB libres.

### Calidad (revisión manual de las respuestas)
| | Compañero (*recasting*) | Tutor |
|---|---|---|
| **gemma4 12B** | ✅ Hace *recasting* de forma natural: *"You **went** to the office very early yesterday!"*, *"You're thirty years old now"*, *"you've been working there since 2019"*. | ✅ Detecta bien *go → went*, *have → am thirty*, *am working → have been working*. Mete algo de ruido (*since → since*). |
| qwen3.5 9B | ⚠️ A veces no hace *recasting* (e01 cambia de tema). | ❌ Se inventa errores (*"to"* no aparece en la frase) y da correcciones idénticas al original. |
| llama3.1 8B | ❌ No hace *recasting*: responde al tema sin modelar la forma correcta. | ❌ Se le escapa *am working since*, duplica *go → went* y explica de forma pobre. |

### Lectura
1. **qwen3.5 no procesa en paralelo:** con el tutor activo, el compañero espera a que el tutor termine (TTFT de unos 1,5 s ≈ duración del tutor). Probablemente su arquitectura de atención híbrida no admite varios slots en Ollama. Queda descartado.
2. **llama3.1 es el más rápido con diferencia,** pero su calidad pedagógica es la peor. No compensa, porque gemma también cumple la latencia.
3. **gemma4 12B cumple la latencia con el tutor activo:**
   - 266 ms de TTFT y 46 tok/s;
   - la primera frase completa tarda unos 500 ms, en el límite de los 300–500 ms del diseño;
   - es el único que hace bien tanto de compañero como de tutor.
4. **El problema de gemma4 es la VRAM:** 15,7 GB de 16. Cabe entera en GPU (49/49 capas), pero sin margen y por encima del presupuesto de 13 GB.

### Decisión propuesta
- **LLM: `gemma4:12b-it-qat`, un único modelo para compañero y tutor,** con `OLLAMA_NUM_PARALLEL=2`. Cierra "un modelo o dos".
- **La VRAM queda resuelta usando whisper `large-v3-q5_0`** (2.ª ronda). Si en el futuro hiciera falta más margen, hay otras palancas:
  - *KV cache* en `q8_0` (`OLLAMA_KV_CACHE_TYPE`);
  - bajar `num_ctx`.

---

## S3 — TTS (2026-10-28)

**Pregunta:** ¿Kokoro en CPU genera el primer audio del compañero lo bastante rápido?

**Criterio:** < 200 ms para una frase de unas 10 palabras.

### Montaje
- `kokoro-onnx` 0.6.1, modelos v1.0 (fp32 de 310 MB e int8 de 88 MB) en `C:\Models\kokoro`, voz `af_heart` y `en-us`.
- CPU: Ryzen 7 5800XT (8 núcleos).
- 5 frases cortas típicas de la primera frase del compañero, repetidas 3 veces.
- Script: [spikes/s3_tts.py](../spikes/s3_tts.py).

### Resultados
| Variante | Frase de ~10 palabras (mediana / máx) | Trozo de 1–6 palabras (mediana / máx) | RTF |
|---|---|---|---|
| fp32, CPU | 644 / 685 ms | **372 / 446 ms** | 0,23 |
| int8, CPU | 574 / 599 ms | — | 0,21 |
| fp32, GPU con DirectML (`onnxruntime-directml` 1.24) | ❌ falla al ejecutar | | |

### Lectura
1. **No cumple el criterio de 200 ms.** Una frase de ~10 palabras (unos 2,7 s de audio) tarda unos 650 ms.
2. **Kokoro tiene un coste fijo de unos 250–300 ms por llamada en CPU.** Por eso, aunque se corte el texto en trozos de 1–6 palabras (hasta la primera coma o el primer punto), no baja de unos 370 ms.
3. **int8 apenas gana:** un 10 % más rápido. No compensa el riesgo de perder calidad de voz.
4. **DirectML no sirve:** ONNX Runtime falla dentro del modelo, probablemente por una operación que no soporta.
5. **La generación no es un cuello de botella:** con un RTF de 0,23, mientras suena una frase da tiempo de sobra a sintetizar la siguiente. El único problema es la latencia del primer audio.

### Decisión propuesta
- **TTS: Kokoro fp32 en CPU**, cortando el *primer* trozo de la respuesta en la primera coma o el primer punto (unos 370 ms). El resto, frase a frase.
- **El presupuesto que importa es el total de S6** (< 1,5 s desde el fin de tu frase): STT unos 170 ms + LLM hasta el primer trozo unos 250–400 ms + TTS unos 370 ms ≈ 0,8–0,95 s. Cabe, aunque el silencio de fin de turno se suma encima (se fija en S4).
- **Si S6 no llega:** Kokoro en GPU con PyTorch + ROCm (la opción secundaria del [diseño](DISENO.md)). Queda VRAM libre (unos 2 GB) para ello.
- **Voz y velocidad: las elige Amado de oído.** Las muestras están en `data/s3/voices/<voz>_<velocidad>.wav`: 8 voces US a 1.0 y 0.9.
