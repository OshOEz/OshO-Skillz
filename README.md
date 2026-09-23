# OshO-Skillz

OshO's Claude Code setup: a plugin marketplace for our own skills and hooks, plus a bootstrap that installs the global toolchain on macOS.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/OshOEz/OshO-Skillz/main/bootstrap/install.sh | bash
```

Re-run it any time to update everything. Restart the terminal and Claude Code afterwards.

Plugins only (no toolchain):

```bash
claude plugin marketplace add OshOEz/OshO-Skillz
claude plugin install osho-core@osho-skillz
```

## What gets installed

| Tool | Source | Role |
|---|---|---|
| [rtk](https://github.com/rtk-ai/rtk) | Homebrew | Compresses Bash output before it reaches the context |
| [code-review-graph](https://github.com/tirth8205/code-review-graph) | `uv tool` + user MCP | Code knowledge graph for reviews and impact analysis |
| [ponytail](https://github.com/DietrichGebert/ponytail) | its marketplace | Writes only the code a task needs |
| [i-have-adhd](https://github.com/ayghri/i-have-adhd) | its marketplace + `OSHO.md` | Action-first answers, always on |
| [superpowers](https://github.com/obra/superpowers) | official marketplace | Planning/TDD/debugging skills, offered per session |
| `osho-core` | this repo | Our hooks and skills |

Third-party plugins are referenced, never copied: they auto-update from upstream.

## Layout

```
.claude-plugin/marketplace.json   plugin catalogue
plugins/<plugin>/                 one plugin: .claude-plugin/plugin.json, skills/, hooks/
bootstrap/install.sh              global setup entry point, runs steps/ in order
bootstrap/Brewfile                CLI tools
bootstrap/claude/OSHO.md          global instructions, imported from ~/.claude/CLAUDE.md
docs/                             skills catalogue and design decisions
```

See [docs/skills.md](docs/skills.md) and [docs/decisions.md](docs/decisions.md).
