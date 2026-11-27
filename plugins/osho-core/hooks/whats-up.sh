#!/usr/bin/env bash
# PreToolUse Bash: hands the command to the repo's own What's up ? guard (gh pr create to prod).
# Silent outside a repo installed with What's up ? (.whatsup/garde.py), like crg.sh with .code-review-graph/.
set -u
cd "${CLAUDE_PROJECT_DIR:-$PWD}" 2>/dev/null || exit 0
[ -f .whatsup/garde.py ] || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
exec python3 .whatsup/garde.py claude
