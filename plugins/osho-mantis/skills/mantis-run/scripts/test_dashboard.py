#!/usr/bin/env python3
"""Auto-test de dashboard.py : serveur local, SSE, commandes
  python3 test_dashboard.py
"""
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
DASH = str(HERE / "dashboard.py")


def cli(*args, check=True):
    r = subprocess.run([sys.executable, DASH, *map(str, args)], capture_output=True, text=True, timeout=15)
    if check:
        assert r.returncode == 0, (args, r.stdout, r.stderr)
    return r


def make_audit(tmp, state=None, findings=()):
    d = Path(tmp) / "audit"
    (d / "workspace" / "findings").mkdir(parents=True)
    (d / "campaign.json").write_text(json.dumps({"repo": "/x/demo", "level": "Light"}))
    (d / "state.json").write_text(json.dumps(state or {"stages": {"architecture": "running"}}))
    for i, f in enumerate(findings):
        (d / "workspace" / "findings" / f"f{i}.json").write_text(json.dumps(f))
    return d


@contextmanager
def server(state=None, findings=()):
    with tempfile.TemporaryDirectory() as tmp:
        d = make_audit(tmp, state, findings)
        try:
            out = json.loads(cli("serve", d).stdout)
            u = urlparse(out["url"])
            yield d, out, u.port, parse_qs(u.query)["key"][0]
        finally:
            cli("stop", d, check=False)


def req(port, method, path, headers=None, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read().decode()
    c.close()
    return r.status, data, r


def post(port, key, body, **hdr):
    h = {"Origin": f"http://127.0.0.1:{port}", "Content-Type": "application/json"}
    h.update(hdr)
    return req(port, "POST", f"/command?key={key}", h, json.dumps(body))


def test_serve_et_reutilise():
    with server() as (d, out, port, key):
        assert out["reused"] is False and out["url"] == f"http://127.0.0.1:{port}/?key={key}"
        info = json.loads((d / "server.json").read_text())
        assert info["port"] == port and info["key"] == key and info["url"] == out["url"] and info["pid"]
        again = json.loads(cli("serve", d).stdout)
        assert again == {"url": out["url"], "reused": True}
        assert req(port, "GET", f"/health?key={key}")[0] == 200


def test_serve_pid_mort():
    with tempfile.TemporaryDirectory() as tmp:
        d = make_audit(tmp)
        (d / "server.json").write_text(json.dumps({"pid": 999999, "port": 1, "url": "http://127.0.0.1:1/?key=x",
                                                   "key": "x", "started_at": "2026-10-22T10:00:00"}))
        try:
            out = json.loads(cli("serve", d).stdout)
            assert out["reused"] is False and out["url"] != "http://127.0.0.1:1/?key=x"
            assert json.loads((d / "server.json").read_text())["pid"] != 999999
        finally:
            cli("stop", d, check=False)


def test_auth():
    with server() as (d, out, port, key):
        assert req(port, "GET", "/")[0] == 403
        assert req(port, "GET", "/?key=mauvaise")[0] == 403
        s, body, r = req(port, "GET", f"/?key={key}")
        assert s == 200 and "mantis_key=" in r.getheader("Set-Cookie") and "HttpOnly" in r.getheader("Set-Cookie")
        assert "SameSite=Strict" in r.getheader("Set-Cookie")
        assert req(port, "GET", "/", {"Cookie": f"mantis_key={key}"})[0] == 200
        assert req(port, "GET", "/health")[0] == 403
        assert req(port, "GET", "/events")[0] == 403
        assert req(port, "GET", f"/?key={key}", {"Host": "evil:80"})[0] == 403
        assert post(port, key, {"action": "pause"}, Origin="http://evil")[0] == 403
        assert post(port, key, {"action": "pause"}, Host=f"evil:{port}")[0] == 403
        assert req(port, "POST", f"/command?key={key}", {}, "{}")[0] == 403  # sans Origin
        assert post(port, "mauvaise", {"action": "pause"})[0] == 403


def test_post_409_sans_session():
    with server({"stages": {"review": "done"}, "finished": True}) as (d, out, port, key):
        s, body, _ = post(port, key, {"action": "pause"})
        assert s == 409 and json.loads(body)["error"] == "Aucune session active : relance /mantis-run"


def test_post_400_puis_200():
    with server({"stages": {"architecture": "running"}}) as (d, out, port, key):
        assert post(port, key, {"action": "nope"})[0] == 400
        assert post(port, key, "pas un objet")[0] == 400
        assert req(port, "POST", f"/command?key={key}", {"Origin": f"http://127.0.0.1:{port}"}, "{pas json")[0] == 400
        s, body, _ = post(port, key, {"action": "pause"})
        cmd = json.loads(body)
        assert s == 200 and cmd["action"] == "pause" and cmd["source"] == "page" and cmd["id"]
        pend = [json.loads(x) for x in cli("pending", d).stdout.splitlines()]
        assert [c["id"] for c in pend] == [cmd["id"]]
        big = post(port, key, {"action": "pause", "x": "a" * 5000})
        assert big[0] == 413


def sse(port, key):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=4)
    c.request("GET", f"/events?key={key}")
    r = c.getresponse()
    assert r.status == 200 and "text/event-stream" in r.getheader("Content-Type")

    def nxt():
        ev = data = None
        while True:
            line = r.fp.readline().decode().rstrip("\n")
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
            elif line == "" and ev:
                return ev, data
    return c, nxt


def test_sse_snapshot_apres_changement():
    with server({"stages": {"review": "running"}}) as (d, out, port, key):
        c, nxt = sse(port, key)
        try:
            ev, data = nxt()
            assert ev == "snapshot"
            rev = lambda s: next(x for x in s["stages"] if x["key"] == "review")["status"]
            assert rev(json.loads(data)) == "running"
            (d / "state.json").write_text(json.dumps({"stages": {"review": "done"}}))
            t0 = time.time()
            while True:
                ev, data = nxt()
                if ev == "snapshot" and rev(json.loads(data)) == "done":
                    break
            assert time.time() - t0 < 3
            act = [json.loads(x) for x in (d / "activity.jsonl").read_text().splitlines()]
            assert any(e["kind"] == "stage" and e["stage"] == "review" for e in act)
        finally:
            c.close()


def test_sse_xss_inerte():
    title = "</script><img src=x onerror=alert(1)>"
    with server(findings=[{"id": "x", "title": title}]) as (d, out, port, key):
        s, body, _ = req(port, "GET", f"/?key={key}")
        assert s == 200 and "</script><img" not in body and "<img src=x" not in body
        assert "__DATA__" not in body and "u003c/script" in body
        c, nxt = sse(port, key)
        try:
            ev, data = nxt()
            assert json.loads(data)["findings"][0]["title"] == title and "\n" not in data
        finally:
            c.close()


def test_surrogate_isole():
    with server(findings=[{"id": "x", "title": "a\udc00b"}]) as (d, out, port, key):
        assert req(port, "GET", f"/?key={key}")[0] == 200
        c, nxt = sse(port, key)
        try:
            assert nxt()[0] == "snapshot"
        finally:
            c.close()
        (d / "workspace" / "findings" / "y.json").write_text(json.dumps({"id": "y", "title": "\udc01"}))
        time.sleep(1.5)  # le watcher survit (activité écrite avec un substitut) et le serveur répond
        assert req(port, "GET", f"/health?key={key}")[0] == 200


def test_audit_supprime_arrete_le_serveur():
    with tempfile.TemporaryDirectory() as tmp:
        d = make_audit(tmp)
        try:
            pid = json.loads((json.loads(cli("serve", d).stdout) and (d / "server.json").read_text()))["pid"]
            shutil.rmtree(d)
            for _ in range(60):
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
                time.sleep(0.1)
            else:
                raise AssertionError("le serveur tourne encore")
        finally:
            cli("stop", d, check=False)


def test_tmp_symlink_non_suivi():
    with tempfile.TemporaryDirectory() as tmp:
        d = make_audit(tmp)
        victim = Path(tmp) / "victime"
        victim.write_text("intact")
        (d / "server.json.tmp").symlink_to(victim)
        try:
            cli("serve", d)
            assert victim.read_text() == "intact" and oct((d / "server.json").stat().st_mode & 0o777) == "0o600"
        finally:
            cli("stop", d, check=False)


def test_stop():
    with server() as (d, out, port, key):
        cli("stop", d)
        assert not (d / "server.json").exists()
        try:
            req(port, "GET", f"/health?key={key}")
            raise AssertionError("le port répond encore")
        except OSError:
            pass


def test_command_terminal():
    with tempfile.TemporaryDirectory() as tmp:
        d = make_audit(tmp, {"stages": {"review": "done"}, "finished": True, "paused": True})
        r = cli("command", d, '{"action": "resume"}')  # listening == none : accepté
        cmd = json.loads(r.stdout)
        assert cmd["source"] == "terminal" and cmd["action"] == "resume"
        r = cli("command", d, '{"action": "pause"}', check=False)
        assert r.returncode == 2 and "pas en cours" in r.stdout
        assert cli("command", d, "pas json", check=False).returncode == 2
        assert [json.loads(x)["id"] for x in cli("pending", d).stdout.splitlines()] == [cmd["id"]]


def test_help():
    out = cli("--help").stdout
    for w in ("serve", "stop", "command", "pending", "apply", "ack"):
        assert w in out


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("OK")
