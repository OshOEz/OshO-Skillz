# osho-mantis : « Corriger » depuis le kanban (lot 2), plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** depuis une carte de la vue Avancement, « Corriger » lance un sous-agent qui commite un correctif sur sa propre branche, puis « Merger » le fusionne dans la branche de l'audit `mantis/<audit>`, sans jamais toucher au répertoire de travail ni à la branche courante de l'utilisateur.

**Architecture :**
- `fixes.py` (nouveau) porte tout l'état `fixes.json` et toutes les opérations git : branche de l'audit, branche et worktree du correctif, fin d'agent, merge en mémoire (`merge-tree --write-tree`, `commit-tree`, `update-ref` avec ancienne valeur), nettoyage. Il a une petite ligne de commande pour mantis-run.
- `commands.py` valide `fix`, `merge_fix`, `end_fixes` et applique `fix` (mise en file) et `merge_fix` (merge). Le serveur applique `merge_fix` dès le POST ; le terminal passe par `dashboard.py apply`.
- `snapshot.py` attache `_fix` à chaque finding, ajoute la colonne « Correctif proposé », redéfinit « Corrigées » (= fusionné) et l'état d'écoute `"fixes"` (mode Corrections).
- `dashboard.html` affiche les boutons et états sur les cartes, la branche de l'audit dans la bannière et le bouton Terminer ; `render.py` ajoute la section README « Corrections fusionnées ».
- Le SKILL.md de mantis-run lance les agents en arrière-plan, traite leur fin et reste à l'écoute après Finish.

**Tech Stack :** Python 3 stdlib (`subprocess`, `fcntl`, `tempfile`), git 2.38+ (`merge-tree --write-tree` ; 2.55 installé), HTML/CSS/JS sans build, Node pour les tests JS existants.

**Spec :** `docs/superpowers/specs/2026-10-22-mantis-fix-from-kanban-design.md` (contraignante). Contexte et conventions : `docs/superpowers/specs/2026-10-22-mantis-dashboard-live-design.md` et `docs/superpowers/plans/2026-10-22-mantis-dashboard-live.md`.

Dossier de travail : `plugins/osho-mantis/skills/mantis-run/scripts/` (noté `S/` ci-dessous).

## Global Constraints

- Aucune dépendance nouvelle : Python 3 stdlib ; HTML/CSS/JS sans build et sans ressource réseau (le fichier final marche hors ligne).
- Authentification du serveur inchangée : `127.0.0.1` seulement, clé de 32 octets, cookie `mantis_key_<port>` en `HttpOnly; SameSite=Strict`, contrôle `Host` et `Origin` sur le POST.
- Tout texte issu d'un finding est inséré avec `textContent` (ou `el()`), **jamais** `innerHTML` ; le JSON inclus passe par `render.safe_json()`.
- Une commande se valide en un seul endroit, `commands.validate()`, utilisé par le POST, `dashboard.py command` et `commands.apply`. Taille maximale : 1 Ko. Toute valeur `finding` contenant `/`, `\` ou `..` est refusée (`commands._bad`), et le fichier `workspace/findings/<stem>.json` doit exister.
- Chaînes visibles en français avec leurs accents ; **aucun tiret cadratin** (`—`) dans le gabarit, les textes du journal ni la nouvelle section du README.
- Toute écriture de `fixes.json` et des fichiers de `<AUDIT>/fixes/` passe par `commands.atomic_write` (tmp en `O_EXCL`, puis `os.replace`), sous le verrou `fixes.locked()`.
- Tout appel git passe par `fixes.git()` : variable d'environnement `GIT_CONFIG_NOSYSTEM=1` et options `-c core.hooksPath=/dev/null -c core.attributesFile=/dev/null`. Aucun `checkout`, `reset`, `stash`, `switch` ni `merge` porcelaine dans `<REPO>` ; seules les refs `refs/heads/mantis/<audit>` et `refs/heads/mantis/fix/<audit>/*` sont créées, déplacées ou supprimées.
- On refuse de créer un worktree si un `.gitattributes` de la révision de départ déclare `filter=`.
- Les noms de branche sont construits par le code : `mantis/<nom du dossier d'audit>` et `mantis/fix/<audit>/<stem court>`. Aucun nom ne vient de la page.
- Worktrees : `tempfile.mkdtemp(prefix="tmp.")` puis `<tmp>/wt`, hors du repo et du dossier d'audit. Rien n'est supprimé sans le garde-fou `fixes.safe_tmp()` (même règle que le shadow du lot 1).
- Le serveur n'exécute que `merge_fix`. Toute autre opération git reste chez mantis-run (via `fixes.py`).
- Messages exacts : commit du correctif `fix(mantis): <title> [<stem>]` ; commit de merge `Merge correctif Mantis : <title> [<stem>]`.
- Au plus 3 agents de correction en même temps (`fixes.FIX_LIMIT = 3`). Modèle sonnet, opus si le bucket est `CRITICAL`. Sous-agent nommé `Correctif <stem court>`. Mode Corrections : 30 min sans clic (`timeout_ms` 1800000).
- `prefers-reduced-motion: reduce` coupe toutes les animations (la règle globale existante couvre le nouvel indicateur de chargement).
- Tests : auto-tests exécutables (`python3 test_x.py` affiche `OK`), sans pytest ; chaque nouveau test est ajouté à la liste d'appels en bas du fichier. Les tests git créent un repo jetable avec `user.name` et `user.email` configurés localement.
- Version du plugin : `0.3.0`.

## Review Focus

1. **Titre de finding hostile** (guillemets, `$(id)`, retour à la ligne) repris dans le message de commit. Attendu : aucune interprétation shell, message sur une ligne. Le message est écrit dans `<AUDIT>/fixes/<stem>.msg` et l'agent commite avec `-F`. Test : `test_titre_hostile_message` (tâche 1).
2. **Double clic sur Merger, ou page et terminal en même temps.** Attendu : un seul commit de merge, le second appel est refusé. Test : `test_merge_double_seul_un` (tâche 2).
3. **Session plantée pendant une correction.** Attendu : à la reprise, `running` devient `ready` si le commit est là et le worktree propre, sinon `failed` « correction interrompue ». Test : `test_reconcile` (tâche 1).
4. **Branche de l'audit supprimée à la main entre `ready` et Merger.** Attendu : `failed` « branche de l'audit introuvable », la branche n'est pas recréée. Test : `test_merge_branche_supprimee` (tâche 2).
5. **Worktree effacé par le nettoyage de `$TMPDIR` de macOS** avant la fin de l'agent. Attendu : `finish` passe à `failed` sans exception et le worktree fantôme est élagué (`git worktree prune`). Test : `test_worktree_disparu` (tâche 1).

---

### Task 1 : `fixes.py`, état et cycle de vie d'une correction

**Files :**
- Create : `S/fixes.py`
- Create : `S/test_fixes.py`

**Interfaces :**
- Consomme : `commands.atomic_write(path, text, mode=0o644)`, `commands._bad(v)`, `render.load_json(path, default)`, `render.bucket(f)`.
- Produit (dans `S/fixes.py`) :
  - `FIX_LIMIT = 3`.
  - `git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess` : lance `git -C <cwd> -c core.hooksPath=/dev/null -c core.attributesFile=/dev/null <args>`, `text=True`, `capture_output=True`, env `GIT_CONFIG_NOSYSTEM=1` ajouté à l'environnement courant. `check=True` lève `RuntimeError(<première ligne de stderr>)`.
  - `locked(audit_dir: Path)` : gestionnaire de contexte, `fcntl.flock(LOCK_EX)` sur `<AUDIT>/fixes.lock` ouvert avec `O_CREAT | O_WRONLY | O_NOFOLLOW`. Il n'est pas réentrant : les fonctions appelées sous verrou utilisent `_save`.
  - `load(audit_dir) -> dict[str, dict]` : contenu de `fixes.json`, `{}` s'il est absent ou n'est pas un objet.
  - `_save(audit_dir, data: dict) -> None` : `atomic_write` de `fixes.json` (`indent=2`), à n'appeler que sous `locked`.
  - `update(audit_dir, stem, **fields) -> dict` : sous verrou, fusionne `fields` dans l'entrée, pose `at` (ISO, secondes), enregistre et renvoie l'entrée.
  - `repo_of(audit_dir) -> Path` : `campaign.json["repo"]`, accepté seulement s'il est égal (après `Path.resolve()`) à `git rev-parse --show-toplevel` lancé depuis le dossier d'audit ; sinon `ValueError("repo de l'audit introuvable")`.
  - `audit_branch(audit_dir) -> str` : `"mantis/" + audit_dir.name`.
  - `short(stem) -> str` : `re.sub(r"[^A-Za-z0-9_-]", "_", stem)[:8]`.
  - `fix_branch(audit_dir, stem) -> str` : `f"mantis/fix/{audit_dir.name}/{short(stem)}"` ; si une autre entrée de `load()` porte déjà ce nom, on utilise le stem assaini entier à la place de `short`.
  - `valid_stem(audit_dir, stem) -> bool` : `not commands._bad(stem)` et le fichier de finding existe.
  - `safe_tmp(path) -> bool` : vrai seulement si `path` est non vide, sans `..`, n'est pas un lien, est un dossier, a pour parent exact `Path(tempfile.gettempdir())` et un nom qui commence par `tmp.`. On l'appelle sur le **parent** du worktree (`<tmp>/wt`).
  - `ensure_audit_branch(audit_dir) -> str` : renvoie le sha de la tête de `mantis/<audit>`. Si la ref n'existe pas, il la crée avec `update-ref refs/heads/<branche> <base> ""` (ancienne valeur vide : création seulement). `<base>` est `state.json["base_commit"]` s'il fait 40 caractères hexadécimaux et que `cat-file -e <sha>^{commit}` réussit ; sinon `rev-parse HEAD`.
  - `has_filter(repo, rev) -> bool` : vrai si un fichier `.gitattributes` de `ls-tree -r --name-only <rev>` contient une ligne non commentée avec `filter=`.
  - `cleanup(audit_dir, stem) -> None` : si `safe_tmp(parent du worktree)`, alors `worktree remove --force <wt>` puis `os.rmdir(parent)` ; dans tous les cas `worktree prune`, puis `branch -D <branche>` si elle commence par `mantis/fix/<audit>/` (erreurs git ignorées : `check=False`). Il vide `worktree` dans l'entrée. Appelée sous verrou : elle prend les données en paramètre, voir la signature privée `_cleanup(audit_dir, data, stem)` ; `cleanup` est l'enveloppe verrouillée.
  - `queue(audit_dir, stem, cmd_id: str | None = None) -> dict` : `status "queued"`, `cmd`, `error None`.
  - `launchable(audit_dir) -> list[str]` : stems `queued` triés par `at`, limités à `FIX_LIMIT - nombre de running`.
  - `start(audit_dir, stem) -> dict` : voir l'algorithme ci-dessous. Renvoie l'entrée, plus `prev_diff` (chemin ou `None`), `msg_file`, `title`, `bucket`, `dirty` (`bool(state["git_status_before"])`), `repo`, `audit`.
  - `finish(audit_dir, stem, interrupted: bool = False) -> dict`.
  - `fail(audit_dir, stem, reason: str) -> dict` : `failed` avec `error = reason`, puis nettoyage.
  - `reconcile(audit_dir) -> list[dict]` : `finish(..., interrupted=True)` sur chaque entrée `running`.
  - `busy(audit_dir) -> list[str]` : stems `running`, `ready` ou `merged`.
  - `active(audit_dir) -> list[str]` : stems `queued` ou `running`.
  - Ligne de commande `python3 fixes.py start|finish|fail|launchable|reconcile|busy|active <AUDIT> [stem] [raison]` : une ligne JSON par résultat (`launchable`, `busy` et `active` : un stem par ligne) ; `--help` liste les 7 sous-commandes ; erreur (`ValueError`, `RuntimeError`) : message sur stdout et code 2.
- Produit (dans `S/test_fixes.py`), réutilisés par les tâches 2, 4 et 5 :
  - `git_audit(tmp, findings=(("f1", F),), state=None) -> tuple[Path, Path]` : repo git dans `<tmp>/repo` avec `app.py` (10 lignes numérotées) commité, dossier d'audit `<repo>/osho-mantis/audit-x` (avec `campaign.json` dont `repo` vaut le toplevel résolu, `level` Light, et les findings), `.git/info/exclude` contenant `osho-mantis/`. Renvoie `(audit_dir, repo)`.
  - `agent_commit(entry, path="app.py", line=3, text="fixed") -> str` : simule l'agent (remplace la ligne `line` dans le worktree, `add -A`, puis `-c core.hooksPath=/dev/null commit -F <msg_file>`, comme le prompt de l'agent) et renvoie le sha.
  - `make_ready(audit, stem, **kw) -> dict` : `start`, `agent_commit`, `finish`.

Algorithme de `start(audit_dir, stem)` (sous `locked`) :
1. `valid_stem` faux, ou statut courant `running`, `ready` ou `merged` : `ValueError`.
2. Si le statut précédent était `conflict` et que `<AUDIT>/fixes/<stem>.prev.diff` existe, on le garde pour `prev_diff`. On appelle `_cleanup` (restes d'un essai précédent).
3. `head = ensure_audit_branch()`. Si `has_filter(repo, head)` : `failed` « le repo déclare un filtre git (.gitattributes) : correction refusée », puis retour.
4. On écrit `<AUDIT>/fixes/<stem>.msg` : `fix(mantis): <titre sur une ligne, 200 caractères max> [<stem>]`.
5. `tmp = mkdtemp(prefix="tmp.")`, puis `worktree add -q -b <fix_branch> <tmp>/wt <head>`. En cas d'échec : `failed` avec la première ligne de stderr, `os.rmdir(tmp)`.
6. Entrée : `status "running"`, `branch`, `worktree`, `base = head`, `commit None`, `error None`, `agent = "Correctif " + short(stem)`.

Règles de `finish` (sous `locked`, entrée `running` attendue, sinon on la renvoie telle quelle) :
- `ahead = rev-list --count <base>..<branch>` (0 si la branche ou le worktree a disparu) ; `clean` : `status --porcelain` vide dans le worktree, faux si le worktree n'existe plus.
- `ahead >= 1` et `clean` : `ready`, avec `commit = rev-parse <branch>`. Le worktree est gardé.
- Sinon : `failed`, avec `error` valant « correction interrompue » si `interrupted`, sinon « aucun commit sur la branche du correctif » (`ahead == 0`) ou « fichiers non commités dans le worktree » ; puis `_cleanup`.

- [ ] **Step 1 : écrire les tests qui échouent** dans `S/test_fixes.py`.
  - `test_start_cree_branches` : après `start(audit, "f1")`, `rev-parse refs/heads/mantis/audit-x` vaut le HEAD du repo, `refs/heads/mantis/fix/audit-x/f1` existe, `entry["status"] == "running"`, `Path(entry["worktree"]).is_dir()`, et `entry["agent"] == "Correctif f1"`.
  - `test_base_commit` : `state={"base_commit": <sha du 1er commit>}`, puis un 2e commit dans le repo ; la branche de l'audit pointe sur le 1er. Avec `base_commit: "zzz"`, elle pointe sur HEAD.
  - `test_branche_audit_reutilisee` : deux `start` sur `f1` et `f2` donnent le même `base` ; un commit ajouté à la main sur `mantis/audit-x` avant le 2e `start` devient son `base`.
  - `test_finish_ready_et_failed` : `make_ready` donne `ready` avec `commit` égal au tip de la branche ; un `start` sans commit puis `finish` donne `failed` « aucun commit sur la branche du correctif », le worktree et la branche du correctif n'existent plus.
  - `test_worktree_disparu` : `start`, puis `shutil.rmtree` du parent du worktree ; `finish` renvoie `failed` sans exception et `git worktree list` ne liste plus ce chemin.
  - `test_reconcile` : deux entrées `running`, l'une avec commit : `reconcile` donne `["ready", "failed"]`, la seconde avec `error == "correction interrompue"`.
  - `test_launchable_limite` : 5 `queue` successifs et 2 `running` : `launchable` renvoie le 1er seulement ; sans `running`, les 3 premiers dans l'ordre.
  - `test_stem_hostile` : `start(audit, "../x")` et `start(audit, "absent")` lèvent `ValueError` ; aucune ref `mantis/` n'est créée.
  - `test_filtre_refuse` : `.gitattributes` commité avec `* filter=evil` : `start` renvoie `failed` et `git worktree list` n'a qu'une ligne.
  - `test_titre_hostile_message` : titre `'a"; $(id) `\nb'` : le fichier `.msg` fait une ligne, contient `$(id)` tel quel et se termine par `[f1]` ; `agent_commit` réussit et `log -1 --format=%s` vaut cette ligne.
  - `test_safe_tmp` : vrai pour `mkdtemp(prefix="tmp.")` ; faux pour `""`, `$HOME`, `gettempdir()/../x`, un lien vers un vrai `mkdtemp`, et un dossier `gettempdir()/com.apple.x`.
  - `test_repo_of_refuse` : `campaign.json["repo"] = "/tmp"` : `start` lève `ValueError("repo de l'audit introuvable")`.
  - `test_cli` : `python3 fixes.py --help` cite les 7 sous-commandes ; `python3 fixes.py start <AUDIT> ../x` sort avec le code 2.
- [ ] **Step 2 :** `python3 S/test_fixes.py` échoue (`ModuleNotFoundError: fixes`).
- [ ] **Step 3 : implémenter `S/fixes.py`** selon les signatures et les règles ci-dessus.
- [ ] **Step 4 :** `python3 S/test_fixes.py` affiche `OK`.
- [ ] **Step 5 : commit** `feat(osho-mantis): fixes.py, branches et worktrees des corrections`.

### Task 2 : `fixes.py`, merger dans la branche de l'audit

**Files :**
- Modify : `S/fixes.py`
- Test : `S/test_fixes.py`

**Interfaces :**
- Consomme : la tâche 1 (`locked`, `load`, `_save`, `_cleanup`, `git`, `repo_of`, `audit_branch`), et les helpers `git_audit`, `agent_commit`, `make_ready`.
- Produit :
  - `merge_ref(repo: Path, ref: str, old: str, fix: str, message: str) -> tuple[str, str | None]`. Elle lance `merge-tree --write-tree <old> <fix>` : code 1 donne `("conflict", None)`, un autre code non nul lève `RuntimeError`. Puis `commit-tree <tree> -p <old> -p <fix> -m <message>` (argument de liste, jamais de shell), puis `update-ref <ref> <new> <old>`. Si cet `update-ref` échoue, elle renvoie `("busy", None)`. Sinon `("merged", <new>)`.
  - `merge(audit_dir, stem) -> tuple[str, str | None]`, sous `locked` du début à la fin. Résultats possibles :
    - `("refused", "le correctif n'est pas prêt")` si le statut relu sous verrou n'est pas `ready` ;
    - `("failed", "branche de l'audit introuvable")` si `rev-parse --verify refs/heads/mantis/<audit>` échoue : statut `failed` avec ce texte, `_cleanup`, et la branche n'est pas recréée ;
    - `("conflict", "conflit avec un autre correctif")` : on écrit `git diff <base> <commit>` dans `<AUDIT>/fixes/<stem>.prev.diff`, statut `conflict`, `_cleanup`. La branche de l'audit est inchangée ;
    - `("busy", "branche de l'audit modifiée pendant la fusion, réessaie")` : statut laissé à `ready`, rien n'est nettoyé ;
    - `("merged", None)` : statut `merged`, `merge_commit = <new>`, `error None`, `_cleanup` (worktree et branche du correctif supprimés ; le commit reste joignable par le merge).
  - Le commit fusionné est `entry["commit"]` (celui constaté à `ready`), pas le tip courant de la branche du correctif. Message : `Merge correctif Mantis : <title> [<stem>]`, avec le titre du fichier de finding.
  - Ligne de commande : rien de nouveau (le merge passe par `commands.apply`, tâche 4).

- [ ] **Step 1 : tests qui échouent.**
  - `test_merge_sans_conflit` : `make_ready` sur `f1`, puis `merge` renvoie `("merged", None)`. `log -1 --format=%s mantis/audit-x` vaut `Merge correctif Mantis : <title> [f1]`, `rev-list --parents -1` montre 2 parents, `status == "merged"`, et la branche du correctif n'existe plus.
  - `test_merge_conflit` : `make_ready` sur `f1` et `f2` qui modifient la même ligne 3 ; le merge de `f1` réussit, celui de `f2` renvoie `"conflict"`. Attendus : le sha de `mantis/audit-x` est le même avant et après le 2e merge, `fixes/f2.prev.diff` contient `+fixed`, `status == "conflict"`, et le worktree de `f2` n'existe plus.
  - `test_recorriger_part_de_la_tete` : après le conflit ci-dessus, `start(audit, "f2")` donne `base` égal à la tête à jour de `mantis/audit-x` et `prev_diff` égal au chemin du `.prev.diff`.
  - `test_merge_concurrent_update_ref` : `merge_ref(repo, "refs/heads/mantis/audit-x", <sha périmé>, <commit>, "m") == ("busy", None)`, et la ref est inchangée.
  - `test_merge_double_seul_un` : deux threads appellent `merge(audit, "f1")` ; attendus : les résultats triés valent `["merged", "refused"]` et `rev-list --merges --count mantis/audit-x == 1`.
  - `test_merge_branche_supprimee` : `make_ready`, puis `update-ref -d refs/heads/mantis/audit-x` ; attendus : `merge` renvoie `"failed"` avec « branche de l'audit introuvable », et la ref n'existe toujours pas.
  - `test_repo_utilisateur_intact` : on relève `status --porcelain`, `symbolic-ref HEAD`, `rev-parse HEAD` et le contenu de `app.py` dans le repo avant `make_ready` puis `merge` ; les quatre sont identiques après.
  - `test_hooks_neutralises` : `config core.hooksPath <repo>/hooks`, avec des hooks exécutables `post-checkout` et `reference-transaction` qui créent `<tmp>/HOOKED` ; après `make_ready` et `merge`, `<tmp>/HOOKED` n'existe pas.
- [ ] **Step 2 :** les tests échouent (`merge` absent).
- [ ] **Step 3 : implémenter `merge_ref` et `merge`.**
- [ ] **Step 4 :** `python3 S/test_fixes.py` affiche `OK`.
- [ ] **Step 5 : commit** `feat(osho-mantis): merge en mémoire des correctifs dans la branche de l'audit`.

### Task 3 : `snapshot.py`, états de correction et colonnes

**Files :**
- Modify : `S/snapshot.py` : `progress`, `build_snapshot`, `COLUMN_LABELS`, `ACT_LABELS`, `diff_events`
- Modify : `S/test_snapshot.py` : le helper `audit(...)` gagne `fixes=None`, qui écrit `fixes.json` ; `test_progress_colonnes` est mis à jour
- Test : `S/test_snapshot.py`

**Interfaces :**
- Consomme : `fixes.load(audit_dir)`, `fixes.audit_branch(audit_dir)`, `commands.pending(audit_dir)`.
- Produit :
  - Chaque finding du snapshot porte `_fix` : `None`, ou un dict avec les clés présentes parmi `status`, `error`, `branch`, `commit`, `merge_commit`, `cmd` et `at` (jamais `worktree`). Si aucune entrée `queued`, `running`, `ready` ou `merged` n'existe et qu'une commande `fix` en attente vise ce stem, alors `_fix = {"status": "queued", "cmd": <id de la 1re commande>}`.
  - `progress(f)`, dans cet ordre : `rejected` ; `fixed` si `(f.get("_fix") or {}).get("status") == "merged"` ; `proposed` si `patch_status` est présent ; `reproduced` ; `evaluated` ; `reviewed` ; `found`. `_fix` est attaché avant le calcul de `_progress`.
  - `progress_columns` : Light = `["found", "reviewed", "proposed", "fixed"]`, sinon `["found", "reviewed", "evaluated", "reproduced", "proposed", "fixed"]`.
  - `COLUMN_LABELS["proposed"] = "Correctif proposé"`.
  - `listening`, dans cet ordre : `"fixes"` si `waiting.kind == "fixes"` ; puis les règles du lot 1 inchangées.
  - `meta` gagne `audit_branch` (`fixes.audit_branch`), `fixes_merged` (nombre d'entrées `merged`) et `dirty_before` (`bool(state.get("git_status_before"))`).
  - `ACT_LABELS` gagne `fix: "Correction"`, `merge_fix: "Fusion"` et `end_fixes: "Fin des corrections"`.
  - `diff_events` gagne `kind: "fix"` : `{finding, from, to}` quand `_fix.status` change (`None` vaut `"none"`). Textes : `running` « Correction lancée : <title> », `ready` « Correctif prêt : <title> », `failed` « Correction en échec : <title> », `conflict` « Conflit sur le correctif : <title> », `merged` « Correctif fusionné : <title> ». Pas d'événement pour `queued`.

- [ ] **Step 1 : tests qui échouent.**
  - `test_progress_colonnes` (mis à jour) : le finding `fix` (`MITIGATION_PROPOSED`) donne `"proposed"`. Colonnes Sharp : `[..., "reproduced", "proposed", "fixed"]` ; Light : `["found", "reviewed", "proposed", "fixed"]`.
  - `test_fix_colonnes` : `fixes={"a": {"status": "merged"}, "c": {"status": "running", "worktree": "/tmp/x"}}`, avec `a` et `c` qui ont `patch_status`. Attendus : `a` donne `fixed`, `c` donne `proposed`, `"worktree" not in c["_fix"]`, et un finding `b` sans entrée a `_fix is None`.
  - `test_fix_queued_derive` : avec `commands.append(d, {"action": "fix", "finding": "f1"}, "page")`, le snapshot donne `_fix == {"status": "queued", "cmd": <id>}` ; après `commands.ack(..., "refused")`, `_fix is None`.
  - `test_listening_fixes` : `state.finished` et `waiting={"kind": "fixes"}` donnent `"fixes"` ; sans `waiting`, `"none"`.
  - `test_meta_branche` : `meta["audit_branch"] == "mantis/" + d.name`, `fixes_merged == 1`, et `dirty_before is True` avec `git_status_before: " M app.py"`.
  - `test_diff_fix_fusionne` : de `ready` à `merged`, un événement `kind "fix"` dont le texte est `"Correctif fusionné : <title>"`, sans `—`.
- [ ] **Step 2 :** `python3 S/test_snapshot.py` échoue.
- [ ] **Step 3 : implémenter.** `snapshot` importe `fixes` en tête (`fixes` n'importe `snapshot` nulle part).
- [ ] **Step 4 :** `python3 S/test_snapshot.py && python3 S/test_render.py && python3 S/test_commands.py` affichent `OK`. `test_render.py` peut échouer seulement sur `test_frise_etapes`, dont la mise à jour revient à la tâche 7 : le noter, ne pas le corriger ici.
- [ ] **Step 5 : commit** `feat(osho-mantis): snapshot, états de correction et colonne Correctif proposé`.

### Task 4 : `commands.py`, valider et appliquer `fix`, `merge_fix` et `end_fixes`

**Files :**
- Modify : `S/commands.py` : `ACTIONS`, `validate`, `apply`
- Test : `S/test_commands.py`

**Interfaces :**
- Consomme : `snapshot.build_snapshot` (`_fix`, `listening`), `fixes.queue(audit_dir, stem, cmd_id)`, `fixes.merge(audit_dir, stem)`, `render.render(audit_dir)`, et les helpers `test_fixes.git_audit` et `make_ready`.
- Produit :
  - `ACTIONS` gagne `"fix"`, `"merge_fix"` et `"end_fixes"`.
  - `validate`, avec `st = (f["_fix"] or {}).get("status")` :
    - `fix` : finding existant et non `REJECTED` ; `snap["listening"] != "none"` (sinon « Aucune session active : relance /mantis-run ») ; `st` dans `(None, "failed", "conflict")`, ou bien `st == "queued"` avec `_fix["cmd"] == cmd.get("id")` (la commande se revalide elle-même dans `apply`) ; sinon « correction déjà demandée » ou, pour `merged`, « déjà fusionné » ;
    - `merge_fix` : finding existant et `st == "ready"`, sinon « le correctif n'est pas prêt » ;
    - `end_fixes` : `snap["listening"] == "fixes"`, sinon « le mode Corrections n'est pas actif ».
  - `apply(audit_dir, cmd_id)` traite aussi `fix` et `merge_fix` (`end_fixes` lève `ValueError("à traiter par mantis-run")`, comme les autres) :
    - `fix` : `fixes.queue(audit_dir, finding, cmd_id)`, puis ack `applied` ;
    - `merge_fix` : `result, reason = fixes.merge(audit_dir, finding)`. `merged` donne ack `applied`, tout autre résultat donne ack `refused` avec `reason`. Si `merged` et que `state.json` a `finished: true`, on appelle `render.render(audit_dir)`.
    - Une exception (`ValueError`, `RuntimeError`) de `fixes` donne ack `refused` avec son message, sans être propagée.

- [ ] **Step 1 : tests qui échouent.**
  - `test_valide_fix` : finding non écarté, étape `running` : `{"action": "fix", "finding": "f1"}` est valide ; avec `fixes={"f1": {"status": "conflict"}}` aussi ; avec `{"status": "ready"}`, `merge_fix` est valide.
  - `test_refus_fix` : chaque cas renvoie une chaîne non vide :
    - `fix` sur un finding écarté ;
    - `fix` sur un statut `running`, `ready` ou `merged` ;
    - `fix` avec `listening == "none"` (audit `finished` sans `waiting`) ;
    - `fix` avec `finding: "../x"` ;
    - `merge_fix` sur un statut `running` ;
    - `end_fixes` hors du mode Corrections ;
    - un second `fix` pendant que le premier est en attente.
  - `test_apply_fix_en_file` : `append` d'une commande `fix`, puis `apply` donne un accusé `applied` et `fixes.load(d)["f1"] == {"status": "queued", "cmd": <id>, ...}` ; un second `apply` renvoie le même accusé.
  - `test_apply_merge` : avec `git_audit` et `make_ready` sur `f1`, puis `append` de `merge_fix` et `apply`, on obtient un accusé `applied` et `status == "merged"`. Sur un audit `finished`, `README.md` existe ensuite (réécrit par `render.render`) ; son contenu est testé en tâche 6.
  - `test_apply_merge_conflit_refuse` : deux correctifs en conflit, le second `merge_fix` donne un accusé `refused` avec la raison `conflit avec un autre correctif`.
- [ ] **Step 2 :** `python3 S/test_commands.py` échoue.
- [ ] **Step 3 : implémenter.** Import tardif de `fixes` et `render` dans `apply`, comme `snapshot`.
- [ ] **Step 4 :** `python3 S/test_commands.py && python3 S/test_snapshot.py && python3 S/test_fixes.py` affichent `OK`.
- [ ] **Step 5 : commit** `feat(osho-mantis): commandes fix, merge_fix et end_fixes`.

### Task 5 : `dashboard.py`, merge immédiat et serveur gardé en mode Corrections

**Files :**
- Modify : `S/dashboard.py` : `signature`, `Dash.watch`, `Handler.do_POST`, `USAGE`
- Test : `S/test_dashboard.py`

**Interfaces :**
- Consomme : `commands.apply(audit, id)` (tâche 4), `snap["listening"] == "fixes"` (tâche 3), et les helpers `test_fixes.git_audit` et `make_ready`.
- Produit :
  - `signature(audit)` surveille aussi `fixes.json`.
  - `do_POST` : la 409 « Aucune session active : relance /mantis-run » ne s'applique pas à `merge_fix`. Après `commands.append` d'un `merge_fix`, le handler appelle `commands.apply(audit, cmd["id"])` dans le même thread, puis répond 200 avec la commande (la page suit son `id` dans `commands.done`, comme au lot 1).
  - `Dash.watch` : `end_seen` est remis à `None` tant que `self.snap["listening"] == "fixes"`. Le serveur ne s'arrête donc pas pendant le mode Corrections ; la règle des 4 h sans changement reste.
  - `USAGE` : la ligne `apply` devient `applique une commande finding (false_positive, prioritize_repro, fix, merge_fix)`.

- [ ] **Step 1 : tests qui échouent.**
  - `test_post_merge_fix_immediat` : un audit `git_audit` avec `finished: true`, sans `waiting`, avec `make_ready` sur `f1`, et un serveur lancé. Le POST `{"action": "merge_fix", "finding": "f1"}` répond 200. **Dès la réponse**, sans attendre, `commands-done.jsonl` contient cet `id` avec `applied` et `fixes.json["f1"]["status"] == "merged"`. Le snapshot SSE suivant, en moins de 2 s, montre `_progress == "fixed"`.
  - `test_post_fix_409_sans_session` : même audit sans `make_ready` ; le POST `fix` donne 409.
  - `test_watch_garde_en_mode_corrections` : avec `END_GRACE_S = 0` et `POLL_S = 0.01`, un audit `finished` avec `waiting={"kind": "fixes"}` garde le thread `watch` vivant après 0,5 s. Une fois `waiting.json` supprimé, le thread s'arrête en moins de 3 s (même montage que `test_watch_arret_malgre_erreur`).
- [ ] **Step 2 :** les tests échouent.
- [ ] **Step 3 : implémenter.**
- [ ] **Step 4 :** `python3 S/test_dashboard.py` affiche `OK` en moins de 40 s.
- [ ] **Step 5 : commit** `feat(osho-mantis): le serveur fusionne les correctifs sans attendre Claude`.

### Task 6 : `render.py`, section « Corrections fusionnées »

**Files :**
- Modify : `S/render.py` : `readme`
- Modify : `S/test_render.py` : le helper `audit(tmp, findings, broken=False)` gagne `fixes=None`, qui écrit `fixes.json` avant de lancer `render.py`
- Test : `S/test_render.py`

**Interfaces :**
- Consomme : `meta["audit_branch"]`, `meta["fixes_merged"]` et `f["_fix"]` (tâche 3).
- Produit : dans `readme(meta, findings, unreadable, st)`, juste avant `## Limites` et seulement si `meta["fixes_merged"] > 0`, ce texte exact (un finding fusionné par ligne, dans l'ordre des findings) :

```
## Corrections fusionnées

<n> correctif(s) sur la branche `<branch>`. Pour les intégrer à ta branche : `git merge <branch>`

- <text(title)> (`<merge_commit[:7] ou commit[:7]>`)
```

`correctif(s)` s'écrit `correctif` si n vaut 1 et `correctifs` sinon. Le titre passe par `text()`. La branche est un nom construit par le code.

- [ ] **Step 1 : tests qui échouent.**
  - `test_readme_corrections_fusionnees` : `fixes={"f0": {"status": "merged", "commit": "a" * 40, "merge_commit": "b" * 40}}`. Attendus : `README.md` contient `## Corrections fusionnées`, `1 correctif sur la branche`, `git merge mantis/` et `` (`bbbbbbb`) ``, et cette section précède `## Limites`.
  - `test_readme_sans_correction` : sans `fixes.json`, `Corrections fusionnées` est absent.
  - `test_readme_corrections_hostile` : un titre `<img src=x onerror=alert(1)>` fusionné apparaît échappé (`&lt;img`).
- [ ] **Step 2 :** les tests échouent.
- [ ] **Step 3 : implémenter.**
- [ ] **Step 4 :** `python3 S/test_render.py && python3 S/test_snapshot.py && python3 S/test_commands.py` affichent `OK`.
- [ ] **Step 5 : commit** `feat(osho-mantis): README, section Corrections fusionnées`.

### Task 7 : `dashboard.html`, boutons de correction, bannière et mode Corrections

**Files :**
- Modify : `S/dashboard.html`
- Modify : `S/test_render.py` : mise à jour de `test_frise_etapes`
- Test : `S/test_render.py`

**Interfaces :**
- Consomme : `f._fix`, `D.progress_columns` (avec `proposed`), `D.listening == "fixes"`, `D.meta.audit_branch`, `fixes_merged`, `dirty_before`, et les actions `fix`, `merge_fix`, `end_fixes`.
- Produit (fonctions et constantes JS de niveau supérieur) :
  - `PROG` gagne `['proposed', 'Correctif proposé', 'Correctif proposé']` juste avant `['fixed', 'Corrigées', 'Corrigé']`.
  - `trail(f)` : `reached.proposed = !!f.patch_status` et `reached.fixed = !!(f._fix && f._fix.status === 'merged')`.
  - `const FIX_LABEL = {queued: 'En file…', running: 'Correction en cours', ready: 'Correctif prêt', failed: 'Échec de la correction', conflict: 'Conflit avec un autre correctif', merged: 'Corrigée'}`.
  - `function fixView(f, mode)`, pure, renvoie `null` ou `{text, action, label, cls}` :
    - `null` si `mode === 'final'`, si `f._bucket === 'REJECTED'` ou si le statut vaut `merged` ;
    - sans statut : `{action: 'fix', label: 'Corriger'}` ;
    - `failed` : `{text: 'Échec : ' + (error || 'raison inconnue'), action: 'fix', label: 'Corriger'}` ;
    - `queued` : `{text: 'En file…'}` ;
    - `running` : `{text: 'Correction en cours', cls: 'loading'}` ;
    - `ready` : `{action: 'merge_fix', label: 'Merger', cls: 'pri'}` ;
    - `conflict` : `{text: 'Conflit avec un autre correctif', action: 'fix', label: 'Recorriger'}`.
  - `card(f)` renvoie toujours `div.fc-card[data-src]`, qui contient le `button.fc` actuel (il garde `data-src`). Dans la vue `progress`, si `fixView(f, D.mode)` n'est pas nul, on ajoute dessous `div.fc-fix` : un `span` pour `text` (avec la classe `cls`), puis `cmdButton({action, finding: f._src}, 'btn sm ' + (cls || ''), label)` si `action` existe. Dans la vue `severity` et en mode `final`, si un statut existe, la puce `el('span', {class: 'chip fx-' + status}, FIX_LABEL[status])` est ajoutée aux `.chips`. Pas de bouton imbriqué dans un bouton.
  - `flip` et la mesure `before` de `renderBoard` portent sur `.fc-card`. `cardFor` cherche toujours `button.fc`.
  - `cmdButton` : la condition de grisage devient `D.listening === 'none' && cmd.action !== 'merge_fix'`.
  - `renderBoard` : dans la vue `progress`, en mode `live`, avec `D.meta.dirty_before`, il affiche au-dessus du kanban `p.fix-warn` avec le texte exact « L'audit portait aussi sur des modifications non commitées : le correctif part du dernier commit. »
  - Bannière : ajouter `<p id="fix-branch" hidden><span></span> <button id="copy-merge" class="btn sm" type="button">Copier git merge</button></p>` dans `#banner`. `renderBanner` l'affiche si `D.meta.fixes_merged > 0`, avec `<n> correctif(s) sur <audit_branch>`. Le bouton copie `git merge <audit_branch>` via `navigator.clipboard`, avec le même retour « Copié » ou « Copie impossible » que « Copier le diff ». Le bouton est aussi présent en mode `final`.
  - `renderActions` : si `D.listening === 'fixes'`, le texte de session est « Claude attend tes demandes de correction », et le seul bouton est `cmdButton({action: 'end_fixes'}, 'btn pri', 'Terminer')` (ni pause, ni arrêt).
  - `ACT_LABEL` gagne `fix: 'Correction'`, `merge_fix: 'Fusion'` et `end_fixes: 'Fin des corrections'`.
  - `ui.view` initial : `new URLSearchParams(location.search).get('kb')` vaut `'progress'` ou `'severity'`, sinon `localStorage["mantis.kbView"]` (pour les captures et les liens).
  - CSS : `.fc-card` reprend la `margin-bottom` de `.fc` ; `.fc-fix` est une rangée flex de 6 px d'écart ; `.btn.sm` fait 24 px de haut ; `.loading::before` est un anneau de 10 px qui tourne (`@keyframes spin`).

- [ ] **Step 1 : tests qui échouent** dans `S/test_render.py`.
  - `test_frise_etapes` (mis à jour) : `D.progress_columns` contient `proposed`. Un `MITIGATION_PROPOSED` sans `_fix` donne `'Correctif proposé': true` et `'Corrigé': false` ; avec `_fix: {status: 'merged'}`, `'Corrigé': true`.
  - `test_fix_view` (node, `fn(js, "fixView")` plus `FIX_LABEL`) : un cas par ligne de la table ci-dessus. Par exemple, `fixView({_bucket: 'HIGH', _fix: {status: 'ready'}}, 'live').action === 'merge_fix'`, `fixView({_bucket: 'HIGH'}, 'final') === null` et `fixView({_bucket: 'REJECTED'}, 'live') === null`.
  - `test_fix_hooks` : `id="fix-branch"`, `id="copy-merge"`, `Correctif proposé`, `Claude attend tes demandes de correction` et `cmd.action !== 'merge_fix'` sont présents dans le HTML ; `innerHTML` et `—` en sont absents.
- [ ] **Step 2 :** `python3 S/test_render.py` échoue.
- [ ] **Step 3 : implémenter.**
- [ ] **Step 4 :** `python3 S/test_render.py && python3 S/test_dashboard.py` affichent `OK` (y compris `node --check`).
- [ ] **Step 5 : vérification visuelle.**
  1. Construire un audit fictif Light avec 7 findings, un par statut `_fix` (aucun, `queued`, `running`, `ready`, `failed`, `conflict`, `merged`), et `git_status_before` non vide, puis le rendre en mode live avec `dashboard.py serve`.
  2. Capturer `<url>&kb=progress` avec `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --screenshot=/tmp/mantis-l2.png --window-size=1440,1000` (passer la clé dans l'URL).
  3. Lire l'image. On doit y voir les colonnes Trouvées, Revues, Correctif proposé et Corrigées, les boutons Corriger, Merger et Recorriger, « En file… », l'indicateur de chargement, la raison d'échec, l'avertissement au-dessus du kanban, et la bannière « 1 correctif sur mantis/… ».
- [ ] **Step 6 : commit** `feat(osho-mantis): boutons Corriger et Merger sur les cartes du kanban`.

### Task 8 : brancher mantis-run et passer en 0.3.0

**Files :**
- Modify : `plugins/osho-mantis/skills/mantis-run/SKILL.md`
- Modify : `plugins/osho-mantis/.claude-plugin/plugin.json` : version `0.2.0` → `0.3.0`, et la description ajoute « one-click fixes merged into a local audit branch »
- Modify : `.claude-plugin/marketplace.json` : description d'osho-mantis alignée mot pour mot sur `plugin.json`
- (mantis-triage/SKILL.md n'a pas à changer : `base_commit` est posé par mantis-run §2.)

**Interfaces :**
- Consomme : `python3 "$R/fixes.py" start|finish|fail|launchable|reconcile|busy|active` (tâches 1 et 2), `python3 "$R/dashboard.py" apply|ack|command|pending|alive` (lot 1 et tâche 4), et `waiting.json` `{"kind": "fixes", "since"}` (tâche 3).

Changements dans `mantis-run/SKILL.md`, d'après la spec §1, §2, §3 et §5 :
- **§1 Select the audit :**
  - si l'audit nommé a `"finished": true`, on fait le contrôle hostile, puis `serve`, puis on passe directement au §5 Corrections, sans relancer d'étape (la sélection automatique continue d'ignorer les audits terminés) ;
  - après le nettoyage des restes, `python3 "$R/fixes.py" reconcile "$AUDIT"`, et une ligne par correction réévaluée.
- **§2.2 :** `state.json` gagne `base_commit` = `git -C "$REPO" rev-parse HEAD` (on l'omet si le repo n'a aucun commit).
- **§3, règle de périmètre :** les findings listés par `python3 "$R/fixes.py" busy "$AUDIT"` (`running`, `ready` ou `merged`) sont exclus de critic, reproduce, patch et calibrate, comme les findings écartés. La liste est relue au début de chacune de ces étapes et avant chaque finding de Patch Sharp+.
- **Checkpoint**, nouvelles lignes :
  - `fix` donne `dashboard.py apply` (met en file et accuse), puis **Lancer les corrections** ;
  - `merge_fix` (venu du terminal) donne `dashboard.py apply` ;
  - `end_fixes` hors du mode Corrections donne `ack refused` « le mode Corrections n'est pas actif ».
- **Wait for the user :** au réveil, `fix` et `merge_fix` sont traités comme `false_positive` (`apply`, l'attente continue), `fix` étant suivi de Lancer les corrections.
- **Nouveau « Lancer les corrections » :** pour chaque stem de `fixes.py launchable` :
  1. `python3 "$R/fixes.py" start "$AUDIT" <stem>` affiche l'entrée JSON. Si son `status` vaut `failed`, on le dit en une ligne et on passe au suivant.
  2. On lance un Agent avec `run_in_background: true`, `subagent_type: general-purpose`, la description `Correctif <stem court>` (= `agent`), le modèle `opus` si `bucket == "CRITICAL"` et `sonnet` sinon, et le prompt de correction ci-dessous.
  3. On note en une ligne « Correction lancée : <titre> », puis on reprend où l'on était, sans attendre l'agent.
- **Prompt de correction** : le texte de la spec §2.3, mot pour mot. Le point 4 devient : `Commit once: git -C <WORKTREE> add -A && git -C <WORKTREE> -c core.hooksPath=/dev/null commit -q -F <MSG_FILE>. Do not push, do not merge.` Deux lignes sont ajoutées sous conditions :
  - si `prev_diff` : `A previous attempt conflicted with another merged fix: <PREV_DIFF>. Redo it on the current code.` ;
  - si `dirty` : `The audit also covered uncommitted changes: your worktree starts from the last commit. If the code the finding targets is not there, commit nothing and answer « aucun ».`
- **Nouveau « Fin d'un agent de correction »** (notification de fin d'un agent `Correctif …`, pendant l'audit comme en mode Corrections) :
  - si l'agent a terminé normalement : `python3 "$R/fixes.py" finish "$AUDIT" <stem>` ;
  - s'il a échoué (erreur, quota) : `fixes.py fail "$AUDIT" <stem> "<raison en une ligne>"` ;
  - on dit le statut en une ligne, puis on refait « Lancer les corrections » (une place s'est libérée) ;
  - en attente (Monitor en cours), on ne relance pas Monitor.
- **Stop :** les commandes `fix` en attente sont acceptées et mises en file (`apply`), au lieu d'être refusées « audit arrêté » ; les agents de correction en cours ne sont pas arrêtés.
- **§4 Finish :**
  - l'étape 5 ajoute, si `fixes_merged > 0` : « <n> correctifs sur `mantis/<audit>` : `git merge mantis/<audit>` » ;
  - la ligne de commit des audits `versioned` passe à la fin du §5, car elle arrête le serveur ;
  - nouvelle étape 6 : entrer dans le §5 Corrections.
- **Nouveau §5 Corrections** (mode d'écoute après l'audit) :
  1. Écrire `waiting.json` `{"kind": "fixes", "since"}`. Dire « Claude attend tes demandes de correction : clique Corriger sur le dashboard, ou tape « corrige <id> ». Tape « terminé » pour finir. »
  2. Lancer Monitor (`timeout_ms` 1800000) avec la même boucle `pending`, puis terminer le tour.
  3. Au réveil, lancer `pending` et traiter dans l'ordre :
     - `fix` : `apply`, puis Lancer les corrections ;
     - `merge_fix` : `apply` ;
     - `false_positive` et `prioritize_repro` : `apply` ;
     - `end_fixes` : `ack applied`, puis sortie ;
     - `pause`, `resume`, `retry`, `answer` et `stop` : `ack refused` « l'audit est terminé ».
     
     Puis relancer Monitor (TaskStop d'abord s'il tourne encore après une réponse tapée).
  4. Monitor expiré sans commande :
     - `fixes.py active` affiche au moins un stem : relancer Monitor si `dashboard.py alive` réussit, sinon sortie ;
     - rien en cours (30 min sans clic) : sortie.
  5. Sortie :
     - `rm -f "$AUDIT/waiting.json"` ;
     - dire « Mode Corrections terminé. `/mantis-run <audit>` le rouvre. », avec la ligne `git merge mantis/<audit>` s'il y a des fusions ;
     - pour un audit `versioned`, la ligne de commit déplacée du §4.
  6. Depuis le terminal :
     - « corrige f-014 » devient `{"action": "fix", "finding": "<stem>"}` ;
     - « merge f-014 » devient `{"action": "merge_fix", ...}` ;
     - « terminé » devient `{"action": "end_fixes"}` ;
     - chacun est enregistré avec `dashboard.py command`, puis traité comme une commande de la page. L'id tapé est résolu vers le stem du fichier sous `workspace/findings/`, comme pour `false_positive`.
- **From the terminal (§3) :** ajouter les mêmes trois exemples.

- [ ] **Step 1 :** écrire les modifications.
- [ ] **Step 2 : relecture de cohérence.**
  - Chaque sous-commande citée existe : `python3 S/fixes.py --help` et `python3 S/dashboard.py --help` les listent.
  - `grep -c "run_in_background" SKILL.md` ≥ 1.
  - `grep -n "Correctif <" SKILL.md` montre le nom de l'agent.
  - Le prompt contient `-F <MSG_FILE>` et `core.hooksPath=/dev/null`.
  - `jq .version plugin.json` vaut `"0.3.0"`.
  - Les deux descriptions sont identiques : `diff <(jq -r .description plugin.json) <(jq -r '.plugins[] | select(.name=="osho-mantis") | .description' .claude-plugin/marketplace.json)` est vide.
- [ ] **Step 3 :** `for t in fixes snapshot commands dashboard render; do python3 S/test_$t.py || exit 1; done` affiche cinq `OK`.
- [ ] **Step 4 : commit** `feat(osho-mantis): corriger et merger depuis le kanban (0.3.0)`.

### Task 9 : essai réel sur `~/dev/mantis-toy` (contrôleur, avant fusion)

Pas de code. Le contrôleur lance une session Claude Code avec le plugin de cette branche, par exemple `claude --plugin-dir /Users/robin-le-gal/dev/OshO-Skillz/plugins/osho-mantis` depuis `~/dev/mantis-toy` (ou par le moyen utilisé pour l'essai du lot 1).

1. **Avant :** `git -C ~/dev/mantis-toy status --porcelain > /tmp/toy-before.txt` et `git -C ~/dev/mantis-toy rev-parse --abbrev-ref HEAD`.
2. `/mantis-run osho-mantis/audit-2026-10-22_17h28` : l'audit est terminé, et le mode Corrections s'ouvre directement. La page affiche « Claude attend tes demandes de correction » et le bouton Terminer. Comme l'audit n'a pas de `base_commit`, la base est le HEAD.
3. **Vue Avancement :** on doit voir les colonnes Trouvées, Revues, Correctif proposé et Corrigées. Cliquer **Corriger** sur deux findings qui touchent tous deux `preview()` dans `app.py` : l'injection de commande (`4c75e393…`) et le path traversal de `/preview`. Les deux cartes passent à « En file… », puis à « Correction en cours ». Deux agents `Correctif <stem court>` sont visibles dans la session.
4. Quand les deux sont prêts, **Merger** le premier : la carte passe dans Corrigées en moins de 2 s, sans attendre Claude, et la bannière affiche « 1 correctif sur mantis/audit-2026-10-22_17h28 ».
5. **Merger** le second : on doit voir « Conflit avec un autre correctif » et le bouton Recorriger. Si git fusionne sans conflit, le noter dans le compte rendu : le conflit reste couvert par `test_merge_conflit`.
6. **Recorriger**, puis **Merger** une fois l'agent prêt : la carte passe dans Corrigées.
7. Vérifier :
   - `git -C ~/dev/mantis-toy log --oneline --graph mantis/audit-2026-10-22_17h28` montre deux merges `Merge correctif Mantis : …` et deux commits `fix(mantis): …` ;
   - `git status --porcelain` est identique à `/tmp/toy-before.txt` ;
   - la branche courante est inchangée ;
   - `git worktree list` n'a plus qu'une ligne ;
   - `git branch --list 'mantis/fix/*'` est vide ;
   - `README.md` de l'audit contient « Corrections fusionnées » ;
   - le `dashboard.html` final, ouvert hors ligne, montre les deux cartes dans Corrigées.
8. Cliquer **Terminer** : le terminal affiche « Mode Corrections terminé… », et la page passe à « Aucune session active ». Le bouton Merger d'une éventuelle carte `ready` reste actif.
