# Skills and hooks

## osho-core

| Component | Type | What it does |
|---|---|---|
| `repo-init` | Skill | After `git init`/`git clone` or on request: builds the code-review-graph and installs its pre-commit hook. Script: `skills/repo-init/scripts/repo-init.sh [path]` |
| `donnees-fictives` | Skill | Builds fully invented test data from confidential client documents, checks nothing leaks, then purges the copies. Tool: `uv run skills/donnees-fictives/scripts/donnees_fictives.py`, self-test: `python3 skills/donnees-fictives/scripts/test_donnees_fictives.py` |
| `audit-loop` | Skill | Audit → fix loop on a PR until it is production-ready: the auditor opens GitHub issues for major problems only, a dev fixes them, the auditor verifies and closes; 3 rounds max, then proposes the merge |
| `auditor` | Agent | Strict senior reviewer used by `audit-loop`; no Edit/Write tools, writes only to GitHub |
| `superpowers-offer.sh prompt` | UserPromptSubmit hook | On substantial dev work, asks once per session whether to use Superpowers, with a one-sentence reason |
| `superpowers-offer.sh session` | SessionStart hook | Strips Superpowers' always-on bootstrap (re-applied after plugin updates) |
| `crg.sh status` / `crg.sh update` | SessionStart / PostToolUse hooks | Shows and incrementally updates the code-review-graph, only in repos where it was built |

## osho-mantis

Installé par le bootstrap (`osho-mantis@osho-skillz`). Lance les skills [google/mantis](https://github.com/google/mantis) (référencés dans `~/.local/share/mantis`) avec l'abonnement Claude Code.

| Component | Type | What it does |
|---|---|---|
| `mantis-triage` | Skill | Triage court : inventaire, zones à risque, niveau recommandé (Light, Sharp, Savage, Overkill) avec estimation de quota, dossier `osho-mantis/audit-<date>_<heure>/` |
| `mantis-run` | Skill | Campagne au niveau choisi, un sous-agent par étape Mantis, reprise après coupure, rapport `README.md`, `patches/`, `dashboard.html` |
| `check-visibility.sh` | Script | `local` / `private` / `public` / `unknown` via `gh` ; self-test : `bash skills/mantis-triage/scripts/test_check_visibility.sh` |
| `inventory.py` | Script | Inventaire zéro token et estimations ; self-test : `python3 skills/mantis-triage/scripts/test_inventory.py` |
| `render.py` | Script | Findings → README, patchs, dashboard ; self-test : `python3 skills/mantis-run/scripts/test_render.py` |

## Adding a skill

1. Create `plugins/<plugin>/skills/<skill-name>/SKILL.md` with `name` and `description` frontmatter ([Agent Skills format](https://code.claude.com/docs/en/skills)).
2. Put helper scripts in `plugins/<plugin>/skills/<skill-name>/scripts/`.
3. Bump `version` in `plugins/<plugin>/.claude-plugin/plugin.json`.
4. Add a row to this file.
