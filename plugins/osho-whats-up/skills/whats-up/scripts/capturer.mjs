#!/usr/bin/env node
// What's up ? — capture one state of an app's atelier as a WebP, with headless Chrome over the DevTools protocol.
// No dependency: Node >= 22 (its WebSocket) and an installed Chrome.
//   node capturer.mjs --url <address> --sortie <file.webp> [--largeur 1440] [--hauteur 900] [--echelle 2]
//                     [--qualite 80] [--clip x,y,w,h] [--attendre 20000]
//   node capturer.mjs --chrome-trouve        prints Chrome's path (exit 0) or exits 2
// Waits for `window.__whatsupPret === true` (the atelier's contract), then two frames. Exit: 0 written, 1 error,
// 2 no Chrome, 3 the page never got ready.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, dirname, join } from 'node:path';

const CHEMINS = [
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  '/Applications/Chromium.app/Contents/MacOS/Chromium',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
];
const NOMS = ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'];

export function trouverChrome(env = process.env) {
  if (env.CHROME && existsSync(env.CHROME)) return env.CHROME;
  for (const c of CHEMINS) if (existsSync(c)) return c;
  for (const d of (env.PATH || '').split(delimiter)) for (const n of NOMS) if (d && existsSync(join(d, n))) return join(d, n);
  return null;
}

export function lireArgs(argv) {
  const a = { largeur: 1440, hauteur: 900, echelle: 2, qualite: 80, attendre: 20000 };
  for (let i = 0; i < argv.length; i++) {
    const k = argv[i].replace(/^--/, '');
    if (k === 'chrome-trouve') { a.chromeTrouve = true; continue; }
    a[k] = argv[++i];
  }
  for (const k of ['largeur', 'hauteur', 'echelle', 'qualite', 'attendre']) a[k] = Number(a[k]);
  if (a.clip) {
    const [x, y, width, height] = String(a.clip).split(',').map(Number);
    if ([x, y, width, height].some((v) => !Number.isFinite(v)) || width <= 0 || height <= 0) throw new Error(`--clip x,y,l,h : ${a.clip}`);
    a.clip = { x, y, width, height };
  }
  return a;
}

class Echec extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

const pause = (ms) => new Promise((r) => setTimeout(r, ms));

function lancerChrome(chrome, profil) {
  const p = spawn(chrome, ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profil}`, '--no-first-run',
    '--no-default-browser-check', '--hide-scrollbars', '--disable-gpu', '--mute-audio', 'about:blank'], { stdio: ['ignore', 'ignore', 'pipe'] });
  const adresse = new Promise((ok, ko) => {
    let lu = '';
    p.stderr.on('data', (d) => {
      lu += d;
      const m = lu.match(/DevTools listening on (ws:\/\/\S+)/);
      if (m) ok(m[1]);
    });
    p.on('exit', (c) => ko(new Echec(1, `Chrome s'est arrêté (${c}) : ${lu.slice(-300)}`)));
    setTimeout(() => ko(new Echec(1, 'Chrome ne répond pas')), 15000);
  });
  return { p, adresse };
}

function connecter(url) {
  const ws = new WebSocket(url);
  let n = 0;
  const attentes = new Map();
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.id && attentes.has(m.id)) {
      const { ok, ko } = attentes.get(m.id);
      attentes.delete(m.id);
      m.error ? ko(new Echec(1, `${m.error.message}`)) : ok(m.result);
    }
  };
  const ouvert = new Promise((ok, ko) => { ws.onopen = ok; ws.onerror = () => ko(new Echec(1, 'DevTools injoignable')); });
  const envoyer = (method, params = {}, sessionId) => new Promise((ok, ko) => {
    const id = ++n;
    attentes.set(id, { ok, ko });
    ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  return { ws, ouvert, envoyer };
}

export async function capturer(a, chrome) {
  const profil = mkdtempSync(join(tmpdir(), 'whats-up-chrome-'));
  const { p, adresse } = lancerChrome(chrome, profil);
  try {
    const { ws, ouvert, envoyer } = connecter(await adresse);
    await ouvert;
    const { targetId } = await envoyer('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await envoyer('Target.attachToTarget', { targetId, flatten: true });
    const s = (m, prm) => envoyer(m, prm, sessionId);
    await s('Emulation.setDeviceMetricsOverride', { width: a.largeur, height: a.hauteur, deviceScaleFactor: a.echelle, mobile: false });
    await s('Page.enable');
    await s('Page.navigate', { url: a.url });
    const fin = Date.now() + a.attendre;
    for (;;) {
      const r = await s('Runtime.evaluate', { expression: 'window.__whatsupPret === true', returnByValue: true }).catch(() => null);
      if (r?.result?.value === true) break;
      if (Date.now() > fin) throw new Echec(3, `page pas prête en ${a.attendre} ms (window.__whatsupPret) : ${a.url}`);
      await pause(100);
    }
    // Two frames: what the state changed is painted.
    await s('Runtime.evaluate', { expression: 'new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))', awaitPromise: true });
    const clip = { ...(a.clip ?? { x: 0, y: 0, width: a.largeur, height: a.hauteur }), scale: 1 };
    const { data } = await s('Page.captureScreenshot', { format: 'webp', quality: a.qualite, clip });
    mkdirSync(dirname(a.sortie), { recursive: true });
    writeFileSync(a.sortie, Buffer.from(data, 'base64'));
    await envoyer('Browser.close').catch(() => {});
    ws.close();
  } finally {
    // Chrome writes its profile until it is gone: wait for its exit before removing it.
    if (p.exitCode === null) {
      const fini = new Promise((r) => p.once('exit', r));
      p.kill();
      await Promise.race([fini, pause(5000)]);
    }
    try { rmSync(profil, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }); } catch { /* a temp folder left behind */ }
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  try {
    const a = lireArgs(process.argv.slice(2));
    const chrome = trouverChrome();
    if (!chrome) throw new Echec(2, 'Chrome introuvable : installe-le, ou donne son chemin dans $CHROME.');
    if (a.chromeTrouve) { console.log(chrome); process.exit(0); }
    if (!a.url || !a.sortie) throw new Echec(1, '--url et --sortie sont requis.');
    await capturer(a, chrome);
    console.log(a.sortie);
    process.exit(0);
  } catch (e) {
    process.stderr.write(`capturer : ${e.message}\n`);
    process.exit(typeof e.code === 'number' ? e.code : 1);
  }
}
