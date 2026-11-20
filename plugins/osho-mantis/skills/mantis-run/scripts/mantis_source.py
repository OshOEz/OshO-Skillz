#!/usr/bin/env python3
"""Copie de Mantis figée sur le commit accepté de mantis.lock, retard sur l'amont, contrat des skills
  python3 mantis_source.py ensure|behind|diff [--lock <fichier>] [--dir <dossier>]
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

LOCK = Path(__file__).resolve().parents[3] / "mantis.lock"
DIR = Path.home() / ".local" / "share" / "mantis"
NET_TIMEOUT = 30  # un fetch bloqué ne doit pas bloquer un audit
UPSTREAM_REF = "refs/mantis/upstream"
STAGE_DIRS = ("mantis-history", "mantis-structural-index", "mantis-architecture", "mantis-threat-model",
              "mantis-plan", "mantis-researcher", "mantis-dedupe", "mantis-review", "mantis-critic",
              "mantis-reproduce", "mantis-chain", "mantis-patch", "mantis-calibrate", "mantis-reflect")
CONTRACT_FIELDS = ("reasoning", "production_viability", "repro_status", "patch_status", "reattack_status",
                   "mantis_risk_score", "FALSE_POSITIVE", "DUPLICATE", "NON_VIABLE", "SAMPLE_OR_TEST",
                   "VIABLE", "CONDITIONAL_VIABLE")
USAGE = __doc__.strip()


def git(cwd, *args, check=True, timeout=None):
    try:
        r = subprocess.run(["git", "-C", str(cwd), "-c", "core.hooksPath=/dev/null",
                            "-c", "core.attributesFile=/dev/null", *args],
                           text=True, capture_output=True, timeout=timeout,
                           env=dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0"))
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git {args[0]} : pas de réponse en {timeout} s")
    if check and r.returncode:
        raise RuntimeError((r.stderr.strip().splitlines() or [f"git {args[0]} a échoué"])[0])
    return r


def load_lock(path):
    lock = json.loads(Path(path).read_text())
    if not all(isinstance(lock.get(k), str) and lock[k] for k in ("repo", "upstream", "commit")):
        raise ValueError(f"{path} : repo, upstream et commit attendus")
    if not re.fullmatch(r"[0-9a-f]{40}", lock["commit"]):
        raise ValueError(f"{path} : commit doit être un sha complet de 40 caractères, pas {lock['commit']!r}")
    # MANTIS_SOURCE_ALLOW_LOCAL=1 n'existe que pour les tests, qui figent des dépôts locaux
    if os.environ.get("MANTIS_SOURCE_ALLOW_LOCAL") != "1":
        for k in ("repo", "upstream"):
            if not lock[k].startswith("https://"):
                raise ValueError(f"{path} : {k} doit commencer par https://")
    return lock


def set_remote(d, name, url):
    if git(d, "remote", "set-url", name, url, check=False).returncode:
        git(d, "remote", "add", name, url)


def ensure(lock, d):
    d = Path(d)
    cloned = not (d / ".git").exists()
    if cloned:
        if d.exists() and any(d.iterdir()):  # git -C remonterait jusqu'à un dépôt englobant
            raise ValueError(f"{d} n'est pas une copie de Mantis (dossier non vide sans .git)")
        d.parent.mkdir(parents=True, exist_ok=True)
        git(d.parent, "clone", "-q", "--no-checkout", "--", lock["repo"], str(d), timeout=NET_TIMEOUT)
    set_remote(d, "origin", lock["repo"])
    set_remote(d, "upstream", lock["upstream"])
    git(d, "fetch", "-q", "origin", check=False, timeout=NET_TIMEOUT)  # hors ligne : le commit peut déjà être là
    if git(d, "cat-file", "-e", lock["commit"] + "^{commit}", check=False).returncode:
        raise ValueError(f"commit {lock['commit']} introuvable dans {lock['repo']}")
    git(d, "checkout", "-q", "--detach", lock["commit"])
    # les SKILL.md sont lus comme consignes : une copie modifiée ne serait plus le commit figé
    dirty = [l[3:] for l in git(d, "status", "--porcelain", "--untracked-files=all").stdout.splitlines()]
    if dirty:
        raise ValueError(f"copie locale de Mantis modifiée ({', '.join(dirty[:5])}) : la remettre au propre ou la supprimer")
    return {"dir": str(d), "commit": lock["commit"], "cloned": cloned}


def upstream_head(lock, d):
    set_remote(d, "upstream", lock["upstream"])
    git(d, "fetch", "-q", "--no-tags", "upstream", f"+HEAD:{UPSTREAM_REF}", timeout=NET_TIMEOUT)
    return git(d, "rev-parse", UPSTREAM_REF).stdout.strip()


def count(d, a, b):
    return int(git(d, "rev-list", "--count", f"{a}..{b}").stdout)


def behind(lock_path, d):
    try:
        lock = load_lock(lock_path)
        if not (Path(d) / ".git").exists():
            return {"behind": None}
        return {"behind": count(d, lock["commit"], upstream_head(lock, d))}
    except Exception:  # jamais bloquant : sans réseau ni amont, on ne sait pas
        return {"behind": None}


def skill_dirs(d, rev):
    out = git(d, "ls-tree", "-d", "--name-only", rev, "skills/").stdout.splitlines()
    return {p.split("/", 1)[1] for p in out}


def diff(lock, d):
    if not (Path(d) / ".git").exists():
        raise ValueError(f"{d} n'est pas une copie de Mantis : lancer ensure d'abord")
    a, b = lock["commit"], upstream_head(lock, d)
    before, after = skill_dirs(d, a), skill_dirs(d, b)
    skills = {}
    for line in git(d, "diff", "--name-status", "--no-renames", a, b, "--", "skills/").stdout.splitlines():
        parts = line.split("\t")[1].split("/")
        if len(parts) < 3:
            continue
        status = "added" if parts[1] not in before else "removed" if parts[1] not in after else "changed"
        e = skills.setdefault(parts[1], {"files": 0, "status": status})
        e["files"] += 1
    manifests = [p for p in git(d, "ls-tree", "-r", "--name-only", b, "--", "skills/").stdout.splitlines()
                 if re.fullmatch(r"skills/[^/]+/SKILL\.md", p)]
    text = "\n".join(git(d, "show", f"{b}:{p}").stdout for p in manifests)
    return {"from": a, "to": b, "commits": count(d, a, b), "skills": skills,
            "contract": {"missing_dirs": [n for n in STAGE_DIRS if f"skills/{n}/SKILL.md" not in manifests],
                         "missing_fields": [f for f in CONTRACT_FIELDS if not re.search(rf"\b{f}\b", text)]}}


def main(argv):
    args, opts = [], {"--lock": LOCK, "--dir": DIR}
    it = iter(argv[1:])
    for a in it:
        if a in opts:
            opts[a] = Path(next(it, ""))
        else:
            args.append(a)
    if len(args) != 1 or args[0] not in ("ensure", "behind", "diff"):
        print(USAGE)
        return 2
    if args[0] == "behind":
        print(json.dumps(behind(opts["--lock"], opts["--dir"])))
        return 0
    try:
        lock = load_lock(opts["--lock"])
        print(json.dumps(globals()[args[0]](lock, opts["--dir"]), ensure_ascii=False))
    except (ValueError, RuntimeError, OSError) as err:
        print(err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
