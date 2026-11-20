#!/usr/bin/env node
// Asserts that the documented text/background and graphic/background token pairs in src/styles/tokens.css
// meet WCAG 2.1 AA in both themes: 4.5:1 for text, 3:1 for UI graphics and focus indicators.
// Semi-transparent colours are composited over the page surface they sit on. Exit code 1 on any failure.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const tokensPath = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'styles', 'tokens.css');

const TEXT_MINIMUM = 4.5;
const GRAPHIC_MINIMUM = 3;

/** Surfaces that body text is drawn on. */
const TEXT_SURFACES = ['surface', 'surface-raised', 'canvas', 'surface-sunken', 'surface-hover', 'surface-selected'];
const TEXT_TOKENS = ['text', 'text-muted', 'text-subtle'];
/** Colours that are fixed in global.css (`text-white`, `text-white/80`, …) rather than themed. */
const FIXED_COLORS = { white: '#ffffff', 'white-80': 'rgba(255, 255, 255, 0.8)', 'white-60': 'rgba(255, 255, 255, 0.6)' };
const TONES = ['success', 'warning', 'danger', 'alert', 'info', 'neutral', 'ai', 'brand'];

/** Pair rules: [foreground token, background token, minimum ratio, description]. Backgrounds with alpha sit on `surface`. */
function documentedPairs() {
  const pairs = [];
  for (const surface of TEXT_SURFACES) {
    for (const text of TEXT_TOKENS) pairs.push([`color-${text}`, `color-${surface}`, TEXT_MINIMUM, 'text']);
    pairs.push(['color-heading-accent', `color-${surface}`, TEXT_MINIMUM, 'heading accent text']);
    pairs.push(['color-action', `color-${surface}`, TEXT_MINIMUM, 'link and action text']);
    for (const tone of TONES) pairs.push([`color-${tone}-text`, `color-${surface}`, TEXT_MINIMUM, `${tone} text`]);
    pairs.push(['color-teal-text', `color-${surface}`, TEXT_MINIMUM, 'teal text']);
  }
  for (const tone of [...TONES, 'teal']) {
    pairs.push([`color-${tone}-text`, `color-${tone}-bg`, TEXT_MINIMUM, `${tone} chip text on its background`]);
  }
  pairs.push(['color-action-subtle-text', 'color-action-subtle', TEXT_MINIMUM, 'subtle button text']);
  pairs.push(['color-action-subtle-text', 'color-action-subtle-hover', TEXT_MINIMUM, 'subtle button text, hover']);
  pairs.push(['color-action-text', 'color-action', TEXT_MINIMUM, 'primary button text']);
  pairs.push(['color-action-text', 'color-action-hover', TEXT_MINIMUM, 'primary button text, hover']);
  pairs.push(['color-action-text', 'color-action-pressed', TEXT_MINIMUM, 'primary button text, pressed']);
  pairs.push(['color-text-on-code', 'color-surface-code', TEXT_MINIMUM, 'code block text']);
  pairs.push(['white', 'color-surface-tooltip', TEXT_MINIMUM, 'tooltip text']);
  pairs.push(['white', 'color-danger-fill', TEXT_MINIMUM, 'danger button text']);
  pairs.push(['white-80', 'color-surface-code', TEXT_MINIMUM, 'code block title']);
  pairs.push(['white-60', 'color-surface-code', TEXT_MINIMUM, 'code block inactive tab']);
  pairs.push(['white-80', 'metlife-dark-blue', TEXT_MINIMUM, 'text on the start of the Ask Keigan gradient']);
  pairs.push(['white-80', 'metlife-purple', TEXT_MINIMUM, 'text on the end of the Ask Keigan gradient']);
  pairs.push(['chart-axis', 'color-surface', TEXT_MINIMUM, 'chart axis labels']);
  pairs.push(['color-action', 'color-surface', GRAPHIC_MINIMUM, 'action graphics']);
  pairs.push(['color-border-control', 'color-surface', GRAPHIC_MINIMUM, 'form control border']);
  pairs.push(['color-border-control', 'color-canvas', GRAPHIC_MINIMUM, 'form control border on the page background']);
  pairs.push(['color-focus-ring-color', 'color-surface', GRAPHIC_MINIMUM, 'focus indicator']);
  pairs.push(['color-focus-ring-color', 'color-canvas', GRAPHIC_MINIMUM, 'focus indicator on the page background']);
  return pairs;
}

function parseBlocks(css) {
  const blocks = { light: {}, dark: {} };
  const blockPattern = /([^{}]+)\{([^{}]*)\}/g;
  for (const [, selector, body] of css.matchAll(blockPattern)) {
    const target = selector.includes('data-theme="dark"') ? blocks.dark : /:root|data-theme="light"/.test(selector) && !selector.includes(':lang') ? blocks.light : null;
    if (!target) continue;
    for (const [, name, value] of body.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) target[name] = value.trim();
  }
  return blocks;
}

function parseColor(value) {
  const hex = value.match(/^#([0-9a-f]{6})$/i);
  if (hex) {
    const n = parseInt(hex[1], 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255, a: 1 };
  }
  const rgba = value.match(/^rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\s*\)$/);
  if (rgba) return { r: +rgba[1], g: +rgba[2], b: +rgba[3], a: rgba[4] === undefined ? 1 : +rgba[4] };
  throw new Error(`Unsupported colour value: ${value}`);
}

const composite = (top, bottom) => ({
  r: top.r * top.a + bottom.r * (1 - top.a),
  g: top.g * top.a + bottom.g * (1 - top.a),
  b: top.b * top.a + bottom.b * (1 - top.a),
  a: 1,
});

function luminance({ r, g, b }) {
  const channel = (v) => {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrastRatio(foreground, background) {
  const [light, dark] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (light + 0.05) / (dark + 0.05);
}

const css = readFileSync(tokensPath, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '');
const blocks = parseBlocks(css);
const themes = { light: blocks.light, dark: { ...blocks.light, ...blocks.dark } };

let failures = 0;
let checked = 0;
for (const [themeName, tokens] of Object.entries(themes)) {
  const resolve = (name) => {
    if (name in FIXED_COLORS) return parseColor(FIXED_COLORS[name]);
    if (!(name in tokens)) throw new Error(`Token --${name} not found in the ${themeName} theme`);
    return parseColor(tokens[name]);
  };
  const page = resolve('color-surface');
  for (const [foregroundName, backgroundName, minimum, description] of documentedPairs()) {
    const background = composite(resolve(backgroundName), page);
    const foreground = composite(resolve(foregroundName), background);
    const ratio = contrastRatio(foreground, background);
    checked += 1;
    if (ratio < minimum) {
      failures += 1;
      console.error(`FAIL [${themeName}] ${description}: --${foregroundName} on --${backgroundName} = ${ratio.toFixed(2)}:1 (needs ${minimum}:1)`);
    }
  }
}

if (failures > 0) {
  console.error(`\n${failures} of ${checked} contrast pairs below WCAG AA.`);
  process.exit(1);
}
console.log(`All ${checked} documented contrast pairs meet WCAG AA in the light and dark themes.`);
