import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  // Dev server: proxy /api calls to the FastAPI backend
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  // Production build goes to dist/; FastAPI serves it via StaticFiles
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
