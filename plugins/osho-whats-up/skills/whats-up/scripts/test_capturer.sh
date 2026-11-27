#!/usr/bin/env bash
# Auto-test de capturer.mjs : une page servie en local, prête après 300 ms, capturée en WebP ; une page jamais prête.
#   bash test_capturer.sh
set -eu
ici="$(cd "$(dirname "$0")" && pwd)"
command -v node >/dev/null 2>&1 || { echo "node absent : test sauté"; exit 0; }
[ "$(node -p 'process.versions.node.split(".")[0]')" -ge 22 ] || { echo "node < 22 : test sauté"; exit 0; }
[ -f "$ici/capturer.mjs" ] || { echo "FAIL: capturer.mjs missing" >&2; exit 1; }
node "$ici/capturer.mjs" --chrome-trouve >/dev/null 2>&1 || { echo "Chrome absent : test sauté"; exit 0; }
t=$(mktemp -d); trap 'kill "$srv" 2>/dev/null; wait "$srv" 2>/dev/null || true; rm -rf "$t"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

cat > "$t/prete.html" <<'H'
<!doctype html><body style="margin:0;background:#c00"><script>setTimeout(() => { window.__whatsupPret = true }, 300)</script>
H
cat > "$t/alerte.html" <<'H'
<!doctype html><script>alert("bloque")</script>
H
cat > "$t/jamais.html" <<'H'
<!doctype html><body style="margin:0;background:#00c">
H
port=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
python3 -m http.server "$port" --bind 127.0.0.1 -d "$t" >/dev/null 2>&1 & srv=$!
for _ in $(seq 1 50); do curl -sf "http://127.0.0.1:$port/prete.html" >/dev/null && break; python3 -c 'import time;time.sleep(0.1)'; done

# Width and height of a WebP file, from its header (VP8, VP8L or VP8X).
taille() { python3 - "$1" <<'P'
import struct, sys
b = open(sys.argv[1], 'rb').read()
assert b[:4] == b'RIFF' and b[8:12] == b'WEBP', 'not a WebP'
k = b[12:16]
if k == b'VP8 ': w, h = struct.unpack('<HH', b[26:30]); print(w & 0x3fff, h & 0x3fff)
elif k == b'VP8L': v = int.from_bytes(b[21:25], 'little'); print((v & 0x3fff) + 1, ((v >> 14) & 0x3fff) + 1)
elif k == b'VP8X': print(int.from_bytes(b[24:27], 'little') + 1, int.from_bytes(b[27:30], 'little') + 1)
P
}

node "$ici/capturer.mjs" --url "http://127.0.0.1:$port/prete.html" --sortie "$t/a.webp" --largeur 400 --hauteur 300 --echelle 2 \
  || fail "capture of a ready page failed"
[ "$(taille "$t/a.webp")" = "800 600" ] || fail "full page: $(taille "$t/a.webp"), expected 800 600"

node "$ici/capturer.mjs" --url "http://127.0.0.1:$port/prete.html" --sortie "$t/b.webp" --largeur 400 --hauteur 300 --echelle 2 --clip 10,20,100,50 \
  || fail "capture with a clip failed"
[ "$(taille "$t/b.webp")" = "200 100" ] || fail "clip: $(taille "$t/b.webp"), expected 200 100"

set +e
node "$ici/capturer.mjs" --url "http://127.0.0.1:$port/jamais.html" --sortie "$t/c.webp" --attendre 1500 2>/dev/null; code=$?
set -e
[ "$code" = 3 ] || fail "never-ready page: exit $code, expected 3"
[ ! -e "$t/c.webp" ] || fail "never-ready page wrote a file"
# Runs `node capturer.mjs <args>` with a hard limit of $1 seconds; prints its exit code (124 when it had to be killed).
borne() {
  local limite=$1; shift
  node "$@" 2>/dev/null & local pid=$!
  for _ in $(seq 1 $((limite * 10))); do kill -0 "$pid" 2>/dev/null || { wait "$pid"; echo $?; return; }; python3 -c 'import time;time.sleep(0.1)'; done
  kill -9 "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; echo 124
}
profils() { ls -d "${TMPDIR:-/tmp}"/whats-up-chrome-* 2>/dev/null | wc -l | tr -d ' '; }

# Reached through a path with a space and through a symlink: it still captures.
mkdir -p "$t/a b"; cp "$ici/capturer.mjs" "$t/a b/capturer.mjs"; ln -s "$ici/capturer.mjs" "$t/lien.mjs"
node "$t/a b/capturer.mjs" --url "http://127.0.0.1:$port/prete.html" --sortie "$t/d.webp" --largeur 200 --hauteur 100 >/dev/null || fail "path with a space failed"
[ -s "$t/d.webp" ] || fail "path with a space wrote nothing"
node "$t/lien.mjs" --url "http://127.0.0.1:$port/prete.html" --sortie "$t/e.webp" --largeur 200 --hauteur 100 >/dev/null || fail "symlink failed"
[ -s "$t/e.webp" ] || fail "symlink wrote nothing"

# Bad options fail at once.
[ "$(borne 5 "$ici/capturer.mjs" --url "http://127.0.0.1:$port/prete.html" --sortie "$t/f.webp" --attendre)" = 1 ] || fail "--attendre without a value"
[ "$(borne 5 "$ici/capturer.mjs" --url "http://127.0.0.1:$port/prete.html" --sortie "$t/f.webp" --largeur 400 --hauteur 300 --clip 300,0,200,100)" = 1 ] || fail "--clip outside the page"

# An unreachable atelier is an error (1), not a page that is not ready yet.
mort=$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1])')
[ "$(borne 10 "$ici/capturer.mjs" --url "http://127.0.0.1:$mort/x.html" --sortie "$t/g.webp" --attendre 8000)" = 1 ] || fail "unreachable atelier"

# A page stuck on alert() never hangs past the delay.
avant=$(profils)
[ "$(borne 15 "$ici/capturer.mjs" --url "http://127.0.0.1:$port/alerte.html" --sortie "$t/h.webp" --attendre 1500)" = 3 ] || fail "page stuck on alert()"

# SIGTERM: Chrome stopped and its profile removed.
node "$ici/capturer.mjs" --url "http://127.0.0.1:$port/jamais.html" --sortie "$t/i.webp" --attendre 20000 2>/dev/null & cap=$!
python3 -c 'import time;time.sleep(2)'; kill -TERM "$cap"; wait "$cap" 2>/dev/null || true
python3 -c 'import time;time.sleep(1)'
[ "$(profils)" = "$avant" ] || fail "a Chrome profile was left behind ($(profils) vs $avant)"
echo "capturer OK"
