#!/usr/bin/env python3
"""File d'actions du dashboard : commands.jsonl (demandes) et commands-done.jsonl (accusés)"""
import json
import os
import secrets
from datetime import datetime
from pathlib import Path

ACTIONS = {"pause", "resume", "stop", "retry", "answer", "false_positive", "prioritize_repro"}
MAX_BYTES = 1024


def _bad(v):
    return not isinstance(v, str) or any(x in v for x in ("/", "\\", ".."))


def validate(cmd, snap):
    """None si la commande est valide, sinon la raison en français"""
    if not isinstance(cmd, dict):
        return "commande illisible"
    action = cmd.get("action")
    if action not in ACTIONS:
        return f"action inconnue : {action}"
    if len(json.dumps(cmd, ensure_ascii=False).encode()) > MAX_BYTES:
        return "commande trop longue (1 Ko maximum)"
    for k in ("finding", "stage"):
        if k in cmd and _bad(cmd[k]):
            return f"{k} invalide"
    meta, waiting = snap["meta"], snap.get("waiting")
    if action == "pause":
        if snap["listening"] != "working" or meta["paused"]:
            return "l'audit n'est pas en cours"
    elif action == "resume":
        if not meta["paused"]:
            return "l'audit n'est pas en pause"
    elif action == "stop":
        if meta["finished"]:
            return "l'audit est déjà terminé"
    elif action == "retry":
        if {s["key"]: s["status"] for s in snap["stages"]}.get(cmd.get("stage")) != "failed":
            return "l'étape n'est pas en échec"
    elif action == "answer":
        if not waiting or waiting.get("kind") != "question":
            return "aucune question en attente"
        if cmd.get("question") != waiting.get("question"):
            return "la question a changé"
        if cmd.get("value") not in [o.get("value") for o in waiting.get("options") or [] if isinstance(o, dict)]:
            return "réponse hors des options"
    else:  # false_positive, prioritize_repro
        f = {x["_src"]: x for x in snap["findings"]}.get(cmd.get("finding"))
        if f is None:
            return "finding introuvable"
        if f["_bucket"] == "REJECTED":
            return "finding déjà écarté"
        if action == "prioritize_repro":
            by = {s["key"]: s["status"] for s in snap["stages"]}
            if "reproduce" not in by:
                return "pas d'étape de reproduction à ce niveau"
            if by["reproduce"] == "done":
                return "la reproduction est terminée"
    return None


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _read(path):
    """Lignes valides d'un jsonl (une ligne tronquée est ignorée)"""
    out = []
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if isinstance(e, dict):
            out.append(e)
    return out


def _write_line(path, obj):
    with open(path, "a") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")


def append(audit_dir, cmd, source):
    cmd = dict(cmd, id=secrets.token_hex(8), at=_now(), source=source)
    _write_line(Path(audit_dir) / "commands.jsonl", cmd)
    return cmd


def done(audit_dir):
    return _read(Path(audit_dir) / "commands-done.jsonl")


def pending(audit_dir):
    acked = {c.get("id") for c in done(audit_dir)}
    return [c for c in _read(Path(audit_dir) / "commands.jsonl") if c.get("id") not in acked]


def ack(audit_dir, cmd_id, result, reason=None):
    if any(c.get("id") == cmd_id for c in done(audit_dir)):
        return
    orig = next((c for c in _read(Path(audit_dir) / "commands.jsonl") if c.get("id") == cmd_id), {})
    _write_line(Path(audit_dir) / "commands-done.jsonl",
                {"id": cmd_id, "action": orig.get("action"), "result": result, "reason": reason, "at": _now()})


def _atomic_json(path, data):
    tmp = Path(f"{path}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def apply(audit_dir, cmd_id):
    import snapshot  # import tardif : snapshot importe commands
    audit_dir = Path(audit_dir)

    def existing():
        return next((c for c in done(audit_dir) if c.get("id") == cmd_id), None)

    if existing():
        return existing()
    cmd = next((c for c in _read(audit_dir / "commands.jsonl") if c.get("id") == cmd_id), None)
    if cmd is None:
        raise ValueError("commande inconnue")
    if cmd.get("action") not in ("false_positive", "prioritize_repro"):
        raise ValueError("à traiter par mantis-run")
    reason = validate(cmd, snapshot.build_snapshot(audit_dir))
    if reason:
        ack(audit_dir, cmd_id, "refused", reason)
        return existing()
    if cmd["action"] == "false_positive":
        p = audit_dir / "workspace" / "findings" / f"{cmd['finding']}.json"
        f = json.loads(p.read_text())
        f["status"] = "FALSE_POSITIVE"
        f["user_override"] = {"action": "false_positive", "at": _now()}
        _atomic_json(p, f)
    else:
        p = audit_dir / "state.json"
        st = json.loads(p.read_text()) if p.exists() else {}
        force = st.get("force_repro") if isinstance(st.get("force_repro"), list) else []
        if cmd["finding"] not in force:
            st["force_repro"] = force + [cmd["finding"]]
            _atomic_json(p, st)
    ack(audit_dir, cmd_id, "applied")
    return existing()
