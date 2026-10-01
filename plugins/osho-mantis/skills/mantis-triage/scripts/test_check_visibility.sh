#!/usr/bin/env bash
# Auto-test de check-visibility.sh avec un faux gh dans le PATH
#   bash test_check_visibility.sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
script="$here/check-visibility.sh"
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
mkdir -p "$t/bin" "$t/mon repo"
cat >"$t/bin/gh" <<'EOF'
#!/bin/sh
[ "$3" = "owner/repo" ] || exit 1
echo "$FAKE_VIS"
EOF
chmod +x "$t/bin/gh"
with_gh="$t/bin:/usr/bin:/bin"
without_gh="/usr/bin:/bin"

check() { # check <PATH> <attendu> [visibilité renvoyée par le faux gh]
  out=$(env PATH="$1" FAKE_VIS="${3:-}" bash "$script" "$t/mon repo")
  [ "$out" = "$2" ] || { echo "FAIL: attendu $2, obtenu '$out' (gh=${3:-absent})"; exit 1; }
}

git -C "$t/mon repo" init -q
check "$with_gh" local
git -C "$t/mon repo" remote add origin git@github.com:owner/repo.git
check "$with_gh" public PUBLIC
check "$with_gh" private PRIVATE
check "$with_gh" private INTERNAL
check "$with_gh" unknown ""
check "$without_gh" unknown
git -C "$t/mon repo" remote set-url origin https://github.com/owner/repo
check "$with_gh" public PUBLIC
git -C "$t/mon repo" remote set-url origin https://gitlab.com/owner/repo.git
check "$with_gh" unknown PUBLIC
echo OK
