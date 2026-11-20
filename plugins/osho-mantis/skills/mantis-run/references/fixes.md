# fixes

Part of mantis-run. Paths: T, R, M as defined in SKILL.md.

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

## 5. Corrections

Listening mode after the audit, so Corriger keeps working. It reuses Wait for the user (3) (references/wait.md), with these differences:
1. Write `waiting.json` as `{"kind": "fixes", "since"}`. Say « Claude attend tes demandes de correction : clique Corriger sur le dashboard, ou tape « corrige <id> ». Tape « terminé » pour finir. »
2. Start Monitor (`timeout_ms` 1800000) with the same `pending` loop as Wait for the user step 3 (references/wait.md), then end your turn.
3. On wake-up (Monitor event or typed reply; a Monitor event when `$AUDIT/waiting.json` no longer exists is stale: ignore it, do not re-arm), run `pending` and handle each command in order:
   - `fix` → `apply`, then Launch fixes;
   - `merge_fix`, `false_positive`, `prioritize_repro` → `apply`;
   - `end_fixes` → ack `applied`, then Exit (5);
   - `pause`, `resume`, `retry`, `answer`, `stop` → ack `refused` « l'audit est terminé ».

   Then start Monitor again (TaskStop the still-running one first if the wake-up was a typed reply). A fix agent's notification goes to Fix agent finished (3) and never re-arms Monitor.
4. Monitor expired with no command (ignored if `$AUDIT/waiting.json` no longer exists): if `python3 "$R/fixes.py" active "$AUDIT"` prints a stem (fix queued or running), start Monitor again if `python3 "$R/dashboard.py" alive "$AUDIT"` exits 0, otherwise Exit; nothing active (30 min without a click) → Exit.
5. Exit: TaskStop a still-running Monitor, `rm -f "$AUDIT/waiting.json"`, say « Mode Corrections terminé. `/mantis-run <audit name>` le rouvre. », plus `git merge mantis/<audit name>` if `fixes.json` has `merged` entries. Fix agents still running keep going; the next `/mantis-run` reconciles them (1) (SKILL.md). If `versioning` is `versioned`, end with (stopping the server first deletes `server.json`, which holds the session key, so it is never committed): `python3 "$R/dashboard.py" stop "<AUDIT>" && git -C "<REPO>" add "osho-mantis/<audit name>" && git -C "<REPO>" commit -m "Audit de sécurité Mantis <date>"`. Never commit yourself. Then end.
6. From the terminal: « corrige f-014 » → `{"action": "fix", "finding": "<stem>"}`, « merge f-014 » → `{"action": "merge_fix", "finding": "<stem>"}`, « terminé » → `{"action": "end_fixes"}`; the typed id resolves to the file stem under `workspace/findings/`, as for `false_positive`. Record it with `python3 "$R/dashboard.py" command "$AUDIT" '<json>'` (exit 2 → tell the user the printed reason and keep listening), then handle it like a page command.
