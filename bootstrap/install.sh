#!/usr/bin/env bash
# OshO-Skillz global setup (macOS). Idempotent: safe to re-run to update everything.
#   curl -fsSL https://raw.githubusercontent.com/OshOEz/OshO-Skillz/main/bootstrap/install.sh | bash
set -euo pipefail

REPO_URL="https://github.com/OshOEz/OshO-Skillz.git"
CHECKOUT="$HOME/.local/share/osho-skillz"

# Run from a checkout when possible, otherwise clone/update one (curl | bash case).
here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || true)"
if [ -n "$here" ] && [ -d "$here/steps" ]; then
  BOOTSTRAP_DIR="$here"
else
  if [ -d "$CHECKOUT/.git" ]; then git -C "$CHECKOUT" pull -q --ff-only
  else git clone -q "$REPO_URL" "$CHECKOUT"; fi
  BOOTSTRAP_DIR="$CHECKOUT/bootstrap"
fi
export BOOTSTRAP_DIR

for step in "$BOOTSTRAP_DIR"/steps/*.sh; do
  echo "==> $(basename "$step" .sh)"
  bash "$step"
done
echo "Done. Restart your terminal and Claude Code."
