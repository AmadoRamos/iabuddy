# IABuddy — Diseño de UI

Diseño vigente: **estilo O2 «Estudio con Onda»**, tema claro, con la mascota Onda. Lienzo: https://claude.ai/artifact/Bn2LdwneukJmkQPxm6No3a (privado). Copia descargada el 2026-11-01 en [canvas/project/](canvas/project/).

El código que implementa este diseño está en [frontend/](../../frontend/): consulta [THEME.md](../../frontend/THEME.md), [COMPONENTS.md](../../frontend/COMPONENTS.md) y el catálogo [design-system.html](../../frontend/design-system.html).

## Lienzo (`canvas/project/`)

[canvas.json](canvas/project/canvas.json) es el índice: guarda la página, la posición y el título de cada artboard. Las páginas del lienzo son estas:

### App · O2: pantallas de la app

| Archivo | Pantalla |
|---|---|
| `AppInicio.dc.html` | Inicio (Hoy): meta diaria, racha, retos, modos de práctica |
| `AppConversacion.dc.html` | Conversación en vivo: chat, botón Onda con sus estados, panel del tutor |
| `AppEscenarios.dc.html` | Escenarios: lista, detalle, objetivos y recompensas |
| `AppPronunciacion.dc.html` | Drill de pronunciación: puntuación por palabra y fonema, niveles por sonido |
| `AppResumen.dc.html` | Resumen de sesión |
| `AppProgreso.dc.html` | Progreso: nivel, calendario de racha, semana, retos y logros |
| `AppAjustes.dc.html` | Ajustes |

Navegación: barra superior con cápsula de 5 destinos (Hoy, Conversar, Escenarios, Sonidos, Progreso) + racha, XP y Ajustes.

### Sistema de diseño (`DS*.dc.html`)

| # | Archivo | Tema | En código |
|---|---|---|---|
| 01 | `DSTema` | Colores de Onda, tintes, neutros, tipografía, espaciado, radios, movimiento | ✔ `theme.css` |
| 02 | `DSBotones` | Botones, botones de ícono, teclas, botón Onda | ✔ |
| 03 | `DSControles` | Segmentado, filtros, interruptor, deslizador, campos, casillas, navegación | ✔ |
| 04 | `DSFeedback` | Modales, tooltips, avisos, alertas, vacío y carga | ✔ |
| 05 | `DSDatos` | Tarjetas, etiquetas, progreso, pronunciación, conversación, Onda, íconos | ✔ |
| 06 | `DSEstados` | Estados de todos los componentes | ✔ |
| 07 | `DSA11y` | Accesibilidad | reglas en `THEME.md` |
| 08 | `DSTokens` | Tokens semánticos y tipografía responsive | ✔ `tokens.css` |
| 09 | `DSCarga` | Carga, háptica y sonido | parcial |
| 10 | `DSNavegacion` | Barra, cajón y navegación inferior móvil, migas, paginador | parcial |
| 11 | `DSFormularios` | Formularios, validación, selector de fecha y hora | parcial |
| 12 | `DSAudio` | Medidor, prueba de micrófono, reproductor A/B | — |
| 13 | `DSReticula` | Breakpoints y elevación | ✔ tokens |
| 14 | `DSErrores` | Errores del sistema local (motor, modelos) | — |
| 15 | `DSPrimerUso` | Primer uso | — |
| 16 | `DSContenido` | Formatos, idiomas, glosario, longitudes | — |
| 17 | `DSGraficas` | Gráficas | — |
| 18 | `DSAcordeon` | Acordeón, búsqueda y atajos | — |
| 19 | `DSLogros` | Logros e insignias | — |

### Exploración: historial de decisiones

- `Main`, `InicioB`–`InicioE`, `Conversacion` y `InicioC2`: 5 direcciones visuales para Inicio.
- `Buddy01`–`Buddy06`: 6 conceptos de mascota. **Elegida: Onda** (`OndaHoja`, `OndaContexto`).
- `InicioO1`–`InicioO4`: Inicio reimaginado con Onda. **Elegido: O2**. O3 (ecualizador) queda reservado para el futuro.
- `O2*.dc.html`: primera versión de las pantallas en estilo O2. Las sustituyen las `App*`.

## Sistema visual (resumen)

- **Tema:** solo claro. Fondo `#F6F7FF`, tarjetas blancas de radio 30, tinta `#1B1340`.
- **Colores de Onda**, cada uno con una función fija:
  - azul `#3D5AFE`: acción y marca;
  - coral `#FF6B3D`: tu voz y «a mejorar»;
  - rosa `#FF5FAE`: sonidos;
  - amarillo `#FFC800`: racha y XP;
  - lima `#9BE22D`: logros y aciertos.
- **Tipografía:** Bricolage Grotesque (títulos y cifras), Figtree (interfaz), Noto Sans Mono (IPA).
- **Tono:** el feedback nunca regaña. Sin rojo ni alarmas: los errores del alumno usan coral suave.
- **Tokens:** [tokens.json](tokens.json) (formato W3C), equivalente a [frontend/css/tokens.css](../../frontend/css/tokens.css): 92 tokens con los mismos valores. El JSON tiene además los 14 tokens de componente de `theme.css` y los breakpoints. Si cambias uno, cambia el otro. El detalle de cada token está en [THEME.md](../../frontend/THEME.md).

## Diseño v0 (retirado)

El primer diseño (tema oscuro, Manrope, aprobado el 2026-10-28) se borró el 2026-11-01. Si lo necesitas, está en el historial de git: `git show caac978:docs/ui/Main.dc.html`.

## Nota técnica

Los `.dc.html` son el código fuente del lienzo de diseño. Usan una plantilla (`{{...}}`, `<sc-for>`, `<sc-if>`) y un script `support.js` del editor, así que **no se abren directamente en el navegador**. Sirven como referencia de estructura, textos, colores y medidas. Los datos que aparecen son de ejemplo.
