#!/usr/bin/env python3
"""Auto-test de guard.py : sauvegarde, contrôle et restauration des findings, RESUME.md, garde du shadow
  python3 test_guard.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Un GIT_DIR hérité (hook pre-push d'un worktree lié) ferait écrire les dépôts de test dans le vrai dépôt.
for _k in subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True).stdout.split():
    os.environ.pop(_k, None)

import guard

GUARD = Path(__file__).with_name("guard.py")


def audit(tmp, state=None):
    d = Path(tmp) / "repo" / "osho-mantis" / "audit-x"
    (d / "workspace" / "findings").mkdir(parents=True)
    (d / "campaign.json").write_text(json.dumps({"repo": str(Path(tmp) / "repo"), "level": "Overkill"}))
    (d / "state.json").write_text(json.dumps(state or {
        "round": 2, "stages": {"plan": "done", "reproduce": "running", "patch": "pending"},
        "force_repro": ["f2"], "notes": ["n1", "reprise après coupure quota"], "deps_volume": "mantis-repo-deps"}))
    for i in (1, 2, 3):
        (d / "workspace" / "findings" / f"f{i}.json").write_text(json.dumps(
            {"id": f"f{i}", "title": f"T{i}", "severity": "HIGH", "repro_status": "reproduced", "patch_diff": "x"}))
    return d


def test_backup_et_rotation():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        paths = []
        for k in range(4):
            paths.append(guard.backup(d, "review", stamp=f"2026103{k}-120000"))
        kept = sorted(p.name for p in (d / "workspace" / "backups").iterdir())
        assert kept == ["review-r2-20261031-120000", "review-r2-20261032-120000", "review-r2-20261033-120000"], kept
        assert (paths[-1] / "f1.json").read_text() == (d / "workspace" / "findings" / "f1.json").read_text()


def test_check_detecte():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        guard.backup(d, "calibrate")
        assert guard.check(d) == []
        f = d / "workspace" / "findings"
        (f / "f1.json").write_text("")                       # vidé par un helper jq
        (f / "f2.json").write_text('{"id": "f2", "tit')      # tronqué
        (f / "f3.json").write_text(json.dumps({"id": "f3", "title": "T3", "severity": "HIGH"}))  # champs perdus
        probs = {p["file"]: p["problem"] for p in guard.check(d)}
        assert set(probs) == {"f1.json", "f2.json", "f3.json"}, probs
        assert probs["f1.json"] == "vide" and probs["f2.json"] == "JSON illisible"
        assert "repro_status" in probs["f3.json"] and "patch_diff" in probs["f3.json"]


def test_check_fichier_disparu():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        guard.backup(d, "patch")
        (d / "workspace" / "findings" / "f3.json").unlink()
        assert [p["file"] for p in guard.check(d)] == ["f3.json"]


def test_restore():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        orig = (d / "workspace" / "findings" / "f1.json").read_text()
        guard.backup(d, "calibrate")
        (d / "workspace" / "findings" / "f1.json").write_text("")
        (d / "workspace" / "findings" / "f3.json").unlink()
        done = guard.restore(d, [p["file"] for p in guard.check(d)])
        assert sorted(done) == ["f1.json", "f3.json"]
        assert (d / "workspace" / "findings" / "f1.json").read_text() == orig and guard.check(d) == []


def test_nouveau_finding_pas_un_probleme():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        guard.backup(d, "review")
        (d / "workspace" / "findings" / "f9.json").write_text(json.dumps({"id": "f9", "title": "nouveau"}))
        assert guard.check(d) == []


def test_lien_refuse():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        os.symlink("/etc/hosts", d / "workspace" / "findings" / "lien.json")
        b = guard.backup(d, "review")
        assert not (b / "lien.json").exists(), "un lien symbolique n'est jamais copié"
        assert {"file": "lien.json", "problem": "lien symbolique"} in guard.check(d)


def test_resume():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        guard.resume(d)
        md = (d / "RESUME.md").read_text()
        for s in ("# Reprise de l'audit Mantis : repo", "Tour : 2", "reproduce", "en cours", "f2", "mantis-repo-deps",
                  f'/mantis-run "{d}"', "docker ps -a", "reprise après coupure quota"):
            assert s in md, s


def test_resume_termine():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, state={"round": 3, "stages": {"reflect": "done"}, "finished": True})
        guard.resume(d)
        assert "Audit terminé" in (d / "RESUME.md").read_text()


def test_cli():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        run = lambda *a: subprocess.run([sys.executable, str(GUARD), *a], capture_output=True, text=True)
        assert run("backup", str(d), "review").returncode == 0
        (d / "workspace" / "findings" / "f1.json").write_text("")
        r = run("check", str(d))
        assert r.returncode == 1 and json.loads(r.stdout.splitlines()[0])["file"] == "f1.json"
        assert run("restore", str(d)).returncode == 0 and run("check", str(d)).returncode == 0
        assert run("resume", str(d)).returncode == 0 and (d / "RESUME.md").exists()
        assert run("nope", str(d)).returncode != 0


def tmp_d():
    return os.path.dirname(subprocess.run(["mktemp", "-u"], capture_output=True, text=True, check=True).stdout.strip())


def state(d):
    return json.loads((d / "state.json").read_text())


def git_repo(repo):
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "suivi.txt").write_text("suivi")
    (repo / "libre.txt").write_text("non suivi")
    os.symlink("suivi.txt", repo / "lien")
    subprocess.run(["git", "-C", str(repo), "add", "suivi.txt", "lien"], check=True)


def test_shadow_guard_accepts_own_mktemp():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        s = guard.shadow_new(d)
        try:
            assert guard.shadow_ok(str(s)) and state(d)["shadow"] == str(s)
        finally:
            shutil.rmtree(s)


def test_shadow_guard_rejects():
    D = tmp_d()
    real = subprocess.run(["mktemp", "-d"], capture_output=True, text=True, check=True).stdout.strip()
    suffixe = f"{os.getpid()}-{os.urandom(4).hex()}"
    voisin, lien = os.path.join(D, f"com.apple.x{suffixe}"), os.path.join(D, f"tmp.lien{suffixe}")
    try:
        os.mkdir(voisin)
        os.symlink(real, lien)
        with tempfile.TemporaryDirectory() as tmp:
            ailleurs = os.path.join(tmp, "tmp.x")
            os.mkdir(ailleurs)
            for p in ("", None, os.path.join(D, "tmp.inexistant"), os.path.expanduser("~"),
                      D + "/../../../../etc/x", voisin, lien, ailleurs, ["x"], 3):
                assert not guard.shadow_ok(p), p
    finally:
        if os.path.islink(lien):
            os.unlink(lien)
        for p in (voisin, real):
            if os.path.isdir(p):
                os.rmdir(p)


def test_shadow_reset_copies_tracked_only():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        git_repo(Path(tmp) / "repo")
        s = guard.shadow_new(d)
        try:
            (s / "reste.txt").write_text("passage précédent")
            assert guard.shadow_reset(d) == s
            assert sorted(os.listdir(s)) == ["suivi.txt"], os.listdir(s)
        finally:
            shutil.rmtree(s)


def test_shadow_reset_refused_path_is_left_alone():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        git_repo(Path(tmp) / "repo")
        hors = Path(tmp) / "tmp.hors"
        hors.mkdir()
        (hors / "temoin").write_text("x")
        (d / "state.json").write_text(json.dumps({"shadow": str(hors), "notes": []}))
        s = guard.shadow_reset(d)
        try:
            assert (hors / "temoin").exists() and s != hors
            st = state(d)
            assert st["shadow"] == str(s) and st["notes"] == ["shadow recréé : ancien chemin refusé ou absent"]
            assert os.listdir(s) == ["suivi.txt"]
        finally:
            shutil.rmtree(s)


def test_shadow_reset_refused_list_entry_replaced_in_place():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        git_repo(Path(tmp) / "repo")
        hors = Path(tmp) / "tmp.hors"
        hors.mkdir()
        (d / "state.json").write_text(json.dumps({"shadow": "garde", "shadows": ["a", str(hors), "b"]}))
        s = guard.shadow_reset(d, str(hors))
        try:
            st = state(d)
            assert hors.is_dir() and st["shadows"] == ["a", str(s), "b"] and st["shadow"] == "garde", st
        finally:
            shutil.rmtree(s)


def test_shadow_commands_refuse_unreadable_state():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        s = guard.shadow_new(d)
        # Les `mktemp -d` de guard sont notés ici, pas comptés dans le dossier temporaire partagé avec d'autres processus.
        made, real = [], guard._mktemp
        guard._mktemp = lambda *a: made.append(a) or real(*a)
        try:
            for bad in ('{"round": 2, "stag', "[1, 2]"):
                (d / "state.json").write_text(bad)
                for cmd in (["shadow-new"], ["shadow-reset"], ["shadow-drop", str(s)]):
                    r = subprocess.run([sys.executable, str(GUARD), cmd[0], str(d), *cmd[1:]], capture_output=True, text=True)
                    assert r.returncode != 0 and "state.json illisible" in r.stderr, (cmd, r.stderr)
                    assert (d / "state.json").read_text() == bad and s.is_dir()
                for fn, args in ((guard.shadow_new, ()), (guard.shadow_reset, ()), (guard.shadow_drop, (str(s),))):
                    try:
                        fn(d, *args)
                        raise AssertionError(f"{fn.__name__} a accepté un state.json illisible")
                    except RuntimeError as err:
                        assert "state.json illisible" in str(err), err
                assert ("-d",) not in made, "aucun shadow créé"
        finally:
            guard._mktemp = real
            shutil.rmtree(s)


def test_shadow_reset_copy_failure_says_so():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)  # tmp/repo n'est pas un dépôt git : git ls-files échoue
        s = guard.shadow_new(d)
        try:
            r = subprocess.run([sys.executable, str(GUARD), "shadow-reset", str(d)], capture_output=True, text=True)
            assert r.returncode != 0 and "incomplet" in r.stderr and "git ls-files" in r.stderr, r.stderr
        finally:
            shutil.rmtree(s)


def test_shadow_drop():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        s = guard.shadow_new(d)
        assert guard.shadow_drop(d) and not s.exists() and "shadow" not in state(d)
        hors = Path(tmp) / "tmp.hors"
        hors.mkdir()
        (d / "state.json").write_text(json.dumps({"shadow": str(hors)}))
        before = (d / "state.json").read_text()
        r = subprocess.run([sys.executable, str(GUARD), "shadow-drop", str(d)], capture_output=True, text=True)
        assert r.returncode == 2 and r.stderr and hors.is_dir() and (d / "state.json").read_text() == before


def test_shadow_list():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        run = lambda *a: subprocess.run([sys.executable, str(GUARD), *a], capture_output=True, text=True)
        a, b = (run("shadow-new", str(d), "--list").stdout.strip() for _ in range(2))
        try:
            assert state(d)["shadows"] == [a, b] and "shadow" not in state(d)
            assert run("shadow-drop", str(d), a).returncode == 0
            assert state(d)["shadows"] == [b] and not os.path.exists(a)
        finally:
            for p in (a, b):
                shutil.rmtree(p, ignore_errors=True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
