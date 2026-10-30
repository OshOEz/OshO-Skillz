#!/usr/bin/env python3
"""Auto-test de export.py : exclusions, liens symboliques, contenu brut, secrets repérés, conflits de patchs
  python3 test_export.py
"""
import json
import os
import tempfile
import zipfile
from pathlib import Path

import export

GKEY = "AIza" + "B" * 35
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
WARN = ("⚠️ Cette archive contient le détail d'exploits et des secrets en clair. "
        "Transmettez-la uniquement par un canal privé.")


def diff(path, start, n):
    body = "".join(f"-l{i}\n+L{i}\n" for i in range(n))
    return f"--- a/{path}\n+++ b/{path}\n@@ -{start},{n} +{start},{n} @@\n{body}"


def audit(tmp):
    d = Path(tmp) / "repo" / "osho-mantis" / "audit-x"
    (d / "workspace" / "findings").mkdir(parents=True)
    (d / "workspace" / "backups" / "review-r1").mkdir(parents=True)
    (d / "patches").mkdir()
    (d / "campaign.json").write_text(json.dumps({"repo": str(Path(tmp) / "repo"), "level": "Sharp",
                                                 "started_at": "2026-10-29T12:00:00",
                                                 "finished_at": "2026-10-29T14:00:00"}))
    (d / "state.json").write_text(json.dumps({"stages": {"patch": "done"}, "base_commit": "abc123",
                                              "finished": True,
                                              "notes": ["conflit : a et b touchent Web.java",
                                                        "f1aaaaaa prérequis : définir API_PASSWORD"]}))
    for name in ("server.json", "server.log", "waiting.json", "commands.jsonl", "commands-done.jsonl"):
        (d / name).write_text("{}")
    (d / "workspace" / "backups" / "review-r1" / "f1.json").write_text("{}")
    (d / "workspace" / "findings" / "x.json.tmp").write_text("")
    f1 = {"id": "f1aaaaaa-1", "title": "Clé Google dans le dépôt", "severity": "HIGH", "status": "VALID",
          "description": f"clé {GKEY}", "patch_status": "VERIFIED_SECURE",
          "patch_diff": diff("app/Web.java", 10, 11)}
    f2 = {"id": "f2", "title": "Autre", "severity": "CRITICAL", "status": "VALID",
          "patch_status": "MITIGATION_PROPOSED", "patch_diff": diff("app/Web.java", 15, 11)}
    f3 = {"id": "f3", "title": "Loin", "severity": "MEDIUM", "status": "VALID",
          "patch_status": "MITIGATION_PROPOSED", "patch_diff": diff("app/Web.java", 40, 3)}
    for stem, f in (("f1", f1), ("f2", f2), ("f3", f3)):
        (d / "workspace" / "findings" / f"{stem}.json").write_text(json.dumps(f))
        (d / "patches" / f"{f['id']}.diff").write_text(f["patch_diff"])
    (d / "patches" / "f2.diff").write_text(diff("app/Web.java", 15, 11) + f"+ aws = '{AWS}'\n")
    (d / "README.md").write_text(f"recopie {GKEY}")
    (d / "dashboard.html").write_text("<html>dash</html>")
    (d / "bilan.html").write_text("<html>bilan</html>")
    os.symlink("/etc", d / "workspace" / "lien")
    os.symlink("/etc/hosts", d / "workspace" / "hosts")
    return d


def names(z):
    return {n.split("/", 1)[1] for n in zipfile.ZipFile(z).namelist()}


def test_exclusions_et_liens():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        out = Path(tmp) / "full.zip"
        m = export.build("full", d, out)
        got = names(out)
        for bad in ("server.json", "server.log", "waiting.json", "commands.jsonl", "commands-done.jsonl",
                    "workspace/backups/review-r1/f1.json", "workspace/findings/x.json.tmp",
                    "workspace/lien", "workspace/hosts"):
            assert bad not in got, bad
        assert not any(n.startswith("workspace/lien/") for n in got)
        for good in ("campaign.json", "state.json", "workspace/findings/f1.json", "patches/f2.diff",
                     "README.md", "dashboard.html", "LISEZMOI-DEV.md", "MANIFESTE.json"):
            assert good in got, good
        assert sorted(m["symlinks_skipped"]) == ["workspace/hosts", "workspace/lien"]


def test_contenu_brut():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        out = Path(tmp) / "full.zip"
        export.build("full", d, out)
        z = zipfile.ZipFile(out)
        src = (d / "workspace" / "findings" / "f1.json").read_bytes()
        assert z.read("audit-x/workspace/findings/f1.json") == src and GKEY.encode() in src


def test_secrets_listes():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        found = export.scan_secrets(d)
        keys = {(s["file"], s["kind"], s["finding"]) for s in found}
        assert ("workspace/findings/f1.json", "clé Google", "f1") in keys, keys
        assert ("patches/f2.diff", "clé AWS", "f2") in keys, keys
        assert not any(s["file"] == "README.md" for s in found), "les recopies ne sont pas listées"
        out = Path(tmp) / "full.zip"
        export.build("full", d, out)
        man = zipfile.ZipFile(out).read("audit-x/MANIFESTE.json").decode()
        assert GKEY not in man and AWS not in man and "clé Google" in man


def test_conflits():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        c = export.conflicts(d)
        pairs = {(x["a"], x["b"], x["kind"]) for x in c if x["kind"] != "note"}
        assert ("f1aaaaaa-1", "f2", "chevauchement") in pairs, pairs
        assert ("f1aaaaaa-1", "f3", "même fichier") in pairs, pairs
        assert ("f2", "f3", "même fichier") in pairs, pairs
        assert any(x["kind"] == "note" and "Web.java" in x["note"] for x in c)


def test_plages():
    r = export.patch_files("--- a/x\n+++ b/x\n@@ -3 +3 @@\n-a\n+b\n@@ -10,0 +11,2 @@\n+c\n+d\n"
                           "--- /dev/null\n+++ b/new.txt\n@@ -0,0 +1 @@\n+n\n")
    assert r == {"x": [(3, 3), (10, 10)], "new.txt": [(0, 0)]}, r


def test_leger():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        out = Path(tmp) / "light.zip"
        export.build("light", d, out)
        assert names(out) == {"bilan.html", "dashboard.html", "LISEZMOI-DEV.md"}, names(out)


def test_lisezmoi():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        md = export.dev_readme(d, export.scan_secrets(d), export.conflicts(d))
        assert md.startswith("# ") and WARN in md
        assert "git apply --check" in md and "abc123" in md
        assert "Secrets à révoquer" in md and "Clé Google dans le dépôt" in md
        assert "définir API_PASSWORD" in md, "prérequis rattaché par l'id court"
        assert md.index("Autre") < md.index("Clé Google dans le dépôt"), "gravité décroissante"


def test_lisezmoi_sans_secret():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        md = export.dev_readme(d, [], [])
        assert "aucun secret repéré par motifs (vérification non exhaustive)" in md


def test_audit_lien_refuse():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp)
        link = Path(tmp) / "lien-audit"
        os.symlink(d, link)
        try:
            export.build("full", link, Path(tmp) / "x.zip")
        except ValueError:
            return
        raise AssertionError("un dossier d'audit qui est un lien symbolique est refusé")


if __name__ == "__main__":
    test_exclusions_et_liens()
    test_contenu_brut()
    test_secrets_listes()
    test_conflits()
    test_plages()
    test_leger()
    test_lisezmoi()
    test_lisezmoi_sans_secret()
    test_audit_lien_refuse()
    print("OK")
