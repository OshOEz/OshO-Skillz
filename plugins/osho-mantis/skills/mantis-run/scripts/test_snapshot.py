#!/usr/bin/env python3
"""Auto-test de snapshot.py : état complet de l'audit pour le dashboard
  python3 test_snapshot.py
"""
import json
import os
import tempfile
import time
from pathlib import Path

from snapshot import LEVEL_STAGES, append_activity, build_snapshot, diff_events, read_snapshot_safe


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


def test_diff_etape():
    def at(status):
        return snap({"repo": "/x/demo", "level": "Light"}, state={"stages": {"review": status}})
    a = diff_events(at("pending"), at("running"), "2026-10-22T14:00:00")
    done = at("done")
    next(x for x in done["stages"] if x["key"] == "review")["started_at"] = "2026-10-22T14:00:00"
    b = diff_events(at("running"), done, "2026-10-22T14:03:20")
    assert b[0]["duration_s"] == 200 and b[0]["text"] == "Étape Revue terminée en 3 min"
    assert [e["kind"] for e in a + b] == ["stage", "stage"] and a[0]["text"] == "Étape Revue démarrée"
    assert b[0]["text"].startswith("Étape Revue terminée") and b[0]["from"] == "running"


def test_textes_echec_et_saut():
    def st(**k):
        return snap({"repo": "/x/demo", "level": "Light"}, state={"stages": k})
    texts = [e["text"] for e in diff_events(st(plan="pending", review="pending"),
                                            st(plan="failed", review="skipped"), "t")]
    assert texts == ["Étape Plan en échec", "Étape Revue sautée"], texts


def test_lecture_unique():
    # state.json devient illisible juste après la première lecture : jamais de snapshot tout pending
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, {"repo": "/x/demo", "level": "Light"}, state={"stages": {"review": "done"}})
        prev = build_snapshot(d)
        real, calls = Path.read_text, []

        def flaky(self, *a, **k):
            if self.name == "state.json":
                calls.append(1)
                return real(self, *a, **k) if len(calls) == 1 else '{"stages": {"rev'
            return real(self, *a, **k)
        Path.read_text = flaky
        try:
            cur = read_snapshot_safe(d, prev)
        finally:
            Path.read_text = real
        assert cur is prev or diff_events(prev, cur, "t") == []
        assert all(x["status"] != "pending" for x in cur["stages"] if x["key"] == "review")


def test_diff_finding():
    c = {"repo": "/x/demo", "level": "Sharp"}
    s0 = snap(c, state={})
    s1 = snap(c, state={}, findings=[{"id": "a", "title": "Faille A"}])
    s2 = snap(c, state={}, findings=[{"id": "a", "title": "Faille A", "reasoning": "x"}])
    n = diff_events(s0, s1, "t")
    p = diff_events(s1, s2, "t")
    assert [e["kind"] for e in n] == ["finding_new"] and n[0]["finding"] == "f0"
    assert [(e["kind"], e["from"], e["to"]) for e in p] == [("finding_progress", "found", "reviewed")]
    assert p[0]["text"] == "Faille A : Trouvées → Revues"


def test_diff_premier_snapshot():
    assert diff_events(None, snap({"repo": "/x/demo"}), "t") == []


def test_diff_waiting_et_commande():
    c = {"repo": "/x/demo", "level": "Light"}
    s0, s1 = snap(c, state={}), snap(c, state={}, waiting={"kind": "failed"})
    assert diff_events(s0, s1, "t")[0]["waiting_kind"] == "failed"
    s2 = dict(s1, commands={"pending": [], "done": [{"id": "1", "action": "retry", "result": "refused", "reason": "non"}]})
    e = diff_events(s1, s2, "t")
    assert e[0]["text"] == "Action retry refusée : non" and e[0]["kind"] == "command"


def test_json_tronque_ignore():
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, {"repo": "/x/demo", "level": "Light"}, state={"stages": {"review": "done"}})
        prev = build_snapshot(d)
        (d / "state.json").write_text('{"stages": {"rev')
        cur = read_snapshot_safe(d, prev)
        assert cur is prev and diff_events(prev, cur, "t") == []
        (d / "state.json").write_text(json.dumps({"stages": {"review": "done"}}))
        assert read_snapshot_safe(d, prev) is not prev


def test_state_mauvaise_forme():
    for state in ([], {"stages": None, "notes": None}):
        s = snap({"repo": "/x/demo", "level": "Light"}, state=state)
        assert s["stages"][1]["status"] == "pending"
    with tempfile.TemporaryDirectory() as tmp:
        d = audit(tmp, [], state=[], waiting=[])
        s = build_snapshot(d)
        assert s["waiting"] is None and s["stages"][0]["key"] == "triage"


def test_textes_sans_cadratin():
    c = {"repo": "/x/demo", "level": "Light"}
    s0 = snap(c, state={"stages": {"review": "pending"}})
    s1 = snap(c, state={"stages": {"review": "failed", "plan": "skipped"}}, waiting={"kind": "failed"},
              findings=[{"id": "a", "title": "A"}])
    evs = diff_events(s0, s1, "t") + diff_events(s1, dict(s1, commands={"pending": [], "done": [
        {"id": "1", "action": "x", "result": "applied"}]}), "t")
    assert len(evs) >= 5 and all("—" not in e["text"] for e in evs)


def test_append_activity():
    with tempfile.TemporaryDirectory() as tmp:
        append_activity(Path(tmp), [{"a": 1}, {"b": "é"}])
        append_activity(Path(tmp), [])
        append_activity(Path(tmp), [{"c": 3}])
        assert [json.loads(x) for x in (Path(tmp) / "activity.jsonl").read_text().splitlines()] == [
            {"a": 1}, {"b": "é"}, {"c": 3}]


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
    test_diff_etape()
    test_textes_echec_et_saut()
    test_lecture_unique()
    test_diff_finding()
    test_diff_premier_snapshot()
    test_diff_waiting_et_commande()
    test_json_tronque_ignore()
    test_state_mauvaise_forme()
    test_textes_sans_cadratin()
    test_append_activity()
    print("OK")
