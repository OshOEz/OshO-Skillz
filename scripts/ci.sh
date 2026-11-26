#!/usr/bin/env bash
# The repo's own CI (make ci). Stops at the first failure and names the file.
set -eu
# A pre-push hook run from a linked worktree exports GIT_DIR; the tests build their own repositories.
unset $(git rev-parse --local-env-vars)
cd "$(dirname "$0")/.."
fail() { echo "FAIL: $*" >&2; exit 1; }

# 1-2. Tests shipped with the plugins; output shown only on failure.
for f in $(find plugins -name 'test_*.py' -not -path '*/__pycache__/*' | sort); do
  echo "test: $f"
  out=$(cd "$(dirname "$f")" && python3 "$(basename "$f")" 2>&1) || { echo "$out" >&2; fail "$f"; }
done
for f in $(find plugins -name 'test_*.sh' | sort); do
  echo "test: $f"
  out=$(bash "$f" 2>&1) || { echo "$out" >&2; fail "$f"; }
done

# 3. Shell syntax.
for f in $(find plugins bootstrap scripts .githooks -name '*.sh' | sort); do
  bash -n "$f" || fail "syntax: $f"
done

# 4. JSON validity (mantis.lock once it exists).
for f in $(find .claude-plugin plugins -name '*.json' | sort) $(find plugins -name mantis.lock); do
  jq empty "$f" 2>/dev/null || fail "invalid JSON: $f"
done

# 5. A skill's name must be its folder name, or it is listed under the wrong name.
for f in plugins/*/skills/*/SKILL.md; do
  want=$(basename "$(dirname "$f")")
  got=$(awk 'NR==1 && $0!="---" {exit} NR>1 && $0=="---" {exit} /^name:/ {sub(/^name:[ \t]*/, ""); print; exit}' "$f")
  [ "$got" = "$want" ] || fail "$f: name '$got', expected '$want'"
done

# 6. Escouade tools quoted in osho-core must exist, or an agent calls a tool that is not there.
for f in plugins/osho-core/skills/*/SKILL.md plugins/osho-core/agents/*.md; do
  # Plain (`get_ticket`) and call form (`get_ticket(ticket)`).
  for w in $(grep -o -E '`[a-z]+_(ticket|user|progress|memory|decision|board|conflict|agent_summary|projects)[`(]' "$f" | tr -d '`(' | sort -u); do
    grep -qx "$w" scripts/escouade-tools.txt || fail "$f: unknown Escouade tool '$w'"
  done
done

# 7. Public repo: no private names or home paths.
if hits=$(git grep -n -i -E "kata|KAT-[0-9]|ezymob|/Users/" -- . ':!scripts/ci.sh'); then
  echo "$hits" >&2
  fail "private name or path in tracked files (listed above)"
fi

echo "CI OK"
