import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// package.json sets "type": "module", so this config loads as ESM and
// __dirname is not defined; derive it from import.meta.url instead.
const root = dirname(fileURLToPath(import.meta.url));

// Multi-page static build. Three entry points:
//   /            landing  (Agent B)
//   /viewer/     viewer   (Agent C)
//   /demo/       design-system primitives demo (Agent A)
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    rollupOptions: {
      input: {
        landing: resolve(root, 'index.html'),
        viewer: resolve(root, 'viewer/index.html'),
        demo: resolve(root, 'demo/index.html'),
      },
    },
  },
});
