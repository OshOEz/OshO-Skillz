#!/usr/bin/env python3
"""Exports d'un audit pour l'équipe de développement (contenu brut, jamais modifié)
  python3 export.py light|full <AUDIT> <sortie.zip>
light : bilan.html + dashboard.html + LISEZMOI-DEV.md ; full : tout le dossier d'audit, sans les fichiers de session.
"""
import json
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path

import render
import snapshot

EXCLUDE_NAMES = {"server.json", "server.log", "waiting.json", "commands.jsonl", "commands-done.jsonl"}
EXCLUDE_DIRS = {("workspace", "backups")}
COPIES = {"README.md", "dashboard.html", "bilan.html"}  # recopient les findings : pas listés comme sources
MAX_SCAN = 5 * 1024 * 1024
WARNING = ("⚠️ Cette archive contient le détail d'exploits et des secrets en clair. "
           "Transmettez-la uniquement par un canal privé.")
SECRET_PATTERNS = [
    ("clé Google", re.compile(rb"AIza[0-9A-Za-z_\-]{35}")),
    ("clé AWS", re.compile(rb"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("clé privée", re.compile(rb"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    ("jeton GitHub", re.compile(rb"\b(?:ghp|gho|ghs|ghu)_[A-Za-z0-9]{36}\b|github_pat_[A-Za-z0-9_]{50,}")),
    ("jeton Slack", re.compile(rb"\bxox[bpas]-[A-Za-z0-9-]{10,}")),
    ("clé API sk-", re.compile(rb"\bsk-(?:ant-|live_|proj-)?[A-Za-z0-9_\-]{20,}")),
    ("URL avec identifiants", re.compile(rb"\b[a-z][a-z0-9+.-]*://[^/\s:@'\"<>]+:[^/\s@'\"<>]{3,}@")),
]
SEV_ORDER = {b: i for i, b in enumerate(render.BUCKETS)}


def _state(audit_dir):
    s = render.load_json(Path(audit_dir) / "state.json", {})
    return s if isinstance(s, dict) else {}


def notes_for(stem, notes, fid=None):
    """Notes de state.json qui citent ce finding (stem, id, ou leurs 8 premiers caractères)"""
    keys = {k for k in (stem, fid, (stem or "")[:8], (fid or "")[:8]) if k and len(k) >= 4}
    return [str(n) for n in notes if any(k in str(n) for k in keys)]


def _walk(audit_dir):
    """(fichiers inclus, exclus, liens ignorés), en chemins relatifs ; ne suit jamais un lien"""
    root = Path(audit_dir).resolve()
    keep, excluded, links = [], [], []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        rel_dir = Path(dirpath).relative_to(root)
        for dn in list(dirnames):
            p = Path(dirpath) / dn
            if p.is_symlink():
                links.append(str(rel_dir / dn))
                dirnames.remove(dn)
            elif (rel_dir / dn).parts in EXCLUDE_DIRS:
                excluded.append(str(rel_dir / dn) + "/")
                dirnames.remove(dn)
        for fn in filenames:
            p, rel = Path(dirpath) / fn, rel_dir / fn
            if p.is_symlink():
                links.append(str(rel))
            elif (rel_dir == Path(".") and fn in EXCLUDE_NAMES) or fn.endswith(".tmp"):
                excluded.append(str(rel))
            elif p.resolve().is_relative_to(root) and p.is_file():
                keep.append(rel)
    return sorted(keep), sorted(excluded), sorted(links)


def files_full(audit_dir):
    return _walk(audit_dir)[0]


def _finding_of(rel, by_file):
    parts = Path(rel).parts
    if len(parts) == 3 and parts[:2] == ("workspace", "findings") and rel.endswith(".json"):
        return Path(rel).stem
    if len(parts) == 2 and parts[0] == "patches" and rel.endswith(".diff"):
        return by_file.get(Path(rel).stem, Path(rel).stem)
    return None


def _findings(audit_dir):
    findings, _ = render.load_findings(Path(audit_dir) / "workspace")
    snapshot.assign_files(findings)
    return findings


def scan_secrets(audit_dir):
    root = Path(audit_dir).resolve()
    by_file = {f["_file"]: f["_src"] for f in _findings(root)}
    found = []
    for rel in files_full(root):
        if str(rel) in COPIES:
            continue
        p = root / rel
        try:
            if p.stat().st_size > MAX_SCAN:
                continue
            data = p.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue
        for kind, rx in SECRET_PATTERNS:
            if rx.search(data):
                found.append({"file": str(rel), "kind": kind, "finding": _finding_of(str(rel), by_file)})
    return found


def patch_files(diff):
    """{fichier: [(début, fin)]} des plages de l'ancien fichier touchées par un diff unifié"""
    out, cur = {}, None
    for line in str(diff).splitlines():
        if line.startswith("+++ "):
            path = line[4:].split("\t")[0].strip()
            cur = path[2:] if path.startswith("b/") else path
            out.setdefault(cur, [])
        elif line.startswith("@@") and cur is not None:
            m = re.match(r"@@ -(\d+)(?:,(\d+))?", line)
            if m:
                a, n = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
                out[cur].append((a, a + max(n, 1) - 1))
    return out


def conflicts(audit_dir):
    audit_dir = Path(audit_dir)
    pats = {}
    for p in sorted((audit_dir / "patches").glob("*.diff")):
        if not p.is_symlink():
            try:
                pats[p.stem] = patch_files(p.read_text(errors="replace"))
            except OSError:
                pass
    out, names = [], sorted(pats)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for path in sorted(set(pats[a]) & set(pats[b])):
                overlap = any(x1 <= y2 and x2 >= y1 for x1, x2 in pats[a][path] for y1, y2 in pats[b][path])
                out.append({"a": a, "b": b, "file": path, "kind": "chevauchement" if overlap else "même fichier"})
    for n in _state(audit_dir).get("notes") or []:
        if "onflit" in str(n):
            out.append({"kind": "note", "note": str(n)})
    return out


def _md(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def dev_data(audit_dir, secrets, confl):
    """Données de la section « Pour l'équipe de développement », partagées par LISEZMOI-DEV.md et le bilan"""
    audit_dir = Path(audit_dir)
    state, camp = _state(audit_dir), render.load_json(audit_dir / "campaign.json", {})
    camp = camp if isinstance(camp, dict) else {}
    notes = state.get("notes") if isinstance(state.get("notes"), list) else []
    findings = {f["_src"]: f for f in _findings(audit_dir)}
    by_file = {f["_file"]: f for f in findings.values()}
    sec = []
    for s in secrets:
        f = findings.get(s["finding"]) if s["finding"] else None
        sec.append(dict(s, title=f["title"] if f else None, file_id=f["_file"] if f else None))
    rows = []
    for p in sorted((audit_dir / "patches").glob("*.diff")):
        f = by_file.get(p.stem)
        if not f:
            continue
        b = render.bucket(f)
        pre = [str(x) for x in (f.get("deploy_prerequisites") or [])] + notes_for(f["_src"], notes, f.get("id"))
        rows.append({"patch": p.stem, "title": f["title"], "bucket": b, "status": f.get("patch_status"),
                     "status_label": render.label("patch_status", f.get("patch_status")) or "", "prereq": pre,
                     "_k": (SEV_ORDER.get(b, 9), f.get("patch_status") != "VERIFIED_SECURE", p.stem)})
    rows.sort(key=lambda r: r.pop("_k"))
    return {"repo": Path(camp.get("repo") or "dépôt").name, "base": state.get("base_commit") or "<commit audité>",
            "secrets": sec, "patches": rows, "pairs": [c for c in confl if c["kind"] != "note"],
            "conflict_notes": [c["note"] for c in confl if c["kind"] == "note"]}


def dev_readme(audit_dir, secrets, confl):
    d = dev_data(audit_dir, secrets, confl)
    base = d["base"]
    L = [f"# Audit de sécurité Mantis : {d['repo']}, mode d'emploi pour les développeurs",
         "", WARNING, "", "## Secrets à révoquer", ""]
    if d["secrets"]:
        L.append(SECRETS_INTRO)
        L.append("")
        for s in d["secrets"]:
            who = (f"{_md(s['title'])} (`{s['finding']}`)" if s["title"]
                   else f"`{s['finding']}`" if s["finding"] else "hors constat")
            L.append(f"- {s['kind']} : {who}, fichier `{s['file']}`")
    else:
        L.append(NO_SECRET)
    L += ["", "## Lire l'audit", "", *[f"{i}. {x}" for i, x in enumerate(READ_STEPS, 1)],
          "", "## Appliquer un patch", "",
          f"Les patchs sont écrits contre le commit `{base}`. Partez d'une branche à ce commit, puis pour chaque patch :",
          "", "```bash", *apply_commands(base), "```", "", APPLY_ORDER, "",
          "| Patch | Constat | Gravité | Statut | Prérequis et réserves |", "|---|---|---|---|---|"]
    for r in d["patches"]:
        L.append(f"| `patches/{r['patch']}.diff` | {_md(r['title'])} | {r['bucket']} | {_md(r['status_label'])} | "
                 f"{_md(' ; '.join(r['prereq']))} |")
    L += ["", "## Patchs en conflit", ""]
    if d["pairs"]:
        L += [CONFLICT_INTRO, ""]
        L += [f"- `{c['a']}` et `{c['b']}` : {c['kind']} dans `{c['file']}`" for c in d["pairs"]]
    else:
        L.append(NO_CONFLICT)
    L += [f"- note de l'audit : {_md(n)}" for n in d["conflict_notes"]]
    L += ["", "## Rejouer une reproduction", "", REPLAY, ""]
    return "\n".join(L)


SECRETS_INTRO = ("Ces fichiers contiennent une valeur de secret (repérage par motifs, non exhaustif). "
                 "Révoquez et remplacez ces secrets, puis purgez-les de l'historique git si besoin.")
NO_SECRET = "aucun secret repéré par motifs (vérification non exhaustive)"
READ_STEPS = ["`bilan.html` : la synthèse, à lire en premier.",
              "`dashboard.html` : chaque constat en détail (filtre, fiche, diff), hors ligne.",
              "`workspace/findings/<id>.json` : les données brutes d'un constat ; `workspace/reproducers/` : les preuves."]
APPLY_ORDER = ("Ordre conseillé : gravité décroissante, patchs vérifiés par re-attaque d'abord. "
               "Un patch « proposé, non vérifié » n'a pas été rejoué contre l'exploit.")
CONFLICT_INTRO = ("« chevauchement » : les deux patchs modifient les mêmes lignes, fusion à la main ; "
                  "« même fichier » : à appliquer l'un après l'autre.")
NO_CONFLICT = "Aucun patch ne touche le même fichier qu'un autre."
REPLAY = ("Chaque preuve de `workspace/reproducers/` se rejoue dans Docker, sans réseau, sur une copie du dépôt "
          "(`docker run --rm --network=none -v <copie>:/src:ro …`). Si l'audit a utilisé un volume de dépendances "
          "(`state.json`, clé `deps_volume`), recréez-le d'abord avec un conteneur qui a le réseau.")


def apply_commands(base):
    return [f"git switch -c correctifs-mantis {base}",
            "git apply --check patches/<id>.diff && git apply patches/<id>.diff"]


def _check_audit(audit_dir):
    p = Path(audit_dir)
    if p.is_symlink() or not p.is_dir():
        raise ValueError("dossier d'audit refusé : lien symbolique ou absent")
    return p.resolve()


def build(kind, audit_dir, out):
    if kind not in ("light", "full"):
        raise ValueError(f"export inconnu : {kind}")
    root = _check_audit(audit_dir)
    secrets, confl = scan_secrets(root), conflicts(root)
    readme = dev_readme(root, secrets, confl)
    top = root.name
    manifest = {"kind": kind, "audit": top, "generated_at": datetime.now().isoformat(timespec="seconds"),
                "warning": WARNING, "secrets": secrets, "conflicts": confl}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        if kind == "light":
            for name, page in render.pages(root).items():
                z.writestr(f"{top}/{name}", page)
            manifest["files"] = sorted(render.pages_names()) + ["LISEZMOI-DEV.md"]
        else:
            keep, excluded, links = _walk(root)
            for rel in keep:
                z.write(root / rel, f"{top}/{rel}")
            manifest.update(files=[str(r) for r in keep] + ["LISEZMOI-DEV.md", "MANIFESTE.json"],
                            excluded=excluded, symlinks_skipped=links)
            z.writestr(f"{top}/MANIFESTE.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        z.writestr(f"{top}/LISEZMOI-DEV.md", readme)
    return manifest


def main(argv):
    if len(argv) != 4:
        sys.exit(__doc__)
    try:
        m = build(argv[1], argv[2], argv[3])
    except ValueError as e:
        sys.exit(str(e))
    print(f"{argv[3]} : {len(m['files'])} fichiers, {len(m['secrets'])} secret(s) repéré(s)")


if __name__ == "__main__":
    main(sys.argv)
