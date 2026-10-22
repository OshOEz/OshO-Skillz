#!/usr/bin/env python3
"""Auto-test de commands.py : file d'actions validée
  python3 test_commands.py
"""
import json
import tempfile
from pathlib import Path

import commands
from snapshot import build_snapshot
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
