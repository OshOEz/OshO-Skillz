#!/usr/bin/env bash
# PreToolUse Bash: hands the command to the repo's own What's up ? guard (gh pr create to prod).
# Silent outside a repo installed with What's up ? (.whatsup/garde.py), like crg.sh with .code-review-graph/.
set -u
command -v python3 >/dev/null 2>&1 || exit 0
entree=$(cat)
# The command runs in the hook's cwd (a worktree, say), not always in the project dir.
cwd=$(printf '%s' "$entree" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("cwd") or "")
except Exception: print("")' 2>/dev/null)
for d in "$cwd" "${CLAUDE_PROJECT_DIR:-}" "$PWD"; do
  [ -n "$d" ] && [ -f "$d/.whatsup/garde.py" ] || continue
  cd "$d" || exit 0
  printf '%s' "$entree" | python3 .whatsup/garde.py claude
  exit $?
done
exit 0
