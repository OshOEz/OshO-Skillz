---
name: mantis-run
description: Runs a Mantis security audit campaign on a git repository from Claude Code, with no Google or API key. Each Mantis stage runs as a Claude Code subagent at the level chosen in triage (Light, Sharp, Savage, Overkill), then a French report, suggested patches and an HTML dashboard are written into osho-mantis/audit-<date>/. Use after mantis-triage, when the user says "lance l'audit" or "mantis run", or wants to resume an interrupted audit. Don't use for the quick triage (mantis-triage).
---

# mantis-run

Visibility of the current directory's repo, computed when this skill loaded: !`bash "${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts/check-visibility.sh"`

Paths: `T="${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts"`, `R="${CLAUDE_PLUGIN_ROOT}/skills/mantis-run/scripts"`, `M="$HOME/.local/share/mantis"`.

References: `wait.md`, `fixes.md` and `patch-reattack.md` live in `${CLAUDE_PLUGIN_ROOT}/skills/mantis-run/references/`. A section marked `(references/<file>.md)` is in that file: read it when you reach a step tagged with it, not before.

## 1. Select the audit

- An audit folder was named → `AUDIT` is that folder; refuse it (tell the user and stop) unless its `campaign.json`'s `repo` equals `git -C "$AUDIT" rev-parse --show-toplevel` (both sides are canonical toplevels, so a subdirectory or symlinked path still matches), then `REPO` is that `repo` field.
- Otherwise `REPO=$(git -C "<named repo or current directory>" rev-parse --show-toplevel)` (same canonical form triage writes), and `AUDIT` is the newest `$REPO/osho-mantis/audit-*` whose `state.json` does not contain `"finished": true`, **skipping** any candidate that is tracked by git (`git -C "$REPO" ls-files --error-unmatch "<candidate>" >/dev/null 2>&1`) or whose name encodes a date after today. A legitimate, still-running audit is never committed, so a tracked or future-dated folder is planted: tell the user and ignore it, falling back to the next newest candidate (or to triage if none is left).
- No such folder → invoke the `mantis-triage` skill first, then continue with the audit folder it created.
- **Hostile repo**, first check once `AUDIT` is known: run `if [ -L "$REPO/osho-mantis" ] || [ -n "$(find "$AUDIT" -type l -print -quit)" ]; then echo HOSTILE; fi` (exits 0 either way). If it printed `HOSTILE`, tell the user and stop instead of using the audit folder. Audited repos may be hostile third-party code that ships a pre-made `osho-mantis/` folder with symlinks pointing outside the repo.
- **Live dashboard**, only after the hostile check passed: `python3 "$R/dashboard.py" serve "$AUDIT"` prints one JSON line `{"url", "reused"}`. If `reused` is `false`, open it: `open "<url>"` on macOS, `xdg-open "<url>"` if it exists, otherwise nothing. Always print the URL in the terminal as a fallback. Then clear leftovers of an interrupted session: `rm -f "$AUDIT/waiting.json"`, and drop `paused`, `stopped` and `current` from `state.json` if present. Then, unless this session still tracks a running fix agent for this audit (Fix agent finished, 3 (references/fixes.md): its worktree must not be reclaimed under it; any other `running` entry was already reconciled when this session first opened the audit), `python3 "$R/fixes.py" reconcile "$AUDIT"` (re-evaluates `running` fixes whose agent died with the previous session; one JSON line each): say one line per entry, « Correction <stem> : <status> <error> ». Then Launch fixes (3) (references/fixes.md) for requests queued by a previous session.
- **Resume after a cut** (quota, closed session), when `state.json` exists and is not finished: `python3 "$R/guard.py" check "$AUDIT"`; if it prints lines, `python3 "$R/guard.py" restore "$AUDIT"` and add the note « findings restaurés à la reprise : <files> ». Remove orphan containers of **this audit only**: `docker ps -aq --filter name=mantis-<audit name>- | xargs -r docker rm -f` (never another project's). Then `python3 "$R/guard.py" resume "$AUDIT"` (rewrites `RESUME.md`, the human-readable checklist).
- **Queue left by the dashboard** while no session was listening: `python3 "$R/dashboard.py" pending "$AUDIT"`, then for each command in order: `launch` → ack `applied` (it is the user's go-ahead); `resume` → drop `paused`, ack `applied`; `retry` whose `stage` is `failed` → set it to `"pending"`, ack `applied` (otherwise refused « plus d'actualité »); `pause`, `stop`, `answer`, `end_fixes` → ack `refused` « plus d'actualité »; `fix`, `false_positive`, `prioritize_repro`, `merge_fix`, `set_cost`, `recompute_cost` → as in the Checkpoint (3).
- The named audit's `state.json` has `"finished": true` → go straight to 5 (Corrections) (references/fixes.md): skip the rest of 1 and 2 to 4, no stage reruns.
- `campaign.json` has no `level` → ask the launch question exactly as in mantis-triage step 6 (waiting.json, plain text, Monitor) but without the « Plus tard » option, then fill `level`, `hypotheses_max`, `parallel`, `started_at`.
- `campaign.json` has no `versioning` → apply mantis-triage step 2 (the visibility line above, or the script).

## 2. Prepare

1. Mantis source, pinned to the accepted commit of `mantis.lock`: `python3 "$R/mantis_source.py" ensure --dir "$M"` (clones or repoints `$M` and checks out that commit; never pulls). A non-zero exit (commit not found, or no clone and no network): tell the user the reason it printed and stop; never fall back to the latest Mantis. Write the `commit` of its JSON line into `campaign.json` as `mantis_commit`. Then `python3 "$R/mantis_source.py" behind --dir "$M"` (always exits 0): if `behind` is a number above 0, say to the user « Mantis a <n> commits de plus que la version figée : le mainteneur du plugin les analyse avec `/mantis-update`. » and add that same line to `state.json`'s `notes` — if `state.json` does not exist yet, add it right after step 2 writes it. `null` or `0` → say nothing.
2. No `state.json` yet → write it with `stages` set to every stage of the level (table below) as `"pending"`, `round: 1`, `notes: []`, `finished: false`, `git_status_before` set to the output of `git -C "$REPO" status --porcelain -- . ':(exclude)osho-mantis'`, and `base_commit` set to `git -C "$REPO" rev-parse HEAD` (omit the key if the repo has no commit yet).
3. If the level includes reproduce and `docker info` fails → set reproduce to `"skipped"` and add the note « reproduce sauté : Docker indisponible ».
4. Shadow copy (used only by reproduce and patch): if `state.json` has no `shadow` key yet, `python3 "$R/guard.py" shadow-new "$AUDIT"` (a `mktemp -d` **outside `$REPO` and `$AUDIT`**, saved as `shadow`). Then wipe and recopy it: `python3 "$R/guard.py" shadow-reset "$AUDIT"`. It copies from tracked files only, no symlinks — never an incremental rsync, so nothing a previous patch wrote into the shadow (new files included) survives, and a hostile repo's `.venv`/`node_modules` symlinks are never copied into a sandbox a patch agent can write through, nor land under the audit folder where the symlink guard above would (wrongly) block every resume. Here, and at every other "wipe and recopy the shadow (2.4)" call site, that is the command, and `$SHADOW` is the path it prints, never a path remembered from earlier: stage agents can rewrite `state.json`'s `shadow`, and `$TMPDIR` can differ across sessions, so when the guard in `guard.py` refuses the saved path, the command leaves it untouched, makes a fresh one in its place and adds the note « shadow recréé : ancien chemin refusé ou absent ». A path the guard refuses is never deleted or touched. A non-zero exit of `shadow-new` or `shadow-reset` (git or rsync failed, or `state.json` unreadable): here in Prepare, tell the user the error and stop; at a stage call site, it is a failure of that stage: follow Failure (3).

5. **Dependency volume** (Sharp+, reproduce not `skipped`, no `deps_volume` in `state.json` yet), automatic, no question: from `inventory.json` `manifests`, pick the stacks present (Maven `pom.xml`, Gradle `build.gradle*`, npm `package.json`, pip `requirements.txt`/`pyproject.toml`). Say in the terminal and add the note « remplissage du volume de dépendances, avec réseau ». `V=mantis-<repo name>-deps`; `docker volume create "$V"`; then one container **with network**, repo read-only, per stack and manifest directory, e.g. `docker run --rm --name mantis-<audit name>-deps -v "$SHADOW":/src:ro -v "$V":/deps maven:3-eclipse-temurin-21 sh -c 'cp -r /src/<dir> /tmp/b && cd /tmp/b && mvn -q -Dmaven.repo.local=/deps/m2 dependency:go-offline'`, `npm ci --ignore-scripts` into `/deps/npm/<dir>/node_modules`, `pip download -d /deps/pip/<dir> -r …`. A failure is a note, not a stop (reproduction then runs without it). Write `deps_volume: "$V"` into `state.json`. The volume is kept after the audit (reused by a re-audit); the report says how to remove it.

## 3. Stages

Run the stages in this order, skipping those that are not in the level or are already `done`. Before each stage, run the checkpoint (below), then set the stage to `"running"` and run `python3 "$R/guard.py" resume "$AUDIT"`. **Findings guard**: before dedupe, review, critic, reproduce, patch and calibrate, `python3 "$R/guard.py" backup "$AUDIT" <stage>`; after every batch of these stages returns, `python3 "$R/guard.py" check "$AUDIT"`, and if it prints lines, `python3 "$R/guard.py" restore "$AUDIT"` then rerun those findings in the next batch and add the note « <stage> : findings abîmés par un agent, restaurés : <files> ». Before dispatching each batch of agents (one message of parallel Agent calls; a single agent is batch `1/1`; in Patch Sharp+ (references/patch-reattack.md), one finding is one batch), write `current: {"stage": "<stage>", "batch": "<k>/<n>", "workers": <agents in this batch>, "model": "<model>"}` into `state.json`; after each batch returns, run the checkpoint. After the stage, drop `current`, run the check, then set the stage to `"done"`. Before the reproduce stage specifically, wipe and recopy the shadow (2.4) first (`python3 "$R/guard.py" shadow-reset "$AUDIT"`) — a clean copy, since a prior patch run may have left its diff applied (matters most for Overkill rounds 2–3, where reproduce reruns after a patch round).

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
| patch | mantis-patch | Light: sonnet · Sharp+: opus | all | Light: status `VALID`/`PROVISIONALLY_VALID`, split into `parallel` groups (the patch agent never applies or runs anything, so no shadow needed). Sharp+: viable findings, split by `repro_status`: `reproduced` ones go through patch + independent re-attack (see below, references/patch-reattack.md); the rest (not reproduced, or reproduce was skipped) get the same mitigation-proposal treatment as Light in groups of `parallel` (checkpoint before each group), each finding with its own shadow as in Patch + re-attack below (references/patch-reattack.md) | each one has `patch_status`; reproduced findings also have `reattack_status`, unless `patch_status` is `VERIFICATION_FAILED` from a failed `git apply` (re-attack step 5 was skipped) |
| calibrate | mantis-calibrate | sonnet | Sharp+ | non-rejected findings, split into `parallel` groups | each one has `mantis_risk_score` |
| reflect | mantis-reflect | sonnet | Savage, Overkill | whole workspace | agent replied |

- "whole repo" scope (history, structural-index, architecture, threat-model, plan, researcher) always means `<REPO>` **excluding the `osho-mantis/` folder** (previous audits and this campaign's own files, not target code); say so in the Scope line. For plan, `<out_of_scope>` always includes `osho-mantis/` in addition to whatever triage set.
- Dispatch parallel groups as several Agent calls in one message (`subagent_type: general-purpose`, with the model from the table).
- A finding is "rejected" if `status` is `FALSE_POSITIVE` or `DUPLICATE`, or if `production_viability` is `NON_VIABLE` or `SAMPLE_OR_TEST`. Rejected findings skip all later stages.
- **Fix scope:** findings printed by `python3 "$R/fixes.py" busy "$AUDIT"` (fix `running`, `ready` or `merged`) are out of scope of critic, reproduce, patch and calibrate, like rejected ones. Rerun it at the start of each of these stages and before each finding in Patch Sharp+ (references/patch-reattack.md); a stage's Check after uses the scope computed at that stage's start.
- Per-finding stages are resumable: on a rerun, only the findings in scope that still lack the checked field are processed.
- **Patch scope, later passes** (Sharp+): a finding whose `repro_status` became `reproduced` while its `patch_status` is `MITIGATION_PROPOSED` (round-1 proposal never re-attacked) goes through patch + re-attack (references/patch-reattack.md). Overkill rounds 2 and 3 also take every `VERIFICATION_FAILED` finding (move its `patch_diff`, `reattack_status` and `reattack_output` summary into a `previous_patches` list on the finding before the patch agent runs; the patch level line then adds: `A previous patch was bypassed (see previous_patches). Before writing the diff, list every sibling of the vulnerable primitive (other routes, loggers, callers, limiters) and fix them at the shared choke point.`) and every non-rejected `LOW` with `mantis_risk_score` ≥ 5.0 that has no `patch_status`.
- **API refusal** (an agent stops on a safety filter): note « <stage> : refus du filtre de l'API pour <ids> », leave those findings as they are (`statically_confirmed` stays), no automatic retry.
- **Overkill:** the plan stage gets one investigation per source file. After reflect, if `round` < 3, increment `round`, reset plan, researcher, dedupe, review, critic, reproduce, patch, calibrate and reflect to `"pending"`, and run them again (plan then replans from `learnings.jsonl`).
- **Failure** (an agent errors, hits the quota, or the check fails) → set the stage to `"failed"`, drop `current`, write `waiting.json` as `{"kind": "failed", "stage": "<stage>", "reason": "<why, 2 lines>", "since": "<date +%Y-%m-%dT%H:%M:%S>"}`, then wait for the user (below) (references/wait.md) with the options « relancer » and « arrêter ». Do not retry on your own.

### Checkpoint

Run before each stage, after each batch of agents returns, and in Patch Sharp+ (references/patch-reattack.md) between two findings. `python3 "$R/dashboard.py" pending "$AUDIT"` prints the unacknowledged commands, one JSON object per line (`{id, at, source, action, ...}`, `finding` = finding file stem); nothing printed → continue. Handle them in order; every command ends acknowledged:
- `false_positive`, `prioritize_repro`, `merge_fix`, `set_cost`, `recompute_cost` → `python3 "$R/dashboard.py" apply "$AUDIT" <id>` (validates, writes the finding or `force_repro` or merges the fix, and acks it itself).
- `fix` → `apply` (queues the fix and acks), then **Launch fixes** (below) (references/fixes.md).
- `end_fixes` → `python3 "$R/dashboard.py" ack "$AUDIT" <id> refused "le mode Corrections n'est pas actif"`.
- `pause` → set `paused: true` in `state.json`, `python3 "$R/dashboard.py" ack "$AUDIT" <id> applied`, then wait for the user (below) (references/wait.md) with `kind: "paused"`.
- `stop` → **Stop** (then `python3 "$R/guard.py" resume "$AUDIT"`): first `apply` every other pending `fix` (queued for the resume, not launched); running fix agents are not stopped (they finish in the background, 1 reconciles them on resume). Then set the `running` stage, if any, back to `"pending"`, drop `current` and `paused`, set `stopped: true`, `rm -f "$AUDIT/waiting.json"`, ack `applied`, ack every other pending command `refused` « audit arrêté » (a leftover `stop` would end the next resume), run Finish 1, 2 and 4 (skip those whose inputs do not exist yet; never 3, so no `finished`), tell the user in 2 lines that the audit is stopped and `/mantis-run` resumes from there, and end.
- `resume`, `retry`, `answer` outside a wait → `python3 "$R/dashboard.py" ack "$AUDIT" <id> refused "aucune attente en cours"`.

**Wait for the user (pause, failure, question)** → read `references/wait.md` when you reach this step (same directory as this file).

**From the terminal** (a request typed at any time in natural language) → read `references/wait.md` when it happens.

**Launch fixes** → read `references/fixes.md` when you reach this step (same directory as this file).

**Fix agent prompt** → read `references/fixes.md` when you reach this step (same directory as this file).

**Fix agent finished** (the notification that a background `Correctif …` agent finished, at any time in this session) → read `references/fixes.md` when it happens.

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

**Patch + re-attack for reproduced findings (Sharp+)** → read `references/patch-reattack.md` when you reach this step (same directory as this file).

## 4. Finish

1. Integrity: compare `git -C "$REPO" status --porcelain -- . ':(exclude)osho-mantis'` with `git_status_before`. If they differ, warn the user first, listing the files that changed, and do not discard anything.
2. If `state.json` has `shadow`, `python3 "$R/guard.py" shadow-drop "$AUDIT"` (deletes it and drops the key); then `python3 "$R/guard.py" shadow-drop "$AUDIT" "<path>"` for every path left in `shadows`. Exit 2 (the guard refused the path, nothing was deleted) → stop and tell the user.
3. Set `finished: true` in `state.json` and `finished_at` (`date +%Y-%m-%dT%H:%M:%S`) in `campaign.json`.
4. `python3 "$R/cost.py" "$AUDIT"` (estimated cost and active time from this session's transcripts, into `cost.json`; never fatal), then `python3 "$R/render.py" "$AUDIT"` (writes `README.md`, `patches/`, `dashboard.html` and `bilan.html`; no `open`: the live page is already open and shows « Audit terminé »).
5. Report, 5 lines max: counts by severity, the top Critical or High finding, the `bilan.html` path, the `dashboard.html` path (for later reading; its Bilan tab exports the light and full archives). If `fixes.json` has `n` > 0 entries with `"status": "merged"`, add « <n> correctifs sur `mantis/<audit name>` : `git merge mantis/<audit name>` ». The commit line of `versioned` audits comes at the end of §5 Corrections (Exit) (references/fixes.md), since it stops the server.
6. Enter 5 (Corrections) (references/fixes.md).

**5. Corrections** → read `references/fixes.md` when you reach this step (same directory as this file).
