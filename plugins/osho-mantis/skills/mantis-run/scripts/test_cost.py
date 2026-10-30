#!/usr/bin/env python3
"""Auto-test de cost.py : transcripts fictifs, fenêtre, doublons, sous-agents, saisie manuelle
  python3 test_cost.py
"""
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import cost

T0 = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc).timestamp()


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def msg(t, mid, model="claude-opus-5-5", out=0, inp=0, cr=0, w5=0, w1=0, kind="assistant"):
    return {"type": kind, "timestamp": iso(t), "message": {
        "id": mid, "model": model, "usage": {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": cr,
                                             "cache_creation": {"ephemeral_5m_input_tokens": w5,
                                                                "ephemeral_1h_input_tokens": w1}}}}


def setup(tmp, lines, sub=None, finished=True, mention=True):
    tmp = Path(tmp)
    audit = tmp / "repo" / "osho-mantis" / "audit-x"
    (audit / "workspace").mkdir(parents=True)
    camp = {"started_at": "2026-10-29T13:00:00"}
    if finished:
        camp["finished_at"] = "2026-10-29T15:00:00"
    (audit / "campaign.json").write_text(json.dumps(camp))
    (audit / "inventory.json").write_text("{}")
    os.utime(audit / "inventory.json", (T0, T0))
    proj = tmp / "projects" / "-x"
    proj.mkdir(parents=True)
    head = [{"type": "user", "timestamp": iso(T0 + 1), "message": {"content": f"/mantis-run {audit}" if mention else "rien"}}]
    (proj / "s1.jsonl").write_text("\n".join(json.dumps(x) for x in head + lines) + "\n")
    if sub is not None:
        (proj / "s1" / "subagents").mkdir(parents=True)
        (proj / "s1" / "subagents" / "agent-a.jsonl").write_text("\n".join(json.dumps(x) for x in sub) + "\n")
    return audit, tmp / "projects"


def test_prix():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects = setup(tmp, [msg(T0 + 10, "m1", out=1_000_000),
                                      msg(T0 + 20, "m2", model="claude-sonnet-5-5", w1=1_000_000)])
        r = cost.compute(audit, projects, now=T0 + 7200)
        assert abs(r["by_model"]["claude-opus-5-5"]["usd"] - 20.0) < 1e-9
        assert abs(r["by_model"]["claude-sonnet-5-5"]["usd"] - 4.0) < 1e-9
        assert abs(r["usd"] - 24.0) < 1e-9 and r["sessions"] == 1
        audit2, projects2 = setup(Path(tmp) / "b", [msg(T0 + 10, "m1", cr=1_000_000)])
        assert abs(cost.compute(audit2, projects2)["usd"] - 0.20) < 1e-9, "lecture de cache Opus 5.5 : 0,20 $/Mtok"


def test_doublons_message_id():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects = setup(tmp, [msg(T0 + 10, "m1", out=1_000_000), msg(T0 + 11, "m1", out=1_000_000)])
        assert abs(cost.compute(audit, projects)["usd"] - 20.0) < 1e-9


def test_fenetre():
    with tempfile.TemporaryDirectory() as tmp:
        # finished_at 15:00 local ; un message 3 jours plus tard est hors fenêtre
        audit, projects = setup(tmp, [msg(T0 + 10, "m1", out=1_000_000), msg(T0 + 3 * 86400, "m2", out=1_000_000),
                                      msg(T0 - 3600, "m0", out=1_000_000)])
        assert abs(cost.compute(audit, projects)["usd"] - 20.0) < 1e-9


def test_sous_agents():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects = setup(tmp, [msg(T0 + 10, "m1", out=1_000_000)],
                                sub=[msg(T0 + 30, "s1", model="claude-haiku-5-5", out=2_000_000)])
        r = cost.compute(audit, projects)
        assert abs(r["usd"] - 21.0) < 1e-9, r


def test_modele_inconnu():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects = setup(tmp, [msg(T0 + 10, "m1", out=1_000_000), msg(T0 + 20, "m2", model="claude-x", out=5)])
        r = cost.compute(audit, projects)
        assert r["unknown_models"] == ["claude-x"] and r["by_model"]["claude-x"]["out"] == 5
        assert r["by_model"]["claude-x"]["usd"] is None and abs(r["usd"] - 20.0) < 1e-9


def test_temps_actif():
    with tempfile.TemporaryDirectory() as tmp:
        lines = [msg(T0 + t, f"m{t}") for t in (100, 160, 200, 500)]
        audit, projects = setup(tmp, lines, sub=[msg(T0 + 300, "s")])  # les sous-agents ne comptent pas
        r = cost.compute(audit, projects)
        assert r["active_s"] == 199, r["active_s"]  # écarts 99 + 60 + 40 ; 300 s ≥ 120 s exclu


def test_sans_transcript():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects = setup(tmp, [msg(T0 + 10, "m1", out=1_000_000)], mention=False)
        r = cost.compute(audit, projects)
        assert r["usd"] is None and r["sessions"] == 0 and r["active_s"] == 0
        r = cost.compute(audit, Path(tmp) / "absent")
        assert r["usd"] is None and r["sessions"] == 0


def test_manuel_prioritaire():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects = setup(tmp, [msg(T0 + 10, "m1", out=1_000_000)])
        cost.save_auto(audit, cost.compute(audit, projects))
        s = cost.summary(audit)
        assert s["source"] == "auto" and abs(s["usd"] - 20.0) < 1e-9 and s["wall_s"] == 7200
        cost.set_manual(audit, 12.5, "facture")
        s = cost.summary(audit)
        assert s["source"] == "manuel" and s["usd"] == 12.5 and s["note"] == "facture"
        cost.set_manual(audit, None, None)
        assert cost.summary(audit)["source"] == "auto"


def test_en_cours():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects = setup(tmp, [msg(T0 + 10, "m1", out=1_000_000)], finished=False)
        assert cost.summary(audit)["wall_s"] > 0, "audit en cours : temps écoulé jusqu'à maintenant"


def test_resume_vide():
    with tempfile.TemporaryDirectory() as tmp:
        s = cost.summary(Path(tmp))
        assert s["usd"] is None and s["source"] is None


def test_match():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects = setup(tmp, [msg(T0 + 10, "m1", out=1_000_000)])
        copy = Path(tmp) / "copie"
        audit.rename(copy)
        assert cost.compute(copy, projects)["sessions"] == 0
        assert cost.compute(copy, projects, match=str(audit))["sessions"] == 1


def test_copie_meme_suffixe():
    """Une copie du dossier d'audit (même <repo>/osho-mantis/<audit>) retrouve ses transcripts"""
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects = setup(tmp, [msg(T0 + 10, "m1", out=1_000_000)])
        dest = Path(tmp) / "ailleurs" / "repo" / "osho-mantis"
        dest.mkdir(parents=True)
        copy = dest / "audit-x"
        audit.rename(copy)
        assert cost.audit_key(copy) == "repo/osho-mantis/audit-x"
        assert cost.compute(copy, projects)["sessions"] == 1


if __name__ == "__main__":
    test_prix()
    test_doublons_message_id()
    test_fenetre()
    test_sous_agents()
    test_modele_inconnu()
    test_temps_actif()
    test_sans_transcript()
    test_manuel_prioritaire()
    test_en_cours()
    test_resume_vide()
    test_match()
    test_copie_meme_suffixe()
    print("OK")
