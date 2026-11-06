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
| Conversación guiada | 1 sola frase del diálogo de la entrevista, 3 intentos (68, 75 y 64 %), sin terminar el diálogo: no hay nada en `guided_results`. Salió un error real, ver Deuda. | ❌ No |
| Tu propia frase | Ningún intento en los registros. | ❌ No |
| Buddy adivina | Se abrió 19 s, sin ningún turno hablado. | ❌ No |

- [ ] Terminar un diálogo de la conversación guiada y ver si las notas se sienten justas.
- [ ] Probar «Tu propia frase» con unas cuantas palabras.
- [ ] Jugar una partida de «Buddy adivina» y anotar si Buddy nombra la palabra sin querer.
- [ ] Medir una sesión completa de 10 min. Lo más largo medido con micrófono son 6,7 min.

---

## 2. Retención del audio

Decidido por Amado el 2026-11-06: se guarda el audio y las sesiones viejas se borran cuando su audio ya esté analizado.

Hoy el audio ya se guarda (`data/logs/sessions/<fecha>/*.wav`, 18 MB en total), pero nunca se borra nada.

- [ ] Decidir desde cuántos días una sesión es «vieja».
- [ ] Decidir qué se borra. Propuesta: solo el `.wav` y el `.jsonl`, porque «Progreso», «Repaso» y «Palabras» leen de `data/iabuddy.db`, y borrar esas filas los dejaría sin historial.
- [ ] Implementarlo. «Analizado» puede comprobarse en el `.jsonl`: cada turno deja `pronunciation_analysis` y `tutor`.

---

## 3. Deuda

### Errores
- [ ] **Guiada: una palabra con guion cuenta como no dicha.** Whisper oyó *back-end*, y *backend* quedó con 0 puntos. `grade_reading` en `backend/pronunciation/scorer.py` separa por el guion: comprobado, la misma frase da 80 con guion y 100 sin él.
- [ ] **Buddy inventó una corrección y dejó pasar las reales** (sesión 21, modo voz). Corrigió una sola vez en 12 turnos, y fue para decirte que dijeras justo lo que habías dicho (*I struggled with that theme*). El tutor marcó 5 errores en los turnos 2 y 11, y Buddy no corrigió ninguno. En la sesión 16, sin misión, corrigió en 5 de 9 turnos. Puede ser la línea de la misión en el prompt: falta medirlo.
- [ ] **El tutor no marcó un error claro:** *I don't speaking about…* (sesión 21, turno 6) salió sin errores.
- [ ] En «Tus frases» entran palabras mal transcritas (*Wispeth*).
- [ ] El aviso de micrófono denegado sigue visible al cambiar de sección.
- [ ] Los minutos totales suman redondeos: 7,7 frente a 7,54 reales.
- [ ] «Esto no lo dije» saca la corrección del repaso y del banco, pero sigue contando en los errores repetidos de «Progreso».

### Por revisar
- [ ] **Guiada: *years* sacó 0-2 de claridad en los 3 intentos**, y *Sure* 2-3 en 2 de ellos. Son la última y la primera palabra de la frase: escuchar los WAV para ver si se corta el audio o es la pronunciación.
- [ ] **Guiada: Whisper oyó *I am* en los 3 intentos** y *I'm* quedó como no dicha. Escuchar si dijiste *I am* o si Whisper la expande; en ese caso habría que aceptar las contracciones.
- [ ] **1.er token del LLM más lento con micrófono:** 0,55-0,85 s en la sesión 21, frente a ~0,3 s en la sesión 19. Sigue cumpliendo el total salvo en 2 de 12 turnos (más de 1,5 s). Comprobar si es por el prompt con la misión.
- [ ] Buddy a veces cita algo que no dijiste (*viewing* por *view*, 1 de 20).
- [ ] Buddy adivina: Buddy puede nombrar la palabra sin querer en una pregunta y contaría como acierto.

### Código sin test que lo detecte
Revisión red/green del 2026-11-06: los 113 tests se vieron en rojo por una razón válida y en verde, y se corrigieron 3 que probaban menos de lo que decían. De 1170 roturas automáticas del backend, 400 no las detectó ningún test (algunas no cambian el comportamiento) y 49 colgaron la ejecución. Por orden de riesgo:

- [ ] `Scorer` en `backend/pronunciation/scorer.py`: el análisis real de pronunciación. Los tests usan `FakeScorer`.
- [ ] `Tutor` en `backend/tutor/tutor.py`: `analyze`, `define_word` y `check_usage`, que decide el veredicto de «Tu propia frase».
- [ ] `Session` en `backend/pipeline/turn_manager.py`:
  - que `finish_mission` se llame al terminar: sin él, las palabras usadas no cuentan en el repaso;
  - que se guarde el turno de Buddy;
  - el aviso `error` cuando falla la respuesta;
  - el descarte cuando Whisper no devuelve texto;
  - que un ruido corto no reabra el turno (`RESUME_FRAMES`).
- [ ] `backend/main.py`: el bucle de `/ws`, el arranque y `/api/health`.
- [ ] `stt.py`, `tts.py`, `vad.py` y las peticiones reales de `llm.py` en `backend/pipeline/`.

### Límites aceptados
Sin acción prevista; se revisan solo si molestan.
- Si escribes en inglés lo que querías decir, la pista del repaso ya trae la respuesta. Decisión de Amado.
- Una forma irregular que falte en `forms` no se detecta en la misión.
- En la lista de «Palabras» no hay botón de escuchar: la voz necesita una sesión abierta.
- Dilo en inglés comprueba que la palabra aparece, no que esté bien usada (eso es «Tu propia frase»). Un acierto significa «la usaste», no que la hayas dicho perfecta.
- Tu propia frase: a veces el comentario suena raro cuando la frase no tiene arreglo.
- Guiada: Whisper a veces arregla lo que dijiste o entiende otra cosa. La nota mide leer en voz alta, no improvisar.
- Pronunciación: la nota de claridad es orientativa (Kokoro saca 81 de media; tú, 40-70 en frases bien dichas). En frases de 4 o más palabras con menos de 15/100 no se muestra ningún aviso, lo que puede ocultar errores reales. En modo pasivo la referencia es lo que entendió Whisper. La «e-» de *speak/start* dio 1 falso en 33 palabras de Kokoro.

---

## 4. Fase 7 — Gamificación y ampliaciones

Aplazado a propósito hasta ahora.

- [ ] Decidir si se quiere gamificación y cuál sería la meta diaria: lo demás de esta lista depende de eso.
- [ ] XP y niveles (DISENO §7.5, pantalla `AppProgreso`).
- [ ] Racha, retos y logros.
- [ ] Vocabulario: listas de frecuencia descargadas.
- [ ] Vocabulario: las palabras que repites demasiado, cuando haya más datos (con 69 turnos eran pocos).

---

## 5. Decisiones tomadas

- **Entorno:** Windows 11 nativo, Python 3.12 con `uv`. Repositorio público con licencia MIT. Modelos en `C:\Models` (`IABUDDY_MODELS_DIR`), fuera del repo. whisper.cpp v1.9.5 compilado con Vulkan en `C:\Tools\whisper.cpp`, porque no hay binario oficial para Windows.
- **Voz:** audífonos. Espacio abre y cierra tu turno e interrumpe a Buddy. Silencio de 900 ms con fusión de turno. Acento US, Kokoro `af_heart` a 0,9×.
- **Modelos** ([spikes](docs/SPIKES.md)): whisper `large-v3-q5_0` por Vulkan con `whisper-server`, y `gemma4:12b-it-qat` para compañero y tutor.
- **Un solo servidor Ollama:** el de la app (puerto 11435, `OLLAMA_NUM_PARALLEL=2`). `iabuddy.bat` cierra el de la bandeja, porque con los dos cargados la VRAM llega a 16,8 GB y todo se ralentiza.
- **Pedagogía:** Buddy es fijo, amigo e instructor. Modo por defecto: en voz. Buddy habla en inglés y señala 1 o 2 errores dentro de su respuesta; el tutor registra todos por escrito (gramática, vocabulario, naturalidad y estilo) y los explica en español. En «panel» y «silencioso», Buddy solo hace *recasting*.
- **Temas:** lista sugerida, editable en la base de datos.
- **Frontend:** React + Vite, solo en `127.0.0.1`. FastAPI sirve el build.
- **Sesión típica: 10 min** (Amado, 2026-11-06). No hace falta resumir el historial: se estiman ~850 tokens de conversación más el prompt, dentro de `num_ctx` 4096.
- **Audio:** ver sección 2.

---

## 6. Hecho

- **Fase 0:** dataset propio de 56 grabaciones (`data/dataset/`) y spikes S1-S6.
- **Fase 1, loop de voz:** VAD, STT, LLM y TTS con barge-in, fusión de turno, descarte de turnos sin voz y panel de tiempos. `iabuddy.bat` lo arranca todo.
- **Fase 2, feedback:** tutor asíncrono, panel, resumen de sesión, SQLite y «¿Qué querías decir?».
- **Fase 3, escenarios:** 5 escenarios en YAML con objetivos, tips y evaluación final.
- **Fase 4, pronunciación:** wav2vec2 en ONNX, avisos por sonido, práctica por grupos y «Tus frases», registros en `data/logs`.
- **Fase 5, progreso:** «Hoy», «Progreso» con calendario, «Repaso» con cajas de Leitner, «Sonidos», resumen y ajustes.
- **Fase 6, vocabulario:** banco de palabras y paquetes, misión de 4 palabras, Dilo en inglés, Tu propia frase, Buddy adivina y conversación guiada. Mismo subrayado en toda la app y práctica centrada.
