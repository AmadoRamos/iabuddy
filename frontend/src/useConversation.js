import { useCallback, useEffect, useRef, useState } from 'react';
import { startMic } from './audio/mic.js';
import { Player } from './audio/player.js';

// Estado de la conversación: WebSocket con el backend, micrófono, reproductor y mensajes.
// El micrófono envía siempre; el backend decide qué audio pertenece a tu turno.
//
// ui: 'off' (sin empezar) · 'connecting' · 'idle' · 'listening' · 'thinking' · 'speaking'
export function useConversation() {
  const [ui, setUi] = useState('off');
  const [messages, setMessages] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [error, setError] = useState(null);
  const [health, setHealth] = useState(null);

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
  useEffect(() => { checkHealth(); }, [checkHealth]);

  const send = (msg) => ws.current?.readyState === WebSocket.OPEN && ws.current.send(JSON.stringify(msg));

  const onEvent = useCallback((m) => {
    switch (m.type) {
      case 'state':
        server.current = m.state;
        if (m.state === 'thinking') turn.current.closedAt ??= performance.now();
        refreshUi();
        break;
      case 'user_text':
        setMessages((ms) => [...ms.filter((x) => !x.live), { who: 'you', text: m.text }]);
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
        setMessages((ms) => [...ms.filter((x) => x.who !== 'you' || x !== ms.at(-1)), { who: 'you', live: true, text: '' }]);
        turn.current = {};
        break;
      case 'turn_discarded':
        setMessages((ms) => ms.filter((x) => !x.live));
        turn.current = {};
        break;
      case 'metrics': {
        const t = turn.current;
        setMetrics({ ...m, client: t.closedAt && t.playAt ? Math.round(t.playAt - t.closedAt) : null });
        turn.current = {};
        break;
      }
      case 'error':
        setError(m.message);
        break;
      default:
    }
  }, [refreshUi]);

  const start = useCallback(async () => {
    setError(null);
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
    sock.onclose = () => { setUi('off'); mic.current?.stop(); checkHealth(); };
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
    send({ type: 'hello' });
  }, [onEvent, refreshUi, checkHealth]);

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

  useEffect(() => () => { ws.current?.close(); mic.current?.stop(); }, []);

  return { ui, messages, metrics, error, health, start, toggle };
}
