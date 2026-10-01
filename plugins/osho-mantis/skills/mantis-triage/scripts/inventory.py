#!/usr/bin/env python3
"""Inventaire zéro token d'un repo git pour le triage osho-mantis
  python3 inventory.py <repo> <sortie.json>
"""
import json
import re
import stat
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
        lang = LANGS.get(path.suffix.lower())
        if not lang:
            continue
        try:
            st = path.lstat()
            if not stat.S_ISREG(st.st_mode):
                continue
            if st.st_size > 1_000_000:
                continue
            text = path.read_text(errors="ignore")
        except OSError:
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
