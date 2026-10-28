# IABuddy — Diseño de UI (v0)

Diseño aprobado el 2026-10-28. Lienzo original: https://claude.ai/artifact/S3kr1JQh4sCtCvaMMCD98r (privado).

## Pantallas

| Archivo | Pantalla | Interactiva |
|---|---|---|
| `Main.dc.html` | Inicio: meta diaria, racha semanal, retos, modos de práctica, sesiones recientes | navegación |
| `Session.dc.html` | Sesión de conversación: chat, botón de turno con 4 estados, panel del tutor, XP por turno | sí (estados del turno, modo del tutor) |
| `Scenarios.dc.html` | Escenarios: lista con estrellas, detalle con objetivos, vocabulario y recompensas | sí (selección) |
| `Pronunciation.dc.html` | Pronunciación: puntuación por palabra y fonema, niveles por sonido | sí (selección de palabra) |
| `Summary.dc.html` | Resumen de sesión: XP ganado, racha, logro, errores agrupados, repertorio | navegación |
| `Progress.dc.html` | Progreso: nivel, estadísticas, mapa de actividad, récords, logros | navegación |
| `Settings.dc.html` | Ajustes: turno de voz, voz de Buddy, tutor, motivación, motores, datos | sí (controles) |
| `canvas.json` | Índice del lienzo (posición y tamaño de cada pantalla) | — |

## Sistema visual

- **Tipografía:** Manrope (UI) + JetBrains Mono (cifras, latencias, fonemas).
- **Fondo / superficies:** `#0E1014` · `#12151B` · `#161920` · `#1D2330` · bordes `#242833`.
- **Texto:** `#ECEEF2` principal · `#A3AAB7` secundario.
- **Azul `#7AB0FF`:** acción principal, Buddy, estado activo.
- **Naranja `#FFB454`:** correcciones y errores.
- **Violeta `#B79CFF`** (fondo `#241E38`, texto `#CDB9FF`): todo lo de gamificación (XP, racha, niveles, logros).
- **Verde `#5FD39A`:** motores listos, objetivos cumplidos.
- **Rojo suave `#FF8A8A`:** grabando tu turno.
- **Navegación:** barra superior con cápsula de pestañas (Inicio, Conversación, Escenarios, Pronunciación, Progreso) + racha, nivel, estado de motores y botón de Ajustes.

## Nota técnica

Los `.dc.html` son el código fuente del lienzo de diseño: usan una plantilla (`{{...}}`, `<sc-for>`, `<sc-if>`) y un script `support.js` del editor, por eso **no se abren directamente en el navegador**. Sirven como referencia de estructura, textos, colores y medidas para construir el frontend real (`frontend/`). Los datos que aparecen son de ejemplo.
