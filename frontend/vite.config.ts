/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: process.env.VITE_BASE_PATH || '/',
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.ts',
    // ios/android hold native build artifacts (incl. RevenueCat SPM checkouts with their own *.test.ts) — never scan them.
    exclude: ['node_modules/**', 'dist/**', 'e2e/**', 'ios/**', 'android/**'],
  },
})
