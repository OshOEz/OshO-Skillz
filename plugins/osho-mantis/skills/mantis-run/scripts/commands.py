#!/usr/bin/env python3
"""File d'actions du dashboard : commands.jsonl (demandes) et commands-done.jsonl (accusés)"""
import json
import math
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path

ACTIONS = {"pause", "resume", "stop", "retry", "answer", "false_positive", "prioritize_repro", "fix", "merge_fix", "end_fixes",
           "set_cost", "recompute_cost", "launch"}
SERVER_ACTIONS = {"merge_fix", "set_cost", "recompute_cost"}  # appliquées par le serveur, sans session Claude
# sans session à l'écoute, mises en file pour la prochaine session mantis-run (les autres : 409)
QUEUEABLE = {"launch", "resume", "retry", "fix", "false_positive", "prioritize_repro"}
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
    elif action == "set_cost":
        usd, note = cmd.get("usd", "absent"), cmd.get("note")
        if usd is not None and (isinstance(usd, bool) or not isinstance(usd, (int, float))
                                or not math.isfinite(usd) or usd < 0):
            return "montant invalide (nombre positif, ou vide pour revenir au calcul automatique)"
        if note is not None and (not isinstance(note, str) or len(note) > 200):
            return "note invalide (200 caractères maximum)"
    elif action == "recompute_cost":
        pass
    elif action == "launch":
        if meta["finished"]:
            return "l'audit est déjà terminé"
        if not meta["stopped"] and any(s["status"] != "pending" for s in snap["stages"] if s["key"] != "triage"):
            return "l'audit est déjà lancé"
        if any(c.get("action") == "launch" for c in snap["commands"]["pending"]):
            return "lancement déjà demandé"
    elif action == "end_fixes":
        if snap["listening"] != "fixes":
            return "le mode Corrections n'est pas actif"
    else:  # false_positive, prioritize_repro, fix, merge_fix
        f = {x["_src"]: x for x in snap["findings"]}.get(cmd.get("finding"))
        if f is None:
            return "finding introuvable"
        if f["_bucket"] == "REJECTED":
            return "finding déjà écarté"
        st = (f["_fix"] or {}).get("status")
        if action == "fix":  # session à l'écoute : contrôlée par le POST (409), mantis-run qui applique est la session
            if st not in (None, "failed", "conflict") and not (st == "queued" and f["_fix"].get("cmd") == cmd.get("id")):
                return "déjà fusionné" if st == "merged" else "correction déjà demandée"
        elif action == "merge_fix":
            if st != "ready":
                return "le correctif n'est pas prêt"
        elif action == "prioritize_repro":
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
    with open(path, "a", encoding="utf-8", errors="replace") as fh:
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
    entry = {"id": cmd_id, "action": orig.get("action"), "result": result, "reason": reason, "at": _now()}
    entry.update({k: orig[k] for k in ("stage", "finding") if k in orig})
    _write_line(Path(audit_dir) / "commands-done.jsonl", entry)


def atomic_write(path, text, mode=0o644):
    """Écrit via <path>.tmp sans jamais suivre un lien planté à cet endroit, puis remplace path"""
    tmp = Path(f"{path}.tmp")
    tmp.unlink(missing_ok=True)  # supprime le lien lui-même, pas sa cible
    fd = os.open(tmp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _atomic_json(path, data):
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))


def _render_if_finished(audit_dir):
    """Le README suit la fusion ; un échec de rendu ne défait pas la fusion"""
    import render
    try:
        state = render.load_json(Path(audit_dir) / "state.json", {})
        if isinstance(state, dict) and state.get("finished"):
            render.render(audit_dir)
    except Exception as e:
        print(f"rendu du README impossible : {e}", file=sys.stderr)


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
    if cmd.get("action") not in ("false_positive", "prioritize_repro", "fix", "merge_fix", "set_cost", "recompute_cost"):
        raise ValueError("à traiter par mantis-run")
    if cmd["action"] in ("set_cost", "recompute_cost"):
        import cost
        reason = validate(cmd, snapshot.build_snapshot(audit_dir))
        if reason:
            ack(audit_dir, cmd_id, "refused", reason)
        else:
            if cmd["action"] == "set_cost":
                cost.set_manual(audit_dir, cmd.get("usd"), cmd.get("note"))
            else:
                cost.save_auto(audit_dir, cost.compute(audit_dir))
            ack(audit_dir, cmd_id, "applied")
        return existing()
    merged = False
    if cmd["action"] == "merge_fix":
        import fixes
        # plantage entre la fusion et l'accusé : la fusion est faite, on ne la refuse pas
        e = fixes.load(audit_dir).get(cmd["finding"]) if not _bad(cmd.get("finding")) else None
        merged = isinstance(e, dict) and e.get("status") == "merged"
    reason = None if merged else validate(cmd, snapshot.build_snapshot(audit_dir))
    if reason:
        ack(audit_dir, cmd_id, "refused", reason)
        return existing()
    if cmd["action"] in ("fix", "merge_fix"):
        import fixes
        try:
            if cmd["action"] == "fix":
                fixes.queue(audit_dir, cmd["finding"], cmd_id)
            elif not merged:
                result, why = fixes.merge(audit_dir, cmd["finding"])
                if result != "merged":
                    ack(audit_dir, cmd_id, "refused", why)
                    return existing()
                merged = True
        except (ValueError, RuntimeError) as e:
            ack(audit_dir, cmd_id, "refused", str(e))
            return existing()
        if merged:
            _render_if_finished(audit_dir)
    elif cmd["action"] == "false_positive":
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
