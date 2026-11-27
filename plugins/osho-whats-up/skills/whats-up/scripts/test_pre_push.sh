#!/usr/bin/env bash
# Auto-test de l'extrait pre-push.sh posé en tête d'un hook git : vrai push vers un dépôt nu.
#   bash test_pre_push.sh
set -eu
for k in $(git rev-parse --local-env-vars); do unset "$k"; done
ici="$(cd "$(dirname "$0")" && pwd)"
extrait="$ici/../assets/pre-push.sh"
t=$(mktemp -d); trap 'rm -rf "$t"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

git init -q --bare -b main "$t/origin.git"
git init -q -b main "$t/app"; cd "$t/app"
git config user.email t@t; git config user.name t
mkdir -p .whatsup public/whats-up
cp "$ici/garde.py" .whatsup/garde.py
echo '{"prod":"main","base":"main","dossier":"public/whats-up"}' > .whatsup/config.json
echo '{"ids":["2026-11-20"]}' > public/whats-up/index.json
git add -A; git commit -q -m init
git remote add origin "$t/origin.git"; git push -q origin main

# An existing hook that reads stdin and records it, after which the snippet is inserted below the shebang.
h="$(git rev-parse --git-path hooks)/pre-push"
printf '#!/bin/sh\ncat > "%s/vu-par-le-hook"\nexit 0\n' "$t" > "$h"; chmod +x "$h"
{ head -n 1 "$h"; cat "$extrait"; tail -n +2 "$h"; } > "$h.new" && mv "$h.new" "$h" && chmod +x "$h"

echo b > b.txt; git add -A; git commit -q -m b
if git push -q origin main 2>"$t/err"; then fail "push without a newer note went through"; fi
grep -q "Pas de fiche What's up ?" "$t/err" || fail "no refusal message: $(cat "$t/err")"

WHATSUP_SANS="test" git push -q origin main || fail "escape refused"
grep -q "refs/heads/main" "$t/vu-par-le-hook" || fail "the existing hook lost its stdin"

# python3 unreachable: the push goes through.
echo c > c.txt; git add -A; git commit -q -m c
PATH="/nonexistent" /usr/bin/git push -q origin main 2>/dev/null || fail "push blocked without python3"
echo "pre-push OK"
