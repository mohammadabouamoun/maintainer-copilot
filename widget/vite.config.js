import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Plain JS config avoids vite needing to bundle the TS config (no .vite-temp needed)
export default defineConfig({
  plugins: [react()],
  cacheDir: '/tmp/vite-cache',
  server: {
    host: true,
    port: 3000,
  }
})
