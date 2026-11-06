import { useEffect, useRef, useState } from 'react';
import { useConversation } from './useConversation.js';

// Textos del dock por estado (O2Conversacion.dc.html)
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
const DAY_LABEL = new Intl.DateTimeFormat('es', { day: 'numeric', month: 'short' });
const WHEN_LABEL = new Intl.DateTimeFormat('es', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });

const NAV = [['hoy', 'Hoy'], ['conversar', 'Conversar'], ['escenarios', 'Escenarios'], ['guiada', 'Guiada'], ['palabras', 'Palabras'], ['sonidos', 'Sonidos'], ['progreso', 'Progreso']];

export default function App() {
  const c = useConversation();
  const { ui, session, summary } = c;
  const [view, setView] = useState('hoy');
  const [drillText, setDrillText] = useState('');
  const [recallKey, setRecallKey] = useState(null); // en el repaso: la palabra que estás recordando, si la hay
  const [topicId, setTopicId] = useState(null); // null = libre
  const [scenarioId, setScenarioId] = useState(null);
  const scenario = scenarioId ?? c.scenarios[0]?.id;

  const h = c.health;
  const down = h && (h.backend === false || !h.whisper || !h.ollama);
  const live = session && !session.drill; // en conversación: Sesión · Conversación · Tutor
  const canPractice = Boolean(h?.pronunciation); // la práctica no usa Whisper ni Ollama
  const busy = !h || down || ui === 'connecting'; // sin saber aún si Whisper y Ollama responden, tampoco se empieza

  const go = (next) => {
    if (next === view && session?.drill === true && !summary) return;
    if (session?.drill) c.leaveDrill();
    if (summary) c.closeSummary();
    c.clearError(); // un aviso de la sección que dejas no vale para la siguiente
    setView(next);
    if (next === 'sonidos' && canPractice) c.start({ drill: true });
  };
  const startReview = () => { setView('palabras'); c.start({ drill: 'review' }); };

  // Espacio: empezar lo que tienes delante o alternar el turno. No en campos de texto ni en el menú.
  useEffect(() => {
    const onKey = (e) => {
      if (e.code !== 'Space' || e.repeat || e.target.closest?.('input, textarea, select, nav')) return;
      const choice = view === 'hoy' || view === 'conversar' ? { topic_id: view === 'hoy' ? null : topicId }
        : view === 'escenarios' && scenario ? { scenario } : null;
      if (!session && !choice) return;
      e.preventDefault();
      if (session?.drill) {
        if (ui === 'connecting') return;
        if (recallKey) c.recallToggle(recallKey, session.drill === 'own');
        else if (drillText) c.drillToggle(drillText, session.drill === 'guided');
      }
      else if (session) { if (ui !== 'connecting') c.toggle(); }
      else if (!summary && !busy) c.start(choice);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [ui, session, summary, view, topicId, scenario, drillText, recallKey, busy, c]);

  let content;
  if (summary) {
    content = <Summary s={summary} onListen={c.listen} busy={busy} onHome={() => go('hoy')} onPractice={canPractice ? () => go('sonidos') : null}
      onRepeat={() => c.start(summary.game ? { game: true } : summary.scenario ? { scenario: summary.scenario.id } : { topic_id: summary.topic_id ?? null })} />;
  }
  else if (live) {
    content = (
      <section className="card conversation" aria-label="Conversación">
        <ChatLog messages={c.messages} feedbacks={c.feedbacks} intents={c.intents} sounds={c.sounds} onIntent={c.sendIntent} onListen={c.listen} onSaveWord={c.saveWord} />
        <Dock ui={ui} onToggle={c.toggle} />
      </section>
    );
  } else if (view === 'hoy') {
    content = <Home topics={c.topics} disabled={busy} canPractice={canPractice} onStart={c.start} onGo={go} onReview={startReview} />;
  } else if (view === 'conversar') {
    content = <section className="card conversation" aria-label="Conversar"><StartCard topics={c.topics} topicId={topicId} setTopicId={setTopicId} onStart={() => c.start({ topic_id: topicId })} disabled={busy} /></section>;
  } else if (view === 'escenarios') {
    content = <Scenarios scenarios={c.scenarios} selected={scenario} onSelect={setScenarioId} onStart={() => c.start({ scenario })} disabled={busy} onListen={c.listen} />;
  } else if (view === 'guiada') {
    const guided = session?.drill === 'guided' && c.scenarios.find((s) => s.id === session.guided);
    content = guided
      ? <section className="card conversation" aria-label="Conversación guiada"><Guided key={session.startedAt} c={c} sc={guided} setText={setDrillText} onFinish={() => go('guiada')} /></section>
      : <GuidedList scenarios={c.scenarios} ready={Boolean(canPractice && h?.whisper)} disabled={ui === 'connecting'} onStart={(id) => c.start({ drill: 'guided', guided: id })} />;
  } else if (view === 'palabras') {
    content = session?.drill === 'review'
      ? <section className="card conversation" aria-label="Repaso"><Review c={c} setText={setDrillText} setRecallKey={setRecallKey} onFinish={() => go('palabras')} /></section>
      : session?.drill === 'own'
        ? <section className="card conversation" aria-label="Tu propia frase"><OwnSentence c={c} setRecallKey={setRecallKey} onFinish={() => go('palabras')} /></section>
        : <Words canReview={canPractice} canOwn={Boolean(h?.whisper && h?.ollama)} ownDisabled={ui === 'connecting'} onReview={startReview} onOwn={() => c.start({ drill: 'own' })} onGame={() => c.start({ game: true })} onDiscard={c.discardWord} />;
  } else if (view === 'sonidos') {
    content = (
      <section className="card conversation" aria-label="Sonidos">
        {session?.drill ? <Drill c={c} setText={setDrillText} />
            : <SoundsEntry canPractice={canPractice} disabled={ui === 'connecting'} onStart={() => c.start({ drill: true })} />}
      </section>
    );
  } else if (view === 'ajustes') {
    content = <Settings c={c} />;
  } else {
    content = <section className="card conversation" aria-label="Tu progreso"><Progress canReview={canPractice} onReview={startReview} /></section>;
  }

  return (
    <div className="container app">
      <header className="topbar">
        <span className="brand"><svg aria-hidden="true" width="44" height="44"><use href="#onda-logo" /></svg>
          <span className="brand-name">iabuddy</span></span>
        {!live && (
          <nav className="nav-pill" aria-label="Principal">
            {NAV.map(([id, label]) => (
              <a key={id} href={`#${id}`} aria-current={view === id && !summary ? 'page' : undefined}
                onClick={(e) => { e.preventDefault(); go(id); }}>{label}</a>
            ))}
          </nav>
        )}
        {!live && (
          <a className="icon-btn settings-link" href="#ajustes" aria-label="Ajustes" title="Ajustes" aria-current={view === 'ajustes' && !summary ? 'page' : undefined}
            onClick={(e) => { e.preventDefault(); go('ajustes'); }}>
            <svg aria-hidden="true" width="20" height="20"><use href="#i-settings" /></svg>
          </a>
        )}
      </header>

      <main className="session">
        {down && <HealthAlert health={h} />}
        {c.error && <div className="alert alert-error" role="alert"><span>{c.error}</span></div>}

        <div className={`session-grid${live ? ' live' : ''}`}>
          {live && <SessionPanel c={c} silenceMs={c.settings?.silence_ms} />}
          {content}
          {(live || summary || view === 'conversar') && !session?.drill && <aside className="session-side">
            <TutorPanel mode={c.mode} onMode={c.changeMode} feedbacks={c.feedbacks} onListen={c.listen} game={Boolean(session?.game)} />
            {!live && <MetricsCard metrics={c.metrics} silenceMs={c.settings?.silence_ms} />}
          </aside>}
        </div>
      </main>
    </div>
  );
}

function ChatLog({ messages, feedbacks, intents, sounds, onIntent, onListen, onSaveWord }) {
  const end = useRef(null);
  // Con llaves: scrollIntoView devuelve una promesa en Chrome reciente y React la tomaría por la limpieza
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages, feedbacks, sounds]);
  return (
    <div className="chat" aria-live="polite">
      {messages.map((m, i) => (m.who === 'buddy' ? (
        <BuddyTurn key={i} m={m} onSave={onSaveWord} />
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

const COMMON_WORDS = new Set('and are but can did does for from had has have her his how its just not our she that the their them they this was were what when where who why will with would yes you your'.split(' '));

// La burbuja de Buddy: al pulsarla salen sus palabras, y pulsando una se guarda en tu banco.
function BuddyTurn({ m, onSave }) {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState({}); // palabra → 'saving' | 'saved' | 'failed'
  const panel = useRef(null);
  useEffect(() => { if (open) panel.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [open]);
  const words = [...new Set(m.text.toLowerCase().match(/[a-z][a-z'-]+/g) ?? [])].filter((w) => w.length > 2 && !w.includes("'") && !COMMON_WORDS.has(w));
  const save = async (e, word) => {
    if (e.detail !== 0) e.currentTarget.blur(); // con el foco aquí, Espacio no abriría tu turno limpiamente
    setSaved((s) => ({ ...s, [word]: 'saving' }));
    const ok = await onSave(word, m.text);
    setSaved((s) => ({ ...s, [word]: ok ? 'saved' : 'failed' }));
  };
  const LABEL = { saving: '…', saved: '✓', failed: '✗' };
  return (
    <div className="buddy-row">
      <svg aria-hidden="true" width="40" height="40" style={{ flex: 'none' }}><use href="#onda-logo" /></svg>
      <div className="buddy-turn">
        <button className="bubble bubble-buddy bubble-btn" lang="en" aria-expanded={open} title="Guardar una palabra"
          onClick={(e) => { if (e.detail !== 0) e.currentTarget.blur(); setOpen((v) => !v); }}>{m.text}{m.cut && ' …'}</button>
        {open && (
          <div className="buddy-words" ref={panel} role="group" aria-label="Guardar una palabra">
            <span className="caption">Pulsa una para guardarla en tu banco:</span>
            <div className="cluster" lang="en">
              {words.map((w) => (
                <button key={w} className="chip" disabled={saved[w] === 'saving' || saved[w] === 'saved'} onClick={(e) => save(e, w)}>
                  {w}{saved[w] && ` ${LABEL[saved[w]]}`}
                </button>
              ))}
            </div>
            {Object.values(saved).includes('failed') && <span className="small" role="alert">No pude buscar el significado. Inténtalo otra vez.</span>}
          </div>
        )}
      </div>
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
        }}>{marked(m.text, [...(fb?.issues ?? []).map((i) => i.original), ...(sounds ?? []).map((s) => s.word)], 'bad')}</button>
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
          <span><BadWords words={[s.word]} />: {s.tip}</span>
          <ListenButton text={s.word} onListen={onListen} />
        </div>
      ))}
      {state === 'failed' && !open && <span className="small muted">No pude analizar lo que escribiste. Inténtalo otra vez.</span>}
      {fb?.intent && !open ? (
        <div className="said-as">
          <LabeledText label="Así se dice" lang="en" action={<ListenButton text={fb.corrected} onListen={onListen} />}>{marked(fb.corrected, fb.issues.map((i) => i.fix), 'ok')}</LabeledText>
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

// El texto de la app: etiqueta, texto y nota, con los mismos tamaños y cajas en todas partes.
// size: body | m | l | xl · box: plain | info | ok · action: un botón a la derecha (escuchar).
// Se alinea según dónde esté: centrado en las pantallas de práctica (.drill), a la izquierda en paneles y tarjetas.
function LabeledText({ label, note, action, size = 'body', box, lang, children, ...rest }) {
  return (
    <div className={`labeled-text size-${size}${box ? ` box-${box}` : ''}${action ? ' with-action' : ''}`} {...rest}>
      {label && <span className="overline">{label}</span>}
      <div className="labeled-text-main" lang={lang}>{children}</div>
      {note && <div className="labeled-text-note">{note}</div>}
      {action && <div className="labeled-text-action">{action}</div>}
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

function Stars({ n }) {
  return (
    <span className="stars" role="img" aria-label={`${n} de 3 estrellas`}>
      {[1, 2, 3].map((i) => <span key={i} className={i <= n ? 'on' : undefined} aria-hidden="true">★</span>)}
    </span>
  );
}

// Hoy: hablar ya, y lo que te conviene con lo que hay guardado. Sin datos todavía, solo hablar.
function Home({ topics, disabled, canPractice, onStart, onGo, onReview }) {
  const [data, setData] = useState(null);
  useEffect(() => { fetch('/api/progress').then((r) => r.json()).then(setData).catch(() => {}); }, []);
  const now = new Date();
  const dayNumber = Math.floor((now - new Date(now.getFullYear(), 0, 0)) / 86400000);
  const topic = topics.length ? topics[dayNumber % topics.length] : null;
  const weekday = new Intl.DateTimeFormat('es', { weekday: 'long' }).format(now);
  const today = data?.days.at(-1)?.minutes ?? 0;
  const sound = data?.sounds[0];
  const error = data?.recurring[0];
  const turns = data?.sessions.reduce((sum, s) => sum + s.turns, 0) ?? 0;
  const clean = turns ? Math.round(data.sessions.reduce((sum, s) => sum + s.clean_pct * s.turns, 0) / turns) : 0;
  return (
    <div className="page stack">
      <section className="home-hero">
        <span className="home-day">{weekday[0].toUpperCase() + weekday.slice(1)} · {today.toLocaleString('es')} min hoy</span>
        <h1 className="display">¿Charlamos?</h1>
        <p className="body-l muted">Pulsa Espacio y cuéntame algo. Usa audífonos.</p>
        <div className="talk-btn home-talk">
          <button aria-label="Hablar con Buddy" disabled={disabled} onClick={(e) => e.detail !== 0 && onStart({ topic_id: null })}>
            <svg aria-hidden="true"><use href="#onda-idle" /></svg>
          </button>
        </div>
        <span className="dock-key"><kbd className="kbd">Espacio</kbd>para hablar</span>
      </section>
      <section className="home-cards">
        {topic && (
          <div className="card card-tight stack">
            <LabeledText label="Tema de hoy" size="m">{topic.title}</LabeledText>
            <div className="cluster">
              <button className="btn btn-primary btn-s" disabled={disabled} onClick={() => onStart({ topic_id: topic.id })}>Hablar de esto</button>
              <button className="btn btn-secondary btn-s" onClick={() => onGo('conversar')}>Otro tema</button>
            </div>
          </div>
        )}
        {data?.review_due > 0 && canPractice && (
          <div className="card card-tight stack">
            <LabeledText label="Repaso" size="m">{data.review_due} para repasar</LabeledText>
            <div className="cluster"><button className="btn btn-primary btn-s" onClick={onReview}>Repasar</button></div>
          </div>
        )}
        {sound && canPractice && (
          <div className="card card-tight stack">
            <LabeledText label="Sonido que más fallas" size="m" note={<BadWords words={sound.words.slice(0, 3)} />}><span className="ipa-inline">/{sound.phone}/</span> ×{sound.count}</LabeledText>
            <div className="cluster"><button className="btn btn-secondary btn-s" onClick={() => onGo('sonidos')}>Practicar</button></div>
          </div>
        )}
      </section>
      {data?.totals.sessions > 0 && (
        <section className="tiles" aria-label="Tus cifras">
          <div className="metric-tile tint-info"><span className="overline">Turnos hablados</span><span className="metric">{data.totals.turns}</span></div>
          <div className="metric-tile tint-warning"><span className="overline">Minutos hablando</span><span className="metric">{data.totals.minutes.toLocaleString('es')}</span></div>
          <div className="metric-tile tint-success"><span className="overline">Turnos sin errores</span><span className="metric">{clean} %</span>
            {error && <span className="small">frecuente: <FixPair original={error.original} fix={error.fix} /></span>}</div>
        </section>
      )}
    </div>
  );
}

function StartCard({ topics, topicId, setTopicId, onStart, disabled }) {
  return (
    <div className="start">
      <svg aria-hidden="true" width="120" height="120"><use href="#onda-idle" /></svg>
      <h1>¿De qué hablamos?</h1>
      <p className="body-l muted">Elige un tema o habla de lo que quieras. Pulsa Espacio para abrir tu turno y otra vez
        para cerrarlo. Usa audífonos.</p>
      <div className="cluster topics" role="group" aria-label="Tema">
        {[{ id: null, title: 'Libre' }, ...topics].map((t) => (
          <button key={t.id ?? 'libre'} className="chip" aria-pressed={topicId === t.id} onClick={() => setTopicId(t.id)}>{t.title}</button>
        ))}
      </div>
      <button className="btn btn-primary btn-l" onClick={onStart} disabled={disabled}>
        Empezar <span className="kbd-inline">Espacio</span>
      </button>
    </div>
  );
}

// Colores de los escenarios, en orden: [fondo, texto sobre él]
const SCENARIO_COLORS = [['var(--lima)', 'var(--text)'], ['var(--amarillo)', 'var(--text)'], ['var(--azul)', '#FFFFFF'], ['var(--coral)', 'var(--text)'], ['var(--rosa)', 'var(--text)']];

function Scenarios({ scenarios, selected, onSelect, onStart, disabled, onListen }) {
  const index = scenarios.findIndex((sc) => sc.id === selected);
  const sc = scenarios[index];
  const colors = (i) => SCENARIO_COLORS[i % SCENARIO_COLORS.length];
  if (!sc) return <div className="page"><span className="muted" aria-busy="true">Cargando escenarios…</span></div>;
  return (
    <div className="page stack">
      <div><h1 className="display">Escenarios</h1><p className="body-l muted">Situaciones con objetivos. 1★ al terminarla, 2★ con la mitad, 3★ con todos.</p></div>
      <div className="scenarios-page">
        <section className="scenarios-list" aria-label="Lista de escenarios">
          {scenarios.map((s, i) => (
            <button key={s.id} className="scenario-card" style={{ '--sc': colors(i)[0] }} aria-pressed={s.id === selected} onClick={() => onSelect(s.id)}>
              <span className="scenario-head">{s.stars ? <Stars n={s.stars} /> : <span className="tag tag-new">Nuevo</span>}</span>
              <span className="scenario-body"><strong className="h3">{s.title}</strong><span className="small muted">{s.goals.length} objetivos</span></span>
            </button>
          ))}
          <div className="scenario-new">
            <strong>Crea tu escenario</strong>
            <span className="small muted">Añade un YAML con rol, contexto, objetivos y frases, y reinicia la app.</span>
            <code className="small">backend/scenarios/mi_escenario.yaml</code>
          </div>
        </section>
        <aside className="card scenario-detail" aria-label="Detalle del escenario">
          <div className="scenario-hero" style={{ background: colors(index)[0], color: colors(index)[1] }}>
            <h2 className="h1">{sc.title}</h2>
            <p>{sc.description}</p>
            {sc.stars > 0 && <Stars n={sc.stars} />}
          </div>
          <div className="stack scenario-info">
            <div className="scenario-roles">
              <LabeledText label="Buddy hace de" lang="en">{sc.partner_role}</LabeledText>
              <LabeledText label="Tú eres" lang="en">{sc.user_role}</LabeledText>
            </div>
            <div className="stack"><span className="overline">Objetivos</span><GoalList goals={sc.goals.map((text) => ({ text }))} /></div>
            {sc.key_phrases.length > 0 && <div className="stack"><span className="overline">Frases útiles</span><PhraseList phrases={sc.key_phrases} onListen={onListen} /></div>}
            <button className="btn btn-primary btn-l" onClick={onStart} disabled={disabled}>Empezar <span className="kbd-inline">Espacio</span></button>
          </div>
        </aside>
      </div>
    </div>
  );
}

const SPEEDS = [0.8, 0.9, 1, 1.1];
const MODE_HELP = {
  silencioso: 'Solo hablas. Las correcciones se guardan para el resumen de la sesión.',
  panel: 'Buddy no te interrumpe: tus correcciones aparecen en el panel del tutor.',
  voz: 'Buddy te corrige en la conversación. En el panel tienes todos los errores, explicados en español.',
};

function Settings({ c }) {
  const v = c.settings;
  const h = c.health;
  const { checkHealth } = c;
  const [sample, setSample] = useState('idle');
  useEffect(() => { checkHealth(); }, [checkHealth]);
  if (!v) return <div className="page"><span className="muted" aria-busy="true">Cargando ajustes…</span></div>;
  const seconds = (ms) => `${(ms / 1000).toLocaleString('es', { minimumFractionDigits: 1 })} s`;
  const trySample = () => {
    const audio = new Audio('/api/voice-sample');
    setSample('loading');
    audio.onplaying = () => setSample('playing');
    audio.onended = () => setSample('idle');
    audio.onerror = () => setSample('failed');
    audio.play().catch(() => setSample('failed'));
  };
  const models = [
    ['Voz a texto', 'whisper-server', h?.whisper],
    ['Modelo de lenguaje', `Ollama · ${h?.model ?? '…'}`, h?.ollama],
    ['Voz', `Kokoro · ${h?.voice ?? '…'}`, h && h.backend !== false],
    ['Pronunciación', 'wav2vec2 + eSpeak', h?.pronunciation],
  ];
  return (
    <div className="page stack">
      <h1>Ajustes</h1>
      <section className="card stack">
        <h2 className="h2">Conversación</h2>
        <div className="setting">
          <div className="cluster" style={{ justifyContent: 'space-between' }}>
            <label htmlFor="silence"><strong>Silencio para cerrar tu turno</strong></label><strong>{seconds(v.silence_ms)}</strong>
          </div>
          <input id="silence" type="range" min="400" max="2000" step="100" value={v.silence_ms}
            aria-valuetext={seconds(v.silence_ms)} onChange={(e) => c.saveSettings({ silence_ms: Number(e.target.value) })} />
          <div className="cluster caption" style={{ justifyContent: 'space-between' }}><span>0,4 s · más ágil</span><span>2 s · más paciente</span></div>
        </div>
        <div className="setting setting-row">
          <div><strong>Velocidad de la voz de Buddy</strong><p className="small muted">Se aplica desde la próxima frase. Voz en inglés americano.</p></div>
          <div className="cluster">
            <div className="segmented" role="group" aria-label="Velocidad">
              {SPEEDS.map((n) => <button key={n} aria-pressed={v.speed === n} onClick={() => c.saveSettings({ speed: n })}>{n.toLocaleString('es', { minimumFractionDigits: 1 })}×</button>)}
            </div>
            <button className="btn btn-secondary btn-s" disabled={sample === 'loading' || sample === 'playing'} onClick={trySample}>
              {sample === 'loading' ? 'Preparando…' : sample === 'playing' ? 'Sonando…' : 'Probar voz'}
            </button>
          </div>
        </div>
        {sample === 'failed' && <p className="small" role="alert">No se pudo reproducir la voz de prueba.</p>}
      </section>
      <section className="card stack">
        <h2 className="h2">Corrección</h2>
        <div className="setting setting-row">
          <div><strong>Cómo te corrige el tutor</strong><p className="small muted">{MODE_HELP[c.mode]}</p></div>
          <div className="segmented" role="group" aria-label="Modo de corrección">
            {MODES.map(([id, label]) => <button key={id} aria-pressed={c.mode === id} onClick={() => c.changeMode(id)}>{label}</button>)}
          </div>
        </div>
      </section>
      <section className="card stack">
        <div className="cluster" style={{ justifyContent: 'space-between' }}>
          <h2 className="h2">Modelos locales</h2>
          {h?.models_dir && <span className="small muted">Carpeta: <code>{h.models_dir}</code></span>}
        </div>
        <div className="model-list">
          {models.map(([name, detail, ok]) => (
            <div className="model-row" key={name}>
              <span className={`model-dot${ok ? ' ok' : ''}`} aria-hidden="true" />
              <span className="model-name"><strong>{name}</strong><span className="small muted">{detail}</span></span>
              <span className="small">{ok ? 'listo' : h ? 'no responde' : '…'}</span>
            </div>
          ))}
        </div>
        <p className="small muted">Usa audífonos: así el micrófono no capta la voz de Buddy.</p>
      </section>
    </div>
  );
}

// Sonidos sin práctica abierta: falta el modelo, o el micrófono no se pudo abrir
function SoundsEntry({ canPractice, disabled, onStart }) {
  return (
    <div className="start">
      <svg aria-hidden="true" width="120" height="120"><use href="#onda-idle" /></svg>
      <h1>Sonidos</h1>
      {canPractice ? (
        <>
          <p className="body-l muted">Lee frases en voz alta y mira qué sonidos revisar.</p>
          <button className="btn btn-primary btn-l" onClick={onStart} disabled={disabled}>Empezar a practicar</button>
        </>
      ) : <p className="body-l muted">Para practicar hace falta el modelo de pronunciación.</p>}
    </div>
  );
}

const DRILL_STATUS = {
  ...STATUS,
  idle: ['Te toca leer', 'Escúchala si quieres y léela en voz alta.', 'para empezar a leer', 'Leer la frase'],
  thinking: ['Analizando…', 'Comparo tu voz con los sonidos de la frase. Si no habías terminado, sigue leyendo.', 'para seguir leyendo', 'Seguir leyendo'],
  speaking: ['Escucha', 'Buddy lee la frase.', 'para empezar a leer', 'Leer la frase'],
};
const RECALL_STATUS = { ...DRILL_STATUS, idle: ['Te toca recordar', 'Intenta decir la frase correcta.', 'para responder', 'Responder'] };
const SAY_STATUS = {
  ...DRILL_STATUS,
  idle: ['Dilo en inglés', 'Di en voz alta una frase completa.', 'para responder', 'Responder'],
  thinking: ['Transcribiendo…', 'Busco la palabra en tu frase. Si no habías terminado, sigue hablando.', 'para seguir hablando', 'Seguir hablando'],
};

function PhraseProgress({ index, total }) {
  return (
    <div className="review-progress">
      <span className="small">Frase {index + 1} de {total}</span>
      <div className="review-steps" aria-hidden="true">{Array.from({ length: total }, (_, i) => <span key={i} className={i <= index ? 'done' : undefined} />)}</div>
    </div>
  );
}

// La frase y, tras leerla, qué se oyó en cada palabra. Sin notas por palabra: la confianza del modelo no es una
// calificación (bien dicha, una frase da 40-70) y solo se marcan los errores típicos que ganan con margen claro.
function PhraseCheck({ text, result, onListen, compact, good, note }) {
  const [picked, setPicked] = useState({});
  const listen = <ListenButton text={text} onListen={onListen} />;
  if (!result) return <LabeledText size="l" box="plain" lang="en" action={listen} note={note} aria-live="polite">{marked(text, good ?? [], 'target')}</LabeledText>;

  const targets = new Set((good ?? []).flatMap((g) => g.toLowerCase().split(/[^a-z0-9'’]+/)));
  const flagged = (w) => w.issues.length > 0 || w.unclear || w.missing;
  const any = result.words.some(flagged);
  const state = (w) => (w.missing ? ['bad', 'no la oí'] : w.issues.length ? ['bad', 'a revisar'] : w.unclear ? ['unclear', 'no se oyó con claridad'] : any || result.passed ? ['ok', 'sin errores claros'] : ['none', '']);
  const first = Math.max(result.words.findIndex(flagged), 0);
  const selected = picked.result === result ? picked.index : first; // una lectura nueva vuelve a la primera a revisar
  const word = result.words[selected];
  return (
    <>
      <LabeledText size="l" box="plain" lang="en" action={listen} note={note} aria-live="polite">
        <div className="word-scores">
          {result.words.map((w, i) => (
            <button key={i} className={`word-score ${state(w)[0]}${targets.has(w.word.toLowerCase()) ? ' target' : ''}`} aria-pressed={i === selected} aria-label={`${w.word}: ${state(w)[1] || 'sin analizar'}`}
              onClick={() => setPicked({ result, index: i })}>{w.word}</button>
          ))}
        </div>
      </LabeledText>
      <div className="cluster" aria-live="polite">
        <strong>{any ? 'Revisa estas palabras' : result.passed ? '¡Sin errores claros!' : 'No te entendí bien esta frase. ¿La repites?'}</strong>
        {result.grade == null && <span className="caption">claridad {result.score}/100</span>}
      </div>
      {word && (any || (result.passed && !compact)) && <WordDetail word={word} onListen={onListen} />}
    </>
  );
}

function WordDetail({ word, onListen }) {
  const heard = (p) => word.issues.find((i) => i.phone === p)?.heard;
  return (
    <div className="word-detail">
      <div className="stack word-phones">
        <div className="cluster"><span className="h2" lang="en">{word.word}</span><ListenButton text={word.word} onListen={onListen} /></div>
        <div className="phones">
          {word.phones.map((p, i) => (
            <span key={i} className="phone">
              <span className={heard(p) ? 'ipa bad' : 'ipa'}>{p}</span>
              {heard(p) && <span className="ipa heard">{heard(p)}</span>}
            </span>
          ))}
        </div>
        {word.issues.length > 0 && <span className="caption">Arriba, el sonido esperado (en-us). Abajo, el error típico que se oyó.</span>}
      </div>
      <div className="word-tip">
        <LabeledText label="Cómo mejorarlo">
          {word.issues.map((i) => <p key={i.phone}><strong className="ipa-inline">/{i.phone}/ → /{i.heard}/</strong> {i.tip}</p>)}
          {!word.issues.length && <p>{word.missing ? 'No la oí en tu frase. Escúchala y repítela.' : word.unclear ? 'No se oyó con claridad. Escúchala y repite la frase.' : 'No se oyó ningún error típico en esta palabra.'}</p>}
        </LabeledText>
      </div>
    </div>
  );
}

// Práctica de pronunciación: tus frases falladas y frases por sonido, primero los sonidos que más fallas.
function Drill({ c, setText }) {
  const failed = c.drills?.failed ?? [];
  const failedGroup = failed.length ? [{ title: 'Tus frases', hint: `${failed.length} con sonidos pendientes`, sentences: failed.map((f) => f.text),
    targets: Object.fromEntries(failed.map((f) => [f.text, f.words])) }] : [];
  const groups = [...failedGroup, ...(c.drills?.sounds ?? [])];
  const [group, setGroup] = useState(0);
  const [index, setIndex] = useState(0);
  const sentences = groups[group]?.sentences ?? [];
  const position = index % (sentences.length || 1);
  const current = sentences[position] ?? '';
  useEffect(() => { setText(current); }, [current, setText]);
  const result = c.drillResult?.text === current ? c.drillResult : null;
  if (!c.drills) return <div className="start"><span className="muted" aria-busy="true">Preparando las frases…</span></div>;
  return (
    <>
      <div className="drill-layout">
        <div className="drill-sounds" role="group" aria-label="Qué quieres practicar">
          <span className="overline">Qué practicar</span>
          {groups.map((g, i) => {
            const [, examples, ipa] = g.title.match(/«(.+)»\s*(.+)/) ?? [];
            return (
              <button key={g.title} className="sound-row" aria-pressed={group === i} onClick={() => { setGroup(i); setIndex(0); }}>
                {ipa && <span className="sound-ipa">{ipa}</span>}
                <span className="sound-text">
                  <strong lang={examples ? 'en' : undefined}>{examples ?? g.title}</strong>
                  <span className="caption">{g.hint ?? (g.errors ? `${g.errors} ${g.errors === 1 ? 'error tuyo' : 'errores tuyos'}` : 'Sin errores tuyos')}</span>
                </span>
              </button>
            );
          })}
        </div>
        <div className="drill stack">
          <PhraseProgress index={position} total={sentences.length} />
          <PhraseCheck text={current} result={result} onListen={c.listen} good={groups[group]?.targets?.[current]} />
          <button className="btn btn-secondary btn-s" onClick={() => setIndex((n) => n + 1)}>Siguiente frase</button>
        </div>
      </div>
      <Dock ui={c.ui} status={DRILL_STATUS} onToggle={() => c.drillToggle(current)} />
    </>
  );
}

const OWN_STATUS = {
  ...DRILL_STATUS,
  idle: ['Tu propia frase', 'Inventa una frase sobre tu vida o tu trabajo.', 'para responder', 'Responder'],
  thinking: ['Revisando…', 'Busco la palabra y el tutor mira cómo la usaste. Si no habías terminado, sigue hablando.', 'para seguir hablando', 'Seguir hablando'],
};

// Tu propia frase: con la palabra a la vista, inventas una frase y el tutor te dice si la usaste bien.
// No mueve las cajas del repaso: con la palabra delante no demuestra que la recuerdes.
function OwnSentence({ c, setRecallKey, onFinish }) {
  if (!c.drills) return <div className="start"><span className="muted" aria-busy="true">Preparando tus palabras…</span></div>;
  return <OwnRound c={c} setRecallKey={setRecallKey} onFinish={onFinish} />;
}

function OwnRound({ c, setRecallKey, onFinish }) {
  const queue = c.drills.own;
  const [index, setIndex] = useState(0);
  const [example, setExample] = useState(false);
  const [good, setGood] = useState(0);
  const item = queue[index];
  const key = item?.key ?? null;
  useEffect(() => { setRecallKey(key); return () => setRecallKey(null); }, [key, setRecallKey]);
  const recall = c.recallResult?.key === key ? c.recallResult : null;
  const usage = c.usageResult?.key === key ? c.usageResult : null;
  const busy = c.ui === 'listening' || c.ui === 'thinking';

  const next = () => {
    if (usage?.ok) setGood((n) => n + 1);
    setIndex((i) => i + 1);
    setExample(false);
  };

  if (!item) {
    return (
      <div className="start">
        <svg aria-hidden="true" width="120" height="120"><use href="#onda-idle" /></svg>
        <h1>{queue.length ? '¡Tanda terminada!' : 'Aún no tienes palabras'}</h1>
        {queue.length > 0 && <p>Usaste bien {good} de {queue.length}.</p>}
        <div className="cluster" style={{ justifyContent: 'center' }}>
          {queue.length > 0 && <button className="btn btn-primary" onClick={() => c.start({ drill: 'own' })}>Otra tanda</button>}
          <button className={`btn ${queue.length ? 'btn-secondary' : 'btn-primary'}`} onClick={onFinish}>Terminar</button>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="drill stack">
        <PhraseProgress index={index} total={queue.length} />
        <LabeledText label="Tu palabra" size="xl" lang="en" note={!same(item.meaning, item.term) && <span lang="es">{item.meaning}</span>}>{item.term}</LabeledText>
        {example
          ? <LabeledText label="Un ejemplo" size="m" box="plain" lang="en">{marked(item.text, [item.target], 'target')}</LabeledText>
          : <LabeledText box="plain" note={<button className="btn btn-secondary btn-s" onClick={() => setExample(true)}>Ver un ejemplo</button>}><span className="muted">Inventa una frase con ella, sobre tu vida o tu trabajo.</span></LabeledText>}
        {recall && (
          <LabeledText label="Te oí" box="info" lang="en" role="status"
            note={!recall.used ? (recall.too_short ? 'Di una frase completa: con palabras sueltas me cuesta entenderte.' : 'No oí la palabra en tu frase. ¿La intentas otra vez?')
              : recall.checking && !usage ? <span className="muted" aria-busy="true">El tutor está revisando tu frase…</span>
                : usage?.failed && 'Oí la palabra, pero el tutor no pudo revisar la frase.'}>{marked(recall.text, [recall.match], 'ok')}</LabeledText>
        )}
        {usage && !usage.failed && (
          <div className={`card card-tight ${usage.ok ? 'feedback-ok' : 'stack feedback'}`} role="status">
            <strong>{usage.ok ? '¡Bien usada!' : 'Todavía no'}</strong>
            <span className="small">{usage.comment}</span>
            {usage.corrected && (
              <LabeledText label="Mejor así" lang="en" action={<ListenButton text={usage.corrected} onListen={c.listen} />}>{usage.corrected}</LabeledText>
            )}
          </div>
        )}
        <div className="cluster">
          <button className={`btn ${usage ? 'btn-primary' : 'btn-secondary'}`} disabled={busy} onClick={next}>{usage ? 'Siguiente' : 'Saltar esta palabra'}</button>
        </div>
      </div>
      <Dock ui={c.ui} status={OWN_STATUS} onToggle={() => c.recallToggle(item.key, true)} />
    </>
  );
}

const GUIDED_STATUS = {
  ...DRILL_STATUS,
  idle: ['Te toca', 'Di la frase en voz alta.', 'para hablar', 'Decir la frase'],
  thinking: ['Calificando…', 'Comparo tu voz con la frase. Si no habías terminado, sigue hablando.', 'para seguir hablando', 'Seguir hablando'],
  speaking: ['Buddy habla', 'Cuando termine, di tu frase.', 'para hablar ya', 'Decir la frase'],
};
const guidedStars = (grade) => (grade >= 90 ? 3 : grade >= 75 ? 2 : 1);

// Guiada: elige una conversación. Salen de los escenarios que traen diálogo en su YAML.
function GuidedList({ scenarios, ready, disabled, onStart }) {
  const list = scenarios.filter((s) => s.guided);
  return (
    <div className="page stack">
      <div><h1 className="display">Conversación guiada</h1>
        <p className="body-l muted">Buddy dice su parte y yo te doy tus frases. Las dices en voz alta y cada una lleva nota.</p></div>
      {!ready && <p className="small muted">Hacen falta Whisper y el modelo de pronunciación.</p>}
      <section className="scenarios-list" aria-label="Conversaciones">
        {list.map((s, i) => (
          <button key={s.id} className="scenario-card" style={{ '--sc': SCENARIO_COLORS[i % SCENARIO_COLORS.length][0] }} disabled={!ready || disabled} onClick={() => onStart(s.id)}>
            <span className="scenario-head">{s.guided_best != null ? <Stars n={guidedStars(s.guided_best)} /> : <span className="tag tag-new">Nueva</span>}</span>
            <span className="scenario-body">
              <strong className="h3">{s.title}</strong>
              <span className="small muted">{s.guided.turns.length} frases{s.guided_best != null && ` · tu mejor nota: ${s.guided_best} %`}</span>
            </span>
          </button>
        ))}
      </section>
    </div>
  );
}

// Conversación guiada: Buddy dice su parte, tú dices la frase que te toca y cada una lleva nota.
function Guided({ c, sc, setText, onFinish }) {
  const { turns, closing } = sc.guided;
  const [index, setIndex] = useState(0);
  const [best, setBest] = useState([]); // el mejor intento de cada frase: nota y palabras
  const turn = turns[index];
  const current = turn?.you ?? '';
  useEffect(() => { setText(current); }, [current, setText]);
  const result = c.drillResult?.text === current && c.drillResult.grade != null ? c.drillResult : null;
  const overall = Math.round(best.reduce((sum, b) => sum + b.grade, 0) / turns.length);

  useEffect(() => {
    if (result) setBest((b) => { const next = [...b]; if (!next[index] || result.grade >= next[index].grade) next[index] = result; return next; });
  }, [result, index]);

  // Buddy dice su frase en cuanto no hay nada sonando; una sola vez por frase
  const spoken = useRef(-1);
  const { listen, saveGuided, ui } = c;
  useEffect(() => {
    if (ui === 'idle' && spoken.current !== index) {
      spoken.current = index;
      listen(turn?.buddy ?? closing);
    }
  }, [ui, index, turn, closing, listen]);

  const saved = useRef(false);
  useEffect(() => {
    if (!turn && !saved.current) {
      saved.current = true;
      saveGuided(sc.id, overall);
    }
  }, [turn, sc.id, overall, saveGuided]);

  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [index]);

  if (!turn) {
    return (
      <div className="guided-end stack">
        <div className="cluster" style={{ justifyContent: 'space-between' }}>
          <div className="stack"><span className="overline">{sc.title}</span><h1>¡Conversación terminada!</h1><Stars n={guidedStars(overall)} /></div>
          <span className="metric">{overall} %</span>
        </div>
        <p className="muted" lang="en">{closing}</p>
        <ul className="review-list">
          {turns.map((t, i) => (
            <li key={t.you} className="word-item">
              <span className="word-item-text"><span lang="en"><SaidWords text={t.you} words={best[i]?.words ?? []} /></span></span>
              <strong>{best[i]?.grade} %</strong>
            </li>
          ))}
        </ul>
        <p className="small muted">La nota es el porcentaje de palabras que se entendieron y sin errores claros de sonido.</p>
        <div className="cluster">
          <button className="btn btn-primary" disabled={ui !== 'idle' || !c.health?.ollama} onClick={() => c.start({ scenario: sc.id })}>Ahora sin guion</button>
          <button className="btn btn-secondary" disabled={ui !== 'idle'} onClick={() => c.start({ drill: 'guided', guided: sc.id })}>Repetirla</button>
          <button className="btn btn-secondary" onClick={onFinish}>Terminar</button>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="chat">
        {turns.slice(0, index + 1).map((t, i) => (
          <div className="stack" key={t.you}>
            <div className="buddy-row">
              <svg aria-hidden="true" width="40" height="40" style={{ flex: 'none' }}><use href="#onda-logo" /></svg>
              <span className="bubble bubble-buddy" lang="en">{t.buddy}</span>
            </div>
            {i < index && (
              <div className="your-turn">
                <span className="bubble bubble-you" lang="en"><SaidWords text={t.you} words={best[i]?.words ?? []} /></span>
                <span className="caption">{best[i]?.grade} %</span>
              </div>
            )}
          </div>
        ))}
        <div ref={end} />
      </div>
      <div className="drill stack guided-line">
        <div className="cluster" style={{ justifyContent: 'space-between' }}>
          <span className="overline">Te toca decir · {index + 1} de {turns.length}</span>
          {result && (
            <span className="cluster">
              <strong className="h2" role="status">{result.grade} %</strong>
              <button className="btn btn-primary btn-s" disabled={ui === 'listening' || ui === 'thinking'} onClick={() => setIndex((i) => i + 1)}>Siguiente</button>
            </span>
          )}
        </div>
        <PhraseCheck text={current} result={result} onListen={c.listen} compact note={turn.es} />
        {result && <span className="small">Te oí: <span lang="en">{result.heard || '(nada)'}</span>. Pulsa Espacio para repetirla; vale tu mejor nota.</span>}
      </div>
      <Dock ui={c.ui} status={GUIDED_STATUS} onToggle={() => c.drillToggle(current, true)} />
    </>
  );
}

// Repaso: primero intentas recordar, hablando. Si no se puede comprobar hablando (una frase larga, o sin
// Whisper), la ves y dices tú si la sabías. Whisper también se equivoca: el «La sabía» sigue a mano tras ver la frase.
function Review({ c, setText, setRecallKey, onFinish }) {
  // Al pedir otra tanda, drills vuelve a null: ReviewRound se desmonta y empieza de cero
  if (!c.drills) return <div className="start"><span className="muted" aria-busy="true">Preparando las frases…</span></div>;
  return <ReviewRound c={c} setText={setText} setRecallKey={setRecallKey} onFinish={onFinish} />;
}

function ReviewRound({ c, setText, setRecallKey, onFinish }) {
  const review = c.drills.review;
  const [again, setAgain] = useState([]); // las que no sabías vuelven al final de la tanda
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [status, setStatus] = useState(null); // lo que dice el backend tras guardar tu última respuesta
  const [gone, setGone] = useState([]); // las que dijiste que no dijiste: no cuentan en el resultado
  const queue = [...review, ...again];
  const item = queue[index];
  const current = item?.text ?? '';
  useEffect(() => { setText(current); }, [current, setText]);
  const result = c.drillResult?.text === current ? c.drillResult : null;
  const reading = c.ui === 'listening' || c.ui === 'thinking';
  const recall = item && c.recallResult?.key === item.key ? c.recallResult : null;
  const hidden = !revealed && !result && !recall?.used; // primero intentas recordarla
  const canRecall = Boolean(item?.speakable && c.health?.whisper);
  const recalling = canRecall && hidden;
  const recallKey = recalling ? item.key : null;
  useEffect(() => { setRecallKey(recallKey); return () => setRecallKey(null); }, [recallKey, setRecallKey]);

  const answer = (known) => {
    c.answerReview(item.key, known).then((s) => s && setStatus(s));
    if (!known) setAgain((a) => [...a, item]);
    setIndex((i) => i + 1);
    setRevealed(false);
  };

  const discard = () => {
    c.discardWord(item.key).then((s) => s && setStatus(s));
    setGone((g) => [...g, item.key]);
    setIndex((i) => i + 1);
    setRevealed(false);
  };

  if (!item) {
    const missed = new Set(again.map((i) => i.key).filter((k) => !gone.includes(k))).size;
    const total = review.length - gone.length;
    const pending = status?.pending ?? 0;
    return (
      <div className="start">
        <svg aria-hidden="true" width="120" height="120"><use href="#onda-idle" /></svg>
        <h1>{review.length ? '¡Repaso terminado!' : 'No tienes nada por repasar'}</h1>
        {total > 0 && <p>Sabías {total - missed} de {total} a la primera.</p>}
        {!pending && status?.next_due && <p className="muted">La siguiente vuelve el {WHEN_LABEL.format(status.next_due * 1000)}.</p>}
        <div className="cluster" style={{ justifyContent: 'center' }}>
          {pending > 0 && <button className="btn btn-primary" onClick={() => c.start({ drill: 'review' })}>Seguir repasando ({pending})</button>}
          <button className={`btn ${pending ? 'btn-secondary' : 'btn-primary'}`} onClick={onFinish}>Terminar</button>
        </div>
      </div>
    );
  }

  const prompt = recalling ? (item.kind === 'word' ? '¿Qué palabra es? Úsala en una frase, en voz alta.' : '¿Cómo se dice bien? Dilo en una frase completa.')
    : item.kind === 'word' ? '¿Qué palabra es? Piénsala y mira la frase.' : '¿Cómo se dice bien? Dilo en voz alta o mira la frase.';
  return (
    <>
      <div className="drill stack">
        <PhraseProgress index={index} total={queue.length} />
        <LabeledText label={item.kind === 'word' ? 'Significa' : item.intent ? 'Querías decir' : 'Antes dijiste'} size="m" lang={item.kind === 'fix' ? 'en' : undefined}
          note={item.kind === 'fix' && <button className="btn btn-secondary btn-s" onClick={discard}>Esto no lo dije</button>}>
          {item.kind === 'fix' ? <span className="word-mark bad">{item.said}</span> : item.meaning}
        </LabeledText>
        {hidden ? (
          <LabeledText box="plain" note={<button className="btn btn-secondary btn-s" onClick={() => setRevealed(true)}>Ver la frase</button>}><span className="muted">{prompt}</span></LabeledText>
        ) : (
          <>
            {recall?.used && <LabeledText label="¡La usaste!" box="ok" lang="en" role="status">{marked(recall.text, [recall.match], 'ok')}</LabeledText>}
            {item.kind === 'word' && <LabeledText label="La palabra" size="xl" lang="en">{item.term}</LabeledText>}
            <PhraseCheck text={current} result={result} onListen={c.listen} good={[item.target]} />
            {item.explanation && <LabeledText label="Por qué" box="info">{item.explanation}</LabeledText>}
            {recall?.used ? (
              <div className="cluster"><button className="btn btn-primary" disabled={reading} onClick={() => answer(true)}>Siguiente</button></div>
            ) : (
              <div className="cluster">
                <button className="btn btn-primary" disabled={reading} onClick={() => answer(true)}>La sabía</button>
                <button className="btn btn-secondary" disabled={reading} onClick={() => answer(false)}>Repasarla otra vez</button>
              </div>
            )}
          </>
        )}
        {recall && !recall.used && (
          <LabeledText label="Te oí" box="info" lang="en" role="status"
            note={recall.too_short ? 'Di una frase completa: con palabras sueltas me cuesta entenderte.' : hidden ? 'No oí la palabra. Inténtalo otra vez o mira la frase.' : 'No oí la palabra en tu frase. Si la dijiste, marca «La sabía».'}>{recall.text}</LabeledText>
        )}
      </div>
      {/* Con una palabra oculta y sin Whisper no hay nada que leer: tu frase no se puede comparar con la del ejemplo */}
      {recalling ? <Dock ui={c.ui} status={SAY_STATUS} onToggle={() => c.recallToggle(item.key)} />
        : (!hidden || item.kind !== 'word') && <Dock ui={c.ui} status={hidden ? RECALL_STATUS : DRILL_STATUS} onToggle={() => c.drillToggle(current)} />}
    </>
  );
}

// Si escribiste en inglés lo que querías decir, su «significado» es la misma frase
const same = (a, b) => a.toLowerCase().replace(/[^a-z]/g, '') === b.toLowerCase().replace(/[^a-z]/g, '');

// Palabras: tu banco. Lo que entra por misiones, lo que guardas del chat y lo que corrige el tutor.
function Words({ canReview, canOwn, ownDisabled, onReview, onOwn, onGame, onDiscard }) {
  const [data, setData] = useState(null);
  useEffect(() => { fetch('/api/words').then((r) => r.json()).then(setData).catch(() => setData({ items: [], review_due: 0, failed: true })); }, []);
  const remove = (key) => onDiscard(key).then((s) => {
    if (s) fetch('/api/words').then((r) => r.json()).then(setData).catch(() => {});
  });
  if (!data) return <div className="page"><span className="muted" aria-busy="true">Cargando tus palabras…</span></div>;
  return (
    <div className="page stack">
      <div><h1 className="display">Palabras</h1>
        <p className="body-l muted">En cada conversación te propongo unas pocas para que las uses. También puedes guardar las que oigas: pulsa una burbuja de Buddy.</p></div>
      {data.review_due > 0 && (
        <section className="review-banner">
          <strong>Tienes {data.review_due} para repasar</strong>
          {canReview ? <button className="btn btn-primary" onClick={onReview}>Repasar</button>
            : <span className="small muted">Para repasar hace falta el modelo de pronunciación.</span>}
        </section>
      )}
      {data.practicable > 0 && (
        <section className="review-banner">
          <div><strong>Tu propia frase</strong>
            <p className="small muted">Inventa frases con tus palabras y el tutor te dice si las usaste bien.</p></div>
          {canOwn ? <button className="btn btn-primary" disabled={ownDisabled} onClick={onOwn}>Practicar</button>
            : <span className="small muted">Hacen falta Whisper y Ollama.</span>}
        </section>
      )}
      {data.guessable > 0 && (
        <section className="review-banner">
          <div><strong>Buddy adivina</strong>
            <p className="small muted">Describe tus palabras en inglés, sin decirlas, y Buddy intenta adivinarlas.</p></div>
          {canOwn ? <button className="btn btn-primary" disabled={ownDisabled} onClick={onGame}>Jugar</button>
            : <span className="small muted">Hacen falta Whisper y Ollama.</span>}
        </section>
      )}
      {data.failed && <div className="alert alert-error" role="alert"><span>No se pudieron cargar tus palabras.</span></div>}
      {!data.failed && !data.items.length && <div className="empty"><span className="small muted">Aún no hay nada aquí. Habla con Buddy: las palabras de tu primera misión aparecerán al terminar.</span></div>}
      {data.items.length > 0 && (
        <ul className="review-list">
          {data.items.map((i) => (
            <li key={i.key} className="word-item">
              <span className="word-item-text">
                <strong lang="en">{i.term}</strong>
                <span className="small">{i.kind === 'fix' && <>Antes dijiste <span lang="en" className="word-mark bad">{i.said}</span>. </>}{same(i.meaning, i.term) ? '' : i.meaning}</span>
                {i.kind === 'word' && <span className="small muted" lang="en">{i.text}</span>}
                <span className="caption">{i.due <= data.now ? 'Para repasar' : `Vuelve el ${DAY_LABEL.format(i.due * 1000)}`}</span>
              </span>
              <button className="btn btn-secondary btn-s" aria-label={`Quitar ${i.term}`} onClick={() => remove(i.key)}>Quitar</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Tope redondo del eje: 1, 2 o 5 por una potencia de 10
function niceMax(value) {
  const base = 10 ** Math.floor(Math.log10(value || 1));
  return [1, 2, 5, 10].map((n) => n * base).find((n) => n >= value);
}

// Gráfica de una sola serie (el título la nombra). Las marcas son finas y las guías, discretas.
const CHART = { w: 420, h: 170, left: 34, right: 16, top: 16, bottom: 24 };
function Chart({ title, kind, points, max, unit }) {
  const [hover, setHover] = useState(null);
  const { w, h, left, right, top, bottom } = CHART;
  const top_ = max ?? niceMax(Math.max(...points.map((p) => p.value), 1));
  const plotW = w - left - right;
  const y = (v) => h - bottom - (v / top_) * (h - top - bottom);
  const band = plotW / Math.max(points.length, 1);
  const x = (i) => left + band * (i + 0.5);
  const last = points.at(-1);
  const current = hover === null ? null : points[hover];
  return (
    <figure className="chart card card-tight">
      <figcaption>{title}</figcaption>
      {points.length === 0 ? <p className="small muted">Aún no hay datos.</p> : (
        <div className="chart-plot">
          <svg viewBox={`0 0 ${w} ${h}`} role="img"
            aria-label={`${title}. ${points.map((p) => `${p.label}: ${p.value} ${unit}`).join('; ')}`}
            onMouseLeave={() => setHover(null)}>
            {[0, top_ / 2, top_].map((t) => (
              <g key={t}>
                <line x1={left} x2={w - right} y1={y(t)} y2={y(t)} stroke="var(--border-subtle)" />
                <text x={left - 6} y={y(t) + 4} textAnchor="end" className="chart-tick">{t}</text>
              </g>
            ))}
            {hover !== null && kind === 'line' && <line x1={x(hover)} x2={x(hover)} y1={top} y2={h - bottom} stroke="var(--border-control)" />}
            {kind === 'bars' ? points.map((p, i) => {
              if (!p.value) return null;
              const bw = Math.min(band - 2, 22); // 2 px de aire entre barras
              const bx = x(i) - bw / 2;
              const by = y(p.value);
              const r = Math.min(4, bw / 2, h - bottom - by);
              return (
                <path key={i} fill="var(--chart-1)" opacity={hover === null || hover === i ? 1 : 0.55}
                  d={`M${bx} ${h - bottom}V${by + r}Q${bx} ${by} ${bx + r} ${by}H${bx + bw - r}Q${bx + bw} ${by} ${bx + bw} ${by + r}V${h - bottom}Z`} />
              );
            }) : (
              <>
                <polyline fill="none" stroke="var(--chart-1)" strokeWidth="2" strokeLinejoin="round"
                  points={points.map((p, i) => `${x(i)},${y(p.value)}`).join(' ')} />
                {points.map((p, i) => (
                  <circle key={i} cx={x(i)} cy={y(p.value)} r={hover === i ? 5 : 4} fill="var(--chart-1)" stroke="var(--surface)" strokeWidth="2" />
                ))}
                <text x={Math.min(x(points.length - 1), w - right - 2)} y={Math.max(y(last.value) - 10, 11)} textAnchor="end" className="chart-value">{last.value}</text>
              </>
            )}
            {kind === 'bars' ? points.map((p, i) => <text key={i} x={x(i)} y={h - 6} textAnchor="middle" className="chart-tick">{p.label}</text>) : (
              <>
                <text x={left} y={h - 6} className="chart-tick">{points[0].label}</text>
                {last.label !== points[0].label && <text x={w - right} y={h - 6} textAnchor="end" className="chart-tick">{last.label}</text>}
              </>
            )}
            {points.map((_, i) => (
              <rect key={i} x={x(i) - band / 2} y={top} width={band} height={h - top - bottom} fill="transparent" onMouseEnter={() => setHover(i)} />
            ))}
          </svg>
          {current && (
            <div className="chart-tip" role="status"
              style={{ left: `${(x(hover) / w) * 100}%`, transform: `translateX(${x(hover) > w * 0.7 ? '-100%' : x(hover) < w * 0.3 ? '0' : '-50%'})` }}>
              <span className="small muted">{current.tip}</span> <strong>{current.value} {unit}</strong>
            </div>
          )}
        </div>
      )}
    </figure>
  );
}

// Tu progreso: se calcula de lo guardado; los errores nunca restan, solo orientan qué practicar.
const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const WEEKDAYS = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
const WEEKDAY_NAMES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

// El mes en curso: qué días practicaste. Sin meta diaria, solo cuenta si hablaste.
function MonthCalendar({ minutes }) {
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth();
  const count = new Date(year, month + 1, 0).getDate();
  const blanks = (new Date(year, month, 1).getDay() + 6) % 7; // la semana empieza en lunes
  const title = new Intl.DateTimeFormat('es', { month: 'long', year: 'numeric' }).format(today);
  const days = Array.from({ length: count }, (_, i) => new Date(year, month, i + 1));
  const practiced = days.filter((d) => minutes[isoDay(d)] > 0).length;
  return (
    <section className="card card-tight stack">
      <div className="cluster" style={{ justifyContent: 'space-between' }}>
        <h2 className="h2">{title[0].toUpperCase() + title.slice(1)}</h2>
        <span className="caption">{practiced} {practiced === 1 ? 'día' : 'días'} con práctica</span>
      </div>
      <div className="calendar">
        {WEEKDAYS.map((d) => <span key={d} className="calendar-head" aria-hidden="true">{d}</span>)}
        {Array.from({ length: blanks }, (_, i) => <span key={`b${i}`} />)}
        {days.map((d) => {
          const m = minutes[isoDay(d)] ?? 0;
          const isToday = d.getDate() === today.getDate();
          const label = `${d.getDate()}: ${m > 0 ? `${m.toLocaleString('es')} min` : 'sin práctica'}${isToday ? ', hoy' : ''}`;
          return <span key={d.getDate()} className={`calendar-day${m > 0 ? ' done' : ''}${isToday ? ' today' : ''}`} title={label} aria-label={label} role="img">{d.getDate()}</span>;
        })}
      </div>
      <div className="cluster caption" aria-hidden="true">
        <span className="calendar-key"><i className="calendar-day done" />Con práctica</span>
        <span className="calendar-key"><i className="calendar-day" />Sin práctica</span>
        <span className="calendar-key"><i className="calendar-day today" />Hoy</span>
      </div>
    </section>
  );
}

function ThisWeek({ minutes }) {
  const today = new Date();
  const monday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - ((today.getDay() + 6) % 7));
  const points = WEEKDAYS.map((label, i) => {
    const m = minutes[isoDay(new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i))] ?? 0;
    return { label, tip: WEEKDAY_NAMES[i], value: m };
  });
  const total = points.reduce((sum, p) => sum + p.value, 0);
  return <Chart title={`Esta semana · ${total.toLocaleString('es', { maximumFractionDigits: 1 })} min`} kind="bars" unit="min" points={points} />;
}

function Progress({ onReview, canReview }) {
  const [data, setData] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => { fetch('/api/progress').then((r) => r.json()).then(setData).catch(() => setFailed(true)); }, []);
  if (failed) return <div className="summary stack"><p role="alert">No pude cargar tu progreso. ¿Está arrancado el backend?</p></div>;
  if (!data) return <div className="start"><span className="muted" aria-busy="true">Cargando tu progreso…</span></div>;
  if (!data.totals.sessions) {
    return <div className="summary stack"><h1>Tu progreso</h1><p className="muted">Aún no hay sesiones. Tu historial aparecerá después de tu primera conversación.</p></div>;
  }
  const recent = data.sessions.slice(0, 20).reverse();
  const when = (s) => WHEN_LABEL.format(new Date(s.date));
  const short = (s) => DAY_LABEL.format(new Date(s.date));
  return (
    <div className="summary stack">
      <h1>Tu progreso</h1>
      <div className="tiles">
        <div className="metric-tile tint-info"><span className="overline">Minutos hablados</span><span className="metric">{data.totals.minutes.toLocaleString('es')}</span></div>
        <div className="metric-tile tint-error"><span className="overline">Sesiones</span><span className="metric">{data.totals.sessions}</span></div>
        <div className="metric-tile tint-warning"><span className="overline">Turnos</span><span className="metric">{data.totals.turns}</span></div>
        <div className="metric-tile tint-success"><span className="overline">Palabras</span><span className="metric">{data.totals.words.toLocaleString('es')}</span></div>
      </div>
      {data.review_due > 0 && (
        <section className="review-banner">
          <div><strong>Tienes {data.review_due} para repasar</strong>
            <p className="small muted">Palabras de tus misiones, las que te corrigió el tutor y frases que escribiste que querías decir.</p></div>
          {canReview ? <button className="btn btn-primary" onClick={onReview}>Repasar</button>
            : <span className="small muted">Para repasar hace falta el modelo de pronunciación.</span>}
        </section>
      )}
      <div className="charts">
        <MonthCalendar minutes={data.minutes_by_day} />
        <ThisWeek minutes={data.minutes_by_day} />
      </div>
      <div className="charts">
        <Chart title="Palabras por minuto, por sesión" kind="line" unit="pal/min" points={recent.map((s) => ({ label: short(s), tip: when(s), value: s.wpm }))} />
        <Chart title="Turnos sin errores, por sesión" kind="line" unit="%" max={100} points={recent.map((s) => ({ label: short(s), tip: when(s), value: s.clean_pct }))} />
      </div>
      <p className="small muted">Las palabras por minuto cuentan las pausas de tu turno. El porcentaje sin errores depende de lo que entienda el transcriptor: sirve para ver la tendencia, no como nota.</p>
      {data.sounds.length > 0 && (
        <section className="stack"><h2 className="h2">Sonidos que más se repiten</h2>
          <ul className="issues">{data.sounds.map((r) => (
            <li key={`${r.phone}${r.heard}`}><span className="tag tag-new">×{r.count}</span>
              <span><BadWords words={r.words} />: {r.tip}</span></li>))}</ul>
        </section>
      )}
      {data.recurring.length > 0 && (
        <section className="stack"><h2 className="h2">Errores que se repiten</h2>
          <ul className="issues">{data.recurring.map((r) => (
            <li key={`${r.type}${r.original}${r.fix}`}><span className="tag tag-new">×{r.count}</span>
              <span><FixPair original={r.original} fix={r.fix} />: {r.explanation}
                <span className="muted"> ({r.sessions === 1 ? 'en 1 sesión' : `en ${r.sessions} sesiones`})</span></span></li>))}</ul>
        </section>
      )}
      <section className="stack"><h2 className="h2">Tus sesiones</h2>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Tus sesiones">
          <table className="sessions">
            <thead><tr><th>Fecha</th><th>Sesión</th><th className="num">Min</th><th className="num">Turnos</th><th className="num">Pal/min</th><th className="num">Sin errores</th><th className="num">Objetivos</th></tr></thead>
            <tbody>{data.sessions.map((s) => (
              <tr key={s.id}><td>{when(s)}</td><td>{s.title}</td><td className="num">{s.minutes.toLocaleString('es')}</td><td className="num">{s.turns}</td>
                <td className="num">{s.wpm}</td><td className="num">{s.clean_pct} %</td><td className="num">{s.goals_total ? `${s.goals_met}/${s.goals_total}` : '—'}</td></tr>))}</tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

// Marca dentro de `text` los fragmentos dados (sin distinguir mayúsculas) con el elemento Tag
// Mismo subrayado que la práctica: verde (ok) lo que está bien, ondulado (bad) lo que hay que revisar.
// Solo palabras enteras: «on» no debe marcar el final de «done».
function marked(text, fragments, kind) {
  const parts = fragments.filter(Boolean).map((f) => f.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).filter(Boolean);
  if (!parts.length) return text;
  return text.split(new RegExp(`(?<!\\w)(${parts.join('|')})(?!\\w)`, 'gi')).map((p, i) =>
    (i % 2 ? <span key={i} className={`word-mark ${kind}`}>{p}</span> : p));
}

function FixPair({ original, fix }) {
  return <strong lang="en">{original && <><span className="word-mark bad">{original}</span> → </>}<span className="word-mark ok">{fix}</span></strong>;
}

function BadWords({ words }) {
  return <strong lang="en">{words.map((w, i) => <span key={w}><span className="word-mark bad">{w}</span>{i < words.length - 1 && ', '}</span>)}</strong>;
}

// Una frase ya calificada, con su puntuación original y el subrayado de cada palabra.
function SaidWords({ text, words }) {
  let next = 0;
  return text.split(/([A-Za-z0-9]+(?:['’][A-Za-z]+)?)/).map((part, i) => {
    const w = i % 2 && words[next]?.word.toLowerCase() === part.toLowerCase() ? words[next++] : null;
    return w ? <span key={i} className={`word-mark ${w.missing || w.issues.length ? 'bad' : w.unclear ? 'unclear' : 'ok'}`}>{part}</span> : part;
  });
}

const clock = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

// Columna de la sesión en curso: de qué va, cuánto llevas y cómo terminarla. En escenarios, objetivos y frases.
function SessionPanel({ c, silenceMs }) {
  const { session, messages, metrics, ending } = c;
  const { scenario } = session;
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const total = session.startedAt ? Math.max(0, (now - session.startedAt) / 1000) : 0;
  const speaking = messages.reduce((sum, m) => sum + (m.seconds ?? 0), 0);
  const done = session.met?.filter(Boolean).length ?? 0;
  return (
    <aside className="session-info" aria-label="Sesión">
      {session.game && <GameCard game={session.game} state={session.gameState} ui={c.ui} onSkip={c.skipGameWord} />}
      <div className="card card-tight stack">
        <h2 className="h2">Sesión</h2>
        <span className="tag tag-info" style={{ alignSelf: 'flex-start' }}>{session.game ? 'Buddy adivina' : scenario ? 'Escenario' : 'Conversación libre'}</span>
        {(scenario || session.topic) && (
          <LabeledText label={scenario ? 'Situación' : 'Tema'} note={scenario && <span className="muted">{scenario.description}</span>}><strong>{scenario?.title ?? session.topic}</strong></LabeledText>
        )}
        <div className="session-times">
          <div className="session-time"><span className="overline">Total</span><span className="metric">{clock(total)}</span></div>
          <div className="session-time"><span className="overline">Hablando</span><span className="metric">{clock(speaking)}</span></div>
        </div>
        <button className="btn btn-secondary session-end" onClick={c.end} disabled={ending}>
          {ending ? (scenario ? 'Evaluando…' : 'Terminando…') : 'Terminar sesión'}
        </button>
      </div>
      {scenario && (
        <>
          <div className="card card-tight stack">
            <div className="cluster" style={{ justifyContent: 'space-between' }}>
              <h2 className="h2">Tus objetivos</h2><span className="caption">{done}/{scenario.goals.length}</span>
            </div>
            <GoalList goals={scenario.goals.map((text, i) => ({ text, met: session.met?.[i] }))} />
          </div>
          {scenario.key_phrases.length > 0 && (
            <div className="card card-tight stack">
              <h2 className="h2">Frases útiles</h2>
              <PhraseList phrases={scenario.key_phrases} onListen={c.listen} />
            </div>
          )}
        </>
      )}
      {session.mission?.length > 0 && (
        <div className="card card-tight stack">
          <div className="cluster" style={{ justifyContent: 'space-between' }}>
            <h2 className="h2">Tu misión</h2><span className="caption">{session.used.length}/{session.mission.length}</span>
          </div>
          <p className="small muted">Intenta usarlas al hablar. Si no salen, vuelven otro día.</p>
          <MissionList words={session.mission} used={session.used} onListen={c.listen} />
        </div>
      )}
      <MetricsCard metrics={metrics} silenceMs={silenceMs} />
    </aside>
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

// Buddy adivina: tu palabra, que Buddy no conoce.
function GameCard({ game, state, ui, onSkip }) {
  const word = game[state.index];
  if (!word) {
    return (
      <div className="card card-tight stack" role="status">
        <h2 className="h2">¡Partida terminada!</h2>
        <p className="small">Buddy adivinó {state.solved.length} de {game.length}.</p>
      </div>
    );
  }
  return (
    <div className="card card-tight stack">
      <div className="cluster" style={{ justifyContent: 'space-between' }}>
        <h2 className="h2">Tu palabra</h2><span className="caption">{state.index + 1}/{game.length} · {state.solved.length} {state.solved.length === 1 ? 'adivinada' : 'adivinadas'}</span>
      </div>
      <LabeledText size="m" lang="en" note={word.meaning} aria-live="polite">{word.term}</LabeledText>
      {state.taboo
        ? <p className="small" role="alert"><strong>¡La dijiste!</strong> Eso no vale: descríbela sin nombrarla.</p>
        : <p className="small muted">Descríbela en inglés sin decirla. Si no dice nada parecido, da otra pista.</p>}
      <div className="cluster">
        <button className="btn btn-secondary btn-s" disabled={ui !== 'idle'} onClick={() => onSkip(false)}>Pasar palabra</button>
        <button className="btn btn-secondary btn-s" disabled={ui !== 'idle'} title="Buddy casi la dijo: cuéntala como adivinada" onClick={() => onSkip(true)}>Casi: ¡la adivinó!</button>
      </div>
    </div>
  );
}

function MissionList({ words, used, onListen }) {
  return (
    <ul className="goals" aria-live="polite">
      {words.map((w) => {
        const met = used.includes(w.key);
        return (
          <li key={w.key} className={met ? 'met' : undefined}>
            <span className="goal-check" aria-hidden="true">{met ? '✓' : ''}</span>
            <span className="mission-word">
              <span className="visually-hidden">{met ? 'Usada: ' : 'Pendiente: '}</span>
              <strong lang="en">{w.term}</strong> <span className="small">{w.meaning}</span>
              {w.example && <span className="small muted" lang="en">{w.example}</span>}
            </span>
            <ListenButton text={w.example ?? w.term} onListen={onListen} />
          </li>
        );
      })}
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

function TutorPanel({ mode, onMode, feedbacks, onListen, game }) {
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
            : game ? 'En el juego Buddy no te corrige: tus errores aparecen solo aquí.'
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
      <LabeledText label="Lo que dijiste" lang="en">{marked(f.text, f.issues.map((i) => i.original), 'bad')}</LabeledText>
      {f.intent && <LabeledText label="Lo que querías decir">{f.intent}</LabeledText>}
      <LabeledText label={f.intent ? 'Así se dice' : 'Mejor así'} lang="en" action={<ListenButton text={f.corrected} onListen={onListen} />}>{marked(f.corrected, f.issues.map((i) => i.fix), 'ok')}</LabeledText>
      <ul className="issues">
        {f.issues.map((i, n) => {
          const [cls, label] = ISSUE_TAG[i.type] ?? ['tag-info', i.type];
          return (
            <li key={n}><span className={`tag ${cls}`}>{label}</span>
              <span><FixPair original={i.original} fix={i.fix} />: {i.explanation_es}</span></li>
          );
        })}
      </ul>
      {f.better && f.better !== f.corrected && (
        <LabeledText label="Suena más natural" lang="en"><span className="better">“{f.better}”</span></LabeledText>
      )}
    </article>
  );
}

function Summary({ s, onListen, onRepeat, onHome, onPractice, busy }) {
  const sc = s.scenario;
  const turns = s.turns ?? 0;
  const done = sc?.goals.filter((g) => g.met).length ?? 0;
  const total = sc?.goals.length ?? 0;
  const types = Object.entries(s.by_type ?? {}).sort((a, b) => b[1] - a[1]);
  const most = types[0]?.[1] ?? 1;
  const perTurn = turns ? (s.words / turns).toLocaleString('es', { maximumFractionDigits: 1 }) : 0;
  return (
    <div className="page stack">
      <section className="card summary-hero">
        {turns > 0 && (
          <div className="confetti" aria-hidden="true">{['amarillo', 'coral', 'azul', 'rosa', 'lima', 'amarillo'].map((color, i) => <span key={i} style={{ background: `var(--${color})` }} />)}</div>
        )}
        <svg aria-hidden="true" width="96" height="96"><use href={`#onda-${turns ? 'celebrate' : 'idle'}`} /></svg>
        <div className="stack summary-title">
          <span className="overline">{sc?.title ?? s.topic ?? 'Conversación libre'} · {clock(s.speaking_s ?? 0)} hablando de {clock(s.duration_s ?? 0)}</span>
          <h1>{turns ? '¡Sesión completada!' : 'Sesión terminada'}</h1>
          {!turns && <p className="muted">No llegaste a hablar en esta sesión.</p>}
          {sc && turns > 0 && (
            <div className="cluster">
              <Stars n={sc.stars} />
              <span className="muted">{done} de {total} objetivos{done < total && ` · ${total - done === 1 ? 'te falta 1' : `te faltan ${total - done}`} para las 3 estrellas`}</span>
            </div>
          )}
        </div>
      </section>

      {turns > 0 && (
        <div className="tiles">
          <div className="metric-tile tint-info"><span className="overline">Palabras por minuto</span><span className="metric">{s.wpm ?? 0}</span></div>
          <div className="metric-tile tint-warning"><span className="overline">Palabras por turno</span><span className="metric">{perTurn}</span></div>
          <div className="metric-tile tint-success"><span className="overline">Turnos sin errores</span><span className="metric">{s.clean_turns ?? 0}/{turns}</span></div>
          <div className="metric-tile tint-error"><span className="overline">Tiempo hablando</span><span className="metric">{clock(s.speaking_s ?? 0)}</span></div>
        </div>
      )}

      {turns > 0 && (
        <div className="summary-grid">
          {sc && (
            <section className="card stack">
              <h2 className="h2">Objetivos · {done} de {total}</h2>
              <GoalList goals={sc.goals} />
              {sc.comment && <p>{sc.comment}</p>}
            </section>
          )}
          {sc?.unused_phrases.length > 0 && (
            <section className="card stack"><h2 className="h2">Frases útiles que no usaste</h2>
              <PhraseList phrases={sc.unused_phrases} onListen={onListen} /></section>
          )}
          {s.game && (
            <section className="card stack">
              <h2 className="h2">Buddy adivinó {s.game.solved.length} de {s.game.solved.length + s.game.skipped.length}</h2>
              {s.game.solved.length > 0 && <><span className="overline">Las adivinó</span>
                <MissionList words={s.game.solved} used={s.game.solved.map((w) => w.key)} onListen={onListen} /></>}
              {s.game.skipped.length > 0 && <><span className="overline">No llegó a adivinarlas</span>
                <MissionList words={s.game.skipped} used={[]} onListen={onListen} /></>}
            </section>
          )}
          {s.mission && (
            <section className="card stack">
              <h2 className="h2">Tu misión · {s.mission.used.length} de {s.mission.used.length + s.mission.unused.length}</h2>
              {s.mission.used.length > 0 && <><span className="overline">Usaste</span>
                <MissionList words={s.mission.used} used={s.mission.used.map((w) => w.key)} onListen={onListen} /></>}
              {s.mission.unused.length > 0 && <><span className="overline">Para la próxima</span>
                <MissionList words={s.mission.unused} used={[]} onListen={onListen} /></>}
            </section>
          )}
          {types.length > 0 && (
            <section className="card stack">
              <h2 className="h2">Tus errores</h2>
              {types.map(([type, n]) => (
                <div className="meter-row" key={type}>
                  <div className="cluster" style={{ justifyContent: 'space-between' }}><strong>{ISSUE_TAG[type]?.[1] ?? type}</strong><span>×{n}</span></div>
                  <div className="meter" aria-hidden="true"><span style={{ width: `${(100 * n) / most}%` }} /></div>
                </div>
              ))}
              {s.recurring?.length > 0 && (
                <>
                  <span className="overline">Se repiten</span>
                  <ul className="issues">{s.recurring.map((r, i) => (
                    <li key={i}><span className="tag tag-new">×{r.count}</span>
                      <span><FixPair original={r.original} fix={r.fix} />: {r.explanation}</span></li>))}</ul>
                </>
              )}
            </section>
          )}
          {s.sounds?.length > 0 && (
            <section className="card stack">
              <h2 className="h2">Pronunciación</h2>
              <ul className="issues">{s.sounds.map((r, i) => (
                <li key={i}><span className="tag tag-new">×{r.count}</span>
                  <span><BadWords words={r.words} /> <span className="ipa-inline">/{r.phone}/ → /{r.heard}/</span>: {r.tip}</span></li>))}</ul>
              {onPractice && <button className="btn btn-secondary btn-s" style={{ alignSelf: 'flex-start' }} onClick={onPractice}>Practicar sonidos</button>}
            </section>
          )}
          {s.phrases?.length > 0 && (
            <section className="card stack"><h2 className="h2">Frases que querías decir</h2>
              <ul className="review-list">{s.phrases.map((p, i) => (
                <li key={i} className="phrase">
                  <span className="small muted">{p.intent}</span>
                  <span className="cluster" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
                    <strong lang="en">{p.english}</strong><ListenButton text={p.english} onListen={onListen} /></span>
                </li>))}</ul>
            </section>
          )}
          {s.review?.length > 0 && (
            <section className="card stack"><h2 className="h2">Frases para repasar</h2>
              <ul className="review-list">{s.review.map((r, i) => (
                <li key={i} lang="en"><span>{marked(r.text, r.wrong, 'bad')}</span><span>{marked(r.corrected, r.fixes, 'ok')}</span></li>))}</ul>
            </section>
          )}
        </div>
      )}

      <div className="cluster">
        <button className="btn btn-primary btn-l" disabled={busy} onClick={onRepeat}>
          {!sc ? 'Hablar otra vez' : sc.stars === 3 ? 'Repetir el escenario' : 'Repetir por las 3 estrellas'}
        </button>
        <button className="btn btn-secondary btn-l" onClick={onHome}>Volver a Hoy</button>
      </div>
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
