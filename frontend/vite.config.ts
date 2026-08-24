import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    // The one chunk that lands anywhere near this limit is echarts, pulled in only by
    // the lazy-loaded chart component on the statistics page - it's already tree-shaken
    // to just the renderer and chart types actually used, and it downloads in parallel
    // with that page's data request rather than blocking any route's initial load.
    chunkSizeWarningLimit: 600,
  },
})
