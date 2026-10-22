---
name: mantis-triage
description: Quick, low-cost security triage of a git repository before a Mantis audit. Inventories the code with a script, flags the riskiest areas, recommends an audit level (Light, Sharp, Savage, Overkill) with quota estimates per Claude subscription, and prepares the osho-mantis/audit-<date> folder. Use when the user asks to audit, scan or security-review a repo with Mantis, or says "mantis triage". Don't use to run the audit itself (that is mantis-run).
---

# mantis-triage

Visibility of the current directory's repo, computed when this skill loaded: !`bash "${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts/check-visibility.sh"`

Scripts: `T="${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts"`, `R="${CLAUDE_PLUGIN_ROOT}/skills/mantis-run/scripts"`.

## Steps

1. **Target.** The repo path the user named, else the current directory, as `REPO=$(git -C "<path>" rev-parse --show-toplevel)` (the canonical toplevel, so triage and `mantis-run` agree on `REPO` from a subdirectory or a symlinked path). If that fails, or if `git -C "$REPO" rev-parse HEAD` fails (repo exists but has no commit yet), stop and ask the user whether to `git init` and commit; the inventory reads `git ls-files`.
2. **Visibility.** If `REPO` is the current directory and the line above is exactly `local`, `private`, `public` or `unknown`, use it. Otherwise run `bash "$T/check-visibility.sh" "$REPO"`. Then:
   - `local` or `private` → `VERSIONING=versioned`, no question.
   - `public` → say: « ⚠️ Repo public : le dossier d'audit contiendra des vulnérabilités détaillées et des exploits, visibles de tous une fois poussés. » Then AskUserQuestion, header `Versionnement`, options `Non versionné (Recommandé)` / `Versionné quand même`.
   - `unknown` → AskUserQuestion, header `Versionnement`, question explaining that `gh` could not confirm whether the repo is public (gh absent, not logged in, or remote outside GitHub), options `Versionné` / `Non versionné`.
   - Non-versioned → resolve the exclude file with `p=$(git -C "$REPO" rev-parse --git-path info/exclude)`; in a worktree or submodule this is already absolute (a shared file outside `$REPO`), otherwise resolve it as `$REPO/$p`. `mkdir -p` its directory, add the line `osho-mantis/` unless already there, then `git -C "$REPO" check-ignore -q osho-mantis/`. If that fails (e.g. a `!osho-mantis/` negation in `.gitignore`), tell the user and stop — do not set `VERSIONING=ignored`. Otherwise `VERSIONING=ignored`.
3. **Audit folder.** Run `if [ -L "$REPO/osho-mantis" ]; then echo SYMLINK; fi` (exits 0 either way). If it printed `SYMLINK`, tell the user the repo ships a symlinked `osho-mantis` and stop. Otherwise `mkdir -p "$REPO/osho-mantis"`, then `AUDIT="$REPO/osho-mantis/audit-$(date +%Y-%m-%d_%Hh%M)"` and `mkdir "$AUDIT" && mkdir "$AUDIT/workspace"` (no `-p`: the audit folder must be new; if it already exists, wait one minute or ask the user). Then start the live dashboard: `python3 "$R/dashboard.py" serve "$AUDIT"` prints one JSON line `{"url", "reused"}`; `open "<url>"` and also print the URL in the terminal as a fallback.
4. **Inventory (zero tokens).** `python3 "$T/inventory.py" "$REPO" "$AUDIT/inventory.json"`.
5. **Short Claude pass.** Dispatch one Agent (`subagent_type: general-purpose`, `model: sonnet`) with the prompt below (fill `<REPO>` and `<AUDIT>`). Do not proceed to step 6 on dispatch alone: wait for the agent's completion notification, then check `<AUDIT>/campaign.json` exists and has a `recommended` key. If the agent failed, or `campaign.json` is missing or has no `recommended` key, fall back to `recommended` from `inventory.json` and tell the user the agent's recommendation was unavailable so this is the inventory-based fallback.
6. **Volume question**, answerable from the terminal or the dashboard (no AskUserQuestion: it would block the page's answer). Four options in this order. Value = level name. Label = level name, plus ` (Recommandé)` on the `recommended` value resolved in step 5 (from `campaign.json`, or the `inventory.json` fallback). Description = the line below + ` : ` + `levels.<level>.subtitle` from `inventory.json`:
   - `Light` : Statique : architecture, threat model, plan, recherche, review, diffs non vérifiés.
   - `Sharp` : + critic, reproduction Docker (High+), patchs vérifiés, calibrage.
   - `Savage` : + historique git, reproduction de tout le viable, chaînes d'exploits.
   - `Overkill` : + chaque fichier source, 2 tours de replanification.

   1. Write `$AUDIT/waiting.json`: `{"kind": "question", "question": "volume", "text": "Quel niveau d'audit ?", "options": [{"value", "label", "description"} × 4, same order], "since": "<date +%Y-%m-%dT%H:%M:%S>"}`.
   2. In the terminal, plain text: `Quel niveau d'audit ?`, then the four options numbered 1 to 4 as `<n>. <label> : <description>`, then « Réponds ici (nom ou numéro) ou sur le dashboard. »
   3. Start the Monitor tool (`timeout_ms` 1800000) with `until [ -n "$(python3 "$R/dashboard.py" pending "$AUDIT")" ]; do sleep 2; done`, then end your turn.
   4. **On wake-up** (Monitor event or typed reply): a Monitor event when `$AUDIT/waiting.json` no longer exists is stale: ignore it and do not re-arm Monitor. Otherwise first run `python3 "$R/dashboard.py" pending "$AUDIT"` (one JSON command per line). The first `answer` with `question` `volume` wins: its `value` is the level. Ack every other pending command `refused` « répondre d'abord à la question Volume » (`python3 "$R/dashboard.py" ack "$AUDIT" <id> refused "<reason>"`). No answer and no typed reply → back to 3.
   5. No page answer pending and the user typed a reply → accept it only if it names a level (Light, Sharp, Savage, Overkill, case ignored) or is its number 1 to 4; otherwise repeat the question (back to 2). Record an accepted reply first: `python3 "$R/dashboard.py" command "$AUDIT" '{"action": "answer", "question": "volume", "value": "<Level>"}'` (`<Level>` capitalised as above) prints the stored command; use its `id`.
   6. Once a level is chosen: `python3 "$R/dashboard.py" ack "$AUDIT" <id> applied`, then `rm "$AUDIT/waiting.json"`. If Monitor is still running (the level came from a typed reply), stop it with TaskStop on its task id.
   7. Monitor expired with no command → if `$AUDIT/waiting.json` no longer exists, ignore this event and do not re-arm Monitor. Otherwise if `python3 "$R/dashboard.py" alive "$AUDIT"` exits 0 (server running), start Monitor again and end your turn; otherwise say « Dashboard arrêté : réponds ici. » and end your turn without Monitor (a typed reply still goes through 5).
7. **campaign.json.** Merge into the file the agent wrote: `level`, `hypotheses_max` (= `levels.<level>.hypotheses` in `inventory.json`) and `parallel` (= `levels.<level>.parallel`), `versioning`, `visibility`, `repo` (`REPO`), `started_at` (`date +%Y-%m-%dT%H:%M:%S`).
8. **Report**, 4 lines max: audit folder, top 3 risks from `triage.md`, chosen level, then « Lancer `/mantis-run "<AUDIT>"` ? » — name the folder explicitly, so mantis-run audits the one just created instead of auto-selecting among `$REPO/osho-mantis/audit-*`.

## Agent prompt

```
You are triaging the git repository at <REPO> before a security audit.
Read <AUDIT>/inventory.json, the repo README if any, and at most 20 key source files
(entry points and the files listed under "surface"). Modify nothing outside <AUDIT>.
Write two files:
1. <AUDIT>/triage.md, in French, 60 lines max:
   ## Stack
   ## Zones à risque   (top 5, each with file:line and one line on why)
   ## Hors périmètre   (generated, vendored, test-only code)
   ## Recommandation   (start from "recommended" in inventory.json; change it only with a one-line reason;
                        then a table of the 4 levels with their "subtitle")
2. <AUDIT>/campaign.json:
   {"repo": "<REPO>", "focus": [up to 10 short hypotheses in English for the Mantis planner, most likely first],
    "out_of_scope": [paths], "recommended": "<Light|Sharp|Savage|Overkill>"}
Reply in 3 lines: stack, top risk, recommended level.
```

## Notes

- Cost: one Sonnet subagent, about 2 to 5 % of a Max 5x window, 1 to 3 minutes.
- The subtitles are order-of-magnitude estimates; say so if the user asks.
