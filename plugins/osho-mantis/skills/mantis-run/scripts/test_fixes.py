#!/usr/bin/env python3
"""Auto-test de fixes.py : branches et worktrees des corrections
  python3 test_fixes.py
"""
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import fixes
from test_snapshot import audit as make_audit

F = {"title": "Faille", "severity": "HIGH"}
HERE = Path(__file__).resolve().parent


def git(cwd, *args):
    return fixes.git(Path(cwd), *args).stdout.strip()


@contextlib.contextmanager
def scratch():
    """Dossier jetable ; les worktrees créés dans $TMPDIR pour <tmp>/repo sont supprimés à la sortie"""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            yield tmp
        finally:
            repo = Path(tmp) / "repo"
            if repo.is_dir():
                for line in git(repo, "worktree", "list", "--porcelain").splitlines()[1:]:
                    if line.startswith("worktree "):
                        parent = Path(line[9:]).parent
                        for p in {parent, Path(tempfile.gettempdir()) / parent.name}:
                            if fixes.safe_tmp(p):
                                shutil.rmtree(p)
                git(repo, "worktree", "prune")


def git_audit(tmp, findings=(("f1", F),), state=None):
    repo = Path(tmp) / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    for k, v in (("user.name", "Test"), ("user.email", "t@example.com"), ("commit.gpgsign", "false")):
        git(repo, "config", k, v)
    (repo / "app.py").write_text("".join(f"{i}\n" for i in range(1, 11)))
    git(repo, "add", "app.py")
    git(repo, "commit", "-q", "-m", "init")
    top = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    d = make_audit(repo / "osho-mantis" / "audit-x", {"repo": str(top), "level": "Light"},
                   state=state, findings=findings)
    with open(repo / ".git" / "info" / "exclude", "a") as fh:
        fh.write("osho-mantis/\n")
    return d, repo


def agent_commit(entry, path="app.py", line=3, text="fixed"):
    wt = Path(entry["worktree"])
    lines = (wt / path).read_text().splitlines()
    lines[line - 1] = text
    (wt / path).write_text("\n".join(lines) + "\n")
    git(wt, "add", "-A")
    git(wt, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-F", entry["msg_file"])
    return git(wt, "rev-parse", "HEAD")


def make_ready(audit, stem, **kw):
    agent_commit(fixes.start(audit, stem), **kw)
    return fixes.finish(audit, stem)


def commit_file(repo, name, text, msg="c"):
    (repo / name).write_text(text)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def has_ref(repo, ref):
    return fixes.git(repo, "rev-parse", "--verify", "-q", ref, check=False).returncode == 0


def test_start_cree_branches():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        e = fixes.start(d, "f1")
        assert git(repo, "rev-parse", "refs/heads/mantis/audit-x") == git(repo, "rev-parse", "HEAD")
        assert has_ref(repo, "refs/heads/mantis/fix/audit-x/f1")
        assert e["status"] == "running" and Path(e["worktree"]).is_dir() and e["agent"] == "Correctif f1"
        assert e["title"] == "Faille" and e["bucket"] == "HIGH" and e["dirty"] is False and e["prev_diff"] is None


def test_base_commit():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        first = git(repo, "rev-parse", "HEAD")
        (d / "state.json").write_text(json.dumps({"base_commit": first}))
        commit_file(repo, "b.txt", "b")
        fixes.start(d, "f1")
        assert git(repo, "rev-parse", "refs/heads/mantis/audit-x") == first
    with scratch() as tmp:
        d, repo = git_audit(tmp, state={"base_commit": "zzz"})
        commit_file(repo, "b.txt", "b")
        fixes.start(d, "f1")
        assert git(repo, "rev-parse", "refs/heads/mantis/audit-x") == git(repo, "rev-parse", "HEAD")


def test_branche_audit_reutilisee():
    with scratch() as tmp:
        d, repo = git_audit(tmp, findings=(("f1", F), ("f2", F), ("f3", F)))
        a, b = fixes.start(d, "f1"), fixes.start(d, "f2")
        assert a["base"] == b["base"]
        tree = git(repo, "rev-parse", "HEAD^{tree}")
        new = git(repo, "commit-tree", tree, "-p", a["base"], "-m", "manuel")
        git(repo, "update-ref", "refs/heads/mantis/audit-x", new)
        assert fixes.start(d, "f3")["base"] == new


def test_finish_ready_et_failed():
    with scratch() as tmp:
        d, repo = git_audit(tmp, findings=(("f1", F), ("f2", F)))
        e = make_ready(d, "f1")
        assert e["status"] == "ready" and e["commit"] == git(repo, "rev-parse", "refs/heads/mantis/fix/audit-x/f1")
        assert Path(e["worktree"]).is_dir()
        s = fixes.start(d, "f2")
        e = fixes.finish(d, "f2")
        assert e["status"] == "failed" and e["error"] == "aucun commit sur la branche du correctif"
        assert not Path(s["worktree"]).exists() and not Path(s["worktree"]).parent.exists()
        assert not has_ref(repo, "refs/heads/mantis/fix/audit-x/f2")


def test_worktree_disparu():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        s = fixes.start(d, "f1")
        shutil.rmtree(Path(s["worktree"]).parent)
        assert fixes.finish(d, "f1")["status"] == "failed"
        listed = git(repo, "worktree", "list")
        assert s["worktree"] not in listed and str(Path(s["worktree"]).resolve()) not in listed


def test_reconcile():
    with scratch() as tmp:
        d, repo = git_audit(tmp, findings=(("f1", F), ("f2", F)))
        agent_commit(fixes.start(d, "f1"))
        fixes.start(d, "f2")
        r = fixes.reconcile(d)
        assert [e["status"] for e in r] == ["ready", "failed"] and r[1]["error"] == "correction interrompue"


def test_launchable_limite():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        for s in ("a", "b", "c", "d", "e"):
            fixes.queue(d, s)
        assert fixes.launchable(d) == ["a", "b", "c"]
        fixes.update(d, "x", status="running")
        fixes.update(d, "y", status="running")
        assert fixes.launchable(d) == ["a"]
        assert fixes.active(d) == ["a", "b", "c", "d", "e", "x", "y"] and fixes.busy(d) == ["x", "y"]


def test_stem_hostile():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        for stem in ("../x", "absent"):
            try:
                fixes.start(d, stem)
                raise AssertionError(stem)
            except ValueError:
                pass
        assert git(repo, "for-each-ref", "refs/heads/mantis/") == ""


def test_filtre_refuse():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        commit_file(repo, ".gitattributes", "# filter=commentaire\n* filter=evil\n")
        e = fixes.start(d, "f1")
        assert e["status"] == "failed" and "filtre git" in e["error"]
        assert len(git(repo, "worktree", "list").splitlines()) == 1


def test_titre_hostile_message():
    with scratch() as tmp:
        d, repo = git_audit(tmp, findings=(("f1", {"title": 'a"; $(id) `\nb\x00\x1b[31m', "severity": "LOW"}),))
        e = fixes.start(d, "f1")
        msg = Path(e["msg_file"]).read_text()
        assert len(msg.splitlines()) == 1 and "$(id)" in msg and msg.rstrip("\n").endswith("[f1]")
        assert "\x00" not in msg and "\x1b" not in msg
        agent_commit(e)
        assert git(Path(e["worktree"]), "log", "-1", "--format=%s") == msg.strip()


def test_safe_tmp():
    t = Path(tempfile.gettempdir())
    real = Path(tempfile.mkdtemp(prefix="tmp."))
    link = t / f"tmp.lien-{os.getpid()}"
    other = t / f"com.apple.x-{os.getpid()}"
    try:
        link.symlink_to(real)
        other.mkdir()
        assert fixes.safe_tmp(real)
        for p in ("", Path.home(), t / ".." / "x", link, other):
            assert not fixes.safe_tmp(p), p
    finally:
        link.unlink(missing_ok=True)
        os.rmdir(real)
        os.rmdir(other)


def test_repo_of_refuse():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        (d / "campaign.json").write_text(json.dumps({"repo": "/tmp", "level": "Light"}))
        try:
            fixes.start(d, "f1")
            raise AssertionError("repo accepté")
        except ValueError as e:
            assert str(e) == "repo de l'audit introuvable"


def test_stem_non_imprimable():
    with scratch() as tmp:
        d, repo = git_audit(tmp, findings=(("a\nb", F),))
        assert (d / "workspace" / "findings" / "a\nb.json").is_file() and not fixes.valid_stem(d, "a\nb")


def test_cleanup_garde_worktree_non_supprime():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        wt = fixes.start(d, "f1")["worktree"]
        real, fixes.safe_tmp = fixes.safe_tmp, lambda p: False  # $TMPDIR différent d'un processus à l'autre
        try:
            e = fixes.fail(d, "f1", "x")
        finally:
            fixes.safe_tmp = real
        assert e["worktree"] == wt and Path(wt).is_dir() and e["cleanup_error"]
        assert fixes.load(d)["f1"]["worktree"] == wt
        fixes.cleanup(d, "f1")
        e = fixes.load(d)["f1"]
        assert e["worktree"] is None and "cleanup_error" not in e and not Path(wt).exists()
        assert not has_ref(repo, "refs/heads/mantis/fix/audit-x/f1")


def test_branche_restante():
    with scratch() as tmp:
        d, repo = git_audit(tmp, findings=(("f1", F), ("f2", F)))
        git(repo, "branch", "mantis/fix/audit-x/f1")
        assert fixes.start(d, "f1")["status"] == "running"
        git(repo, "worktree", "add", "-q", "-b", "mantis/fix/audit-x/f2", str(Path(tmp) / "reste"))
        e = fixes.start(d, "f2")
        assert e["status"] == "failed" and "encore extraite" in e["error"]
        assert (Path(tmp) / "reste").is_dir()


def test_worktree_etranger_garde():
    with scratch() as tmp:
        d, repo = git_audit(tmp, findings=(("f1", F), ("f2", F)))
        git(repo, "worktree", "add", "-q", "--detach", str(Path(tmp) / "etranger"))
        shutil.rmtree(Path(tmp) / "etranger")  # disque démonté : enregistrement périmé de l'utilisateur
        fixes.start(d, "f1")
        fixes.finish(d, "f1")
        shutil.rmtree(Path(fixes.start(d, "f2")["worktree"]).parent)
        fixes.finish(d, "f2")
        assert (repo / ".git" / "worktrees" / "etranger").is_dir()
        assert len(git(repo, "worktree", "list").splitlines()) == 2


def test_fix_branch_collision():
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "audit-x"
        d.mkdir()
        fixes.update(d, "abcdefgh1", branch="mantis/fix/audit-x/abcdefgh")
        assert fixes.fix_branch(d, "abcdefgh1") == "mantis/fix/audit-x/abcdefgh"
        assert fixes.fix_branch(d, "abcdefgh2") == "mantis/fix/audit-x/abcdefgh2"
        assert fixes.fix_branch(d, "a.b") == "mantis/fix/audit-x/a_b"


def test_cli():
    run = lambda *a: subprocess.run([sys.executable, str(HERE / "fixes.py"), *a], capture_output=True, text=True)
    out = run("--help")
    assert out.returncode == 0
    for c in ("start", "finish", "fail", "launchable", "reconcile", "busy", "active"):
        assert c in out.stdout, c
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        assert run("start", str(d), "../x").returncode == 2


def test_merge_sans_conflit():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        make_ready(d, "f1")
        assert fixes.merge(d, "f1") == ("merged", None)
        assert git(repo, "log", "-1", "--format=%s", "mantis/audit-x") == "Merge correctif Mantis : Faille [f1]"
        assert len(git(repo, "rev-list", "--parents", "-1", "mantis/audit-x").split()) == 3
        e = fixes.load(d)["f1"]
        assert e["status"] == "merged" and e["merge_commit"] == git(repo, "rev-parse", "mantis/audit-x")
        assert e["error"] is None and not has_ref(repo, "refs/heads/mantis/fix/audit-x/f1")


def _conflit(tmp):
    d, repo = git_audit(tmp, findings=(("f1", F), ("f2", F)))
    make_ready(d, "f1", text="autre")
    wt2 = make_ready(d, "f2")["worktree"]
    assert fixes.merge(d, "f1")[0] == "merged"
    return d, repo, wt2


def test_merge_conflit():
    with scratch() as tmp:
        d, repo, wt2 = _conflit(tmp)
        before = git(repo, "rev-parse", "mantis/audit-x")
        assert fixes.merge(d, "f2") == ("conflict", "conflit avec un autre correctif")
        assert git(repo, "rev-parse", "mantis/audit-x") == before
        assert "+fixed" in (d / "fixes" / "f2.prev.diff").read_text()
        assert fixes.load(d)["f2"]["status"] == "conflict" and not Path(wt2).exists()


def test_recorriger_part_de_la_tete():
    with scratch() as tmp:
        d, repo, _ = _conflit(tmp)
        fixes.merge(d, "f2")
        e = fixes.start(d, "f2")
        assert e["base"] == git(repo, "rev-parse", "mantis/audit-x")
        assert e["prev_diff"] == str(d / "fixes" / "f2.prev.diff")


def test_merge_concurrent_update_ref():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        e = make_ready(d, "f1")
        ref = "refs/heads/mantis/audit-x"
        stale = git(repo, "rev-parse", ref)
        tree = git(repo, "rev-parse", "HEAD^{tree}")
        git(repo, "update-ref", ref, git(repo, "commit-tree", tree, "-p", stale, "-m", "autre"))
        now = git(repo, "rev-parse", ref)
        assert fixes.merge_ref(repo, ref, stale, e["commit"], "m") == ("busy", None)
        assert git(repo, "rev-parse", ref) == now


def test_merge_double_seul_un():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        make_ready(d, "f1")
        out = []
        ts = [threading.Thread(target=lambda: out.append(fixes.merge(d, "f1")[0])) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        assert sorted(out) == ["merged", "refused"], out
        assert git(repo, "rev-list", "--merges", "--count", "mantis/audit-x") == "1"


def test_merge_branche_supprimee():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        make_ready(d, "f1")
        git(repo, "update-ref", "-d", "refs/heads/mantis/audit-x")
        assert fixes.merge(d, "f1") == ("failed", "branche de l'audit introuvable")
        assert fixes.load(d)["f1"]["status"] == "failed"
        assert not has_ref(repo, "refs/heads/mantis/audit-x")


def test_repo_utilisateur_intact():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        snap = lambda: (git(repo, "status", "--porcelain"), git(repo, "symbolic-ref", "HEAD"),
                        git(repo, "rev-parse", "HEAD"), (repo / "app.py").read_text())
        before = snap()
        make_ready(d, "f1")
        assert fixes.merge(d, "f1")[0] == "merged"
        assert snap() == before


def test_hooks_neutralises():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        hooks = repo / "hooks"
        hooks.mkdir()
        for h in ("post-checkout", "reference-transaction"):
            (hooks / h).write_text(f"#!/bin/sh\ntouch '{tmp}/HOOKED'\n")
            (hooks / h).chmod(0o755)
        git(repo, "config", "core.hooksPath", str(hooks))
        make_ready(d, "f1")
        assert fixes.merge(d, "f1")[0] == "merged"
        assert not (Path(tmp) / "HOOKED").exists()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
