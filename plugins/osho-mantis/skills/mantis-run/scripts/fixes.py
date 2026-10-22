#!/usr/bin/env python3
"""Corrections en un clic : fixes.json, branche de l'audit, branches et worktrees des correctifs
  python3 fixes.py start|finish|fail|launchable|reconcile|busy|active <AUDIT> [stem] [raison]
"""
import contextlib
import fcntl
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import commands
import render

FIX_LIMIT = 3
BAD_AUDIT_NAME = "nom du dossier d'audit non pris en charge pour une branche git"
USAGE = __doc__.strip()


def git(cwd, *args, check=True):
    r = subprocess.run(["git", "-C", str(cwd), "-c", "core.hooksPath=/dev/null",
                        "-c", "core.attributesFile=/dev/null", *args],
                       text=True, capture_output=True, env=dict(os.environ, GIT_CONFIG_NOSYSTEM="1"))
    if check and r.returncode:
        raise RuntimeError((r.stderr.strip().splitlines() or [f"git {args[0]} a échoué"])[0])
    return r


@contextlib.contextmanager
def locked(audit_dir):
    fd = os.open(Path(audit_dir) / "fixes.lock", os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def load(audit_dir):
    data = render.load_json(Path(audit_dir) / "fixes.json", {})
    return data if isinstance(data, dict) else {}


def _save(audit_dir, data):
    commands.atomic_write(Path(audit_dir) / "fixes.json", json.dumps(data, ensure_ascii=False, indent=2))


def _set(data, stem, **fields):
    e = data.get(stem) if isinstance(data.get(stem), dict) else {}
    e.update(fields, at=datetime.now().isoformat(timespec="seconds"))
    data[stem] = e
    return e


def update(audit_dir, stem, **fields):
    with locked(audit_dir):
        data = load(audit_dir)
        e = _set(data, stem, **fields)
        _save(audit_dir, data)
        return e


def repo_of(audit_dir):
    repo = render.load_json(Path(audit_dir) / "campaign.json", {})
    repo = repo.get("repo") if isinstance(repo, dict) else None
    top = git(audit_dir, "rev-parse", "--show-toplevel", check=False)
    if not isinstance(repo, str) or not repo or top.returncode \
            or Path(repo).resolve() != Path(top.stdout.strip()).resolve():
        raise ValueError("repo de l'audit introuvable")
    return Path(repo).resolve()


def audit_branch(audit_dir):
    return "mantis/" + Path(audit_dir).name


def audit_branch_ok(audit_dir):
    """Le nom du dossier d'audit donne une branche git valide (snapshot s'en sert pour masquer git merge)"""
    name = Path(audit_dir).name
    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", name)) and not name.startswith(".") \
        and ".." not in name and not name.endswith(".lock")


def short(stem):
    return re.sub(r"[^A-Za-z0-9_-]", "_", stem)[:8]


def fix_branch(audit_dir, stem):
    name = f"mantis/fix/{Path(audit_dir).name}/{short(stem)}"
    if any(s != stem and isinstance(e, dict) and e.get("branch") == name for s, e in load(audit_dir).items()):
        name = f"mantis/fix/{Path(audit_dir).name}/{re.sub(r'[^A-Za-z0-9_-]', '_', stem)}"
    return name


def _finding_path(audit_dir, stem):
    return Path(audit_dir) / "workspace" / "findings" / f"{stem}.json"


def _finding(audit_dir, stem):
    f = render.load_json(_finding_path(audit_dir, stem), {})
    return f if isinstance(f, dict) else {}


def _title(f, stem):
    """Titre sur une ligne, sans caractère de contrôle, pour les messages de commit"""
    return re.sub(r"[\x00-\x1f\x7f]", "", " ".join(str(f.get("title") or stem).split()))[:200]


def valid_stem(audit_dir, stem):
    return (not commands._bad(stem) and stem != "" and stem.isprintable()
            and _finding_path(audit_dir, stem).is_file())


def safe_tmp(path):
    """Seul un dossier tmp.* créé par mkdtemp, juste sous $TMPDIR, peut être supprimé"""
    if not str(path) or ".." in Path(path).parts:
        return False
    p = Path(path)
    return (not p.is_symlink() and p.is_dir() and p.parent == Path(tempfile.gettempdir())
            and p.name.startswith("tmp."))


def ensure_audit_branch(audit_dir):
    if not audit_branch_ok(audit_dir):
        raise ValueError(BAD_AUDIT_NAME)
    repo, ref = repo_of(audit_dir), "refs/heads/" + audit_branch(audit_dir)
    r = git(repo, "rev-parse", "--verify", "-q", ref + "^{commit}", check=False)
    if r.returncode == 0:
        return r.stdout.strip()
    if _with(audit_dir, "merged"):  # la recréer depuis base_commit perdrait ces fusions sans bruit
        raise ValueError("branche de l'audit supprimée alors que des correctifs y étaient fusionnés")
    state = render.load_json(Path(audit_dir) / "state.json", {})
    base = state.get("base_commit") if isinstance(state, dict) else None
    if not (isinstance(base, str) and re.fullmatch(r"[0-9a-f]{40}", base)
            and git(repo, "cat-file", "-e", base + "^{commit}", check=False).returncode == 0):
        base = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "update-ref", ref, base, "")  # ancienne valeur vide : création seulement
    return base


def _attr_lines(repo, rev):
    """Lignes non commentées de tous les .gitattributes de la révision"""
    names = git(repo, "ls-tree", "-r", "-z", "--name-only", rev).stdout.split("\0")
    for n in names:
        if n.rsplit("/", 1)[-1] == ".gitattributes":
            text = git(repo, "cat-file", "-p", f"{rev}:{n}", check=False).stdout
            yield from (ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def has_filter(repo, rev):
    return any("filter=" in ln for ln in _attr_lines(repo, rev))


def has_merge_driver(repo, rev):
    """merge=<pilote> hors des pilotes intégrés : git lancerait la commande de merge.<pilote>.driver"""
    return any(m not in ("text", "binary", "union")
               for ln in _attr_lines(repo, rev) for m in re.findall(r"(?:^|\s)merge=(\S+)", ln))


def _worktrees(repo):
    """{chemin réel: ref extraite ou None} des worktrees enregistrés"""
    out, path = {}, None
    for line in git(repo, "worktree", "list", "--porcelain", check=False).stdout.splitlines():
        if line.startswith("worktree "):
            path = os.path.realpath(line[9:])
            out[path] = None
        elif line.startswith("branch ") and path:
            out[path] = line[7:]
    return out


def _cleanup(audit_dir, data, stem, keep_branch=False):
    e = data.get(stem)
    if not isinstance(e, dict):
        return
    repo, wt = repo_of(audit_dir), e.get("worktree")
    if isinstance(wt, str) and wt:
        gone = not os.path.lexists(wt)
        # dossier disparu : remove --force n'efface que notre enregistrement (jamais de prune global)
        if gone or safe_tmp(Path(wt).parent):
            git(repo, "worktree", "remove", "--force", os.path.realpath(wt), check=False)  # git enregistre le chemin réel
        if not gone and safe_tmp(Path(wt).parent):
            with contextlib.suppress(OSError):
                os.rmdir(Path(wt).parent)
        if os.path.lexists(wt) or os.path.realpath(wt) in _worktrees(repo):
            e["cleanup_error"] = "worktree non supprimé (hors du dossier temporaire ou refus de git)"
        else:
            e["worktree"] = None
            e.pop("cleanup_error", None)
    br = e.get("branch")
    if not keep_branch and isinstance(br, str) and br.startswith(f"mantis/fix/{Path(audit_dir).name}/"):
        git(repo, "branch", "-D", br, check=False)


def cleanup(audit_dir, stem):
    with locked(audit_dir):
        data = load(audit_dir)
        _cleanup(audit_dir, data, stem)
        _save(audit_dir, data)


def queue(audit_dir, stem, cmd_id=None):
    return update(audit_dir, stem, status="queued", cmd=cmd_id, error=None)


def _with(audit_dir, *statuses):
    return [s for s, e in load(audit_dir).items() if isinstance(e, dict) and e.get("status") in statuses]


def launchable(audit_dir):
    entries = [(s, e) for s, e in load(audit_dir).items() if isinstance(e, dict)]
    queued = sorted((e for e in entries if e[1].get("status") == "queued"), key=lambda x: str(x[1].get("at") or ""))
    running = sum(e.get("status") == "running" for _, e in entries)
    return [s for s, _ in queued][:max(0, FIX_LIMIT - running)]


def busy(audit_dir):
    return _with(audit_dir, "running", "ready", "merged")


def active(audit_dir):
    return _with(audit_dir, "queued", "running")


def _keep_old_branch(audit_dir, repo, data, stem):
    """Branche gardée après un merge raté : renommée en <branche>-ancien-<n> pour que son commit reste joignable"""
    e = data.get(stem) if isinstance(data.get(stem), dict) else {}
    br, sha = e.get("branch"), e.get("commit")
    if not (isinstance(br, str) and isinstance(sha, str) and sha  # commit seulement après ready ; queued à ce stade
            and br.startswith(f"mantis/fix/{Path(audit_dir).name}/")):  # fixes.json n'est pas sûr : jamais une autre branche
        return
    old = "refs/heads/" + br
    if git(repo, "rev-parse", "--verify", "-q", old, check=False).stdout.strip() != sha \
            or old in _worktrees(repo).values():  # déplacée ou extraite par l'utilisateur : on n'y touche pas
        return
    n = 1
    while git(repo, "rev-parse", "--verify", "-q", f"{old}-ancien-{n}", check=False).returncode == 0:
        n += 1
    git(repo, "update-ref", f"{old}-ancien-{n}", sha, "")
    _set(data, stem, kept_branch=f"{br}-ancien-{n}")
    try:
        git(repo, "update-ref", "-d", old, sha)
    except RuntimeError as err:
        raise ValueError(f"branche {br} non renommée : {err}") from None


def start(audit_dir, stem):
    audit_dir = Path(audit_dir)
    with locked(audit_dir):
        data = load(audit_dir)
        prev = data.get(stem) if isinstance(data.get(stem), dict) else {}
        if not valid_stem(audit_dir, stem) or prev.get("status") in ("running", "ready", "merged"):
            raise ValueError("finding invalide ou correction déjà en cours")
        repo = repo_of(audit_dir)
        diff = audit_dir / "fixes" / f"{stem}.prev.diff"
        prev_diff = str(diff) if diff.is_file() else None  # la commande fix a déjà remis l'entrée en queued
        try:
            head = ensure_audit_branch(audit_dir)
            _keep_old_branch(audit_dir, repo, data, stem)
        except ValueError as err:
            e = _set(data, stem, status="failed", error=str(err))
            _save(audit_dir, data)
            return dict(e)
        _cleanup(audit_dir, data, stem)
        if has_filter(repo, head):
            e = _set(data, stem, status="failed",
                     error="le repo déclare un filtre git (.gitattributes) : correction refusée")
            _save(audit_dir, data)
            return dict(e)
        f = _finding(audit_dir, stem)
        title = _title(f, stem)
        (audit_dir / "fixes").mkdir(exist_ok=True)
        msg = audit_dir / "fixes" / f"{stem}.msg"
        commands.atomic_write(msg, f"fix(mantis): {title} [{stem}]\n")
        branch = fix_branch(audit_dir, stem)
        if git(repo, "rev-parse", "--verify", "-q", "refs/heads/" + branch, check=False).returncode == 0:
            holder = next((p for p, ref in _worktrees(repo).items() if ref == "refs/heads/" + branch), None)
            if holder:
                e = _set(data, stem, status="failed",
                         error=f"la branche {branch} est encore extraite dans le worktree {holder}")
                _save(audit_dir, data)
                return dict(e)
            git(repo, "branch", "-D", branch)  # reste d'un nettoyage raté : la branche est à nous (préfixe mantis/fix/<audit>/)
        tmp = tempfile.mkdtemp(prefix="tmp.")
        wt = str(Path(tmp) / "wt")
        try:
            git(repo, "worktree", "add", "-q", "-b", branch, wt, head)
        except RuntimeError as err:
            os.rmdir(tmp)
            e = _set(data, stem, status="failed", error=str(err))
            _save(audit_dir, data)
            return dict(e)
        e = _set(data, stem, status="running", branch=branch, worktree=wt, base=head, commit=None,
                 error=None, agent="Correctif " + branch.rsplit("/", 1)[-1])  # suffixe de la branche : unique même si short() collisionne
        _save(audit_dir, data)
    state = render.load_json(audit_dir / "state.json", {})
    return dict(e, prev_diff=prev_diff, msg_file=str(msg), title=title, bucket=render.bucket(f),
                dirty=bool(state.get("git_status_before")) if isinstance(state, dict) else False,
                repo=str(repo), audit=str(audit_dir))


def finish(audit_dir, stem, interrupted=False):
    with locked(audit_dir):
        data = load(audit_dir)
        e = data.get(stem)
        if not isinstance(e, dict) or e.get("status") != "running":
            return e
        repo, wt, br = repo_of(audit_dir), e.get("worktree"), e.get("branch")
        alive = isinstance(wt, str) and wt and Path(wt).is_dir()
        ahead, clean = 0, False
        if alive:
            r = git(repo, "rev-list", "--count", f"{e.get('base')}..{br}", check=False)
            ahead = int(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip().isdigit() else 0
            r = git(wt, "status", "--porcelain", check=False)
            clean = r.returncode == 0 and not r.stdout.strip()
        if ahead >= 1 and clean:
            e = _set(data, stem, status="ready", commit=git(repo, "rev-parse", br).stdout.strip())
        else:
            reason = ("correction interrompue" if interrupted else "aucun commit sur la branche du correctif"
                      if ahead == 0 else "fichiers non commités dans le worktree")
            e = _set(data, stem, status="failed", error=reason)
            _cleanup(audit_dir, data, stem)
        _save(audit_dir, data)
        return e


def fail(audit_dir, stem, reason):
    with locked(audit_dir):
        data = load(audit_dir)
        e = _set(data, stem, status="failed", error=reason)
        _cleanup(audit_dir, data, stem)
        _save(audit_dir, data)
        return e


def reconcile(audit_dir):
    return [finish(audit_dir, s, interrupted=True) for s in _with(audit_dir, "running")]


def merge_ref(repo, ref, old, fix, message):
    """Merge en mémoire de fix dans ref (attendue à old) ; aucun worktree ni index touché"""
    r = git(repo, "merge-tree", "--write-tree", old, fix, check=False)
    if r.returncode == 1:
        return ("conflict", None)
    if r.returncode:
        raise RuntimeError((r.stderr.strip().splitlines() or ["git merge-tree a échoué"])[0])
    tree = r.stdout.split("\n", 1)[0].strip()
    new = git(repo, "commit-tree", tree, "-p", old, "-p", fix, "-m", message).stdout.strip()
    if git(repo, "update-ref", ref, new, old, check=False).returncode:  # ref déplacée entre-temps
        return ("busy", None)
    return ("merged", new)


def merge(audit_dir, stem):
    audit_dir = Path(audit_dir)
    with locked(audit_dir):
        data = load(audit_dir)
        e = data.get(stem)
        if not isinstance(e, dict) or e.get("status") != "ready":
            return ("refused", "le correctif n'est pas prêt")
        try:
            base, fix = e["base"], e["commit"]
        except KeyError:
            raise RuntimeError("entrée de correction incomplète") from None
        repo, ref = repo_of(audit_dir), "refs/heads/" + audit_branch(audit_dir)
        holder = next((p for p, b in _worktrees(repo).items() if b == ref), None)
        if holder:  # update-ref changerait le HEAD et les fichiers de ce worktree
            return ("busy", f"branche de l'audit extraite dans {holder} : change de branche puis réessaie")
        r = git(repo, "rev-parse", "--verify", "-q", ref + "^{commit}", check=False)
        old = r.stdout.strip()
        why = (BAD_AUDIT_NAME if not audit_branch_ok(audit_dir)
               else "branche de l'audit introuvable" if r.returncode
               else "pilote de merge non autorisé dans .gitattributes"
               if has_merge_driver(repo, old) or has_merge_driver(repo, fix) else None)
        if why:  # la branche du correctif est gardée : l'utilisateur peut récupérer le correctif
            _set(data, stem, status="failed", error=why)
            _cleanup(audit_dir, data, stem, keep_branch=True)
            _save(audit_dir, data)
            return ("failed", why)
        msg = f"Merge correctif Mantis : {_title(_finding(audit_dir, stem), stem)} [{stem}]"
        res, new = merge_ref(repo, ref, old, fix, msg)
        if res == "busy":
            return ("busy", "branche de l'audit modifiée pendant la fusion, réessaie")
        if res == "conflict":
            why = "conflit avec un autre correctif"
            diff = git(repo, "diff", "--no-color", "--no-ext-diff", "--no-textconv", base, fix).stdout
            (audit_dir / "fixes").mkdir(exist_ok=True)
            commands.atomic_write(audit_dir / "fixes" / f"{stem}.prev.diff", diff)
            _set(data, stem, status="conflict", error=why)
        else:
            _set(data, stem, status="merged", merge_commit=new, error=None)
        _save(audit_dir, data)  # avant le nettoyage : un merge fait ne doit jamais rester ready
        _cleanup(audit_dir, data, stem)
        _save(audit_dir, data)
        return (res, why)


def main(argv):
    cmds = ("start", "finish", "fail", "launchable", "reconcile", "busy", "active")
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(USAGE)
        return 0
    need = {"start": 4, "finish": 4, "fail": 5}.get(argv[1], 3)
    if argv[1] not in cmds or len(argv) < need:
        print(USAGE)
        return 2
    cmd, audit, rest = argv[1], Path(argv[2]), argv[3:]
    try:
        if cmd in ("launchable", "busy", "active"):
            for s in globals()[cmd](audit):
                print(s)
        elif cmd == "reconcile":
            for e in reconcile(audit):
                print(json.dumps(e, ensure_ascii=False))
        elif cmd == "fail":
            print(json.dumps(fail(audit, rest[0], rest[1]), ensure_ascii=False))
        else:
            print(json.dumps(globals()[cmd](audit, rest[0]), ensure_ascii=False))
    except (ValueError, RuntimeError, OSError) as err:  # OSError : dossier absent, fixes.lock planté en lien
        print(err)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
