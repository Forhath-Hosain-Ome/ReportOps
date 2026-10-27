import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const apiUrl = process.env.VITE_API_URL || 'http://127.0.0.1:8000/api'
const wsUrl = process.env.VITE_WS_URL || 'ws://127.0.0.1:8000/ws'
const apiTarget = apiUrl.startsWith('/') ? 'http://backend:8000' : new URL(apiUrl).origin
const wsTarget = wsUrl.startsWith('/') ? 'ws://backend:8000' : new URL(wsUrl).origin

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/auth": { target: apiTarget, changeOrigin: true },
      "/puma": { target: apiTarget, changeOrigin: true },
      "/image/": { target: apiTarget, changeOrigin: true },
      "/final-summary": { target: apiTarget, changeOrigin: true },
      "/ws": { target: wsTarget, ws: true, changeOrigin: true },
    },
  },
})
