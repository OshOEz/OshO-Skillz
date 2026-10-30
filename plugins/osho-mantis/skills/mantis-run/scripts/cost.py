#!/usr/bin/env python3
"""Coût estimé et temps actif d'un audit, depuis les transcripts Claude Code → cost.json
  python3 cost.py <AUDIT> [--match <chemin cherché dans les transcripts>]
Estimation au tarif public de l'API, pas une facture. Ne copie jamais le contenu d'un transcript.
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Tarif public de l'API par million de jetons (entrée, sortie, lecture de cache), relevé le 2026-10-30.
PRICES = {
    "claude-fable-5-1": (10.0, 50.0, 0.25), "claude-fable-5": (10.0, 50.0, 1.0),
    "claude-opus-5-5": (4.0, 20.0, 0.20), "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4-8": (5.0, 25.0, 0.50), "claude-opus-4-7": (5.0, 25.0, 0.50), "claude-opus-4-6": (5.0, 25.0, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20), "claude-sonnet-5": (2.0, 10.0, 0.20), "claude-sonnet-4-6": (3.0, 15.0, 0.30),
    "claude-haiku-5-5": (0.10, 0.50, 0.01), "claude-haiku-4-5": (1.0, 5.0, 0.10),
}
CACHE_5M, CACHE_1H = 1.25, 2.0  # écriture de cache, en multiple du prix d'entrée
ACTIVE_GAP_S = 120  # écart au-delà duquel la session principale est considérée en attente (quota, pause)
FIELDS = ("in", "out", "cache_read", "cache_write_5m", "cache_write_1h")


def default_projects():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude") / "projects"


def _ts(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _campaign(audit_dir):
    try:
        c = json.loads((Path(audit_dir) / "campaign.json").read_text())
        return c if isinstance(c, dict) else {}
    except (OSError, ValueError):
        return {}


def window(audit_dir, now=None):
    audit_dir = Path(audit_dir)
    inv = audit_dir / "inventory.json"
    try:
        start = (inv if inv.exists() else audit_dir).stat().st_mtime
    except OSError:
        start = None
    end = _ts(_campaign(audit_dir).get("finished_at"))
    return start, end if end is not None else (time.time() if now is None else now)


def find_sessions(projects, match, since):
    needles = {match.encode(), json.dumps(match)[1:-1].encode()}
    found = []
    for p in sorted(Path(projects).glob("*/*.jsonl")):
        try:
            if since is not None and p.stat().st_mtime < since:
                continue
            data = p.read_bytes()
        except OSError:
            continue
        if any(n in data for n in needles):
            found.append(p)
    return found


def _lines(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    yield d
    except OSError:
        return


def compute(audit_dir, projects=None, now=None, match=None):
    audit_dir = Path(audit_dir)
    projects = Path(projects) if projects is not None else default_projects()
    start, end = window(audit_dir, now)
    inside = lambda t: t is not None and (start is None or t >= start) and t <= end
    sessions = find_sessions(projects, match or str(audit_dir), start) if projects.is_dir() else []
    usage, main_ts = {}, []
    for s in sessions:
        files = [(s, True)] + [(p, False) for p in sorted((s.parent / s.stem / "subagents").glob("*.jsonl"))]
        for path, main in files:
            for d in _lines(path):
                t = _ts(d.get("timestamp"))
                if not inside(t):
                    continue
                if main and d.get("type") in ("user", "assistant"):
                    main_ts.append(t)
                m = d.get("message")
                if isinstance(m, dict) and isinstance(m.get("usage"), dict) and m.get("model") \
                        and not str(m["model"]).startswith("<"):
                    usage[m.get("id") or d.get("requestId") or id(d)] = (m["model"], m["usage"])
    by_model = {}
    for model, u in usage.values():
        c = by_model.setdefault(model, dict.fromkeys(FIELDS, 0))
        cc = u.get("cache_creation") if isinstance(u.get("cache_creation"), dict) else {}
        c["in"] += u.get("input_tokens") or 0
        c["out"] += u.get("output_tokens") or 0
        c["cache_read"] += u.get("cache_read_input_tokens") or 0
        c["cache_write_5m"] += cc.get("ephemeral_5m_input_tokens") or 0
        c["cache_write_1h"] += cc.get("ephemeral_1h_input_tokens") or 0
    total, unknown = 0.0, []
    for model, c in by_model.items():
        if model not in PRICES:
            c["usd"] = None
            unknown.append(model)
            continue
        pi, po, pr = PRICES[model]
        c["usd"] = (c["in"] * pi + c["out"] * po + c["cache_read"] * pr
                    + c["cache_write_5m"] * pi * CACHE_5M + c["cache_write_1h"] * pi * CACHE_1H) / 1e6
        total += c["usd"]
    main_ts.sort()
    active = sum(b - a for a, b in zip(main_ts, main_ts[1:]) if b - a < ACTIVE_GAP_S)
    return {"usd": round(total, 2) if by_model and len(unknown) < len(by_model) else None,
            "by_model": by_model, "unknown_models": sorted(unknown), "active_s": int(round(active)),
            "sessions": len(sessions),
            "computed_at": datetime.fromtimestamp(time.time() if now is None else now).isoformat(timespec="seconds")}


def load(audit_dir):
    try:
        d = json.loads((Path(audit_dir) / "cost.json").read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(audit_dir, data):
    p = Path(audit_dir) / "cost.json"
    tmp = p.with_name(".cost.json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    os.replace(tmp, p)


def save_auto(audit_dir, auto):
    data = load(audit_dir)
    data["auto"] = auto
    _save(audit_dir, data)


def set_manual(audit_dir, usd, note=None):
    data = load(audit_dir)
    data["manual"] = None if usd is None else {"usd": float(usd), "note": note or "",
                                                "at": datetime.now().isoformat(timespec="seconds")}
    _save(audit_dir, data)


def summary(audit_dir):
    data = load(audit_dir)
    auto = data.get("auto") if isinstance(data.get("auto"), dict) else {}
    manual = data.get("manual") if isinstance(data.get("manual"), dict) else None
    c = _campaign(audit_dir)
    s, e = _ts(c.get("started_at")), _ts(c.get("finished_at"))
    out = {"usd": auto.get("usd"), "source": "auto" if auto.get("usd") is not None else None,
           "active_s": auto.get("active_s") or None, "wall_s": int(e - s) if s is not None and e is not None else None,
           "note": None, "by_model": auto.get("by_model") or {}, "unknown_models": auto.get("unknown_models") or []}
    if manual and isinstance(manual.get("usd"), (int, float)):
        out.update(usd=manual["usd"], source="manuel", note=manual.get("note") or None)
    return out


def fmt_s(seconds):
    if seconds is None:
        return "inconnu"
    m = int(seconds) // 60
    return f"{m // 60} h {m % 60:02d} min"


def main(argv):
    if len(argv) not in (2, 4) or (len(argv) == 4 and argv[2] != "--match"):
        sys.exit(__doc__)
    auto = compute(argv[1], match=argv[3] if len(argv) == 4 else None)
    save_auto(argv[1], auto)
    s = summary(argv[1])
    usd = "inconnu" if s["usd"] is None else f"{s['usd']:.0f} $"
    print(f"coût {usd} ({s['source'] or 'aucun transcript'}), actif {fmt_s(s['active_s'])}, "
          f"total {fmt_s(s['wall_s'])}, {auto['sessions']} session(s)")


if __name__ == "__main__":
    main(sys.argv)
