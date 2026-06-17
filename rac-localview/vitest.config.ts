import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Test harness for the viewer (RAC v0.21.9). Lives outside src/viewer/ so it
// does not enter the vendored-shell drift hash.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./test/setup.ts'],
    include: ['test/**/*.test.{ts,tsx}'],
  },
});
