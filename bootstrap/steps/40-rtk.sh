#!/usr/bin/env bash
# rtk: token-saving Bash proxy hook for Claude Code (installed by the Brewfile).
set -euo pipefail
eval "$(/opt/homebrew/bin/brew shellenv)"
rtk init -g --auto-patch >/dev/null
