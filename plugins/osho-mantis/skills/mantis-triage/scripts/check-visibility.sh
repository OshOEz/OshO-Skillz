#!/usr/bin/env bash
# Visibilité du repo git pour osho-mantis : local | private | public | unknown
#   bash check-visibility.sh [repo]
set -u
repo="${1:-.}"
remotes=$(git -C "$repo" remote 2>/dev/null)
[ -n "$remotes" ] || { echo local; exit 0; }

# Check all remotes and track visibility: public > unknown > private
has_public=0
has_unknown=0
has_private=0

for remote in $remotes; do
  url=$(git -C "$repo" remote get-url "$remote")
  case "$url" in
    *github.com[:/]*)
      # GitHub remote: check visibility via gh
      if command -v gh >/dev/null 2>&1; then
        slug=$(printf '%s\n' "$url" | sed -E 's#^.*github\.com[:/]##; s#\.git$##')
        vis=$(gh repo view "$slug" --json visibility -q .visibility 2>/dev/null)
        case "$vis" in
          PUBLIC) has_public=1 ;;
          PRIVATE|INTERNAL) has_private=1 ;;
          *) has_unknown=1 ;;
        esac
      else
        has_unknown=1
      fi
      ;;
    *)
      # Non-GitHub remote: unknown visibility
      has_unknown=1
      ;;
  esac
done

# Return worst case: public > unknown > private
if [ "$has_public" = 1 ]; then
  echo public
elif [ "$has_unknown" = 1 ]; then
  echo unknown
else
  echo private
fi
