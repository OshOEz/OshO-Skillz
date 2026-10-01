---
name: mantis-triage
description: Quick, low-cost security triage of a git repository before a Mantis audit. Inventories the code with a script, flags the riskiest areas, recommends an audit level (Light, Sharp, Savage, Overkill) with quota estimates per Claude subscription, and prepares the osho-mantis/audit-<date> folder. Use when the user asks to audit, scan or security-review a repo with Mantis, or says "mantis triage". Don't use to run the audit itself (that is mantis-run).
---

# mantis-triage

Visibility of the current directory's repo, computed when this skill loaded: !`bash "${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts/check-visibility.sh"`

Scripts: `T="${CLAUDE_PLUGIN_ROOT}/skills/mantis-triage/scripts"`.

## Steps

1. **Target.** The repo path the user named, else the current directory, as an absolute path `REPO`. If `git -C "$REPO" rev-parse HEAD` fails, stop and ask the user whether to `git init` and commit; the inventory reads `git ls-files`.
2. **Visibility.** If `REPO` is the current directory and the line above is exactly `local`, `private`, `public` or `unknown`, use it. Otherwise run `bash "$T/check-visibility.sh" "$REPO"`. Then:
   - `local` or `private` → `VERSIONING=versioned`, no question.
   - `public` → say: « ⚠️ Repo public : le dossier d'audit contiendra des vulnérabilités détaillées et des exploits, visibles de tous une fois poussés. » Then AskUserQuestion, header `Versionnement`, options `Non versionné (Recommandé)` / `Versionné quand même`.
   - `unknown` → AskUserQuestion, header `Versionnement`, question explaining that `gh` could not confirm whether the repo is public (gh absent, not logged in, or remote outside GitHub), options `Versionné` / `Non versionné`.
   - Non-versioned → resolve the exclude file with `p=$(git -C "$REPO" rev-parse --git-path info/exclude)`; in a worktree or submodule this is already absolute (a shared file outside `$REPO`), otherwise resolve it as `$REPO/$p`. `mkdir -p` its directory, add the line `osho-mantis/` unless already there, then `git -C "$REPO" check-ignore -q osho-mantis/`. If that fails (e.g. a `!osho-mantis/` negation in `.gitignore`), tell the user and stop — do not set `VERSIONING=ignored`. Otherwise `VERSIONING=ignored`.
3. **Audit folder.** Refuse to continue if `$REPO/osho-mantis` exists and is a symlink (`[ -L "$REPO/osho-mantis" ]`): tell the user the repo ships a symlinked `osho-mantis` and stop. Otherwise `mkdir -p "$REPO/osho-mantis"`, then `AUDIT="$REPO/osho-mantis/audit-$(date +%Y-%m-%d_%Hh%M)"` and `mkdir "$AUDIT" && mkdir "$AUDIT/workspace"` (no `-p`: the audit folder must be new; if it already exists, wait one minute or ask the user).
4. **Inventory (zero tokens).** `python3 "$T/inventory.py" "$REPO" "$AUDIT/inventory.json"`.
5. **Short Claude pass.** Dispatch one Agent (`subagent_type: general-purpose`, `model: sonnet`) with the prompt below (fill `<REPO>` and `<AUDIT>`), and wait for it.
6. **Volume question.** AskUserQuestion, header `Volume`, question `Quel niveau d'audit ?`, four options in this order. Label = level name, plus ` (Recommandé)` on `recommended` from `campaign.json`. Description = the line below + ` — ` + `levels.<level>.subtitle` from `inventory.json`:
   - `Light` : Statique : architecture, threat model, plan, recherche, review, diffs non vérifiés.
   - `Sharp` : + critic, reproduction Docker (High+), patchs vérifiés, calibrage.
   - `Savage` : + historique git, reproduction de tout le viable, chaînes d'exploits.
   - `Overkill` : + chaque fichier source, 2 tours de replanification.
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
