#!/usr/bin/env python3
"""Fil de Claude : texte des messages de l'orchestrateur et de ses sous-agents, lu dans les transcripts
Claude Code de l'audit (les mêmes que cost.py), en lecture seule. Ni réflexion, ni appels d'outils, ni leurs
résultats, ni entrées utilisateur : ils peuvent contenir des fichiers entiers ou des secrets.
"""
import json
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import cost

MAX_TEXT = 2000
LIMIT = 200
KEEP = 2000
TAIL = 512 * 1024  # premier passage : seulement la fin des gros fichiers
REFRESH_S = 30


def _clip(s):
    return s if len(s) <= MAX_TEXT else s[:MAX_TEXT] + "…"


class Feed:
    def __init__(self, audit_dir, projects=None):
        self.audit = Path(audit_dir)
        self.projects = Path(projects) if projects is not None else cost.default_projects()
        self.lock = threading.Lock()
        self.items = deque(maxlen=KEEP)
        self.seq = 0
        self.offsets = {}   # fichier -> octets déjà lus
        self.agents = {}    # fichier de sous-agent -> {"who", "model", "ended"}
        self.sessions, self.found_at = [], 0.0

    def _files(self):
        now = time.time()
        if now - self.found_at > REFRESH_S or not self.sessions:
            start, _ = cost.window(self.audit)
            self.sessions = cost.find_sessions(self.projects, cost.audit_key(self.audit), start) if self.projects.is_dir() else []
            self.found_at = now
        out = []
        for s in self.sessions:
            out.append((s, None))
            out += [(p, p) for p in sorted((s.parent / s.stem / "subagents").glob("*.jsonl"))]
        return out

    def _meta(self, path):
        try:
            m = json.loads(path.with_name(path.stem + ".meta.json").read_text())
            return m if isinstance(m, dict) else {}
        except (OSError, ValueError):
            return {}

    def _read_new(self, path):
        try:
            size = path.stat().st_size
        except OSError:
            return []
        pos = self.offsets.get(path)
        first = pos is None
        if first:
            pos = max(0, size - TAIL)
        if size <= pos:
            self.offsets[path] = pos
            return []
        with open(path, "rb") as fh:
            fh.seek(pos)
            data = fh.read(size - pos)
        if first and pos > 0:  # au milieu d'une ligne : on repart à la suivante
            cut = data.find(b"\n")
            data, pos = (data[cut + 1:], pos + cut + 1) if cut >= 0 else (b"", pos)
        end = data.rfind(b"\n")
        if end < 0:
            self.offsets[path] = pos
            return []
        self.offsets[path] = pos + end + 1
        out = []
        for line in data[:end].splitlines():
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if isinstance(d, dict):
                out.append(d)
        return out

    def update(self):
        start, _ = cost.window(self.audit)
        new = []
        for path, sub in self._files():
            if sub is not None and path not in self.agents:
                m = self._meta(path)
                self.agents[path] = {"who": str(m.get("description") or "Sous-agent"), "model": m.get("model"),
                                     "started": False, "ended": False}
            who = self.agents[path]["who"] if sub is not None else "Claude"
            prev_id = None
            for d in self._read_new(path):
                t = cost._ts(d.get("timestamp"))
                if t is None or (start is not None and t < start):
                    continue
                if sub is not None and not self.agents[path]["started"]:
                    self.agents[path]["started"] = True
                    self.agents[path]["started_at"] = t
                    model = self.agents[path]["model"]
                    new.append({"t": t, "who": who, "kind": "agent_start",
                                "text": "Agent lancé" + (f" (modèle {model})" if model else "")})
                m = d.get("message")
                if d.get("type") != "assistant" or not isinstance(m, dict) or not isinstance(m.get("content"), list):
                    continue
                txt = "\n".join(str(b.get("text") or "") for b in m["content"]
                                if isinstance(b, dict) and b.get("type") == "text").strip()
                if not txt:
                    continue
                if prev_id is not None and m.get("id") == prev_id and new and new[-1]["kind"] == "message":
                    new[-1]["text"] = _clip(new[-1]["text"] + "\n" + txt)
                    continue
                prev_id = m.get("id")
                new.append({"t": t, "who": who, "kind": "message", "text": _clip(txt)})
            if sub is not None:
                a = self.agents[path]
                if a["started"] and not a["ended"] and self._meta(path).get("finished"):
                    a["ended"] = True
                    try:
                        t = path.with_name(path.stem + ".meta.json").stat().st_mtime
                    except OSError:
                        t = time.time()
                    new.append({"t": t, "who": who, "kind": "agent_end", "text": "Agent terminé"})
        for it in sorted(new, key=lambda x: x["t"]):
            self.seq += 1
            self.items.append({"seq": self.seq, "at": datetime.fromtimestamp(it.pop("t")).isoformat(timespec="seconds"),
                               **it})

    def agent_list(self):
        with self.lock:
            self.update()
            return [{"who": a["who"], "started_at": a["started_at"], "done": a["ended"]}
                    for a in self.agents.values() if a["started"]]

    def since(self, after):
        with self.lock:
            self.update()
            items = [i for i in self.items if i["seq"] > after][-LIMIT:]
            return {"items": items, "last": self.seq}


def batch_agents(agents, since, workers):
    """Agents du lot en cours : lancés depuis le début du lot (5 s de marge), hors agents de correction,
    les `workers` derniers ; [] si le début du lot est inconnu"""
    if since is None:
        return []
    got = sorted((a for a in agents if a["started_at"] >= since - 5 and not str(a["who"]).startswith("Correctif")),
                 key=lambda a: a["started_at"])
    if workers:
        got = got[-int(workers):]
    return [{"who": a["who"], "done": bool(a["done"])} for a in got]
