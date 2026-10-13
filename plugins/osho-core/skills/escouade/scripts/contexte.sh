#!/usr/bin/env bash
# Contexte Escouade d'un dépôt : clé du ticket, branche, base, retard sur origin/<base>.
#   contexte.sh [chemin] [base]
# Sort 1 (sans rien afficher) hors d'une branche ticket/<clé>, celle qu'Escouade crée pour chaque ticket.
set -eu
repo=${1:-.}
branche=$(git -C "$repo" branch --show-current 2>/dev/null) || exit 1
case "$branche" in ticket/?*) ;; *) exit 1 ;; esac
base=${2:-$(git -C "$repo" symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')}
base=${base:-main}
retard=$(git -C "$repo" rev-list --count "HEAD..origin/$base" 2>/dev/null) || retard=inconnu
echo "ticket: $(echo "${branche#ticket/}" | tr '[:lower:]' '[:upper:]')"
echo "branche: $branche"
echo "base: $base"
echo "retard: $retard"
