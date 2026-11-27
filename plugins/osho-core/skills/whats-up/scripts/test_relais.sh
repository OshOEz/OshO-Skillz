#!/usr/bin/env bash
# Auto-test du relais hooks/whats-up.sh : rien hors d'un repo installé, sinon stdin passé au garde du repo.
#   bash test_relais.sh
set -eu
relais="$(cd "$(dirname "$0")/../../../hooks" && pwd)/whats-up.sh"
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

# a. Repo not installed: exit 0, nothing printed.
mkdir "$t/vide"
out=$(echo '{"tool_input":{"command":"gh pr create --base main"}}' | CLAUDE_PROJECT_DIR="$t/vide" bash "$relais" 2>&1) || fail "a: exit $?"
[ -z "$out" ] || fail "a: unexpected output: $out"

# b. Installed repo: the repo's guard gets stdin and its exit code is returned.
mkdir -p "$t/app/.whatsup"
printf 'import sys\nsys.stderr.write("recu:" + sys.stdin.read())\nsys.exit(2)\n' > "$t/app/.whatsup/garde.py"
set +e
out=$(echo '{"x":1}' | CLAUDE_PROJECT_DIR="$t/app" bash "$relais" 2>&1); code=$?
set -e
[ "$code" = 2 ] || fail "b: exit $code, expected 2"
echo "$out" | grep -q 'recu:{"x":1}' || fail "b: stdin not passed: $out"
echo "relais OK"
