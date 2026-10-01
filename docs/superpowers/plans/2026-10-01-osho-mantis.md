# osho-mantis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un plugin Claude Code `osho-mantis` qui fait un triage court d'un repo, puis lance une campagne Mantis au niveau choisi (Light → Overkill) avec l'abonnement Claude Code, et écrit rapport, patchs suggérés et dashboard dans `<repo>/osho-mantis/audit-<date>_<heure>/`.

**Architecture:** Deux skills Markdown (`mantis-triage`, `mantis-run`) orchestrent des sous-agents Claude Code qui lisent chacun un `SKILL.md` de Mantis, cloné dans `~/.local/share/mantis`. Tout ce qui est déterministe est confié à trois scripts sans dépendance : visibilité du repo, inventaire avec estimations, et rendu (README, patchs, dashboard). Les scripts ne consomment aucun token et sont testés.

**Tech Stack:** Bash, Python 3 (stdlib uniquement), HTML/CSS/JS inline (sans framework), skills et plugins Claude Code.

**Spec:** `docs/superpowers/specs/2026-10-01-osho-mantis-design.md`

## Global Constraints

- Mantis est référencé (`~/.local/share/mantis`, `git clone`/`git pull --ff-only` de `https://github.com/google/mantis`), jamais copié dans ce repo.
- Scripts : Python 3 stdlib uniquement, Bash portable macOS (`/bin/bash` 3.2, sed BSD). Aucune dépendance à installer.
- Dossier d'audit : `<repo>/osho-mantis/audit-$(date +%Y-%m-%d_%Hh%M)/`, versionné par défaut ; non versionné → `osho-mantis/` dans `.git/info/exclude`.
- Niveaux, exactement : `Light`, `Sharp`, `Savage`, `Overkill` ; parallélisme 2 / 3 / 4 / 6 ; hypothèses 5 / 10 / 20 / tous les fichiers source.
- Textes destinés à l'utilisateur (rapport, dashboard, questions) en français ; instructions des SKILL.md en anglais, comme `repo-init`.
- Le dashboard ne charge aucune ressource externe.
- Les skills ne commitent jamais dans le repo cible et ne le modifient jamais hors `osho-mantis/`.
- Chemins de scripts dans les SKILL.md : `${CLAUDE_PLUGIN_ROOT}/skills/<skill>/scripts/…` (convention `repo-init`).

## Review Focus

- Un finding contient du HTML ou `</script>` (texte écrit par un LLM à partir de code hostile) → le dashboard et le README l'affichent comme du texte, sans l'exécuter. Testé dans Task 3.
- Un finding sans champs optionnels, un fichier JSON illisible ou un `id` du type `../x` → aucun plantage ; « non évalué à ce niveau » ; le patch est écrit dans `patches/` et pas ailleurs. Testé dans Task 3.
- Un audit sans aucun finding → README et dashboard affichent clairement « Aucun finding ». Testé dans Task 3.
- Des audits précédents sont versionnés dans `osho-mantis/` (avec des exploits) → ils ne doivent pas compter comme surface d'attaque du repo. Testé dans Task 2.
- Remote SSH `git@github.com:…`, remote hors GitHub, `gh` absent → visibilité correcte ou `unknown`, jamais `private` par erreur. Testé dans Task 1.

---

### Task 1: Plugin scaffold + `check-visibility.sh`

**Files:**
- Create: `plugins/osho-mantis/.claude-plugin/plugin.json`
- Create: `plugins/osho-mantis/skills/mantis-triage/scripts/check-visibility.sh`
- Create: `plugins/osho-mantis/skills/mantis-triage/scripts/test_check_visibility.sh`
- Modify: `.claude-plugin/marketplace.json`

**Interfaces:**
- Produces: `check-visibility.sh [repo]` → affiche exactement une ligne parmi `local`, `private`, `public`, `unknown` ; code retour 0 ; repo par défaut = dossier courant.

- [ ] **Step 1: Create the branch**

```bash
cd ~/dev/OshO-Skillz && git checkout -b feat/osho-mantis
```

- [ ] **Step 2: Write the failing test**

`plugins/osho-mantis/skills/mantis-triage/scripts/test_check_visibility.sh`:

```bash
#!/usr/bin/env bash
# Auto-test de check-visibility.sh avec un faux gh dans le PATH
#   bash test_check_visibility.sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
script="$here/check-visibility.sh"
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
mkdir -p "$t/bin" "$t/mon repo"
cat >"$t/bin/gh" <<'EOF'
#!/bin/sh
[ "$3" = "owner/repo" ] || exit 1
echo "$FAKE_VIS"
EOF
chmod +x "$t/bin/gh"
with_gh="$t/bin:/usr/bin:/bin"
without_gh="/usr/bin:/bin"

check() { # check <PATH> <attendu> [visibilité renvoyée par le faux gh]
  out=$(env PATH="$1" FAKE_VIS="${3:-}" bash "$script" "$t/mon repo")
  [ "$out" = "$2" ] || { echo "FAIL: attendu $2, obtenu '$out' (gh=${3:-absent})"; exit 1; }
}

git -C "$t/mon repo" init -q
check "$with_gh" local
git -C "$t/mon repo" remote add origin git@github.com:owner/repo.git
check "$with_gh" public PUBLIC
check "$with_gh" private PRIVATE
check "$with_gh" private INTERNAL
check "$with_gh" unknown ""
check "$without_gh" unknown
git -C "$t/mon repo" remote set-url origin https://github.com/owner/repo
check "$with_gh" public PUBLIC
git -C "$t/mon repo" remote set-url origin https://gitlab.com/owner/repo.git
check "$with_gh" unknown PUBLIC
echo OK
```

- [ ] **Step 3: Run it to verify it fails**

Run: `bash plugins/osho-mantis/skills/mantis-triage/scripts/test_check_visibility.sh`
Expected: FAIL (`check-visibility.sh` absent, `bash: …/check-visibility.sh: No such file or directory`).

- [ ] **Step 4: Write `check-visibility.sh`**

```bash
#!/usr/bin/env bash
# Visibilité du repo git pour osho-mantis : local | private | public | unknown
#   bash check-visibility.sh [repo]
set -u
repo="${1:-.}"
remote=$(git -C "$repo" remote 2>/dev/null | head -n 1)
[ -n "$remote" ] || { echo local; exit 0; }
url=$(git -C "$repo" remote get-url "$remote")
case "$url" in
  *github.com[:/]*) ;;
  *) echo unknown; exit 0 ;;
esac
command -v gh >/dev/null 2>&1 || { echo unknown; exit 0; }
slug=$(printf '%s\n' "$url" | sed -E 's#^.*github\.com[:/]##; s#\.git$##')
vis=$(gh repo view "$slug" --json visibility -q .visibility 2>/dev/null) || { echo unknown; exit 0; }
case "$vis" in
  PUBLIC) echo public ;;
  PRIVATE|INTERNAL) echo private ;;
  *) echo unknown ;;
esac
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `bash plugins/osho-mantis/skills/mantis-triage/scripts/test_check_visibility.sh`
Expected: `OK`

- [ ] **Step 6: Plugin manifest + marketplace entry**

`plugins/osho-mantis/.claude-plugin/plugin.json`:

```json
{
  "name": "osho-mantis",
  "version": "0.1.0",
  "description": "Mantis security audits from Claude Code, no API key: quick triage, Light→Overkill campaign, French report, suggested patches and HTML dashboard.",
  "author": { "name": "OshOEz" },
  "repository": "https://github.com/OshOEz/OshO-Skillz",
  "license": "MIT"
}
```

In `.claude-plugin/marketplace.json`, append to `plugins` (after the `osho-core` object, with a comma):

```json
    {
      "name": "osho-mantis",
      "source": "./plugins/osho-mantis",
      "description": "Mantis security audits from Claude Code, no API key: quick triage, Light→Overkill campaign, French report, suggested patches and HTML dashboard."
    }
```

Run: `python3 -m json.tool .claude-plugin/marketplace.json >/dev/null && python3 -m json.tool plugins/osho-mantis/.claude-plugin/plugin.json >/dev/null && echo valid`
Expected: `valid`

- [ ] **Step 7: Commit**

```bash
chmod +x plugins/osho-mantis/skills/mantis-triage/scripts/*.sh
git add .claude-plugin/marketplace.json plugins/osho-mantis
git commit -m "osho-mantis: plugin scaffold and repo visibility check"
```

---

### Task 2: `inventory.py` (inventaire + estimations)

**Files:**
- Create: `plugins/osho-mantis/skills/mantis-triage/scripts/inventory.py`
- Test: `plugins/osho-mantis/skills/mantis-triage/scripts/test_inventory.py`

**Interfaces:**
- Produces: `python3 inventory.py <repo> <sortie.json>`. Code retour 2 et message sur stderr si `<repo>` n'est pas un repo git. Écrit un JSON avec :
  - `repo` (str, chemin absolu), `files` (int), `lines` (int)
  - `languages`: `{nom: {"files": int, "lines": int}}`
  - `manifests`: `[chemin]`
  - `surface`: `{type: {"count": int, "files": [chemin, …10 max]}}`, types : `http_route`, `command_exec`, `raw_sql`, `deserialization`, `file_upload`, `auth`
  - `history`: `{"commits": int, "security_commit_count": int, "security_commits": ["<hash> <sujet>", …20 max]}`
  - `repro`: `{"has_tests": bool, "has_dockerfile": bool, "docker": bool, "runsc": bool}`
  - `levels`: `{"Light"|"Sharp"|"Savage"|"Overkill": {"hypotheses": int, "parallel": int, "calls": {"haiku": int, "sonnet": int, "opus": int}, "subtitle": str}}`
  - `recommended`: un nom de niveau
- Affiche une ligne : `<files> fichiers, <lines> lignes, recommandé : <niveau>`.

- [ ] **Step 1: Write the failing test**

`plugins/osho-mantis/skills/mantis-triage/scripts/test_inventory.py`:

```python
#!/usr/bin/env python3
"""Auto-test de inventory.py sur un repo git inventé
  python3 test_inventory.py
"""
import json
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
        sortie = Path(tmp, "inventory.json")
        r = subprocess.run(OUTIL + [str(repo), str(sortie)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        inv = json.loads(sortie.read_text())
        assert inv["languages"] == {"Python": {"files": 2, "lines": 6}, "JavaScript": {"files": 1, "lines": 4}}, inv["languages"]
        assert inv["files"] == 3, "les audits versionnés dans osho-mantis/ sont exclus"
        assert inv["surface"]["http_route"] == {"count": 1, "files": ["app.py"]}
        assert inv["surface"]["command_exec"] == {"count": 1, "files": ["app.py"]}
        assert inv["history"]["commits"] == 2 and inv["history"]["security_commit_count"] == 1
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 plugins/osho-mantis/skills/mantis-triage/scripts/test_inventory.py`
Expected: FAIL, `AssertionError` with `can't open file '…/inventory.py'` in stderr.

- [ ] **Step 3: Write `inventory.py`**

```python
#!/usr/bin/env python3
"""Inventaire zéro token d'un repo git pour le triage osho-mantis
  python3 inventory.py <repo> <sortie.json>
"""
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

LANGS = {".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".ts": "TypeScript",
         ".tsx": "TypeScript", ".go": "Go", ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby", ".php": "PHP",
         ".rs": "Rust", ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".cs": "C#",
         ".swift": "Swift", ".scala": "Scala", ".sh": "Shell", ".sql": "SQL", ".tf": "Terraform",
         ".vue": "Vue", ".svelte": "Svelte"}
MANIFESTS = {"package.json", "pyproject.toml", "requirements.txt", "setup.py", "go.mod", "pom.xml", "build.gradle",
             "build.gradle.kts", "Cargo.toml", "Gemfile", "composer.json", "Dockerfile", "docker-compose.yml",
             "docker-compose.yaml"}
SKIP_DIRS = {"node_modules", "vendor", "dist", "build", ".venv", "venv", "third_party", "osho-mantis"}
SURFACE = {k: re.compile(v, re.I) for k, v in {
    "http_route": r"@(app|router|bp|blueprint)\.(route|get|post|put|delete|patch)\b|\b(app|router)\.(get|post|put|delete|patch|use)\(|@(Get|Post|Put|Delete|Request)Mapping|\bdo_(GET|POST|PUT|DELETE)\b|http\.HandleFunc",
    "command_exec": r"\bsubprocess\.|os\.system\(|os\.popen\(|child_process|\bexecSync\(|Runtime\.getRuntime\(\)\.exec|exec\.Command\(|shell=True",
    "raw_sql": r"\.execute\(\s*f?[\"'].*\b(select|insert|update|delete)\b|\.raw\(|\bquery\(\s*[\"'`].*\+",
    "deserialization": r"pickle\.loads?\(|yaml\.load\(|marshal\.loads\(|ObjectInputStream|unserialize\(|\beval\(",
    "file_upload": r"multipart|request\.files|\bupload",
    "auth": r"\b(password|passwd|jwt|login|authenticate|authorize|session)\b",
}.items()}
SECURITY_COMMIT = re.compile(r"cve-\d+|\b(xss|csrf|ssrf|xxe|rce|injection|sanitiz\w*|vuln\w*|security|exploit|overflow|traversal)\b", re.I)
TEST_PATH = re.compile(r"(^|/)(tests?|spec|__tests__)/|(^|/)test_[^/]+\.py$|_test\.(go|py)$|\.(test|spec)\.[jt]sx?$")
LEVELS = [("Light", 5, 2), ("Sharp", 10, 3), ("Savage", 20, 4), ("Overkill", None, 6)]
# ponytail: coût d'un appel d'agent en % d'une fenêtre Max 5x, estimé ; recalibrer après les premiers audits réels
COST = {"haiku": 0.2, "sonnet": 1.0, "opus": 3.0}
PLANS = [("Pro", 5), ("Max 5x", 1), ("Max 20x", 0.25)]


def run(repo, *args):
    r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def tracked(repo):
    out = run(repo, "ls-files", "-z")
    return [p for p in out.split("\0") if p and not SKIP_DIRS.intersection(Path(p).parts)]


def docker():
    try:
        r = subprocess.run(["docker", "info", "--format", "{{json .Runtimes}}"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False, False
    return r.returncode == 0, r.returncode == 0 and "runsc" in r.stdout


def calls(level, h):
    f = -(-h // 2)  # findings attendus : 1 pour 2 hypothèses
    c = {"haiku": 0, "sonnet": 3 + h + f, "opus": f}  # architecture, threat-model, plan, researchers, review, patch
    if level != "Light":
        c["haiku"] += 2                       # structural-index, dedupe
        c["sonnet"] += f                      # calibrate
        c["opus"] += f + -(-f // 2)           # critic, reproduce High+
    if level in ("Savage", "Overkill"):
        c["haiku"] += 1                       # history
        c["sonnet"] += 1                      # reflect
        c["opus"] += 1 + f // 2               # chain, reproduce du reste
    if level == "Overkill":
        c["sonnet"] += 2 * (2 + h // 4)       # 2 tours reflect → replan → researchers
    return c


def windows(pct):
    if pct < 100:
        return f"~{max(1, round(pct))} % d'une fenêtre"
    return f"~{pct / 100:.1f} fenêtres".replace(".", ",")


def estimate(inv):
    src = sum(l["files"] for l in inv["languages"].values()) or 1
    levels = {}
    for name, h, par in LEVELS:
        h = min(h or src, src)
        c = calls(name, h)
        pct = sum(COST[k] * n for k, n in c.items())
        levels[name] = {"hypotheses": h, "parallel": par, "calls": c,
                        "subtitle": " · ".join(f"{p} : {windows(pct * k)}" for p, k in PLANS)}
    surface = sum(s["count"] for s in inv["surface"].values())
    lines = inv["lines"]
    rec = "Light" if lines < 2000 or not surface else "Sharp" if lines < 20000 else "Savage"
    return levels, rec


def inventory(repo):
    files = tracked(repo)
    langs = defaultdict(lambda: {"files": 0, "lines": 0})
    hits, where = Counter(), defaultdict(Counter)
    total_lines = 0
    for rel in files:
        path = repo / rel
        try:
            if path.stat().st_size > 1_000_000:
                continue
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        lang = LANGS.get(path.suffix.lower())
        if not lang:
            continue
        n = text.count("\n")
        langs[lang]["files"] += 1
        langs[lang]["lines"] += n
        total_lines += n
        for line in text.splitlines():
            for kind, rx in SURFACE.items():
                if rx.search(line):
                    hits[kind] += 1
                    where[kind][rel] += 1
    log = run(repo, "log", "--format=%h %s", "-n", "5000").splitlines()
    security = [c for c in log if SECURITY_COMMIT.search(c)]
    has_docker, has_runsc = docker()
    inv = {
        "repo": str(repo),
        "files": sum(l["files"] for l in langs.values()),
        "lines": total_lines,
        "languages": dict(langs),
        "manifests": sorted(p for p in files if Path(p).name in MANIFESTS or p.endswith(".csproj")),
        "surface": {k: {"count": hits[k], "files": [p for p, _ in where[k].most_common(10)]} for k in SURFACE},
        "history": {"commits": len(log), "security_commit_count": len(security), "security_commits": security[:20]},
        "repro": {"has_tests": any(TEST_PATH.search(p) for p in files),
                  "has_dockerfile": any(Path(p).name == "Dockerfile" for p in files),
                  "docker": has_docker, "runsc": has_runsc},
    }
    inv["levels"], inv["recommended"] = estimate(inv)
    return inv


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    repo = Path(sys.argv[1]).resolve()
    if run(repo, "rev-parse", "--is-inside-work-tree").strip() != "true":
        print(f"pas un repo git : {repo}", file=sys.stderr)
        sys.exit(2)
    inv = inventory(repo)
    Path(sys.argv[2]).write_text(json.dumps(inv, ensure_ascii=False, indent=2) + "\n")
    print(f"{inv['files']} fichiers, {inv['lines']} lignes, recommandé : {inv['recommended']}")


if __name__ == "__main__":
    main()
```

Expected counts in the fixture: `app.py` has 4 lines and `tests/test_app.py` has 2 (Python = 6); `index.js` has 3 lines + 1 (JavaScript = 4). One `subprocess.` line gives `command_exec` = 1. `osho-mantis/` is excluded.

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 plugins/osho-mantis/skills/mantis-triage/scripts/test_inventory.py`
Expected: `OK`

- [ ] **Step 5: Smoke run on a real repo**

Run: `python3 plugins/osho-mantis/skills/mantis-triage/scripts/inventory.py ~/dev/mantis /tmp/inv.json && python3 -c "import json;d=json.load(open('/tmp/inv.json'));print(d['recommended'], d['levels']['Sharp']['subtitle'])"`
Expected: une ligne `… fichiers, … lignes, recommandé : …` puis un niveau et un sous-titre `Pro : … · Max 5x : … · Max 20x : …`, en moins de 10 s.

- [ ] **Step 6: Commit**

```bash
git add plugins/osho-mantis/skills/mantis-triage/scripts/inventory.py plugins/osho-mantis/skills/mantis-triage/scripts/test_inventory.py
git commit -m "osho-mantis: zero-token repo inventory with per-level quota estimates"
```

---

### Task 3: `render.py` (README.md, patches, dashboard.html)

**Files:**
- Create: `plugins/osho-mantis/skills/mantis-run/scripts/render.py`
- Test: `plugins/osho-mantis/skills/mantis-run/scripts/test_render.py`

**Interfaces:**
- Consumes (all optional, missing → defaults): `<audit>/campaign.json` (`repo`, `level`, `mantis_commit`, `started_at`, `finished_at` en ISO `YYYY-MM-DDTHH:MM:SS`), `<audit>/state.json` (`stages: {nom: "done"|"pending"|"failed"|"skipped"}`, `notes: [str]`), `<audit>/workspace/findings/*.json` (Mantis `finding` schema).
- Produces: `python3 render.py <audit>` → écrit `<audit>/README.md`, `<audit>/patches/<safe_id>.diff` (findings non écartés qui ont `patch_diff`), `<audit>/dashboard.html`. `safe_id` = `id` avec tout caractère hors `[A-Za-z0-9_.-]` remplacé par `_`. Code retour 0.
- Buckets: `REJECTED` si `status` ∈ {FALSE_POSITIVE, DUPLICATE} ou `production_viability` ∈ {NON_VIABLE, SAMPLE_OR_TEST} ; sinon `priority` puis `severity` en majuscules si ∈ {CRITICAL, HIGH, MEDIUM, LOW}, sinon LOW.
- Dans le HTML, les données sont dans `<script id="data" type="application/json">…</script>` ; chaque finding y porte `_bucket` et `_file` (safe_id).

- [ ] **Step 1: Write the failing test**

`plugins/osho-mantis/skills/mantis-run/scripts/test_render.py`:

```python
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


if __name__ == "__main__":
    test_trois_findings()
    test_aucun_finding()
    print("OK")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python3 plugins/osho-mantis/skills/mantis-run/scripts/test_render.py`
Expected: FAIL, `AssertionError` with `can't open file '…/render.py'`.

- [ ] **Step 3: Write `render.py`**

```python
#!/usr/bin/env python3
"""Rapport osho-mantis : findings Mantis → README.md, patches/<id>.diff, dashboard.html
  python3 render.py <dossier d'audit>
"""
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

BUCKETS = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
REJECTED_STATUS = {"FALSE_POSITIVE", "DUPLICATE"}
REJECTED_VIABILITY = {"NON_VIABLE", "SAMPLE_OR_TEST"}
NA = "non évalué à ce niveau"


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def load_findings(workspace):
    findings, unreadable = [], []
    for p in sorted(Path(workspace, "findings").glob("*.json")):
        f = load_json(p, None)
        if isinstance(f, dict) and f.get("title"):
            f["id"] = str(f.get("id") or p.stem)
            findings.append(f)
        else:
            unreadable.append(p.name)
    return findings, unreadable


def safe_id(f):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", f["id"])


def bucket(f):
    if f.get("status") in REJECTED_STATUS or f.get("production_viability") in REJECTED_VIABILITY:
        return "REJECTED"
    level = str(f.get("priority") or f.get("severity") or "LOW").upper()
    return level if level in BUCKETS else "LOW"


def sort_key(f):
    return (-(f.get("mantis_risk_score") or 0), str(f["title"]).lower())


def stats(findings):
    b = [bucket(f) for f in findings]
    kept = [f for f, x in zip(findings, b) if x != "REJECTED"]
    return {"by_bucket": {k: b.count(k) for k in BUCKETS + ["REJECTED"]}, "total": len(findings),
            "confirmed": sum(f.get("status") == "VALID" for f in kept),
            "reproduced": sum(f.get("repro_status") == "reproduced" for f in kept),
            "patched": sum(f.get("patch_status") == "VERIFIED_SECURE" for f in kept)}


def duration(start, end):
    try:
        minutes = int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds() // 60)
    except (TypeError, ValueError):
        return ""
    return f"{minutes // 60} h {minutes % 60:02d} min"


def text(value):
    """Valeur de finding pour du Markdown : jamais de HTML actif"""
    if value in (None, "", []):
        return NA
    value = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
    return html.escape(value, quote=False)


def cell(value):
    return text(value).replace("|", "\\|").replace("\n", " ")


def block(code, lang=""):
    longest = max((len(m) for m in re.findall(r"`+", code)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{lang}\n{code.rstrip()}\n{fence}"


def readme(meta, findings, unreadable, st):
    kept = sorted((f for f in findings if bucket(f) != "REJECTED"), key=lambda f: (BUCKETS.index(bucket(f)), sort_key(f)))
    rejected = [f for f in findings if bucket(f) == "REJECTED"]
    out = [f"# Audit de sécurité — {text(meta['repo_name'])}", "",
           f"{meta['started_at'] or '?'} · niveau **{meta['level'] or '?'}** · Mantis `{meta['mantis_commit'] or '?'}`"
           + (f" · durée {meta['duration']}" if meta["duration"] else ""), "",
           "[Ouvrir le dashboard](dashboard.html) : GitHub affiche le HTML en source, ouvrez le fichier en local.", "",
           "| Critical | High | Medium | Low | Écartés |", "|---|---|---|---|---|",
           "| " + " | ".join(str(st["by_bucket"][k]) for k in BUCKETS + ["REJECTED"]) + " |", ""]
    if not findings:
        out += ["**Aucun finding** : rien n'a été signalé à ce niveau d'audit.", ""]
    if kept:
        out += ["## Findings", "", "| Sévérité | Titre | Emplacement | Reproduit | Patch vérifié |", "|---|---|---|---|---|"]
        out += [f"| {bucket(f)} | {cell(f['title'])} | {cell(f.get('code_paths'))} | "
                f"{'oui' if f.get('repro_status') == 'reproduced' else 'non'} | "
                f"{'oui' if f.get('patch_status') == 'VERIFIED_SECURE' else 'non'} |" for f in kept]
        out.append("")
        for f in kept:
            out += [f"### [{bucket(f)}] {text(f['title'])}", "",
                    f"**Résumé** : {text(f.get('executive_summary'))}", "",
                    f"**Emplacement** : {text(f.get('code_paths'))} · **CWE** : {text(f.get('cwe'))}", "",
                    f"**Problème** : {text(f.get('description'))}", "",
                    f"**Impact** : {text(f.get('impact'))}", "",
                    f"**Cas testé** : {text(f.get('repro_status'))}"]
            for key in ("run_command", "repro_output"):
                if f.get(key):
                    out += ["", block(str(f[key]), "bash" if key == "run_command" else "")]
            out += ["", f"**Correction** ({text(f.get('patch_status'))})", ""]
            if f.get("patch_diff"):
                out += [block(str(f["patch_diff"]), "diff"), "",
                        f"Appliquer depuis la racine du repo : `git apply osho-mantis/{meta['audit_name']}/patches/{safe_id(f)}.diff`"]
            else:
                out.append(text(f.get("mitigation")))
            out.append("")
    if rejected:
        out += ["## Écartés", ""]
        out += [f"- {text(f['title'])} — {text(f.get('status') or f.get('production_viability'))} : "
                f"{text(f.get('critic_reasoning') or f.get('reasoning'))[:200]}" for f in rejected]
        out.append("")
    out += ["## Limites", ""] + [f"- {text(n)}" for n in meta["notes"]]
    if unreadable:
        out.append(f"- Fichiers de finding illisibles, ignorés : {', '.join(unreadable)}")
    out += ["- Findings produits par IA : à vérifier par un humain avant tout signalement.", ""]
    return "\n".join(out)


def safe_json(obj):
    return (json.dumps(obj, ensure_ascii=False)
            .replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e"))


def render(audit_dir):
    audit_dir = Path(audit_dir).resolve()
    campaign = load_json(audit_dir / "campaign.json", {})
    state = load_json(audit_dir / "state.json", {})
    findings, unreadable = load_findings(audit_dir / "workspace")
    meta = {"repo_name": Path(campaign.get("repo") or audit_dir.parent.parent).name,
            "audit_name": audit_dir.name, "level": campaign.get("level"),
            "mantis_commit": campaign.get("mantis_commit"), "started_at": campaign.get("started_at"),
            "duration": duration(campaign.get("started_at"), campaign.get("finished_at")),
            "notes": state.get("notes", []),
            "stages": [k for k, v in state.get("stages", {}).items() if v == "done"]}
    st = stats(findings)
    (audit_dir / "README.md").write_text(readme(meta, findings, unreadable, st))
    for f in findings:
        if f.get("patch_diff") and bucket(f) != "REJECTED":
            (audit_dir / "patches").mkdir(exist_ok=True)
            (audit_dir / "patches" / f"{safe_id(f)}.diff").write_text(str(f["patch_diff"]).rstrip("\n") + "\n")
    payload = {"meta": meta, "stats": st,
               "findings": [dict(f, _bucket=bucket(f), _file=safe_id(f)) for f in sorted(findings, key=sort_key)]}
    (audit_dir / "dashboard.html").write_text(TEMPLATE.replace("__DATA__", safe_json(payload)))


TEMPLATE = r"""<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audit Mantis</title>
<style>
:root{--bg:#f7f7f8;--card:#fff;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e6;--crit:#c62828;--high:#e65100;--med:#b58900;--low:#2e7d32;--rej:#757575;--add:#e6f4ea;--del:#fdecea}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1e1e21;--fg:#ececf0;--muted:#a0a0a8;--line:#2e2e33;--add:#12301c;--del:#3a1614}}
*{box-sizing:border-box}
body{margin:0;font:14px/1.5 -apple-system,system-ui,sans-serif;background:var(--bg);color:var(--fg)}
header,main{max-width:1400px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:0 0 4px}
main>h2{font-size:15px;margin:24px 0 8px}
.muted{color:var(--muted)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px}
.stat b{display:block;font-size:22px}
.board{display:grid;grid-template-columns:repeat(5,minmax(220px,1fr));gap:10px;overflow-x:auto}
.col{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px;min-height:80px}
.col h3{font-size:13px;margin:0 0 8px;display:flex;justify-content:space-between}
summary{cursor:pointer;list-style:none}
.card{display:block;width:100%;text-align:left;background:var(--bg);color:inherit;font:inherit;border:1px solid var(--line);border-left:4px solid var(--c);border-radius:6px;padding:8px;margin-bottom:6px;cursor:pointer}
.card:hover,.card:focus-visible{outline:2px solid var(--c)}
.badge{display:inline-block;font-size:11px;padding:0 6px;border-radius:10px;border:1px solid var(--line);margin:4px 4px 0 0}
#panel{position:fixed;top:0;right:0;height:100%;width:min(640px,100%);background:var(--card);border-left:1px solid var(--line);box-shadow:-4px 0 16px rgba(0,0,0,.15);transform:translateX(100%);transition:transform .2s;display:flex;flex-direction:column}
#panel.open{transform:none}
.phead{display:flex;justify-content:space-between;align-items:flex-start;gap:8px;padding:16px}
.phead h2{margin:0;font-size:16px}
.phead button{background:none;border:0;color:inherit;font-size:18px;cursor:pointer}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);padding:0 16px}
.tabs button{background:none;border:0;border-bottom:2px solid transparent;padding:8px;color:inherit;font:inherit;cursor:pointer}
.tabs button[aria-selected=true]{border-color:var(--fg);font-weight:600}
#content{padding:16px;overflow:auto}
dt{font-weight:600;margin-top:12px}
dd{margin:2px 0 0;white-space:pre-wrap}
pre{background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px;overflow:auto;white-space:pre-wrap;margin:4px 0}
.add{background:var(--add)}.del{background:var(--del)}
@media (max-width:700px){.board{grid-template-columns:1fr}}
</style>
</head>
<body>
<header><h1 id="title"></h1><div id="meta" class="muted"></div><div id="stages" class="muted"></div></header>
<main>
<section class="grid" id="stats"></section>
<h2>Points critiques</h2><section class="grid" id="critical"></section>
<h2>Kanban</h2><section class="board" id="board"></section>
</main>
<aside id="panel" aria-hidden="true">
<div class="phead"><h2 id="ptitle"></h2><button id="close" aria-label="Fermer">✕</button></div>
<nav class="tabs" role="tablist" id="tabs"></nav>
<div id="content"></div>
</aside>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const NA = 'non évalué à ce niveau';
const COLS = [['CRITICAL', 'Critical', '--crit'], ['HIGH', 'High', '--high'], ['MEDIUM', 'Medium', '--med'], ['LOW', 'Low', '--low'], ['REJECTED', 'Écartés', '--rej']];
const m = D.meta, s = D.stats;

function el(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === 'class') e.className = v; else if (k === 'style') e.style.cssText = v; else e.setAttribute(k, v);
  }
  for (const k of kids) e.append(k);
  return e;
}
function val(f, k) {
  const x = f[k];
  if (x == null || x === '' || (Array.isArray(x) && !x.length)) return NA;
  return Array.isArray(x) ? x.join(', ') : String(x);
}
function card(f) {
  const col = COLS.find(c => c[0] === f._bucket);
  const b = el('button', {class: 'card', style: '--c:var(' + col[2] + ')'},
    el('div', {}, el('strong', {}, String(f.title))), el('div', {class: 'muted'}, val(f, 'code_paths')));
  if (f.cwe) b.append(el('span', {class: 'badge'}, String(f.cwe)));
  if (f.repro_status === 'reproduced') b.append(el('span', {class: 'badge'}, 'reproduit'));
  if (f.patch_status === 'VERIFIED_SECURE') b.append(el('span', {class: 'badge'}, 'patch vérifié'));
  b.addEventListener('click', () => openPanel(f));
  return b;
}
function dl(f, rows) {
  const d = el('dl');
  for (const [label, k] of rows) d.append(el('dt', {}, label), el('dd', {}, val(f, k)));
  return d;
}
function pre(f, k, label) {
  return el('div', {}, el('dt', {}, label), f[k] ? el('pre', {}, String(f[k])) : el('dd', {}, NA));
}
function diff(f) {
  if (!f.patch_diff) return el('div', {}, el('dt', {}, 'Diff'), el('dd', {}, NA));
  const p = el('pre');
  for (const line of String(f.patch_diff).split('\n')) {
    const c = line.startsWith('+') && !line.startsWith('+++') ? 'add' : line.startsWith('-') && !line.startsWith('---') ? 'del' : '';
    p.append(el('div', c ? {class: c} : {}, line || ' '));
  }
  return el('div', {}, el('dt', {}, 'Diff'), p);
}
const TABS = [
  ['Résumé', f => dl(f, [['Résumé', 'executive_summary'], ['Impact', 'impact'], ["Position de l'attaquant", 'attacker_position'], ['Privilèges requis', 'privileges_required'], ['Interaction utilisateur', 'user_interaction']])],
  ['Problème', f => dl(f, [['Description', 'description'], ['Emplacement', 'code_paths'], ['CWE', 'cwe'], ['Analyse du review', 'reasoning'], ['Analyse du critic', 'critic_reasoning']])],
  ['Cas testé', f => { const d = dl(f, [['Statut', 'repro_status'], ['Script', 'repro_file_path']]); d.append(pre(f, 'run_command', 'Commande'), pre(f, 'repro_output', 'Sortie')); return d; }],
  ['Correction', f => {
    const d = dl(f, [['Statut', 'patch_status'], ['Re-attaque', 'reattack_status'], ['Mitigation', 'mitigation']]);
    d.append(diff(f));
    if (f.patch_diff && f._bucket !== 'REJECTED') d.append(el('p', {}, 'Appliquer : ', el('code', {}, 'git apply osho-mantis/' + m.audit_name + '/patches/' + f._file + '.diff')));
    return d;
  }],
];
const panel = document.getElementById('panel'), tabs = document.getElementById('tabs'), content = document.getElementById('content');
let current = null;
function show(i) {
  [...tabs.children].forEach((b, j) => b.setAttribute('aria-selected', String(i === j)));
  content.replaceChildren(TABS[i][1](current));
}
function openPanel(f) {
  current = f;
  document.getElementById('ptitle').textContent = '[' + f._bucket + '] ' + f.title;
  tabs.replaceChildren(...TABS.map(([label], i) => { const b = el('button', {role: 'tab'}, label); b.addEventListener('click', () => show(i)); return b; }));
  show(0);
  panel.classList.add('open');
  panel.setAttribute('aria-hidden', 'false');
}
function closePanel() { panel.classList.remove('open'); panel.setAttribute('aria-hidden', 'true'); }
document.getElementById('close').addEventListener('click', closePanel);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closePanel(); });

document.title = 'Audit — ' + (m.repo_name || 'repo');
document.getElementById('title').textContent = 'Audit de sécurité — ' + (m.repo_name || 'repo');
document.getElementById('meta').textContent = [m.started_at, 'niveau ' + (m.level || '?'), 'Mantis ' + (m.mantis_commit || '?'), m.duration].filter(Boolean).join(' · ');
if (m.stages.length) document.getElementById('stages').textContent = 'Étapes exécutées : ' + m.stages.join(', ');
const tiles = [['Findings', s.total], ['Critical', s.by_bucket.CRITICAL], ['High', s.by_bucket.HIGH], ['Medium', s.by_bucket.MEDIUM], ['Low', s.by_bucket.LOW], ['Confirmés', s.confirmed], ['Reproduits', s.reproduced], ['Patchs vérifiés', s.patched], ['Écartés', s.by_bucket.REJECTED]];
for (const [label, n] of tiles) document.getElementById('stats').append(el('div', {class: 'stat'}, el('b', {}, String(n)), label));
const crit = D.findings.filter(f => f._bucket === 'CRITICAL' || f._bucket === 'HIGH');
const critBox = document.getElementById('critical');
if (!crit.length) critBox.append(el('p', {class: 'muted'}, D.findings.length ? 'Aucun point Critical ou High.' : 'Aucun finding.'));
for (const f of crit) {
  const c = card(f);
  if (f.executive_summary) c.append(el('div', {}, String(f.executive_summary)));
  critBox.append(c);
}
const board = document.getElementById('board');
for (const [key, label] of COLS) {
  const items = D.findings.filter(f => f._bucket === key);
  const head = el('h3', {}, el('span', {}, label), el('span', {class: 'muted'}, String(items.length)));
  const col = key === 'REJECTED' ? el('details', {class: 'col'}, el('summary', {}, head)) : el('div', {class: 'col'}, head);
  for (const f of items) col.append(card(f));
  board.append(col);
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    render(sys.argv[1])
    print(f"README.md, dashboard.html écrits dans {Path(sys.argv[1]).resolve()}")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 plugins/osho-mantis/skills/mantis-run/scripts/test_render.py`
Expected: `OK`

- [ ] **Step 5: Visual check**

Run:
```bash
d=$(mktemp -d) && mkdir -p "$d/workspace/findings" && python3 - "$d" <<'EOF'
import json, sys
sys.path.insert(0, "plugins/osho-mantis/skills/mantis-run/scripts")
from test_render import CRIT, LOW, REJ
for i, f in enumerate([CRIT, LOW, REJ]):
    open(f"{sys.argv[1]}/workspace/findings/f{i}.json", "w").write(json.dumps(f))
EOF
python3 plugins/osho-mantis/skills/mantis-run/scripts/render.py "$d" && open "$d/dashboard.html"
```
Expected: le dashboard s'ouvre. 3 cartes, avec le titre hostile affiché en texte et aucune alerte JS. Un clic sur la carte Critical ouvre le panneau et ses 4 onglets, avec le diff coloré. La colonne « Écartés » est repliée. Échap ferme le panneau. Vérifier aussi avec la fenêtre réduite à la largeur d'un téléphone : les colonnes s'empilent.

- [ ] **Step 6: Commit**

```bash
git add plugins/osho-mantis/skills/mantis-run/scripts
git commit -m "osho-mantis: zero-token report renderer (README, patches, dashboard)"
```

---

### Task 4: Skill `mantis-triage`

**Files:**
- Create: `plugins/osho-mantis/skills/mantis-triage/SKILL.md`

**Interfaces:**
- Consumes: `check-visibility.sh` (Task 1), `inventory.py` et ses clés `levels`, `recommended` (Task 2).
- Produces: `<audit>/inventory.json`, `<audit>/triage.md`, `<audit>/campaign.json` avec, au minimum, `repo`, `focus` (liste), `out_of_scope` (liste), `recommended`, `level`, `hypotheses_max`, `parallel`, `versioning` (`versioned`|`ignored`), `visibility`, `started_at`. `mantis-run` (Task 5) lit ces clés. La « question de volume » est définie ici (étape 6) et réutilisée telle quelle par `mantis-run`.

- [ ] **Step 1: Write `SKILL.md`**

````markdown
---
name: mantis-triage
description: Quick, low-cost security triage of a git repository before a Mantis audit. Inventories the code with a script, flags the riskiest areas, recommends an audit level (Light, Sharp, Savage, Overkill) with quota estimates per Claude subscription, and prepares the osho-mantis/audit-<date> folder. Use when the user asks to audit, scan or security-review a repo with Mantis, or says "mantis triage". Don't use to run the audit itself (that is mantis-run).
---

# mantis-triage

Visibility of the current directory's repo, computed when this skill loaded: !`bash "${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts/check-visibility.sh"`

Scripts: `T="${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts"`.

## Steps

1. **Target.** The repo path the user named, else the current directory, as an absolute path `REPO`. If `git -C "$REPO" rev-parse HEAD` fails, stop and ask the user whether to `git init` and commit; the inventory reads `git ls-files`.
2. **Visibility.** If `REPO` is the current directory and the line above is exactly `local`, `private`, `public` or `unknown`, use it. Otherwise run `bash "$T/check-visibility.sh" "$REPO"`. Then:
   - `local` or `private` → `VERSIONING=versioned`, no question.
   - `public` → say: « ⚠️ Repo public : le dossier d'audit contiendra des vulnérabilités détaillées et des exploits, visibles de tous une fois poussés. » Then AskUserQuestion, header `Versionnement`, options `Non versionné (Recommandé)` / `Versionné quand même`.
   - `unknown` → AskUserQuestion, header `Versionnement`, question explaining that `gh` could not confirm whether the repo is public (gh absent, not logged in, or remote outside GitHub), options `Versionné` / `Non versionné`.
   - Non-versioned → `VERSIONING=ignored` and add the line `osho-mantis/` to `$REPO/.git/info/exclude` unless it is already there.
3. **Audit folder.** `AUDIT="$REPO/osho-mantis/audit-$(date +%Y-%m-%d_%Hh%M)"` and `mkdir -p "$AUDIT/workspace"`.
4. **Inventory (zero tokens).** `python3 "$T/inventory.py" "$REPO" "$AUDIT/inventory.json"`.
5. **Short Claude pass.** Dispatch one Agent (`subagent_type: general-purpose`, `model: sonnet`) with the prompt below (fill `<REPO>` and `<AUDIT>`), and wait for it.
6. **Volume question.** AskUserQuestion, header `Volume`, question `Quel niveau d'audit ?`, four options in this order. Label = level name, plus ` (Recommandé)` on `recommended` from `campaign.json`. Description = the line below + ` — ` + `levels.<level>.subtitle` from `inventory.json`:
   - `Light` : Statique : architecture, threat model, plan, recherche, review, diffs non vérifiés.
   - `Sharp` : + critic, reproduction Docker (High+), patchs vérifiés, calibrage.
   - `Savage` : + historique git, reproduction de tout le viable, chaînes d'exploits.
   - `Overkill` : + chaque fichier source, 2 tours de replanification.
7. **campaign.json.** Merge into the file the agent wrote: `level`, `hypotheses_max` and `parallel` (from `levels.<level>` in `inventory.json`), `versioning`, `visibility`, `repo` (`REPO`), `started_at` (`date +%Y-%m-%dT%H:%M:%S`).
8. **Report**, 4 lines max: audit folder, top 3 risks from `triage.md`, chosen level, then « Lancer `/mantis-run` ? ».

## Agent prompt

```
You are triaging the git repository at <REPO> before a security audit.
Read <AUDIT>/inventory.json, the repo README if any, and at most 20 key source files
(entry points and the files listed under "surface"). Modify nothing outside <AUDIT>.
Write two files:
1. <AUDIT>/triage.md, in French, 60 lines max:
   ## Stack
   ## Zones à risque   (top 5, each with file:line and one line on why)
   ## Hors périmètre   (generated, vendored, test-only code)
   ## Recommandation   (start from "recommended" in inventory.json; change it only with a one-line reason;
                        then a table of the 4 levels with their "subtitle")
2. <AUDIT>/campaign.json:
   {"repo": "<REPO>", "focus": [up to 10 short hypotheses in English for the Mantis planner, most likely first],
    "out_of_scope": [paths], "recommended": "<Light|Sharp|Savage|Overkill>"}
Reply in 3 lines: stack, top risk, recommended level.
```

## Notes

- Cost: one Sonnet subagent, about 2 to 5 % of a Max 5x window, 1 to 3 minutes.
- The subtitles are order-of-magnitude estimates; say so if the user asks.
````

- [ ] **Step 2: Check the `!` injection**

Run (from the plugin repo): `claude --plugin-dir plugins/osho-mantis -p "Quote verbatim the line of your mantis-triage skill that starts with 'Visibility of the current directory' — invoke the skill, do nothing else."`
Expected: the line ends in `private` (OshO-Skillz is private) or `public`. It must not end in the literal `!`bash …``. If the injection does not run, keep the line anyway (step 2 of the skill falls back to Bash), and record it in the Task 6 notes.

- [ ] **Step 3: Commit**

```bash
git add plugins/osho-mantis/skills/mantis-triage/SKILL.md
git commit -m "osho-mantis: mantis-triage skill"
```

---

### Task 5: Skill `mantis-run`

**Files:**
- Create: `plugins/osho-mantis/skills/mantis-run/SKILL.md`

**Interfaces:**
- Consumes: `campaign.json` (Task 4 keys), `check-visibility.sh` (Task 1), `render.py` (Task 3), Mantis `SKILL.md` files under `~/.local/share/mantis/mantis-<stage>/`.
- Produces: `<audit>/state.json` = `{"stages": {nom: "pending"|"done"|"failed"|"skipped"}, "round": int, "notes": [str], "git_status_before": str, "finished": bool}`, with `campaign.json.mantis_commit` / `finished_at`. Then, through `render.py`: `README.md`, `patches/`, `dashboard.html`.

- [ ] **Step 1: Write `SKILL.md`**

````markdown
---
name: mantis-run
description: Runs a Mantis security audit campaign on a git repository from Claude Code, with no Google or API key. Each Mantis stage runs as a Claude Code subagent at the level chosen in triage (Light, Sharp, Savage, Overkill), then a French report, suggested patches and an HTML dashboard are written into osho-mantis/audit-<date>/. Use after mantis-triage, when the user says "lance l'audit" or "mantis run", or wants to resume an interrupted audit. Don't use for the quick triage (mantis-triage).
---

# mantis-run

Visibility of the current directory's repo, computed when this skill loaded: !`bash "${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts/check-visibility.sh"`

Paths: `T="${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts"`, `R="${CLAUDE_PLUGIN_ROOT}/skills/mantis-run/scripts"`, `M="$HOME/.local/share/mantis"`.

## 1. Select the audit

- An audit folder was named → `AUDIT` is that folder, and `REPO` is the `repo` field of its campaign.json.
- Otherwise `REPO` is the named repo or the current directory, and `AUDIT` is the newest `$REPO/osho-mantis/audit-*` whose `state.json` does not contain `"finished": true`.
- No such folder → invoke the `mantis-triage` skill first, then continue with the audit folder it created.
- `campaign.json` has no `level` → ask the volume question exactly as in mantis-triage step 6, then fill `level`, `hypotheses_max`, `parallel`.
- `campaign.json` has no `versioning` → apply mantis-triage step 2 (the visibility line above, or the script).

## 2. Prepare

1. Mantis source: `if [ -d "$M/.git" ]; then git -C "$M" pull --ff-only -q; else git clone -q https://github.com/google/mantis "$M"; fi`. If the pull fails (for example when offline), continue with the local copy and add a note. Write `git -C "$M" rev-parse --short HEAD` into `campaign.json` as `mantis_commit`.
2. No `state.json` yet → write it with `stages` set to every stage of the level (table below) as `"pending"`, `round: 1`, `notes: []`, `finished: false`, and `git_status_before` set to the output of `git -C "$REPO" status --porcelain -- . ':(exclude)osho-mantis'`.
3. If the level includes reproduce and `docker info` fails → set reproduce to `"skipped"` and add the note « reproduce sauté : Docker indisponible ».
4. Shadow copy: `rsync -a --delete --exclude .git --exclude osho-mantis "$REPO/" "$AUDIT/workspace/shadow/"`.

## 3. Stages

Run the stages in this order, skipping those that are not in the level or are already `done`. Before each stage, set it to `"pending"`. After it, run the check, then set it to `"done"`.

| Stage | Mantis dir | Model | Levels | Scope | Check after |
|---|---|---|---|---|---|
| history | mantis-history | haiku | Savage, Overkill | whole repo | `workspace/historical_learnings.jsonl` exists |
| structural-index | mantis-structural-index | haiku | Sharp+ | whole repo | `workspace/kb/structural_index/` exists |
| architecture | mantis-architecture | sonnet | all | whole repo | `workspace/kb/` has a `.md` file |
| threat-model | mantis-threat-model | sonnet | all | whole repo | `workspace/kb/THREAT_MODEL.md` exists |
| plan | mantis-plan | sonnet | all | whole repo | `workspace/plan.json` has 1 to `hypotheses_max` investigations |
| researcher | mantis-researcher | sonnet | all | investigations split into `parallel` contiguous groups | every agent replied; `workspace/findings/` exists |
| dedupe | mantis-dedupe | haiku | Sharp+ | all findings | finding count did not increase |
| review | mantis-review | sonnet | all | findings split into `parallel` groups | each one has `reasoning` |
| critic | mantis-critic | opus | Sharp+ | status `VALID` or `PROVISIONALLY_VALID` | each one has `production_viability` |
| reproduce | mantis-reproduce | opus | Sharp+ | viable (`VIABLE`, `CONDITIONAL_VIABLE`); Sharp: only `CRITICAL` or `HIGH` | each one has `repro_status` |
| chain | mantis-chain | opus | Savage, Overkill | findings with `repro_status` = `reproduced` (skip if fewer than 2) | agent replied |
| patch | mantis-patch | opus | all | Light: status `VALID`/`PROVISIONALLY_VALID`; Sharp+: viable findings. **One finding at a time**: rerun the rsync from 2.4 before each one | each one has `patch_status` |
| calibrate | mantis-calibrate | sonnet | Sharp+ | non-rejected findings, split into `parallel` groups | each one has `mantis_risk_score` |
| reflect | mantis-reflect | sonnet | Savage, Overkill | whole workspace | agent replied |

- Dispatch parallel groups as several Agent calls in one message (`subagent_type: general-purpose`, with the model from the table).
- A finding is "rejected" if `status` is `FALSE_POSITIVE` or `DUPLICATE`, or if `production_viability` is `NON_VIABLE` or `SAMPLE_OR_TEST`. Rejected findings skip all later stages.
- Per-finding stages are resumable: on a rerun, only the findings in scope that still lack the checked field are processed.
- **Overkill:** the plan stage gets one investigation per source file. After reflect, if `round` < 3, increment `round`, reset plan, researcher, dedupe, review, critic, reproduce, patch, calibrate and reflect to `"pending"`, and run them again (plan then replans from `learnings.jsonl`).
- **Failure** (an agent errors, hits the quota, or the check fails) → set the stage to `"failed"` and stop. Tell the user which stage failed and why, in 2 lines, and that rerunning `/mantis-run` resumes from there. Do not retry in a loop.

### Stage agent prompt

```
You run the Mantis stage `<stage>` of a security audit.
1. Read <M>/<mantis dir>/SKILL.md and follow it in standalone mode with:
   --state_root <AUDIT>      (state files live in <AUDIT>/workspace/)
   --target_root <CODE>      (<CODE> = <REPO>; for reproduce and patch, <AUDIT>/workspace/shadow)
2. <REPO> is read-only. Write only under <AUDIT>/workspace/.
3. Do not delegate to sub-agents: you are one of <n> parallel workers.
4. Scope: <scope>.            (e.g. "only investigations #4 to #6 of workspace/plan.json",
                               "only findings <id>, <id>", "the whole workspace")
5. <level line>
6. <docker line>              (reproduce and patch only)
7. Reply in 5 lines max: what you wrote (paths or finding ids), and any blocker.
```

- Level line, Light patch: `Light level: write patch_diff as a unified diff relative to the repo root (a/<file>, b/<file>) and set patch_status to MITIGATION_PROPOSED. Do not execute any code.`
- Level line, plan: `Write at most <hypotheses_max> investigations. Prioritise these hypotheses: <focus>. Skip: <out_of_scope>.` For Overkill, instead: `One investigation per source file.`
- Level line, otherwise: `Level <level>.`
- Docker line: `Execute target code only with: docker run --rm --network=none <--runtime=runsc if inventory.json repro.runsc> -v "<AUDIT>/workspace/shadow":/src<:ro for reproduce> -w /src <official image for the stack, e.g. python:3.12-slim> <cmd>. Pulling the image is the only network access allowed. Never run target code on the host.`

## 4. Finish

1. Integrity: compare `git -C "$REPO" status --porcelain -- . ':(exclude)osho-mantis'` with `git_status_before`. If they differ, warn the user first, listing the files that changed, and do not discard anything.
2. `rm -rf "$AUDIT/workspace/shadow"`.
3. Set `finished: true` in `state.json` and `finished_at` (`date +%Y-%m-%dT%H:%M:%S`) in `campaign.json`.
4. `python3 "$R/render.py" "$AUDIT"`, then `open "$AUDIT/dashboard.html"`.
5. Report, 5 lines max: counts by severity, the top Critical or High finding, the `README.md` path. If `versioning` is `versioned`, end with: `git -C "<REPO>" add "osho-mantis/<audit name>" && git -C "<REPO>" commit -m "Audit de sécurité Mantis <date>"`. Never commit yourself.
````

- [ ] **Step 2: Lint the skill against the stage list**

Run: `for s in history structural-index architecture threat-model plan researcher dedupe review critic reproduce chain patch calibrate reflect; do [ -f ~/.local/share/mantis/mantis-$s/SKILL.md ] || [ -f ~/dev/mantis/mantis-$s/SKILL.md ] || echo "missing $s"; done; echo checked`
Expected: `checked`, with no `missing …` line (each stage in the table exists in Mantis).

- [ ] **Step 3: Commit**

```bash
git add plugins/osho-mantis/skills/mantis-run/SKILL.md
git commit -m "osho-mantis: mantis-run orchestrator skill"
```

---

### Task 6: Documentation

**Files:**
- Modify: `docs/skills.md` (append a section)
- Modify: `README.md` (section after `## osho-core`)
- Modify: `docs/decisions.md` (append 2 decisions)

- [ ] **Step 1: `docs/skills.md`** — insert before `## Adding a skill`:

```markdown
## osho-mantis

Opt-in : `claude plugin install osho-mantis@osho-skillz`. Lance les skills [google/mantis](https://github.com/google/mantis) (référencés dans `~/.local/share/mantis`) avec l'abonnement Claude Code.

| Component | Type | What it does |
|---|---|---|
| `mantis-triage` | Skill | Triage court : inventaire, zones à risque, niveau recommandé (Light, Sharp, Savage, Overkill) avec estimation de quota, dossier `osho-mantis/audit-<date>_<heure>/` |
| `mantis-run` | Skill | Campagne au niveau choisi, un sous-agent par étape Mantis, reprise après coupure, rapport `README.md`, `patches/`, `dashboard.html` |
| `check-visibility.sh` | Script | `local` / `private` / `public` / `unknown` via `gh` ; self-test : `bash skills/mantis-triage/scripts/test_check_visibility.sh` |
| `inventory.py` | Script | Inventaire zéro token et estimations ; self-test : `python3 skills/mantis-triage/scripts/test_inventory.py` |
| `render.py` | Script | Findings → README, patchs, dashboard ; self-test : `python3 skills/mantis-run/scripts/test_render.py` |
```

- [ ] **Step 2: `README.md`** — insert before `## Repository layout`:

````markdown
## osho-mantis (opt-in)

Security audits with [google/mantis](https://github.com/google/mantis), run on your Claude Code subscription (no Google or API key needed).

```bash
claude plugin install osho-mantis@osho-skillz
```

In a repo, say *"mantis triage"*: a short pass recommends a level (**Light → Sharp → Savage → Overkill**) with a quota estimate for your subscription. Then *"mantis run"* runs the audit and writes `osho-mantis/audit-<date>/` (README report, suggested patches, HTML dashboard). Run it only on code you are allowed to test; reproduction runs in Docker without network.
````

- [ ] **Step 3: `docs/decisions.md`** — append:

```markdown
**Mantis is referenced in `~/.local/share/mantis`, not installed as skills.** Each osho-mantis subagent reads the `SKILL.md` of its stage. Its 19 descriptions cost nothing in other sessions, and Mantis (Apache-2.0) stays outside this MIT repo.

**Audit folders are versioned by default, with a guard for public repos.** An audit contains detailed vulnerabilities and exploits. The skill checks visibility with `gh`, recommends not versioning when the repo is public, and asks when visibility is unknown.
```

- [ ] **Step 4: Run all self-tests**

Run: `bash plugins/osho-mantis/skills/mantis-triage/scripts/test_check_visibility.sh && python3 plugins/osho-mantis/skills/mantis-triage/scripts/test_inventory.py && python3 plugins/osho-mantis/skills/mantis-run/scripts/test_render.py`
Expected: `OK` three times.

- [ ] **Step 5: Commit**

```bash
git add docs/skills.md README.md docs/decisions.md
git commit -m "osho-mantis: document plugin, skills and decisions"
```

---

### Task 7: End-to-end Light audit (manual, by the user)

Needs an interactive Claude Code session, because of the AskUserQuestion prompts and the subscription quota. The implementer prepares the target, then hands over to the user.

- [ ] **Step 1: Prepare a throwaway target repo**

```bash
rm -rf ~/dev/mantis-e2e && mkdir ~/dev/mantis-e2e && cp ~/dev/mantis/reference/test_targets/app.py ~/dev/mantis-e2e/
git -C ~/dev/mantis-e2e init -q && git -C ~/dev/mantis-e2e add . && git -C ~/dev/mantis-e2e commit -qm "vulnerable target"
```

- [ ] **Step 2: User runs the audit** (about 10 to 20 min, roughly 20 % of a Max 5x window)

```bash
cd ~/dev/mantis-e2e && claude --plugin-dir ~/dev/OshO-Skillz/plugins/osho-mantis
```
Then say: `mantis triage`, pick **Light**, then `mantis run`.

- [ ] **Step 3: Verify**

Run:
```bash
a=$(ls -d ~/dev/mantis-e2e/osho-mantis/audit-* | tail -1)
grep -iE "traversal|injection" "$a/README.md" | head -3
git -C ~/dev/mantis-e2e status --porcelain -- . ':(exclude)osho-mantis'
ls "$a"
```
Expected:
- At least one line mentions path traversal or command injection: these are the 2 known vulnerabilities in `app.py`.
- The `git status` line is empty: the target is unchanged outside `osho-mantis/`.
- `ls` shows `README.md`, `dashboard.html`, `campaign.json`, `state.json`, `inventory.json`, `triage.md`, `workspace`, and `patches` if diffs were produced.
- The dashboard opened automatically.

- [ ] **Step 4: Fix-ups**

Fix any problem found, in the SKILL.md files (prompts, checks) or the scripts (with a test). Then:

```bash
git add -A plugins/osho-mantis && git commit -m "osho-mantis: fixes from end-to-end Light run"
```
````
