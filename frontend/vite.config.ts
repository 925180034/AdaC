import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react()],
  server: {
    allowedHosts: ['u307207-94cd-0c29b003.nmb1.seetacloud.com'],
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
    exclude: ['e2e/**', 'node_modules/**', 'dist/**'],
  },
})
