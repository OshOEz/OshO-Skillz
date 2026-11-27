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
echo "capturer OK"
