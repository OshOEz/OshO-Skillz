#!/usr/bin/env python3
"""Garde-fous de mantis-run : findings sauvegardés avant chaque étape qui les écrit en parallèle, contrôlés
après chaque lot, restaurés si un agent les a abîmés ; RESUME.md pour reprendre après une coupure.
  python3 guard.py backup <AUDIT> <étape>    copie workspace/findings dans workspace/backups/<étape>-r<tour>-<horodatage>/
  python3 guard.py check <AUDIT>             une ligne JSON par finding abîmé ; code 1 s'il y en a
  python3 guard.py restore <AUDIT> [fichier…] restaure depuis la dernière sauvegarde (défaut : ceux de check)
  python3 guard.py resume <AUDIT>            écrit RESUME.md depuis state.json
Garde du shadow (copie de travail du dépôt, un `mktemp -d` hors du dépôt et de l'audit) :
  python3 guard.py shadow-new <AUDIT> [--list]   crée un shadow, l'écrit dans state.json (`shadow`, ou ajouté à `shadows`)
  python3 guard.py shadow-reset <AUDIT> [chemin] vide et recopie les fichiers suivis (défaut : `shadow`) ; chemin refusé
                                                 par la garde : laissé intact, remplacé par un shadow neuf, note ajoutée
  python3 guard.py shadow-drop <AUDIT> [chemin]  supprime le shadow et le retire de state.json ; code 2 si refusé
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

KEEP = 3
ST_FR = {"done": "fait", "running": "en cours", "failed": "en échec", "pending": "à faire", "skipped": "sauté"}


def _load(path, default):
    try:
        d = json.loads(Path(path).read_text())
        return d if isinstance(d, type(default)) else default
    except (OSError, ValueError):
        return default


def _dirs(audit):
    a = Path(audit)
    return a / "workspace" / "findings", a / "workspace" / "backups"


def _backups(audit):
    bdir = _dirs(audit)[1]
    if not bdir.is_dir() or bdir.is_symlink():
        return []
    return sorted((p for p in bdir.iterdir() if p.is_dir() and not p.is_symlink()), key=lambda p: p.name.rsplit("-", 2)[-2:])


def backup(audit, stage, stamp=None):
    fdir, bdir = _dirs(audit)
    if bdir.is_symlink():
        raise ValueError("workspace/backups est un lien symbolique : refusé")
    rnd = _load(Path(audit) / "state.json", {}).get("round") or 1
    dest = bdir / f"{stage}-r{rnd}-{stamp or datetime.now().strftime('%Y%m%d-%H%M%S')}"
    dest.mkdir(parents=True, exist_ok=True)
    for p in sorted(fdir.glob("*.json")):
        if p.is_file() and not p.is_symlink():
            shutil.copy2(p, dest / p.name)
    for old in _backups(audit)[:-KEEP]:
        shutil.rmtree(old)
    return dest


def check(audit):
    fdir = _dirs(audit)[0]
    last = _backups(audit)[-1] if _backups(audit) else None
    probs, seen = [], set()
    for p in sorted(fdir.glob("*.json")):
        seen.add(p.name)
        if p.is_symlink():
            probs.append({"file": p.name, "problem": "lien symbolique"})
            continue
        raw = p.read_bytes() if p.is_file() else b""
        if not raw.strip():
            probs.append({"file": p.name, "problem": "vide"})
            continue
        try:
            f = json.loads(raw)
        except ValueError:
            probs.append({"file": p.name, "problem": "JSON illisible"})
            continue
        if not isinstance(f, dict) or not f.get("title"):
            probs.append({"file": p.name, "problem": "sans titre"})
            continue
        old = _load(last / p.name, {}) if last else {}
        lost = sorted(k for k in old if k not in f)
        if lost:
            probs.append({"file": p.name, "problem": "champs perdus : " + ", ".join(lost)})
    if last:
        for p in sorted(last.glob("*.json")):
            if p.name not in seen:
                probs.append({"file": p.name, "problem": "fichier disparu"})
    return probs


def restore(audit, files):
    fdir = _dirs(audit)[0]
    done = []
    for name in files:
        if "/" in name or "\\" in name or ".." in name:
            continue
        src = next((b / name for b in reversed(_backups(audit)) if (b / name).is_file()), None)
        if src is None:
            continue
        dst = fdir / name
        tmp = fdir / f".{name}.restore"
        shutil.copy2(src, tmp)
        if dst.is_symlink():
            dst.unlink()
        os.replace(tmp, dst)
        done.append(name)
    return done


def resume(audit):
    audit = Path(audit)
    st, camp = _load(audit / "state.json", {}), _load(audit / "campaign.json", {})
    stages = st.get("stages") if isinstance(st.get("stages"), dict) else {}
    notes = [str(n) for n in st.get("notes") or []]
    repo = Path(camp.get("repo") or audit.parent.parent).name
    if st.get("finished"):
        status = "Audit terminé : ce fichier ne sert plus qu'à l'historique."
    elif st.get("stopped"):
        status = "Audit arrêté par l'utilisateur."
    else:
        status = "Audit en cours ou interrompu (quota, coupure)."
    L = [f"# Reprise de l'audit Mantis : {repo}", "", f"**{status}** Écrit par mantis-run, ne pas modifier à la main.", "",
         "## Relancer", "", "```", f'/mantis-run "{audit}"', "```", "",
         "`state.json` fait foi. Une étape « en cours » à la reprise a été interrompue : elle est relancée, "
         "seuls les findings sans le champ attendu (ou listés dans `force_repro`) sont repris.", "",
         "## État", "", f"- Niveau : {camp.get('level') or 'à choisir'}", f"- Tour : {st.get('round') or 1}"]
    cur = st.get("current")
    if isinstance(cur, dict) and cur.get("stage"):
        L.append(f"- Lot en cours au moment de la coupure : {cur.get('stage')} {cur.get('batch') or ''}".rstrip())
    if st.get("force_repro"):
        L.append("- À reproduire de force (`force_repro`) : " + ", ".join(map(str, st["force_repro"])))
    if st.get("deps_volume"):
        L.append(f"- Volume de dépendances : `{st['deps_volume']}` (monté en lecture seule, `--network=none`)")
    L += ["", "| Étape | État |", "|---|---|"] + [f"| {k} | {ST_FR.get(v, v)} |" for k, v in stages.items()]
    L += ["", "## Avant de relancer", "",
          f"1. Conteneurs orphelins de cet audit seulement : `docker ps -a --filter name=mantis-{audit.name} --format '{{{{.Names}}}}'`, "
          "à supprimer ; ne jamais toucher aux conteneurs d'autres projets.",
          f"2. Fichiers temporaires laissés par un agent : `find \"{audit}\" -name '*.tmp'`.",
          f"3. Intégrité des findings : `python3 guard.py check \"{audit}\"`, puis `restore` si besoin.", "",
          "## Règles", "", "- Rien ne s'exécute sur l'hôte : uniquement `docker run --rm`, sans réseau sauf le remplissage "
          "du volume de dépendances.", "- Un agent écrit dans un nouveau fichier, le valide, puis le renomme ; jamais "
          "`jq … > même_fichier`.", ""]
    if notes:
        L += ["## Dernières notes", ""] + [f"- {n}" for n in notes[-8:]] + [""]
    tmp = audit / ".RESUME.md.tmp"
    tmp.write_text("\n".join(L))
    os.replace(tmp, audit / "RESUME.md")
    return audit / "RESUME.md"


def _mktemp(*args):
    return subprocess.run(["mktemp", *args], capture_output=True, text=True, check=True).stdout.strip()


def _save_state(audit, st):
    tmp = Path(audit) / ".state.json.tmp"
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2))
    os.replace(tmp, Path(audit) / "state.json")


def shadow_ok(path):
    """Seul un `mktemp -d` encore présent passe ; le parent se compare sans résoudre les liens."""
    return bool(path) and os.path.isdir(path) and not os.path.islink(path) and ".." not in path \
        and os.path.dirname(path) == os.path.dirname(_mktemp("-u")) and os.path.basename(path).startswith("tmp.")


def shadow_new(audit, as_list=False):
    path = _mktemp("-d")
    st = _load(Path(audit) / "state.json", {})
    if as_list:
        st["shadows"] = list(st.get("shadows") or []) + [path]
    else:
        st["shadow"] = path
    _save_state(audit, st)
    return Path(path)


def _copy(audit, shadow):
    repo = _load(Path(audit) / "campaign.json", {}).get("repo")
    if not repo:
        raise RuntimeError("campaign.json sans `repo`")
    ls = subprocess.run(["git", "-C", repo, "ls-files", "-z"], capture_output=True)
    if ls.returncode:
        raise RuntimeError("git ls-files a échoué : " + ls.stderr.decode(errors="replace").strip())
    rs = subprocess.run(["rsync", "-a", "--no-links", "--from0", "--files-from=-", f"{repo}/", f"{shadow}/"],
                        input=ls.stdout, capture_output=True)
    if rs.returncode:
        raise RuntimeError("rsync a échoué : " + rs.stderr.decode(errors="replace").strip())


def shadow_reset(audit, path=None):
    st = _load(Path(audit) / "state.json", {})
    path = path or st.get("shadow")
    if shadow_ok(path):
        shutil.rmtree(path)
        os.mkdir(path)
    else:
        # Le chemin refusé n'est jamais supprimé ni modifié : un shadow neuf prend sa place dans state.json.
        old, path = path, _mktemp("-d")
        shadows = list(st.get("shadows") or [])
        if old and old in shadows:
            shadows[shadows.index(old)] = path
            st["shadows"] = shadows
        else:
            st["shadow"] = path
        st["notes"] = list(st.get("notes") or []) + ["shadow recréé : ancien chemin refusé ou absent"]
        _save_state(audit, st)
    try:
        _copy(audit, path)
    except RuntimeError as e:
        raise RuntimeError(f"shadow {path} incomplet, à refaire : {e}") from None
    return Path(path)


def shadow_drop(audit, path=None):
    st = _load(Path(audit) / "state.json", {})
    path = path or st.get("shadow")
    if not shadow_ok(path):
        return False
    shutil.rmtree(path)
    if st.get("shadow") == path:
        del st["shadow"]
    if path in (st.get("shadows") or []):
        st["shadows"] = [p for p in st["shadows"] if p != path]
    _save_state(audit, st)
    return True


def main(argv):
    shadow_cmds = ("shadow-new", "shadow-reset", "shadow-drop")
    if len(argv) < 3 or argv[1] not in ("backup", "check", "restore", "resume", *shadow_cmds) \
            or (argv[1] == "backup" and len(argv) != 4) or (argv[1] in shadow_cmds and len(argv) > 4) \
            or (argv[1] == "shadow-new" and argv[3:] not in ([], ["--list"])):
        sys.exit(__doc__)
    cmd, audit = argv[1], Path(argv[2])
    if not audit.is_dir() or audit.is_symlink():
        sys.exit("dossier d'audit refusé")
    if cmd == "backup":
        print(backup(audit, argv[3]))
    elif cmd == "check":
        probs = check(audit)
        for p in probs:
            print(json.dumps(p, ensure_ascii=False))
        sys.exit(1 if probs else 0)
    elif cmd == "restore":
        files = argv[3:] or [p["file"] for p in check(audit)]
        for name in restore(audit, files):
            print(name)
    elif cmd == "shadow-new":
        print(shadow_new(audit, as_list=argv[3:] == ["--list"]))
    elif cmd == "shadow-reset":
        try:
            print(shadow_reset(audit, argv[3] if len(argv) > 3 else None))
        except RuntimeError as e:
            sys.exit(str(e))
    elif cmd == "shadow-drop":
        if not shadow_drop(audit, argv[3] if len(argv) > 3 else None):
            print("shadow refusé par la garde : rien supprimé", file=sys.stderr)
            sys.exit(2)
    else:
        print(resume(audit))


if __name__ == "__main__":
    main(sys.argv)
