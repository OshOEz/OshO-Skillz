# wait

Part of mantis-run. Paths: T, R, M as defined in SKILL.md.

### Wait for the user (pause, failure, question)

1. `waiting.json` is written: pause `{"kind": "paused", "since"}`, failure as above (SKILL.md), question as in mantis-triage step 6 (`since` = `date +%Y-%m-%dT%H:%M:%S`).
2. Say it in the terminal in plain text (no AskUserQuestion: it would block the page's answer): pause « En pause. Réponds « reprendre » ou « arrêter », ici ou sur le dashboard. »; failure: the stage, the 2-line reason, then « Réponds « relancer » ou « arrêter », ici ou sur le dashboard. »; question: its options, numbered.
3. Start the Monitor tool (`timeout_ms` 1800000) with `until [ -n "$(python3 "$R/dashboard.py" pending "$AUDIT")" ]; do sleep 2; done`, then end your turn.

On wake-up (Monitor event or typed reply): a Monitor event when `$AUDIT/waiting.json` no longer exists is stale: ignore it and do not re-arm Monitor. Otherwise run `pending` first and handle each command in order:
- `false_positive`, `prioritize_repro`, `fix`, `merge_fix` → `apply` as in the checkpoint (SKILL.md) (`fix` then Launch fixes (references/fixes.md)); the wait goes on.
- `resume` (paused) → drop `paused`. `retry` whose `stage` is the failed one → set it to `"pending"`. `answer` to the current question → take its `value`. Each lifts the wait: ack `applied`, then `rm "$AUDIT/waiting.json"`; if Monitor is still running (the wait was lifted by a typed reply), stop it with TaskStop on its task id; handle the remaining pending commands with the checkpoint rules (SKILL.md) (a duplicate `resume`, `retry` or `answer` is refused there); then continue where the audit was (the stage loop reruns a `pending` stage).
- `stop` → Stop, as in the checkpoint (SKILL.md) (TaskStop a still-running Monitor first).
- Any other command (`pause` while waiting, `retry` of another stage, `answer` to another question) → ack `refused` « ne correspond pas à l'attente en cours »; the wait goes on.
- No pending command and the user typed a reply → map it (« reprendre » → `{"action": "resume"}`, « relancer » → `{"action": "retry", "stage": "<stage>"}`, « arrêter » → `{"action": "stop"}`, a question answer as in mantis-triage step 6), record it with `python3 "$R/dashboard.py" command "$AUDIT" '<json>'` (exit 2 → tell the user the printed reason and stay waiting), then handle it like a page command. Unclear reply → ask again.
- Wait not lifted → back to 3.

Monitor expired with no command → if `$AUDIT/waiting.json` no longer exists, ignore this event and do not re-arm Monitor. Otherwise if `python3 "$R/dashboard.py" alive "$AUDIT"` exits 0 (server running), start Monitor again and end your turn; otherwise `rm "$AUDIT/waiting.json"`, say « Dashboard arrêté : relance `/mantis-run`. » and end.

### From the terminal

A request typed at any time in natural language (« mets en pause », « marque f-014 en faux positif », « reproduis f-020 en priorité », « corrige f-014 », « merge f-014 », « terminé », « arrête l'audit ») → build the matching command (`pause`, `false_positive`/`prioritize_repro`/`fix`/`merge_fix` with `finding` = the file stem under `workspace/findings/`, `end_fixes`, `stop`) and record it with `python3 "$R/dashboard.py" command "$AUDIT" '<json>'`. Exit 2 → tell the user the printed reason. Otherwise it shows on the page and is handled at the next checkpoint (SKILL.md).
