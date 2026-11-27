#!/usr/bin/env bash
# Auto-test des fonctions pures de whats-up.js (fiches dues, filtre CSS) et des fiches d'exemple, sous node, sans navigateur.
#   bash test_whats_up.sh
set -eu
command -v node >/dev/null 2>&1 || { echo "node absent : test sauté"; exit 0; }
assets="$(cd "$(dirname "$0")/../assets" && pwd)"
node --input-type=module - "$assets" <<'JS'
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
const assets = process.argv[2];
const { dues, filtrerCss, cle } = await import(`${assets}/whats-up.js`);

assert.deepEqual(dues(['2026-01-01', '2026-01-02'], null), ['2026-01-02']);
assert.deepEqual(dues(['2026-01-01', '2026-01-02', '2026-01-03'], '2026-01-01'), ['2026-01-02', '2026-01-03']);
assert.deepEqual(dues(['2026-01-01'], '2026-01-01'), []);
assert.deepEqual(dues([], null), []);
assert.deepEqual(dues(['2026-01-01-9', '2026-01-01-10'], '2026-01-01-9'), ['2026-01-01-10']);
assert.ok(cle('2026-01-01-10') > cle('2026-01-01-9'));

assert.equal(filtrerCss('@import url(https://x/y.css);\n.a{color:red}'), '\n.a{color:red}');
assert.doesNotMatch(filtrerCss('.a{background:url(//cdn/x.png)}'), /cdn/);
assert.doesNotMatch(filtrerCss('.a{background:url("https://x/y.png")}'), /https/);
assert.match(filtrerCss('.a{background:url(data:image/png;base64,AA)}'), /data:image/);
assert.match(filtrerCss('.a{background:url(./fond.png)}'), /fond\.png/);

const ex = `${assets}/exemple`;
const index = JSON.parse(readFileSync(`${ex}/index.json`, 'utf8')).ids;
const fiches = readdirSync(ex).filter(n => n.endsWith('.json') && n !== 'index.json').map(n => n.slice(0, -5)).sort();
assert.deepEqual(index, fiches);
for (const id of fiches) {
  const f = JSON.parse(readFileSync(`${ex}/${id}.json`, 'utf8'));
  assert.equal(f.id, id);
  assert.ok(f.ecrans.length > 0 && f.ecrans.every(e => e.etiquette && e.titre && e.texte && e.scene));
}
console.log('whats-up OK');
JS
