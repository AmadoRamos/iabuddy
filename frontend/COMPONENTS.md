# Componentes de IABuddy

CSS en [css/components.css](css/components.css) y comportamiento en [js/ui.js](js/ui.js). Catálogo vivo: [design-system.html](design-system.html).
Tema y tokens: [THEME.md](THEME.md).

Son HTML + CSS + JS sin framework ni paso de build. El estado vive en atributos ARIA (`aria-pressed`, `aria-checked`, `aria-selected`, `aria-current`, `aria-invalid`, `aria-busy`, `disabled`). El CSS los lee y `ui.js` los alterna. Así, lo accesible y lo visual no pueden desincronizarse.

## Estados comunes (lámina 06)

| Estado | Regla |
|---|---|
| Hover | Sube 2–3 px o el fondo pasa al tinte siguiente. 150 ms. |
| Foco | `--focus-ring`, solo con `:focus-visible`. |
| Activo | Baja 1 px y el tono se oscurece un paso. |
| Seleccionado | Relleno azul (tinta en filtros) o anillo de 4 px del color de la sección. |
| Desactivado | Fondo `#E6E8F2`, texto `#6B6788`, sin sombra ni hover. Explica el motivo cerca. |
| Cargando | `aria-busy="true"` + `.dots`. |

## Botones

```html
<button class="btn btn-primary">Responder</button>
<button class="btn btn-secondary btn-s">Charla libre</button>
<button class="btn btn-primary btn-l">Empezar <span class="kbd-inline">Espacio</span></button>
<button class="btn btn-primary" aria-busy="true"><span class="dots" aria-hidden="true"><i></i><i></i><i></i></span><span class="visually-hidden">Cargando</span></button>
```

- Variantes: `btn-primary` (una por vista), `btn-secondary`, `btn-tonal` (azul), `btn-tonal-pink`, `btn-tonal-success`, `btn-tonal-warning`, `btn-tonal-error` y `btn-ink`.
- Tamaños: `btn-l` 60 px / 18 · M por defecto 50 px / 16 · `btn-s` 44 px / 14 (mínimo). `btn-block` ocupa todo el ancho.
- **Botón de ícono:** `.icon-btn` (44 px). Variantes: `icon-btn-sticker`, `icon-btn-info`, `icon-btn-pink` e `icon-btn-success`. Lleva siempre `aria-label`. Con `aria-pressed` funciona como alternador.

## Teclas y chips de cabecera

- `<kbd class="kbd">Espacio</kbd>`. Con `data-pressed` se muestra presionada.
- `.stat-chip.stat-chip-streak` (racha) y `.stat-chip.stat-chip-xp` (XP), con borde sticker.

## Navegación

- **Barra superior:** `header.topbar` › `.brand` + `nav.nav-pill` (los enlaces con `aria-current="page"`) + chips + botón de Ajustes. Los cinco destinos son Hoy, Conversar, Escenarios, Sonidos y Progreso.
- **Menú lateral de sección** (Ajustes): `nav.side-menu`. El color de cada entrada se pone con `style="--section: var(--coral)"`.

## Controles

| Componente | Marcado | Nota |
|---|---|---|
| Segmentado | `div.segmented[role=group]` › `button[aria-pressed]` | `segmented-fill` reparte el ancho. Solo una opción activa; `ui.js` emite `change` en el grupo. |
| Filtros | `div.segmented.filters` | Activo en tinta, para no competir con la acción azul. |
| Pestañas | `div.tabs[role=tablist]` › `button[role=tab][aria-selected]` | |
| Chip | `button.chip[aria-pressed]` | Alternable suelto. |
| Interruptor | `button.switch[role=switch][aria-checked][aria-labelledby]` | |
| Deslizador | `input[type=range]` + `<output>` | Color con `accent-color`. |
| Progreso por pasos | `div.steps[role=img][aria-label]` › `i.done` / `i` | |
| Campo | `div.field` › `label` + `input.input` + `.field-hint` | Error: `aria-invalid="true"` + `.field-error`, enlazado con `aria-describedby`. |
| Selector | `select.select` | |
| Casilla de objetivo | `button.check[role=checkbox][aria-checked]` › `span.check-box` + texto | Redonda, borde discontinuo; marcada en lima. |

Cualquier contenedor con `data-single` actúa como grupo de una sola opción. Por ejemplo, las palabras del drill.

## Datos

- **Tarjeta:** `.card` (radio 30, sombra suave), `.card-tight` con menos relleno.
- **Métrica tintada:** `.metric-tile.tint-{info|error|warning|success|pink}` › `.overline` + `.metric`.
- **Tarjeta seleccionable:** `button.select-card[aria-pressed]` › `.select-card-media` + `.select-card-body`. El anillo toma `--section` (por defecto, coral).
- **Etiquetas:** `.tag` con `tag-xp`, `tag-grammar`, `tag-pron`, `tag-vocab`, `tag-new` o `tag-info`.
- **Gravedad del error:** `.tag.severity[data-level=1|2|3]` › `.severity-bars` con 3 `<i>`.
- **Nivel:** `.level-badge` (barra vertical como Onda, no un hexágono).
- **Barra de progreso:** `.progress[role=progressbar]` › `<i style="width:…">`. `progress-live` muestra rayas animadas (meta en curso).
- **Día de racha:** `.day` con `day-done`, `day-shield`, `day-missed` o `day-today`, y siempre `aria-label`.
- **Nivel de un sonido:** `.sound-level[data-level=1..5]` con 5 `<i>`.
- **Esqueleto:** `.skeleton` dentro de un contenedor con `aria-busy="true"`.

## Pronunciación

- Banda de puntuación: `score-good` (≥ 85), `score-close` (70–84) o `score-practice` (< 70).
- **Palabra del drill:** `button.drill-word.score-*[aria-pressed]` › `.drill-word-text` + `.drill-word-bar` + `.drill-word-score`, dentro de un grupo `data-single` con `lang="en"`.
- **Fonema:** `.phoneme` › `.phoneme-expected` (espeak-ng) + `.phoneme-match` o `.phoneme-miss` (wav2vec2) + `.phoneme-score`.

## Textos

`LabeledText` (`src/App.jsx`) es el texto de la app: etiqueta, texto y nota. No escribas a mano `overline` + `<p>`.

- `size`: `body` (por defecto), `m` (título de tarjeta o pista), `l` (la frase que hay que decir), `xl` (la palabra sola).
- `box`: sin caja, `plain`, `info` o `ok`. `note`: texto o botón debajo. `action`: un botón a la derecha, como escuchar.
- La alineación la da el sitio: centrado dentro de `.drill` (pantallas de práctica), a la izquierda en paneles y tarjetas.

## Conversación

- Burbujas: `.bubble.bubble-buddy` (dentro de `.buddy-row` con el avatar), `.bubble.bubble-you` y `.bubble.bubble-live` (turno en curso, con borde punteado y cursor).
- Recast: `<mark class="recast">went</mark>` (resaltado lima).
- Palabra a revisar: `<span class="review">` (subrayado punteado rosa).
- Corrección: `<s class="wrong">go</s> → <mark class="recast">went</mark>`.
- Lo que hay que practicar: `<span class="word-mark target">deadline</span>` (fondo lima) dentro de una frase, y `.review-target` para la palabra sola.
- En la app, frases con errores: `<span class="word-mark bad">go</span> → <span class="word-mark ok">went</span>` (`src/app.css`). Es el subrayado de `.word-score` dentro de un texto normal; sustituye a `s.wrong` y `mark.recast`.

## Onda · botón de hablar

```html
<div class="talk-btn" data-state="idle">
  <button aria-label="Hablar (mantén Espacio)"><svg aria-hidden="true"><use href="#onda-idle"/></svg></button>
</div>
```

| `data-state` | Símbolo | Anillos |
|---|---|---|
| `idle` | `#onda-idle` | — |
| `listening` | `#onda-listening` | coral + rosa |
| `thinking` | `#onda-thinking` | — |
| `speaking` | `#onda-speaking` | azul + lima |
| (`button` con `disabled`) | `#onda-off` | — |

Los símbolos de Onda (también `onda-logo`, `onda-celebrate` y `onda-rest`) y los iconos (`i-*`) están en el `<svg>` oculto al inicio de `design-system.html`. Cópialo a cada página o muévelo a un `icons.svg` cuando haya más de una página. Las animaciones de las barras usan las clases `.sway`, `.talk` y `.bounce`.

## Avisos

- **Modal:** `<dialog class="modal" aria-labelledby>`. Se abre con `<button data-open="id">` y se cierra con `data-close` o con `<form method="dialog">`. `showModal()` atrapa el foco, Esc cierra y el foco vuelve al botón que lo abrió. Para la celebración, añade `modal-celebrate`.
- **Tooltip:** `.tt-wrap` › disparador con `aria-describedby` + `span.tooltip[role=tooltip]`. Aparece al pasar el cursor y al recibir el foco, con 300 ms de espera. Esc lo oculta. `tooltip-wide` sirve para textos largos. Nunca contiene información imprescindible.
- **Toast:** `import { toast } from './js/ui.js'` y luego `toast({ title, text, kind: 'success' | 'streak', action: { label, onClick } })`. Se muestra uno a la vez, abajo a la derecha, con `role="status"`. Se cierra a los 5 s si no tiene acción.
- **Alerta en línea:** `.alert.alert-{info|warning|error}` con `role` `note`, `status` o `alert`, ícono y texto. Es para problemas técnicos, no para errores del alumno.
- **Vacío:** `.empty` con Onda descansando + texto + acción.

## Pendiente (láminas sin pasar a código)

Se añadirán cuando una pantalla los necesite:

- 09 Carga, háptica y sonido: solo está el estado «cargando». Faltan los sonidos de interfaz y la vibración.
- 10 Navegación: cajón lateral y navegación inferior en móvil, migas de pan y paginador.
- 11 Formularios: selector de fecha y hora (usar `<input type="date|time">` nativo).
- 12 Audio: medidor de nivel, prueba de micrófono y reproductor A/B.
- 14 Errores del sistema local, 15 Primer uso, 17 Gráficas, 18 Acordeón, búsqueda y atajos, 19 Logros e insignias.
