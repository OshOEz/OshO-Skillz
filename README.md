<div align="center">

# OshO-Skillz

**One command to set up a Claude Code workspace on macOS: toolchain, plugins, skills and hooks.**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![Platform: macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)
![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin%20marketplace-d97757.svg)

</div>

---

## Quick start

```bash
curl -fsSL https://raw.githubusercontent.com/OshOEz/OshO-Skillz/main/bootstrap/install.sh | bash
```

Then restart your terminal and Claude Code. Re-run the same command any time to update everything: it is idempotent and takes about 15 s once installed.

Only want the plugin, without the toolchain?

```bash
claude plugin marketplace add OshOEz/OshO-Skillz
claude plugin install osho-core@osho-skillz
claude plugin install osho-mantis@osho-skillz
```

## What you get

| Tool | Installed via | What it does for you |
|---|---|---|
| [rtk](https://github.com/rtk-ai/rtk) | Homebrew | Compresses Bash output before it reaches the context |
| [code-review-graph](https://github.com/tirth8205/code-review-graph) | `uv tool` + user MCP | Code knowledge graph for reviews and impact analysis |
| [ponytail](https://github.com/DietrichGebert/ponytail) | its marketplace | Writes only the code a task needs |
| [i-have-adhd](https://github.com/ayghri/i-have-adhd) | its marketplace + `OSHO.md` | Action-first answers, always on |
| [superpowers](https://github.com/obra/superpowers) | official marketplace | Planning, TDD and debugging skills, offered per session |
| **osho-core** | this repo | Our own skills and hooks (below) |
| **osho-mantis** | this repo | Security audits with google/mantis on your subscription (below) |

Third-party plugins are **referenced, never copied**: they auto-update from upstream.

## How the installer works

`bootstrap/install.sh` runs each script in `bootstrap/steps/` in order. Run through `curl | bash`, it first clones this repo to `~/.local/share/osho-skillz`.

| Step | Does |
|---|---|
| `10-brew` | Installs Homebrew if missing, then the [Brewfile](bootstrap/Brewfile) (git, gh, jq, node, python, uv, rtk, poppler) |
| `20-path` | Puts Homebrew, its Python and `~/.local/bin` first on `PATH` (`~/.zprofile`) |
| `30-claude-code` | Installs the Claude Code CLI if missing |
| `40-rtk` | Registers rtk's global hook (`rtk init -g`) |
| `50-code-review-graph` | Installs/upgrades the CLI, adds the MCP server, refreshes its skills, ignores `.code-review-graph/` globally |
| `60-plugins` | Adds the marketplaces, installs the plugins, turns on auto-update |
| `70-claude-md` | Installs [`OSHO.md`](bootstrap/claude/OSHO.md) and imports it from `~/.claude/CLAUDE.md` |

## osho-core

| Component | Type | What it does |
|---|---|---|
| `repo-init` | Skill | After `git init` / `git clone`, or on request: builds the code-review-graph and installs its pre-commit hook |
| `donnees-fictives` | Skill | Builds invented test data from confidential client documents, with an automatic leak check and purge |
| `audit-loop` | Skill + agent | Say *"audit loop on PR #12"*: a senior auditor files issues for production-breaking problems only, a dev fixes them, repeat up to 3 rounds, then it proposes the merge |
| `tache` | Skill | Paste *"/tache <id>"* from a card of Horizon's Kanban: the session starts from the card's context and leaves a session log on it when done. Needs the `horizon-kanban` MCP server (Horizon → Kanban → Accès Claude Code) and Tailscale |
| `superpowers-offer` | Hooks | Removes Superpowers' always-on bootstrap; on substantial dev work, asks once per session whether to use it |
| `crg` | Hooks | Shows the graph status at session start and updates it after each edit, only in repos where it was built |

### Activate a repo

In Claude Code, just say *"init this repo"*, or run the script directly:

```bash
bash plugins/osho-core/skills/repo-init/scripts/repo-init.sh path/to/repo
```

```
graph: built
pre-commit: installed (.git/hooks/pre-commit)
```

From then on the graph stays up to date on every edit and every commit.

## osho-mantis

Security audits with [google/mantis](https://github.com/google/mantis), run on your Claude Code subscription (no Google or API key needed). Installed by the bootstrap; Mantis itself is cloned to `~/.local/share/mantis` on first use.

In a repo, say *"mantis triage"*: a short pass recommends a level with a quota estimate for your subscription. Then *"mantis run"* runs the audit. If it is interrupted (quota, error), say *"mantis run"* again to resume where it stopped.

| Level | Adds | Needs |
|---|---|---|
| **Light** | Static only: architecture, threat model, plan, research, review, unverified patch diffs | — |
| **Sharp** | + critic, reproduction of High/Critical findings, patches verified by re-attack, risk scoring | Docker |
| **Savage** | + git history, reproduction of every viable finding, exploit chains | Docker |
| **Overkill** | + one investigation per source file, up to 3 rounds of replanning | Docker |

Without Docker, reproduction is skipped and noted in the report. Reproduction runs in `docker run --network=none` on a temporary copy; your repo is never modified.

Each audit writes to `osho-mantis/audit-<date>/` in the target repo:

```
README.md         French report, one section per finding
dashboard.html    standalone dashboard (open it locally, works offline)
patches/<id>.diff one suggested fix per finding: git apply osho-mantis/audit-<date>/patches/<id>.diff
```

The folder is meant to be committed (the skill prints the command, never commits itself); on a public repo it asks first, since it contains exploits. Run it only on code you are allowed to test, and have a human check every finding before reporting it.

## Repository layout

```
.claude-plugin/marketplace.json   plugin catalogue
plugins/<plugin>/                 one plugin: .claude-plugin/plugin.json, skills/, agents/, hooks/
bootstrap/install.sh              global setup entry point, runs steps/ in order
bootstrap/steps/                  one script per install step
bootstrap/Brewfile                CLI tools
bootstrap/claude/OSHO.md          global instructions, imported from ~/.claude/CLAUDE.md
docs/                             skills catalogue and design decisions
```

## Learn more

- [docs/skills.md](docs/skills.md): every skill and hook, and how to add a new skill
- [docs/decisions.md](docs/decisions.md): why things are built the way they are

## License

[MIT](LICENSE)
