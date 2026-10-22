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


def audit(tmp, findings, broken=False, fixes=None):
    d = Path(tmp)
    (d / "workspace" / "findings").mkdir(parents=True)
    if fixes is not None:
        (d / "fixes.json").write_text(json.dumps(fixes))
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


def test_filtre():
    """Text input hides cards whose title/code_paths/cwe don't match (case-insensitive); column counts follow."""
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [CRIT, LOW])
        html, _ = data(d)
        assert 'id="filter"' in html
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        m = re.search(r"function matches\(f, q\)\s*\{.*?\n\}", js, re.S)
        assert m, "matches(f, q) not found in dashboard JS"
        script = Path(tmp, "matches.js")
        script.write_text(m.group(0) + """
const assert = require('assert');
const f = {title: 'Injection de commande', code_paths: ['app.py:76'], cwe: 'CWE-78'};
assert.strictEqual(matches(f, ''), true);
assert.strictEqual(matches(f, 'INJECTION'), true, 'case-insensitive title match');
assert.strictEqual(matches(f, 'app.py'), true, 'code_paths match');
assert.strictEqual(matches(f, 'cwe-78'), true, 'cwe match, case-insensitive');
assert.strictEqual(matches(f, 'sqlite'), false);
console.log('OK');
""")
        r = subprocess.run(["node", str(script)], capture_output=True, text=True)
        assert r.returncode == 0 and "OK" in r.stdout, r.stderr + r.stdout


def test_lien_profond():
    """Clicking a card sets location.hash to _file; on load a matching hash opens its panel; close/Escape clears it."""
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [CRIT, LOW])
        html, _ = data(d)
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        m = re.search(r"function findingForHash\(findings, hash\)\s*\{.*?\n\}", js, re.S)
        assert m, "findingForHash(findings, hash) not found in dashboard JS"
        assert "location.hash = f._file" in js, "card click must set the deep link"
        assert "hashchange" in js, "a hash set by another tab/back-nav must open its panel"
        assert "history.replaceState" in js, "closing/Escape must clear the hash without a new history entry"
        script = Path(tmp, "hash.js")
        script.write_text(m.group(0) + """
const assert = require('assert');
const findings = [{_file: 'c1', title: 'A'}, {_file: 'c2', title: 'B'}];
assert.strictEqual(findingForHash(findings, '#c2').title, 'B');
assert.strictEqual(findingForHash(findings, ''), null);
assert.strictEqual(findingForHash(findings, '#nope'), null);
console.log('OK');
""")
        r = subprocess.run(["node", str(script)], capture_output=True, text=True)
        assert r.returncode == 0 and "OK" in r.stdout, r.stderr + r.stdout


def test_themes_horizon():
    """Gabarit Horizon : jetons sombre et clair, aucun innerHTML, aucun tiret cadratin, identifiants DOM attendus."""
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [CRIT, LOW])
        html, _ = data(d)
        for token in ("--bg:#0b0d14", "--bg:#eff1f5", "--primary:#7ea6ff", "--primary:#0050d7", "data-theme"):
            assert token in html, token
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        assert "innerHTML" not in js, "texte des findings via textContent / el() uniquement"
        assert "\u2014" not in RENDER.with_name("dashboard.html").read_text(), "aucun tiret cadratin dans le gabarit"
        for i in ("topbar", "conn", "theme-toggle", "banner", "kpis", "waiting-banner", "pipeline", "filter",
                  "kb-view-toggle", "board", "actions", "activity", "peek", "live-region"):
            assert f'id="{i}"' in html, i
        assert html.count('class="kpi"') == 4
        assert re.search(r'id="peek"[^>]*role="dialog"[^>]*aria-modal="true"', html)
        assert re.search(r'id="live-region"[^>]*aria-live="polite"', html)
        assert 'data-view="severity"' in html


def fn(js, name):
    m = re.search(r"function " + name + r"\(.*?\)\s*\{.*?\n\}", js, re.S)
    assert m, f"{name} not found in dashboard JS"
    return m.group(0)


def node_ok(tmp, code):
    script = Path(tmp, "t.js")
    script.write_text(code + "\nconsole.log('OK');\n")
    r = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr + r.stdout


def test_frise_etapes():
    """trail() ne coche que les étapes prouvées par les champs : un correctif proposé ne vaut ni critic ni reproduction."""
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        prog = re.search(r"const PROG = \[.*?\];", js, re.S).group(0)
        node_ok(tmp, prog + fn(js, "trail") + """
const assert = require('assert');
function el(tag, attrs, ...kids) { return {cls: (attrs || {}).class || '', kids, append(...k) { this.kids.push(...k); }}; }
const D = {progress_columns: ['found', 'reviewed', 'evaluated', 'reproduced', 'proposed', 'fixed']};
const steps = f => Object.fromEntries(trail(f).kids.map(k => [k.kids[0], k.cls === 'y']));
assert.deepStrictEqual(steps({reasoning: 'x', patch_status: 'MITIGATION_PROPOSED', _progress: 'proposed', _bucket: 'CRITICAL'}),
  {'Trouvé': true, 'Revu': true, 'Évalué': false, 'Reproduit': false, 'Correctif proposé': true, 'Corrigé': false});
assert.strictEqual(steps({patch_status: 'MITIGATION_PROPOSED', _fix: {status: 'merged'}, _progress: 'fixed', _bucket: 'CRITICAL'})['Corrigé'], true);
""")


def test_pas_encore_evalue():
    """Audit en direct : une propriété dont l'étape est au niveau mais pas finie est « pas encore évalué »."""
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        consts = "".join(re.search(r"const " + c + r" = .*?;\n", js, re.S).group(0) for c in ("NA", "PENDING", "PRODUCER"))
        node_ok(tmp, consts + fn(js, "naText") + """
const assert = require('assert');
let D = {mode: 'live', meta: {finished: false, stopped: false},
         stages: [{key: 'critic', status: 'running'}, {key: 'reproduce', status: 'pending'}, {key: 'patch', status: 'done'},
                  {key: 'calibrate', status: 'skipped'}]};
assert.strictEqual(naText('production_viability'), 'pas encore évalué');
assert.strictEqual(naText('repro_output'), 'pas encore évalué');
assert.strictEqual(naText('patch_status'), 'non évalué à ce niveau', 'étape finie');
assert.strictEqual(naText('mantis_risk_score'), 'non évalué à ce niveau', 'étape sautée');
assert.strictEqual(naText('cwe'), 'non évalué à ce niveau', 'aucune étape productrice');
D.stages = [{key: 'patch', status: 'pending'}];
assert.strictEqual(naText('repro_status'), 'non évalué à ce niveau', 'reproduce absent du niveau');
D.meta.finished = true;
assert.strictEqual(naText('patch_status'), 'non évalué à ce niveau', 'audit terminé');
D = {mode: 'final', meta: {}, stages: [{key: 'patch', status: 'pending'}]};
assert.strictEqual(naText('patch_status'), 'non évalué à ce niveau', 'fichier final');
""")

def test_conn_label():
    """Indicateur de connexion : en direct < 15 s, reconnexion < 60 s, hors ligne sinon ou en mode final."""
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        node_ok(tmp, fn(js, "pad") + fn(js, "hhmm") + fn(js, "connLabel") + """
const assert = require('assert');
assert.ok(connLabel(3, 'live').startsWith('En direct'), connLabel(3, 'live'));
assert.strictEqual(connLabel(3, 'live'), 'En direct, mis à jour il y a 3 s');
assert.strictEqual(connLabel(30, 'live'), 'Reconnexion…');
assert.ok(connLabel(90, 'live').startsWith('Hors ligne'));
assert.ok(connLabel(0, 'final').startsWith('Hors ligne'));
assert.ok(/^Hors ligne, données du \\d\\d:\\d\\d$/.test(connLabel(0, 'final')), connLabel(0, 'final'));
""")


def test_final_sans_eventsource():
    """Le fichier final n'ouvre pas de flux : new EventSource est conditionné à D.mode === 'live'."""
    with tempfile.TemporaryDirectory() as tmp:
        html, payload = data(audit(tmp, [CRIT]))
        assert payload["mode"] == "final"
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        assert js.count("new EventSource") == 1
        assert re.search(r"if \(D\.mode === ['\"]live['\"]\) \{[^}]*new EventSource", js), "EventSource non conditionné"


def test_carte_option():
    """Carte de choix : puce Recommandé et coût en lignes ; ancien waiting.json (sans summary) : label et description."""
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        node_ok(tmp, fn(js, "optionBody") + """
const assert = require('assert');
function el(tag, attrs, ...kids) { return {tag, cls: (attrs || {}).class || '', kids: kids.filter(k => k != null)}; }
const txt = n => n == null ? '' : typeof n === 'string' ? n : n.kids.map(txt).join('|');
const find = (n, c) => !n || typeof n === 'string' ? null : n.cls === c ? n : n.kids.map(k => find(k, c)).find(Boolean) || null;
let r = optionBody({value: 'Light', label: 'Light (Recommandé)', summary: 'Statique : plan', recommended: true,
  cost: 'Pro : ~1,0 fenêtres · Max 5x : ~20 %', description: 'x'});
const root = {kids: r.kids};
assert.strictEqual(r.rec, true);
assert.strictEqual(txt(find(root, 'nm')), 'Light');
assert.strictEqual(txt(find(root, 'rec-chip')), 'Recommandé');
assert.strictEqual(txt(find(root, 'sum')), 'Statique : plan');
assert.strictEqual(txt(find(root, 'cost')), 'Pro|~1,0 fenêtres|Max 5x|~20 %');
r = optionBody({value: 'Sharp', label: 'Sharp', summary: 's', cost: 'c', recommended: false});
assert.strictEqual(r.rec, false);
assert.strictEqual(find({kids: r.kids}, 'rec-chip'), null);
assert.strictEqual(find({kids: r.kids}, 'cost raw').kids[0], 'c');
r = optionBody({value: 'Light', label: 'Light (Recommandé)', description: 'Statique : a : Pro : ~1'});
assert.strictEqual(r.rec, true, 'ancien format : (Recommandé) dans le label');
assert.strictEqual(txt(find({kids: r.kids}, 'nm')), 'Light');
assert.strictEqual(txt(find({kids: r.kids}, 'sum')), 'Statique : a : Pro : ~1');
assert.strictEqual(find({kids: r.kids}, 'cost'), null);
r = optionBody({value: 'oui', label: 'Oui'});
assert.strictEqual(txt(find({kids: r.kids}, 'nm')), 'Oui');
assert.strictEqual(r.rec, false);
""")


def test_pipeline_hooks():
    """Sélecteur de vue du pipeline : deux boutons-icônes avec aria-pressed."""
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        for i in ("view-reseau", "view-matrice"):
            assert re.search(r'id="' + i + r'"[^>]*aria-pressed=', html), i
        assert 'aria-label="Vue réseau"' in html and 'aria-label="Vue matrice"' in html


def test_stage_view():
    """stageView : « reseau » par défaut et pour toute valeur inconnue."""
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        node_ok(tmp, fn(js, "stageView") + """
const assert = require('assert');
assert.strictEqual(stageView(null), 'reseau');
assert.strictEqual(stageView('matrice'), 'matrice');
assert.strictEqual(stageView('x'), 'reseau');
""")


def test_reduced_motion():
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        assert "prefers-reduced-motion" in html


def test_readme_corrections_fusionnees():
    fixes = {"f0": {"status": "merged", "commit": "a" * 40, "merge_commit": "b" * 40}}
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [CRIT, LOW], fixes=fixes)
        readme = (d / "README.md").read_text()
        assert "## Corrections fusionnées" in readme
        assert "1 correctif sur la branche" in readme and "git merge mantis/" in readme
        assert "(`bbbbbbb`)" in readme
        assert readme.index("## Corrections fusionnées") < readme.index("## Limites")


def test_readme_sans_correction():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [CRIT, LOW])
        assert "Corrections fusionnées" not in (d / "README.md").read_text()


def test_readme_corrections_hostile():
    hostile = dict(LOW, id="h1", title="<img src=x onerror=alert(1)>")
    fixes = {"f0": {"status": "merged", "commit": "a" * 40, "merge_commit": "b" * 40}}
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [hostile], fixes=fixes)
        readme = (d / "README.md").read_text()
        assert "&lt;img" in readme and "<img src=x" not in readme


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


def test_question_texte():
    """La bannière d'attente affiche w.text (phrase) plutôt que w.question (identifiant)."""
    triage = RENDER.parents[2] / "mantis-triage" / "SKILL.md"
    assert '"text": "Quel niveau d\'audit ?"' in triage.read_text()
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        assert "waitText(w)" in fn(js, "renderWaiting")
        node_ok(tmp, fn(js, "waitText") + """
const assert = require('assert');
assert.strictEqual(waitText({question: 'volume', text: "Quel niveau d'audit ?"}), "Quel niveau d'audit ?");
assert.strictEqual(waitText({question: 'Q ?'}), 'Q ?');
""")


def test_cles_stables():
    """Fiche ouverte et cartes déjà vues suivies par _src (stable) ; l'ancre d'URL reste _file."""
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        assert "ui.peek = f._src" in js and "seenFiles = new Set(D.findings.map(f => f._src))" in js
        assert "x._file === ui.peek" not in js and "location.hash = f._file" in js


def test_cmd_text():
    """Tuile Actions : la cible est nommée (« Relance de Plan », « Faux positif <titre> »)."""
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        label = re.search(r"const ACT_LABEL = \{.*?\};", js, re.S).group(0)
        node_ok(tmp, label + fn(js, "cmdText") + """
const assert = require('assert');
const D = {stages: [{key: 'plan', name: 'Plan'}], findings: [{_src: 'f1', title: 'Injection'}]};
assert.strictEqual(cmdText({action: 'retry', stage: 'plan'}), 'Relance de Plan');
assert.strictEqual(cmdText({action: 'false_positive', finding: 'f1'}), 'Faux positif Injection');
assert.strictEqual(cmdText({action: 'false_positive', finding: 'zz'}), 'Faux positif zz');
assert.strictEqual(cmdText({action: 'pause'}), 'Pause');
""")



def test_etat_commande():
    """Retour d'action à côté du bouton : Envoyé tant que l'id n'est pas acquitté, puis Appliqué ou Refusé ;
    le bouton reste bloqué (inflight) jusqu'à ce qu'un snapshot montre l'id ; une réponse envoyée bloque
    toutes les options de la question jusqu'à la levée de l'attente."""
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        node_ok(tmp, "const inflight = new Set(), sent = new Map();" + "".join(
            fn(js, n) for n in ("cmdKey", "cmdState", "blocked", "settleSent")) + """
const assert = require('assert');
const fp = JSON.stringify({action: 'false_positive', finding: 'f1'});
let D = {commands: {pending: [], done: []}, waiting: null};
inflight.add(fp); sent.set(fp, 'abc');
assert.strictEqual(cmdState(fp).t, 'Envoyé, pris en compte à la fin du lot en cours');
assert.ok(blocked({action: 'false_positive', finding: 'f1'}));
settleSent(); assert.ok(inflight.has(fp)); // POST résolu, snapshot pas encore arrivé : toujours bloqué
D = {commands: {pending: [{action: 'false_positive', finding: 'f1', id: 'abc', at: 't', source: 'page'}], done: []}, waiting: null};
settleSent(); assert.ok(!inflight.has(fp) && blocked({action: 'false_positive', finding: 'f1'}));
D = {commands: {pending: [], done: [{id: 'abc', result: 'applied'}]}, waiting: null};
assert.strictEqual(cmdState(fp).t, 'Appliqué'); assert.ok(!blocked({action: 'false_positive', finding: 'f1'}));
D = {commands: {pending: [], done: [{id: 'abc', result: 'refused', reason: 'non'}]}, waiting: null};
assert.strictEqual(cmdState(fp).t, 'Refusé : non');
// commande en file connue seulement du serveur (page rechargée) : bloquée aussi
inflight.clear(); sent.clear();
D = {commands: {pending: [{action: 'pause', id: 'p1', at: 't', source: 'page'}], done: []}, waiting: null};
assert.ok(blocked({action: 'pause'}) && !blocked({action: 'stop'}));
// question : une réponse envoyée bloque toutes les options, jusqu'à la levée de l'attente
const w = {kind: 'question', question: 'volume', options: [{value: 'Light'}, {value: 'Sharp'}]};
const a = JSON.stringify({action: 'answer', question: 'volume', value: 'Light'});
sent.set(a, 'q1');
D = {commands: {pending: [{action: 'answer', question: 'volume', value: 'Light', id: 'q1'}], done: []}, waiting: w};
assert.ok(blocked({action: 'answer', question: 'volume', value: 'Sharp'}));
D = {commands: {pending: [], done: [{id: 'q1', result: 'applied'}]}, waiting: w};
assert.ok(blocked({action: 'answer', question: 'volume', value: 'Sharp'}));
D = {commands: {pending: [], done: [{id: 'q1', result: 'applied'}]}, waiting: null};
settleSent(); assert.ok(!sent.has(a));
""")


def test_fix_view():
    """fixView() : état de correction d'une carte, en texte et en bouton (Corriger, Merger, Recorriger)."""
    if not shutil.which("node"):
        return
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        js = re.findall(r"<script>(.*?)</script>", html, re.S)[0]
        label = re.search(r"const FIX_LABEL = \{.*?\};", js, re.S).group(0)
        node_ok(tmp, label + fn(js, "fixView") + """
const assert = require('assert');
const v = (st, extra) => fixView({_bucket: 'HIGH', _fix: st ? Object.assign({status: st}, extra) : null}, 'live');
assert.strictEqual(fixView({_bucket: 'HIGH'}, 'final'), null);
assert.strictEqual(fixView({_bucket: 'REJECTED'}, 'live'), null);
assert.strictEqual(v('merged'), null);
assert.deepStrictEqual([v(null).action, v(null).label], ['fix', 'Corriger']);
assert.deepStrictEqual([v('failed', {error: 'tests rouges'}).text, v('failed').action, v('failed').label], ['Échec : tests rouges', 'fix', 'Corriger']);
assert.strictEqual(v('failed').text, 'Échec : raison inconnue');
assert.deepStrictEqual([v('queued').text, v('queued').action], ['En file…', undefined]);
assert.deepStrictEqual([v('running').text, v('running').cls, v('running').action], ['Correction en cours', 'loading', undefined]);
assert.deepStrictEqual([v('ready').action, v('ready').label, v('ready').cls], ['merge_fix', 'Merger', 'pri']);
assert.deepStrictEqual([v('conflict').text, v('conflict').action, v('conflict').label], ['Conflit avec un autre correctif', 'fix', 'Recorriger']);
assert.strictEqual(FIX_LABEL.merged, 'Corrigée');
""")


def test_fix_hooks():
    """Bannière de branche, mode Corrections et grisage de Merger présents ; ni innerHTML ni tiret cadratin."""
    with tempfile.TemporaryDirectory() as tmp:
        html, _ = data(audit(tmp, [CRIT]))
        for s in ('id="fix-branch"', 'id="copy-merge"', "Correctif proposé", "Claude attend tes demandes de correction",
                  "cmd.action !== 'merge_fix'"):
            assert s in html, s
        assert "innerHTML" not in html and "\u2014" not in html


if __name__ == "__main__":
    test_trois_findings()
    test_niveau_banniere_et_reproduce()
    test_libelles_francais()
    test_description_longue()
    test_filtre()
    test_lien_profond()
    test_themes_horizon()
    test_frise_etapes()
    test_pas_encore_evalue()
    test_conn_label()
    test_final_sans_eventsource()
    test_pipeline_hooks()
    test_stage_view()
    test_reduced_motion()
    test_aucun_finding()
    test_safe_id_collision()
    test_safe_id_triple_collision()
    test_question_texte()
    test_cles_stables()
    test_cmd_text()
    test_etat_commande()
    test_carte_option()
    test_readme_corrections_fusionnees()
    test_readme_sans_correction()
    test_readme_corrections_hostile()
    test_fix_view()
    test_fix_hooks()
    print("OK")
