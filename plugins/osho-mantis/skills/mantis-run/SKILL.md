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
- **Hostile repo**, first check once `AUDIT` is known: run `if [ -L "$REPO/osho-mantis" ] || [ -n "$(find "$AUDIT" -type l -print -quit)" ]; then echo HOSTILE; fi` (exits 0 either way). If it printed `HOSTILE`, tell the user and stop instead of using the audit folder. Audited repos may be hostile third-party code that ships a pre-made `osho-mantis/` folder with symlinks pointing outside the repo.
- **Live dashboard**, only after the hostile check passed: `python3 "$R/dashboard.py" serve "$AUDIT"` prints one JSON line `{"url", "reused"}`. If `reused` is `false`, `open "<url>"`. Always print the URL in the terminal as a fallback. Then clear leftovers of an interrupted session: `rm -f "$AUDIT/waiting.json"`, and drop `paused`, `stopped` and `current` from `state.json` if present. Then, unless this session still tracks a running fix agent for this audit (Fix agent finished, 3: its worktree must not be reclaimed under it; any other `running` entry was already reconciled when this session first opened the audit), `python3 "$R/fixes.py" reconcile "$AUDIT"` (re-evaluates `running` fixes whose agent died with the previous session; one JSON line each): say one line per entry, « Correction <stem> : <status> <error> ». Then Launch fixes (3) for requests queued by a previous session.
- **Resume after a cut** (quota, closed session), when `state.json` exists and is not finished: `python3 "$R/guard.py" check "$AUDIT"`; if it prints lines, `python3 "$R/guard.py" restore "$AUDIT"` and add the note « findings restaurés à la reprise : <files> ». Remove orphan containers of **this audit only**: `docker ps -aq --filter name=mantis-<audit name>- | xargs -r docker rm -f` (never another project's). Then `python3 "$R/guard.py" resume "$AUDIT"` (rewrites `RESUME.md`, the human-readable checklist).
- **Queue left by the dashboard** while no session was listening: `python3 "$R/dashboard.py" pending "$AUDIT"`, then for each command in order: `launch` → ack `applied` (it is the user's go-ahead); `resume` → drop `paused`, ack `applied`; `retry` whose `stage` is `failed` → set it to `"pending"`, ack `applied` (otherwise refused « plus d'actualité »); `pause`, `stop`, `answer`, `end_fixes` → ack `refused` « plus d'actualité »; `fix`, `false_positive`, `prioritize_repro`, `merge_fix`, `set_cost`, `recompute_cost` → as in the Checkpoint (3).
- The named audit's `state.json` has `"finished": true` → go straight to 5 (Corrections): skip the rest of 1 and 2 to 4, no stage reruns.
- `campaign.json` has no `level` → ask the launch question exactly as in mantis-triage step 6 (waiting.json, plain text, Monitor) but without the « Plus tard » option, then fill `level`, `hypotheses_max`, `parallel`, `started_at`.
- `campaign.json` has no `versioning` → apply mantis-triage step 2 (the visibility line above, or the script).

## 2. Prepare

1. Mantis source: `if [ -d "$M/.git" ]; then git -C "$M" pull --ff-only -q; else git clone -q https://github.com/google/mantis "$M"; fi`. If the pull fails (for example when offline), continue with the local copy and add a note. Write `git -C "$M" rev-parse --short HEAD` into `campaign.json` as `mantis_commit`.
2. No `state.json` yet → write it with `stages` set to every stage of the level (table below) as `"pending"`, `round: 1`, `notes: []`, `finished: false`, `git_status_before` set to the output of `git -C "$REPO" status --porcelain -- . ':(exclude)osho-mantis'`, and `base_commit` set to `git -C "$REPO" rev-parse HEAD` (omit the key if the repo has no commit yet).
3. If the level includes reproduce and `docker info` fails → set reproduce to `"skipped"` and add the note « reproduce sauté : Docker indisponible ».
4. Shadow copy (used only by reproduce and patch): if `state.json` has no `shadow` key yet, create one with `mktemp -d` **outside `$REPO` and `$AUDIT`** and save its path there as `shadow`. Then wipe and recopy it from tracked files only, no symlinks — never an incremental rsync, so nothing a previous patch wrote into the shadow (new files included) survives, and a hostile repo's `.venv`/`node_modules` symlinks are never copied into a sandbox a patch agent can write through, nor land under the audit folder where the symlink guard above would (wrongly) block every resume. **Shadow guard — run before every `rm -rf "$SHADOW"` in this skill** (stage agents can rewrite `state.json`'s `shadow`, and `$TMPDIR` can differ across sessions): let `D="$(dirname "$(mktemp -u)")"`; it passes only if `[ -n "$SHADOW" ]`, `[ -d "$SHADOW" ]`, `[ ! -L "$SHADOW" ]`, `$SHADOW` contains no `..`, `[ "$(dirname "$SHADOW")" = "$D" ]`, and `basename "$SHADOW"` matches `tmp.*` — only an actual, still-existing `mktemp -d` path passes; `$D/../../../../Users/x`, a sibling of the real shadow like `$D/com.apple.x`, `$HOME`, an empty value, a path that no longer exists, and a symlink (even to a real `mktemp -d` dir) all fail it. A path that fails the guard is never deleted or touched. Here, and at every other "wipe and recopy the shadow (2.4)" call site: if it passes, `rm -rf "$SHADOW" && mkdir -p "$SHADOW"`; if it fails (missing, gone, or rejected — a plain `$TMPDIR` mismatch on resume is enough), instead `mktemp -d` a fresh one, save it as the new `shadow` in `state.json`, and add the note « shadow recréé : ancien chemin refusé ou absent ». Either way finish with: `git -C "$REPO" ls-files -z | rsync -a --no-links --from0 --files-from=- "$REPO/" "$SHADOW/"` (`$SHADOW` = the current value, freshly recreated or not). A bare "Shadow guard (2.4)" check with no recopy (Finish, 4.2) still stops and tells the user on failure instead of deleting.

5. **Dependency volume** (Sharp+, reproduce not `skipped`, no `deps_volume` in `state.json` yet), automatic, no question: from `inventory.json` `manifests`, pick the stacks present (Maven `pom.xml`, Gradle `build.gradle*`, npm `package.json`, pip `requirements.txt`/`pyproject.toml`). Say in the terminal and add the note « remplissage du volume de dépendances, avec réseau ». `V=mantis-<repo name>-deps`; `docker volume create "$V"`; then one container **with network**, repo read-only, per stack and manifest directory, e.g. `docker run --rm --name mantis-<audit name>-deps -v "$SHADOW":/src:ro -v "$V":/deps maven:3-eclipse-temurin-21 sh -c 'cp -r /src/<dir> /tmp/b && cd /tmp/b && mvn -q -Dmaven.repo.local=/deps/m2 dependency:go-offline'`, `npm ci --ignore-scripts` into `/deps/npm/<dir>/node_modules`, `pip download -d /deps/pip/<dir> -r …`. A failure is a note, not a stop (reproduction then runs without it). Write `deps_volume: "$V"` into `state.json`. The volume is kept after the audit (reused by a re-audit); the report says how to remove it.

## 3. Stages

Run the stages in this order, skipping those that are not in the level or are already `done`. Before each stage, run the checkpoint (below), then set the stage to `"running"` and run `python3 "$R/guard.py" resume "$AUDIT"`. **Findings guard**: before dedupe, review, critic, reproduce, patch and calibrate, `python3 "$R/guard.py" backup "$AUDIT" <stage>`; after every batch of these stages returns, `python3 "$R/guard.py" check "$AUDIT"`, and if it prints lines, `python3 "$R/guard.py" restore "$AUDIT"` then rerun those findings in the next batch and add the note « <stage> : findings abîmés par un agent, restaurés : <files> ». Before dispatching each batch of agents (one message of parallel Agent calls; a single agent is batch `1/1`; in Patch Sharp+, one finding is one batch), write `current: {"stage": "<stage>", "batch": "<k>/<n>", "workers": <agents in this batch>, "model": "<model>"}` into `state.json`; after each batch returns, run the checkpoint. After the stage, drop `current`, run the check, then set the stage to `"done"`. Before the reproduce stage specifically, wipe and recopy the shadow (2.4) first — a clean copy, since a prior patch run may have left its diff applied (matters most for Overkill rounds 2–3, where reproduce reruns after a patch round).

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
| reproduce | mantis-reproduce | opus | Sharp+ | viable (`VIABLE`, `CONDITIONAL_VIABLE`); Sharp: only `CRITICAL` or `HIGH`; plus, at every level, the non-rejected findings listed in `state.json`'s `force_repro` (finding file stems under `workspace/findings/`), **even if they already have a `repro_status`**, unless their `repro_round` equals the current `round` | each one has `repro_status`; each `force_repro` one has `repro_round` = `round` (then drop it from `force_repro`) |
| chain | mantis-chain | opus | Savage, Overkill | findings with `repro_status` = `reproduced` (skip if fewer than 2) | agent replied |
| patch | mantis-patch | Light: sonnet · Sharp+: opus | all | Light: status `VALID`/`PROVISIONALLY_VALID`, split into `parallel` groups (the patch agent never applies or runs anything, so no shadow needed). Sharp+: viable findings, split by `repro_status`: `reproduced` ones go through patch + independent re-attack (see below); the rest (not reproduced, or reproduce was skipped) get the same mitigation-proposal treatment as Light in groups of `parallel` (checkpoint before each group), each finding with its own shadow as in Patch + re-attack below | each one has `patch_status`; reproduced findings also have `reattack_status`, unless `patch_status` is `VERIFICATION_FAILED` from a failed `git apply` (re-attack step 5 was skipped) |
| calibrate | mantis-calibrate | sonnet | Sharp+ | non-rejected findings, split into `parallel` groups | each one has `mantis_risk_score` |
| reflect | mantis-reflect | sonnet | Savage, Overkill | whole workspace | agent replied |

- "whole repo" scope (history, structural-index, architecture, threat-model, plan, researcher) always means `<REPO>` **excluding the `osho-mantis/` folder** (previous audits and this campaign's own files, not target code); say so in the Scope line. For plan, `<out_of_scope>` always includes `osho-mantis/` in addition to whatever triage set.
- Dispatch parallel groups as several Agent calls in one message (`subagent_type: general-purpose`, with the model from the table).
- A finding is "rejected" if `status` is `FALSE_POSITIVE` or `DUPLICATE`, or if `production_viability` is `NON_VIABLE` or `SAMPLE_OR_TEST`. Rejected findings skip all later stages.
- **Fix scope:** findings printed by `python3 "$R/fixes.py" busy "$AUDIT"` (fix `running`, `ready` or `merged`) are out of scope of critic, reproduce, patch and calibrate, like rejected ones. Rerun it at the start of each of these stages and before each finding in Patch Sharp+; a stage's Check after uses the scope computed at that stage's start.
- Per-finding stages are resumable: on a rerun, only the findings in scope that still lack the checked field are processed.
- **Patch scope, later passes** (Sharp+): a finding whose `repro_status` became `reproduced` while its `patch_status` is `MITIGATION_PROPOSED` (round-1 proposal never re-attacked) goes through patch + re-attack. Overkill rounds 2 and 3 also take every `VERIFICATION_FAILED` finding (move its `patch_diff`, `reattack_status` and `reattack_output` summary into a `previous_patches` list on the finding before the patch agent runs; the patch level line then adds: `A previous patch was bypassed (see previous_patches). Before writing the diff, list every sibling of the vulnerable primitive (other routes, loggers, callers, limiters) and fix them at the shared choke point.`) and every non-rejected `LOW` with `mantis_risk_score` ≥ 5.0 that has no `patch_status`.
- **API refusal** (an agent stops on a safety filter): note « <stage> : refus du filtre de l'API pour <ids> », leave those findings as they are (`statically_confirmed` stays), no automatic retry.
- **Overkill:** the plan stage gets one investigation per source file. After reflect, if `round` < 3, increment `round`, reset plan, researcher, dedupe, review, critic, reproduce, patch, calibrate and reflect to `"pending"`, and run them again (plan then replans from `learnings.jsonl`).
- **Failure** (an agent errors, hits the quota, or the check fails) → set the stage to `"failed"`, drop `current`, write `waiting.json` as `{"kind": "failed", "stage": "<stage>", "reason": "<why, 2 lines>", "since": "<date +%Y-%m-%dT%H:%M:%S>"}`, then wait for the user (below) with the options « relancer » and « arrêter ». Do not retry on your own.

### Checkpoint

Run before each stage, after each batch of agents returns, and in Patch Sharp+ between two findings. `python3 "$R/dashboard.py" pending "$AUDIT"` prints the unacknowledged commands, one JSON object per line (`{id, at, source, action, ...}`, `finding` = finding file stem); nothing printed → continue. Handle them in order; every command ends acknowledged:
- `false_positive`, `prioritize_repro`, `merge_fix`, `set_cost`, `recompute_cost` → `python3 "$R/dashboard.py" apply "$AUDIT" <id>` (validates, writes the finding or `force_repro` or merges the fix, and acks it itself).
- `fix` → `apply` (queues the fix and acks), then **Launch fixes** (below).
- `end_fixes` → `python3 "$R/dashboard.py" ack "$AUDIT" <id> refused "le mode Corrections n'est pas actif"`.
- `pause` → set `paused: true` in `state.json`, `python3 "$R/dashboard.py" ack "$AUDIT" <id> applied`, then wait for the user (below) with `kind: "paused"`.
- `stop` → **Stop** (then `python3 "$R/guard.py" resume "$AUDIT"`): first `apply` every other pending `fix` (queued for the resume, not launched); running fix agents are not stopped (they finish in the background, 1 reconciles them on resume). Then set the `running` stage, if any, back to `"pending"`, drop `current` and `paused`, set `stopped: true`, `rm -f "$AUDIT/waiting.json"`, ack `applied`, ack every other pending command `refused` « audit arrêté » (a leftover `stop` would end the next resume), run Finish 1, 2 and 4 (skip those whose inputs do not exist yet; never 3, so no `finished`), tell the user in 2 lines that the audit is stopped and `/mantis-run` resumes from there, and end.
- `resume`, `retry`, `answer` outside a wait → `python3 "$R/dashboard.py" ack "$AUDIT" <id> refused "aucune attente en cours"`.

### Wait for the user (pause, failure, question)

1. `waiting.json` is written: pause `{"kind": "paused", "since"}`, failure as above, question as in mantis-triage step 6 (`since` = `date +%Y-%m-%dT%H:%M:%S`).
2. Say it in the terminal in plain text (no AskUserQuestion: it would block the page's answer): pause « En pause. Réponds « reprendre » ou « arrêter », ici ou sur le dashboard. »; failure: the stage, the 2-line reason, then « Réponds « relancer » ou « arrêter », ici ou sur le dashboard. »; question: its options, numbered.
3. Start the Monitor tool (`timeout_ms` 1800000) with `until [ -n "$(python3 "$R/dashboard.py" pending "$AUDIT")" ]; do sleep 2; done`, then end your turn.

On wake-up (Monitor event or typed reply): a Monitor event when `$AUDIT/waiting.json` no longer exists is stale: ignore it and do not re-arm Monitor. Otherwise run `pending` first and handle each command in order:
- `false_positive`, `prioritize_repro`, `fix`, `merge_fix` → `apply` as in the checkpoint (`fix` then Launch fixes); the wait goes on.
- `resume` (paused) → drop `paused`. `retry` whose `stage` is the failed one → set it to `"pending"`. `answer` to the current question → take its `value`. Each lifts the wait: ack `applied`, then `rm "$AUDIT/waiting.json"`; if Monitor is still running (the wait was lifted by a typed reply), stop it with TaskStop on its task id; handle the remaining pending commands with the checkpoint rules (a duplicate `resume`, `retry` or `answer` is refused there); then continue where the audit was (the stage loop reruns a `pending` stage).
- `stop` → Stop, as in the checkpoint (TaskStop a still-running Monitor first).
- Any other command (`pause` while waiting, `retry` of another stage, `answer` to another question) → ack `refused` « ne correspond pas à l'attente en cours »; the wait goes on.
- No pending command and the user typed a reply → map it (« reprendre » → `{"action": "resume"}`, « relancer » → `{"action": "retry", "stage": "<stage>"}`, « arrêter » → `{"action": "stop"}`, a question answer as in mantis-triage step 6), record it with `python3 "$R/dashboard.py" command "$AUDIT" '<json>'` (exit 2 → tell the user the printed reason and stay waiting), then handle it like a page command. Unclear reply → ask again.
- Wait not lifted → back to 3.

Monitor expired with no command → if `$AUDIT/waiting.json` no longer exists, ignore this event and do not re-arm Monitor. Otherwise if `python3 "$R/dashboard.py" alive "$AUDIT"` exits 0 (server running), start Monitor again and end your turn; otherwise `rm "$AUDIT/waiting.json"`, say « Dashboard arrêté : relance `/mantis-run`. » and end.

### From the terminal

A request typed at any time in natural language (« mets en pause », « marque f-014 en faux positif », « reproduis f-020 en priorité », « corrige f-014 », « merge f-014 », « terminé », « arrête l'audit ») → build the matching command (`pause`, `false_positive`/`prioritize_repro`/`fix`/`merge_fix` with `finding` = the file stem under `workspace/findings/`, `end_fixes`, `stop`) and record it with `python3 "$R/dashboard.py" command "$AUDIT" '<json>'`. Exit 2 → tell the user the printed reason. Otherwise it shows on the page and is handled at the next checkpoint.

### Launch fixes

For each stem printed by `python3 "$R/fixes.py" launchable "$AUDIT"` (queued fixes, at most 3 fix agents running at once):
1. `python3 "$R/fixes.py" start "$AUDIT" <stem>` prints the entry as JSON (`status`, `branch`, `worktree`, `agent`, `title`, `bucket`, `msg_file`, `prev_diff`, `dirty`, `repo`, `audit`). Exit 2, or `status` is `failed` → say it in one line (the printed reason or `error`) and go to the next stem.
2. Agent call with `run_in_background: true`, `subagent_type: general-purpose`, `description` = `agent` (`Correctif <stem court>`, unique within the audit), model `opus` if `bucket` is `CRITICAL`, else `sonnet`, and the fix agent prompt below.
3. Add `{agent, stem, at}` (`at` from `start`) to this session's list of fix agents launched and not yet seen finish. Say « Correction lancée : <title> » in one line, then carry on where you were, without waiting for the agent.

### Fix agent prompt

```
You fix one security finding of a Mantis audit in a git worktree.
Worktree (your only writable location): <WORKTREE>, on branch <FIX_BRANCH>.
Finding: <AUDIT>/workspace/findings/<stem>.json (read it: title, description, code_paths, reasoning, patch_diff if any).
1. Fix the root cause with the smallest change. If patch_diff exists, start from it and adapt it to the current code.
2. Edit only files inside <WORKTREE>. Never touch <REPO>, other branches, or <AUDIT>.
3. Never build, install, run or test target code on the host (static work only).
4. Commit once: git -C <WORKTREE> add -A && git -C <WORKTREE> -c core.hooksPath=/dev/null commit -q -F <MSG_FILE>. Do not push, do not merge.
5. If you cannot fix it safely, commit nothing and say why.
<prev_diff line>
<dirty line>
Reply in 3 lines: commit sha or « aucun », files changed, any doubt.
```

- `<stem>` = the stem passed to `start`; `<WORKTREE>`, `<FIX_BRANCH>`, `<MSG_FILE>`, `<REPO>`, `<AUDIT>` = `worktree`, `branch`, `msg_file`, `repo`, `audit` from `start`. Never put the finding's title in the prompt: the commit message is already in `<MSG_FILE>`.
- Prev_diff line, only if `prev_diff` is set: `A previous attempt conflicted with another merged fix: <PREV_DIFF>. Redo it on the current code.`
- Dirty line, only if `dirty` is true: `The audit also covered uncommitted changes: your worktree starts from the last commit. If the code the finding targets is not there, commit nothing and answer « aucun ».`
- Omit a line whose condition is false.

### Fix agent finished

Applies to the notification that a background `Correctif …` agent finished, at any time in this session: during the audit, in Corrections mode, after its Exit, or outside an audit (`$AUDIT` = the audit it was launched for). Take its `{stem, at}` from this session's list (match on `agent`) and drop it from the list. Act only if `fixes.json[stem]` still has `status` `running` and that same `at`; otherwise the notification is stale (an older run of a stem since relaunched or reconciled): say so in one line and stop here. Otherwise:
- it ended normally (it replied) → `python3 "$R/fixes.py" finish "$AUDIT" <stem>` (`ready` if it committed and left the worktree clean, else `failed` with the reason);
- it failed (error, quota) → `python3 "$R/fixes.py" fail "$AUDIT" <stem> "<one-line reason>"`.

Say the resulting `status` (and `error`) in one line, then Launch fixes (a slot is free). If a Monitor wait is running, leave it: do not start another one.

### Stage agent prompt

```
You run the Mantis stage `<stage>` of a security audit.
1. Read <M>/skills/<mantis dir>/SKILL.md and follow it in standalone mode with:
   --state_root <AUDIT>      (state files live in <AUDIT>/workspace/)
   --target_root <CODE>      (<CODE> = <REPO>; for reproduce and patch, <SHADOW> — the path saved in state.json)
2. <REPO> is read-only. Write only under <AUDIT>/workspace/.
3. Never build, install, run or test target code on the host, never run an interpreter (python, node, java, mvn, dart…) on the host for the target, never copy files from other folders of this machine; static reading only. Code execution is allowed only in reproduce/patch, via the docker line below.
   Writing a finding: write to a new file under <AUDIT>/workspace/tmp/, check it parses and keeps every field it had, then rename it over the original. Never `jq … > same_file`. Temporary files only under <AUDIT>/workspace/tmp/.
4. Do not delegate to sub-agents: you are one of <n> parallel workers.
5. Scope: <scope>.            (e.g. "only investigations #4 to #6 of workspace/plan.json",
                               "only findings <id>, <id>", "the whole workspace")
6. <level line>
7. <docker line>              (reproduce and patch only)
8. Reply in 5 lines max: what you wrote (paths or finding ids), and any blocker.
```

- Level line, patch for a finding without `repro_status: reproduced` (Light; or Sharp+ when that finding wasn't reproduced, including every finding when reproduce was `skipped` for lack of Docker): `This finding has no verified reproduction: write patch_diff as a unified diff relative to the repo root (a/<file>, b/<file>) and set patch_status to MITIGATION_PROPOSED. Do not execute any code or attempt a re-attack.`
- Level line, plan: `Write at most <hypotheses_max> investigations. Prioritise these hypotheses: <focus>. Skip: <out_of_scope>.` For Overkill, instead: `One investigation per source file.`
- Level line, reproduce: `Level <level>. Write repro_round: <round> in every finding you process. If the code needs AWS Secrets Manager or a third-party upstream (Google, payment, maps…), run an in-container stand-in on a docker network created with --internal, never the real endpoint, and save the stand-in under workspace/reproducers/ so later rounds reuse it.`
- Level line, otherwise: `Level <level>.`
- Docker line: `Execute target code only with: docker run --rm --name mantis-<audit name>-<stem>-<n> --network=none <-v "<deps_volume>":/deps:ro if state.json has deps_volume, with offline flags such as mvn -o -Dmaven.repo.local=/deps/m2 or NODE_PATH=/deps/npm/<dir>/node_modules> <--runtime=runsc if inventory.json repro.runsc> -v "<SHADOW>":/src<:ro for reproduce and the re-attack> <-v "<AUDIT>/workspace/reproducers":/poc:ro for reproduce and the re-attack> -w /src <official image for the stack, e.g. python:3.12-slim> <cmd>. For reproduce and the re-attack, the PoC file you wrote under state_root/workspace/reproducers/ is mounted read-only at /poc — run it as /poc/<file>. Pulling the image is the only network access allowed. Never run target code on the host.`

### Patch + re-attack for reproduced findings (Sharp+)

Upstream `mantis-patch/SKILL.md` only grants `VERIFIED_SECURE` once "a fresh, independent `@mantis-reproduce --reattack` sub-agent" confirms the patch holds — but a Claude Code subagent has no Agent tool, so it cannot launch that sub-agent itself, and point 4 of the common prompt forbids delegating anyway. mantis-run applies the patch and runs the re-attack itself, never one agent grading its own patch — and never trusting that the agent applied the diff it wrote to the tree the re-attack then tests:

Findings with `repro_status: reproduced` run in groups of `parallel` (checkpoint before each group), **each with its own shadow**: `mktemp -d` per finding, path appended to `state.json`'s `shadows` list (same Shadow guard as 2.4, same recopy from tracked files), removed with the guard once the finding is done. Steps 1 to 7 run per finding inside a group (dispatch the group's patch agents in one message, then their re-attack agents in one message); `$SHADOW` below means that finding's own shadow.
1. Wipe and recopy the shadow (2.4) — a clean copy for this finding alone.
2. Dispatch the patch agent (stage agent prompt, `mantis-patch`, opus, **no docker line** — it must not execute any code, only write `patch_diff`, scope this one finding), with this level line instead of the ones above: `Write patch_diff as a unified diff relative to the repo root (a/<file>, b/<file>) and set patch_status to VERIFICATION_INCOMPLETE. Do not apply the diff, run any code, or attempt a re-attack yourself — mantis-run applies it and dispatches an independent re-attack agent next.`
3. Wipe and recopy the shadow (2.4) again, immediately before applying — a clean tree for `git apply`, regardless of what happened between step 1 and now.
4. mantis-run itself writes `patch_diff` to a temp file `F` and runs `(cd "$SHADOW" && git apply --check "$F" && git apply "$F")`. On failure: set `patch_status` to `VERIFICATION_FAILED`, add a note naming the finding, and skip steps 5–6 for it (no re-attack).
5. Dispatch a second, separate agent (stage agent prompt, Mantis dir `mantis-reproduce`, opus, docker line, scope this one finding), with this level line: `Follow mantis-reproduce in --reattack mode against the patched code at <SHADOW> (the patch is already applied there by mantis-run): attempt to reproduce the finding again and write reattack_status (failed_to_bypass or bypassed_patch).`
6. mantis-run itself sets the finding's final `patch_status` from `reattack_status`: `failed_to_bypass` → `VERIFIED_SECURE`; `bypassed_patch` → `VERIFICATION_FAILED`; anything else (missing or unclear) → `VERIFICATION_INCOMPLETE`.
7. Check: this finding has `patch_status`, and also `reattack_status` unless step 4 skipped the re-attack.

## 4. Finish

1. Integrity: compare `git -C "$REPO" status --porcelain -- . ':(exclude)osho-mantis'` with `git_status_before`. If they differ, warn the user first, listing the files that changed, and do not discard anything.
2. Shadow guard (2.4), then `rm -rf "$SHADOW"` (the path saved as `shadow` in `state.json`), then drop that key; same for every path left in `shadows`.
3. Set `finished: true` in `state.json` and `finished_at` (`date +%Y-%m-%dT%H:%M:%S`) in `campaign.json`.
4. `python3 "$R/cost.py" "$AUDIT"` (estimated cost and active time from this session's transcripts, into `cost.json`; never fatal), then `python3 "$R/render.py" "$AUDIT"` (writes `README.md`, `patches/`, `dashboard.html` and `bilan.html`; no `open`: the live page is already open and shows « Audit terminé »).
5. Report, 5 lines max: counts by severity, the top Critical or High finding, the `bilan.html` path, the `dashboard.html` path (for later reading; its Bilan tab exports the light and full archives). If `fixes.json` has `n` > 0 entries with `"status": "merged"`, add « <n> correctifs sur `mantis/<audit name>` : `git merge mantis/<audit name>` ». The commit line of `versioned` audits comes at the end of §5 Corrections (Exit), since it stops the server.
6. Enter 5 (Corrections).

## 5. Corrections

Listening mode after the audit, so Corriger keeps working. It reuses Wait for the user (3), with these differences:
1. Write `waiting.json` as `{"kind": "fixes", "since"}`. Say « Claude attend tes demandes de correction : clique Corriger sur le dashboard, ou tape « corrige <id> ». Tape « terminé » pour finir. »
2. Start Monitor (`timeout_ms` 1800000) with the same `pending` loop as Wait for the user step 3, then end your turn.
3. On wake-up (Monitor event or typed reply; a Monitor event when `$AUDIT/waiting.json` no longer exists is stale: ignore it, do not re-arm), run `pending` and handle each command in order:
   - `fix` → `apply`, then Launch fixes;
   - `merge_fix`, `false_positive`, `prioritize_repro` → `apply`;
   - `end_fixes` → ack `applied`, then Exit (5);
   - `pause`, `resume`, `retry`, `answer`, `stop` → ack `refused` « l'audit est terminé ».

   Then start Monitor again (TaskStop the still-running one first if the wake-up was a typed reply). A fix agent's notification goes to Fix agent finished (3) and never re-arms Monitor.
4. Monitor expired with no command (ignored if `$AUDIT/waiting.json` no longer exists): if `python3 "$R/fixes.py" active "$AUDIT"` prints a stem (fix queued or running), start Monitor again if `python3 "$R/dashboard.py" alive "$AUDIT"` exits 0, otherwise Exit; nothing active (30 min without a click) → Exit.
5. Exit: TaskStop a still-running Monitor, `rm -f "$AUDIT/waiting.json"`, say « Mode Corrections terminé. `/mantis-run <audit name>` le rouvre. », plus `git merge mantis/<audit name>` if `fixes.json` has `merged` entries. Fix agents still running keep going; the next `/mantis-run` reconciles them (1). If `versioning` is `versioned`, end with (stopping the server first deletes `server.json`, which holds the session key, so it is never committed): `python3 "$R/dashboard.py" stop "<AUDIT>" && git -C "<REPO>" add "osho-mantis/<audit name>" && git -C "<REPO>" commit -m "Audit de sécurité Mantis <date>"`. Never commit yourself. Then end.
6. From the terminal: « corrige f-014 » → `{"action": "fix", "finding": "<stem>"}`, « merge f-014 » → `{"action": "merge_fix", "finding": "<stem>"}`, « terminé » → `{"action": "end_fixes"}`; the typed id resolves to the file stem under `workspace/findings/`, as for `false_positive`. Record it with `python3 "$R/dashboard.py" command "$AUDIT" '<json>'` (exit 2 → tell the user the printed reason and keep listening), then handle it like a page command.
