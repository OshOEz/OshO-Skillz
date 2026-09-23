---
name: repo-init
description: Activate OshO's per-repo tooling (code-review-graph graph + pre-commit hook) in a git repository. Use right after `git init` or `git clone`, when opening a repo where `.code-review-graph/` is missing, or when the user asks to set up, activate or initialize tools for a repo.
---

# repo-init

Global tools (rtk, plugins, MCP server) are already installed machine-wide. This skill turns on what must be activated per repository.

## Steps

1. Find the target repo: the path the user named, the repo just cloned, or the current directory.
2. If it is not a git repository, ask the user before running `git init`. Do not init silently.
3. Run the script from the repo root:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/skills/repo-init/scripts/repo-init.sh" <repo-path>
   ```

   It is idempotent: it builds the code-review-graph (or updates it if already built) and installs the code-review-graph pre-commit hook.
4. Report in two lines: graph built/updated (files, nodes) and pre-commit hook installed/already present.

## Notes

- A cold build takes about 40 s per 3,000 files. For a very large repo, tell the user the expected wait before starting.
- `.code-review-graph/` is ignored by the global gitignore; do not add it to the repo's `.gitignore`.
- Once the graph exists, the osho-core hooks keep it updated after every edit.
