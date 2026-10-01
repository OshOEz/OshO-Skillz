---
name: mantis-run
description: Runs a Mantis security audit campaign on a git repository from Claude Code, with no Google or API key. Each Mantis stage runs as a Claude Code subagent at the level chosen in triage (Light, Sharp, Savage, Overkill), then a French report, suggested patches and an HTML dashboard are written into osho-mantis/audit-<date>/. Use after mantis-triage, when the user says "lance l'audit" or "mantis run", or wants to resume an interrupted audit. Don't use for the quick triage (mantis-triage).
---

# mantis-run

Visibility of the current directory's repo, computed when this skill loaded: !`bash "${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts/check-visibility.sh"`

Paths: `T="${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts"`, `R="${CLAUDE_PLUGIN_ROOT}/skills/mantis-run/scripts"`, `M="$HOME/.local/share/mantis"`.

## 1. Select the audit

- An audit folder was named → `AUDIT` is that folder; refuse it (tell the user and stop) unless its `campaign.json`'s `repo` equals `git -C "$AUDIT" rev-parse --show-toplevel` (both sides are canonical toplevels, so a subdirectory or symlinked path still matches), then `REPO` is that `repo` field.
- Otherwise `REPO=$(git -C "<named repo or current directory>" rev-parse --show-toplevel)` (same canonical form triage writes), and `AUDIT` is the newest `$REPO/osho-mantis/audit-*` whose `state.json` does not contain `"finished": true`, **skipping** any candidate that is tracked by git (`git -C "$REPO" ls-files --error-unmatch "<candidate>" >/dev/null 2>&1`) or whose name encodes a date after today. A legitimate, still-running audit is never committed, so a tracked or future-dated folder is planted: tell the user and ignore it, falling back to the next newest candidate (or to triage if none is left).
- No such folder → invoke the `mantis-triage` skill first, then continue with the audit folder it created.
- **Hostile repo**, first check once `AUDIT` is known: refuse to use the audit folder (tell the user and stop) if `[ -L "$REPO/osho-mantis" ]` or `[ -n "$(find "$AUDIT" -type l -print -quit)" ]`. Audited repos may be hostile third-party code that ships a pre-made `osho-mantis/` folder with symlinks pointing outside the repo.
- `campaign.json` has no `level` → ask the volume question exactly as in mantis-triage step 6, then fill `level`, `hypotheses_max`, `parallel`.
- `campaign.json` has no `versioning` → apply mantis-triage step 2 (the visibility line above, or the script).

## 2. Prepare

1. Mantis source: `if [ -d "$M/.git" ]; then git -C "$M" pull --ff-only -q; else git clone -q https://github.com/google/mantis "$M"; fi`. If the pull fails (for example when offline), continue with the local copy and add a note. Write `git -C "$M" rev-parse --short HEAD` into `campaign.json` as `mantis_commit`.
2. No `state.json` yet → write it with `stages` set to every stage of the level (table below) as `"pending"`, `round: 1`, `notes: []`, `finished: false`, and `git_status_before` set to the output of `git -C "$REPO" status --porcelain -- . ':(exclude)osho-mantis'`.
3. If the level includes reproduce and `docker info` fails → set reproduce to `"skipped"` and add the note « reproduce sauté : Docker indisponible ».
4. Shadow copy (used only by reproduce and patch): if `state.json` has no `shadow` key yet, create one with `mktemp -d` **outside `$REPO` and `$AUDIT`** and save its path there as `shadow`. Then wipe and recopy it from tracked files only, no symlinks — never an incremental rsync, so nothing a previous patch wrote into the shadow (new files included) survives, and a hostile repo's `.venv`/`node_modules` symlinks are never copied into a sandbox a patch agent can write through, nor land under the audit folder where the symlink guard above would (wrongly) block every resume. **Shadow guard — run before every `rm -rf "$SHADOW"` in this skill** (stage agents can rewrite `state.json`'s `shadow`): let `D="$(dirname "$(mktemp -u)")"`; refuse and stop, telling the user, unless `[ -n "$SHADOW" ]`, `[ ! -L "$SHADOW" ]`, `$SHADOW` contains no `..`, `[ "$(dirname "$SHADOW")" = "$D" ]`, and `basename "$SHADOW"` matches `tmp.*` — only an actual `mktemp -d` path passes; `$D/../../../../Users/x`, a sibling of the real shadow like `$D/com.apple.x`, `$HOME`, an empty value, and a symlink (even to a real `mktemp -d` dir) are all refused. Then: `rm -rf "$SHADOW" && mkdir -p "$SHADOW" && git -C "$REPO" ls-files -z | rsync -a --no-links --from0 --files-from=- "$REPO/" "$SHADOW/"` (`$SHADOW` = the path saved in `state.json`).

## 3. Stages

Run the stages in this order, skipping those that are not in the level or are already `done`. Before each stage, set it to `"pending"`. After it, run the check, then set it to `"done"`. Before the reproduce stage specifically, wipe and recopy the shadow (2.4) first — a clean copy, since a prior patch run may have left its diff applied (matters most for Overkill rounds 2–3, where reproduce reruns after a patch round).

| Stage | Mantis dir | Model | Levels | Scope | Check after |
|---|---|---|---|---|---|
| history | mantis-history | haiku | Savage, Overkill | whole repo | `workspace/historical_learnings.jsonl` exists |
| structural-index | mantis-structural-index | haiku | Sharp+ | whole repo | `workspace/kb/structural_index/` exists |
| architecture | mantis-architecture | sonnet | all | whole repo | `workspace/kb/` has a `.md` file |
| threat-model | mantis-threat-model | sonnet | all | whole repo | `workspace/kb/THREAT_MODEL.md` exists |
| plan | mantis-plan | sonnet | all | whole repo | `workspace/plan.json` has 1 to `hypotheses_max` investigations (Overkill: at least 1 — one-per-source-file can exceed `hypotheses_max`) |
| researcher | mantis-researcher | sonnet | all | investigations split into `parallel` contiguous groups | every agent replied; `workspace/findings/` exists |
| dedupe | mantis-dedupe | haiku | Sharp+ | all findings | finding count did not increase |
| review | mantis-review | sonnet | all | findings split into `parallel` groups | each one has `reasoning` |
| critic | mantis-critic | opus | Sharp+ | status `VALID` or `PROVISIONALLY_VALID` | each one has `production_viability` |
| reproduce | mantis-reproduce | opus | Sharp+ | viable (`VIABLE`, `CONDITIONAL_VIABLE`); Sharp: only `CRITICAL` or `HIGH` | each one has `repro_status` |
| chain | mantis-chain | opus | Savage, Overkill | findings with `repro_status` = `reproduced` (skip if fewer than 2) | agent replied |
| patch | mantis-patch | opus | all | Light: status `VALID`/`PROVISIONALLY_VALID`. Sharp+: viable findings, split by `repro_status`: `reproduced` ones go through patch + independent re-attack (see below); the rest (not reproduced, or reproduce was skipped) get the same mitigation-proposal treatment as Light. **One finding at a time**: wipe and recopy the shadow from 2.4 before each one | each one has `patch_status`; reproduced findings also have `reattack_status` |
| calibrate | mantis-calibrate | sonnet | Sharp+ | non-rejected findings, split into `parallel` groups | each one has `mantis_risk_score` |
| reflect | mantis-reflect | sonnet | Savage, Overkill | whole workspace | agent replied |

- "whole repo" scope (history, structural-index, architecture, threat-model, plan, researcher) always means `<REPO>` **excluding the `osho-mantis/` folder** (previous audits and this campaign's own files, not target code); say so in the Scope line. For plan, `<out_of_scope>` always includes `osho-mantis/` in addition to whatever triage set.
- Dispatch parallel groups as several Agent calls in one message (`subagent_type: general-purpose`, with the model from the table).
- A finding is "rejected" if `status` is `FALSE_POSITIVE` or `DUPLICATE`, or if `production_viability` is `NON_VIABLE` or `SAMPLE_OR_TEST`. Rejected findings skip all later stages.
- Per-finding stages are resumable: on a rerun, only the findings in scope that still lack the checked field are processed.
- **Overkill:** the plan stage gets one investigation per source file. After reflect, if `round` < 3, increment `round`, reset plan, researcher, dedupe, review, critic, reproduce, patch, calibrate and reflect to `"pending"`, and run them again (plan then replans from `learnings.jsonl`).
- **Failure** (an agent errors, hits the quota, or the check fails) → set the stage to `"failed"` and stop. Tell the user which stage failed and why, in 2 lines, and that rerunning `/mantis-run` resumes from there. Do not retry in a loop.

### Stage agent prompt

```
You run the Mantis stage `<stage>` of a security audit.
1. Read <M>/<mantis dir>/SKILL.md and follow it in standalone mode with:
   --state_root <AUDIT>      (state files live in <AUDIT>/workspace/)
   --target_root <CODE>      (<CODE> = <REPO>; for reproduce and patch, <SHADOW> — the path saved in state.json)
2. <REPO> is read-only. Write only under <AUDIT>/workspace/.
3. Never build, install, run or test target code on the host; static reading only. Code execution is allowed only in reproduce/patch, via the docker line below.
4. Do not delegate to sub-agents: you are one of <n> parallel workers.
5. Scope: <scope>.            (e.g. "only investigations #4 to #6 of workspace/plan.json",
                               "only findings <id>, <id>", "the whole workspace")
6. <level line>
7. <docker line>              (reproduce and patch only)
8. Reply in 5 lines max: what you wrote (paths or finding ids), and any blocker.
```

- Level line, patch for a finding without `repro_status: reproduced` (Light; or Sharp+ when that finding wasn't reproduced, including every finding when reproduce was `skipped` for lack of Docker): `This finding has no verified reproduction: write patch_diff as a unified diff relative to the repo root (a/<file>, b/<file>) and set patch_status to MITIGATION_PROPOSED. Do not execute any code or attempt a re-attack.`
- Level line, plan: `Write at most <hypotheses_max> investigations. Prioritise these hypotheses: <focus>. Skip: <out_of_scope>.` For Overkill, instead: `One investigation per source file.`
- Level line, otherwise: `Level <level>.`
- Docker line: `Execute target code only with: docker run --rm --network=none <--runtime=runsc if inventory.json repro.runsc> -v "<SHADOW>":/src<:ro for reproduce and the re-attack> <-v "<AUDIT>/workspace/reproducers":/poc:ro for reproduce and the re-attack> -w /src <official image for the stack, e.g. python:3.12-slim> <cmd>. For reproduce and the re-attack, the PoC file you wrote under state_root/workspace/reproducers/ is mounted read-only at /poc — run it as /poc/<file>. Pulling the image is the only network access allowed. Never run target code on the host.`

### Patch + re-attack for reproduced findings (Sharp+)

Upstream `mantis-patch/SKILL.md` only grants `VERIFIED_SECURE` once "a fresh, independent `@mantis-reproduce --reattack` sub-agent" confirms the patch holds — but a Claude Code subagent has no Agent tool, so it cannot launch that sub-agent itself, and point 4 of the common prompt forbids delegating anyway. mantis-run applies the patch and runs the re-attack itself, never one agent grading its own patch — and never trusting that the agent applied the diff it wrote to the tree the re-attack then tests:

For each finding with `repro_status: reproduced`, one at a time:
1. Wipe and recopy the shadow (2.4) — a clean copy for this finding alone.
2. Dispatch the patch agent (stage agent prompt, `mantis-patch`, opus, **no docker line** — it must not execute any code, only write `patch_diff`, scope this one finding), with this level line instead of the ones above: `Write patch_diff as a unified diff relative to the repo root (a/<file>, b/<file>) and set patch_status to VERIFICATION_INCOMPLETE. Do not apply the diff, run any code, or attempt a re-attack yourself — mantis-run applies it and dispatches an independent re-attack agent next.`
3. Wipe and recopy the shadow (2.4) again, immediately before applying — a clean tree for `git apply`, regardless of what happened between step 1 and now.
4. mantis-run itself writes `patch_diff` to a temp file `F` and runs `(cd "$SHADOW" && git apply --check "$F" && git apply "$F")`. On failure: set `patch_status` to `VERIFICATION_FAILED`, add a note naming the finding, and skip steps 5–6 for it (no re-attack).
5. Dispatch a second, separate agent (stage agent prompt, Mantis dir `mantis-reproduce`, opus, docker line, scope this one finding), with this level line: `Follow mantis-reproduce in --reattack mode against the patched code at <SHADOW> (the patch is already applied there by mantis-run): attempt to reproduce the finding again and write reattack_status (failed_to_bypass or bypassed_patch).`
6. mantis-run itself sets the finding's final `patch_status` from `reattack_status`: `failed_to_bypass` → `VERIFIED_SECURE`; `bypassed_patch` → `VERIFICATION_FAILED`; anything else (missing or unclear) → `VERIFICATION_INCOMPLETE`.
7. Check: this finding has `patch_status`, and also `reattack_status` unless step 4 skipped the re-attack.

## 4. Finish

1. Integrity: compare `git -C "$REPO" status --porcelain -- . ':(exclude)osho-mantis'` with `git_status_before`. If they differ, warn the user first, listing the files that changed, and do not discard anything.
2. Shadow guard (2.4), then `rm -rf "$SHADOW"` (the path saved as `shadow` in `state.json`), then drop that key.
3. Set `finished: true` in `state.json` and `finished_at` (`date +%Y-%m-%dT%H:%M:%S`) in `campaign.json`.
4. `python3 "$R/render.py" "$AUDIT"`, then `open "$AUDIT/dashboard.html"`.
5. Report, 5 lines max: counts by severity, the top Critical or High finding, the `README.md` path. If `versioning` is `versioned`, end with: `git -C "<REPO>" add "osho-mantis/<audit name>" && git -C "<REPO>" commit -m "Audit de sécurité Mantis <date>"`. Never commit yourself.
