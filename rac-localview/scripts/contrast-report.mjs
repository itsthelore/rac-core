#!/usr/bin/env node
/**
 * contrast-report.mjs — WCAG 2.x contrast audit for the Lore tokens.
 *
 * Parses src/styles/tokens.css, computes the contrast ratio of every
 * text colour the system uses against each of the three surfaces, and
 * prints a pass/fail table at the AA threshold (4.5:1). No dependencies;
 * relative luminance is implemented per WCAG 2.x.
 *
 * Exit code 1 if any used text/surface pair fails.
 *
 * Usage: node scripts/contrast-report.mjs   (or: npm run contrast)
 */

import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const css = readFileSync(join(root, 'src/styles/tokens.css'), 'utf8');

// ---- token parsing ------------------------------------------------------
const tokens = {};
for (const match of css.matchAll(/--([a-z-]+):\s*(#[0-9a-fA-F]{6})\b/g)) {
  tokens[match[1]] = match[2];
}

// ---- WCAG maths ---------------------------------------------------------
function srgbChannel(v) {
  const c = v / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function luminance(hex) {
  const r = srgbChannel(parseInt(hex.slice(1, 3), 16));
  const g = srgbChannel(parseInt(hex.slice(3, 5), 16));
  const b = srgbChannel(parseInt(hex.slice(5, 7), 16));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function contrast(hexA, hexB) {
  const la = luminance(hexA);
  const lb = luminance(hexB);
  const [hi, lo] = la >= lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

// ---- the pairs the system actually uses as text -------------------------
const TEXT_TOKENS = [
  'text',
  'text-muted',
  'accent',
  'accent-bright',
  'info',
  'success',
  'warning',
  'error',
];
const SURFACE_TOKENS = ['bg', 'bg-panel', 'bg-element'];
const THRESHOLD = 4.5;

// Tokens never used as text, excluded from the audit by design.
const EXCLUDED = [
  'accent-muted (fill/selected-row background only)',
  'border-subtle, border, border-active (borders only)',
];

const missing = [...TEXT_TOKENS, ...SURFACE_TOKENS].filter(
  (name) => !tokens[name],
);
if (missing.length > 0) {
  console.error(`missing tokens in tokens.css: ${missing.join(', ')}`);
  process.exit(1);
}

// ---- report -------------------------------------------------------------
const col = 16;
let failures = 0;

console.log('Lore token contrast report — WCAG AA, threshold 4.5:1');
console.log(`source: src/styles/tokens.css\n`);

const header =
  'text \\ surface'.padEnd(col) +
  SURFACE_TOKENS.map((s) => `${s} ${tokens[s]}`.padEnd(col + 6)).join('');
console.log(header);
console.log('-'.repeat(header.length));

for (const text of TEXT_TOKENS) {
  let line = `${text}`.padEnd(col);
  for (const surface of SURFACE_TOKENS) {
    const ratio = contrast(tokens[text], tokens[surface]);
    const pass = ratio >= THRESHOLD;
    if (!pass) failures += 1;
    line += `${ratio.toFixed(2)}:1 ${pass ? 'PASS' : 'FAIL'}`.padEnd(col + 6);
  }
  console.log(line);
}

console.log('\nexcluded (never used as text):');
for (const note of EXCLUDED) console.log(`  - ${note}`);

if (failures > 0) {
  console.error(
    `\n${failures} pair(s) below ${THRESHOLD}:1 — fix the token, not the use site.`,
  );
  process.exit(1);
}
console.log(
  `\nall ${TEXT_TOKENS.length * SURFACE_TOKENS.length} used pairs pass at ${THRESHOLD}:1.`,
);
