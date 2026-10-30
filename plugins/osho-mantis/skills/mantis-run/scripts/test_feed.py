#!/usr/bin/env python3
"""Auto-test de feed.py : fil de Claude en lecture seule depuis les transcripts
  python3 test_feed.py
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import feed

T0 = datetime(2026, 10, 29, 12, 0, tzinfo=timezone.utc).timestamp()


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat().replace("+00:00", "Z")


def asst(t, mid, *blocks):
    return {"type": "assistant", "timestamp": iso(t), "message": {"id": mid, "role": "assistant", "content": list(blocks)}}


def text(s):
    return {"type": "text", "text": s}


def setup(tmp):
    tmp = Path(tmp)
    audit = tmp / "repo" / "osho-mantis" / "audit-x"
    (audit / "workspace").mkdir(parents=True)
    (audit / "inventory.json").write_text("{}")
    os.utime(audit / "inventory.json", (T0, T0))
    proj = tmp / "projects" / "-x"
    (proj / "s1" / "subagents").mkdir(parents=True)
    main = proj / "s1.jsonl"
    lines = [{"type": "user", "timestamp": iso(T0 + 1), "message": {"role": "user", "content": f"/mantis-run {audit}"}},
             asst(T0 + 2, "m1", {"type": "thinking", "thinking": "secret de réflexion"}),
             asst(T0 + 3, "m1", text("Je lance le triage.")),
             asst(T0 + 4, "m1", {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "cat .env"}}),
             {"type": "user", "timestamp": iso(T0 + 5), "message": {"role": "user", "content": [
                 {"type": "tool_result", "tool_use_id": "t1", "content": "API_KEY=supersecret"}]}},
             asst(T0 + 6, "m2", text("x" * 3000))]
    main.write_text("".join(json.dumps(x) + "\n" for x in lines))
    sub = proj / "s1" / "subagents" / "agent-a.jsonl"
    sub.write_text(json.dumps(asst(T0 + 10, "s1", text("Trois findings écrits."))) + "\n")
    (proj / "s1" / "subagents" / "agent-a.meta.json").write_text(json.dumps(
        {"description": "R2 critic groupe 02", "model": "opus", "finished": False}))
    return audit, tmp / "projects", main, sub


def test_texte_assistant_seul():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects, *_ = setup(tmp)
        f = feed.Feed(audit, projects)
        items = f.since(0)["items"]
        texts = [i["text"] for i in items if i["kind"] == "message"]
        assert texts[0] == "Je lance le triage." and len(texts[1]) <= feed.MAX_TEXT + 1
        blob = json.dumps(items, ensure_ascii=False)
        assert "supersecret" not in blob and "cat .env" not in blob and "secret de réflexion" not in blob
        assert "/mantis-run" not in blob, "les entrées utilisateur ne sont pas affichées"
        assert all(i["who"] == "Claude" for i in items if i["kind"] == "message" and i["text"].startswith("Je"))


def test_sous_agent():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects, main, sub = setup(tmp)
        f = feed.Feed(audit, projects)
        items = f.since(0)["items"]
        start = [i for i in items if i["kind"] == "agent_start"]
        assert start and start[0]["who"] == "R2 critic groupe 02" and "opus" in start[0]["text"]
        assert any(i["who"] == "R2 critic groupe 02" and i["text"] == "Trois findings écrits." for i in items)
        meta = sub.with_name("agent-a.meta.json")
        meta.write_text(json.dumps({"description": "R2 critic groupe 02", "model": "opus", "finished": True}))
        after = f.since(items[-1]["seq"])["items"]
        assert [i["kind"] for i in after] == ["agent_end"]


def test_curseur_incremental():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects, main, _ = setup(tmp)
        f = feed.Feed(audit, projects)
        r = f.since(0)
        last = r["last"]
        assert f.since(last)["items"] == []
        with open(main, "a") as fh:
            fh.write(json.dumps(asst(T0 + 20, "m3", text("Étape plan terminée."))) + "\n")
            fh.write('{"type": "assistant", "timest')  # ligne en cours d'écriture : relue au tour suivant
        new = f.since(last)["items"]
        assert [i["text"] for i in new] == ["Étape plan terminée."]
        with open(main, "a") as fh:
            fh.write('amp": "' + iso(T0 + 21) + '", "message": {"id": "m4", "content": [{"type": "text", "text": "Fin."}]}}\n')
        assert [i["text"] for i in f.since(new[-1]["seq"])["items"]] == ["Fin."]


def test_doublons_streaming():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects, main, _ = setup(tmp)
        with open(main, "a") as fh:
            fh.write(json.dumps(asst(T0 + 30, "m9", text("Partie 1."))) + "\n")
            fh.write(json.dumps(asst(T0 + 31, "m9", text("Partie 2."))) + "\n")
        items = feed.Feed(audit, projects).since(0)["items"]
        m9 = [i for i in items if i["text"].startswith("Partie")]
        assert len(m9) == 1 and m9[0]["text"] == "Partie 1.\nPartie 2."


def test_sans_transcript():
    with tempfile.TemporaryDirectory() as tmp:
        audit, *_ = setup(tmp)
        assert feed.Feed(audit, Path(tmp) / "absent").since(0) == {"items": [], "last": 0}


def test_limite():
    with tempfile.TemporaryDirectory() as tmp:
        audit, projects, main, _ = setup(tmp)
        with open(main, "a") as fh:
            for k in range(300):
                fh.write(json.dumps(asst(T0 + 100 + k, f"n{k}", text(f"msg {k}"))) + "\n")
        r = feed.Feed(audit, projects).since(0)
        assert len(r["items"]) == feed.LIMIT and r["items"][-1]["text"] == "msg 299"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
