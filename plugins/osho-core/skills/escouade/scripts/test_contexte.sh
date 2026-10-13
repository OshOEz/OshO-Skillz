#!/usr/bin/env bash
# Auto-test de contexte.sh sur des dépôts jetables
#   bash test_contexte.sh
set -eu
script="$(cd "$(dirname "$0")" && pwd)/contexte.sh"
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
g() { git -C "$t/clone" -c user.name=t -c user.email=t@t "$@" >/dev/null 2>&1; }
fail() { echo "FAIL: $1"; echo "$out"; exit 1; }

git init -q -b dev "$t/origine"
git -C "$t/origine" -c user.name=t -c user.email=t@t commit -q --allow-empty -m init
git clone -q "$t/origine" "$t/clone" 2>/dev/null

# Hors ticket : code 1, rien affiché
out=$(bash "$script" "$t/clone") && fail "branche dev reconnue comme ticket"
[ -z "$out" ] || fail "sortie hors ticket"

# Ticket à jour, base lue sur origin/HEAD
g switch -c ticket/kat-4
out=$(bash "$script" "$t/clone") || fail "ticket non reconnu"
[ "$out" = "$(printf 'ticket: KAT-4\nbranche: ticket/kat-4\nbase: dev\nretard: 0')" ] || fail "ticket à jour"

# La base avance sur origin : retard 2
git -C "$t/origine" -c user.name=t -c user.email=t@t commit -q --allow-empty -m a
git -C "$t/origine" -c user.name=t -c user.email=t@t commit -q --allow-empty -m b
g fetch -q origin
out=$(bash "$script" "$t/clone")
echo "$out" | grep -qx 'retard: 2' || fail "retard attendu 2"

# Base donnée en argument mais absente d'origin : retard inconnu
out=$(bash "$script" "$t/clone" main)
echo "$out" | grep -qx 'base: main' || fail "base en argument"
echo "$out" | grep -qx 'retard: inconnu' || fail "retard inconnu"

echo "OK test_contexte"
