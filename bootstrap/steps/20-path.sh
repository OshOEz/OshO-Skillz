#!/usr/bin/env bash
# Put Homebrew (and its unversioned python/pip) ahead of the macOS binaries, plus ~/.local/bin.
set -euo pipefail
MARK="# >>> osho-skillz path >>>"
touch "$HOME/.zprofile"
grep -qF "$MARK" "$HOME/.zprofile" && exit 0
cat >> "$HOME/.zprofile" <<'BLOCK'
# >>> osho-skillz path >>>
eval "$(/opt/homebrew/bin/brew shellenv)"
export PATH="$HOME/.local/bin:$(brew --prefix python)/libexec/bin:$PATH"
# <<< osho-skillz path <<<
BLOCK
