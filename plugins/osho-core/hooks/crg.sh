#!/usr/bin/env bash
# code-review-graph hooks, only in repos where the graph was built (`code-review-graph build`).
#   crg.sh status -> SessionStart: print graph status
#   crg.sh update -> PostToolUse (Edit|Write): incremental graph update
cat >/dev/null || true
command -v code-review-graph >/dev/null 2>&1 || exit 0
root=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
[ -d "$root/.code-review-graph" ] || exit 0

case "${1:-}" in
  status) code-review-graph status --repo "$root" || true ;;
  update) code-review-graph update --skip-flows -q --repo "$root" || true ;;
esac
exit 0
