#!/usr/bin/env python3
"""Auto-test de snapshot.py : état complet de l'audit pour le dashboard
  python3 test_snapshot.py
"""
import json
import os
import tempfile
import time
from pathlib import Path

from snapshot import LEVEL_STAGES, build_snapshot


def audit(tmp, campaign, state=None, findings=(), waiting=None, activity=()):
    d = Path(tmp)
    (d / "workspace" / "findings").mkdir(parents=True)
    (d / "campaign.json").write_text(json.dumps(campaign))
    if state is not None:
        (d / "state.json").write_text(json.dumps(state))
    for i, f in enumerate(findings):
        name, body = f if isinstance(f, tuple) else (f"f{i}", f)
        (d / "workspace" / "findings" / f"{name}.json").write_text(json.dumps(body))
    if waiting is not None:
        (d / "waiting.json").write_text(json.dumps(waiting))
    if activity:
        (d / "activity.jsonl").write_text("\n".join(json.dumps(a) for a in activity) + "\n")
    return d


def snap(campaign, mode="live", **kw):
    with tempfile.TemporaryDirectory() as tmp:
        return build_snapshot(audit(tmp, campaign, **kw), mode)


def test_snapshot_triage_seul():
    s = snap({"repo": "/x/demo"})
    assert s["stages"][0]["key"] == "triage" and s["stages"][0]["code"] == "TRI"
    assert s["stages"][0]["status"] == "running" and s["listening"] == "working"
    assert s["findings"] == [] and s["commands"] == {"pending": [], "done": []} and s["current"] is None


def test_snapshot_sharp_en_cours():
    s = snap({"repo": "/x/demo", "level": "Sharp"},
             state={"stages": {"architecture": "done", "review": "running"}})
    assert [x["key"] for x in s["stages"]] == ["triage"] + LEVEL_STAGES["Sharp"]
    by = {x["key"]: x["status"] for x in s["stages"]}
    assert by["triage"] == "done" and by["architecture"] == "done"
    assert by["review"] == "running" and by["critic"] == "pending" and s["listening"] == "working"


def test_niveau_inconnu():
    s = snap({"repo": "/x/demo", "level": "Zzz"}, state={"stages": {"b": "done", "a": "running"}})
    assert [x["key"] for x in s["stages"]] == ["triage", "b", "a"]


def test_snapshot_failed_et_waiting():
    s = snap({"repo": "/x/demo", "level": "Sharp"}, state={"stages": {"plan": "failed"}},
             waiting={"kind": "failed", "stage": "plan", "reason": "x"})
    assert s["listening"] == "waiting" and s["waiting"]["stage"] == "plan"


def test_snapshot_fini():
    s = snap({"repo": "/x/demo", "level": "Sharp"},
             state={"stages": {"review": "running"}, "finished": True})
    assert s["listening"] == "none" and s["meta"]["finished"] is True


def test_progress_colonnes():
    fs = [{"id": "rej", "title": "r", "status": "FALSE_POSITIVE", "patch_status": "VERIFIED_SECURE"},
          {"id": "fix", "title": "f", "patch_status": "MITIGATION_PROPOSED", "repro_status": "reproduced"},
          {"id": "rep", "title": "p", "repro_status": "reproduced", "production_viability": "VIABLE"},
          {"id": "eva", "title": "e", "production_viability": "VIABLE", "reasoning": "x"},
          {"id": "rev", "title": "v", "reasoning": "x"},
          {"id": "fou", "title": "o"}]
    s = snap({"repo": "/x/demo", "level": "Sharp"}, state={}, findings=fs)
    got = {f["id"]: f["_progress"] for f in s["findings"]}
    assert got == {"rej": "rejected", "fix": "fixed", "rep": "reproduced", "eva": "evaluated",
                   "rev": "reviewed", "fou": "found"}, got
    assert s["progress_columns"] == ["found", "reviewed", "evaluated", "reproduced", "fixed"]
    assert snap({"repo": "/x/demo", "level": "Light"})["progress_columns"] == ["found", "reviewed", "fixed"]


def test_overkill_tour_2():
    s = snap({"repo": "/x/demo", "level": "Overkill"}, state={"stages": {}, "round": 2})
    assert s["meta"]["round"] == 2 and len(s["stages"]) == 15


def test_src_et_file():
    s = snap({"repo": "/x/demo", "level": "Light"}, state={},
             findings=[("a", {"id": "x", "title": "A"}), ("b", {"id": "x", "title": "B"})])
    assert {f["_src"] for f in s["findings"]} == {"a", "b"}
    assert len({f["_file"] for f in s["findings"]}) == 2


def test_durees():
    ev = [{"kind": "stage", "stage": "plan", "to": "running", "at": "2026-10-22T14:00:00"},
          {"kind": "stage", "stage": "plan", "to": "done", "at": "2026-10-22T14:04:00"}]
    s = snap({"repo": "/x/demo", "level": "Light"}, state={"stages": {"plan": "done"}}, activity=ev)
    plan = next(x for x in s["stages"] if x["key"] == "plan")
    assert plan["duration_s"] == 240 and plan["started_at"] == "2026-10-22T14:00:00"
    assert s["stages"][0]["duration_s"] is None


def test_stale():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, {"repo": "/x/demo", "level": "Light"}, state={"stages": {"plan": "running"}})
        old = time.time() - 1300
        for p in [d / "campaign.json", d / "state.json", d / "workspace" / "findings"]:
            os.utime(p, (old, old))
        assert build_snapshot(d)["stale"] is True
        assert build_snapshot(d, now=old + 10)["stale"] is False


if __name__ == "__main__":
    test_snapshot_triage_seul()
    test_snapshot_sharp_en_cours()
    test_niveau_inconnu()
    test_snapshot_failed_et_waiting()
    test_snapshot_fini()
    test_progress_colonnes()
    test_overkill_tour_2()
    test_src_et_file()
    test_durees()
    test_stale()
    print("OK")
