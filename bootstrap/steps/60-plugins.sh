#!/usr/bin/env bash
# Claude Code plugins, referenced from their upstream marketplaces (never vendored), with auto-update on.
set -euo pipefail
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
SETTINGS="$HOME/.claude/settings.json"

# marketplace-name  github-repo
MARKETPLACES=(
  "osho-skillz OshOEz/OshO-Skillz"
  "ponytail DietrichGebert/ponytail"
  "i-have-adhd ayghri/i-have-adhd"
)
PLUGINS=(
  osho-core@osho-skillz
  ponytail@ponytail
  i-have-adhd@i-have-adhd
  superpowers@claude-plugins-official
)

known=$(claude plugin marketplace list 2>/dev/null || true)
for entry in "${MARKETPLACES[@]}"; do
  set -- $entry
  grep -q "❯ $1\$" <<<"$known" || claude plugin marketplace add "$2" >/dev/null
done
claude plugin marketplace update >/dev/null 2>&1 || true

installed=$(claude plugin list 2>/dev/null || true)
for p in "${PLUGINS[@]}"; do
  grep -q "❯ $p\$" <<<"$installed" || claude plugin install "$p" --scope user >/dev/null
done

# Auto-update third-party marketplaces (the official one already does).
tmp=$(mktemp)
jq 'if .extraKnownMarketplaces then .extraKnownMarketplaces |= with_entries(.value.autoUpdate = true) else . end' "$SETTINGS" > "$tmp" && mv "$tmp" "$SETTINGS"
