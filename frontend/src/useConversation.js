import { useCallback, useEffect, useRef, useState } from 'react';
import { startMic } from './audio/mic.js';
import { Player } from './audio/player.js';

// Estado de la conversación: WebSocket con el backend, micrófono, reproductor y mensajes.
// El micrófono envía siempre; el backend decide qué audio pertenece a tu turno.
//
// ui: 'off' (sin empezar) · 'connecting' · 'idle' · 'listening' · 'thinking' · 'speaking'
// session: null (eligiendo) · { topic } o { scenario, met } en curso · { drill: true } practicando
// pronunciación · summary: resumen al terminar
export function useConversation() {
  const [ui, setUi] = useState('off');
  const [messages, setMessages] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState(null);
  const [health, setHealth] = useState(null);
  const [topics, setTopics] = useState([]);
  const [scenarios, setScenarios] = useState([]);
  const [ending, setEnding] = useState(false); // esperando el resumen (y la evaluación del escenario)
  const [session, setSession] = useState(null);
  const [summary, setSummary] = useState(null);
  const [feedbacks, setFeedbacks] = useState([]); // análisis del tutor, uno por turno tuyo
  const [settings, setSettings] = useState(null); // { silence_ms, speed, feedback }
  const [mode, setMode] = useState('voz'); // corrección: 'silencioso' | 'panel' | 'voz' (TODO §1.3)
  const [sounds, setSounds] = useState({}); // turno → sonidos con error claro
  const [drills, setDrills] = useState(null); // frases de práctica: { sounds, failed }
  const [drillResult, setDrillResult] = useState(null);
  const [recallResult, setRecallResult] = useState(null); // «Dilo en inglés»: lo que se oyó y si estaba la palabra
  const [usageResult, setUsageResult] = useState(null); // «Tu propia frase»: lo que dice el tutor de cómo la usaste
  const [intents, setIntents] = useState({}); // turno → 'pending' | 'failed' mientras el tutor analiza lo que escribiste

  const ws = useRef(null);
  const mic = useRef(null);
  const player = useRef(null);
  const server = useRef('idle'); // último estado que dijo el backend
  const playing = useRef(false);
  const turn = useRef({}); // tiempos del turno en curso, medidos en el navegador

  const refreshUi = useCallback(() => {
    setUi(playing.current && server.current !== 'listening' ? 'speaking'
      : server.current === 'speaking' ? 'thinking' : server.current);
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      setHealth(await (await fetch('/api/health')).json());
    } catch {
      setHealth({ backend: false });
    }
  }, []);
  useEffect(() => {
    checkHealth();
    fetch('/api/topics').then((r) => r.json()).then(setTopics).catch(() => {});
    fetch('/api/settings').then((r) => r.json()).then((v) => { setSettings(v); setMode(v.feedback); }).catch(() => {});
    fetch('/api/scenarios').then((r) => r.json()).then(setScenarios).catch(() => {});
  }, [checkHealth]);

  const send = (msg) => ws.current?.readyState === WebSocket.OPEN && ws.current.send(JSON.stringify(msg));

  const onEvent = useCallback((m) => {
    switch (m.type) {
      case 'state':
        server.current = m.state;
        if (m.state === 'thinking') turn.current.closedAt ??= performance.now();
        refreshUi();
        break;
      case 'session':
        setSession({ topic: m.topic, scenario: m.scenario, met: m.scenario?.goals.map(() => false), mission: m.mission ?? [], used: [], game: m.game, gameState: { index: 0, solved: [], skipped: [] }, startedAt: Date.now() });
        break;
      case 'goals': // objetivos del escenario cumplidos hasta ahora
        setSession((s) => s && { ...s, met: m.met });
        break;
      case 'game': // «Buddy adivina»: por qué palabra vas
        setSession((s) => s && { ...s, gameState: m });
        break;
      case 'mission': // palabras de la misión que ya usaste
        setSession((s) => s && { ...s, used: m.used });
        break;
      case 'user_text':
        setMessages((ms) => [...ms.filter((x) => !x.live), { who: 'you', text: m.text, turn: m.turn, seconds: m.seconds }]);
        break;
      case 'feedback':
        setFeedbacks((fs) => [m, ...fs.filter((f) => f.turn !== m.turn)]);
        if (m.intent) setIntents(({ [m.turn]: _, ...rest }) => rest);
        break;
      case 'pronunciation':
        setSounds((s) => ({ ...s, [m.turn]: m.issues }));
        break;
      case 'drill_result':
        setDrillResult(m);
        break;
      case 'recall_result':
        setRecallResult(m);
        break;
      case 'usage_result':
        setUsageResult(m);
        break;
      case 'intent_failed':
        setIntents((it) => ({ ...it, [m.turn]: 'failed' }));
        break;
      case 'summary':
        setSummary(m);
        setSession(null);
        setEnding(false);
        break;
      case 'partner_text':
        setMessages((ms) => {
          const last = ms.at(-1);
          if (last?.who === 'buddy' && last.open) return [...ms.slice(0, -1), { ...last, text: `${last.text} ${m.text}` }];
          return [...ms.filter((x) => !x.live), { who: 'buddy', text: m.text, open: true }];
        });
        break;
      case 'partner_done':
        player.current.markDone();
        setMessages((ms) => ms.map((x) => (x.open ? { ...x, open: false } : x)));
        break;
      case 'barge_in':
        setMessages((ms) => ms.map((x) => (x.open ? { ...x, open: false, cut: true } : x)));
        break;
      case 'turn_resumed': // sigues hablando: tu frase anterior vuelve a ser parte del turno
        setRecallResult(null);
        setUsageResult(null);
        // Por su n.º de turno, no por ser la última: con la tecla, la burbuja en vivo ya está detrás
        setMessages((ms) => [...ms.filter((x) => !x.live && x.turn !== m.turn), { who: 'you', live: true, text: '' }]);
        setFeedbacks((fs) => fs.filter((f) => f.turn !== m.turn));
        turn.current = {};
        break;
      case 'turn_discarded':
        setMessages((ms) => ms.filter((x) => !x.live));
        turn.current = {};
        break;
      case 'metrics': {
        const t = turn.current;
        const client = t.closedAt && t.playAt ? Math.round(t.playAt - t.closedAt) : null;
        setMetrics({ ...m, client });
        send({ type: 'client_metrics', heard_ms: client }); // solo para los registros
        turn.current = {};
        break;
      }
      case 'error':
        setError(m.message);
        break;
      default:
    }
  }, [refreshUi]);

  // Empieza una sesión: choice = { topic_id } (null = libre), { scenario } o { drill: true }. La primera vez abre WebSocket y micrófono.
  const start = useCallback(async (choice = {}) => {
    setError(null);
    setMessages([]);
    setFeedbacks([]);
    setIntents({});
    setSummary(null);
    setMetrics(null);
    setSounds({});
    setDrillResult(null);
    setRecallResult(null);
    setUsageResult(null);
    if (choice.drill) setDrills(null);
    if (choice.drill) fetch('/api/drills').then((r) => r.json()).then(setDrills).catch(() => setDrills({ sounds: [], failed: [], review: [], own: [] }));
    const begin = () => {
      if (choice.drill) {
        // Sin sesión en el backend: cada frase se analiza por separado
        setSession({ drill: choice.drill, guided: choice.guided, startedAt: Date.now() });
        return;
      }
      setSession({ topic: null });
      send({ type: 'hello', ...choice, feedback: mode });
    };
    if (ws.current?.readyState === WebSocket.OPEN) {
      begin();
      return;
    }
    setUi('connecting');
    player.current = new Player({
      onPlaying: (at) => { playing.current = true; turn.current.playAt ??= at; refreshUi(); },
      onIdle: () => { playing.current = false; refreshUi(); },
    });
    await player.current.unlock(); // aún dentro del gesto del usuario
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const sock = new WebSocket(`${proto}://${location.host}/ws`);
    sock.binaryType = 'arraybuffer';
    sock.onmessage = (e) => (typeof e.data === 'string' ? onEvent(JSON.parse(e.data)) : player.current.enqueue(e.data));
    sock.onclose = () => { setUi('off'); setSession(null); setEnding(false); mic.current?.stop(); checkHealth(); };
    ws.current = sock;
    try {
      await new Promise((ok, fail) => { sock.onopen = ok; sock.onerror = () => fail(new Error('No se pudo conectar con el backend.')); });
      mic.current = await startMic((frame) => sock.readyState === WebSocket.OPEN && sock.send(frame));
    } catch (e) {
      sock.close();
      setUi('off');
      setError(e.name === 'NotAllowedError' ? 'El navegador no tiene permiso para usar el micrófono.' : e.message);
      return;
    }
    server.current = 'idle';
    refreshUi();
    begin();
  }, [onEvent, refreshUi, checkHealth, mode]);

  const end = useCallback(() => {
    if (playing.current) player.current.stop();
    setEnding(true);
    send({ type: 'end' });
  }, []);

  // Escribiste lo que querías decir en el turno `turn`
  const sendIntent = useCallback((turn, text) => {
    setIntents((it) => ({ ...it, [turn]: 'pending' }));
    send({ type: 'intent', turn, text });
  }, []);

  // 🔊 Buddy lee una frase (solo si no está hablando)
  const listen = useCallback((text) => {
    if (!playing.current) send({ type: 'say', text });
  }, []);

  // Ajustes: se aplican a la sesión abierta, si la hay, y quedan guardados
  const saveSettings = useCallback((patch) => {
    setSettings((v) => ({ ...v, ...patch }));
    send({ type: 'settings', ...patch });
    fetch('/api/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) })
      .then((r) => { if (!r.ok) throw new Error(); })
      .catch(() => setError('No se pudo guardar el ajuste.'));
  }, []);

  const changeMode = useCallback((m) => {
    setMode(m);
    saveSettings({ feedback: m });
  }, [saveSettings]);

  // Práctica: abre o cierra tu lectura de `text` (grade: se califica). Lo demás funciona como en un turno normal
  const drillToggle = useCallback((text, grade = false) => {
    if (server.current === 'listening') send({ type: 'stop' });
    else if (server.current === 'thinking') send({ type: 'start' });
    else {
      if (playing.current) player.current.stop();
      setDrillResult(null);
      send({ type: 'drill', text, grade });
    }
  }, []);

  // «Dilo en inglés» y «Tu propia frase» (check: el tutor la revisa): abre o cierra tu frase con la palabra `key`
  const recallToggle = useCallback((key, check = false) => {
    if (server.current === 'listening') send({ type: 'stop' });
    else if (server.current === 'thinking') send({ type: 'start' });
    else {
      if (playing.current) player.current.stop();
      setRecallResult(null);
      setUsageResult(null);
      send({ type: 'recall', key, check });
    }
  }, []);

  // Repaso: guarda tu respuesta y devuelve cuántas quedan y cuándo vuelve la siguiente
  const answerReview = useCallback((key, known) => {
    setDrillResult(null); // si la frase vuelve en esta tanda, no debe aparecer ya resuelta
    setRecallResult(null);
    return fetch('/api/review', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key, known }) })
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .catch(() => setError('No se pudo guardar el repaso.'));
  }, []);

  // «Esto no lo dije» o quitarla del banco
  const discardWord = useCallback((key) => {
    setDrillResult(null);
    setRecallResult(null);
    return fetch('/api/review/discard', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key }) })
      .then((r) => { if (!r.ok) throw new Error(); return r.json(); })
      .catch(() => { setError('No se pudo quitar.'); return null; });
  }, []);

  // Guarda una palabra del chat. El tutor busca su significado: devuelve si se pudo
  const saveWord = useCallback((term, context) => (
    fetch('/api/words', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ term, context }) })
      .then((r) => r.ok).catch(() => false)
  ), []);

  // Conversación guiada: guarda la nota; el escenario enseña tu mejor resultado
  const saveGuided = useCallback((scenario, grade) => {
    fetch('/api/guided', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ scenario, grade }) })
      .then((r) => { if (!r.ok) throw new Error(); return fetch('/api/scenarios'); })
      .then((r) => r.json()).then(setScenarios)
      .catch(() => setError('No se pudo guardar la nota.'));
  }, []);

  const skipGameWord = useCallback((solved = false) => send({ type: 'game_skip', solved }), []);

  const leaveDrill = useCallback(() => {
    if (server.current === 'listening') send({ type: 'stop' });
    setSession(null);
  }, []);

  // Espacio / botón Onda: abre o cierra tu turno; si Buddy habla, lo interrumpe.
  const toggle = useCallback(() => {
    if (server.current === 'listening') {
      turn.current = { closedAt: performance.now() };
      send({ type: 'stop' });
      return;
    }
    if (playing.current) player.current.stop();
    turn.current = {};
    setMessages((ms) => [...ms.filter((x) => !x.live), { who: 'you', live: true, text: '' }]);
    send({ type: 'start' });
  }, []);

  // Los errores de la pantalla también van a los registros del backend
  useEffect(() => {
    const report = (e) => send({ type: 'client_error', message: String(e.reason ?? e.message).slice(0, 500), where: e.filename });
    window.addEventListener('error', report);
    window.addEventListener('unhandledrejection', report);
    return () => { window.removeEventListener('error', report); window.removeEventListener('unhandledrejection', report); };
  }, []);

  // Las estrellas de los escenarios cambian al terminar uno
  useEffect(() => {
    if (summary?.scenario) fetch('/api/scenarios').then((r) => r.json()).then(setScenarios).catch(() => {});
  }, [summary]);

  useEffect(() => () => { ws.current?.close(); mic.current?.stop(); }, []);

  return { ui, messages, metrics, error, health, topics, scenarios, session, summary, feedbacks, mode, intents, ending, sounds, drills, drillResult, drillToggle, recallResult, usageResult, recallToggle, leaveDrill, answerReview, discardWord, saveWord, skipGameWord, saveGuided,
    settings, saveSettings, checkHealth, start, toggle, end, changeMode, sendIntent, listen, closeSummary: () => setSummary(null) };
}
