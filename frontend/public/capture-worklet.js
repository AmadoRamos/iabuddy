// Corre en el hilo de audio. El AudioContext ya va a 16 kHz (el navegador remuestrea el
// micrófono), así que aquí solo se pasa a int16 y se envían ventanas de 512 muestras (32 ms),
// el tamaño que usa Silero VAD en el backend.
const FRAME = 512;

class Capture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Int16Array(FRAME);
    this.n = 0;
  }

  process(inputs) {
    const ch = inputs[0][0];
    if (ch) {
      for (let i = 0; i < ch.length; i++) {
        const s = Math.max(-1, Math.min(1, ch[i]));
        this.buf[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
        if (this.n === FRAME) {
          this.port.postMessage(this.buf.buffer, [this.buf.buffer]);
          this.buf = new Int16Array(FRAME);
          this.n = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor('capture', Capture);
