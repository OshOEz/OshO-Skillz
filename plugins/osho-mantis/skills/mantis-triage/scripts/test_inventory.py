#!/usr/bin/env python3
"""Auto-test de inventory.py sur un repo git inventé
  python3 test_inventory.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

OUTIL = [sys.executable, str(Path(__file__).with_name("inventory.py"))]
FICHIERS = {
    "app.py": 'import subprocess\n@app.route("/preview")\ndef preview(name):\n    subprocess.run(name, shell=True)\n',
    "index.js": "const a = 1;\nconst b = 2;\nconsole.log(a + b);\n",
    "tests/test_app.py": "def test_ok():\n    assert True\n",
    "osho-mantis/audit-2026-01-01_10h00/repro.py": "import os\nos.system('id')\n",
}


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                   check=True, capture_output=True)


def test_inventaire():
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp, "mon repo")
        for nom, texte in FICHIERS.items():
            (repo / nom).parent.mkdir(parents=True, exist_ok=True)
            (repo / nom).write_text(texte)
        git(repo, "init", "-q")
        git(repo, "add", ".")
        git(repo, "commit", "-qm", "init")
        (repo / "index.js").write_text(FICHIERS["index.js"] + "// escape\n")
        git(repo, "commit", "-qam", "fix XSS in search")
        os.symlink("/dev/zero", str(repo / "evil.py"))
        git(repo, "add", "evil.py")
        git(repo, "commit", "-qm", "add symlink")
        sortie = Path(tmp, "inventory.json")
        r = subprocess.run(OUTIL + [str(repo), str(sortie)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        inv = json.loads(sortie.read_text())
        assert inv["languages"] == {"Python": {"files": 2, "lines": 6}, "JavaScript": {"files": 1, "lines": 4}}, inv["languages"]
        assert inv["files"] == 3, "les audits versionnés dans osho-mantis/ sont exclus"
        assert inv["surface"]["http_route"] == {"count": 1, "files": ["app.py"]}
        assert inv["surface"]["command_exec"] == {"count": 1, "files": ["app.py"]}
        assert inv["history"]["commits"] == 3 and inv["history"]["security_commit_count"] == 1
        assert inv["history"]["security_commits"][0].endswith("fix XSS in search")
        assert inv["repro"]["has_tests"] is True and inv["repro"]["has_dockerfile"] is False
        assert list(inv["levels"]) == ["Light", "Sharp", "Savage", "Overkill"]
        assert inv["levels"]["Light"]["hypotheses"] == 3 and inv["levels"]["Overkill"]["hypotheses"] == 3
        assert [inv["levels"][n]["parallel"] for n in inv["levels"]] == [2, 3, 4, 6]
        assert all(p in inv["levels"]["Sharp"]["subtitle"] for p in ("Pro :", "Max 5x :", "Max 20x :"))
        assert inv["recommended"] == "Light"
        assert "recommandé : Light" in r.stdout


def test_pas_un_repo_git():
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(OUTIL + [tmp, str(Path(tmp, "x.json"))], capture_output=True, text=True)
        assert r.returncode == 2 and "pas un repo git" in r.stderr


if __name__ == "__main__":
    test_inventaire()
    test_pas_un_repo_git()
    print("OK")
