#!/usr/bin/env bash
# Global instructions: install OSHO.md and import it from ~/.claude/CLAUDE.md.
set -euo pipefail
cp "$BOOTSTRAP_DIR/claude/OSHO.md" "$HOME/.claude/OSHO.md"
touch "$HOME/.claude/CLAUDE.md"
grep -qx '@OSHO.md' "$HOME/.claude/CLAUDE.md" || echo '@OSHO.md' >> "$HOME/.claude/CLAUDE.md"
