# Tema de IABuddy

Fuente: página «Sistema de diseño» del lienzo ([docs/ui/canvas/project/](../docs/ui/canvas/project/), láminas `DSTema`, `DSTokens`, `DSA11y` y `DSReticula`).
Solo hay **tema claro**: el diseño lo decide así («Tema claro, nunca oscuro»).

## Archivos

| Archivo | Qué contiene |
|---|---|
| [css/tokens.css](css/tokens.css) | Variables CSS generadas desde el sistema de diseño. Se edita solo para cambiar un valor del sistema. |
| [docs/ui/tokens.json](../docs/ui/tokens.json) | Todos los tokens en formato W3C (`$value`, `$type`): los 91 de `tokens.css`, los 14 de componente de `theme.css` y los 4 breakpoints. Si cambias un valor en el CSS, cámbialo también aquí. Revisado el 2026-11-01: los valores coinciden. |
| [css/theme.css](css/theme.css) | Importa fuentes y tokens, añade los tintes de componente que faltan en `tokens.css`, estilos base, tipografía, layout y animaciones. |

Una página solo necesita esto:

```html
<link rel="stylesheet" href="css/theme.css">
<link rel="stylesheet" href="css/components.css">
<script type="module" src="js/ui.js"></script>
```

## Color

Los cinco colores de Onda tienen una función fija. No se usan como decoración libre.

| Token | Valor | Función | Texto encima |
|---|---|---|---|
| `--azul` | `#3D5AFE` | Acción principal, marca, cara de Onda | blanco (5,1:1) |
| `--coral` | `#FF6B3D` | Tu voz, energía, «a mejorar» | tinta |
| `--rosa` | `#FF5FAE` | Pronunciación y sonidos | tinta |
| `--amarillo` | `#FFC800` | Racha, XP, avisos suaves | tinta · nunca como texto sobre blanco |
| `--lima` | `#9BE22D` | Logros, aciertos, puntuación ≥ 85 | tinta · nunca como texto sobre blanco |

**Tintes** (fondo + su texto oscuro del mismo tono, siempre juntos):

| Uso | Fondo | Texto |
|---|---|---|
| Info / azul | `--info-bg` `#E3E8FF` | `--info-text` `#2338C9` |
| Error / coral | `--error-bg` `#FFE8DF` | `--error-text` `#9A3412` |
| Sonidos / rosa | `--pink-bg` `#FFE8F3` | `--pink-text` `#9D174D` |
| Aviso / amarillo | `--warning-bg` `#FFF4C7` | `--warning-text` `#854D0E` |
| Éxito / lima | `--success-bg` `#EEFAD9` | `--success-text` `#2F5208` |

Cada familia semántica (`info`, `success`, `warning`, `error`) tiene además `--*-fill` (relleno sólido) y `--*-border` (borde e icono).

**Neutros:**

| Token | Valor | Uso |
|---|---|---|
| `--text` | `#1B1340` | Texto principal (16,2:1) |
| `--text-2` | `#4A4366` | Texto secundario |
| `--text-3` | `#5B5478` | Texto terciario |
| `--text-disabled` | `#6B6788` | Solo controles desactivados |
| `--link` | `#2338C9` | Enlaces, siempre subrayados |
| `--bg` | `#F6F7FF` | Fondo de la app |
| `--surface` | `#FFFFFF` | Tarjetas |
| `--sunken` | `#F1F3FF` | Pistas de segmentados, campos |
| `--track` | `#E6E8F2` | Barras de progreso vacías |
| `--border-control` | `#8A86A3` | Bordes de campos y chips (3,5:1) |
| `--border-subtle` | `#ECEEF8` | Separadores y guías de gráficas |
| `--switch-off` | `#7D7898` | Interruptor apagado (4,2:1) |
| `--pending` | `#6E7BC4` | Borde discontinuo de pendiente o bloqueado |

**Acción:** `--action` `#3D5AFE` (primario, selección) · `--action-pressed` `#2A43D9` · `--on-action` `#FFFFFF`.

**Gráficas:**
- Series: `--chart-1` `#3D5AFE` Conversación · `--chart-2` `#D9480F` Escenarios · `--chart-3` `#C0287A` Sonidos · `--chart-4` `#4D7C0F` Otros.
- Escala secuencial de minutos al día: `--seq-0` `#EEF0F8` 0 · `--seq-1` `#C6CFFF` 1–4 · `--seq-2` `#8C9FFF` 5–9 · `--seq-3` `#3D5AFE` 10–14 · `--seq-4` `#2338C9` 15+.

**Tokens de componente** (en `theme.css` y en el grupo `component` de `tokens.json`): `--pink-bg`, `--pink-text`, `--info-hover`, `--info-pressed`, `--disabled-*`, `--error-field-bg`, `--bubble-buddy`, `--bubble-you`, `--mark-recast`, `--mark-review`, `--strike`, `--scrim`.

**Bandas de puntuación** (pronunciación): ≥ 85 lima (bien) · 70–84 amarillo (casi) · < 70 coral (a practicar). Siempre con la cifra al lado, nunca solo el color.

## Tipografía

| Familia | Token | Uso |
|---|---|---|
| Bricolage Grotesque 700–800 | `--font-display` | Títulos y cifras, tracking negativo |
| Figtree 500–800 | `--font-body` | Texto e interfaz |
| Noto Sans Mono 500–700 | `--font-mono` | Símbolos IPA, rutas y valores técnicos |

Escala responsive (clases en `theme.css`):

| Clase | Token | Tamaño |
|---|---|---|
| `.display` | `--fs-display` | 76 → 44 px |
| `h1`, `.h1` | `--fs-h1` | 60 → 36 px |
| `h2`, `.h2` | `--fs-h2` | 30 → 24 px |
| `.metric` | `--fs-metric` | 44 → 34 px |
| `.body-l` | `--fs-body-l` | 18 → 17 px |
| cuerpo | `--fs-body` | 16 px (los campos siempre 16) |
| `.small` | `--fs-small` | 14 px |
| `.caption`, `.overline` | `--fs-caption` | 13 px (mínimo absoluto 12) |

Interlineado: `--lh-tight` 1.05 (títulos) · `--lh-body` 1.5 (texto).

El inglés que se practica se marca con `lang="en"`. La interfaz y las explicaciones van en español.

## Espacio, radios y sombras

- Espaciado: `--space-xs` 4 · `s` 8 · `m` 12 · `l` 18 · `xl` 24 · `2xl` 40 · `3xl` 56.
- Objetivo táctil mínimo: `--touch-min` 44 px.
- Radios: `--radius-chip` 10 · `--radius-tile` 18 · `--radius-card` 30 · `--radius-pill` 999 (botones y chips).
- Borde «sticker» de 2,5 px en tinta (`--border-sticker`): **solo** barra superior, chips de racha/XP y teclas.
- Sombras: `--shadow-card`, `--shadow-raised`, `--shadow-overlay`, `--shadow-modal`.
- Capas: `--z-sticky` 10 · `--z-dropdown` 100 · `--z-drawer` 200 · `--z-modal` 300 · `--z-toast` 400 · `--z-tooltip` 500.

## Layout

- **Regla: siempre se usa el 100 % de la pantalla, a lo ancho y a lo alto.** Ningún contenedor limita el ancho de la página ni se centra con un máximo: nada de `max-width`, `width: min(…px, …)` ni anchos fijos en maquetación. Las rejillas y columnas se reparten el espacio disponible (`flex`, `auto-fit`). Solo se limitan los elementos flotantes o sueltos que no son maquetación, como burbujas de chat, menús, avisos y modales.
- A lo alto, la app mide al menos `100dvh` y las zonas principales crecen con `flex: 1`, sin `max-height` en `vh`. Desde 1024 × 600 px mide justo la pantalla y cada columna hace su propio scroll; por debajo, la conversación llena la pantalla y el resto de la página se desplaza.
- Esta regla manda sobre el lienzo: las láminas y pantallas de `docs/ui/canvas/` aún dibujan un contenedor de 1320 px.
- Contenedor: `.container` solo pone el margen lateral `--margin` `clamp(16px, 4vw, 40px)`.
- Medianil entre columnas: `--gutter` `clamp(16px, 2vw, 24px)`.
- Breakpoints: xs < 600 · sm 600–899 · md 900–1199 · lg ≥ 1200. Están en `tokens.json` pero no en `tokens.css`: las variables CSS no funcionan dentro de `@media`, así que se escriben los números.
- Utilidades: `.stack` (columna) y `.cluster` (fila que envuelve). El hueco se ajusta con `--gap`.

## Movimiento

- Duraciones: `--dur-fast` 150 ms (hover, presionado) · `--dur-base` 250 ms (modales, tooltips, avisos) · `--dur-slow` 500 ms (progreso, celebración).
- Curvas: `--ease-out`, `--ease-pop` (rebote suave).
- Animaciones compartidas en `theme.css`: `dot`, `ring`, `sway`, `talk`, `popin`, `shimmer`, `stripes`, `caret`.
- Con `prefers-reduced-motion: reduce`, o `data-motion="reduced"` en `<html>` desde Ajustes, se detienen todas.

## Accesibilidad

- Foco visible en todo elemento interactivo: `--focus-ring` (anillo azul de 3 px con 3 px de aire blanco), solo con teclado (`:focus-visible`).
- Contraste de texto ≥ 4,5:1. Amarillo y lima nunca se usan como color de texto.
- El color nunca va solo: va acompañado de icono, cifra o texto.
- Tono sin culpa: los errores del alumno usan coral suave, nunca rojo ni alarmas.

## Pendiente

- Las fuentes se cargan desde Google Fonts. Para que la app funcione sin red, autoalojarlas en `frontend/fonts/` y cambiar el `@import` de `theme.css`.
