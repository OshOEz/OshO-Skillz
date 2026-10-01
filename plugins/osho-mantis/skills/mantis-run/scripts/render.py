#!/usr/bin/env python3
"""Rapport osho-mantis : findings Mantis → README.md, patches/<id>.diff, dashboard.html
  python3 render.py <dossier d'audit>
"""
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

BUCKETS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
REJECTED_STATUS = {"FALSE_POSITIVE", "DUPLICATE"}
REJECTED_VIABILITY = {"NON_VIABLE", "SAMPLE_OR_TEST"}
NA = "non évalué à ce niveau"
LEVEL_BANNERS = {
    "Light": "Analyse statique : pas de reproduction, correctifs proposés non vérifiés.",
    "Sharp": "Reproduction Docker des High+ et correctifs vérifiés par re-attaque.",
    "Savage": "Reproduction de tout le viable, chaînes d'exploits.",
    "Overkill": "Revue exhaustive de chaque fichier, 3 tours.",
}


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def load_findings(workspace):
    findings, unreadable = [], []
    for p in sorted(Path(workspace, "findings").glob("*.json")):
        f = load_json(p, None)
        if isinstance(f, dict) and f.get("title"):
            f["id"] = str(f.get("id") or p.stem)
            findings.append(f)
        else:
            unreadable.append(p.name)
    return findings, unreadable


def safe_id(f):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", f["id"])


def bucket(f):
    if f.get("status") in REJECTED_STATUS or f.get("production_viability") in REJECTED_VIABILITY:
        return "REJECTED"
    level = str(f.get("priority") or f.get("severity") or "LOW").upper()
    return level if level in BUCKETS else "LOW"


def sort_key(f):
    return (-(f.get("mantis_risk_score") or 0), str(f["title"]).lower())


def stats(findings):
    b = [bucket(f) for f in findings]
    kept = [f for f, x in zip(findings, b) if x != "REJECTED"]
    return {"by_bucket": {k: b.count(k) for k in BUCKETS + ["REJECTED"]}, "total": len(findings),
            "confirmed": sum(f.get("status") == "VALID" for f in kept),
            "reproduced": sum(f.get("repro_status") == "reproduced" for f in kept),
            "patched": sum(f.get("patch_status") == "VERIFIED_SECURE" for f in kept)}


def duration(start, end):
    try:
        minutes = int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() // 60)
    except (TypeError, ValueError):
        return ""
    return f"{minutes // 60} h {minutes % 60:02d} min"


def text(value):
    """Valeur de finding pour du Markdown : jamais de HTML actif"""
    if value in (None, "", []):
        return NA
    value = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
    return html.escape(value, quote=False)


def cell(value):
    return text(value).replace("|", "\\|").replace("\n", " ")


def summary(f):
    """executive_summary (set by calibrate) is absent in Light; fall back to impact"""
    return f.get("executive_summary") or f.get("impact")


def block(code, lang=""):
    longest = max((len(m) for m in re.findall(r"`+", code)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{lang}\n{code.rstrip()}\n{fence}"


def readme(meta, findings, unreadable, st):
    kept = sorted((f for f in findings if bucket(f) != "REJECTED"), key=lambda f: (BUCKETS.index(bucket(f)), sort_key(f)))
    rejected = [f for f in findings if bucket(f) == "REJECTED"]
    out = [f"# Audit de sécurité — {text(meta['repo_name'])}", "",
           f"{meta['started_at'] or '?'} · niveau **{meta['level'] or '?'}** · Mantis `{meta['mantis_commit'] or '?'}`"
           + (f" · durée {meta['duration']}" if meta["duration"] else ""), ""]
    if meta["level_banner"]:
        out += [text(meta["level_banner"]), ""]
    out += ["[Ouvrir le dashboard](dashboard.html) : GitHub affiche le HTML en source, ouvrez le fichier en local.", "",
           "| Critical | High | Medium | Low | Écartés |", "|---|---|---|---|---|",
           "| " + " | ".join(str(st["by_bucket"][k]) for k in BUCKETS + ["REJECTED"]) + " |", ""]
    if not findings:
        out += ["**Aucun finding** : rien n'a été signalé à ce niveau d'audit.", ""]
    if kept:
        out += ["## Findings", "", "| Sévérité | Titre | Emplacement | Reproduit | Patch vérifié |", "|---|---|---|---|---|"]
        out += [f"| {bucket(f)} | {cell(f['title'])} | {cell(f.get('code_paths'))} | "
                f"{'oui' if f.get('repro_status') == 'reproduced' else 'non'} | "
                f"{'oui' if f.get('patch_status') == 'VERIFIED_SECURE' else 'non'} |" for f in kept]
        out.append("")
        for f in kept:
            out += [f"### [{bucket(f)}] {text(f['title'])}", "",
                    f"**Résumé** : {text(summary(f))}", "",
                    f"**Emplacement** : {text(f.get('code_paths'))} · **CWE** : {text(f.get('cwe'))}", "",
                    f"**Problème** : {text(f.get('description'))}", "",
                    f"**Impact** : {text(f.get('impact'))}", "",
                    f"**Cas testé** : {text(f.get('repro_status'))}"]
            for key in ("run_command", "repro_output"):
                if f.get(key):
                    out += ["", block(str(f[key]), "bash" if key == "run_command" else "")]
            out += ["", f"**Correction** ({text(f.get('patch_status'))})", ""]
            if f.get("patch_diff"):
                out += [block(str(f["patch_diff"]), "diff"), "",
                        f"Appliquer depuis la racine du repo : `git apply osho-mantis/{meta['audit_name']}/patches/{f['_file']}.diff`"]
            else:
                out.append(text(f.get("mitigation")))
            out.append("")
    if rejected:
        out += ["## Écartés", ""]
        out += [f"- {text(f['title'])} — {text(f.get('status') or f.get('production_viability'))} : "
                f"{text((f.get('critic_reasoning') or f.get('reasoning') or '')[:200])}" for f in rejected]
        out.append("")
    out += ["## Limites", ""] + [f"- {text(n)}" for n in meta["notes"]]
    if unreadable:
        out.append(f"- Fichiers de finding illisibles, ignorés : {', '.join(unreadable)}")
    out += ["- Findings produits par IA : à vérifier par un humain avant tout signalement.", ""]
    return "\n".join(out)


def safe_json(obj):
    return (json.dumps(obj, ensure_ascii=False)
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e"))


def render(audit_dir):
    audit_dir = Path(audit_dir).resolve()
    campaign = load_json(audit_dir / "campaign.json", {})
    state = load_json(audit_dir / "state.json", {})
    findings, unreadable = load_findings(audit_dir / "workspace")
    # Compute _file for each finding with deduplication against all used names
    used = set()
    for f in findings:
        name = safe_id(f)
        if name in used:
            suffix = 2
            while f"{name}-{suffix}" in used:
                suffix += 1
            name = f"{name}-{suffix}"
        used.add(name)
        f["_file"] = name
    meta = {"repo_name": Path(campaign.get("repo") or audit_dir.parent.parent).name,
            "audit_name": audit_dir.name, "level": campaign.get("level"),
            "mantis_commit": campaign.get("mantis_commit"), "started_at": campaign.get("started_at"),
            "duration": duration(campaign.get("started_at"), campaign.get("finished_at")),
            "notes": state.get("notes", []),
            "stages": [k for k, v in state.get("stages", {}).items() if v == "done"]}
    meta["reproduce_done"] = "reproduce" in meta["stages"]
    meta["level_banner"] = LEVEL_BANNERS.get(meta["level"], "")
    st = stats(findings)
    (audit_dir / "README.md").write_text(readme(meta, findings, unreadable, st))
    for f in findings:
        if f.get("patch_diff") and bucket(f) != "REJECTED":
            (audit_dir / "patches").mkdir(exist_ok=True)
            (audit_dir / "patches" / f"{f['_file']}.diff").write_text(str(f["patch_diff"]).rstrip("\n") + "\n")
    payload = {"meta": meta, "stats": st,
               "findings": [dict(f, _bucket=bucket(f), _summary=summary(f)) for f in sorted(findings, key=sort_key)]}
    (audit_dir / "dashboard.html").write_text(TEMPLATE.replace("__DATA__", safe_json(payload)))


TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audit Mantis</title>
<style>
:root{--bg:#f7f7f8;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e6;--crit:#c62828;--high:#e65100;--med:#b58900;--low:#2e7d32;--rej:#757575;--add:#e6f4ea;--del:#fdecea}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1e1e21;--fg:#ececf0;--muted:#a0a0a8;--line:#2e2e33;--add:#12301c;--del:#3a1614}}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,system-ui,sans-serif;background:var(--bg);color:var(--fg)}
header,main{max-width:1400px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:0 0 4px}
main>h2{font-size:15px;margin:24px 0 8px}
.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px}
.stat b{display:block;font-size:22px}
.board{display:grid;grid-template-columns:repeat(5,minmax(220px,1fr));gap:10px;overflow-x:auto}
.col{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px;min-height:80px}
.col h3{font-size:13px;margin:0 0 8px;display:flex;justify-content:space-between}
summary{cursor:pointer;list-style:none}
.card{display:block;width:100%;text-align:left;background:var(--bg);color:inherit;font:inherit;border:1px solid var(--line);border-left:4px solid var(--c);border-radius:6px;padding:8px;margin-bottom:6px;cursor:pointer}
.card:hover,.card:focus-visible{outline:2px solid var(--c)}
.badge{display:inline-block;font-size:11px;padding:0 6px;border-radius:10px;border:1px solid var(--line);margin:4px 4px 0 0}
#panel{position:fixed;top:0;right:0;height:100%;width:min(640px,100%);background:var(--card);border-left:1px solid var(--line);box-shadow:-4px 0 16px rgba(0,0,0,.15);transform:translateX(100%);transition:transform .2s;display:flex;flex-direction:column}
#panel.open{transform:none}
.phead{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;padding:16px}
.phead h2{margin:0;font-size:16px}
.phead button{background:none;border:0;color:inherit;font-size:18px;cursor:pointer}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);padding:0 16px}
.tabs button{background:none;border:0;border-bottom:2px solid transparent;padding:8px;color:inherit;font:inherit;cursor:pointer}
.tabs button[aria-selected=true]{border-color:var(--fg);font-weight:600}
#content{padding:16px;overflow:auto}
dt{font-weight:600;margin-top:12px}
dd{margin:2px 0 0;white-space:pre-wrap}
pre{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px;overflow:auto;white-space:pre-wrap;margin:4px 0}
.add{background:var(--add)}.del{background:var(--del)}
@media (max-width:700px){.board{grid-template-columns:1fr}}
</style>
</head>
<body>
<header><h1 id="title"></h1><div id="meta" class="muted"></div><div id="stages" class="muted"></div></header>
<main>
<div id="level-banner"></div>
<section class="grid" id="stats"></section>
<h2>Points critiques</h2><section class="grid" id="critical"></section>
<h2>Kanban</h2><section class="board" id="board"></section>
</main>
<aside id="panel" aria-hidden="true">
<div class="phead"><h2 id="ptitle"></h2><button id="close" aria-label="Fermer">✕</button></div>
<nav class="tabs" role="tablist" id="tabs"></nav>
<div id="content"></div>
</aside>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const NA = 'non évalué à ce niveau';
const COLS = [['CRITICAL', 'Critical', '--crit'], ['HIGH', 'High', '--high'], ['MEDIUM', 'Medium', '--med'], ['LOW', 'Low', '--low'], ['REJECTED', 'Écartés', '--rej']];
const m = D.meta, s = D.stats;

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v; else if (k === 'style') e.style.cssText = v; else e.setAttribute(k, v);
  }
  for (const k of kids) e.append(k);
  return e;
}
function val(f, k) {
  const x = f[k];
  if (x == null || x === '' || (Array.isArray(x) && !x.length)) return NA;
  return Array.isArray(x) ? x.join(', ') : String(x);
}
function card(f) {
  const col = COLS.find(c => c[0] === f._bucket);
  const b = el('button', {class: 'card', style: '--c:var(' + col[2] + ')'},
    el('div', {}, el('strong', {}, String(f.title))), el('div', {class: 'muted'}, val(f, 'code_paths')));
  if (f.cwe) b.append(el('span', {class: 'badge'}, String(f.cwe)));
  if (f.repro_status === 'reproduced') b.append(el('span', {class: 'badge'}, 'reproduit'));
  if (f.patch_status === 'VERIFIED_SECURE') b.append(el('span', {class: 'badge'}, 'patch vérifié'));
  b.addEventListener('click', () => openPanel(f));
  return b;
}
function dl(f, rows) {
  const d = el('dl');
  for (const [label, k] of rows) d.append(el('dt', {}, label), el('dd', {}, val(f, k)));
  return d;
}
function pre(f, k, label) {
  return el('div', {}, el('dt', {}, label), f[k] ? el('pre', {}, String(f[k])) : el('dd', {}, NA));
}
function diff(f) {
  if (!f.patch_diff) return el('div', {}, el('dt', {}, 'Diff'), el('dd', {}, NA));
  const p = el('pre');
  for (const line of String(f.patch_diff).split('\n')) {
    const c = line.startsWith('+') && !line.startsWith('+++') ? 'add' : line.startsWith('-') && !line.startsWith('---') ? 'del' : '';
    p.append(el('div', c ? {class: c} : {}, line || ' '));
  }
  return el('div', {}, el('dt', {}, 'Diff'), p);
}
const TABS = [
  ['Résumé', f => dl(f, [['Résumé', '_summary'], ['Impact', 'impact'], ["Position de l'attaquant", 'attacker_position'], ['Privilèges requis', 'privileges_required'], ['Interaction utilisateur', 'user_interaction']])],
  ['Problème', f => dl(f, [['Description', 'description'], ['Emplacement', 'code_paths'], ['CWE', 'cwe'], ['Analyse du review', 'reasoning'], ['Analyse du critic', 'critic_reasoning']])],
  ['Cas testé', f => { const d = dl(f, [['Statut', 'repro_status'], ['Script', 'repro_file_path']]); d.append(pre(f, 'run_command', 'Commande'), pre(f, 'repro_output', 'Sortie')); return d; }],
  ['Correction', f => {
    const d = dl(f, [['Statut', 'patch_status'], ['Re-attaque', 'reattack_status'], ['Mitigation', 'mitigation']]);
    d.append(diff(f));
    if (f.patch_diff && f._bucket !== 'REJECTED') d.append(el('p', {}, 'Appliquer : ', el('code', {}, 'git apply osho-mantis/' + m.audit_name + '/patches/' + f._file + '.diff')));
    return d;
  }],
];
const panel = document.getElementById('panel'), tabs = document.getElementById('tabs'), content = document.getElementById('content');
let current = null;
function show(i) {
  [...tabs.children].forEach((b, j) => b.setAttribute('aria-selected', String(i === j)));
  content.replaceChildren(TABS[i][1](current));
}
function openPanel(f) {
  current = f;
  document.getElementById('ptitle').textContent = '[' + f._bucket + '] ' + f.title;
  tabs.replaceChildren(...TABS.map(([label], i) => { const b = el('button', {role: 'tab'}, label); b.addEventListener('click', () => show(i)); return b; }));
  show(0);
  panel.classList.add('open');
  panel.setAttribute('aria-hidden', 'false');
}
function closePanel() { panel.classList.remove('open'); panel.setAttribute('aria-hidden', 'true'); }
document.getElementById('close').addEventListener('click', closePanel);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePanel(); });

document.title = 'Audit — ' + (m.repo_name || 'repo');
document.getElementById('title').textContent = 'Audit de sécurité — ' + (m.repo_name || 'repo');
document.getElementById('meta').textContent = [m.started_at, 'niveau ' + (m.level || '?'), 'Mantis ' + (m.mantis_commit || '?'), m.duration].filter(Boolean).join(' · ');
if (m.stages.length) document.getElementById('stages').textContent = 'Étapes exécutées : ' + m.stages.join(', ');
if (m.level_banner) document.getElementById('level-banner').textContent = m.level_banner;
const tiles = [['Findings', s.total], ['Critical', s.by_bucket.CRITICAL], ['High', s.by_bucket.HIGH], ['Medium', s.by_bucket.MEDIUM], ['Low', s.by_bucket.LOW], ['Confirmés', s.confirmed], ['Reproduits', s.reproduced, !m.reproduce_done], ['Patchs vérifiés', s.patched, !m.reproduce_done], ['Écartés', s.by_bucket.REJECTED]];
for (const [label, n, na] of tiles) {
  const t = na ? el('div', {class: 'stat'}, el('b', {}, '—'), label, el('div', {class: 'muted'}, NA))
              : el('div', {class: 'stat'}, el('b', {}, String(n)), label);
  document.getElementById('stats').append(t);
}
const crit = D.findings.filter(f => f._bucket === 'CRITICAL' || f._bucket === 'HIGH');
const critBox = document.getElementById('critical');
if (!crit.length) critBox.append(el('p', {class: 'muted'}, D.findings.length ? 'Aucun point Critical ou High.' : 'Aucun finding.'));
for (const f of crit) {
  const c = card(f);
  if (f._summary) c.append(el('div', {}, String(f._summary)));
  critBox.append(c);
}
const board = document.getElementById('board');
for (const [key, label] of COLS) {
  const items = D.findings.filter(f => f._bucket === key);
  const head = el('h3', {}, el('span', {}, label), el('span', {class: 'muted'}, String(items.length)));
  const col = key === 'REJECTED' ? el('details', {class: 'col'}, el('summary', {}, head)) : el('div', {class: 'col'}, head);
  for (const f of items) col.append(card(f));
  board.append(col);
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    render(sys.argv[1])
    print(f"README.md, dashboard.html écrits dans {Path(sys.argv[1]).resolve()}")
