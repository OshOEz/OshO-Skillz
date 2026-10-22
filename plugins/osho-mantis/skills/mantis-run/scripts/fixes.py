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


def short(stem):
    return re.sub(r"[^A-Za-z0-9_-]", "_", stem)[:8]


def fix_branch(audit_dir, stem):
    name = f"mantis/fix/{Path(audit_dir).name}/{short(stem)}"
    if any(s != stem and isinstance(e, dict) and e.get("branch") == name for s, e in load(audit_dir).items()):
        name = f"mantis/fix/{Path(audit_dir).name}/{re.sub(r'[^A-Za-z0-9_-]', '_', stem)}"
    return name


def _finding_path(audit_dir, stem):
    return Path(audit_dir) / "workspace" / "findings" / f"{stem}.json"


def valid_stem(audit_dir, stem):
    return not commands._bad(stem) and stem != "" and _finding_path(audit_dir, stem).is_file()


def safe_tmp(path):
    """Seul un dossier tmp.* créé par mkdtemp, juste sous $TMPDIR, peut être supprimé"""
    if not str(path) or ".." in Path(path).parts:
        return False
    p = Path(path)
    return (not p.is_symlink() and p.is_dir() and p.parent == Path(tempfile.gettempdir())
            and p.name.startswith("tmp."))


def ensure_audit_branch(audit_dir):
    repo, ref = repo_of(audit_dir), "refs/heads/" + audit_branch(audit_dir)
    r = git(repo, "rev-parse", "--verify", "-q", ref + "^{commit}", check=False)
    if r.returncode == 0:
        return r.stdout.strip()
    state = render.load_json(Path(audit_dir) / "state.json", {})
    base = state.get("base_commit") if isinstance(state, dict) else None
    if not (isinstance(base, str) and re.fullmatch(r"[0-9a-f]{40}", base)
            and git(repo, "cat-file", "-e", base + "^{commit}", check=False).returncode == 0):
        base = git(repo, "rev-parse", "HEAD").stdout.strip()
    git(repo, "update-ref", ref, base, "")  # ancienne valeur vide : création seulement
    return base


def has_filter(repo, rev):
    names = git(repo, "ls-tree", "-r", "-z", "--name-only", rev).stdout.split("\0")
    for n in names:
        if n.rsplit("/", 1)[-1] == ".gitattributes":
            text = git(repo, "cat-file", "-p", f"{rev}:{n}", check=False).stdout
            if any("filter=" in ln for ln in text.splitlines() if not ln.lstrip().startswith("#")):
                return True
    return False


def _cleanup(audit_dir, data, stem):
    e = data.get(stem)
    if not isinstance(e, dict):
        return
    repo, wt = repo_of(audit_dir), e.get("worktree")
    if isinstance(wt, str) and wt and safe_tmp(Path(wt).parent):
        git(repo, "worktree", "remove", "--force", wt, check=False)
        with contextlib.suppress(OSError):
            os.rmdir(Path(wt).parent)
    git(repo, "worktree", "prune", check=False)
    br = e.get("branch")
    if isinstance(br, str) and br.startswith(f"mantis/fix/{Path(audit_dir).name}/"):
        git(repo, "branch", "-D", br, check=False)
    e["worktree"] = None


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
    data = load(audit_dir)
    queued = sorted(_with(audit_dir, "queued"), key=lambda s: str(data[s].get("at") or ""))
    return queued[:max(0, FIX_LIMIT - len(_with(audit_dir, "running")))]


def busy(audit_dir):
    return _with(audit_dir, "running", "ready", "merged")


def active(audit_dir):
    return _with(audit_dir, "queued", "running")


def start(audit_dir, stem):
    audit_dir = Path(audit_dir)
    with locked(audit_dir):
        data = load(audit_dir)
        prev = data.get(stem) if isinstance(data.get(stem), dict) else {}
        if not valid_stem(audit_dir, stem) or prev.get("status") in ("running", "ready", "merged"):
            raise ValueError("finding invalide ou correction déjà en cours")
        repo = repo_of(audit_dir)
        diff = audit_dir / "fixes" / f"{stem}.prev.diff"
        prev_diff = str(diff) if prev.get("status") == "conflict" and diff.is_file() else None
        _cleanup(audit_dir, data, stem)
        head = ensure_audit_branch(audit_dir)
        if has_filter(repo, head):
            e = _set(data, stem, status="failed",
                     error="le repo déclare un filtre git (.gitattributes) : correction refusée")
            _save(audit_dir, data)
            return dict(e)
        f = render.load_json(_finding_path(audit_dir, stem), {})
        f = f if isinstance(f, dict) else {}
        title = " ".join(str(f.get("title") or stem).split())[:200]
        (audit_dir / "fixes").mkdir(exist_ok=True)
        msg = audit_dir / "fixes" / f"{stem}.msg"
        commands.atomic_write(msg, f"fix(mantis): {title} [{stem}]\n")
        branch = fix_branch(audit_dir, stem)
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
                 error=None, agent="Correctif " + short(stem))
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
