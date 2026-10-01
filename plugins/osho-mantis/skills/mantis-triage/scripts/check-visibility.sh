#!/usr/bin/env bash
# Visibilité du repo git pour osho-mantis : local | private | public | unknown
#   bash check-visibility.sh [repo]
set -u
repo="${1:-.}"
remote=$(git -C "$repo" remote 2>/dev/null | head -n 1)
[ -n "$remote" ] || { echo local; exit 0; }
url=$(git -C "$repo" remote get-url "$remote")
case "$url" in
  *github.com[:/]*) ;;
  *) echo unknown; exit 0 ;;
esac
command -v gh >/dev/null 2>&1 || { echo unknown; exit 0; }
slug=$(printf '%s\n' "$url" | sed -E 's#^.*github\.com[:/]##; s#\.git$##')
vis=$(gh repo view "$slug" --json visibility -q .visibility 2>/dev/null) || { echo unknown; exit 0; }
case "$vis" in
  PUBLIC) echo public ;;
  PRIVATE|INTERNAL) echo private ;;
  *) echo unknown ;;
esac
