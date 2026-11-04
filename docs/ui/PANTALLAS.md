# Diseños, pantallas y endpoints

Qué diseño de [App/](App/), [Sistema de Diseño/](Sistema%20de%20Diseño/) y [canvas/project/](canvas/project/) corresponde a cada pantalla de la app y qué endpoints usa. Para los estilos y los tokens, consulta [README.md](README.md).

## Cómo está montada la app

- **Solo hay una URL de página: `/`.** La app no tiene rutas: [App.jsx](../../frontend/src/App.jsx) cambia de pantalla según su estado (`view`, `session`, `summary`), así que los enlaces entre pantallas del lienzo (`AppProgreso.dc.html`, etc.) no equivalen a direcciones reales.
- FastAPI sirve la app desde `frontend/dist` en `http://127.0.0.1:8000`. En desarrollo, Vite la sirve y reenvía `/api` y `/ws` al puerto 8000.
- **Estado** indica cuánto del diseño está construido: **Parcial** significa que falta parte de lo que dibuja el diseño. Lo que falta se detalla en cada fila.

## Pantallas de la app

**Los diseños con prefijo `O2` (e `InicioO2`), en [App/](App/), son la referencia.** Los `App*`, en `canvas/project/`, son copias: el contenido es idéntico y solo cambian los enlaces entre pantallas. Un cambio de diseño se hace primero en el `O2` y se copia al `App`, ajustando esos enlaces.

| Diseño | Copia | Pantalla | Cuándo se muestra en `/` | Componente | Endpoints | Estado |
|---|---|---|---|---|---|---|
| [InicioO2](App/InicioO2.dc.html) | [AppInicio](canvas/project/AppInicio.dc.html) | Hoy (y Conversar, para elegir tema) | Sección «Hoy» o «Conversar» del menú | `Home`, `StartCard` | `GET /api/health`, `GET /api/topics`, `GET /api/progress` | **Parcial.** Hablar ya, tema de hoy, repaso, sonido que más fallas y tus cifras. Falta: meta diaria, racha, nivel, prompt del día y calentamiento |
| [O2Conversacion](App/O2Conversacion.dc.html) | [AppConversacion](canvas/project/AppConversacion.dc.html) | Conversación en vivo | Sesión en curso (el menú se oculta) | `SessionPanel`, `ChatLog`, `Dock`, `TutorPanel` | `WS /ws` | **Parcial.** Las 3 columnas están hechas. Falta: XP |
| [O2Escenarios](App/O2Escenarios.dc.html) | [AppEscenarios](canvas/project/AppEscenarios.dc.html) | Escenarios | Sección «Escenarios» del menú | `Scenarios` | `GET /api/scenarios`, `WS /ws` | **Parcial.** Lista, detalle con papeles, objetivos y frases, y mejores estrellas. Falta: filtros y duración (no existen esos datos), criterio de fin y recompensas de XP |
| [O2Pronunciacion](App/O2Pronunciacion.dc.html) | [AppPronunciacion](canvas/project/AppPronunciacion.dc.html) | Sonidos: práctica de pronunciación y repaso | Sección «Sonidos» del menú, o «Repasar» | `Drill`, `Review`, `PhraseCheck` | `GET /api/drills`, `POST /api/review`, `WS /ws` | **Parcial.** Lista de sonidos, progreso, palabras seleccionables y fonemas esperados. Sin notas por palabra o fonema ni niveles a propósito: la confianza del modelo no es una calificación. Falta: XP. El repaso comparte el estilo, pero tiene flujo propio y no está en el diseño |
| [O2Resumen](App/O2Resumen.dc.html) | [AppResumen](canvas/project/AppResumen.dc.html) | Resumen de sesión | Al terminar una sesión | `Summary` | `WS /ws` (evento `summary`) | **Parcial.** Cabecera con estrellas, cifras, objetivos, errores por tipo, pronunciación y botones para repetir o practicar. Sin notas por sonido a propósito. Falta: XP, racha y vocabulario (no existe ese dato) |
| [O2Progreso](App/O2Progreso.dc.html) | [AppProgreso](canvas/project/AppProgreso.dc.html) | Progreso | Sección «Progreso» del menú | `Progress`, `MonthCalendar`, `ThisWeek`, `Chart` | `GET /api/progress` | **Parcial.** Calendario del mes (solo días con práctica) y semana. El historial, las gráficas y los errores y sonidos repetidos no están en el diseño. Falta: nivel, racha, retos y logros |
| [O2Ajustes](App/O2Ajustes.dc.html) | [AppAjustes](canvas/project/AppAjustes.dc.html) | Ajustes | Icono arriba a la derecha | `Settings` | `GET /api/health`, `GET` y `PUT /api/settings`, `GET /api/voice-sample` | **Parcial.** Silencio, velocidad con voz de prueba, modo de corrección y estado de los modelos. Sin idioma (decidido: español) ni umbral de confianza (la app no decide con él). Falta: metas, XP, protector de racha y cambiar la tecla |

## Endpoints

Definidos en [backend/main.py](../../backend/main.py).

| Endpoint | Para qué | Pantalla | Diseño |
|---|---|---|---|
| `GET /` | Sirve la app (`frontend/dist`) | Todas | Todas las pantallas O2 |
| `GET /api/health` | Comprueba Whisper, Ollama y el modelo de pronunciación | Todas: aviso `HealthAlert` | [DSErrores](Sistema%20de%20Diseño/DSErrores.dc.html) (parcial) |
| `GET /api/topics` | Temas de conversación | Hoy y Conversar | [InicioO2](App/InicioO2.dc.html) |
| `GET /api/scenarios` | Lista de escenarios con papeles y tus mejores estrellas | Escenarios | [O2Escenarios](App/O2Escenarios.dc.html) |
| `GET /api/drills` | Frases por sonido, tus frases falladas y el repaso pendiente | Práctica | [O2Pronunciacion](App/O2Pronunciacion.dc.html) |
| `POST /api/review` | Guarda «La sabía» o «Repasarla otra vez»; devuelve cuántas quedan y cuándo vuelve la siguiente | Repaso | Sin diseño |
| `GET /api/progress` | Historial, minutos por día, métricas, errores y sonidos repetidos | Hoy y Progreso | [O2Progreso](App/O2Progreso.dc.html) (dibuja solo el calendario y la semana) |
| `GET` y `PUT /api/settings` | Lee y guarda silencio, velocidad y modo de corrección | Ajustes y panel del tutor | [O2Ajustes](App/O2Ajustes.dc.html) |
| `GET /api/voice-sample` | Voz de Buddy a la velocidad actual, en WAV | Ajustes | [O2Ajustes](App/O2Ajustes.dc.html) |
| `WS /ws` | Audio y eventos de la sesión | Conversación, Práctica y Resumen | Abajo |

### Mensajes de `WS /ws`

Definidos en [turn_manager.py](../../backend/pipeline/turn_manager.py). El audio va en binario: PCM de 16 kHz hacia el servidor y de 24 kHz hacia el navegador.

| Pantalla | El navegador envía | El servidor responde |
|---|---|---|
| Conversación | `hello`, `start`, `stop`, `settings`, `intent`, `say` | `session`, `state`, `user_text`, `partner_text`, `partner_done`, `barge_in`, `turn_resumed`, `turn_discarded`, `feedback`, `intent_failed`, `pronunciation`, `goals`, `metrics`, `error` |
| Práctica | `drill`, `stop`, `start`, `say`, `settings` | `state`, `drill_result`, `turn_discarded`, `turn_resumed` |
| Resumen | `end` | `summary` |
| Solo registros | `client_error`, `client_metrics` | — |

## Sistema de diseño

Son láminas de componentes y reglas: **no corresponden a ninguna página ni endpoint**. La columna «En código» dice si ya existe y dónde se usa dentro de la app.

| Diseño | Tema | En código |
|---|---|---|
| [DSTema](Sistema%20de%20Diseño/DSTema.dc.html) | Colores, tipografía, espaciado, movimiento | Sí, en toda la app (`theme.css`) |
| [DSTokens](Sistema%20de%20Diseño/DSTokens.dc.html) | Tokens semánticos y tipografía responsive | Sí, en toda la app (`tokens.css`) |
| [DSReticula](Sistema%20de%20Diseño/DSReticula.dc.html) | Breakpoints y elevación | Sí: las 3 columnas de Conversación usan sus breakpoints |
| [DSA11y](Sistema%20de%20Diseño/DSA11y.dc.html) | Accesibilidad | Reglas en [THEME.md](../../frontend/THEME.md) |
| [DSBotones](Sistema%20de%20Diseño/DSBotones.dc.html) | Botones, teclas, botón Onda | Sí: botón Onda en `Dock` |
| [DSControles](Sistema%20de%20Diseño/DSControles.dc.html) | Segmentado, filtros, campos | Sí: segmentado en `TutorPanel`, filtros en `StartCard` |
| [DSFeedback](Sistema%20de%20Diseño/DSFeedback.dc.html) | Modales, tooltips, avisos, vacío y carga | Sí: alertas y vacíos |
| [DSDatos](Sistema%20de%20Diseño/DSDatos.dc.html) | Tarjetas, etiquetas, conversación, Onda | Sí, en toda la app |
| [DSEstados](Sistema%20de%20Diseño/DSEstados.dc.html) | Estados de los componentes | Sí |
| [DSCarga](Sistema%20de%20Diseño/DSCarga.dc.html) | Carga, háptica y sonido | Parcial |
| [DSNavegacion](Sistema%20de%20Diseño/DSNavegacion.dc.html) | Barra, cajón, navegación móvil | Parcial: `nav-pill` en la barra superior. Sin cajón ni navegación móvil propia |
| [DSFormularios](Sistema%20de%20Diseño/DSFormularios.dc.html) | Formularios y validación | Parcial: formulario de «¿Qué querías decir?» en `YourTurn` |
| [DSErrores](Sistema%20de%20Diseño/DSErrores.dc.html) | Errores del sistema local | Parcial: `HealthAlert` |
| [DSGraficas](Sistema%20de%20Diseño/DSGraficas.dc.html) | Gráficas | No se siguió esta lámina: `Chart` usa solo el token `--chart-1`. Falta contrastarlos |
| [DSAudio](Sistema%20de%20Diseño/DSAudio.dc.html) | Medidor, prueba de micrófono, reproductor A/B | No |
| [DSPrimerUso](Sistema%20de%20Diseño/DSPrimerUso.dc.html) | Primer uso | No |
| [DSContenido](Sistema%20de%20Diseño/DSContenido.dc.html) | Formatos, idiomas, glosario | No |
| [DSAcordeon](Sistema%20de%20Diseño/DSAcordeon.dc.html) | Acordeón, búsqueda y atajos | No |
| [DSLogros](Sistema%20de%20Diseño/DSLogros.dc.html) | Logros e insignias | No |

## Exploración: historial de decisiones

**Ninguno se usa en la app ni corresponde a una página.** Se conservan para saber qué se descartó y por qué. La mascota es la excepción: lo elegido en `OndaHoja` vive en el sprite de [index.html](../../frontend/index.html) (`#onda-*`).

| Diseños | Qué exploraban | Resultado |
|---|---|---|
| [Main](canvas/project/Main.dc.html), [InicioB](canvas/project/InicioB.dc.html), [InicioC](canvas/project/InicioC.dc.html), [InicioC2](canvas/project/InicioC2.dc.html), [InicioD](canvas/project/InicioD.dc.html), [InicioE](canvas/project/InicioE.dc.html), [Conversacion](canvas/project/Conversacion.dc.html) | Direcciones visuales de Inicio y una primera conversación en vivo | Descartados |
| [Buddy01](canvas/project/Buddy01.dc.html), [Buddy02](canvas/project/Buddy02.dc.html), [Buddy03](canvas/project/Buddy03.dc.html), [Buddy04](canvas/project/Buddy04.dc.html), [Buddy05](canvas/project/Buddy05.dc.html), [Buddy06](canvas/project/Buddy06.dc.html) | Conceptos de mascota | Elegido: Buddy03, Onda |
| [OndaHoja](canvas/project/OndaHoja.dc.html), [OndaContexto](canvas/project/OndaContexto.dc.html) | Hoja de personaje de Onda y Onda en contexto | Vigentes como referencia de la mascota |
| [InicioO1](canvas/project/InicioO1.dc.html), [InicioO3](canvas/project/InicioO3.dc.html), [InicioO4](canvas/project/InicioO4.dc.html) | Otras versiones de Inicio con Onda | Se eligió `InicioO2` (arriba). O3 queda reservado para el futuro |

[canvas.json](canvas/project/canvas.json) no es un diseño: es el índice del lienzo, con la página, la posición y el título de cada lámina. Apunta a cada archivo con su ruta relativa (`../../App/…`, `../../Sistema de Diseño/…`). Al añadir, mover o renombrar un diseño, actualiza sus entradas en `boards` y `order`.

## Al cambiar algo

Actualiza este archivo si añades un diseño, una pantalla o un endpoint, y también si construyes algo que aquí figura como pendiente.
