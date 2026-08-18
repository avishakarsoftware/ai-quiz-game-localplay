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
    coverage: {
      provider: 'v8',
      // `include` is REQUIRED for an honest number. Without it v8 only instruments files a test
      // happens to import, so completely untested files vanish from the DENOMINATOR and coverage
      // reads far better than it is: the first measurement (2026-08-09) reported 50.4% while
      // silently omitting 16 files — among them OrganizerPage.tsx, the largest file in the repo.
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/**/*.test.{ts,tsx}',
        'src/__tests__/**',
        'src/test/**',
        'src/**/*.d.ts',
        'src/main.tsx',        // bootstrap: mounts React, nothing to assert
        'src/vite-env.d.ts',
      ],
      reporter: ['text-summary', 'json-summary', 'html'],
    },
  },
})
