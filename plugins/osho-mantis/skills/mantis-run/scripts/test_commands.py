#!/usr/bin/env python3
"""Auto-test de commands.py : file d'actions validée
  python3 test_commands.py
"""
import json
import tempfile
from pathlib import Path

import commands
import fixes
from snapshot import build_snapshot
from test_fixes import git_audit, make_ready, scratch
from test_snapshot import audit

F = {"title": "Faille", "severity": "HIGH"}
WAIT = {"kind": "question", "question": "Q ?", "options": [{"value": "a"}, {"value": "b"}]}


def sharp(tmp, **kw):
    kw.setdefault("state", {"stages": {"plan": "failed", "review": "running"}})
    kw.setdefault("findings", [("f1", F)])
    return audit(tmp, {"repo": "/x/demo", "level": "Sharp"}, **kw)


def test_valide_chaque_action():
    with tempfile.TemporaryDirectory() as tmp:
        d = sharp(tmp)
        s = build_snapshot(d)
        for c in ({"action": "pause"}, {"action": "stop"}, {"action": "retry", "stage": "plan"},
                  {"action": "false_positive", "finding": "f1"}, {"action": "prioritize_repro", "finding": "f1"}):
            assert commands.validate(c, s) is None, c
    with tempfile.TemporaryDirectory() as tmp:
        s = build_snapshot(sharp(tmp, state={"paused": True, "stages": {"review": "running"}}))
        assert commands.validate({"action": "resume"}, s) is None
    with tempfile.TemporaryDirectory() as tmp:
        s = build_snapshot(sharp(tmp, waiting=WAIT))
        assert commands.validate({"action": "answer", "question": "Q ?", "value": "a"}, s) is None


def test_refus():
    with tempfile.TemporaryDirectory() as tmp:
        s = build_snapshot(sharp(tmp, state={"stages": {"plan": "done"}}, waiting=WAIT))
        for c in ({"action": "zzz"}, {"action": "false_positive", "finding": "../x"},
                  {"action": "false_positive"}, {"action": "retry", "stage": "plan"},
                  {"action": "answer", "question": "Q ?", "value": "zzz"},
                  {"action": "false_positive", "finding": "f1", "x": "a" * 1100}):
            assert commands.validate(c, s), c
    with tempfile.TemporaryDirectory() as tmp:
        s = build_snapshot(audit(tmp, {"repo": "/x", "level": "Light"}, state={}, findings=[("f1", F)]))
        assert commands.validate({"action": "prioritize_repro", "finding": "f1"}, s)


def test_pending_ack():
    with tempfile.TemporaryDirectory() as tmp:
        d = sharp(tmp)
        a = commands.append(d, {"action": "pause"}, "ui")
        b = commands.append(d, {"action": "stop"}, "ui")
        commands.ack(d, a["id"], "applied")
        commands.ack(d, a["id"], "applied")
        assert [c["id"] for c in commands.pending(d)] == [b["id"]]
        assert len(commands.done(d)) == 1 and commands.done(d)[0]["action"] == "pause"


def test_apply_false_positive():
    with tempfile.TemporaryDirectory() as tmp:
        d = sharp(tmp)
        c = commands.append(d, {"action": "false_positive", "finding": "f1"}, "ui")
        commands.apply(d, c["id"])
        f = json.loads((d / "workspace" / "findings" / "f1.json").read_text())
        assert f["status"] == "FALSE_POSITIVE" and "user_override" in f and commands.pending(d) == []


def test_apply_prioritize_repro_garde_state():
    with tempfile.TemporaryDirectory() as tmp:
        d = sharp(tmp)
        c = commands.append(d, {"action": "prioritize_repro", "finding": "f1"}, "ui")
        commands.apply(d, c["id"])
        st = json.loads((d / "state.json").read_text())
        assert st["force_repro"] == ["f1"] and st["stages"]["review"] == "running"


def test_apply_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        d = sharp(tmp)
        c = commands.append(d, {"action": "false_positive", "finding": "f1"}, "ui")
        commands.apply(d, c["id"])
        at = json.loads((d / "workspace" / "findings" / "f1.json").read_text())["user_override"]["at"]
        r = commands.apply(d, c["id"])
        assert r["result"] == "applied" and len([x for x in commands.done(d) if x["id"] == c["id"]]) == 1
        assert json.loads((d / "workspace" / "findings" / "f1.json").read_text())["user_override"]["at"] == at


def test_apply_devenue_invalide():
    with tempfile.TemporaryDirectory() as tmp:
        d = sharp(tmp)
        c = commands.append(d, {"action": "false_positive", "finding": "f1"}, "ui")
        (d / "workspace" / "findings" / "f1.json").write_text(json.dumps(dict(F, status="FALSE_POSITIVE")))
        assert commands.apply(d, c["id"])["result"] == "refused"


def test_tmp_symlink_non_suivi():
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as out:
        d = sharp(tmp, findings=[("f1", F), ("f2", F)])
        victim = Path(out) / "victime"
        victim.write_text("intact")
        (d / "workspace" / "findings" / "f1.json.tmp").symlink_to(victim)
        (d / "state.json.tmp").symlink_to(victim)
        for c in ({"action": "false_positive", "finding": "f1"}, {"action": "prioritize_repro", "finding": "f2"}):
            assert commands.apply(d, commands.append(d, c, "ui")["id"])["result"] == "applied"
        assert victim.read_text() == "intact"
        assert not (d / "workspace" / "findings" / "f1.json").is_symlink() and not (d / "state.json").is_symlink()
        assert json.loads((d / "workspace" / "findings" / "f1.json").read_text())["status"] == "FALSE_POSITIVE"
        assert json.loads((d / "state.json").read_text())["force_repro"] == ["f2"]


def test_ack_copie_la_cible():
    with tempfile.TemporaryDirectory() as tmp:
        d = sharp(tmp)
        r = commands.append(d, {"action": "retry", "stage": "plan"}, "ui")
        f = commands.append(d, {"action": "false_positive", "finding": "f1"}, "ui")
        commands.ack(d, r["id"], "applied")
        commands.apply(d, f["id"])
        by = {x["id"]: x for x in commands.done(d)}
        assert by[r["id"]]["stage"] == "plan" and "finding" not in by[r["id"]]
        assert by[f["id"]]["finding"] == "f1" and "stage" not in by[f["id"]]


def _fx(tmp, fx=None, state=None, finding=F):
    return audit(tmp, {"repo": "/x/demo", "level": "Sharp"}, fixes=fx, findings=[("f1", finding)],
                 state=state or {"stages": {"review": "running"}})


def test_valide_fix():
    with tempfile.TemporaryDirectory() as tmp:
        assert commands.validate({"action": "fix", "finding": "f1"}, build_snapshot(_fx(tmp))) is None
    with tempfile.TemporaryDirectory() as tmp:
        s = build_snapshot(_fx(tmp, {"f1": {"status": "conflict"}}))
        assert commands.validate({"action": "fix", "finding": "f1"}, s) is None
    with tempfile.TemporaryDirectory() as tmp:
        s = build_snapshot(_fx(tmp, {"f1": {"status": "ready"}}))
        assert commands.validate({"action": "merge_fix", "finding": "f1"}, s) is None


def test_refus_fix():
    with tempfile.TemporaryDirectory() as tmp:
        s = build_snapshot(_fx(tmp, finding={"title": "x", "status": "FALSE_POSITIVE"}))
        assert commands.validate({"action": "fix", "finding": "f1"}, s)
    for st in ("running", "ready", "merged"):
        with tempfile.TemporaryDirectory() as tmp:
            s = build_snapshot(_fx(tmp, {"f1": {"status": st}}))
            assert commands.validate({"action": "fix", "finding": "f1"}, s), st
            assert commands.validate({"action": "end_fixes"}, s)
            if st == "running":
                assert commands.validate({"action": "merge_fix", "finding": "f1"}, s)
    with tempfile.TemporaryDirectory() as tmp:
        s = build_snapshot(_fx(tmp, state={"finished": True}))
        assert s["listening"] == "none" and commands.validate({"action": "fix", "finding": "f1"}, s)
        assert commands.validate({"action": "fix", "finding": "../x"}, s)
    with tempfile.TemporaryDirectory() as tmp:
        d = _fx(tmp)
        commands.append(d, {"action": "fix", "finding": "f1"}, "ui")
        assert commands.validate({"action": "fix", "finding": "f1"}, build_snapshot(d))


def test_apply_fix_en_file():
    with tempfile.TemporaryDirectory() as tmp:
        d = _fx(tmp)
        c = commands.append(d, {"action": "fix", "finding": "f1"}, "ui")
        r = commands.apply(d, c["id"])
        assert r["result"] == "applied"
        e = fixes.load(d)["f1"]
        assert e["status"] == "queued" and e["cmd"] == c["id"]
        assert commands.apply(d, c["id"]) == r


def test_apply_merge():
    for fin in (False, True):
        with scratch() as tmp:
            d, repo = git_audit(tmp, state={"finished": True} if fin else None)
            make_ready(d, "f1")
            c = commands.append(d, {"action": "merge_fix", "finding": "f1"}, "ui")
            assert commands.apply(d, c["id"])["result"] == "applied"
            assert fixes.load(d)["f1"]["status"] == "merged"
            assert (d / "README.md").exists() == fin


def test_apply_merge_conflit_refuse():
    with scratch() as tmp:
        d, repo = git_audit(tmp, findings=(("f1", F), ("f2", F)))
        make_ready(d, "f1", text="autre")
        make_ready(d, "f2")
        for stem in ("f1", "f2"):
            r = commands.apply(d, commands.append(d, {"action": "merge_fix", "finding": stem}, "ui")["id"])
        assert r["result"] == "refused" and r["reason"] == "conflit avec un autre correctif"


def test_apply_merge_erreur_refusee():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        make_ready(d, "f1")
        data = fixes.load(d)
        data["f1"].pop("base")
        (d / "fixes.json").write_text(json.dumps(data))
        c = commands.append(d, {"action": "merge_fix", "finding": "f1"}, "ui")
        r = commands.apply(d, c["id"])
        assert r["result"] == "refused" and "incomplète" in r["reason"]


def test_apply_merge_rendu_en_echec():
    import render
    with scratch() as tmp:
        d, repo = git_audit(tmp, state={"finished": True})
        make_ready(d, "f1")
        c = commands.append(d, {"action": "merge_fix", "finding": "f1"}, "ui")
        orig, render.render = render.render, lambda *_: (_ for _ in ()).throw(RuntimeError("boum"))
        try:
            r = commands.apply(d, c["id"])
        finally:
            render.render = orig
        assert r["result"] == "applied" and fixes.load(d)["f1"]["status"] == "merged"


def test_apply_merge_deja_fusionne_sans_accuse():
    with scratch() as tmp:
        d, repo = git_audit(tmp)
        make_ready(d, "f1")
        c = commands.append(d, {"action": "merge_fix", "finding": "f1"}, "ui")
        assert fixes.merge(d, "f1")[0] == "merged"  # plantage avant l'accusé
        assert commands.apply(d, c["id"])["result"] == "applied"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
