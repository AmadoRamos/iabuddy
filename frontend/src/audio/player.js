// Reproduce en cola los trozos de voz del compañero (PCM int16 mono a 24 kHz, Kokoro).
// stop() corta al instante (barge-in). onIdle salta cuando ya no queda audio y el servidor
// avisó de que la respuesta terminó: así no parpadea entre dos trozos.
const RATE = 24000;

export class Player {
  constructor({ onPlaying, onIdle }) {
    this.onPlaying = onPlaying;
    this.onIdle = onIdle;
    this.ctx = null;
    this.sources = new Set();
    this.nextTime = 0;
    this.active = false;
    this.done = true;
  }

  unlock() {
    // Llamar desde un gesto del usuario: Chrome no deja sonar audio sin uno.
    this.ctx ??= new AudioContext();
    return this.ctx.resume();
  }

  enqueue(arrayBuffer) {
    const ctx = this.ctx;
    const pcm = new Int16Array(arrayBuffer);
    const buf = ctx.createBuffer(1, pcm.length, RATE);
    const ch = buf.getChannelData(0);
    for (let i = 0; i < pcm.length; i++) ch[i] = pcm[i] / 32768;

    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    const start = Math.max(ctx.currentTime + 0.02, this.nextTime);
    src.start(start);
    this.nextTime = start + buf.duration;
    this.sources.add(src);
    this.done = false;
    if (!this.active) {
      this.active = true;
      this.onPlaying?.(performance.now() + (start - ctx.currentTime) * 1000);
    }
    src.onended = () => {
      this.sources.delete(src);
      this.#maybeIdle();
    };
  }

  markDone() {
    this.done = true;
    this.#maybeIdle();
  }

  stop() {
    for (const s of this.sources) {
      s.onended = null;
      s.stop();
    }
    this.sources.clear();
    this.nextTime = 0;
    this.done = true;
    this.#maybeIdle();
  }

  #maybeIdle() {
    if (this.active && this.done && this.sources.size === 0) {
      this.active = false;
      this.onIdle?.();
    }
  }
}
