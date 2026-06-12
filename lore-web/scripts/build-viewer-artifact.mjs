#!/usr/bin/env node
/**
 * build-viewer-artifact.mjs — assemble the single-file export-viewer
 * artifact. No dependencies.
 *
 * Input: the dedicated viewer build at dist/.viewer-build/ (produced by
 * `vite build --config vite.config.viewer.ts`: one JS chunk, one CSS
 * file, no module preloads, no dynamic imports).
 *
 * Output: a self-contained HTML file that opens from file:// with zero
 * network requests:
 *   - the JS chunk and CSS are inlined,
 *   - @font-face rules that reference woff2 files are stripped — the
 *     artifact falls back to the system mono stack (documented in
 *     VIEWER_CONTRACT.md),
 *   - the corpus JSON is embedded as
 *     <script type="application/json" id="lore-export">…</script>.
 *
 * Usage:
 *   node scripts/build-viewer-artifact.mjs
 *     [--corpus path/to/lore-export.json]   default: the committed sample
 *     [--out path/to/output.html]           default: dist/viewer/lore-viewer.html
 *     [--shell-only]                        emit the Portal shell instead
 *
 * --shell-only emits the same single-file artifact with an EMPTY data
 * seam — <script type="application/json" id="lore-export"></script> —
 * for `rac export --html` to inject a corpus into. Default --out then
 * becomes dist/viewer/lore-portal-shell.html.
 */

import { gzipSync } from 'node:zlib';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function arg(flag, fallback) {
  const i = process.argv.indexOf(flag);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

const shellOnly = process.argv.includes('--shell-only');
const corpusPath = resolve(root, arg('--corpus', 'src/viewer/sample/lore-export.sample.json'));
const outPath = resolve(
  root,
  arg('--out', shellOnly ? 'dist/viewer/lore-portal-shell.html' : 'dist/viewer/lore-viewer.html'),
);
const buildDir = resolve(root, 'dist/.viewer-build');
const htmlPath = resolve(buildDir, 'viewer/index.html');

function fail(message) {
  console.error(`build-viewer-artifact: ${message}`);
  process.exit(1);
}

let html;
try {
  html = readFileSync(htmlPath, 'utf8');
} catch {
  fail(`missing ${htmlPath} — run "vite build --config vite.config.viewer.ts" first`);
}

/* ---- locate the one JS chunk and the one CSS file -------------------- */

const scriptTags = [...html.matchAll(/<script type="module"[^>]*\bsrc="([^"]+)"[^>]*><\/script>/g)];
const cssTags = [...html.matchAll(/<link rel="stylesheet"[^>]*\bhref="([^"]+)"[^>]*>/g)];

if (scriptTags.length !== 1) fail(`expected exactly 1 module script, found ${scriptTags.length}`);
if (cssTags.length !== 1) fail(`expected exactly 1 stylesheet link, found ${cssTags.length}`);

const htmlDir = dirname(htmlPath);
const readAsset = (href) => readFileSync(resolve(htmlDir, href), 'utf8');

/* ---- JS: must be self-contained --------------------------------------- */

let js = readAsset(scriptTags[0][1]);

// Inline <script type="module"> executes from file:// only if nothing
// external is imported. The single-entry config should guarantee that;
// verify rather than trust.
if (/(^|[;\s])import\s*(["']|\()/.test(js) || /__vitePreload/.test(js)) {
  fail('viewer bundle contains external imports or preload helpers — not inlineable');
}
// </script> inside the inlined JS would terminate the tag early. "\/"
// is a valid escape in JS strings and regexes, so this is safe.
js = js.replaceAll('</script', '<\\/script');

/* ---- CSS: strip file-referencing @font-face, verify no url() ---------- */

let css = readAsset(cssTags[0][1]);

// Drop @font-face blocks that reference files (woff2). The local-only
// metric fallback @font-face (src: local(...)) is kept, so the artifact
// renders in the system mono stack from --font-mono. Inlining ~200KB of
// fonts is deliberately avoided — see VIEWER_CONTRACT.md.
css = css.replace(/@font-face\s*\{[^}]*url\([^}]*\}/g, '');

const fileUrls = [...css.matchAll(/url\(\s*(?!["']?data:)[^)]*\)/g)];
if (fileUrls.length > 0) {
  fail(`CSS still references files after font stripping: ${fileUrls.map((m) => m[0]).join(', ')}`);
}

/* ---- corpus JSON ------------------------------------------------------- */

// Shell-only: the data seam stays empty (no whitespace inside the
// element) so the exporter can substitute its corpus byte-for-byte.
let corpus = null;
let corpusInline = '';
if (!shellOnly) {
  const corpusRaw = readFileSync(corpusPath, 'utf8');
  corpus = JSON.parse(corpusRaw); // validate
  // Make the JSON safe inside a <script> element. Both replacements are
  // valid JSON escapes, so the payload parses unchanged.
  corpusInline = JSON.stringify(corpus)
    .replaceAll('</', '<\\/')
    .replaceAll('<!--', '<\\u0021--');
}

/* ---- assemble ---------------------------------------------------------- */

html = html.replace(cssTags[0][0], () => `<style>\n${css}\n</style>`);
html = html.replace(
  scriptTags[0][0],
  () =>
    `<script type="application/json" id="lore-export">${corpusInline}</script>\n` +
    `<script type="module">\n${js}\n</script>`,
);
// Belt and braces: no preload/prefetch links survive.
html = html.replace(/<link rel="(?:modulepreload|preload|prefetch)"[^>]*>/g, '');

/* ---- verify: no external references ------------------------------------ */

const external = [
  ...html.matchAll(/\s(?:src|href)="(?!#|data:)[^"]*"/g),
].filter((m) => !m[0].startsWith(' href="#'));
if (external.length > 0) {
  fail(`artifact still has external references: ${external.map((m) => m[0].trim()).join(', ')}`);
}
if (/url\(\s*(?!["']?data:)[^)]*\)/.test(html.match(/<style>[\s\S]*?<\/style>/)?.[0] ?? '')) {
  fail('artifact CSS still has url() file references');
}

mkdirSync(dirname(outPath), { recursive: true });
writeFileSync(outPath, html);

const bytes = Buffer.byteLength(html);
const gzip = gzipSync(Buffer.from(html), { level: 9 }).length;
const kb = (n) => `${(n / 1024).toFixed(1)} KB`;
console.log(`wrote ${outPath}`);
if (corpus) {
  console.log(`  corpus: ${corpusPath} (${corpus.artifacts.length} artifacts)`);
} else {
  console.log('  corpus: none (shell-only — empty #lore-export data seam)');
}
console.log(`  size: ${kb(bytes)} raw, ${kb(gzip)} gzipped`);
