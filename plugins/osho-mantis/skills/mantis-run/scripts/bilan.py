#!/usr/bin/env python3
"""Bilan d'un audit Mantis : synthèse HTML autonome, sans JS (bilan.html et onglet Bilan du dashboard)
  python3 bilan.py <AUDIT>   écrit <AUDIT>/bilan.html
Structure reprise de la synthèse Kata, sans note ni plafond ; style du dashboard (jetons Horizon).
"""
import re
import sys
from collections import defaultdict
from html import escape
from pathlib import Path

import cost
import export
import render

SEV_FR = {"CRITICAL": "Critique", "HIGH": "Haute", "MEDIUM": "Moyenne", "LOW": "Basse", "REJECTED": "Écarté"}
SEV_CLS = {"CRITICAL": "crit", "HIGH": "high", "MEDIUM": "med", "LOW": "low", "REJECTED": "rej"}
LIMITS = {
    "Light": "analyse statique seule : aucun constat n'a été rejoué, aucun correctif n'a été vérifié.",
    "Sharp": "seuls les constats critiques et hauts ont été rejoués, dans Docker sans réseau.",
    "Savage": "les constats exploitables ont été rejoués dans Docker sans réseau.",
    "Overkill": "chaque fichier source a été relu, en trois tours au plus ; les constats exploitables ont été rejoués dans Docker sans réseau.",
}
RESERVE_WORDS = ("prérequis", "résiduel", "rotation", "risque fonctionnel", "à ajouter", "requis")
INCIDENT_WORDS = ("incident", "arrêt", "reprise", "coupure", "écart à la règle", "supprimé par un agent")
LIMIT_WORDS = ("partiel", "non lu", "survol", "bloqué", "filtre", "non tranché", "non testé", "greppé")
SECTIONS = [("ouverture", "En une phrase"), ("depot", "Le dépôt audité"), ("bref", "En bref"),
            ("echelles", "Gravité, reproduction, correctif : ce que veulent dire les mots"),
            ("constats", "Les constats"), ("dev", "Pour l'équipe de développement"), ("deroule", "Déroulé de l'audit"),
            ("verification", "Comment ces résultats ont été vérifiés"), ("lexique", "Lexique")]
SCALES = {
    "Gravité": [("Critique", "prise de contrôle, fuite massive ou accès total sans authentification"),
                ("Haute", "atteinte sérieuse à des données ou à des comptes, exploitable en conditions réelles"),
                ("Moyenne", "atteinte limitée, ou exploitable seulement sous conditions"),
                ("Basse", "défaut de durcissement, impact faible ou très indirect")],
    "Reproduction": [(render.ENUM_LABELS["repro_status"][k], v) for k, v in (
        ("reproduced", "l'exploit a été rejoué dans un conteneur Docker sans réseau, et il a marché"),
        ("statically_confirmed", "le chemin du défaut a été suivi dans le code, sans exécution"),
        ("not_attempted", "pas de tentative (dépendance manquante, hors périmètre du niveau)"),
        ("failed_to_reproduce", "la tentative n'a pas abouti : le défaut reste possible, non prouvé"))],
    "Correctif": [(render.ENUM_LABELS["patch_status"][k], v) for k, v in (
        ("VERIFIED_SECURE", "le patch a été appliqué puis attaqué par un agent distinct, qui n'a pas pu le contourner"),
        ("MITIGATION_PROPOSED", "diff proposé, jamais rejoué contre l'exploit"),
        ("VERIFICATION_INCOMPLETE", "re-attaque partielle ou impossible : à vérifier à la main"),
        ("VERIFICATION_FAILED", "le patch a été contourné ou ne s'applique pas : à reprendre"))],
}
LEXIQUE = [("Constat (finding)", "un défaut de sécurité supposé, avec son emplacement, son impact et ses preuves"),
           ("PoC", "preuve de faisabilité : le petit programme qui déclenche le défaut"),
           ("Re-attaque", "nouvelle tentative d'exploitation, par un agent distinct, contre le code corrigé"),
           ("Shadow", "copie temporaire du dépôt où sont rejoués exploits et patchs ; le dépôt n'est jamais modifié"),
           ("Tour", "un passage complet plan, recherche, revue, reproduction, correctifs, réflexion ; Overkill en fait jusqu'à trois"),
           ("Écarté", "faux positif, doublon, code de test ou non exploitable en production"),
           ("Score de risque", "note de 0 à 10 calculée par l'étape de calibrage, à partir de l'impact et de la probabilité")]

CSS = """
:root{color-scheme:dark;--bg:#0b0d14;--card:#12151f;--elev:#171b27;--fg:#e7ebf6;--muted:#a6aec8;--faint:#8c94ae;
--primary:#7ea6ff;--border:#242a3b;--banner:#18203d;--banner2:#10162b;--muted-bg:#1c2131;
--ok:oklch(.72 .15 155);--warn:oklch(.80 .15 85);--bad:oklch(.65 .20 25);
--crit:oklch(.62 .22 20);--high:oklch(.70 .18 45);--med:oklch(.80 .15 85);--low:oklch(.72 .08 240);
--sans:"Source Sans 3","Source Sans Pro",system-ui,sans-serif;--mono:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,monospace}
@media (prefers-color-scheme:light){:root{color-scheme:light;--bg:#eff1f5;--card:#fff;--elev:#f7f8fb;--fg:#0b1a4a;
--muted:#46527c;--faint:#626c90;--primary:#0050d7;--border:#e1e5ee;--banner:#d4daee;--banner2:#e7eaf5;--muted-bg:#eceff6}}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--fg)}
body{font:15px/1.55 var(--sans);font-variant-numeric:tabular-nums}
.top{height:48px;display:flex;align-items:center;gap:10px;padding:0 20px;background:var(--card);border-bottom:1px solid var(--border);font-size:13px;color:var(--muted)}
.logo{width:22px;height:22px;border-radius:7px;background:var(--primary);color:var(--bg);display:grid;place-items:center;font-weight:800;font-size:12px}
.banner{position:relative;overflow:hidden;background:var(--banner);padding:24px 20px;border-bottom:1px solid var(--border)}
.banner::after{content:"";position:absolute;inset:0 0 0 auto;width:34%;background:var(--banner2);clip-path:polygon(14% 0,100% 0,100% 100%,0 100%)}
.banner>*{position:relative;z-index:1;max-width:1040px;margin:0 auto}
h1{margin:0;font-size:26px;line-height:1.25;font-weight:600}
.engine{margin:6px auto 0;font-size:13px;color:var(--muted)}
main{max-width:1040px;margin:0 auto;padding:12px 20px 64px}
h2{font-size:21px;font-weight:600;margin:44px 0 12px;padding-top:12px;border-top:2px solid var(--primary)}
h3{font-size:16px;margin:24px 0 8px}
a{color:var(--primary)}code,.mono{font-family:var(--mono);font-size:13px}
code{background:var(--muted-bg);padding:0 4px;border-radius:4px;overflow-wrap:anywhere}
pre{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px;overflow-x:auto}
.provisoire{max-width:1040px;margin:12px auto 0;padding:10px 14px;border:1px solid var(--warn);border-radius:10px;color:var(--warn)}
.verdict{font-size:18px;font-weight:600;margin:14px 0 8px}
.warn{border:1px solid var(--bad);background:color-mix(in oklch,var(--bad) 12%,transparent);border-radius:10px;padding:12px 14px;margin:12px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}
.tile{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.tile b{display:block;font:500 28px/1.1 var(--mono)}.tile span{font-size:13px;color:var(--muted)}
.tile.crit{border-left:3px solid var(--crit)}.tile.high{border-left:3px solid var(--high)}
.tile.med{border-left:3px solid var(--med)}.tile.low{border-left:3px solid var(--low)}
.pill{display:inline-block;padding:0 8px;border-radius:999px;font-size:12px;font-weight:600;white-space:nowrap;border:1px solid}
.pill.crit{color:var(--crit)}.pill.high{color:var(--high)}.pill.med{color:var(--med)}.pill.low{color:var(--low)}.pill.rej{color:var(--faint)}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--border);border-radius:10px;font-size:14px;margin:8px 0 14px}
th{text-align:left;font-weight:600;font-size:13px;color:var(--muted);background:var(--elev);padding:8px 10px;border-bottom:1px solid var(--border)}
td{padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:top}tr:last-child td{border-bottom:0}
.card-list{list-style:none;padding:0;display:grid;gap:8px}
.card-list li{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:10px 14px}
.muted{color:var(--muted)}details summary{cursor:pointer;color:var(--muted)}
.toc{columns:2;font-size:14px}dl dt{font-weight:600;margin-top:8px}dl dd{margin:0 0 0 0;color:var(--muted)}
@media (max-width:760px){table{display:block;overflow-x:auto}.toc{columns:1}}
@media print{.top{display:none}body{background:#fff;color:#000}h2{break-after:avoid}tr{break-inside:avoid}}
"""


def e(x):
    """Texte échappé ; l'apostrophe reste lisible, les attributs sont toujours entre guillemets doubles"""
    return escape("" if x is None else str(x), quote=False).replace('"', "&quot;")


def inline(text):
    """Texte Markdown simple d'une ligne : échappé, puis `code` seulement"""
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", e(text))


def fmt_usd(usd):
    return "inconnu" if usd is None else f"≈ {usd:,.0f} $".replace(",", " ")


def sev(b):
    return f'<span class="pill {SEV_CLS.get(b, "low")}">{SEV_FR.get(b, b)}</span>'


def plural(n, one, many):
    return f"{n} {one if n == 1 else many}"


def triage_sections(audit_dir):
    try:
        text = (Path(audit_dir) / "triage.md").read_text(errors="replace")
    except OSError:
        return {}
    out, cur = {}, None
    for line in text.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip()
            out[cur] = []
        elif cur and line.strip():
            out[cur].append(re.sub(r"^\s*(?:[-*]|\d+\.)\s+", "", line))
    return out


def stage_totals(activity):
    tot, passes = defaultdict(int), defaultdict(int)
    for ev in activity:
        if ev.get("kind") == "stage" and ev.get("to") == "done" and isinstance(ev.get("duration_s"), (int, float)):
            tot[ev["stage"]] += int(ev["duration_s"])
            passes[ev["stage"]] += 1
    return tot, passes


def build(audit_dir, snap=None, live=False):
    from snapshot import build_snapshot, read_activity  # import tardif : snapshot importe render
    audit_dir = Path(audit_dir).resolve()
    snap = snap or build_snapshot(audit_dir, mode="live" if live else "final")
    meta, findings = snap["meta"], snap["findings"]
    state = export._state(audit_dir)
    notes = [str(n) for n in meta.get("notes") or []]
    kept = [f for f in findings if f["_bucket"] != "REJECTED"]
    rejected = [f for f in findings if f["_bucket"] == "REJECTED"]
    open_hi = [f for f in kept if f["_bucket"] in ("CRITICAL", "HIGH") and f.get("patch_status") != "VERIFIED_SECURE"]
    c = cost.summary(audit_dir)
    secrets, confl = export.scan_secrets(audit_dir), export.conflicts(audit_dir)
    dev = export.dev_data(audit_dir, secrets, confl)
    repo, level, rnd = meta["repo_name"], meta.get("level") or "inconnu", state.get("round") or 1
    base = state.get("base_commit")
    H = []
    w = H.append

    w("<!doctype html>\n<html lang=\"fr\"><head><meta charset=\"utf-8\"><base target=\"_top\">"
      "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
      f"<title>{e(repo)} : bilan de l'audit de sécurité</title><style>{CSS}</style>\n</head><body>")
    w(f'<header class="banner"><h1>{e(repo)} : bilan de l\'audit de sécurité</h1>'
      f'<p class="engine">Audit {e(meta["audit_name"])}. Moteur : Mantis {e(meta.get("mantis_commit") or "?")}, niveau {e(level)}, '
      f'{plural(rnd, "tour", "tours")}. Limite : {e(LIMITS.get(level, "niveau inconnu."))}</p></header>')
    if live:
        w(f'<p class="provisoire">Audit en cours, tour {e(rnd)} : bilan provisoire</p>')
    w("<main>")

    # Ouverture
    n_open = len(open_hi)
    verdict = ("Aucune faille critique ou haute ouverte." if not n_open else
               f"{n_open} faille critique ou haute reste ouverte : à corriger avant d'exposer l'application."
               if n_open == 1 else
               f"{n_open} failles critiques ou hautes restent ouvertes : à corriger avant d'exposer l'application.")
    w('<section id="ouverture">')
    w(f"<p>Cette analyse porte sur le dépôt <b>{e(repo)}</b>"
      + (f" au commit <code>{e(base)}</code>" if base else "") +
      f" : {plural(len(findings), 'constat examiné', 'constats examinés')}, "
      f"{plural(len(kept), 'retenu', 'retenus')}, {plural(len(rejected), 'écarté', 'écartés')}.</p>")
    w(f'<p class="verdict">{e(verdict)}</p>')
    src = " (saisi)" if c["source"] == "manuel" else ""
    w(f"<p>Coût estimé : <b>{e(fmt_usd(c['usd']))}</b>{src} (équivalent API, estimation au tarif public, pas une facture ; "
      f"sur abonnement, l'audit consomme du quota). Durée : {e(cost.fmt_s(c['active_s']))} de travail actif, "
      f"{e(cost.fmt_s(c['wall_s']))} au total.</p>")
    w("<p class=\"muted\">Ce bilan ne remplace ni une revue humaine de chaque constat ni un test d'intrusion.</p>")
    w("</section>")

    # Sommaire
    w('<nav id="sommaire"><h2>Sommaire</h2><ol class="toc">')
    for sid, title in SECTIONS[1:]:
        w(f'<li><a href="#{sid}">{e(title)}</a></li>')
    w("</ol></nav>")

    # Dépôt
    tri = triage_sections(audit_dir)
    w(f'<section id="depot"><h2>{e(SECTIONS[1][1])}</h2>')
    for key, title in (("Stack", "Composants"), ("Zones à risque", "Zones à risque repérées au triage")):
        if tri.get(key):
            w(f"<h3>{title}</h3><ul>" + "".join(f"<li>{inline(x)}</li>" for x in tri[key]) + "</ul>")
    if not tri:
        w('<p class="muted">Pas de triage enregistré.</p>')
    w("</section>")

    # En bref
    st = snap["stats"]["by_bucket"]
    ps = defaultdict(int)
    for f in kept:
        ps[f.get("patch_status")] += 1
    w(f'<section id="bref"><h2>{e(SECTIONS[2][1])}</h2><div class="tiles">')
    for b in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        n = st.get(b, 0)
        w(f'<div class="tile {SEV_CLS[b]}"><b>{n}</b><span>{SEV_FR[b].lower()}{"s" if n > 1 else ""} '
          f'{"retenues" if n > 1 else "retenue"}</span></div>')
    for n, lab in ((sum(f.get("repro_status") == "reproduced" for f in kept), "reproduits dans Docker"),
                   (ps["VERIFIED_SECURE"], "correctifs vérifiés"), (ps["VERIFICATION_FAILED"], "correctifs contournés"),
                   (ps["MITIGATION_PROPOSED"], "correctifs proposés, non vérifiés"), (len(rejected), "écartés")):
        w(f'<div class="tile"><b>{n}</b><span>{lab}</span></div>')
    w("</div>")
    top = sorted(kept, key=lambda f: (render.BUCKETS.index(f["_bucket"]), -render.risk(f)))[:5]
    w("<h3>Le plus grave</h3>")
    if top:
        w('<ul class="card-list">')
        for f in top:
            summ = str(render.summary(f) or "").split(". ")[0][:300]
            w(f'<li>{sev(f["_bucket"])} <a href="dashboard.html#{e(f["_file"])}">{e(f["title"])}</a>'
              f'<br><span class="muted">{e(summ)}</span><br><span class="mono muted">'
              f'{e(render.label("repro_status", f.get("repro_status")) or "non rejoué")} · '
              f'{e(render.label("patch_status", f.get("patch_status")) or "sans correctif")}</span></li>')
        w("</ul>")
    else:
        w("<p>Aucun constat retenu.</p>")
    reserves = [n for n in notes if any(k in n.lower() for k in RESERVE_WORDS)]
    w("<h3>Réserves</h3>")
    w("<ul>" + "".join(f"<li>{e(n)}</li>" for n in reserves) + "</ul>" if reserves
      else '<p class="muted">Aucune réserve notée pendant l\'audit.</p>')
    w("</section>")

    # Échelles
    w(f'<section id="echelles"><h2>{e(SECTIONS[3][1])}</h2>')
    for title, rows in SCALES.items():
        w(f"<h3>{e(title)}</h3><table><tbody>" + "".join(f"<tr><td><b>{e(a)}</b></td><td>{e(b)}</td></tr>"
                                                         for a, b in rows) + "</tbody></table>")
    w("</section>")

    # Constats
    w(f'<section id="constats"><h2>{e(SECTIONS[4][1])}</h2>')
    head = ("<table><thead><tr><th>Gravité</th><th>Constat</th><th>Emplacement</th><th>Reproduction</th>"
            "<th>Correctif</th><th>Score</th></tr></thead><tbody>")

    def row(f):
        loc = (f.get("code_paths") or [""])[0] if isinstance(f.get("code_paths"), list) else f.get("code_paths")
        score = f.get("mantis_risk_score")
        return (f'<tr><td>{sev(f["_bucket"])}</td><td><a href="dashboard.html#{e(f["_file"])}">{e(f["title"])}</a></td>'
                f'<td class="mono">{e(loc)}</td><td>{e(render.label("repro_status", f.get("repro_status")) or "")}</td>'
                f'<td>{e(render.label("patch_status", f.get("patch_status")) or "")}</td>'
                f'<td class="mono">{e(score if score is not None else "")}</td></tr>')
    if kept:
        for b in render.BUCKETS:
            group = [f for f in kept if f["_bucket"] == b]
            if group:
                w(f"<h3>{SEV_FR[b]} ({len(group)})</h3>" + head + "".join(row(f) for f in group) + "</tbody></table>")
    else:
        w("<p>Aucun constat retenu.</p>")
    if rejected:
        w(f"<details><summary>{plural(len(rejected), 'constat écarté', 'constats écartés')}</summary>"
          + head + "".join(row(f) for f in rejected) + "</tbody></table></details>")
    w("</section>")

    # Pour l'équipe de développement
    w(f'<section id="dev"><h2>{e(SECTIONS[5][1])}</h2>')
    w(f'<div class="warn">{e(export.WARNING)}</div>')
    w("<h3>Secrets à révoquer</h3>")
    if dev["secrets"]:
        w(f"<p>{e(export.SECRETS_INTRO)}</p><ul>")
        for s in dev["secrets"]:
            who = (f'<a href="dashboard.html#{e(s["file_id"])}">{e(s["title"])}</a>' if s["title"]
                   else e(s["finding"] or "hors constat"))
            w(f"<li>{e(s['kind'])} : {who}, fichier <code>{e(s['file'])}</code></li>")
        w("</ul>")
    else:
        w(f"<p>{e(export.NO_SECRET)}</p>")
    w("<h3>Lire l'audit</h3><ol>" + "".join(f"<li>{inline(x)}</li>" for x in export.READ_STEPS) + "</ol>")
    w(f"<h3>Appliquer un patch</h3><p>Les patchs sont écrits contre le commit <code>{e(dev['base'])}</code>. "
      "Partez d'une branche à ce commit, puis pour chaque patch :</p>"
      f"<pre>{e(chr(10).join(export.apply_commands(dev['base'])))}</pre><p>{e(export.APPLY_ORDER)}</p>")
    if dev["patches"]:
        w("<table><thead><tr><th>Patch</th><th>Constat</th><th>Gravité</th><th>Statut</th><th>Prérequis et réserves</th>"
          "</tr></thead><tbody>")
        for r in dev["patches"]:
            w(f'<tr><td class="mono">patches/{e(r["patch"])}.diff</td><td>{e(r["title"])}</td><td>{sev(r["bucket"])}</td>'
              f'<td>{e(r["status_label"])}</td><td>{"<br>".join(e(x) for x in r["prereq"])}</td></tr>')
        w("</tbody></table>")
    w("<h3>Patchs en conflit</h3>")
    if dev["pairs"]:
        w(f"<p>{e(export.CONFLICT_INTRO)}</p><ul>" + "".join(
            f"<li><code>{e(x['a'])}</code> et <code>{e(x['b'])}</code> : {e(x['kind'])} dans <code>{e(x['file'])}</code></li>"
            for x in dev["pairs"]) + "</ul>")
    else:
        w(f"<p>{e(export.NO_CONFLICT)}</p>")
    if dev["conflict_notes"]:
        w("<ul>" + "".join(f"<li>Note de l'audit : {e(n)}</li>" for n in dev["conflict_notes"]) + "</ul>")
    w(f"<h3>Rejouer une reproduction</h3><p>{inline(export.REPLAY)}</p></section>")

    # Déroulé
    tot, passes = stage_totals(read_activity(audit_dir / "activity.jsonl"))  # le snapshot n'en garde que 200
    w(f'<section id="deroule"><h2>{e(SECTIONS[6][1])}</h2>')
    w(f"<p>Niveau {e(level)}, {plural(rnd, 'tour', 'tours')}. Début {e(meta.get('started_at') or '?')}, "
      f"durée totale {e(cost.fmt_s(c['wall_s']))}, dont {e(cost.fmt_s(c['active_s']))} de travail actif "
      "(le reste : pauses de quota et attentes de réponse).</p>")
    w("<table><thead><tr><th>Étape</th><th>Passages</th><th>Durée cumulée, pauses comprises</th><th>État</th></tr></thead><tbody>")
    for s in snap["stages"]:
        w(f'<tr><td>{e(s["name"])}</td><td class="mono">{passes.get(s["key"], "")}</td>'
          f'<td class="mono">{e(cost.fmt_s(tot[s["key"]]) if s["key"] in tot else "inconnue")}</td>'
          f'<td>{e({"done": "terminée", "running": "en cours", "failed": "en échec", "skipped": "sautée"}.get(s["status"], "à venir"))}</td></tr>')
    w("</tbody></table>")
    if c["by_model"]:
        w("<h3>Coût par modèle</h3><table><thead><tr><th>Modèle</th><th>Jetons de sortie</th><th>Lectures de cache</th>"
          "<th>Coût estimé</th></tr></thead><tbody>")
        for model, m in sorted(c["by_model"].items(), key=lambda x: -(x[1].get("usd") or 0)):
            w(f'<tr><td class="mono">{e(model)}</td><td class="mono">{m.get("out", 0):,}</td>'
              f'<td class="mono">{m.get("cache_read", 0):,}</td><td class="mono">{e(fmt_usd(m.get("usd")))}</td></tr>'
              .replace(",", " "))
        w("</tbody></table>")
    incidents = [n for n in notes if any(k in n.lower() for k in INCIDENT_WORDS)]
    if incidents:
        w("<h3>Incidents et reprises</h3><ul>" + "".join(f"<li>{e(n)}</li>" for n in incidents) + "</ul>")
    w("</section>")

    # Vérification
    w(f'<section id="verification"><h2>{e(SECTIONS[7][1])}</h2>')
    w("<p>Chaque étape est confiée à un agent Claude distinct qui suit la méthode Mantis. Les constats sont relus "
      "(revue), puis contestés par un critique qui écarte ce qui n'est pas exploitable en production.</p>")
    if level != "Light":
        w("<p>Les constats retenus sont rejoués dans un conteneur Docker sans réseau, sur une copie du dépôt. "
          "Un correctif n'est dit « vérifié » qu'après une re-attaque menée par un autre agent que celui qui l'a écrit, "
          "sur le code corrigé.</p>")
    lim = [n for n in notes if any(k in n.lower() for k in LIMIT_WORDS)]
    if lim:
        w("<h3>Limites de couverture</h3><ul>" + "".join(f"<li>{e(n)}</li>" for n in lim) + "</ul>")
    w("</section>")

    # Lexique
    w(f'<section id="lexique"><h2>{e(SECTIONS[8][1])}</h2><dl>'
      + "".join(f"<dt>{e(a)}</dt><dd>{e(b)}</dd>" for a, b in LEXIQUE) + "</dl></section>")
    w("</main></body></html>\n")
    return "\n".join(H)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = Path(sys.argv[1]) / "bilan.html"
    out.write_text(build(sys.argv[1]), encoding="utf-8")
    print(out)
