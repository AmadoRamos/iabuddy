import { useEffect, useRef } from 'react';
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

export default function App() {
  const { ui, messages, metrics, error, health, start, toggle } = useConversation();
  const started = ui !== 'off';

  // Espacio: empezar la sesión o alternar el turno. No en campos de texto.
  useEffect(() => {
    const onKey = (e) => {
      if (e.code !== 'Space' || e.repeat || e.target.closest?.('input, textarea, select')) return;
      e.preventDefault();
      if (ui === 'off') start();
      else if (ui !== 'connecting') toggle();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [ui, start, toggle]);

  const down = health && (health.backend === false || !health.whisper || !health.ollama);

  return (
    <div className="container">
      <header className="topbar">
        <span className="brand"><svg aria-hidden="true" width="44" height="44"><use href="#onda-logo" /></svg>
          <span className="brand-name">iabuddy</span></span>
        <span className="tag tag-info">Conversación libre</span>
      </header>

      <main className="session">
        {down && <HealthAlert health={health} />}
        {error && <div className="alert alert-error" role="alert"><span>{error}</span></div>}

        <div className="session-grid">
          <section className="card conversation" aria-label="Conversación">
            {started ? <ChatLog messages={messages} /> : <StartCard onStart={start} disabled={down} />}
            {started && <Dock ui={ui} onToggle={toggle} />}
          </section>
          <aside className="session-side">
            <MetricsCard metrics={metrics} silenceMs={health?.silence_ms} />
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
          <svg aria-hidden="true" width="40" height="40" style={{ flex: 'none' }}><use href="#onda-logo" /></svg>
          <span className="bubble bubble-buddy" lang="en">{m.text}{m.cut && ' …'}</span>
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

function StartCard({ onStart, disabled }) {
  return (
    <div className="start">
      <svg aria-hidden="true" width="120" height="120"><use href="#onda-idle" /></svg>
      <h1>¿Charlamos?</h1>
      <p className="body-l muted">Habla en inglés con Buddy. Pulsa Espacio para abrir tu turno y otra vez para cerrarlo.
        Usa audífonos.</p>
      <button className="btn btn-primary btn-l" onClick={onStart} disabled={disabled}>
        Empezar <span className="kbd-inline">Espacio</span>
      </button>
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
    <div className="card card-tight stack">
      <div className="cluster" style={{ justifyContent: 'space-between' }}>
        <h3>Tiempos</h3><span className="caption">último turno · local</span>
      </div>
      {rows ? (
        <dl className="metrics">
          {rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}
        </dl>
      ) : <p className="muted small">Aparecen al terminar tu primer turno.</p>}
    </div>
  );
}
