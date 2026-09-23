#!/usr/bin/env bash
# Homebrew + CLI tools from the Brewfile.
set -euo pipefail
if ! command -v brew >/dev/null 2>&1 && [ ! -x /opt/homebrew/bin/brew ]; then
  NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi
eval "$(/opt/homebrew/bin/brew shellenv)"
brew bundle --file "$BOOTSTRAP_DIR/Brewfile" --quiet
brew upgrade --quiet $(brew bundle list --file "$BOOTSTRAP_DIR/Brewfile" --formula) || true
