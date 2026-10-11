#!/usr/bin/env bash
# PostToolUse on Skill: when a Superpowers skill that ends in a review or a decision starts,
# remind Claude to present it through osho-core:revue-artefact (an artifact page) rather than in the terminal.
set -euo pipefail

input=$(cat)
skill=$(jq -r '.tool_input.skill // empty' <<<"$input")

case "$skill" in
  superpowers:brainstorming)
    moment="the spec, once written: present its summary and the choices to validate" ;;
  superpowers:writing-plans)
    moment="the plan, once written: present its summary, the decisions it takes and the execution choice" ;;
  superpowers:subagent-driven-development|superpowers:executing-plans)
    moment="the end-of-work report: what changes for users, what reviews caught, rulings made, open questions" ;;
  superpowers:finishing-a-development-branch)
    moment="the integration choice (PR / merge / keep) together with the work summary and any open question" ;;
  *) exit 0 ;;
esac

context="[revue-artefact] When you reach $moment, do not write it as a long terminal message nor chain AskUserQuestion calls: invoke the Skill osho-core:revue-artefact and publish it as an artifact page where the user ticks answers, then read them back when they say it is done. Keep using AskUserQuestion only for a single simple question."

jq -n --arg c "$context" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $c}}'
