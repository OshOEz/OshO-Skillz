#!/usr/bin/env bash
# code-review-graph: CLI on Homebrew Python, user-scope MCP server, skills regenerated from the installed version.
# Hooks ship in the osho-core plugin; graph instructions ship in OSHO.md.
set -euo pipefail
eval "$(/opt/homebrew/bin/brew shellenv)"
export PATH="$HOME/.local/bin:$PATH"
PY="$(brew --prefix python)/libexec/bin/python"

if uv tool list 2>/dev/null | grep -q '^code-review-graph '; then
  uv tool upgrade code-review-graph --python "$PY" -q
else
  uv tool install code-review-graph --python "$PY" -q
fi

claude mcp get code-review-graph >/dev/null 2>&1 \
  || claude mcp add -s user code-review-graph -- code-review-graph serve >/dev/null

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
git -C "$tmp" init -q
code-review-graph install --platform claude-code --no-hooks --no-instructions -y --repo "$tmp" >/dev/null
mkdir -p "$HOME/.claude/skills"
cp -R "$tmp/.claude/skills/." "$HOME/.claude/skills/"

ignore="$HOME/.config/git/ignore"
mkdir -p "$(dirname "$ignore")"; touch "$ignore"
grep -qx '.code-review-graph/' "$ignore" || echo '.code-review-graph/' >> "$ignore"
