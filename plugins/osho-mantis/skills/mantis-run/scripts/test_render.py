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
        assert "**Résumé** : Clickjacking." in readme, "LOW has no executive_summary: README Résumé falls back to impact"
        assert "broken.json" in readme and "reproduce sauté : niveau Light" in readme
        assert "git apply osho-mantis/" in readme and ".._c1.diff" in readme
        if shutil.which("node"):
            js = Path(tmp, "check.js")
            js.write_text(re.findall(r"<script>(.*?)</script>", html, re.S)[0])
            r = subprocess.run(["node", "--check", str(js)], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr


def test_niveau_banniere_et_reproduce():
    """Level banner + reproduce-not-run tiles show '-' instead of a misleading 0."""
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [CRIT, LOW])  # fixture state.json: reproduce = "skipped", not "done"
        html, payload = data(d)
        assert payload["meta"]["reproduce_done"] is False
        assert payload["meta"]["level_banner"] == "Analyse statique : pas de reproduction, correctifs proposés non vérifiés."
        readme = (d / "README.md").read_text()
        assert "Analyse statique : pas de reproduction, correctifs proposés non vérifiés." in readme
        if shutil.which("node"):
            js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
            assert "reproduce_done" in js
    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "workspace" / "findings").mkdir(parents=True)
        (d / "campaign.json").write_text(json.dumps({"repo": "/x/demo", "level": "Sharp", "mantis_commit": "47099ed",
                                                      "started_at": "2026-10-01T14:32:00"}))
        (d / "state.json").write_text(json.dumps({"stages": {"reproduce": "done"}, "notes": []}))
        r = subprocess.run([sys.executable, str(RENDER), str(d)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        _, payload = data(d)
        assert payload["meta"]["reproduce_done"] is True
        assert payload["meta"]["level_banner"] == "Reproduction Docker des High+ et correctifs vérifiés par re-attaque."


def test_libelles_francais():
    """Enum values (status, repro_status, patch_status, ...) get a French label; README shows it, dashboard payload carries one shared table."""
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [CRIT, LOW])
        html, payload = data(d)
        readme = (d / "README.md").read_text()
        assert "Vérifié par re-attaque" in readme, "CRIT patch_status=VERIFIED_SECURE -> French label"
        assert "VERIFIED_SECURE" not in readme
        assert payload["labels"]["status"]["VALID"] == "Confirmé"
        assert payload["labels"]["patch_status"]["VERIFIED_SECURE"] == "Vérifié par re-attaque"
        assert payload["labels"]["production_viability"]["VIABLE"] == "Exploitable en prod"
        if shutil.which("node"):
            js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
            assert "D.labels" in js, "dashboard must read the labels table from the payload, not duplicate it"


def test_description_longue():
    """Problème tab: first-sentence lead line + full text under <details>."""
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [CRIT])
        html, _ = data(d)
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        m = re.search(r"function leadOf\(desc\)\s*\{.*?\n\}", js, re.S)
        assert m, "leadOf(desc) not found in dashboard JS"
        script = Path(tmp, "lead.js")
        two_sentences = "Premier point très clair. Deuxième point qui développe le contexte en long."
        no_boundary = "x" * 300
        script.write_text(m.group(0) + f"""
const assert = require('assert');
assert.strictEqual(leadOf({json.dumps(two_sentences)}), "Premier point très clair.");
assert.strictEqual(leadOf({json.dumps(no_boundary)}).length, 241);
console.log('OK');
""")
        r = subprocess.run(["node", str(script)], capture_output=True, text=True)
        assert r.returncode == 0 and "OK" in r.stdout, r.stderr + r.stdout


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


def test_safe_id_triple_collision():
    """Three findings: a/b, a_b-2, a_b (suffixed name can collide with another's unsuffixed safe_id)."""
    COL1 = {"id": "a/b", "title": "First", "severity": "CRITICAL", "status": "VALID",
            "patch_diff": "DIFF-1\n"}
    COL2 = {"id": "a_b-2", "title": "Second", "severity": "CRITICAL", "status": "VALID",
            "patch_diff": "DIFF-2\n"}
    COL3 = {"id": "a_b", "title": "Third", "severity": "CRITICAL", "status": "VALID",
            "patch_diff": "DIFF-3\n"}
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [COL1, COL2, COL3])
        html, payload = data(d)
        # All three findings should have distinct _file names
        files = {f["id"]: f["_file"] for f in payload["findings"]}
        all_files = set(files.values())
        assert len(all_files) == 3, f"Expected 3 distinct _file names, got {len(all_files)}: {files}"
        # All three patch files should exist with correct content
        patches = sorted(p.name for p in (d / "patches").iterdir())
        assert len(patches) == 3, f"Expected 3 patch files, got {len(patches)}: {patches}"
        # Check each patch file has correct content
        for finding_id, expected_diff in [("a/b", "DIFF-1"), ("a_b-2", "DIFF-2"), ("a_b", "DIFF-3")]:
            patch_content = (d / "patches" / f"{files[finding_id]}.diff").read_text()
            assert expected_diff in patch_content, f"Finding {finding_id} patch missing {expected_diff}"
            # Verify no cross-contamination
            for other_diff in ["DIFF-1", "DIFF-2", "DIFF-3"]:
                if other_diff != expected_diff:
                    assert other_diff not in patch_content, f"Finding {finding_id} patch contains unexpected {other_diff}"
        # README should reference all three files
        readme = (d / "README.md").read_text()
        for file_name in all_files:
            assert file_name in readme, f"README missing reference to {file_name}"


if __name__ == "__main__":
    test_trois_findings()
    test_niveau_banniere_et_reproduce()
    test_libelles_francais()
    test_description_longue()
    test_aucun_finding()
    test_safe_id_collision()
    test_safe_id_triple_collision()
    print("OK")
