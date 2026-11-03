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
  const [topicId, setTopicId] = useState(null);

  // Espacio: empezar la sesión o alternar el turno. No en campos de texto ni en el resumen.
  useEffect(() => {
    const onKey = (e) => {
      if (e.code !== 'Space' || e.repeat || e.target.closest?.('input, textarea, select')) return;
      e.preventDefault();
      if (session) { if (ui !== 'connecting') c.toggle(); } else if (!summary && ui !== 'connecting') c.start(topicId);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [ui, session, summary, topicId, c]);

  const h = c.health;
  const down = h && (h.backend === false || !h.whisper || !h.ollama);

  return (
    <div className="container">
      <header className="topbar">
        <span className="brand"><svg aria-hidden="true" width="44" height="44"><use href="#onda-logo" /></svg>
          <span className="brand-name">iabuddy</span></span>
        <div className="cluster">
          <span className="tag tag-info">Conversación libre{session?.topic && ` · ${session.topic}`}</span>
          {session && <button className="btn btn-secondary btn-s" onClick={c.end}>Terminar sesión</button>}
        </div>
      </header>

      <main className="session">
        {down && <HealthAlert health={h} />}
        {c.error && <div className="alert alert-error" role="alert"><span>{c.error}</span></div>}

        <div className="session-grid">
          <section className="card conversation" aria-label="Conversación">
            {summary ? <Summary s={summary} onClose={c.closeSummary} />
              : session ? <><ChatLog messages={c.messages} /><Dock ui={ui} onToggle={c.toggle} /></>
                : <StartCard topics={c.topics} topicId={topicId} setTopicId={setTopicId}
                    onStart={() => c.start(topicId)} disabled={down || ui === 'connecting'} />}
          </section>
          <aside className="session-side">
            <TutorPanel mode={c.mode} onMode={c.changeMode} feedbacks={c.feedbacks} />
            <MetricsCard metrics={c.metrics} silenceMs={h?.silence_ms} />
          </aside>
        </div>
      </main>
    </div>
  );
}

function ChatLog({ messages }) {
  const end = useRef(null);
  // Con llaves: scrollIntoView devuelve una promesa en Chrome reciente y React la tomaría por la limpieza
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }); }, [messages]);
  return (
    <div className="chat" aria-live="polite">
      {messages.map((m, i) => (m.who === 'buddy' ? (
        <div className="buddy-row" key={i}>
          <svg aria-hidden="true" width="40" height="40" style={{ flex: 'none', visibility: m.tip ? 'hidden' : undefined }}><use href="#onda-logo" /></svg>
          <span className={`bubble bubble-buddy${m.tip ? ' bubble-tip' : ''}`} lang="en">
            {m.tip && <span className="tag tag-xp">Así se dice</span>}{m.text}{m.cut && ' …'}
          </span>
        </div>
      ) : (
        <span key={i} className={`bubble ${m.live ? 'bubble-live' : 'bubble-you'}`} lang="en">{m.text || (m.live && '…')}</span>
      )))}
      <div ref={end} />
    </div>
  );
}

function Dock({ ui, onToggle }) {
  const [title, text, keyHint, label] = STATUS[ui] ?? STATUS.idle;
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

function StartCard({ topics, topicId, setTopicId, onStart, disabled }) {
  return (
    <div className="start">
      <svg aria-hidden="true" width="120" height="120"><use href="#onda-idle" /></svg>
      <h1>¿Charlamos?</h1>
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

// Marca dentro de `text` los fragmentos dados (sin distinguir mayúsculas) con el elemento Tag
function highlight(text, fragments, Tag, className) {
  const parts = fragments.filter(Boolean).map((f) => f.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (!parts.length) return text;
  return text.split(new RegExp(`(${parts.join('|')})`, 'gi')).map((p, i) =>
    (i % 2 ? <Tag key={i} className={className}>{p}</Tag> : p));
}

function TutorPanel({ mode, onMode, feedbacks }) {
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
            : mode === 'voz' ? 'Buddy termina su respuesta con un tip sobre tu error principal. Aquí tienes todos.'
              : 'Tus correcciones aparecen aquí, sin interrumpir la conversación.'}
        </p>
      </div>
      {mode !== 'silencioso' && (feedbacks.length
        ? feedbacks.map((f) => <FeedbackCard key={f.turn} f={f} />)
        : <div className="empty"><span className="small muted">Aquí aparecerán las correcciones de cada turno tuyo.</span></div>)}
    </>
  );
}

function FeedbackCard({ f }) {
  if (!f.issues.length) {
    return (
      <article className="card card-tight feedback-ok">
        <strong>Tu turno {f.turn} · ¡sin errores!</strong>
        <span className="small">{f.text.split(/\s+/).length} palabras, natural y correcto.</span>
      </article>
    );
  }
  const level = Math.max(...f.issues.map((i) => i.severity));
  return (
    <article className="card card-tight stack feedback">
      <div className="cluster" style={{ justifyContent: 'space-between' }}>
        <strong>Tu turno {f.turn}</strong>
        <span className="tag severity" data-level={level}><span className="severity-bars"><i /><i /><i /></span>{SEVERITY[level]}</span>
      </div>
      <div><span className="overline">Lo que dijiste</span>
        <p lang="en">{highlight(f.text, f.issues.map((i) => i.original), 's', 'wrong')}</p></div>
      <div><span className="overline">Mejor así</span>
        <p lang="en">{highlight(f.corrected, f.issues.map((i) => i.fix), 'mark', 'recast')}</p></div>
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

function Summary({ s, onClose }) {
  const min = (sec) => `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`;
  const errors = Object.values(s.by_type ?? {}).reduce((a, b) => a + b, 0);
  return (
    <div className="summary stack">
      <div className="cluster" style={{ gap: 16 }}>
        <svg aria-hidden="true" width="72" height="72"><use href="#onda-celebrate" /></svg>
        <div><h1>¡Buena sesión!</h1><p className="muted">{s.turns ? 'Esto es lo que hablaste hoy.' : 'No llegaste a hablar en esta sesión.'}</p></div>
      </div>
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
