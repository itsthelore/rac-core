#!/usr/bin/env node
/**
 * make-lantern.mjs — generate design/lantern.png, a 16x24 pixel-art
 * lantern placeholder, from a hand-authored pixel grid. PNG is encoded
 * with node:zlib only — no dependencies.
 *
 * This is a PLACEHOLDER for the real mascot (the hooded pixel-art
 * lamplighter). Colours are taken from src/styles/tokens.css.
 *
 * Usage: node scripts/make-lantern.mjs
 */

import { deflateSync } from 'node:zlib';
import { writeFileSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(dirname(fileURLToPath(import.meta.url)));

// Pull colours from the tokens file so the asset can never drift from
// the design system.
const tokensCss = readFileSync(join(root, 'src/styles/tokens.css'), 'utf8');
function token(name) {
  const match = tokensCss.match(
    new RegExp(`--${name}:\\s*(#[0-9a-fA-F]{6})\\b`),
  );
  if (!match) throw new Error(`token --${name} not found in tokens.css`);
  const hex = match[1];
  return [
    parseInt(hex.slice(1, 3), 16),
    parseInt(hex.slice(3, 5), 16),
    parseInt(hex.slice(5, 7), 16),
    255,
  ];
}

// Palette: '.' transparent, '#' dark frame, 'F' lit frame highlight,
// 'g' amber glow, 'G' bright glow core, 'd' dim amber edge.
const palette = {
  '.': [0, 0, 0, 0],
  '#': token('border'),
  F: token('border-active'),
  g: token('accent'),
  G: token('accent-bright'),
  d: token('accent-muted'),
};

// Hand-authored 16x24 grid: handle arc, finial, cap, glass body with a
// bright core, base and foot.
const grid = [
  '................',
  '.....######.....',
  '....##....##....',
  '....#......#....',
  '....#......#....',
  '....##....##....',
  '...####..####...',
  '...#FFFFFFFF#...',
  '..############..',
  '..#dggggggggd#..',
  '..#dggggggggd#..',
  '..#ggGGGGGGgg#..',
  '..#ggGGGGGGgg#..',
  '..#ggGGGGGGgg#..',
  '..#ggGGGGGGgg#..',
  '..#dggggggggd#..',
  '..#dggggggggd#..',
  '..############..',
  '...#FFFFFFFF#...',
  '...##########...',
  '.....######.....',
  '....########....',
  '...##########...',
  '................',
];

const width = grid[0].length;
const height = grid.length;
if (grid.some((row) => row.length !== width)) {
  throw new Error('grid rows must all be the same width');
}

// ---- raw RGBA scanlines with filter byte 0 (None) ----------------------
const raw = Buffer.alloc(height * (1 + width * 4));
let offset = 0;
for (const row of grid) {
  raw[offset++] = 0; // filter: None
  for (const ch of row) {
    const rgba = palette[ch];
    if (!rgba) throw new Error(`unknown palette character: ${ch}`);
    raw[offset++] = rgba[0];
    raw[offset++] = rgba[1];
    raw[offset++] = rgba[2];
    raw[offset++] = rgba[3];
  }
}

// ---- minimal PNG encoder ------------------------------------------------
const CRC_TABLE = new Int32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c;
});

function crc32(buf) {
  let c = 0xffffffff;
  for (const byte of buf) c = CRC_TABLE[(c ^ byte) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function chunk(type, data) {
  const out = Buffer.alloc(12 + data.length);
  out.writeUInt32BE(data.length, 0);
  out.write(type, 4, 'ascii');
  data.copy(out, 8);
  out.writeUInt32BE(crc32(out.subarray(4, 8 + data.length)), 8 + data.length);
  return out;
}

const ihdr = Buffer.alloc(13);
ihdr.writeUInt32BE(width, 0);
ihdr.writeUInt32BE(height, 4);
ihdr[8] = 8; // bit depth
ihdr[9] = 6; // colour type: RGBA
ihdr[10] = 0; // compression
ihdr[11] = 0; // filter
ihdr[12] = 0; // interlace

const png = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  chunk('IHDR', ihdr),
  chunk('IDAT', deflateSync(raw, { level: 9 })),
  chunk('IEND', Buffer.alloc(0)),
]);

const outPath = join(root, 'design/lantern.png');
writeFileSync(outPath, png);
console.log(`wrote ${outPath} (${width}x${height}, ${png.length} bytes)`);
