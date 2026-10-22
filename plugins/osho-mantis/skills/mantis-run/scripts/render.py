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
LEVEL_BANNERS = {
    "Light": "Analyse statique : pas de reproduction, correctifs proposés non vérifiés.",
    "Sharp": "Reproduction Docker des High+ et correctifs vérifiés par re-attaque.",
    "Savage": "Reproduction de tout le viable, chaînes d'exploits.",
    "Overkill": "Revue exhaustive de chaque fichier, 3 tours.",
}
ENUM_LABELS = {
    "status": {"VALID": "Confirmé", "PROVISIONALLY_VALID": "Probable", "FALSE_POSITIVE": "Faux positif",
               "DUPLICATE": "Doublon", "NEEDS_RESEARCH": "À creuser"},
    "repro_status": {"reproduced": "Reproduit", "statically_confirmed": "Confirmé statiquement",
                     "not_attempted": "Non tenté", "failed_to_reproduce": "Non reproduit"},
    "patch_status": {"VERIFIED_SECURE": "Vérifié par re-attaque", "MITIGATION_PROPOSED": "Correctif proposé, non vérifié",
                     "VERIFICATION_INCOMPLETE": "Vérification incomplète",
                     "VERIFICATION_FAILED": "Correctif contourné ou inapplicable", "ERROR": "Erreur"},
    "reattack_status": {"failed_to_bypass": "Re-attaque échouée (correctif tient)",
                        "bypassed_patch": "Correctif contourné", "inconclusive_baseline_changed": "Non concluant"},
    "production_viability": {"VIABLE": "Exploitable en prod", "CONDITIONAL_VIABLE": "Exploitable sous conditions",
                             "NON_VIABLE": "Non exploitable", "SAMPLE_OR_TEST": "Code d'exemple ou de test"},
}


def label(field, value):
    """French label for an enum value; unknown values pass through unchanged."""
    if value in (None, "", []):
        return None
    return ENUM_LABELS.get(field, {}).get(str(value), str(value))


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def load_findings(workspace, carry=None):
    """carry : findings du snapshot précédent par _src, gardés si leur fichier est en cours d'écriture"""
    findings, unreadable = [], []
    for p in sorted(Path(workspace, "findings").glob("*.json")):
        f = load_json(p, None)
        if isinstance(f, dict) and f.get("title"):
            f["id"] = str(f.get("id") or p.stem)
            f["_src"] = p.stem
            findings.append(f)
        elif carry and p.stem in carry:
            findings.append(dict(carry[p.stem]))
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


def risk(f):
    """Score de risque en nombre ; une valeur non numérique vaut 0"""
    try:
        return float(f.get("mantis_risk_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def sort_key(f):
    return (-risk(f), str(f["title"]).lower())


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


def text_enum(field, value):
    """Markdown-safe French label for an enum field's value."""
    return text(label(field, value))


def cell(value):
    return text(value).replace("|", "\\|").replace("\n", " ")


def summary(f):
    """executive_summary (set by calibrate) is absent in Light; fall back to impact"""
    return f.get("executive_summary") or f.get("impact")


def block(code, lang=""):
    longest = max((len(m) for m in re.findall(r"`+", code)), default=0)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{lang}\n{code.rstrip()}\n{fence}"


def readme(meta, findings, unreadable, st):
    kept = sorted((f for f in findings if bucket(f) != "REJECTED"), key=lambda f: (BUCKETS.index(bucket(f)), sort_key(f)))
    rejected = [f for f in findings if bucket(f) == "REJECTED"]
    out = [f"# Audit de sécurité — {text(meta['repo_name'])}", "",
           f"{meta['started_at'] or '?'} · niveau **{meta['level'] or '?'}** · Mantis `{meta['mantis_commit'] or '?'}`"
           + (f" · durée {meta['duration']}" if meta["duration"] else ""), ""]
    if meta["level_banner"]:
        out += [text(meta["level_banner"]), ""]
    out += ["[Ouvrir le dashboard](dashboard.html) : GitHub affiche le HTML en source, ouvrez le fichier en local.", "",
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
                    f"**Résumé** : {text(summary(f))}", "",
                    f"**Emplacement** : {text(f.get('code_paths'))} · **CWE** : {text(f.get('cwe'))}", "",
                    f"**Problème** : {text(f.get('description'))}", "",
                    f"**Impact** : {text(f.get('impact'))}", "",
                    f"**Cas testé** : {text_enum('repro_status', f.get('repro_status'))}"]
            for key in ("run_command", "repro_output"):
                if f.get(key):
                    out += ["", block(str(f[key]), "bash" if key == "run_command" else "")]
            out += ["", f"**Correction** ({text_enum('patch_status', f.get('patch_status'))})", ""]
            if f.get("patch_diff"):
                out += [block(str(f["patch_diff"]), "diff"), "",
                        f"Appliquer depuis la racine du repo : `git apply osho-mantis/{meta['audit_name']}/patches/{f['_file']}.diff`"]
            else:
                out.append(text(f.get("mitigation")))
            out.append("")
    if rejected:
        out += ["## Écartés", ""]
        for f in rejected:
            field = "status" if f.get("status") else "production_viability"
            out.append(f"- {text(f['title'])} — {text_enum(field, f.get(field))} : "
                       f"{text((f.get('critic_reasoning') or f.get('reasoning') or '')[:200])}")
        out.append("")
    if meta["fixes_merged"] > 0:
        merged = [f for f in findings if (f.get("_fix") or {}).get("status") == "merged"]
        n = meta["fixes_merged"]
        out += ["## Corrections fusionnées", "",
                f"{n} correctif{'' if n == 1 else 's'} sur la branche `{meta['audit_branch']}`."
                + (f" Pour les intégrer à ta branche : `git merge {meta['audit_branch']}`"
                   if meta.get("audit_branch_ok") else ""), ""]
        out += [f"- {text(f['title'])} (`{(f['_fix'].get('merge_commit') or f['_fix'].get('commit') or '')[:7]}`)"
                for f in merged] + [""]
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
    from snapshot import build_snapshot  # import tardif : snapshot importe render
    payload = build_snapshot(audit_dir, mode="final")
    findings, meta, st = payload["findings"], payload["meta"], payload["stats"]
    unreadable = load_findings(audit_dir / "workspace")[1]
    (audit_dir / "README.md").write_text(readme(meta, findings, unreadable, st))
    for f in findings:
        if f.get("patch_diff") and bucket(f) != "REJECTED":
            (audit_dir / "patches").mkdir(exist_ok=True)
            (audit_dir / "patches" / f"{f['_file']}.diff").write_text(str(f["patch_diff"]).rstrip("\n") + "\n")
    page = Path(__file__).with_name("dashboard.html").read_text(encoding="utf-8")
    (audit_dir / "dashboard.html").write_text(page.replace("__DATA__", safe_json(payload), 1), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    render(sys.argv[1])
    print(f"README.md, dashboard.html écrits dans {Path(sys.argv[1]).resolve()}")
