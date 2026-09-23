#!/usr/bin/env bash
# Keep Superpowers installed (skills available) without its always-on bootstrap; offer it per session.
#   superpowers-offer.sh session -> SessionStart: strip the plugin's bootstrap hook (re-applied after plugin updates)
#   superpowers-offer.sh prompt  -> UserPromptSubmit: ask Claude to evaluate the task and offer Superpowers once
set -euo pipefail

CACHE="$HOME/.claude/plugins/cache/claude-plugins-official/superpowers"
STATE_DIR="$HOME/.claude/state/superpowers-offer"
input=$(cat)

case "${1:-}" in
  session)
    for f in "$CACHE"/*/hooks/hooks.json; do
      [ -f "$f" ] && jq -e '.hooks | length > 0' "$f" >/dev/null 2>&1 && echo '{"hooks":{}}' > "$f"
    done
    find "$STATE_DIR" -type f -mtime +2 -delete 2>/dev/null || true
    exit 0
    ;;
  prompt) ;;
  *) exit 0 ;;
esac

session_id=$(jq -r '.session_id // empty' <<<"$input")
prompt=$(jq -r '.prompt // empty' <<<"$input")
[ -n "$session_id" ] || exit 0
marker="$STATE_DIR/$session_id"

# Already decided this session, or slash command: stay quiet.
[ -e "$marker" ] && exit 0
[[ "$prompt" == /* ]] && exit 0
mkdir -p "$STATE_DIR"

context="[superpowers-offer] Superpowers skills are installed but its workflow is not active this session.
Classify the user's request. It qualifies ONLY for substantial software work: building a feature, multi-file change or refactor, non-trivial debugging, designing/planning an implementation, or a TDD/review workflow. It does NOT qualify for questions, explanations, config/install/setup tasks, one-line fixes, or chit-chat.
- If it does NOT qualify: say nothing about Superpowers and answer normally.
- If it qualifies: before any other work, run \`touch '$marker'\`, then call AskUserQuestion (header \"Superpowers\") asking in the user's language whether to use Superpowers for this session, options Oui / Non. The question holds exactly ONE concise sentence on why Superpowers helps THIS task (name the relevant skill).
  - Oui: invoke the Skill superpowers:using-superpowers and follow it for the rest of the session.
  - Non: continue normally."

jq -n --arg c "$context" '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $c}}'
