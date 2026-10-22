#!/usr/bin/env python3
"""Snapshot de l'audit : modèle de données unique du serveur, de la page et de render.py
  build_snapshot(dossier d'audit, mode="live"|"final") -> dict
"""
import json
import time
from datetime import datetime
from pathlib import Path

import render

_ALL = ["history", "structural-index", "architecture", "threat-model", "plan", "researcher", "dedupe",
        "review", "critic", "reproduce", "chain", "patch", "calibrate", "reflect"]
LEVEL_STAGES = {
    "Light": ["architecture", "threat-model", "plan", "researcher", "review", "patch"],
    "Sharp": [k for k in _ALL if k not in ("history", "chain", "reflect")],
    "Savage": _ALL,
    "Overkill": _ALL,
}
STAGE_CODES = {"triage": "TRI", "history": "HIS", "structural-index": "IDX", "architecture": "ARC",
               "threat-model": "THR", "plan": "PLN", "researcher": "RSC", "dedupe": "DDP", "review": "REV",
               "critic": "CRT", "reproduce": "REP", "chain": "CHN", "patch": "PAT", "calibrate": "CAL",
               "reflect": "RFL"}
STAGE_NAMES = {"triage": "Triage", "history": "Historique", "structural-index": "Index structurel",
               "architecture": "Architecture", "threat-model": "Modèle de menaces", "plan": "Plan",
               "researcher": "Recherche", "dedupe": "Dédoublonnage", "review": "Revue", "critic": "Critique",
               "reproduce": "Reproduction", "chain": "Chaînes d'exploits", "patch": "Correctifs",
               "calibrate": "Calibrage", "reflect": "Réflexion"}
STALE_S = 1200
END = {"done", "failed", "skipped"}


def progress(f):
    if render.bucket(f) == "REJECTED":
        return "rejected"
    if f.get("patch_status") in ("VERIFIED_SECURE", "MITIGATION_PROPOSED"):
        return "fixed"
    if f.get("repro_status") == "reproduced":
        return "reproduced"
    if f.get("production_viability"):
        return "evaluated"
    return "reviewed" if f.get("reasoning") else "found"


def assign_files(findings):
    """_file : nom de fichier unique (patch, ancre de page), dédoublonné parmi tous les noms déjà pris"""
    used = set()
    for f in findings:
        name = render.safe_id(f)
        suffix = 2
        while name in used:
            name = f"{render.safe_id(f)}-{suffix}"
            suffix += 1
        used.add(name)
        f["_file"] = name


def read_activity(path):
    """Lignes valides de activity.jsonl (une ligne tronquée est ignorée)"""
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


def timing(activity, key):
    """(started_at, duration_s) d'une étape : dernier passage à running, puis fin éventuelle"""
    start = end = None
    for e in activity:
        if e.get("kind") != "stage" or e.get("stage") != key:
            continue
        if e.get("to") == "running":
            start, end = e.get("at"), None
        elif e.get("to") in END and start and end is None:
            end = e.get("at")
    try:
        return start, int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
    except (TypeError, ValueError):
        return start, None


def build_snapshot(audit_dir, mode="live", now=None):
    audit_dir = Path(audit_dir).resolve()
    now = time.time() if now is None else now
    campaign = render.load_json(audit_dir / "campaign.json", {})
    state = render.load_json(audit_dir / "state.json", {})
    waiting = render.load_json(audit_dir / "waiting.json", None)
    findings, _ = render.load_findings(audit_dir / "workspace")
    assign_files(findings)
    activity = read_activity(audit_dir / "activity.jsonl")
    done_stages = state.get("stages", {})
    level = campaign.get("level")
    keys = LEVEL_STAGES.get(level) or list(done_stages)
    stages = []
    for key in ["triage"] + keys:
        status = ("done" if level else "running") if key == "triage" else done_stages.get(key, "pending")
        started, dur = timing(activity, key)
        stages.append({"key": key, "code": STAGE_CODES.get(key, key[:3].upper()), "name": STAGE_NAMES.get(key, key),
                       "status": status, "duration_s": dur, "started_at": started,
                       "notes": [n for n in state.get("notes", []) if key in str(n)]})
    finished, stopped = bool(state.get("finished")), bool(state.get("stopped"))
    if finished or stopped:
        listening = "none"
    elif waiting is not None:
        listening = "waiting"
    else:
        listening = "working" if any(s["status"] == "running" for s in stages) else "none"
    watched = [audit_dir / n for n in ("campaign.json", "state.json", "waiting.json", "activity.jsonl")]
    watched += [audit_dir / "workspace" / "findings"] + list((audit_dir / "workspace" / "findings").glob("*.json"))
    mtimes = [p.stat().st_mtime for p in watched if p.exists()]
    age = int(now - max(mtimes)) if mtimes else 0
    meta = {"repo_name": Path(campaign.get("repo") or audit_dir.parent.parent).name,
            "audit_name": audit_dir.name, "level": level,
            "mantis_commit": campaign.get("mantis_commit"), "started_at": campaign.get("started_at"),
            "duration": render.duration(campaign.get("started_at"), campaign.get("finished_at")),
            "notes": state.get("notes", []),
            "stages": [k for k, v in done_stages.items() if v == "done"],
            "round": state.get("round"), "finished": finished, "stopped": stopped,
            "paused": bool(state.get("paused")), "audit_age_s": age}
    meta["reproduce_done"] = "reproduce" in meta["stages"]
    meta["level_banner"] = render.LEVEL_BANNERS.get(level, "")
    return {"mode": mode, "generated_at": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
            "meta": meta, "stats": render.stats(findings), "labels": render.ENUM_LABELS, "stages": stages,
            "current": state.get("current"), "waiting": waiting, "listening": listening,
            "stale": listening == "working" and age > STALE_S,
            "findings": [dict(f, _bucket=render.bucket(f), _summary=render.summary(f), _progress=progress(f))
                         for f in sorted(findings, key=render.sort_key)],
            "progress_columns": (["found", "reviewed", "fixed"] if level == "Light"
                                 else ["found", "reviewed", "evaluated", "reproduced", "fixed"]),
            "activity": activity[-200:], "commands": {"pending": [], "done": []}}
