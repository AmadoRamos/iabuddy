// El worklet vive en public/: se sirve tal cual (Vite incrustaría uno tan pequeño como data:).
const WORKLET_URL = '/capture-worklet.js';

// Micrófono → PCM int16 a 16 kHz en ventanas de 32 ms → onFrame(ArrayBuffer).
// Pedir 16 kHz al AudioContext funciona en Chrome y Edge (los navegadores objetivo).
export async function startMic(onFrame) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const ctx = new AudioContext({ sampleRate: 16000 });
  await ctx.audioWorklet.addModule(WORKLET_URL);
  const node = new AudioWorkletNode(ctx, 'capture');
  node.port.onmessage = (e) => onFrame(e.data);
  const mute = ctx.createGain();
  mute.gain.value = 0; // conectado a la salida para que el grafo procese, pero sin sonar
  ctx.createMediaStreamSource(stream).connect(node).connect(mute).connect(ctx.destination);
  return {
    stop() {
      stream.getTracks().forEach((t) => t.stop());
      ctx.close();
    },
  };
}
