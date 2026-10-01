#!/usr/bin/env python3
"""Auto-test de render.py : 3 findings (dont un hostile) + 1 fichier cassé, puis un audit sans finding
  python3 test_render.py
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RENDER = Path(__file__).with_name("render.py")
XSS = "</script><script>alert(1)</script>"
CRIT = {"id": "../c1", "title": "Injection de commande <img src=x onerror=alert(1)>", "severity": "CRITICAL",
        "priority": "CRITICAL", "status": "VALID", "mantis_risk_score": 9.1, "description": XSS,
        "code_paths": ["app.py:76"], "repro_status": "reproduced", "run_command": "curl 'localhost/preview?file=a;id'",
        "repro_output": "uid=0(root)", "patch_status": "VERIFIED_SECURE",
        "patch_diff": "--- a/app.py\n+++ b/app.py\n@@ -76 +76 @@\n-    subprocess.run(cmd, shell=True)\n+    subprocess.run([\"cat\", name])\n"}
LOW = {"id": "l1", "title": "En-tête de sécurité manquant", "severity": "LOW", "status": "PROVISIONALLY_VALID",
       "code_paths": ["app.py:12"], "description": "X-Frame-Options absent.", "impact": "Clickjacking.",
       "mitigation": "Ajouter l'en-tête.", "history": [], "attacker_position": "remote",
       "privileges_required": "none", "user_interaction": "required"}
REJ = {"id": "r1", "title": "Faux SQLi", "severity": "HIGH", "status": "FALSE_POSITIVE", "reasoning": "Requête paramétrée."}


def audit(tmp, findings, broken=False):
    d = Path(tmp)
    (d / "workspace" / "findings").mkdir(parents=True)
    (d / "campaign.json").write_text(json.dumps({"repo": "/x/demo", "level": "Light", "mantis_commit": "47099ed",
                                                 "started_at": "2026-10-01T14:32:00", "finished_at": "2026-10-01T15:47:00"}))
    (d / "state.json").write_text(json.dumps({"stages": {"threat-model": "done", "reproduce": "skipped"},
                                              "notes": ["reproduce sauté : niveau Light"]}))
    for i, f in enumerate(findings):
        (d / "workspace" / "findings" / f"f{i}.json").write_text(json.dumps(f))
    if broken:
        (d / "workspace" / "findings" / "broken.json").write_text("{pas du json")
    r = subprocess.run([sys.executable, str(RENDER), str(d)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return d


def data(d):
    html = (d / "dashboard.html").read_text()
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    return html, json.loads(m.group(1))


def test_trois_findings():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [CRIT, LOW, REJ], broken=True)
        html, payload = data(d)
        assert {f["id"]: f["_bucket"] for f in payload["findings"]} == {"../c1": "CRITICAL", "l1": "LOW", "r1": "REJECTED"}
        assert XSS not in html and "<img src=x" not in html, "le texte des findings n'est jamais du HTML actif"
        st = payload["stats"]
        assert st["by_bucket"]["REJECTED"] == 1 and st["reproduced"] == 1 and st["patched"] == 1 and st["total"] == 3
        assert payload["meta"]["duration"] == "1 h 15 min"
        assert sorted(p.name for p in (d / "patches").iterdir()) == [".._c1.diff"], "patch confiné dans patches/"
        readme = (d / "README.md").read_text()
        assert "Injection de commande" in readme and "<img src=x" not in readme
        assert "## Écartés" in readme and "Faux SQLi" in readme
        assert "non évalué à ce niveau" in readme
        assert "broken.json" in readme and "reproduce sauté : niveau Light" in readme
        assert "git apply osho-mantis/" in readme and ".._c1.diff" in readme
        if shutil.which("node"):
            js = Path(tmp, "check.js")
            js.write_text(re.findall(r"<script>(.*?)</script>", html, re.S)[0])
            r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr


def test_aucun_finding():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [])
        _, payload = data(d)
        assert payload["findings"] == [] and payload["stats"]["total"] == 0
        assert "Aucun finding" in (d / "README.md").read_text()
        assert not (d / "patches").exists()


def test_safe_id_collision():
    """Two findings whose IDs differ only in sanitized chars (e.g., "a/b" and "a_b") get distinct files."""
    COL1 = {"id": "a/b", "title": "Finding one", "severity": "CRITICAL", "status": "VALID",
            "patch_diff": "DIFF-ONE\n"}
    COL2 = {"id": "a_b", "title": "Finding two", "severity": "CRITICAL", "status": "VALID",
            "patch_diff": "DIFF-TWO\n"}
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [COL1, COL2])
        html, payload = data(d)
        # Both findings should have distinct _file names
        files = {f["id"]: f["_file"] for f in payload["findings"]}
        assert files["a/b"] != files["a_b"], f"Collision: both map to {files['a/b']}"
        # Both patch files should exist with correct content
        patches = sorted(p.name for p in (d / "patches").iterdir())
        assert len(patches) == 2, f"Expected 2 patch files, got {len(patches)}"
        # Check patch file content matches
        patch1_content = (d / "patches" / f"{files['a/b']}.diff").read_text()
        patch2_content = (d / "patches" / f"{files['a_b']}.diff").read_text()
        assert "DIFF-ONE" in patch1_content and "DIFF-TWO" not in patch1_content
        assert "DIFF-TWO" in patch2_content and "DIFF-ONE" not in patch2_content
        # README should reference both files
        readme = (d / "README.md").read_text()
        assert files["a/b"] in readme and files["a_b"] in readme


if __name__ == "__main__":
    test_trois_findings()
    test_aucun_finding()
    test_safe_id_collision()
    print("OK")
