---
name: repo-init
description: Activate OshO's per-repo tooling (code-review-graph graph + pre-commit hook, versioned pre-push hook) and align the repo on Nobori's Git & CI process (feat → dev → prod, local CI before push, GitHub Actions only to go to prod). Use right after `git init` or `git clone`, when opening a repo where `.code-review-graph/` is missing, when the user asks to set up, activate or initialize tools for a repo, or to audit or align a repo on the Git & CI process.
---

# repo-init

Global tools (rtk, plugins, MCP server) are already installed machine-wide. This skill turns on what must be activated per repository, then checks the repo against Nobori's Git & CI process.

## Part 1 · Tooling (script, safe to rerun)

1. Find the target repo: the path the user named, the repo just cloned, or the current directory.
2. If it is not a git repository, ask the user before running `git init`. Do not init silently.
3. Run the script from the repo root:

   ```bash
   bash "${CLAUDE_PLUGIN_ROOT}/skills/repo-init/scripts/repo-init.sh" <repo-path>
   ```

   It is idempotent: it builds the code-review-graph (or updates it), installs the code-review-graph pre-commit hook, and, if the repo has a versioned `.githooks/pre-push`, installs a relay hook that runs it. The relay works in every worktree and never uses `core.hooksPath` (which would disable the pre-commit).
4. Report in three lines: graph built/updated (files, nodes), pre-commit installed/already present, pre-push installed/none/not installed.

## Part 2 · Git & CI process (audit, then plan, then the user's approval)

Source: [Process Git & CI sur GitHub Nobori](https://app.notion.com/p/nobori/Process-Git-CI-sur-GitHub-Nobori-400eff7489dc806599cdcc8cf52f914e). The org has **2,000 GitHub Actions minutes a month for all repos**; once spent, nothing runs for anyone.

**Rules**

- Flow `feat/<topic>` → `dev` → `prod`. `prod` = production, `dev` = integration. No other environment branch (`staging`, `main`, `master`…).
- One CI command (`make ci`, or the stack's own runner, e.g. `npm run ci`) runs locally before each push, from `.githooks/pre-push`. If the full suite needs services (database, browser), the pre-push runs the fast subset (typecheck, lint, unit) and the full suite stays a manual step.
- GitHub Actions only on pull requests to `prod` (CI) and pushes to `prod` (deploy only, no tests). If the host deploys by itself on a push to `prod` (Render, Vercel…), no deploy workflow.
- `ubuntu-latest` only, one job per workflow, `timeout-minutes` everywhere, `concurrency` (`cancel-in-progress: true` for CI, `false` for deploy). No `schedule` without a validated reason.
- `dev` → `prod` merges as a merge commit, never squash or rebase.

**Steps**

1. **Read only.** Collect: `.github/workflows/*.yml` (`on:`, branches, `runs-on`, `timeout-minutes`, `concurrency`, jobs), the CI command, `.githooks/` and `.git/hooks/`, the rules in CLAUDE.md / AGENTS.md, and with `gh`: `gh repo view <owner/repo> --json visibility,mergeCommitAllowed,defaultBranchRef`, the remote branches, `gh api repos/<owner/repo>/actions/workflows` (a workflow may be `disabled_manually`), `gh run list -L 100 --json workflowName,event,headBranch`.
2. **Report** each gap: 🔴 burns minutes or may deploy by mistake (push trigger on `dev`/`feat`, macOS/Windows runner, job without timeout, tests rerun on deploy); 🟠 rule not tooled (no CI command, no pre-push, no rules for agents, missing `dev`/`prod`, merge commit disabled); ⚪ the rest. Each with its proof (file line or `gh` output).
3. **Plan, then wait for approval**: files created, GitHub settings changed, branches to delete. Ask before choosing the pre-push scope and the deploy target.
4. **Apply** on a `feat/ci-rules` branch from `dev`, PR to `dev`:
   - the CI command; `.githooks/pre-push` (`#!/bin/sh` then `exec <ci command>`), plus a one-line install target for collaborators without OshO (`make hooks` / `npm run hooks`) noted in the README; then rerun the script of Part 1;
   - remove workflows triggered by a push to another branch than `prod`; add `ci-promotion.yml` / `deploy.yml` only if the user wants them now;
   - a « Process Git & CI » section in CLAUDE.md (and AGENTS.md): never push to `prod`, CI command green before each push, never `--no-verify`, group commits, no PR to `prod` without an explicit request, merge commit to `prod`, no workflow added or changed without approval (2,000 minutes a month).
5. **GitHub settings** one by one, each after confirmation. Delete a remote branch only once the user has named it, and only after checking it holds no commit missing from `dev` (`git log --no-merges origin/dev..origin/<branch>` empty).
6. **Verify**: the CI command passes, the hook blocks a push when it fails. Never push to `prod`: a workflow pushed there would run.

## Notes

- A cold build takes about 40 s per 3,000 files. For a very large repo, tell the user the expected wait before starting.
- `.code-review-graph/` is ignored by the global gitignore; do not add it to the repo's `.gitignore`.
- Once the graph exists, the osho-core hooks keep it updated after every edit.
