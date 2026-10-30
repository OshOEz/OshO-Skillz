#!/usr/bin/env python3
"""Auto-test de guard.py : sauvegarde, contrôle et restauration des findings, RESUME.md
  python3 test_guard.py
"""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
