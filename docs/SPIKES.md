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

Dataset: 28 frases con errores (`e*`), 24 palabras de pares mínimos (`p*`) y 4 grabaciones libres (`f*`, 98 s en total). Todas son de Amado y están en `data/dataset/`.

Script: [spikes/s1_stt.py](../spikes/s1_stt.py). Qué error tiene cada frase y cuál sería su forma corregida está en [spikes/s1_errors.csv](../spikes/s1_errors.csv).

Cada transcripción de una frase se clasifica así:
- **conserva:** aparece el error tal cual.
- **corrige:** aparece la forma corregida.
- **otro:** el STT entendió otra cosa en esa zona, por pronunciación o por audio.

### Resultados
| Sistema | WER frases | WER libre | Errores conservados | Corregidos | Otro | Pares OK | Latencia frase (mediana / p90) | RTF libre |
|---|---|---|---|---|---|---|---|---|
| **whisper-v3** | **16,1 %** | 22,4 % | **19/28 (68 %)** | **3** | 6 | **8/24** | 159 / 170 ms | 0,018 |
| whisper-v3+beam5 | 17,8 % | 18,1 % | 18/28 (64 %) | 3 | 7 | 7/24 | 206 / 314 ms | 0,027 |
| whisper-turbo | 17,2 % | 19,0 % | 15/28 (54 %) | 6 | 7 | 8/24 | 94 / 107 ms | 0,008 |
| whisper-turbo+beam5 | 17,2 % | 19,8 % | 15/28 (54 %) | 6 | 7 | 8/24 | 126 / 169 ms | 0,016 |
| whisper-turbo+prompt | 16,7 % | 18,1 % | 15/28 (54 %) | 7 | 6 | 8/24 | 98 / 104 ms | 0,008 |
| parakeet-tdt-v2 | 27,2 % | 23,3 % | 13/28 (46 %) | 5 | 10 | 5/24 | 180 / 235 ms | 0,046 |

Las latencias de whisper son de la 2.ª ronda, con los cinco sistemas medidos en las mismas condiciones. En la 1.ª ronda turbo dio 157 ms.

Si se ignoran los casos "otro" (que dependen de la pronunciación más que del modelo), los errores conservados quedan así:

| Sistema | Errores conservados (sin "otro") | Criterio ≥ 80 % |
|---|---|---|
| **whisper-v3** | **19/22 (86 %)** | ✅ |
| whisper-turbo | 15/21 (71 %) | ❌ |
| Parakeet | 13/18 (72 %) | ❌ |

### Lectura
0. **2.ª ronda: `large-v3` (sin turbo) corrige mucho menos.** Conserva *arrived to*, *explain me*, *said me* y *used to work*, que turbo normalizaba.
   - Solo corrige tres errores: *interested on* → *in*, *Is very important* → *It's*, y *informations* → *information* (aunque deja *are*).
   - La latencia sigue siendo de unos 160 ms por frase.
   - En habla libre empeora un poco (22 % frente a 19 % de WER): se come el *"A normal day"* inicial de f01 y entiende mal *FastAPI*. Con 4 grabaciones, son unas 4 palabras de diferencia.
   - **Beam search no ayuda** en ninguno de los dos modelos: es igual o peor y más lento.

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
- **STT: whisper.cpp `large-v3` (sin turbo) en GPU (Vulkan), greedy, sin prompt.** Es el único que cumple el criterio de errores, con unos 160 ms por frase.
  - Ocupa más VRAM que turbo (unos 3 GB frente a unos 1,6 GB).
  - En S2 hay que comprobar que convive con el LLM. Si no cabe, se vuelve a turbo.
- **Integración: proceso aparte con `whisper-server` (HTTP).** Funciona y evita compilar bindings de Python.
- **Consecuencia para el tutor (Fase 2):** aun con v3, el STT puede normalizar preposiciones regidas (*interested on*), sujetos omitidos (*Is very important*) y plurales incontables. El tutor no debe dar por hecho que la transcripción recoge todos los errores.

Detalle por frase: `data/s1/results.csv` (local, no está en el repo).
