import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  envDir: fileURLToPath(new URL('..', import.meta.url)),
  server: { host: '127.0.0.1', port: 5173, strictPort: true },
  test: {
    coverage: {
      include: ['src/App.tsx', 'src/components/**/*.{ts,tsx}', 'src/services/**/*.{ts,tsx}'],
      thresholds: { statements: 80, branches: 80, functions: 80, lines: 80 },
    },
  },
})
