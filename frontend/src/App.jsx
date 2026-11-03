import { useEffect, useRef, useState } from 'react';
import { useConversation } from './useConversation.js';

// Textos del dock por estado (AppConversacion.dc.html)
const STATUS = {
  idle: ['Tu turno', 'Pulsa Espacio cuando quieras hablar.', 'para hablar', 'Hablar'],
  listening: ['Te escucho…', 'Pulsa Espacio al terminar, o haz una pausa.', 'cierra tu turno', 'Cerrar mi turno'],
  thinking: ['Pensando…', 'Transcribo tu turno y preparo la respuesta. Si no habías terminado, sigue hablando.', 'para seguir hablando', 'Seguir hablando'],
  speaking: ['Buddy habla', 'La primera frase suena mientras se generan las demás.', 'para interrumpir', 'Interrumpir a Buddy'],
  connecting: ['Conectando…', 'Preparo el micrófono y la conexión.', '', 'Conectando'],
};
const DOCK_BG = { listening: 'var(--error-field-bg)', thinking: 'var(--bg)', speaking: 'var(--info-bg)' };
const ISSUE_TAG = { grammar: ['tag-grammar', 'Gramática'], vocabulary: ['tag-vocab', 'Vocabulario'], naturalness: ['tag-info', 'Naturalidad'] };
const SEVERITY = { 1: 'Leve', 2: 'Media', 3: 'Alta' };
const MODES = [['silencioso', 'Silencioso'], ['panel', 'Panel'], ['voz', 'En voz']];

export default function App() {
  const c = useConversation();
  const { ui, session, summary } = c;
  const [drillText, setDrillText] = useState('');
  const [choice, setChoice] = useState({ topic_id: null }); // { topic_id } (null = libre) o { scenario }

  // Espacio: empezar la sesión o alternar el turno. No en campos de texto ni en el resumen.
  useEffect(() => {
    const onKey = (e) => {
      if (e.code !== 'Space' || e.repeat || e.target.closest?.('input, textarea, select')) return;
      e.preventDefault();
      if (session?.drill) { if (ui !== 'connecting' && drillText) c.drillToggle(drillText); }
      else if (session) { if (ui !== 'connecting') c.toggle(); } else if (!summary && ui !== 'connecting') c.start(choice);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [ui, session, summary, choice, drillText, c]);

  const h = c.health;
  const down = h && (h.backend === false || !h.whisper || !h.ollama);

  return (
    <div className="container">
      <header className="topbar">
        <span className="brand"><svg aria-hidden="true" width="44" height="44"><use href="#onda-logo" /></svg>
          <span className="brand-name">iabuddy</span></span>
        <div className="cluster">
          <span className="tag tag-info">{session?.drill ? 'Pronunciación' : session?.scenario ? `Escenario · ${session.scenario.title}`
            : `Conversación libre${session?.topic ? ` · ${session.topic}` : ''}`}</span>
          {session?.drill && <button className="btn btn-secondary btn-s" onClick={c.leaveDrill}>Salir</button>}
          {session && !session.drill && (
            <button className="btn btn-secondary btn-s" onClick={c.end} disabled={c.ending}>
              {c.ending ? (session.scenario ? 'Evaluando…' : 'Terminando…') : 'Terminar sesión'}
            </button>
          )}
        </div>
      </header>

      <main className="session">
        {down && <HealthAlert health={h} />}
        {c.error && <div className="alert alert-error" role="alert"><span>{c.error}</span></div>}

        <div className="session-grid">
          <section className="card conversation" aria-label="Conversación">
            {summary ? <Summary s={summary} onClose={c.closeSummary} onListen={c.listen} />
              : session?.drill ? <Drill c={c} text={drillText} setText={setDrillText} />
              : session ? <><ChatLog messages={c.messages} feedbacks={c.feedbacks} intents={c.intents} sounds={c.sounds}
                  onIntent={c.sendIntent} onListen={c.listen} /><Dock ui={ui} onToggle={c.toggle} /></>
                : <StartCard topics={c.topics} scenarios={c.scenarios} choice={choice} setChoice={setChoice}
                    onStart={() => c.start(choice)} disabled={down || ui === 'connecting'}
                    onDrill={h?.pronunciation ? () => c.start({ drill: true }) : null} />}
          </section>
          {!session?.drill && <aside className="session-side">
            {session?.scenario && <GoalsCard scenario={session.scenario} met={session.met} onListen={c.listen} />}
            <TutorPanel mode={c.mode} onMode={c.changeMode} feedbacks={c.feedbacks} onListen={c.listen} />
            <MetricsCard metrics={c.metrics} silenceMs={h?.silence_ms} />
          </aside>}
        </div>
      </main>
    </div>
  );
}

function ChatLog({ messages, feedbacks, intents, sounds, onIntent, onListen }) {
  const end = useRef(null);
  // Con llaves: scrollIntoView devuelve una promesa en Chrome reciente y React la tomaría por la limpieza
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages, feedbacks, sounds]);
  return (
    <div className="chat" aria-live="polite">
      {messages.map((m, i) => (m.who === 'buddy' ? (
        <div className="buddy-row" key={i}>
          <svg aria-hidden="true" width="40" height="40" style={{ flex: 'none' }}><use href="#onda-logo" /></svg>
          <span className="bubble bubble-buddy" lang="en">{m.text}{m.cut && ' …'}</span>
        </div>
      ) : m.live ? (
        <span key={i} className="bubble bubble-live" lang="en">{m.text || '…'}</span>
      ) : (
        <YourTurn key={i} m={m} fb={feedbacks.find((f) => f.turn === m.turn)} state={intents[m.turn]} sounds={sounds[m.turn]}
          onIntent={onIntent} onListen={onListen} />
      )))}
      <div ref={end} />
    </div>
  );
}

// Tu burbuja: al pulsarla, opciones («¿Qué querías decir?», escuchar). Escribes tu intención y
// aparece cómo decirlo en inglés.
function YourTurn({ m, fb, state, sounds, onIntent, onListen }) {
  const [menu, setMenu] = useState(false);
  const [up, setUp] = useState(false);
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const box = useRef(null);

  // El menú se cierra al pulsar fuera o con Esc
  useEffect(() => {
    if (!menu) return undefined;
    const close = (e) => { if (e.type === 'keydown' ? e.key === 'Escape' : !box.current?.contains(e.target)) setMenu(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => { document.removeEventListener('mousedown', close); document.removeEventListener('keydown', close); };
  }, [menu]);
  const submit = (e) => {
    e.preventDefault();
    if (!text.trim()) return;
    onIntent(m.turn, text.trim());
    setOpen(false);
  };
  const pick = (action) => { setMenu(false); action(); };
  return (
    <div className="your-turn" ref={box}>
      {/* La burbuja es un botón: al pulsarla aparecen sus opciones, flotando sobre el chat */}
      <div className="bubble-anchor">
      <button className="bubble bubble-you bubble-btn" lang="en" aria-haspopup="menu" aria-expanded={menu}
        onClick={(e) => {
          // Cerca del final del chat, el menú se abre hacia arriba para no quedar recortado
          const chat = e.currentTarget.closest('.chat')?.getBoundingClientRect();
          setUp(chat ? e.currentTarget.getBoundingClientRect().bottom + 120 > chat.bottom : false);
          setMenu((v) => !v);
        }}>{m.text}</button>
      {menu && (
        <div className={`bubble-menu${up ? ' bubble-menu-up' : ''}`} role="menu" aria-label="Opciones de tu frase">
          <button role="menuitem" autoFocus onClick={() => pick(() => setOpen(true))}>
            ✎ {fb?.intent ? 'Cambiar lo que querías decir' : '¿Qué querías decir?'}
          </button>
          {fb?.corrected && (
            <button role="menuitem" onClick={() => pick(() => onListen(fb.corrected))}>
              🔊 Escuchar cómo se dice
            </button>
          )}
        </div>
      )}
      </div>
      {sounds?.map((s) => (
        <div className="pron-note" key={`${s.word}${s.phone}`}>
          <span><strong lang="en">{s.word}</strong>: {s.tip}</span>
          <ListenButton text={s.word} onListen={onListen} />
        </div>
      ))}
      {state === 'failed' && !open && <span className="small muted">No pude analizar lo que escribiste. Inténtalo otra vez.</span>}
      {fb?.intent && !open ? (
        <div className="said-as">
          <span className="overline">Así se dice</span>
          <p lang="en">{highlight(fb.corrected, fb.issues.map((i) => i.fix), 'mark', 'recast')}</p>
          <ListenButton text={fb.corrected} onListen={onListen} />
        </div>
      ) : state === 'pending' ? (
        <span className="small muted" aria-busy="true">Buscando cómo decirlo… <span className="dots" aria-hidden="true"><i /><i /><i /></span></span>
      ) : open ? (
        <form className="intent-form" onSubmit={submit}>
          <label className="visually-hidden" htmlFor={`intent-${m.turn}`}>¿Qué querías decir?</label>
          <textarea id={`intent-${m.turn}`} className="input" rows={2} autoFocus value={text}
            placeholder="Escribe lo que querías decir, en español o en inglés"
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) submit(e);
              if (e.key === 'Escape') setOpen(false);
            }} />
          <div className="cluster">
            <button type="button" className="btn btn-secondary btn-s" onClick={() => setOpen(false)}>Cancelar</button>
            <button className="btn btn-primary btn-s">Enviar</button>
          </div>
        </form>
      ) : null}
    </div>
  );
}

function ListenButton({ text, onListen }) {
  return (
    <button className="icon-btn" aria-label={`Escuchar: ${text}`} title="Escuchar" onClick={() => onListen(text)}>
      <svg aria-hidden="true" width="20" height="20"><use href="#i-listen" /></svg>
    </button>
  );
}

function Dock({ ui, onToggle, status = STATUS }) {
  const [title, text, keyHint, label] = status[ui] ?? status.idle;
  return (
    <div className="dock" style={{ background: DOCK_BG[ui] }}>
      <div className="dock-status">
        <span className="h2">{title}</span>
        <span className="muted">{text}</span>
      </div>
      <div className="talk-btn" data-state={ui === 'connecting' ? undefined : ui}>
        {/* detail === 0: clic generado por el teclado; Espacio ya lo gestiona el listener global */}
        <button aria-label={label} disabled={ui === 'connecting'} onClick={(e) => e.detail !== 0 && onToggle()}>
          <svg aria-hidden="true"><use href={`#onda-${ui === 'connecting' ? 'off' : ui}`} /></svg>
        </button>
      </div>
      <div className="dock-key">{keyHint && <><kbd className="kbd">Espacio</kbd>{keyHint}</>}</div>
    </div>
  );
}

function StartCard({ topics, scenarios, choice, setChoice, onStart, onDrill, disabled }) {
  return (
    <div className="start">
      <svg aria-hidden="true" width="120" height="120"><use href="#onda-idle" /></svg>
      <h1>¿Charlamos?</h1>
      <p className="body-l muted">Elige un tema o habla de lo que quieras. Pulsa Espacio para abrir tu turno y otra vez
        para cerrarlo. Usa audífonos.</p>
      <div className="cluster topics" role="group" aria-label="Tema">
        {[{ id: null, title: 'Libre' }, ...topics].map((t) => (
          <button key={t.id ?? 'libre'} className="chip" aria-pressed={!choice.scenario && choice.topic_id === t.id}
            onClick={() => setChoice({ topic_id: t.id })}>{t.title}</button>
        ))}
      </div>
      {scenarios.length > 0 && (
        <>
          <h2 className="h2">O practica una situación</h2>
          <div className="scenarios" role="group" aria-label="Escenario">
            {scenarios.map((sc) => (
              <button key={sc.id} className="scenario-card" aria-pressed={choice.scenario === sc.id}
                onClick={() => setChoice({ scenario: sc.id })}>
                <strong>{sc.title}</strong><span className="small muted">{sc.description}</span>
              </button>
            ))}
          </div>
        </>
      )}
      <button className="btn btn-primary btn-l" onClick={onStart} disabled={disabled}>
        Empezar <span className="kbd-inline">Espacio</span>
      </button>
      {onDrill && <button className="btn btn-secondary" onClick={onDrill} disabled={disabled}>Practicar pronunciación</button>}
    </div>
  );
}

const DRILL_STATUS = {
  ...STATUS,
  idle: ['Te toca leer', 'Escúchala si quieres y léela en voz alta.', 'para empezar a leer', 'Leer la frase'],
  thinking: ['Analizando…', 'Comparo tu voz con los sonidos de la frase. Si no habías terminado, sigue leyendo.', 'para seguir leyendo', 'Seguir leyendo'],
  speaking: ['Escucha', 'Buddy lee la frase.', 'para empezar a leer', 'Leer la frase'],
};

// Práctica de pronunciación: tus frases falladas y frases por sonido. Lees, y ves qué sonidos revisar.
function Drill({ c, text, setText }) {
  const failed = c.drills?.failed ?? [];
  const groups = [...(failed.length ? [{ title: `Tus frases (${failed.length})`, sentences: failed.map((f) => f.text) }] : []),
    ...(c.drills?.sounds ?? [])];
  const [group, setGroup] = useState(0);
  const [index, setIndex] = useState(0);
  const sentences = groups[group]?.sentences ?? [];
  const current = sentences[index % (sentences.length || 1)] ?? '';
  useEffect(() => { setText(current); }, [current, setText]);
  const result = c.drillResult?.text === current ? c.drillResult : null;
  const issues = result?.words.filter((w) => w.issues.length) ?? [];
  const unclear = result?.words.filter((w) => w.unclear && !w.issues.length) ?? [];
  if (!c.drills) return <div className="start"><span className="muted" aria-busy="true">Preparando las frases…</span></div>;
  return (
    <>
      <div className="drill stack">
        <div className="cluster" role="group" aria-label="Sonido que quieres practicar">
          {groups.map((g, i) => (
            <button key={g.title} className="chip" aria-pressed={group === i} onClick={() => { setGroup(i); setIndex(0); }}>{g.title}</button>
          ))}
        </div>
        <div className="drill-phrase">
          <p lang="en" aria-live="polite">
            {result ? result.words.map((w, i) => (
              <span key={i} className={w.issues.length || w.unclear ? 'drill-word-bad' : undefined}>{w.word} </span>
            )) : current}
          </p>
          <ListenButton text={current} onListen={c.listen} />
        </div>
        {result && (
          <section className="stack" aria-live="polite">
            <div className="cluster" style={{ justifyContent: 'space-between' }}>
              <strong>{issues.length || unclear.length ? 'Revisa estas palabras' : result.passed ? '¡Sin errores claros!' : 'No te entendí bien esta frase. ¿La repites?'}</strong>
              <span className="caption">claridad {result.score}/100</span>
            </div>
            {issues.flatMap((w, n) => w.issues.map((s) => (
              <div className="pron-note" key={`${n}${s.phone}`}>
                <span><strong lang="en">{w.word}</strong>: {s.tip}</span>
                <ListenButton text={w.word} onListen={c.listen} />
              </div>
            )))}
            {unclear.map((w, n) => (
              <div className="pron-note" key={n}>
                <span><strong lang="en">{w.word}</strong>: no se oyó con claridad. Escúchala y repite la frase.</span>
                <ListenButton text={w.word} onListen={c.listen} />
              </div>
            ))}
          </section>
        )}
        <button className="btn btn-secondary btn-s" style={{ alignSelf: 'flex-start' }} onClick={() => setIndex((n) => n + 1)}>Otra frase</button>
      </div>
      <Dock ui={c.ui} status={DRILL_STATUS} onToggle={() => c.drillToggle(current)} />
    </>
  );
}

// Marca dentro de `text` los fragmentos dados (sin distinguir mayúsculas) con el elemento Tag
function highlight(text, fragments, Tag, className) {
  const parts = fragments.filter(Boolean).map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (!parts.length) return text;
  return text.split(new RegExp(`(${parts.join('|')})`, 'gi')).map((p, i) =>
    (i % 2 ? <Tag key={i} className={className}>{p}</Tag> : p));
}

// Objetivos del escenario: se marcan cuando los cumples. Debajo, frases útiles para la escena.
function GoalsCard({ scenario, met = [], onListen }) {
  const done = met.filter(Boolean).length;
  return (
    <div className="card card-tight stack">
      <div className="cluster" style={{ justifyContent: 'space-between' }}>
        <h2 className="h2">Tus objetivos</h2><span className="caption">{done}/{scenario.goals.length}</span>
      </div>
      <p className="small muted">{scenario.description}</p>
      <GoalList goals={scenario.goals.map((text, i) => ({ text, met: met[i] }))} />
      {scenario.key_phrases.length > 0 && (
        <details>
          <summary className="small"><strong>Frases útiles</strong></summary>
          <PhraseList phrases={scenario.key_phrases} onListen={onListen} />
        </details>
      )}
    </div>
  );
}

function GoalList({ goals }) {
  return (
    <ul className="goals">
      {goals.map((g, i) => (
        <li key={i} className={g.met ? 'met' : undefined}>
          <span className="goal-check" aria-hidden="true">{g.met ? '✓' : ''}</span>
          <span><span className="visually-hidden">{g.met ? 'Cumplido: ' : 'Pendiente: '}</span>{g.text}
            {g.evidence && <span className="small muted" lang="en"> · “{g.evidence}”</span>}</span>
        </li>
      ))}
    </ul>
  );
}

function PhraseList({ phrases, onListen }) {
  return (
    <ul className="phrases">
      {phrases.map((p) => (
        <li key={p}><span lang="en">{p}</span><ListenButton text={p} onListen={onListen} /></li>
      ))}
    </ul>
  );
}

function TutorPanel({ mode, onMode, feedbacks, onListen }) {
  return (
    <>
      <div className="card card-tight stack">
        <div className="cluster" style={{ justifyContent: 'space-between' }}>
          <h2 className="h2">Tutor</h2><span className="caption">explica en español</span>
        </div>
        <div className="segmented segmented-fill" role="group" aria-label="Modo de corrección">
          {MODES.map(([v, label]) => (
            <button key={v} aria-pressed={mode === v} onClick={() => onMode(v)}>{label}</button>
          ))}
        </div>
        <p className="small muted">
          {mode === 'silencioso' ? 'Solo hablas. Las correcciones se guardan para el resumen de la sesión.'
            : mode === 'voz' ? 'Buddy te corrige en la conversación. Aquí tienes todos los errores, explicados en español.'
              : 'Buddy no te interrumpe: tus correcciones aparecen solo aquí.'}
        </p>
      </div>
      {mode !== 'silencioso' && (feedbacks.length
        ? feedbacks.map((f) => <FeedbackCard key={f.turn} f={f} onListen={onListen} />)
        : <div className="empty"><span className="small muted">Aquí aparecerán las correcciones de cada turno tuyo.</span></div>)}
    </>
  );
}

function FeedbackCard({ f, onListen }) {
  if (!f.issues.length && !f.intent) {
    return (
      <article className="card card-tight feedback-ok">
        <strong>Tu turno {f.turn} · ¡sin errores!</strong>
        <span className="small">{f.text.split(/\s+/).length} palabras, natural y correcto.</span>
      </article>
    );
  }
  const level = Math.max(1, ...f.issues.map((i) => i.severity));
  return (
    <article className="card card-tight stack feedback">
      <div className="cluster" style={{ justifyContent: 'space-between' }}>
        <strong>Tu turno {f.turn}</strong>
        {f.issues.length > 0 && <span className="tag severity" data-level={level}><span className="severity-bars"><i /><i /><i /></span>{SEVERITY[level]}</span>}
      </div>
      <div><span className="overline">Lo que dijiste</span>
        <p lang="en">{highlight(f.text, f.issues.map((i) => i.original), 's', 'wrong')}</p></div>
      {f.intent && <div><span className="overline">Lo que querías decir</span><p>{f.intent}</p></div>}
      <div className="cluster" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
        <div><span className="overline">{f.intent ? 'Así se dice' : 'Mejor así'}</span>
          <p lang="en">{highlight(f.corrected, f.issues.map((i) => i.fix), 'mark', 'recast')}</p></div>
        <ListenButton text={f.corrected} onListen={onListen} />
      </div>
      <ul className="issues">
        {f.issues.map((i, n) => {
          const [cls, label] = ISSUE_TAG[i.type] ?? ['tag-info', i.type];
          return (
            <li key={n}><span className={`tag ${cls}`}>{label}</span>
              <span><strong lang="en">{i.original} → {i.fix}</strong>: {i.explanation_es}</span></li>
          );
        })}
      </ul>
      {f.better && f.better !== f.corrected && (
        <div><span className="overline">Suena más natural</span><p lang="en" className="better">“{f.better}”</p></div>
      )}
    </article>
  );
}

function Summary({ s, onClose, onListen }) {
  const min = (sec) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
  const errors = Object.values(s.by_type ?? {}).reduce((a, b) => a + b, 0);
  const sc = s.scenario;
  return (
    <div className="summary stack">
      <div className="cluster" style={{ gap: 16 }}>
        <svg aria-hidden="true" width="72" height="72"><use href="#onda-celebrate" /></svg>
        <div><h1>¡Buena sesión!</h1><p className="muted">{s.turns ? 'Esto es lo que hablaste hoy.' : 'No llegaste a hablar en esta sesión.'}</p></div>
      </div>
      {sc && (
        <section className="stack scenario-result">
          <div className="cluster" style={{ justifyContent: 'space-between' }}>
            <h2 className="h2">{sc.title}</h2>
            <span className="stars" role="img" aria-label={`${sc.stars} de 3 estrellas`}>
              {[1, 2, 3].map((n) => <span key={n} className={n <= sc.stars ? 'on' : undefined} aria-hidden="true">★</span>)}
            </span>
          </div>
          <GoalList goals={sc.goals} />
          {sc.comment && <p>{sc.comment}</p>}
          {sc.unused_phrases.length > 0 && (
            <div className="stack"><span className="overline">Frases útiles que no usaste</span>
              <PhraseList phrases={sc.unused_phrases} onListen={onListen} /></div>
          )}
        </section>
      )}
      <div className="tiles">
        <div className="metric-tile tint-info"><span className="overline">Duración</span><span className="metric">{min(s.duration_s ?? 0)}</span></div>
        <div className="metric-tile tint-error"><span className="overline">Tus turnos</span><span className="metric">{s.turns ?? 0}</span></div>
        <div className="metric-tile tint-warning"><span className="overline">Palabras/min</span><span className="metric">{s.wpm ?? 0}</span></div>
        <div className="metric-tile tint-success"><span className="overline">Sin errores</span><span className="metric">{s.clean_turns ?? 0}/{s.turns ?? 0}</span></div>
      </div>
      {errors > 0 && (
        <p className="muted">{errors} correcciones: {Object.entries(s.by_type).map(([t, n]) => `${n} de ${(ISSUE_TAG[t]?.[1] ?? t).toLowerCase()}`).join(', ')}.</p>
      )}
      {s.recurring?.length > 0 && (
        <section className="stack"><h2 className="h2">Errores que se repiten</h2>
          <ul className="issues">{s.recurring.map((r, i) => (
            <li key={i}><span className="tag tag-new">×{r.count}</span>
              <span><strong lang="en">{r.original} → {r.fix}</strong>: {r.explanation}</span></li>))}</ul>
        </section>
      )}
      {s.sounds?.length > 0 && (
        <section className="stack"><h2 className="h2">Sonidos para practicar</h2>
          <ul className="issues">{s.sounds.map((r, i) => (
            <li key={i}><span className="tag tag-new">×{r.count}</span>
              <span><strong lang="en">{r.words.join(', ')}</strong>: {r.tip}</span></li>))}</ul>
        </section>
      )}
      {s.phrases?.length > 0 && (
        <section className="stack"><h2 className="h2">Frases que querías decir</h2>
          <ul className="review-list">{s.phrases.map((p, i) => (
            <li key={i} className="phrase">
              <span className="small muted">{p.intent}</span>
              <span className="cluster" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
                <strong lang="en">{p.english}</strong><ListenButton text={p.english} onListen={onListen} /></span>
            </li>))}</ul>
        </section>
      )}
      {s.review?.length > 0 && (
        <section className="stack"><h2 className="h2">Frases para repasar</h2>
          <ul className="review-list">{s.review.map((r, i) => (
            <li key={i} lang="en"><s className="wrong">{r.text}</s><span>{r.corrected}</span></li>))}</ul>
        </section>
      )}
      <button className="btn btn-primary btn-l" style={{ alignSelf: 'flex-start' }} onClick={onClose}>Nueva sesión</button>
    </div>
  );
}

function HealthAlert({ health }) {
  const missing = health.backend === false ? ['el backend']
    : [!health.whisper && 'whisper-server', !health.ollama && 'Ollama'].filter(Boolean);
  return (
    <div className="alert alert-warning" role="alert">
      <span>No responde {missing.join(' ni ')}. Arranca todo con <b>iabuddy.bat</b> y recarga la página.</span>
    </div>
  );
}

// Panel de depuración: tiempos del último turno (ms desde que se cierra tu turno)
function MetricsCard({ metrics, silenceMs }) {
  const m = metrics;
  const rows = m && [
    ['Cierre del turno', m.reason === 'silencio' ? `silencio (${silenceMs} ms)` : 'tecla'],
    ['STT', `${m.stt} ms`],
    ['LLM · 1.er token', `${m.llm_token - m.stt} ms`],
    ['LLM · 1.er trozo', `${m.first_chunk - m.stt} ms`],
    ['TTS · 1.er trozo', `${m.first_audio - m.first_chunk} ms`],
    ['Servidor → 1.er audio', `${m.first_audio} ms`],
    ['Tú oyes a Buddy a los', m.client != null ? `${m.client} ms` : '—'],
  ];
  return (
    <details className="card card-tight">
      <summary className="cluster" style={{ justifyContent: 'space-between' }}>
        <h3>Tiempos</h3><span className="caption">último turno · local</span>
      </summary>
      {rows ? (
        <dl className="metrics">
          {rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      ) : <p className="muted small">Aparecen al terminar tu primer turno.</p>}
    </details>
  );
}
