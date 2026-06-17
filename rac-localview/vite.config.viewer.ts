import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const root = dirname(fileURLToPath(import.meta.url));

/**
 * Dedicated single-entry build for the export-viewer artifact
 * (`lore export --html`). Produces exactly one JS chunk and one CSS
 * file in dist/.viewer-build/, which scripts/build-viewer-artifact.mjs
 * then inlines into a single self-contained HTML file at
 * dist/viewer/lore-viewer.html.
 *
 * The hosted multi-page build (vite.config.ts) is untouched; this
 * config exists so the artifact bundle has no shared chunks, no module
 * preloads and no dynamic imports — inline <script type="module"> only
 * works from file:// when nothing external is imported.
 */
export default defineConfig({
  base: './',
  plugins: [react()],
  build: {
    outDir: 'dist/.viewer-build',
    emptyOutDir: true,
    modulePreload: false,
    cssCodeSplit: false,
    rollupOptions: {
      input: resolve(root, 'viewer/index.html'),
      output: {
        inlineDynamicImports: true,
        manualChunks: undefined,
      },
    },
  },
});
