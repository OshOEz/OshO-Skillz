# osho-mantis lot 3 : bilan, exports, coût, vue Cycle, pilotage sans console, robustesse — plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bilan HTML (onglet + fichier), exports léger/complet, coût et durées auto, vue Cycle, pilotage sans console, robustesse de mantis-run.

**Architecture:** Nouveaux scripts stdlib à côté de `render.py` (`cost.py`, `export.py`, `bilan.py`, `guard.py`), appelés par `render.py` et par le serveur `dashboard.py` (routes `/bilan`, `/export`, commandes serveur). `dashboard.html` gagne des onglets et la vue Cycle. Les SKILL.md portent le reste.

**Tech Stack:** Python 3 stdlib, HTML/CSS/JS sans build ; auto-tests `python3 test_<x>.py` (fonctions `test_*` + appel en bas, `print("OK")`).

**Spec:** `docs/superpowers/specs/2026-10-30-mantis-bilan-export-design.md`

## Global Constraints

- Dossier de scripts : `plugins/osho-mantis/skills/mantis-run/scripts/` (noté `S/`).
- Textes visibles en français, accents corrects, sans tiret cadratin.
- Aucune dépendance ; aucun code du projet audité exécuté sur l'hôte.
- Tout texte issu d'un finding ou d'une note passe par `html.escape` (bilan) ou `textContent` (page).
- Cas d'essai en lecture seule : copier `…/Ezymob-Global/osho-mantis/audit-2026-10-29_12h07` dans `mktemp -d` avant tout rendu ou export.
- Exports bruts (décision 4) : aucun contenu modifié ; exclus : `server.json`, `server.log`, `waiting.json`, `commands.jsonl`, `commands-done.jsonl`, `workspace/backups/`, `*.tmp`, liens symboliques.
- Prix (par Mtok, entrée / sortie) : `claude-opus-5-5` 4 / 20, `claude-opus-4-8` 5 / 25, `claude-sonnet-5-5` 2 / 10, `claude-haiku-5-5` 0,10 / 0,50 ; cache lu 0,1×, écrit 5 min 1,25×, 1 h 2×. Temps actif : écarts < 120 s de la session principale.
- Version du plugin : 0.4.0 (`plugin.json`), ligne dans `docs/skills.md`.
- Commits sur `feat/mantis-dashboard-bilan` ; jamais de push ni de merge.

## Review Focus

1. Audit sans transcript trouvé (autre machine, `CLAUDE_CONFIG_DIR` vide) : coût « inconnu », pas d'erreur ; test dans Task 1.
2. Audit en cours (pas de `finished_at`) : bilan provisoire et coût jusqu'à maintenant ; tests Tasks 1 et 3.
3. Lien symbolique ou fichier énorme sous `workspace/` à l'export : symlink jamais suivi ; test Task 2.
4. Finding illisible (0 octet, JSON tronqué) au moment du rendu ou de l'export : ignoré par le bilan, exporté tel quel ; test Task 3.
5. `GET /export` sans clé ou avec une autre `Origin` : 403 ; test Task 4.

---

## Lot 1 : bilan, exports, coût

### Task 1: `cost.py`

**Files:** Create `S/cost.py`, `S/test_cost.py`

**Interfaces:**
- Produces: `PRICES: dict[str, tuple[float, float]]` ; `find_sessions(audit_dir: Path, projects: Path, since: float) -> list[Path]` (jsonl principaux qui contiennent `str(audit_dir)`, mtime ≥ since) ; `compute(audit_dir: Path, projects: Path | None = None, now: float | None = None, match: str | None = None) -> dict` (`match` : chemin cherché dans les transcripts, défaut `str(audit_dir)` ; option CLI `--match` pour une copie) → `{"usd": float|None, "by_model": {model: {"in","out","cache_read","cache_write_5m","cache_write_1h","usd"}}, "unknown_models": [..], "active_s": int, "wall_s": int|None, "sessions": int, "computed_at": iso}` ; `load(audit_dir) -> dict` (lit `cost.json`, `{}` sinon) ; `save_auto(audit_dir, auto)` ; `set_manual(audit_dir, usd: float|None, note: str|None)` ; `summary(audit_dir) -> {"usd", "source": "manuel"|"auto"|None, "active_s", "wall_s", "note"}`. CLI : `python3 cost.py <AUDIT>` écrit `cost.json.auto` et affiche le résumé.
- `projects` par défaut : `$CLAUDE_CONFIG_DIR/projects` ou `~/.claude/projects`. Fenêtre : mtime d'`inventory.json` (sinon du dossier) → `campaign.finished_at` (sinon now). `wall_s` = `started_at`→`finished_at` (None si absent).

- [ ] Step 1: tests — `test_doublons_message_id` (deux lignes même `message.id` comptées une fois), `test_fenetre` (message hors fenêtre ignoré), `test_sous_agents` (`<session>/subagents/*.jsonl` comptés), `test_modele_inconnu` (jetons comptés, `usd` du modèle None, listé dans `unknown_models`), `test_temps_actif` (messages à t, t+60, t+100, t+400 → 100 s), `test_sans_transcript` (`usd` None, `sessions` 0), `test_manuel_prioritaire` (`set_manual(…, 12.5)` → `summary()["source"] == "manuel"`, `set_manual(None)` → retour à auto), `test_prix` (1 M jetons de sortie opus-5-5 → 20,0 $ ; 1 M cache écrit 1 h sonnet → 4,0 $).
- [ ] Step 2: `python3 S/test_cost.py` échoue (module absent).
- [ ] Step 3: implémenter.
- [ ] Step 4: `python3 S/test_cost.py` → `OK`. Puis `python3 S/cost.py <copie> --match <chemin d'origine>` → ≈ 300 $ et 2 h 46 actives.
- [ ] Step 5: commit `feat(osho-mantis): cost.py, coût estimé et temps actif depuis les transcripts`.

### Task 2: `export.py`

**Files:** Create `S/export.py`, `S/test_export.py`

**Interfaces:**
- Consumes: `render.load_json`, `render.load_findings`, `render.bucket`.
- Produces: `EXCLUDE_NAMES = {"server.json","server.log","waiting.json","commands.jsonl","commands-done.jsonl"}` ; `SECRET_PATTERNS: list[tuple[str, re.Pattern]]` (type lisible, motif) ; `scan_secrets(audit_dir) -> list[{"file": rel, "kind": str, "finding": stem|None}]` (fichiers texte < 5 Mo, hors `dashboard.html`/`README.md`/`bilan.html` qui recopient les findings) ; `patch_files(diff: str) -> dict[path, list[(start, end)]]` (plages `+++ b/` / `@@ -a,b`) ; `conflicts(audit_dir) -> list[{"a","b","file","kind": "chevauchement"|"même fichier"}]` (patches/*.diff, plus les notes contenant « conflit ») ; `dev_readme(audit_dir, secrets, conflicts) -> str` (Markdown, §2.4 + avertissement) ; `files_full(audit_dir) -> list[Path]` (os.walk sans suivre les liens, exclusions, chaque chemin `resolve()` sous audit_dir) ; `build(kind: "light"|"full", audit_dir, out: Path) -> dict` (manifeste). Light = `bilan.html` + `dashboard.html` (régénérés par `render.render` sur place si absents, sinon tels quels) + `LISEZMOI-DEV.md`. CLI : `python3 export.py light|full <AUDIT> <sortie.zip>`.
- Avertissement (texte exact, en tête de `LISEZMOI-DEV.md`) : « ⚠️ Cette archive contient le détail d'exploits et des secrets en clair. Transmettez-la uniquement par un canal privé. » suivi de « Secrets à révoquer : » et d'une ligne par secret (finding ou fichier, type), ou « aucun secret repéré par motifs (vérification non exhaustive) ».

- [ ] Step 1: tests — `test_exclusions` (zip complet sans `server.json`, `commands.jsonl`, `commands-done.jsonl`, `waiting.json`, `server.log`, `workspace/backups/x`, `a.tmp`), `test_symlink_ignore` (lien vers `/etc` absent du zip), `test_contenu_brut` (octets identiques à la source pour un finding contenant `AIza` + 35 car.), `test_secrets_listes` (finding et patch avec clé Google et `AKIA…` → 2 entrées rattachées au stem, valeur absente de `MANIFESTE.json`), `test_conflits` (deux diffs même fichier, plages 10-20 et 15-25 → chevauchement ; 10-12 et 40-42 → même fichier), `test_leger` (zip = {`bilan.html`,`dashboard.html`,`LISEZMOI-DEV.md`}), `test_lisezmoi` (contient l'avertissement exact, `git apply --check`, `base_commit`).
- [ ] Step 2: échoue.
- [ ] Step 3: implémenter (zip via `zipfile.ZIP_DEFLATED`, écrit dans `out`).
- [ ] Step 4: `python3 S/test_export.py` → `OK`.
- [ ] Step 5: commit `feat(osho-mantis): export.py, exports léger et complet`.

### Task 3: `bilan.py` et `render.py`

**Files:** Create `S/bilan.py`, `S/test_bilan.py` ; Modify `S/render.py` (`render()` écrit `bilan.html`, calcule `cost.json` auto si possible, sans faire échouer le rendu), `S/test_render.py` (bilan.html écrit).

**Interfaces:**
- Consumes: `snapshot.build_snapshot`, `cost.summary`, `export.conflicts`, `export.scan_secrets`.
- Produces: `bilan.build(audit_dir: Path, snap: dict | None = None, live: bool = False) -> str` (page complète). `fmt_s(seconds) -> "2 h 46 min"`. `notes_for(stem, notes) -> list[str]` (note qui contient le stem ou ses 8 premiers caractères).
- Sections, dans l'ordre et avec ces `id` : `ouverture`, `sommaire`, `depot`, `bref`, `echelles`, `constats`, `dev`, `deroule`, `verification`, `lexique`. Verdict (texte exact) : « N failles critiques ou hautes restent ouvertes : à corriger avant d'exposer l'application. » (N = CRITICAL/HIGH non écartés sans `VERIFIED_SECURE`) ou « Aucune faille critique ou haute ouverte. ». Coût : « ≈ 301 $ (équivalent API, estimation au tarif public, pas une facture) ». Mode live : bandeau « Audit en cours, tour N : bilan provisoire ». Liens constat : `dashboard.html#<_file>`. Style : jetons Horizon de `dashboard.html` (clair/sombre via `prefers-color-scheme`), pas de JS.

- [ ] Step 1: tests — `test_sections` (les 10 `id`), `test_verdict_ouvert` / `test_verdict_ferme`, `test_xss` (titre `<img onerror>` et note `</style>` échappés), `test_notes_rattachees`, `test_pas_de_plafond` (ni « plafond » ni « note d'ensemble »), `test_live` (bandeau provisoire), `test_aucun_finding`, `test_finding_illisible` (fichier 0 octet ignoré), `test_avertissement_secrets` (secret repéré → section `dev` le liste).
- [ ] Step 2: échoue.
- [ ] Step 3: implémenter ; dans `render()`, `bilan.html` écrit après `dashboard.html`, `cost.compute` dans un `try` qui note l'erreur sans échouer.
- [ ] Step 4: `python3 S/test_bilan.py && python3 S/test_render.py` → `OK`.
- [ ] Step 5: commit `feat(osho-mantis): bilan.html, synthèse de l'audit`.

### Task 4: serveur et page (onglet Bilan, exports, coût)

**Files:** Modify `S/dashboard.py`, `S/commands.py`, `S/snapshot.py` (meta `cost`), `S/dashboard.html`, `S/test_dashboard.py`, `S/test_commands.py`.

**Interfaces:**
- `GET /bilan` → `bilan.build(audit, snap, live=not finished)` (`text/html`, en-tête `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`). `GET /export?kind=light|full` → zip (`Content-Disposition: attachment; filename="mantis-<repo>-<audit>-<léger|complet>.zip"`), 400 si kind inconnu ; clé exigée, `Origin` si présent doit être le serveur. Commandes serveur (sans session, comme `merge_fix`) : `set_cost {usd: nombre ≥ 0 | null, note?: str ≤ 200}` → `cost.set_manual`, ack `applied` ; `recompute_cost` → `cost.compute` + `save_auto`.
- `snapshot.meta["cost"] = cost.summary(audit_dir)`.
- Page : onglets « Suivi » / « Bilan » (`localStorage`, `#bilan`) ; Bilan = iframe (`/bilan` en live, `bilan.html` en final), boutons d'export qui ouvrent une confirmation avec l'avertissement exact de Task 2 ; en final, « Exports disponibles avec le dashboard en direct ». Bannière : « ≈ X $ · 2 h 46 actives · 19 h 57 au total », clic → panneau détail + saisie (`set_cost`) + « Recalculer ».

- [ ] Step 1: tests — `test_export_sans_cle_403`, `test_export_full_zip` (zip lisible, sans `server.json`), `test_bilan_route`, `test_set_cost` (valide : 12.5, null ; refusé : -1, "abc", note > 200), `test_set_cost_sans_session` (accepté, pas de 409), `test_snapshot_cost`.
- [ ] Step 2: échoue.
- [ ] Step 3: implémenter.
- [ ] Step 4: tous les `test_*.py` → `OK` ; rendu + exports sur la copie du cas d'essai, ouverture de `bilan.html`.
- [ ] Step 5: commit `feat(osho-mantis): onglet Bilan, exports et coût dans le dashboard`.

**Point d'arrêt : compte rendu du lot 1, attendre.**

## Lot 2 : vue Cycle et pilotage sans console

### Task 5: tours dans le snapshot
**Files:** `S/snapshot.py`, `S/test_snapshot.py`.
- Produces: événements d'étape avec `round` (lu dans `state.round`) ; `snap["rounds"] = [{"round": n, "stages": [{key, code, name, status, duration_s}]}]` pour plan→reflect, et `snap["prep"]` (triage → threat-model). Tour sans `round` dans le journal : k-ième passage `running→done` de `plan` = tour k.
- Tests : `test_rounds_overkill` (3 tours, statut et durée par tour), `test_rounds_journal_ancien`, `test_rounds_light` (un seul tour).

### Task 6: vue Cycle
**Files:** `S/dashboard.html`, `S/test_dashboard.py` (présence des hooks).
- Remplace `.pv-rail`, Réseau et Matrice. Cartes absolues sur fond pointillé ; courbes `M x1 y1 C mx y1, mx y2, x2 y2` ; bouts ronds HTML ; flèche reflect(N) → plan(N+1) ; flèche entrante de l'étape `running` animée (`stroke-dasharray: 6 6`, `stroke-dashoffset` en boucle 1 s) seulement si `listening == "working"` et pas `prefers-reduced-motion` ; nouvelle rangée en fondu.

### Task 7: lancer et file sans session
**Files:** `S/commands.py`, `S/dashboard.py`, `S/snapshot.py`, `S/dashboard.html`, tests.
- `launch` (niveau choisi et `state.json` absent, ou `stopped`). Sans session : `launch`, `resume`, `retry`, `fix`, `false_positive`, `prioritize_repro` acceptées et en file ; `pause`, `stop`, `answer`, `end_fixes` → 409. Bandeau « Aucune session Claude n'écoute… » avec bouton « Copier » de `/mantis-run "<AUDIT>"`. Serveur : fin + page connectée → reste en vie (borne 24 h inchangée).
- Tests : `test_launch`, `test_file_sans_session`, `test_vie_serveur_page_connectee`.

### Task 8: SKILL.md (lancement, file)
- mantis-triage étape 6 : options « Lancer en <niveau> » + « Plus tard » ; réponse niveau → enchaîne mantis-run sur `AUDIT` ; « Plus tard » → fin, bouton `launch`.
- mantis-run §1 : traiter la file en attente avant de reprendre (`launch` = accord, `resume`/`retry` appliquées, `pause`/`stop` refusées « plus d'actualité »).

## Lot 3 : robustesse

### Task 9: `guard.py`
**Files:** Create `S/guard.py`, `S/test_guard.py`.
- `backup(audit, stage) -> Path` (`workspace/backups/<stage>-r<round>-<horodatage>/`, 3 derniers gardés) ; `check(audit) -> list[{"file","problem"}]` (illisible, vide, `id` perdu, champs perdus par rapport à la dernière sauvegarde) ; `restore(audit, files) -> list` ; `resume(audit)` écrit `RESUME.md`. CLI `backup|check|restore|resume`.
- Tests : fichier vidé restauré, JSON tronqué détecté, champ perdu détecté, rotation à 3, `RESUME.md` contient tour, étape interrompue, `force_repro`.

### Task 10: SKILL.md mantis-run (robustesse)
- `guard.py backup` avant dedupe, review, critic, reproduce, patch, calibrate ; `check` après chaque lot, `restore` + note ; `resume` à chaque passage `running` et à l'arrêt ; nettoyage des conteneurs `mantis-<audit>-*` à la reprise.
- `force_repro` + `repro_round` ; volume `mantis-<repo>-deps` rempli automatiquement (réseau signalé), monté `:ro` ; doublures d'amont (`--internal`) ; un shadow par finding (`shadows` + même garde) en lots de `parallel` ; `MITIGATION_PROPOSED` devenu reproduit → patch + re-attaque ; `VERIFICATION_FAILED` et LOW ≥ 5,0 → tour suivant avec `previous_patches` et voies voisines ; règles d'écriture (nouveau fichier, valider, renommer ; `workspace/tmp/`) dans le prompt d'étape.

### Task 11: docs et version
- `plugin.json` 0.4.0 (+ description), `marketplace.json` description, `docs/skills.md` (lignes `cost.py`, `export.py`, `bilan.py`, `guard.py`), README section osho-mantis (bilan, exports).
