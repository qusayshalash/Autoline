import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // The app calls /api on its own origin. In development that is this server, which hands
  // the call to the backend - the same arrangement the reverse proxy makes in production,
  // so the session cookie behaves the same way in both.
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
  build: {
    // The one chunk that lands anywhere near this limit is echarts, pulled in only by
    // the lazy-loaded chart component on the statistics page - it's already tree-shaken
    // to just the renderer and chart types actually used, and it downloads in parallel
    // with that page's data request rather than blocking any route's initial load.
    chunkSizeWarningLimit: 600,
  },
})
