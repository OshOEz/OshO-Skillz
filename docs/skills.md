# Skills and hooks

## osho-core

| Component | Type | What it does |
|---|---|---|
| `repo-init` | Skill | After `git init`/`git clone` or on request: builds the code-review-graph and installs its pre-commit hook. Script: `skills/repo-init/scripts/repo-init.sh [path]` |
| `superpowers-offer.sh prompt` | UserPromptSubmit hook | On substantial dev work, asks once per session whether to use Superpowers, with a one-sentence reason |
| `superpowers-offer.sh session` | SessionStart hook | Strips Superpowers' always-on bootstrap (re-applied after plugin updates) |
| `crg.sh status` / `crg.sh update` | SessionStart / PostToolUse hooks | Shows and incrementally updates the code-review-graph, only in repos where it was built |

## Adding a skill

1. Create `plugins/<plugin>/skills/<skill-name>/SKILL.md` with `name` and `description` frontmatter ([Agent Skills format](https://code.claude.com/docs/en/skills)).
2. Put helper scripts in `plugins/<plugin>/skills/<skill-name>/scripts/`.
3. Bump `version` in `plugins/<plugin>/.claude-plugin/plugin.json`.
4. Add a row to this file.
