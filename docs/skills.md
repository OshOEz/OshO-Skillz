# Skills and hooks

## osho-core

| Component | Type | What it does |
|---|---|---|
| `repo-init-nobori` | Skill | After `git init`/`git clone` or on request: builds the code-review-graph, installs its pre-commit hook and the relay to the versioned `.githooks/pre-push`, then audits and aligns the repo on Nobori's Git & CI process (plan, then approval). Script: `skills/repo-init-nobori/scripts/repo-init.sh [path]` |
| `donnees-fictives` | Skill | Builds fully invented test data from confidential client documents, checks nothing leaks, then purges the copies. Tool: `uv run skills/donnees-fictives/scripts/donnees_fictives.py`, self-test: `python3 skills/donnees-fictives/scripts/test_donnees_fictives.py` |
| `audit-loop` | Skill | Audit → fix loop on an Escouade ticket in review, until it is production-ready, 3 rounds max: majors are sent back to the ticket's agent (`reject_ticket`), no PR or issue, findings kept in a local state file; the ticket is approved (`approve_ticket`) only on the user's yes and only at the audited commit; minor findings become one follow-up ticket created only on the user's yes. After round 3, the loop asks the user before going on. A pull request outside Escouade: use `/code-review` |
| `revue-artefact` | Skill | Plans, specs, end-of-work reports and questions as an artifact page: a plain-language summary, then the questions with Claude's recommendation pre-ticked; the user ticks and sends, Claude reads the answers back. Script: `skills/revue-artefact/scripts/remplir.sh contenu.json revue.html`, self-test: `bash skills/revue-artefact/scripts/test_remplir.sh` |
| `auditor` | Agent | Strict senior reviewer used by `audit-loop`; read-only (no Edit/Write tools, never writes code, no `gh`). Reads the ticket's branch in git and returns its findings in a block in its reply, written nowhere else |
| `superpowers-offer.sh prompt` | UserPromptSubmit hook | On substantial dev work, asks once per session whether to use Superpowers, with a one-sentence reason |
| `superpowers-offer.sh session` | SessionStart hook | Strips Superpowers' always-on bootstrap (re-applied after plugin updates) |
| `crg.sh status` / `crg.sh update` | SessionStart / PostToolUse hooks | Shows and incrementally updates the code-review-graph, only in repos where it was built |
| `revue-artefact.sh` | PostToolUse hook (Skill) | When a Superpowers skill that ends in a review or a decision starts, reminds Claude to present specs, plans and end-of-work reports as a page with `revue-artefact` |

## osho-mantis

Installé par le bootstrap (`osho-mantis@osho-skillz`). Lance les skills [google/mantis](https://github.com/google/mantis) (référencés dans `~/.local/share/mantis`) avec l'abonnement Claude Code. Mantis y est figé sur le commit de `mantis.lock`, pris sur le fork `OshOEz/mantis`.

| Component | Type | What it does |
|---|---|---|
| `mantis-triage` | Skill | Triage court : inventaire, zones à risque, niveau recommandé (Light, Sharp, Savage, Overkill) avec estimation de quota, dossier `osho-mantis/audit-<date>_<heure>/` |
| `mantis-run` | Skill | Campagne au niveau choisi, un sous-agent par étape Mantis, reprise après coupure, rapport `README.md`, `patches/`, `dashboard.html` |
| `mantis-update` | Skill | Pour le mainteneur, dans un clone d'OshO-Skillz : analyse par un sous-agent les commits de google/mantis depuis la version figée (utile, ce qui casse `mantis-run`, suspect), recommande prendre, attendre ou ne pas prendre sur une page de revue ; sur « prendre », synchronise le fork, déplace `mantis.lock` et ouvre une PR sans la fusionner |
| `check-visibility.sh` | Script | `local` / `private` / `public` / `unknown` via `gh` ; self-test : `bash skills/mantis-triage/scripts/test_check_visibility.sh` |
| `inventory.py` | Script | Inventaire zéro token et estimations ; self-test : `python3 skills/mantis-triage/scripts/test_inventory.py` |
| `render.py` | Script | Findings → README, patchs, dashboard, bilan ; self-test : `python3 skills/mantis-run/scripts/test_render.py` |
| `bilan.py` | Script | Bilan HTML autonome (synthèse pour les développeurs, aussi onglet Bilan) ; self-test : `python3 skills/mantis-run/scripts/test_bilan.py` |
| `export.py` | Script | Exports léger (bilan + dashboard) et complet (zip brut de l'audit, sans fichiers de session), secrets à révoquer listés ; self-test : `python3 skills/mantis-run/scripts/test_export.py` |
| `cost.py` | Script | Coût estimé (tarif public de l'API) et temps actif depuis les transcripts Claude Code → `cost.json` ; self-test : `python3 skills/mantis-run/scripts/test_cost.py` |
| `feed.py` | Script | Fil de Claude en lecture seule pour le dashboard (texte des messages, lancement et retour des agents) ; self-test : `python3 skills/mantis-run/scripts/test_feed.py` |
| `guard.py` | Script | Sauvegarde, contrôle et restauration des findings, `RESUME.md` après une coupure, garde du dossier de travail (`shadow-new`, `shadow-reset`, `shadow-drop`) ; self-test : `python3 skills/mantis-run/scripts/test_guard.py` |
| `mantis_source.py` | Script | Copie de Mantis figée sur le commit de `mantis.lock` (`ensure`), commits de retard sur google/mantis (`behind`), skills changés et contrat des étapes (`diff`) ; self-test : `python3 skills/mantis-run/scripts/test_mantis_source.py` |
| `mantis.lock` | Fichier | Commit accepté de Mantis, pris sur le fork `OshOEz/mantis` ; seul `/mantis-update` le change |

## Adding a skill

1. Create `plugins/<plugin>/skills/<skill-name>/SKILL.md` with `name` and `description` frontmatter ([Agent Skills format](https://code.claude.com/docs/en/skills)).
2. Put helper scripts in `plugins/<plugin>/skills/<skill-name>/scripts/`.
3. Bump `version` in `plugins/<plugin>/.claude-plugin/plugin.json`.
4. Add a row to this file.
