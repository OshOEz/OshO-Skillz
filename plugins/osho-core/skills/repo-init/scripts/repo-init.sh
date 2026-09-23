#!/usr/bin/env bash
# Activate per-repo tooling: code-review-graph graph + pre-commit hook. Idempotent.
#   repo-init.sh [repo-path]
set -euo pipefail

root=$(git -C "${1:-.}" rev-parse --show-toplevel 2>/dev/null) || { echo "error: ${1:-.} is not a git repository" >&2; exit 1; }
command -v code-review-graph >/dev/null 2>&1 || { echo "error: code-review-graph not installed (run the OshO-Skillz bootstrap)" >&2; exit 1; }

# 1. Graph
if [ -d "$root/.code-review-graph" ]; then
  code-review-graph update --repo "$root" 2>&1 | tail -1
  echo "graph: updated"
else
  code-review-graph build --repo "$root" 2>&1 | tail -1
  echo "graph: built"
fi

# 2. Pre-commit hook (same block as `code-review-graph install`), appended to any existing hook
hooks_dir=$(git -C "$root" rev-parse --git-path hooks)
case "$hooks_dir" in /*) ;; *) hooks_dir="$root/$hooks_dir" ;; esac
hook="$hooks_dir/pre-commit"
mark="# >>> code-review-graph pre-commit hook >>>"

if [ -f "$hook" ] && grep -qF "$mark" "$hook"; then
  echo "pre-commit: already present"
else
  mkdir -p "$hooks_dir"
  [ -f "$hook" ] || echo '#!/bin/sh' > "$hook"
  cat >> "$hook" <<'HOOK'
# >>> code-review-graph pre-commit hook >>>
if command -v code-review-graph >/dev/null 2>&1; then
    crg_root=$(git rev-parse --show-toplevel 2>/dev/null) || crg_root=""
    if [ -n "$crg_root" ] && [ -d "$crg_root/.code-review-graph" ]; then
        code-review-graph update --repo "$crg_root" || true
        code-review-graph detect-changes --brief --repo "$crg_root" || true
    fi
fi
# <<< code-review-graph pre-commit hook <<<
HOOK
  chmod +x "$hook"
  echo "pre-commit: installed ($hook)"
fi
