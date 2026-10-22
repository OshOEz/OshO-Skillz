#!/usr/bin/env python3
"""Serveur local du dashboard live et commandes associées (127.0.0.1 uniquement)
  python3 dashboard.py serve|stop|command|pending|apply|ack ...   (--help pour le détail)
"""
import hmac
import json
import os
import queue
import secrets
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import commands
import render
import snapshot

HERE = Path(__file__).resolve().parent
POLL_S, PING_S = 0.5, 10
END_GRACE_S, IDLE_S, HARD_IDLE_S = 1800, 4 * 3600, 24 * 3600  # HARD : même avec une page ouverte
MAX_BODY = 4096  # validate() plafonne la commande à 1 Ko ; on coupe avant de tout lire
USAGE = """usage: dashboard.py <commande> <AUDIT> [...]
  serve <AUDIT>                        démarre (ou réutilise) le serveur, affiche {"url", "reused"}
  stop <AUDIT>                         arrête le serveur
  alive <AUDIT>                        code 0 si le serveur tourne et répond, 1 sinon
  command <AUDIT> '<json>'             ajoute une commande depuis le terminal (code 2 si refusée)
  pending <AUDIT>                      commandes en attente, une par ligne
  apply <AUDIT> <id>                   applique une commande finding (false_positive, prioritize_repro)
  ack <AUDIT> <id> applied|refused [raison]   accuse réception d'une commande"""


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def signature(audit):
    paths = [audit / n for n in ("state.json", "campaign.json", "waiting.json", "commands.jsonl",
                                 "commands-done.jsonl")]
    paths += sorted((audit / "workspace" / "findings").glob("*.json"))
    sig = []
    for p in paths:
        try:
            st = p.stat()
            sig.append((str(p), st.st_mtime_ns, st.st_size))
        except OSError:
            pass
    return tuple(sig)


class Dash:
    def __init__(self, audit):
        self.audit, self.key = audit, secrets.token_hex(32)
        self.lock = threading.Lock()
        self.clients = []
        self.snap = snapshot.build_snapshot(audit)
        self.stop_evt = threading.Event()
        self.httpd = None

    def fresh(self):
        with self.lock:
            return snapshot.read_snapshot_safe(self.audit, self.snap)

    def subscribe(self):
        q = queue.Queue()
        with self.lock:
            self.clients.append(q)
            q.put(("snapshot", json.dumps(self.snap, ensure_ascii=False)))
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    def watch(self):
        sig, last_change, end_seen = signature(self.audit), time.time(), None
        try:
            while not self.stop_evt.wait(POLL_S):
                if not self.audit.is_dir():
                    break
                try:
                    sig, last_change = self.tick(sig, last_change)
                except Exception as e:  # une erreur de tick ne doit jamais empêcher l'arrêt automatique ci-dessous
                    print(f"watch: {e!r}", file=sys.stderr, flush=True)
                m, idle = self.snap["meta"], time.time() - last_change
                if not (m["finished"] or m["stopped"]):
                    end_seen = None
                elif end_seen is None:
                    end_seen = time.time()
                if end_seen and time.time() - end_seen > END_GRACE_S:
                    break
                if (idle > IDLE_S and not self.clients) or idle > HARD_IDLE_S:
                    break
        finally:
            self.shutdown()

    def tick(self, sig, last_change):
        new = signature(self.audit)
        if new == sig:
            return sig, last_change
        with self.lock:
            prev = self.snap
            cur = snapshot.read_snapshot_safe(self.audit, prev)
            if cur is prev:  # JSON en cours d'écriture : on réessaie au prochain tour
                return sig, last_change
            events = snapshot.diff_events(prev, cur, now_iso())
            if events:
                snapshot.append_activity(self.audit, events)
                cur = snapshot.read_snapshot_safe(self.audit, cur)  # relu pour inclure le journal ; tronqué : on garde cur
            self.snap = cur
            msg = ("snapshot", json.dumps(cur, ensure_ascii=False))
            for q in self.clients:
                q.put(msg)
        return new, time.time()

    def shutdown(self):
        self.stop_evt.set()
        threading.Thread(target=self.httpd.shutdown, daemon=True).start()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    dash = None

    def log_message(self, *a):  # l'URL de la requête contient la clé
        pass

    def send(self, code, body=b"", ctype="application/json", extra=()):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8", "replace")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def authorized(self, need_origin=False):
        port = self.server.server_address[1]
        if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return False, False
        if need_origin and self.headers.get("Origin") not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            return False, False
        via_query = parse_qs(urlparse(self.path).query).get("key", [""])[0]
        cookie = ""
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == "mantis_key":
                cookie = v
        ok = lambda k: hmac.compare_digest(k.encode(), self.dash.key.encode())
        return (ok(via_query) or ok(cookie)), ok(via_query)

    def do_GET(self):
        okay, via_query = self.authorized()
        if not okay:
            return self.send(403, {"error": "accès refusé"})
        route = urlparse(self.path).path
        if route == "/health":
            self.send(200, {"ok": True})
        elif route == "/":
            page = (HERE / "dashboard.html").read_text(encoding="utf-8")
            page = page.replace("__DATA__", render.safe_json(self.dash.fresh()), 1)
            cookie = f"mantis_key={self.dash.key}; HttpOnly; SameSite=Strict; Path=/"
            self.send(200, page, "text/html", [("Set-Cookie", cookie)] if via_query else [])
        elif route == "/events":
            self.events()
        else:
            self.send(404, {"error": "introuvable"})

    def events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        q = self.dash.subscribe()
        try:
            while not self.dash.stop_evt.is_set():
                try:
                    ev, data = q.get(timeout=PING_S)
                except queue.Empty:
                    ev, data = "ping", now_iso()
                self.wfile.write(f"event: {ev}\ndata: {data}\n\n".encode("utf-8", "replace"))
                self.wfile.flush()
        except OSError:
            pass
        finally:
            self.dash.unsubscribe(q)

    def do_POST(self):
        self.close_connection = True  # corps éventuellement non lu : pas de réutilisation de la connexion
        if not self.authorized(need_origin=True)[0] or urlparse(self.path).path != "/command":
            return self.send(403, {"error": "accès refusé"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0:
            return self.send(400, {"error": "Content-Length invalide"})
        if n > MAX_BODY:
            return self.send(413, {"error": "commande trop longue (1 Ko maximum)"})
        try:
            cmd = json.loads(self.rfile.read(n))
        except (ValueError, RecursionError):
            return self.send(400, {"error": "commande illisible"})
        snap = self.dash.fresh()
        if snap["listening"] == "none":
            return self.send(409, {"error": "Aucune session active : relance /mantis-run"})
        reason = commands.validate(cmd, snap)
        if reason:
            return self.send(400, {"error": reason})
        self.send(200, commands.append(self.dash.audit, cmd, "page"))


def run(audit):
    audit = Path(audit).resolve()
    dash = Dash(audit)
    Handler.dash = dash
    httpd = dash.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    info = {"pid": os.getpid(), "port": port, "url": f"http://127.0.0.1:{port}/?key={dash.key}",
            "key": dash.key, "started_at": now_iso()}
    commands.atomic_write(audit / "server.json", json.dumps(info), 0o600)  # la clé ouvre le dashboard
    signal.signal(signal.SIGTERM, lambda *_: dash.shutdown())
    threading.Thread(target=dash.watch, daemon=True).start()
    try:
        httpd.serve_forever()
    finally:
        (audit / "server.json").unlink(missing_ok=True)


def read_info(audit):
    try:
        return json.loads((Path(audit) / "server.json").read_text())
    except (OSError, ValueError):
        return None


def alive(info):
    """Le serveur de server.json tourne (pid vivant et /health répond)"""
    import http.client
    try:
        os.kill(info["pid"], 0)
        c = http.client.HTTPConnection("127.0.0.1", info["port"], timeout=2)
        c.request("GET", f"/health?key={info['key']}")
        ok = c.getresponse().status == 200
        c.close()
        return ok
    except (OSError, KeyError, TypeError):
        return False


def serve(audit):
    audit = Path(audit).resolve()
    info = read_info(audit)
    if info and alive(info):
        return {"url": info["url"], "reused": True}
    (audit / "server.json").unlink(missing_ok=True)
    with open(audit / "server.log", "ab") as log:
        subprocess.Popen([sys.executable, str(HERE / "dashboard.py"), "_run", str(audit)],
                         stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    for _ in range(100):
        info = read_info(audit)
        if info:
            return {"url": info["url"], "reused": False}
        time.sleep(0.05)
    raise SystemExit("le serveur n'a pas démarré (voir server.log)")


def stop(audit):
    audit = Path(audit).resolve()
    info = read_info(audit)
    if info and alive(info):  # on ne tue que le vrai serveur, jamais un pid réattribué
        os.kill(info["pid"], signal.SIGTERM)
        for _ in range(100):
            if not (audit / "server.json").exists():
                break
            time.sleep(0.05)
    (audit / "server.json").unlink(missing_ok=True)


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help") or argv[1] not in (
            "serve", "stop", "alive", "command", "pending", "apply", "ack", "_run") or len(argv) < 3:
        print(USAGE)
        return 0 if len(argv) < 2 or argv[1] in ("-h", "--help") else 2
    cmd, audit, rest = argv[1], argv[2], argv[3:]
    if (cmd in ("command", "apply") and not rest) or (cmd == "ack" and len(rest) < 2):
        print(USAGE)
        return 2
    if cmd == "_run":
        run(audit)
    elif cmd == "serve":
        print(json.dumps(serve(audit)))
    elif cmd == "stop":
        stop(audit)
    elif cmd == "alive":
        info = read_info(Path(audit).resolve())
        return 0 if info and alive(info) else 1
    elif cmd == "pending":
        for c in commands.pending(audit):
            print(json.dumps(c, ensure_ascii=False))
    elif cmd == "command":
        try:
            body = json.loads(rest[0])
        except (ValueError, IndexError):
            body = None
        reason = commands.validate(body, snapshot.build_snapshot(audit))
        if reason:
            print(reason)
            return 2
        print(json.dumps(commands.append(audit, body, "terminal"), ensure_ascii=False))
    elif cmd == "apply":
        try:
            print(json.dumps(commands.apply(audit, rest[0]), ensure_ascii=False))
        except (ValueError, IndexError) as e:
            print(e or USAGE)
            return 2
    elif cmd == "ack":
        if len(rest) < 2 or rest[1] not in ("applied", "refused"):
            print(USAGE)
            return 2
        commands.ack(audit, rest[0], rest[1], rest[2] if len(rest) > 2 else None)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
