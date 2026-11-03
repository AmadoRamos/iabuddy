import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// En desarrollo (npm run dev) Vite reenvía /ws y /api al backend de FastAPI.
// En producción FastAPI sirve frontend/dist directamente.
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
      '/api': 'http://127.0.0.1:8000',
    },
  },
});
