# Tema de IABuddy

Fuente: página «Sistema de diseño» del lienzo ([docs/ui/canvas/project/](../docs/ui/canvas/project/), láminas `DSTema`, `DSTokens`, `DSA11y` y `DSReticula`).
Solo hay **tema claro**: el diseño lo decide así («Tema claro, nunca oscuro»).

## Archivos

| Archivo | Qué contiene |
|---|---|
| [css/tokens.css](css/tokens.css) | Variables CSS generadas desde el sistema de diseño. Se edita solo para cambiar un valor del sistema. |
| [docs/ui/tokens.json](../docs/ui/tokens.json) | Los mismos tokens en formato W3C (`$value`, `$type`). Si cambias uno, cambia el otro. |
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

**Neutros:** tinta `--text` `#1B1340`, `--text-2` `#4A4366`, `--text-3` `#5B5478`, fondo `--bg` `#F6F7FF`, superficie `--surface` `#FFFFFF`, pista `--track` `#E6E8F2`.

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

El inglés que se practica se marca con `lang="en"`. La interfaz y las explicaciones van en español.

## Espacio, radios y sombras

- Espaciado: `--space-xs` 4 · `s` 8 · `m` 12 · `l` 18 · `xl` 24 · `2xl` 40 · `3xl` 56.
- Objetivo táctil mínimo: `--touch-min` 44 px.
- Radios: `--radius-chip` 10 · `--radius-tile` 18 · `--radius-card` 30 · `--radius-pill` 999 (botones y chips).
- Borde «sticker» de 2,5 px en tinta (`--border-sticker`): **solo** barra superior, chips de racha/XP y teclas.
- Sombras: `--shadow-card`, `--shadow-raised`, `--shadow-overlay`, `--shadow-modal`.
- Capas: `--z-sticky` 10 · `--z-dropdown` 100 · `--z-drawer` 200 · `--z-modal` 300 · `--z-toast` 400 · `--z-tooltip` 500.

## Layout

- Contenedor: `.container` (máx. 1320 px, margen `clamp(16px, 4vw, 40px)`).
- Breakpoints: xs < 600 · sm 600–899 · md 900–1199 · lg ≥ 1200. Las variables CSS no funcionan dentro de `@media`, así que se escriben los números.
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
