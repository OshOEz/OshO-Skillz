#!/usr/bin/env python3
"""Snapshot de l'audit : modèle de données unique du serveur, de la page et de render.py
  build_snapshot(dossier d'audit, mode="live"|"final") -> dict
"""
import json
import time
from datetime import datetime
from pathlib import Path

import commands
import fixes
import cost
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
    if (f.get("_fix") or {}).get("status") == "merged":
        return "fixed"
    if f.get("patch_status"):
        return "proposed"
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


def timing(activity, key, start=None, default_end=None):
    """(started_at, duration_s) d'une étape : dernier passage à running, puis fin éventuelle ;
    start/default_end : valeurs par défaut quand le journal n'en a pas (triage, vu par le serveur déjà en cours)"""
    end = None
    for e in activity:
        if e.get("kind") != "stage" or e.get("stage") != key:
            continue
        if e.get("to") == "running":
            start, end = e.get("at"), None
        elif e.get("to") in END and start and end is None:
            end = e.get("at")
    end = end or default_end
    try:
        return start, int((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds())
    except (TypeError, ValueError):
        return start, None


def stage_rounds(activity):
    """{(étape, tour): durée cumulée} depuis le journal ; un événement sans « round » prend le tour
    compté par les démarrages de plan (k-ième démarrage = tour k ; avant le premier, tour 1)"""
    out, rnd = {}, 0
    for e in activity:
        if e.get("kind") != "stage":
            continue
        if "round" not in e and e.get("stage") == "plan" and e.get("to") == "running":
            rnd += 1
        r = e.get("round") or max(rnd, 1)
        if e.get("to") == "done":
            d = e.get("duration_s")
            k = (e.get("stage"), r)
            out[k] = (out.get(k) or 0) + d if isinstance(d, (int, float)) else out.get(k)
    return out


def cycle(stages, level, rnd, activity):
    """Vue Cycle : préparation (jusqu'à threat-model), puis une rangée par tour (plan → dernière étape)"""
    keys = [s["key"] for s in stages]
    cut = keys.index("plan") if "plan" in keys else len(keys)
    durs = stage_rounds(activity)
    pick = lambda s, **kw: dict({k: s[k] for k in ("key", "code", "name", "status", "duration_s")}, **kw)
    prep = [pick(s, duration_s=s["duration_s"] if (s["key"], 1) not in durs else durs[(s["key"], 1)])
            for s in stages[:cut]]
    rnd = rnd if isinstance(rnd, int) and rnd >= 1 else 1
    rounds = []
    for r in range(1, rnd + 1):
        cur = r == rnd
        rounds.append({"round": r, "stages": [pick(s, status=s["status"] if cur else "done", duration_s=durs.get((s["key"], r)))
                                              for s in stages[cut:]]})
    return {"prep": prep, "rounds": rounds, "max_rounds": 3 if level == "Overkill" else 1}


def build_snapshot(audit_dir, mode="live", now=None, loaded=None):
    """loaded : campaign/state/waiting déjà lus (read_snapshot_safe), pour ne lire chaque fichier qu'une fois"""
    audit_dir = Path(audit_dir).resolve()
    now = time.time() if now is None else now
    # un JSON de mauvaise forme (liste, null) vaut un fichier vide
    loaded = loaded or {}
    campaign = loaded["campaign"] if "campaign" in loaded else render.load_json(audit_dir / "campaign.json", {})
    state = loaded["state"] if "state" in loaded else render.load_json(audit_dir / "state.json", {})
    waiting = loaded["waiting"] if "waiting" in loaded else render.load_json(audit_dir / "waiting.json", None)
    campaign, state = (x if isinstance(x, dict) else {} for x in (campaign, state))
    waiting = waiting if isinstance(waiting, dict) else None
    notes = state.get("notes") if isinstance(state.get("notes"), list) else []
    findings, _ = render.load_findings(audit_dir / "workspace", loaded.get("carry"))
    assign_files(findings)
    fix_entries = loaded["fixes"] if isinstance(loaded.get("fixes"), dict) else fixes.load(audit_dir)
    pending_cmds = commands.pending(audit_dir)
    pending_fix = {}
    for c in pending_cmds:
        if c.get("action") == "fix":
            pending_fix.setdefault(c.get("finding"), c.get("id"))
    for f in findings:
        e = fix_entries.get(f["_src"])
        e = e if isinstance(e, dict) else {}
        if e.get("status") not in ("queued", "running", "ready", "merged") and f["_src"] in pending_fix:
            f["_fix"] = {"status": "queued", "cmd": pending_fix[f["_src"]]}  # relance après failed/conflict incluse
        else:
            f["_fix"] = {k: e[k] for k in ("status", "error", "branch", "commit", "merge_commit", "cmd", "at")
                         if k in e} if e else None
    activity = read_activity(audit_dir / "activity.jsonl")
    done_stages = state.get("stages") if isinstance(state.get("stages"), dict) else {}
    level = campaign.get("level")
    keys = LEVEL_STAGES.get(level) or list(done_stages)
    inv = audit_dir / "inventory.json"  # écrit au début du triage
    try:
        tri_start = datetime.fromtimestamp((inv if inv.exists() else audit_dir).stat().st_mtime).isoformat(
            timespec="seconds")
    except OSError:  # dossier supprimé pendant la lecture
        tri_start = None
    stages = []
    for key in ["triage"] + keys:
        status = ("done" if level else "running") if key == "triage" else done_stages.get(key, "pending")
        started, dur = (timing(activity, key, tri_start, campaign.get("started_at") if level else None)
                        if key == "triage" else timing(activity, key))
        stages.append({"key": key, "code": STAGE_CODES.get(key, key[:3].upper()), "name": STAGE_NAMES.get(key, key),
                       "status": status, "duration_s": dur, "started_at": started,
                       "notes": [n for n in notes if key in str(n)]})
    finished, stopped = bool(state.get("finished")), bool(state.get("stopped"))
    if waiting is not None and waiting.get("kind") == "fixes":
        listening = "fixes"
    elif finished or stopped:
        listening = "none"
    elif waiting is not None:
        listening = "waiting"
    else:
        listening = "working" if any(s["status"] == "running" for s in stages) else "none"
    watched = [audit_dir / n for n in ("campaign.json", "state.json", "waiting.json", "activity.jsonl", "fixes.json",
                                       "cost.json")]
    watched += [audit_dir / "workspace" / "findings"] + list((audit_dir / "workspace" / "findings").glob("*.json"))
    mtimes = [p.stat().st_mtime for p in watched if p.exists()]
    age = int(now - max(mtimes)) if mtimes else 0
    meta = {"repo_name": Path(campaign.get("repo") or audit_dir.parent.parent).name,
            "audit_name": audit_dir.name, "level": level,
            "mantis_commit": campaign.get("mantis_commit"), "started_at": campaign.get("started_at"),
            "duration": render.duration(campaign.get("started_at"), campaign.get("finished_at")),
            "notes": notes,
            "stages": [k for k, v in done_stages.items() if v == "done"],
            "round": state.get("round"), "finished": finished, "stopped": stopped,
            "paused": bool(state.get("paused")), "audit_age_s": age,
            "audit_branch": fixes.audit_branch(audit_dir), "audit_branch_ok": fixes.audit_branch_ok(audit_dir),
            "fixes_merged": sum(1 for e in fix_entries.values() if isinstance(e, dict) and e.get("status") == "merged"),
            "dirty_before": bool(state.get("git_status_before"))}
    meta["reproduce_done"] = "reproduce" in meta["stages"]
    meta["cost"] = cost.summary(audit_dir)
    meta["level_banner"] = render.LEVEL_BANNERS.get(level, "")
    return {"mode": mode, "generated_at": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
            "meta": meta, "stats": render.stats(findings), "labels": render.ENUM_LABELS, "stages": stages,
            "current": state.get("current"),
            "cycle": cycle(stages, level, state.get("round"), activity), "waiting": waiting, "listening": listening,
            "stale": listening == "working" and age > STALE_S,
            "findings": [dict(f, _bucket=render.bucket(f), _summary=render.summary(f), _progress=progress(f))
                         for f in sorted(findings, key=render.sort_key)],
            "progress_columns": (["found", "reviewed", "proposed", "fixed"] if level == "Light"
                                 else ["found", "reviewed", "evaluated", "reproduced", "proposed", "fixed"]),
            "activity": activity[-200:], "commands": {"pending": pending_cmds[-50:],
                         "done": commands.done(audit_dir)[-50:]}}


COLUMN_LABELS = {"found": "Trouvées", "reviewed": "Revues", "evaluated": "Évaluées", "reproduced": "Reproduites",
                 "proposed": "Correctif proposé", "fixed": "Corrigées", "rejected": "Écartés"}


def _secs(start, at):
    try:
        return max(0, int((datetime.fromisoformat(at) - datetime.fromisoformat(start)).total_seconds()))
    except (TypeError, ValueError):
        return None  # début inconnu : durée inconnue


ACT_LABELS = {"pause": "Pause", "resume": "Reprise", "stop": "Arrêt", "retry": "Relance", "answer": "Réponse",
              "false_positive": "Faux positif", "prioritize_repro": "Priorité de reproduction",
              "fix": "Correction", "merge_fix": "Fusion", "end_fixes": "Fin des corrections"}


def cmd_text(c, snap):
    """Même texte que cmdText() de la page : « Relance de Plan », « Faux positif <titre> »"""
    stage = next((s["name"] for s in snap["stages"] if s["key"] == c.get("stage")), c.get("stage"))
    title = next((f.get("title") for f in snap["findings"] if f["_src"] == c.get("finding")), None) or c.get("finding")
    parts = [ACT_LABELS.get(c.get("action"), str(c.get("action"))),
             f"de {stage}" if stage and stage != c.get("stage") else stage, title]
    return " ".join(str(x) for x in parts if x)


def diff_events(prev, cur, at):
    """Événements d'activité entre deux snapshots ; sans snapshot précédent, il n'y en a aucun"""
    if prev is None:
        return []
    ev = []
    before = {s["key"]: s for s in prev["stages"]}
    for s in cur["stages"]:
        old = before.get(s["key"], {}).get("status", "pending")
        if s["status"] == old:
            continue
        secs = _secs(s["started_at"], at)
        texts = {"running": "démarrée", "done": "terminée" if secs is None else f"terminée en {round(secs / 60)} min",
                 "failed": "en échec", "skipped": "sautée"}
        if s["status"] not in texts:
            continue
        e = {"at": at, "kind": "stage", "stage": s["key"], "from": old, "to": s["status"],
             "text": f"Étape {s['name']} {texts[s['status']]}"}
        if isinstance(cur["meta"].get("round"), int):
            e["round"] = cur["meta"]["round"]
        if s["status"] == "done" and secs is not None:
            e["duration_s"] = secs
        ev.append(e)
    old_f = {f["_src"]: f for f in prev["findings"]}
    for f in cur["findings"]:
        o = old_f.get(f["_src"])
        title = f.get("title") or f["_src"]
        if o is None:
            ev.append({"at": at, "kind": "finding_new", "finding": f["_src"], "bucket": f["_bucket"],
                       "text": f"Nouveau finding : {title}"})
        elif o["_progress"] != f["_progress"]:
            a, b = o["_progress"], f["_progress"]
            ev.append({"at": at, "kind": "finding_progress", "finding": f["_src"], "from": a, "to": b,
                       "text": f"{title} : {COLUMN_LABELS.get(a, a)} → {COLUMN_LABELS.get(b, b)}"})
    fix_texts = {"running": "Correction lancée", "ready": "Correctif prêt", "failed": "Correction en échec",
                 "conflict": "Conflit sur le correctif", "merged": "Correctif fusionné"}
    for f in cur["findings"]:
        o = old_f.get(f["_src"])
        a, b = ((o or {}).get("_fix") or {}).get("status", "none"), (f.get("_fix") or {}).get("status", "none")
        if o is not None and a != b and b in fix_texts:
            ev.append({"at": at, "kind": "fix", "finding": f["_src"], "from": a, "to": b,
                       "text": f"{fix_texts[b]} : {f.get('title') or f['_src']}"})
    if cur["waiting"] is not None and prev["waiting"] is None:
        ev.append({"at": at, "kind": "waiting", "waiting_kind": cur["waiting"].get("kind"),
                   "text": "En attente de ta réponse"})
    seen = {c.get("id") for c in prev["commands"]["done"]}
    for c in cur["commands"]["done"]:
        if c.get("id") in seen:
            continue
        refused = c.get("result") == "refused"
        ev.append({"at": at, "kind": "command", "id": c.get("id"), "action": c.get("action"),
                   "result": c.get("result"), "text": cmd_text(c, cur) + " : " + (
                       f"refusée : {c.get('reason') or 'raison inconnue'}" if refused else "appliquée")})
    return ev


def append_activity(audit_dir, events):
    if not events:
        return
    with open(Path(audit_dir) / "activity.jsonl", "a", encoding="utf-8", errors="replace") as fh:
        fh.write("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))


def read_snapshot_safe(audit_dir, prev, mode="live"):
    """Snapshot courant, ou prev inchangé si un JSON surveillé est en cours d'écriture (illisible).
    Chaque fichier est lu une seule fois : celui qu'on valide est celui dont on construit le snapshot."""
    loaded = {"carry": {f["_src"]: f for f in prev["findings"]} if prev else {}}
    for key, default in (("state", {}), ("campaign", {}), ("waiting", None), ("fixes", {})):
        p = Path(audit_dir) / f"{key}.json"
        if not p.exists():
            loaded[key] = default
            continue
        try:
            loaded[key] = json.loads(p.read_text())
        except ValueError:
            return prev
        except OSError:
            loaded[key] = default
    return build_snapshot(audit_dir, mode, loaded=loaded)
