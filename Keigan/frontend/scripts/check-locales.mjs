#!/usr/bin/env node
// Checks every locale (except es-MX, which is a sparse override of es) against English:
// valid JSON, identical key sets, identical {{placeholder}} sets per key.
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'i18n', 'locales');
const SKIP = new Set(['en', 'es-MX']);
const PLURAL = /_(zero|one|two|few|many|other)$/;

function flatten(value, prefix = '', out = {}) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [k, v] of Object.entries(value)) flatten(v, prefix ? `${prefix}.${k}` : k, out);
  } else {
    out[prefix] = value;
  }
  return out;
}

function placeholders(text) {
  if (typeof text !== 'string') return [];
  return [...new Set([...text.matchAll(/\{\{\s*([^}\s]+)\s*\}\}/g)].map((m) => m[1]))].sort();
}

// Plural forms may legitimately differ per language, so compare by base key.
const baseKey = (k) => k.replace(PLURAL, '');

function load(file) {
  try {
    return { data: JSON.parse(readFileSync(file, 'utf8')) };
  } catch (e) {
    return { error: e.message };
  }
}

const enDir = join(root, 'en');
const namespaces = readdirSync(enDir).filter((f) => f.endsWith('.json'));
const locales = readdirSync(root, { withFileTypes: true })
  .filter((d) => d.isDirectory() && !SKIP.has(d.name))
  .map((d) => d.name);

let issues = 0;
const report = (msg) => {
  issues += 1;
  console.error(msg);
};

for (const locale of locales) {
  for (const ns of namespaces) {
    const label = `${locale}/${ns}`;
    const file = join(root, locale, ns);
    if (!existsSync(file)) {
      report(`${label}: file missing`);
      continue;
    }
    const en = load(join(enDir, ns));
    const tr = load(file);
    if (tr.error) {
      report(`${label}: invalid JSON (${tr.error})`);
      continue;
    }
    const enFlat = flatten(en.data);
    const trFlat = flatten(tr.data);
    const enKeys = new Set(Object.keys(enFlat).map(baseKey));
    const trKeys = new Set(Object.keys(trFlat).map(baseKey));
    for (const k of enKeys) if (!trKeys.has(k)) report(`${label}: missing key ${k}`);
    for (const k of trKeys) if (!enKeys.has(k)) report(`${label}: extra key ${k}`);
    for (const [k, v] of Object.entries(trFlat)) {
      if (!(k in enFlat)) {
        // plural variants only in target language (e.g. _many) borrow the English _other
        const en2 = enFlat[k.replace(PLURAL, '_other')];
        if (en2 === undefined) continue;
        if (placeholders(en2).join() !== placeholders(v).join()) {
          report(`${label}: placeholder mismatch at ${k}`);
        }
        continue;
      }
      const a = placeholders(enFlat[k]);
      const b = placeholders(v);
      if (a.join('|') !== b.join('|')) {
        report(`${label}: placeholder mismatch at ${k} (en: {${a.join(',')}} vs {${b.join(',')}})`);
      }
    }
    if (typeof tr.data !== 'object') report(`${label}: root must be an object`);
  }
}

// es-MX sanity: must be valid JSON only.
const mxDir = join(root, 'es-MX');
if (existsSync(mxDir)) {
  for (const ns of namespaces) {
    const f = join(mxDir, ns);
    if (existsSync(f) && load(f).error) report(`es-MX/${ns}: invalid JSON`);
  }
}

console.log(
  `Checked ${locales.length} locales x ${namespaces.length} namespaces: ${issues === 0 ? 'zero issues' : `${issues} issue(s)`}.`,
);
process.exit(issues === 0 ? 1 - 1 : 1);
