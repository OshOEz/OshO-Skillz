#!/usr/bin/env python3
"""Auto-test de bilan.py : sections, verdict, échappement, notes rattachées, bilan provisoire
  python3 test_bilan.py
"""
import json
import tempfile
from pathlib import Path

import bilan
import render

SECTIONS = ["ouverture", "sommaire", "depot", "bref", "echelles", "constats", "dev", "deroule", "verification",
            "lexique"]
HOSTILE = "<img src=x onerror=alert(1)>"


def audit(tmp, findings, finished=True, notes=(), level="Overkill", rnd=3):
    d = Path(tmp) / "repo" / "osho-mantis" / "audit-x"
    (d / "workspace" / "findings").mkdir(parents=True)
    camp = {"repo": str(Path(tmp) / "repo"), "level": level, "mantis_commit": "f3162c0",
            "started_at": "2026-10-29T12:10:09"}
    if finished:
        camp["finished_at"] = "2026-10-30T08:07:47"
    (d / "campaign.json").write_text(json.dumps(camp))
    (d / "state.json").write_text(json.dumps({"stages": {"plan": "done", "reflect": "done" if finished else "running"},
                                              "round": rnd, "finished": finished, "base_commit": "5e9944e",
                                              "notes": list(notes)}))
    (d / "triage.md").write_text("# Triage\n\n## Stack\n- Java Spring `api`\n\n## Zones à risque\n1. WebSecurityConfig permitAll\n")
    for i, f in enumerate(findings):
        (d / "workspace" / "findings" / f"s{i}.json").write_text(json.dumps(f))
    return d


def F(i, sev="HIGH", **kw):
    return dict({"id": f"id{i}aaaaaa", "title": f"Constat {i}", "severity": sev, "priority": sev, "status": "VALID",
                 "code_paths": [f"app/A{i}.java:10"]}, **kw)


def test_sections():
    with tempfile.TemporaryDirectory() as tmp:
        page = bilan.build(audit(tmp, [F(1)]))
        for s in SECTIONS:
            assert f'id="{s}"' in page, s
        assert "<script" not in page.lower(), "pas de JS dans le bilan"
        assert "Java Spring" in page and "permitAll" in page


def test_verdict_ouvert():
    with tempfile.TemporaryDirectory() as tmp:
        page = bilan.build(audit(tmp, [F(1, "CRITICAL"), F(2, "HIGH", patch_status="VERIFIED_SECURE"), F(3, "MEDIUM")]))
        assert "1 faille critique ou haute reste ouverte : à corriger avant d'exposer l'application." in page


def test_verdict_ferme():
    with tempfile.TemporaryDirectory() as tmp:
        page = bilan.build(audit(tmp, [F(2, "HIGH", patch_status="VERIFIED_SECURE"), F(3, "LOW"),
                                       F(4, "CRITICAL", status="FALSE_POSITIVE")]))
        assert "Aucune faille critique ou haute ouverte." in page


def test_xss():
    with tempfile.TemporaryDirectory() as tmp:
        page = bilan.build(audit(tmp, [F(1, title=HOSTILE)], notes=[f"id1aaaaa {HOSTILE} </style>"]))
        assert HOSTILE not in page and "</style><" not in page.replace("</style>\n</head>", "")
        assert "&lt;img src=x" in page


def test_notes_rattachees():
    with tempfile.TemporaryDirectory() as tmp:
        page = bilan.build(audit(tmp, [F(1)], notes=["id1aaaaa prérequis : définir EZYMOB_API_PASSWORD"]))
        assert "EZYMOB_API_PASSWORD" in page.split('id="bref"')[1], "la réserve apparaît dans En bref"
        page = bilan.build(audit(tmp + "/b", [F(1)], notes=["id1aaaaa relu deux fois"]))
        assert "relu deux fois" not in page.split('id="bref"')[1].split('id="echelles"')[0], "simple mention : pas une réserve"


def test_pas_de_plafond():
    with tempfile.TemporaryDirectory() as tmp:
        page = bilan.build(audit(tmp, [F(1)])).lower()
        assert "plafond" not in page and "note d'ensemble" not in page


def test_live():
    with tempfile.TemporaryDirectory() as tmp:
        page = bilan.build(audit(tmp, [F(1)], finished=False, rnd=2), live=True)
        assert "Audit en cours, tour 2 : bilan provisoire" in page


def test_aucun_finding():
    with tempfile.TemporaryDirectory() as tmp:
        page = bilan.build(audit(tmp, []))
        assert "Aucune faille critique ou haute ouverte." in page and "Aucun constat" in page


def test_finding_illisible():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [F(1)])
        (d / "workspace" / "findings" / "vide.json").write_text("")
        assert "Constat 1" in bilan.build(d)


def test_secrets_et_cout():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [F(1, description="clé AIza" + "C" * 35)])
        (d / "cost.json").write_text(json.dumps({"auto": {"usd": 300.6, "active_s": 9960}}))
        page = bilan.build(d)
        dev = page.split('id="dev"')[1]
        assert "Secrets à révoquer" in dev and "Constat 1" in dev
        assert "≈ 301 $" in page and "2 h 46 min" in page and "19 h 57 min" in page
        assert "pas une facture" in page


def test_render_ecrit_bilan():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [F(1)])
        render.render(d)
        assert (d / "bilan.html").read_text().startswith("<!doctype html>")
        assert set(render.pages(d)) == {"bilan.html", "dashboard.html"} == set(render.pages_names())


if __name__ == "__main__":
    test_sections()
    test_verdict_ouvert()
    test_verdict_ferme()
    test_xss()
    test_notes_rattachees()
    test_pas_de_plafond()
    test_live()
    test_aucun_finding()
    test_finding_illisible()
    test_secrets_et_cout()
    test_render_ecrit_bilan()
    print("OK")
