// Prerender the landing page into dist/index.html so the hero content
// paints before any JavaScript loads (LCP budget: 1.5s on throttled
// mobile). Runs AFTER `vite build`:
//
//   1. SSR-build src/landing/prerender-entry.tsx into dist/.ssr/
//   2. import it, render the landing to an HTML string
//   3. verify/repair asset URLs against the client build's dist/assets
//   4. inject the string into <div id="root"> in dist/index.html
//   5. delete dist/.ssr
//
// No new dependencies: react-dom/server and Vite's JS API only.

import { readFileSync, writeFileSync, readdirSync, existsSync, rmSync } from 'node:fs';
import { dirname, resolve, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'vite';
import react from '@vitejs/plugin-react';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const distDir = join(root, 'dist');
const ssrDir = join(distDir, '.ssr');
const indexPath = join(distDir, 'index.html');

if (!existsSync(indexPath)) {
  console.error('prerender: dist/index.html not found — run `vite build` first.');
  process.exit(1);
}

// 1. SSR build. Deliberately not loading vite.config.ts: its multi-page
// rollup inputs would fight the single SSR entry. base './' matches the
// client build so asset URLs come out in the same shape.
await build({
  configFile: false,
  root,
  base: './',
  plugins: [react()],
  logLevel: 'warn',
  build: {
    ssr: resolve(root, 'src/landing/prerender-entry.tsx'),
    outDir: ssrDir,
    emptyOutDir: true,
  },
});

try {
  // 2. Render.
  const entry = join(ssrDir, 'prerender-entry.js');
  const { render } = await import(pathToFileURL(entry).href);
  let html = render();
  if (!html || !html.includes('hero__title')) {
    throw new Error('prerender: rendered HTML is empty or missing the hero.');
  }

  // 3a. The SSR build emits root-absolute asset URLs ("/assets/...")
  // even with base './'; the client build is relative. dist/index.html
  // lives at the dist root, so './assets/...' is the correct form and
  // keeps subpath deployments working.
  html = html.replaceAll('"/assets/', '"./assets/');

  // 3b. Asset URL verification. Static asset imports must resolve to the
  // SAME hashed filenames the client build emitted. Vite hashes by
  // content so they normally agree, but if the SSR build disagrees,
  // rewrite each reference to the client build's actual filename by
  // matching `<name>-<hash>.<ext>` on name + extension.
  const clientAssets = readdirSync(join(distDir, 'assets'));
  const assetRef = /(?:\.\/)?assets\/([\w.-]+)/g;
  const misses = [];
  html = html.replaceAll(assetRef, (full, file) => {
    if (clientAssets.includes(file)) return full;
    const m = file.match(/^(.*)-[\w]+(\.[a-z0-9]+)$/i);
    const replacement =
      m && clientAssets.find((a) => a.startsWith(`${m[1]}-`) && a.endsWith(m[2]));
    if (replacement) {
      misses.push(`${file} -> ${replacement}`);
      return full.replace(file, replacement);
    }
    throw new Error(`prerender: no client asset matches "${file}".`);
  });
  if (misses.length > 0) {
    console.warn(`prerender: rewrote ${misses.length} asset URL(s):`);
    for (const m of misses) console.warn(`  ${m}`);
  }

  // 4. Inject, and inline the landing's stylesheets. The page CSS is a
  // few kilobytes; inlining removes the render-blocking requests so the
  // prerendered content paints immediately.
  const marker = '<div id="root"></div>';
  let indexHtml = readFileSync(indexPath, 'utf8');
  if (!indexHtml.includes(marker)) {
    throw new Error(`prerender: ${marker} not found in dist/index.html.`);
  }
  indexHtml = indexHtml.replace(marker, `<div id="root">${html}</div>`);

  // Preload the hero mascot — it is the LCP element, and without a hint
  // it queues behind fonts and scripts on throttled connections.
  const heroAsset = html.match(/\.\/assets\/lamplighter-[\w-]+\.png/)?.[0];
  if (heroAsset) {
    indexHtml = indexHtml.replace(
      '</title>',
      `</title>\n    <link rel="preload" as="image" href="${heroAsset}" fetchpriority="high" />`,
    );
  }
  indexHtml = indexHtml.replace(
    /<link rel="stylesheet"[^>]*href="\.\/(assets\/[\w.-]+\.css)"[^>]*>/g,
    (tag, href) => {
      const cssPath = join(distDir, href);
      if (!existsSync(cssPath)) return tag;
      // url() refs in built CSS are relative to assets/; re-anchor them
      // to the document root where the inlined style now lives.
      const css = readFileSync(cssPath, 'utf8')
        .trim()
        .replaceAll('url(./', 'url(./assets/');
      return `<style>${css}</style>`;
    },
  );
  writeFileSync(indexPath, indexHtml);
  console.log('prerender: landing injected into dist/index.html');
} finally {
  // 5. Clean up the SSR build either way.
  rmSync(ssrDir, { recursive: true, force: true });
}
