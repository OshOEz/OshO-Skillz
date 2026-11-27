#!/usr/bin/env node
// What's up ? — capture one state of an app's atelier as a WebP, with headless Chrome over the DevTools protocol.
// No dependency: Node >= 22 (its WebSocket) and an installed Chrome.
//   node capturer.mjs --url <address> --sortie <file.webp> [--largeur 1440] [--hauteur 900] [--echelle 2]
//                     [--qualite 80] [--clip x,y,w,h] [--attendre 20000]
//   node capturer.mjs --chrome-trouve        prints Chrome's path (exit 0) or exits 2
// Waits for `window.__whatsupPret === true` (the atelier's contract), then two frames. Exit: 0 written, 1 error,
// 2 no Chrome, 3 the page never got ready.
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, mkdtempSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { delimiter, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

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
  for (const k of ['largeur', 'hauteur', 'echelle', 'qualite', 'attendre']) {
    a[k] = Number(a[k]);
    if (!Number.isFinite(a[k]) || a[k] <= 0) throw new Echec(1, `--${k} : un nombre positif attendu`);
  }
  if (a.qualite > 100) throw new Echec(1, '--qualite : de 1 à 100');
  if (a.clip) {
    const [x, y, width, height] = String(a.clip).split(',').map(Number);
    const ok = [x, y, width, height].every(Number.isFinite) && x >= 0 && y >= 0 && width > 0 && height > 0
      && x + width <= a.largeur && y + height <= a.hauteur;
    if (!ok) throw new Echec(1, `--clip x,y,l,h dans la page (${a.largeur} × ${a.hauteur}) : ${a.clip}`);
    a.clip = { x, y, width, height };
  }
  return a;
}

class Echec extends Error {
  constructor(code, message) { super(message); this.code = code; }
}

const pause = (ms) => new Promise((r) => setTimeout(r, ms));

/** `promesse`, or `erreur` after `ms`: no DevTools call may hang the capture (an alert(), a blocked page, a crash). */
const borner = (promesse, ms, erreur) => Promise.race([promesse, new Promise((_, ko) => setTimeout(() => ko(erreur), ms).unref())]);

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
    p.on('error', (e) => ko(new Echec(2, `Chrome ne se lance pas (${e.message}) : vérifie $CHROME.`)));
    setTimeout(() => ko(new Echec(1, 'Chrome ne répond pas')), 15000).unref();
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
  // Chrome gone: every pending call fails instead of waiting forever.
  ws.onclose = () => { for (const { ko } of attentes.values()) ko(new Echec(1, 'Chrome a fermé la connexion')); attentes.clear(); };
  const envoyer = (method, params = {}, sessionId) => new Promise((ok, ko) => {
    const id = ++n;
    attentes.set(id, { ok, ko });
    ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
  return { ws, ouvert, envoyer };
}

// The running Chrome and its profile, so a signal can clean them up too.
let enCours = null;

async function arreter() {
  if (!enCours) return;
  const { p, profil } = enCours;
  enCours = null;
  // Chrome writes its profile until it is gone: wait for its exit before removing it.
  if (p.exitCode === null && p.signalCode === null) {
    const fini = new Promise((r) => p.once('exit', r));
    p.kill();
    await Promise.race([fini, pause(5000)]);
  }
  try { rmSync(profil, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }); } catch { /* a temp folder left behind */ }
}

export async function capturer(a, chrome) {
  const profil = mkdtempSync(join(tmpdir(), 'whats-up-chrome-'));
  const { p, adresse } = lancerChrome(chrome, profil);
  enCours = { p, profil };
  try {
    await borner(prendre(a, adresse), a.attendre + 30000, new Echec(1, 'Chrome ne répond plus'));
  } finally {
    await arreter();
  }
}

async function prendre(a, adresse) {
  {
    const { ws, ouvert, envoyer } = connecter(await adresse);
    await ouvert;
    const { targetId } = await envoyer('Target.createTarget', { url: 'about:blank' });
    const { sessionId } = await envoyer('Target.attachToTarget', { targetId, flatten: true });
    const s = (m, prm) => envoyer(m, prm, sessionId);
    await s('Emulation.setDeviceMetricsOverride', { width: a.largeur, height: a.hauteur, deviceScaleFactor: a.echelle, mobile: false });
    await s('Page.enable');
    const nav = await s('Page.navigate', { url: a.url });
    if (nav.errorText) throw new Echec(1, `atelier injoignable (${nav.errorText}) : ${a.url}`);
    const fin = Date.now() + a.attendre;
    const pret = () => borner(s('Runtime.evaluate', { expression: 'window.__whatsupPret === true', returnByValue: true }),
      Math.max(fin - Date.now(), 200), null).then((r) => r?.result?.value === true, () => false);
    for (;;) {
      if (await pret()) break;
      if (Date.now() > fin) throw new Echec(3, `page pas prête en ${a.attendre} ms (window.__whatsupPret) : ${a.url}`);
      await pause(100);
    }
    // Two frames: what the state changed is painted.
    await borner(s('Runtime.evaluate', { expression: 'new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))', awaitPromise: true }),
      5000, new Echec(3, 'la page ne se dessine plus'));
    // Reloaded meanwhile (a dev server that reloads on edit): not the state that was asked.
    if (!(await pret())) throw new Echec(1, `la page s'est rechargée pendant la capture : relance-la : ${a.url}`);
    const clip = { ...(a.clip ?? { x: 0, y: 0, width: a.largeur, height: a.hauteur }), scale: 1 };
    const { data } = await s('Page.captureScreenshot', { format: 'webp', quality: a.qualite, clip });
    mkdirSync(dirname(a.sortie), { recursive: true });
    writeFileSync(a.sortie, Buffer.from(data, 'base64'));
    await borner(envoyer('Browser.close'), 2000, null).catch(() => {});
    ws.close();
  }
}

// Run as a script (through a path with spaces or a symlink too), not when imported.
const principal = (() => { try { return realpathSync(process.argv[1]) === fileURLToPath(import.meta.url); } catch { return false; } })();
if (principal) {
  for (const [sig, code] of [['SIGINT', 130], ['SIGTERM', 143]]) process.on(sig, () => { arreter().finally(() => process.exit(code)); });
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
