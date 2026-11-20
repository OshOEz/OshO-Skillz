#!/usr/bin/env python3
"""Auto-test de mantis_source.py : copie figée de Mantis, retard sur l'amont, contrat
  python3 test_mantis_source.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["GIT_CONFIG_GLOBAL"] = os.devnull  # aucun réglage de la machine dans les dépôts de test
os.environ["MANTIS_SOURCE_ALLOW_LOCAL"] = "1"  # dépôts de test en chemins locaux, pas en https
import mantis_source as ms

HERE = Path(__file__).resolve().parent


def git(cwd, *args):
    return ms.git(cwd, *args).stdout.strip()


def commit(repo, files, msg="c"):
    for name, text in files.items():
        p = repo / name
        if text is None:
            git(repo, "rm", "-q", "-r", name)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        git(repo, "add", name)
    git(repo, "commit", "-q", "-m", msg)
    return git(repo, "rev-parse", "HEAD")


def world(tmp):
    """Amont avec toutes les étapes et tous les champs, fork nu cloné de l'amont, mantis.lock sur le fork"""
    tmp = Path(tmp)
    up = tmp / "upstream"
    up.mkdir()
    git(up, "init", "-q", "-b", "main")
    for k, v in (("user.name", "Test"), ("user.email", "t@example.com"), ("commit.gpgsign", "false")):
        git(up, "config", k, v)
    files = {f"skills/{d}/SKILL.md": f"# {d}\n" for d in ms.STAGE_DIRS}
    files["skills/mantis-review/SKILL.md"] += "".join(f"- `{f}`\n" for f in ms.CONTRACT_FIELDS)
    pinned = commit(up, files, "init")
    fork = tmp / "fork.git"
    git(tmp, "clone", "-q", "--bare", str(up), str(fork))
    lock = tmp / "mantis.lock"
    lock.write_text(json.dumps({"repo": str(fork), "upstream": str(up), "commit": pinned}))
    return up, fork, lock, pinned


def run(cmd, lock, d):
    r = subprocess.run([sys.executable, str(HERE / "mantis_source.py"), cmd, "--lock", str(lock), "--dir", str(d)],
                       text=True, capture_output=True)
    return r.returncode, (json.loads(r.stdout) if r.returncode == 0 else r.stderr)


def test_ensure_clones_and_pins():
    with tempfile.TemporaryDirectory() as tmp:
        up, fork, lock, pinned = world(tmp)
        commit(up, {"later.txt": "x"})
        d = Path(tmp) / "mantis"
        code, out = run("ensure", lock, d)
        assert code == 0 and out == {"dir": str(d), "commit": pinned, "cloned": True}, out
        assert git(d, "rev-parse", "HEAD") == pinned


def test_ensure_repoints_existing_clone():
    with tempfile.TemporaryDirectory() as tmp:
        up, fork, lock, pinned = world(tmp)
        commit(up, {"later.txt": "x"})
        d = Path(tmp) / "mantis"
        git(tmp, "clone", "-q", str(up), str(d))
        code, out = run("ensure", lock, d)
        assert code == 0 and out["cloned"] is False, out
        assert git(d, "remote", "get-url", "origin") == str(fork)
        assert git(d, "remote", "get-url", "upstream") == str(up)
        assert git(d, "rev-parse", "HEAD") == pinned


def test_ensure_offline_with_commit_present():
    with tempfile.TemporaryDirectory() as tmp:
        up, fork, lock, pinned = world(tmp)
        d = Path(tmp) / "mantis"
        assert run("ensure", lock, d)[0] == 0
        shutil.rmtree(fork)
        code, out = run("ensure", lock, d)
        assert code == 0 and out["commit"] == pinned, out


def test_ensure_unknown_commit_fails():
    with tempfile.TemporaryDirectory() as tmp:
        up, fork, lock, pinned = world(tmp)
        d = Path(tmp) / "mantis"
        assert run("ensure", lock, d)[0] == 0
        lock.write_text(json.dumps({"repo": str(fork), "upstream": str(up), "commit": "0" * 40}))
        code, err = run("ensure", lock, d)
        assert code == 1 and "0" * 40 in err, err
        assert git(d, "rev-parse", "HEAD") == pinned


def test_behind_counts_and_never_fails():
    with tempfile.TemporaryDirectory() as tmp:
        up, fork, lock, pinned = world(tmp)
        d = Path(tmp) / "mantis"
        assert run("ensure", lock, d)[0] == 0
        for i in range(3):
            commit(up, {f"n{i}.txt": "x"})
        assert run("behind", lock, d) == (0, {"behind": 3})
        shutil.rmtree(up)
        assert run("behind", lock, d) == (0, {"behind": None})
        assert run("behind", lock, Path(tmp) / "absent") == (0, {"behind": None})


def test_diff_reports_contract():
    with tempfile.TemporaryDirectory() as tmp:
        up, fork, lock, pinned = world(tmp)
        d = Path(tmp) / "mantis"
        assert run("ensure", lock, d)[0] == 0
        git(up, "mv", "skills/mantis-critic", "skills/mantis-critique")
        review = (up / "skills/mantis-review/SKILL.md").read_text().replace("`repro_status`", "")
        commit(up, {"skills/mantis-review/SKILL.md": review, "skills/mantis-new/SKILL.md": "# new\n",
                    "skills/mantis two/SKILL.md": "# two\n"})
        code, out = run("diff", lock, d)
        assert code == 0, out
        assert out["from"] == pinned and out["to"] == git(up, "rev-parse", "HEAD") and out["commits"] == 1, out
        assert out["skills"] == {
            "mantis-critic": {"files": 1, "status": "removed"},
            "mantis-critique": {"files": 1, "status": "added"},
            "mantis-new": {"files": 1, "status": "added"},
            "mantis-review": {"files": 1, "status": "changed"},
            "mantis two": {"files": 1, "status": "added"},
        }, out["skills"]
        assert out["contract"] == {"missing_dirs": ["mantis-critic"], "missing_fields": ["repro_status"]}, out
        assert git(d, "rev-parse", "HEAD") == pinned  # l'amont n'est jamais extrait



def test_ensure_refuses_modified_copy():
    with tempfile.TemporaryDirectory() as tmp:
        up, fork, lock, pinned = world(tmp)
        d = Path(tmp) / "mantis"
        assert run("ensure", lock, d)[0] == 0
        (d / ".gitignore").write_text(".DS_Store\n")  # fichier non suivi
        (d / "skills/mantis-plan/SKILL.md").write_text("autre consigne\n")
        code, err = run("ensure", lock, d)
        assert code == 1 and "skills/mantis-plan/SKILL.md" in err and "modifiée" in err, err
        assert (d / "skills/mantis-plan/SKILL.md").read_text() == "autre consigne\n"  # rien d'effacé
        git(d, "checkout", "--", "skills/mantis-plan/SKILL.md")
        code, err = run("ensure", lock, d)
        assert code == 1 and ".gitignore" in err, err
        (d / ".gitignore").unlink()
        assert run("ensure", lock, d)[0] == 0


def test_lock_values_checked():
    with tempfile.TemporaryDirectory() as tmp:
        up, fork, lock, pinned = world(tmp)
        d = Path(tmp) / "mantis"
        lock.write_text(json.dumps({"repo": str(fork), "upstream": str(up), "commit": "origin/main"}))
        code, err = run("ensure", lock, d)
        assert code == 1 and "40" in err and not d.exists(), err
        assert run("behind", lock, d) == (0, {"behind": None})
        lock.write_text(json.dumps({"repo": str(fork), "upstream": str(up), "commit": pinned}))
        env = dict(os.environ)
        del env["MANTIS_SOURCE_ALLOW_LOCAL"]
        r = subprocess.run([sys.executable, str(HERE / "mantis_source.py"), "ensure", "--lock", str(lock),
                            "--dir", str(d)], text=True, capture_output=True, env=env)
        assert r.returncode == 1 and "https://" in r.stderr and not d.exists(), r.stderr


def test_dir_not_a_clone():
    with tempfile.TemporaryDirectory() as tmp:
        up, fork, lock, pinned = world(tmp)
        d = up / "sub"  # dans un dépôt git : git -C remonterait jusqu'à l'amont
        d.mkdir()
        assert run("behind", lock, d) == (0, {"behind": None})
        (d / "x.txt").write_text("x")
        code, err = run("ensure", lock, d)
        assert code == 1 and "pas une copie de Mantis" in err, err
        assert git(up, "remote") == ""
        (d / "x.txt").unlink()
        code, out = run("ensure", lock, d)
        assert code == 0 and out["cloned"] is True and git(d, "rev-parse", "HEAD") == pinned, out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
