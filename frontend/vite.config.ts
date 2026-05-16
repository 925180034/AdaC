import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ['u307207-94cd-0c29b003.nmb1.seetacloud.com'],
    proxy: {
      '/tables': 'http://localhost:6008',
      '/datasets': 'http://localhost:6008',
      '/runtime': 'http://localhost:6008',
      '/tasks': 'http://localhost:6008',
      '/discover': 'http://localhost:6008',
      '/match': 'http://localhost:6008',
      '/integrate': 'http://localhost:6008',
      '/healthz': 'http://localhost:6008',
      '/metrics': 'http://localhost:6008',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
