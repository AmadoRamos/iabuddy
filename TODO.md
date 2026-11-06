# TODO — IABuddy

> Referencia: [docs/DISENO.md](docs/DISENO.md) · Spikes: [docs/SPIKES.md](docs/SPIKES.md) · Última actualización: 2026-11-06
>
> Las fases 0 a 6 están construidas. Lo pendiente va primero; lo hecho se resume al final y su detalle queda en git.

---

## 1. Probar con micrófono

Revisado el 2026-11-06 con los registros de la sesión de Amado del 2026-11-05 (`data/logs/sessions/2026-11-05_*`).

| Qué | Lo que hubo | ¿Basta? |
|---|---|---|
| Conversación, resumen y tiempos (Fase 5) | Sesión 21: 12 turnos en 6,7 min. 1.er audio oído: mediana de 1,36 s y máximo de 1,68 s, sin crecer (1,36 s en los 6 primeros turnos, 1,34 s en los 6 últimos). | ✅ Sí |
| Misión de palabras: detección | 4 de 4: *to be honest*, *figure it out*, *struggled with*, *looking forward to*. | ✅ Sí |
| Dilo en inglés | 7 intentos, 3 de 3 frases logradas. 3 rechazos justos por frase corta y un fallo de Whisper que se resolvió repitiendo. | ✅ Sí |
| Conversación guiada | 1 sola frase del diálogo de la entrevista, 3 intentos (68, 75 y 64 %), sin terminar el diálogo: no hay nada en `guided_results`. Salió un error real, ya corregido: *back-end* contaba *backend* como no dicha. | ❌ No |
| Tu propia frase | Ningún intento en los registros. | ❌ No |
| Buddy adivina | Se abrió 19 s, sin ningún turno hablado. | ❌ No |

- [ ] Terminar un diálogo de la conversación guiada y ver si las notas se sienten justas.
- [ ] Probar «Tu propia frase» con unas cuantas palabras.
- [ ] Jugar una partida de «Buddy adivina» y anotar si Buddy nombra la palabra sin querer.
- [ ] Medir una sesión completa de 10 min. Lo más largo medido con micrófono son 6,7 min.
- [ ] Comprobar en una sesión de voz que Buddy señala más errores reales ahora que no conoce la misión, y que sigues usando las palabras sin que te lleve hacia ellas ([S7](docs/SPIKES.md)).

---

## 2. Deuda

### Errores
- [ ] **El tutor no marcó un error claro:** *I don't speaking about…* (sesión 21, turno 6) salió sin errores. Buddy tampoco lo señala con el historial real, ni sin la misión (1 de 6); sin historial, sí (6 de 6).
- [ ] En «Tus frases» entran palabras mal transcritas (*Wispeth*).
- [ ] El aviso de micrófono denegado sigue visible al cambiar de sección.
- [ ] Los minutos totales suman redondeos: 7,7 frente a 7,54 reales.
- [ ] «Esto no lo dije» saca la corrección del repaso y del banco, pero sigue contando en los errores repetidos de «Progreso».

### Por revisar
- [ ] **Guiada: *years* sacó 0-2 de claridad en los 3 intentos**, y *Sure* 2-3 en 2 de ellos. Son la última y la primera palabra de la frase: escuchar los WAV para ver si se corta el audio o es la pronunciación.
- [ ] **Guiada: Whisper oyó *I am* en los 3 intentos** y *I'm* quedó como no dicha. Escuchar si dijiste *I am* o si Whisper la expande; en ese caso habría que aceptar las contracciones.
- [ ] **1.er token del LLM más lento con micrófono:** 0,55-0,85 s en la sesión 21, frente a ~0,3 s en la sesión 19. Sigue cumpliendo el total salvo en 2 de 12 turnos (más de 1,5 s). Volver a medirlo: ese prompt ya no lleva la misión.
- [ ] La línea del tema elegido también va al final del prompt, como iba la misión: falta medir si reduce las correcciones.
- [ ] Buddy a veces cita algo que no dijiste (*viewing* por *view*, 1 de 20).
- [ ] Buddy adivina: Buddy puede nombrar la palabra sin querer en una pregunta y contaría como acierto.

### Código sin test que lo detecte
Revisión red/green del 2026-11-06: ya tienen test `Tutor`, `Session` (incluido `intent_failed`), `Scorer`, `backend/main.py` (`/ws`, arranque, `/api/health`), `stt.py`, `tts.py`, `vad.py` y `llm.py`. `tests/test_models.py` usa Kokoro, Silero y wav2vec2 reales (se salta sin `C:\Models`, y son ~6 s de los ~10 s de la suite). De 309 roturas automáticas de los 6 módulos más `intent_failed`, 29 no las detecta ningún test. Casi todas no cambian el comportamiento, son valores exactos en el límite o son tiempos de espera. Queda:

- [ ] Las peticiones reales a whisper-server y Ollama solo se prueban contra servidores simulados: si cambia su API, los tests no lo verán. Solo lo prueba el micrófono.
- [ ] `Scorer`, `ends[j - 1]` en `analyze`: si el final de la palabra se calcula mal, ningún test lo nota, salvo con un último sonido muy largo.

### Límites aceptados
Sin acción prevista; se revisan solo si molestan.
- Una sesión vieja con algún turno sin analizar se queda para siempre, porque nada vuelve a analizarla: si el tutor falló, si Buddy no llegó a sonar o si faltaba el modelo de fonemas. Hoy son 0 de 23.
- Si escribes en inglés lo que querías decir, la pista del repaso ya trae la respuesta. Decisión de Amado.
- Una forma irregular que falte en `forms` no se detecta en la misión.
- En la lista de «Palabras» no hay botón de escuchar: la voz necesita una sesión abierta.
- Dilo en inglés comprueba que la palabra aparece, no que esté bien usada (eso es «Tu propia frase»). Un acierto significa «la usaste», no que la hayas dicho perfecta.
- Tu propia frase: a veces el comentario suena raro cuando la frase no tiene arreglo.
- Guiada: Whisper a veces arregla lo que dijiste o entiende otra cosa. La nota mide leer en voz alta, no improvisar.
- Pronunciación: la nota de claridad es orientativa (Kokoro saca 81 de media; tú, 40-70 en frases bien dichas). En frases de 4 o más palabras con menos de 15/100 no se muestra ningún aviso, lo que puede ocultar errores reales. En modo pasivo la referencia es lo que entendió Whisper. La «e-» de *speak/start* dio 1 falso en 33 palabras de Kokoro.

---

## 3. Fase 7 — Gamificación y ampliaciones

Aplazado a propósito hasta ahora.

- [ ] Decidir si se quiere gamificación y cuál sería la meta diaria: lo demás de esta lista depende de eso.
- [ ] XP y niveles (DISENO §7.5, pantalla `AppProgreso`).
- [ ] Racha, retos y logros.
- [ ] Vocabulario: listas de frecuencia descargadas.
- [ ] Vocabulario: las palabras que repites demasiado, cuando haya más datos (con 69 turnos eran pocos).

---

## 4. Decisiones tomadas

- **Entorno:** Windows 11 nativo, Python 3.12 con `uv`. Repositorio público con licencia MIT. Modelos en `C:\Models` (`IABUDDY_MODELS_DIR`), fuera del repo. whisper.cpp v1.9.5 compilado con Vulkan en `C:\Tools\whisper.cpp`, porque no hay binario oficial para Windows.
- **Voz:** audífonos. Espacio abre y cierra tu turno e interrumpe a Buddy. Silencio de 900 ms con fusión de turno. Acento US, Kokoro `af_heart` a 0,9×.
- **Modelos** ([spikes](docs/SPIKES.md)): whisper `large-v3-q5_0` por Vulkan con `whisper-server`, y `gemma4:12b-it-qat` para compañero y tutor.
- **Un solo servidor Ollama:** el de la app (puerto 11435, `OLLAMA_NUM_PARALLEL=2`). `iabuddy.bat` cierra el de la bandeja, porque con los dos cargados la VRAM llega a 16,8 GB y todo se ralentiza.
- **Pedagogía:** Buddy es fijo, amigo e instructor. Modo por defecto: en voz. Buddy habla en inglés y señala 1 o 2 errores dentro de su respuesta; el tutor registra todos por escrito (gramática, vocabulario, naturalidad y estilo) y los explica en español. En «panel» y «silencioso», Buddy solo hace *recasting*.
- **Temas:** lista sugerida, editable en la base de datos.
- **Frontend:** React + Vite, solo en `127.0.0.1`. FastAPI sirve el build.
- **Sesión típica: 10 min** (Amado, 2026-11-06). No hace falta resumir el historial: se estiman ~850 tokens de conversación más el prompt, dentro de `num_ctx` 4096.
- **Misión:** Buddy no conoce sus palabras (Amado, 2026-11-06). Con ellas en el prompt dejaba pasar tus errores e inventaba correcciones ([S7](docs/SPIKES.md)).
- **Retención del audio** (Amado, 2026-11-06): se guarda. Al arrancar se borran el `.wav` y el `.jsonl` de las sesiones de más de 30 días ya analizadas (`prune_sessions` en `backend/session_log.py`). Las filas de `data/iabuddy.db` se quedan, porque de ellas leen «Progreso», «Repaso» y «Palabras».

---

## 5. Hecho

- **Fase 0:** dataset propio de 56 grabaciones (`data/dataset/`) y spikes S1-S6.
- **Fase 1, loop de voz:** VAD, STT, LLM y TTS con barge-in, fusión de turno, descarte de turnos sin voz y panel de tiempos. `iabuddy.bat` lo arranca todo.
- **Fase 2, feedback:** tutor asíncrono, panel, resumen de sesión, SQLite y «¿Qué querías decir?».
- **Fase 3, escenarios:** 5 escenarios en YAML con objetivos, tips y evaluación final.
- **Fase 4, pronunciación:** wav2vec2 en ONNX, avisos por sonido, práctica por grupos y «Tus frases», registros en `data/logs`.
- **Fase 5, progreso:** «Hoy», «Progreso» con calendario, «Repaso» con cajas de Leitner, «Sonidos», resumen y ajustes.
- **Fase 6, vocabulario:** banco de palabras y paquetes, misión de 4 palabras, Dilo en inglés, Tu propia frase, Buddy adivina y conversación guiada. Mismo subrayado en toda la app y práctica centrada.
