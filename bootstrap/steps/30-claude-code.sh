#!/usr/bin/env bash
# Claude Code CLI (native installer, self-updating).
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
command -v claude >/dev/null 2>&1 || curl -fsSL https://claude.ai/install.sh | bash
