# osho-mantis : dashboard live (lot 1), plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal :** remplacer le `dashboard.html` de fin d'audit par une page servie en local qui suit l'audit en direct (triage compris) et permet d'agir depuis la page comme depuis le terminal. À la fin, la même page devient le rapport final hors ligne.

**Architecture :**
- `snapshot.py` lit le dossier d'audit et en tire un dictionnaire unique, le « snapshot », plus les événements d'activité.
- `commands.py` gère la file d'actions (`commands.jsonl` → `commands-done.jsonl`).
- `dashboard.py` est un serveur Python stdlib qui scrute les fichiers et pousse le snapshot en SSE.
- `dashboard.html` est le gabarit unique, en vanilla JS, partagé par le mode live et par le fichier final que produit `render.py`.
- Les SKILL.md branchent le tout : lancement du serveur, points de contrôle, attente via Monitor.

**Tech Stack :** Python 3 stdlib (`http.server`, `json`, `secrets`, `subprocess`), HTML/CSS/JS sans build, Node seulement pour `node --check` dans les tests (déjà le cas).

**Spec :** `docs/superpowers/specs/2026-10-22-mantis-dashboard-live-design.md`. La maquette de référence est `docs/superpowers/specs/assets/2026-10-22-mantis-dashboard-maquette.html` : l'ouvrir avant toute tâche de gabarit.

Dossier de travail : `plugins/osho-mantis/skills/mantis-run/scripts/` (noté `S/` ci-dessous).

## Global Constraints

- Aucune dépendance nouvelle : Python 3 stdlib côté serveur ; HTML/CSS/JS sans build et sans ressource réseau (pas de police ni de CDN), car le fichier final doit marcher hors ligne.
- Le serveur écoute sur `127.0.0.1` uniquement. Une clé de session de 32 octets aléatoires (`secrets.token_hex(32)`) est exigée sur toutes les routes : `?key=` au premier chargement, puis cookie `mantis_key` en `HttpOnly; SameSite=Strict`. Le POST exige aussi `Origin` égal à `http://127.0.0.1:<port>` ou `http://localhost:<port>`. Toute requête dont l'en-tête `Host` n'est pas l'un de ces deux hôtes reçoit une 403.
- Tout texte issu d'un finding est inséré dans la page avec `textContent` (ou `el()`), **jamais** avec `innerHTML`. Le JSON inclus dans la page passe par `safe_json()` de `render.py`.
- Une commande se valide en un seul endroit, `commands.validate()`, utilisé par le POST, par `dashboard.py command` et par `dashboard.py apply`. Taille maximale : 1 Ko.
- Les jetons de design sont ceux de la spec §6, recopiés en variables CSS. Thème sombre par défaut et thème clair disponible, posés sur `<html data-theme>`. Rayons : 10 px pour tuiles, fiche et pipeline ; 6 px pour boutons, cartes et champs.
- Toutes les chaînes visibles sont en français avec leurs accents, et **aucun tiret cadratin** (`—`) n'apparaît dans le gabarit ni dans les textes du journal.
- `prefers-reduced-motion: reduce` coupe toutes les animations.
- Les étapes et leur ordre, par niveau : Light = architecture, threat-model, plan, researcher, review, patch. Sharp = structural-index, architecture, threat-model, plan, researcher, dedupe, review, critic, reproduce, patch, calibrate. Savage et Overkill = history, structural-index, architecture, threat-model, plan, researcher, dedupe, review, critic, reproduce, chain, patch, calibrate, reflect. Triage est toujours affiché en premier.
- Codes d'étapes : triage TRI, history HIS, structural-index IDX, architecture ARC, threat-model THR, plan PLN, researcher RSC, dedupe DDP, review REV, critic CRT, reproduce REP, chain CHN, patch PAT, calibrate CAL, reflect RFL.
- Les tests sont des auto-tests exécutables (`python3 test_x.py` affiche `OK`), sans pytest, comme `test_render.py`.

## Review Focus

1. **Écritures concurrentes sur `state.json`.** Le serveur lit le fichier pendant que Claude l'écrit, et il peut tomber sur un JSON tronqué. Attendu : le serveur garde le snapshot précédent et ne produit aucun faux événement « étape repassée à pending ». Test : `test_json_tronque_ignore` (tâche 2).
2. **Une commande cliquée deux fois, ou rejouée après un redémarrage.** Attendu : un seul effet. Test : `test_apply_idempotent` (tâche 3).
3. **Serveur relancé avec un vieux `server.json` dont le pid est mort.** Attendu : un nouveau serveur démarre et le fichier est remplacé. Test : `test_serve_pid_mort` (tâche 4).
4. **Finding hostile dont le titre contient `</script>` ou `<img onerror>`.** Le risque existe dans le snapshot SSE comme dans le fichier final. Attendu : texte inerte dans les deux modes. Tests : `test_trois_findings` existant (fichier final) et `test_sse_xss_inerte` (tâche 4).
5. **Audit sans `state.json`** (triage seul) **ou avec un niveau absent.** Attendu : la page s'affiche avec Triage en cours, sans exception. Test : `test_snapshot_triage_seul` (tâche 1).

---

### Task 1 : `snapshot.py`, construire le snapshot

**Files :**
- Create : `S/snapshot.py`
- Modify : `S/render.py`. `load_findings` ajoute `f["_src"] = p.stem`. `render()` délègue à `build_snapshot`. Le calcul de `_file` est déplacé dans `snapshot.assign_files()`.
- Test : `S/test_snapshot.py`

**Interfaces :**
- Produit `build_snapshot(audit_dir: Path, mode: str = "live", now: float | None = None) -> dict`, avec les clés :
  - `mode` : `"live"` ou `"final"` ;
  - `generated_at` : ISO ;
  - `meta` : les clés actuelles de `render()`, plus `round`, `finished`, `stopped`, `paused`, `audit_age_s` ;
  - `stats` : `render.stats()` ;
  - `labels` : `render.ENUM_LABELS` ;
  - `stages` : liste de `{key, code, name, status, duration_s, started_at, notes}` ;
  - `current` : `state["current"]` ou `None` ;
  - `waiting` : contenu de `waiting.json` ou `None` ;
  - `listening` : `"working"`, `"waiting"` ou `"none"` ;
  - `stale` : booléen ;
  - `findings` : liste triée par `render.sort_key`, chaque finding enrichi de `_bucket`, `_summary`, `_file`, `_src` et `_progress` ;
  - `progress_columns` : liste de clés ;
  - `activity` : les 200 dernières lignes de `activity.jsonl` ;
  - `commands` : `{pending: [...], done: [...]}`, au plus 50 chacun, rempli par la tâche 3 (liste vide ici).
- Produit aussi `LEVEL_STAGES: dict[str, list[str]]`, `STAGE_CODES: dict[str, str]`, `STAGE_NAMES: dict[str, str]`, `progress(f: dict) -> str` et `assign_files(findings: list) -> None`.
- Consomme : `render.load_json`, `load_findings`, `bucket`, `stats`, `summary`, `sort_key`, `ENUM_LABELS`, `LEVEL_BANNERS`, `duration`.

Règles que le constructeur ne peut pas deviner :
- **Statut de Triage :** `done` si `campaign.json` a `level`, sinon `running`.
- **Statut des autres étapes :** la valeur de `state["stages"]`. Une étape absente vaut `pending`. Valeurs possibles : `pending`, `running`, `done`, `failed`, `skipped`.
- **Niveau inconnu :** les étapes sont les clés de `state["stages"]` dans leur ordre.
- **`progress(f)`**, dans cet ordre de priorité :
  - `rejected` si `bucket(f) == "REJECTED"` ;
  - `fixed` si `patch_status` vaut `VERIFIED_SECURE` ou `MITIGATION_PROPOSED` ;
  - `reproduced` si `repro_status == "reproduced"` ;
  - `evaluated` si `production_viability` est présent ;
  - `reviewed` si `reasoning` est présent ;
  - `found` sinon.
- **`progress_columns`** : Light = `["found", "reviewed", "fixed"]`, sinon `["found", "reviewed", "evaluated", "reproduced", "fixed"]`.
- **`listening`**, dans cet ordre :
  - `"none"` si `finished` ou `stopped` ;
  - `"waiting"` si `waiting.json` existe ;
  - `"working"` si une étape est `running` ou si Triage est `running` ;
  - `"none"` sinon.
- **`stale`** vaut vrai si `listening == "working"` et que le fichier surveillé le plus récent date de plus de 1200 s.
- **Durées** (`duration_s`, `started_at`) : lues dans `activity.jsonl`, d'après les événements `kind == "stage"` de la tâche 2 : dernier passage à `running`, puis passage à `done`, `failed` ou `skipped`. Sinon `None`.
- **`notes` d'une étape** : les entrées de `state["notes"]` qui contiennent la clé de l'étape.

- [ ] **Step 1 : écrire les tests qui échouent** dans `test_snapshot.py`, avec un helper `audit(tmp, campaign, state=None, findings=(), waiting=None, activity=())` qui écrit les fichiers.
  - `test_snapshot_triage_seul` : `campaign={"repo": "/x/demo"}`, sans `state.json`. Attendus : `stages[0] == {"key": "triage", "code": "TRI", ...}` avec `status "running"`, `listening == "working"`, `findings == []`.
  - `test_snapshot_sharp_en_cours` : Sharp, `state.stages` avec `architecture done` et `review running`. Attendus : `[s["key"] for s in stages] == ["triage"] + LEVEL_STAGES["Sharp"]`, review `running`, critic `pending`, `listening == "working"`.
  - `test_snapshot_failed_et_waiting` : `waiting={"kind": "failed", "stage": "plan", "reason": "x"}`. Attendus : `listening == "waiting"` et `snap["waiting"]["stage"] == "plan"`.
  - `test_snapshot_fini` : `state.finished = true`. Attendu : `listening == "none"`.
  - `test_progress_colonnes` : un finding par statut de `progress`, et la table d'attendus ci-dessus. En Light, `progress_columns == ["found", "reviewed", "fixed"]`.
  - `test_overkill_tour_2` : `state.round == 2`. Attendus : `meta.round == 2` et 15 étapes.
  - `test_src_et_file` : deux fichiers `a.json` et `b.json` avec le même `id: "x"`. Attendus : `_src` vaut `{"a", "b"}`, et les `_file` sont distincts.
  - `test_durees` : `activity` contient `{"kind": "stage", "stage": "plan", "to": "running", "at": "2026-10-22T14:00:00"}` puis `"to": "done"` à `14:04:00`. Attendu : `duration_s == 240`.
  - `test_stale` : étape `running` et mtime des fichiers reculé de 1300 s (`os.utime`). Attendu : `stale is True`.
- [ ] **Step 2 :** `python3 S/test_snapshot.py` échoue (`ModuleNotFoundError: snapshot`).
- [ ] **Step 3 : implémenter `snapshot.py`.** `render()` appelle désormais `build_snapshot(audit_dir, mode="final")` pour son payload. Il continue d'écrire `README.md` et `patches/` à partir des mêmes findings, avec `_file` calculé par `assign_files`. Le gabarit reste l'actuel `TEMPLATE` à ce stade.
- [ ] **Step 4 :** `python3 S/test_snapshot.py && python3 S/test_render.py` affichent tous deux `OK`.
- [ ] **Step 5 : commit** `feat(osho-mantis): snapshot.py, état complet de l'audit pour le dashboard`.

### Task 2 : événements d'activité

**Files :**
- Modify : `S/snapshot.py`
- Test : `S/test_snapshot.py`

**Interfaces :**
- Produit `diff_events(prev: dict | None, cur: dict, at: str) -> list[dict]`. Chaque événement est `{at, kind, text, ...}` :
  - `kind: "stage"` : `{stage, from, to}`, avec `duration_s` quand `to` vaut `done` ;
  - `kind: "finding_new"` : `{finding: _src, bucket}` ;
  - `kind: "finding_progress"` : `{finding, from, to}` ;
  - `kind: "waiting"` : `{waiting_kind}` à l'apparition de `waiting.json` ;
  - `kind: "command"` : `{id, action, result}` à chaque nouvel accusé.
- Produit `append_activity(audit_dir: Path, events: list[dict]) -> None`, qui ajoute à `activity.jsonl`, une ligne JSON par événement.
- Produit `read_snapshot_safe(audit_dir, prev, mode="live") -> dict`. Elle renvoie `prev` inchangé si un JSON surveillé (`state.json`, `campaign.json`, `waiting.json`) est présent mais illisible.

Textes (`text`), en français et sans tiret cadratin :
- `"Étape <name> démarrée"` ;
- `"Étape <name> terminée en <m> min"` ;
- `"Étape <name> en échec"` ;
- `"Étape <name> sautée"` ;
- `"Nouveau finding : <title>"` ;
- `"<title> : <colonne d'avant> → <colonne d'après>"`, avec les libellés de colonnes Trouvées, Revues, Évaluées, Reproduites, Corrigées et Écartés ;
- `"En attente de ta réponse"` ;
- `"Action <action> appliquée"` ou `"Action <action> refusée : <reason>"`.

Avec `prev=None`, la fonction ne renvoie aucun événement : le premier snapshot sert de référence.

- [ ] **Step 1 : tests qui échouent.**
  - `test_diff_etape` : review passe de `pending` à `running`, puis à `done`. Attendus : deux événements `kind "stage"`, et le texte du second commence par `"Étape Review terminée"`.
  - `test_diff_finding` : un nouveau finding apparaît, puis reçoit `reasoning`. Attendus : `finding_new` puis `finding_progress` de `found` à `reviewed`.
  - `test_diff_premier_snapshot` : `diff_events(None, snap, at) == []`.
  - `test_json_tronque_ignore` : on écrit `'{"stages": {"rev'` dans `state.json`. Attendus : `read_snapshot_safe(d, prev)` renvoie `prev` (`is`), et `diff_events(prev, prev, at) == []`.
  - `test_textes_sans_cadratin` : aucun `text` ne contient `—`.
- [ ] **Step 2 :** le test échoue (fonctions absentes).
- [ ] **Step 3 :** implémenter les fonctions.
- [ ] **Step 4 :** `python3 S/test_snapshot.py` affiche `OK`.
- [ ] **Step 5 : commit** `feat(osho-mantis): journal d'activité déduit des snapshots`.

### Task 3 : `commands.py`, la file d'actions

**Files :**
- Create : `S/commands.py`
- Modify : `S/snapshot.py`, où `build_snapshot` remplit `commands` avec `pending()` et `done()`
- Test : `S/test_commands.py`

**Interfaces :**
- `ACTIONS = {"pause", "resume", "stop", "retry", "answer", "false_positive", "prioritize_repro"}`.
- `validate(cmd: dict, snap: dict) -> str | None` renvoie `None` si la commande est valide, sinon une raison en français. Les règles d'acceptation sont celles de la table du §3.1 de la spec :
  - `retry` exige `stage` avec un statut `failed` ;
  - `answer` exige `waiting.kind == "question"`, `question == waiting.question` et `value` présente parmi `waiting.options[].value` ;
  - `false_positive` exige un `finding` égal à un `_src` existant dont `_bucket` n'est pas `REJECTED` ;
  - `prioritize_repro` exige que reproduce soit dans les étapes, ne soit pas `done`, et que le finding ne soit pas écarté ;
  - `pause` exige que l'audit tourne et ne soit pas en pause ; `resume` exige `meta.paused` ; `stop` est refusé si `finished` ;
  - toute valeur de `finding` ou `stage` contenant `/`, `\` ou `..` est refusée, comme tout JSON sérialisé de plus de 1024 octets.
- `append(audit_dir, cmd: dict, source: str) -> dict` ajoute `id` (`secrets.token_hex(8)`), `at` et `source`, écrit une ligne dans `commands.jsonl` et renvoie la commande complète.
- `pending(audit_dir) -> list[dict]` renvoie, dans l'ordre, les commandes dont l'`id` est absent de `commands-done.jsonl`.
- `done(audit_dir) -> list[dict]` renvoie le contenu de `commands-done.jsonl`.
- `ack(audit_dir, cmd_id: str, result: str, reason: str | None = None) -> None`. `result` vaut `applied` ou `refused`. Rien n'est écrit si l'`id` est déjà accusé.
- `apply(audit_dir, cmd_id) -> dict`. Elle ne traite que `false_positive` et `prioritize_repro`. Elle revalide d'abord la commande contre un `build_snapshot` frais ; si la commande n'est plus valide, elle l'accuse `refused`. Sinon :
  - `false_positive` réécrit le finding de façon atomique (tmp puis `os.replace`) avec `status: "FALSE_POSITIVE"` et `user_override: {action, at}` ;
  - `prioritize_repro` ajoute l'id à `state.json["force_repro"]`, sans doublon ;
  - puis elle accuse `applied` et renvoie l'accusé.
  - Une commande déjà accusée renvoie son accusé existant sans rien réécrire. Une autre action lève `ValueError("à traiter par mantis-run")`.

- [ ] **Step 1 : tests qui échouent.**
  - `test_valide_chaque_action` : une commande valide par action, chacune sur un snapshot préparé. Attendu : `validate(...) is None`.
  - `test_refus` : chacun de ces cas renvoie une chaîne non vide :
    - action inconnue ;
    - `finding: "../x"` ;
    - finding absent ;
    - `retry` sur une étape `done` ;
    - `answer` avec une `value` hors des options ;
    - commande de plus de 1024 octets ;
    - `prioritize_repro` en Light.
  - `test_pending_ack` : on ajoute 2 commandes et on accuse la première. Attendus : `pending` ne renvoie que la seconde, et un second `ack` du même id n'ajoute rien.
  - `test_apply_false_positive` : après `apply`, le fichier du finding a `status == "FALSE_POSITIVE"` et contient `user_override`, et `pending == []`.
  - `test_apply_idempotent` : deux `apply` du même id donnent une seule ligne pour cet id dans `commands-done.jsonl`, et le `user_override.at` n'est pas réécrit.
  - `test_apply_devenue_invalide` : on écarte le finding entre `append` et `apply`. Attendu : un accusé `refused`.
- [ ] **Step 2 :** le test échoue.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** `python3 S/test_commands.py && python3 S/test_snapshot.py` affichent `OK`.
- [ ] **Step 5 : commit** `feat(osho-mantis): file de commandes validée du dashboard`.

### Task 4 : `dashboard.py`, serveur et ligne de commande

**Files :**
- Create : `S/dashboard.py`
- Test : `S/test_dashboard.py`

**Interfaces :**
- Ligne de commande :
  - `python3 dashboard.py serve <AUDIT>` affiche une ligne JSON `{"url": ..., "reused": bool}` et rend la main en moins de 5 s ;
  - `python3 dashboard.py stop <AUDIT>` ;
  - `python3 dashboard.py command <AUDIT> '<json>'` affiche la commande ajoutée, avec `source: "terminal"` et sans contrôle de `listening` ; si `validate` échoue, elle sort avec le code 2 et affiche la raison ;
  - `python3 dashboard.py pending <AUDIT>` affiche une commande en attente par ligne, et rien s'il n'y en a pas ;
  - `python3 dashboard.py apply <AUDIT> <id>` ;
  - `python3 dashboard.py ack <AUDIT> <id> applied|refused [reason]` ;
  - `python3 dashboard.py _run <AUDIT>` est le processus serveur, réservé à l'usage interne.
- `serve` lance `_run` avec `subprocess.Popen(..., start_new_session=True)`, sorties redirigées vers `<AUDIT>/server.log`, puis attend `server.json`.
- Réutilisation : si `server.json` existe, que son pid est vivant (`os.kill(pid, 0)`) et que `GET /health?key=` répond 200, `serve` affiche son URL avec `reused: true`. Sinon, il supprime le fichier et relance un serveur.
- `server.json` contient `{pid, port, url, key, started_at}`. L'URL a la forme `http://127.0.0.1:<port>/?key=<key>`.
- Routes : `GET /`, `GET /health`, `GET /events` (SSE), `POST /command`.
  - `GET /` sert `dashboard.html` (tâche 5) en remplaçant `__DATA__` par `safe_json(snapshot)`. Tant que la tâche 5 n'est pas faite, une page minimale qui contient `__DATA__` suffit.
  - `GET /events` envoie `event: snapshot` avec `data: <json>` à la connexion puis à chaque changement, et `event: ping` avec `data: <iso>` toutes les 10 s.
  - `POST /command` répond :
    - 403 si la clé, l'`Origin` ou le `Host` sont mauvais ;
    - 409 avec `{"error": "Aucune session active : relance /mantis-run"}` si `listening == "none"` ;
    - 400 avec `{"error": raison}` si `validate` échoue ;
    - sinon 200 avec la commande complète.
- Boucle de surveillance (thread, toutes les 0,5 s) :
  - la signature est l'ensemble des `(chemin, mtime_ns, taille)` de `state.json`, `campaign.json`, `waiting.json`, `commands.jsonl`, `commands-done.jsonl` et `workspace/findings/*.json` ;
  - si elle change : `read_snapshot_safe`, puis `diff_events` et `append_activity`, puis un nouveau snapshot diffusé à tous les clients.
- Arrêt automatique, puis suppression de `server.json` :
  - 1800 s après que `finished` ou `stopped` est vu ;
  - ou après 4 h sans changement de signature et sans client connecté ;
  - `SIGTERM` déclenche le même arrêt propre.

- [ ] **Step 1 : tests qui échouent.** Chaque test lance un vrai serveur sur un audit temporaire et l'arrête dans un `finally`.
  - `test_serve_et_reutilise` : un second `serve` renvoie `reused: true` et la même URL.
  - `test_serve_pid_mort` : on écrit à la main un `server.json` avec `pid: 999999`. Attendus : `serve` démarre un nouveau serveur avec `reused: false`, et `server.json.pid` change.
  - `test_auth` : `GET /` sans clé donne 403. `POST /command` avec la clé mais avec `Origin: http://evil` donne 403, et avec `Host: evil:port` aussi 403.
  - `test_post_409_sans_session` : audit avec `finished: true`. Attendu : POST valide → 409.
  - `test_post_400_puis_200` : étape `running`. Attendus : `{"action": "nope"}` → 400 ; `{"action": "pause"}` → 200, et `dashboard.py pending` affiche cette commande.
  - `test_sse_snapshot_apres_changement` : on lit le premier `event: snapshot`, on réécrit `state.json` avec review `done`, puis on lit le snapshot suivant en moins de 3 s. Attendus : review vaut `done`, et `activity.jsonl` contient un événement `stage`.
  - `test_sse_xss_inerte` : un finding titré `</script><img src=x onerror=alert(1)>`. Attendus : le corps de `GET /` ne contient ni `</script><img` ni `<img src=x`.
  - `test_stop` : après `stop`, `server.json` n'existe plus et le port refuse la connexion.
  - `test_command_terminal` : `dashboard.py command` réussit même avec `listening == "none"`. Avec une commande invalide, il sort avec le code 2.
- [ ] **Step 2 :** le test échoue.
- [ ] **Step 3 :** implémenter (`http.server.ThreadingHTTPServer`, `BaseHTTPRequestHandler`, une file par client SSE).
- [ ] **Step 4 :** `python3 S/test_dashboard.py` affiche `OK` en moins de 30 s.
- [ ] **Step 5 : commit** `feat(osho-mantis): serveur local du dashboard live (SSE + commandes)`.

### Task 5 : gabarit, structure, bannière, kanban et fiche

**Files :**
- Create : `S/dashboard.html`, le gabarit unique. Il contient une seule balise `<script>` sans attribut (le code) et une seule balise `<script id="data" type="application/json">__DATA__</script>`.
- Modify : `S/render.py`. On supprime `TEMPLATE`, et `render()` lit `Path(__file__).with_name("dashboard.html")`.
- Modify : `S/dashboard.py`, dont `GET /` sert ce gabarit.
- Modify : `S/test_render.py`, où l'on réécrit `test_theme_clair` en `test_themes_horizon` ; les autres tests restent inchangés.

**Interfaces :**
- Consomme le snapshot de la tâche 1 (`window.D = JSON.parse(...)`).
- Produit des fonctions JS de niveau supérieur, réutilisées par les tâches 6 et 7 :
  - `render(D)` (re)dessine toute la page à partir d'un snapshot, sans perdre le filtre, la vue choisie, la fiche ouverte ni son défilement ;
  - `el(tag, attrs, ...kids)` ;
  - `openPeek(f)` et `closePeek()` ;
  - `sendCommand(cmd)`, qui ne fait rien en mode `final` (la tâche 7 la remplit) ;
  - `renderPipeline(D)`, qui ne fait rien ici (la tâche 6 la remplit).
- Conserve sous ces noms exacts, pour les tests existants : `function leadOf(desc)`, `function matches(f, q)`, `function findingForHash(findings, hash)`, `location.hash = f._file`, `hashchange`, `history.replaceState`, `D.labels` et `reproduce_done`.
- Identifiants DOM :
  - `#topbar`, `#conn`, `#theme-toggle` ;
  - `#banner` et `#kpis`, avec 4 `.kpi` ;
  - `#waiting-banner`, `#pipeline`, `#filter` ;
  - `#kb-view-toggle`, avec `data-view` valant `severity` ou `progress` ;
  - `#board`, `#actions`, `#activity` ;
  - `#peek` (`role="dialog"`, `aria-modal="true"`) et `#live-region` (`aria-live="polite"`).

Contenu, d'après la spec §2 et la maquette :
- La barre du haut affiche le logo « M » et le fil d'Ariane `Mantis / <repo> / <audit>`.
- La bannière à diagonale (`clip-path: polygon(14% 0,100% 0,100% 100%,0 100%)`) affiche :
  - le titre `Audit <niveau>, <étape en cours> en cours`, ou `terminé`, `en pause`, `arrêté` ;
  - le sous-titre avec le début, le tour et le temps écoulé ;
  - 4 KPI en mono : findings, critiques ou hautes, reproduits, patchs vérifiés. Ils affichent `n/a` avec un `title` quand la stat ne s'applique pas (reproduits et patchs vérifiés quand `reproduce_done` est faux et que le niveau est Light).
- Le kanban a la vue `severity` par défaut, avec les colonnes Critical, High, Medium, Low et Écartés (`<details>` repliée), et la vue `progress`, avec `D.progress_columns` plus Écartés. La vue choisie est mémorisée dans `localStorage["mantis.kbView"]`.
- Une carte (`<button class="fc">`) contient la pastille de sévérité (texte et couleur), le titre, `code_paths` en mono et les puces Confirmé, Reproduit et Patch vérifié.
- La fiche s'ouvre en superposition centrée (`#peek`, largeur `min(860px, 100%)`, fond assombri). Elle contient, dans l'ordre :
  - la barre : `_src`, le fichier, « Ouvrir en pleine page » (`#<_file>&full`) et ✕ ;
  - la pastille de sévérité et le titre ;
  - la frise des étapes traversées (déduite de `_progress` et des champs) ;
  - les propriétés ;
  - les sections du panneau actuel : problème avec `leadOf`, impact, preuve, correctif avec diff coloré, historique ;
  - les boutons « Marquer faux positif », « Prioriser la reproduction » et « Copier le diff », qui appellent `sendCommand` et sont masqués en mode `final`.
- Comportement de la fiche : Échap, clic hors fiche ou ✕ la ferment ; le focus est piégé dedans puis rendu à la carte.
- Thème : `data-theme="dark"` par défaut. Au premier chargement, la page suit `prefers-color-scheme` ; ensuite c'est le choix mémorisé dans `localStorage["mantis.theme"]` qui compte. Les deux jeux de jetons sont ceux de la spec §6.

- [ ] **Step 1 : test qui échoue.** On réécrit `test_theme_clair` en `test_themes_horizon` :
  - `--bg:#0b0d14` et `--bg:#eff1f5` sont tous deux dans le HTML, ainsi que `--primary:#7ea6ff`, `--primary:#0050d7` et `data-theme` ;
  - `"innerHTML"` n'apparaît pas dans le JS ;
  - `"—"` n'apparaît pas dans le HTML ;
  - les identifiants DOM listés plus haut sont tous présents.
- [ ] **Step 2 :** `python3 S/test_render.py` échoue sur `test_themes_horizon`.
- [ ] **Step 3 :** écrire `dashboard.html` et brancher `render.py` et `dashboard.py`.
- [ ] **Step 4 :** `python3 S/test_render.py && python3 S/test_dashboard.py` affichent `OK` (y compris `node --check`).
- [ ] **Step 5 : vérification visuelle.** On rend l'audit fictif de `test_render.audit()` puis on fait une capture : `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --screenshot=/tmp/mantis-t5.png --window-size=1440,1000 file://<audit>/dashboard.html`. Lire l'image et la comparer à la maquette : la bannière, les 4 KPI, le kanban par sévérité et le thème sombre doivent y être.
- [ ] **Step 6 : commit** `feat(osho-mantis): gabarit Horizon du dashboard (bannière, kanban 2 vues, fiche)`.

### Task 6 : pipeline Réseau et Matrice

**Files :**
- Modify : `S/dashboard.html`
- Test : `S/test_render.py`

**Interfaces :**
- Consomme `D.stages`, `D.current`, `D.meta` (`round`, `audit_age_s`) et `D.activity`.
- Remplit `renderPipeline(D)`. Produit aussi `function stageView(stored)`, qui renvoie `"reseau"` ou `"matrice"` (défaut `"reseau"`, toute valeur inconnue donnant `"reseau"`), et `openStage(key)`. La valeur passée à `stageView` est `new URLSearchParams(location.search).get("view")` si ce paramètre est présent, sinon `localStorage["mantis.stageView"]`.

Contenu, d'après la spec §2.3 et la maquette :
- **Sélecteur :** deux boutons-icônes empilés verticalement à gauche du pipeline (`#view-reseau`, `#view-matrice`), avec `aria-label` « Vue réseau » et « Vue matrice » et `aria-pressed`. Le choix est mémorisé dans `localStorage["mantis.stageView"]`.
- **Réseau :**
  - des nœuds ronds de 30 px portant le code, reliés par des fils, sur une grille de 24 px ;
  - nœud `done` en succès, `running` en accent avec une pulsation, `skipped` en pointillé, `failed` en erreur ;
  - fil entrant de l'étape active parcouru par un flux ;
  - dérivation `W1…Wn` avant l'étape active quand `D.current.workers > 1` ;
  - pied : `T+ HH:MM:SS`, `Étape i / n`, workers actifs et modèle.
- **Matrice :**
  - une case par étape (code de 15 px en mono, nom, état, durée) ;
  - case active encadrée de coins et balayée par une ligne ;
  - `skipped` hachuré et barré ;
  - bandeau `Opération Mantis`, niveau, tour et T+ ;
  - les 3 derniers événements de `D.activity` en bas.
- **Overkill :** `Tour <n> / 3` est affiché dans les deux vues.
- **Clic sur une étape :** ouvre un panneau dans `#peek`, réutilisé, qui affiche l'état, le début, la durée et les notes. Si l'étape est `failed`, il affiche aussi la raison (`D.waiting.reason` quand `D.waiting.stage == key`) et les boutons « Relancer » (`sendCommand({action: "retry", stage: key})`) et « Arrêter ».
- Sous 1024 px, le pipeline défile horizontalement.

- [ ] **Step 1 : tests qui échouent** dans `test_render.py.`
  - `test_pipeline_hooks` : `#view-reseau`, `#view-matrice` et `aria-pressed` sont présents.
  - `test_stage_view` : `stageView` est extraite par regex et exécutée sous node ; attendus : `stageView(null) === "reseau"`, `stageView("matrice") === "matrice"`, `stageView("x") === "reseau"`.
  - `test_reduced_motion` : `prefers-reduced-motion` est présent dans le CSS.
- [ ] **Step 2 :** les tests échouent.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** `python3 S/test_render.py` affiche `OK`.
- [ ] **Step 5 : vérification visuelle.** Deux captures Chrome headless d'un audit Sharp fictif avec review `running`. Pour passer d'une vue à l'autre sans clic, ouvrir un `file://` dont le `localStorage` est vide affiche Réseau ; pour la Matrice, ajouter `?view=matrice` à l'URL. Comparer les deux captures à la maquette.
- [ ] **Step 6 : commit** `feat(osho-mantis): pipeline Réseau et Matrice`.

### Task 7 : comportement live dans la page

**Files :**
- Modify : `S/dashboard.html`
- Test : `S/test_render.py` et `S/test_dashboard.py`

**Interfaces :**
- Consomme `GET /events` et `POST /command` (tâche 4), ainsi que `D.listening`, `D.stale`, `D.waiting` et `D.commands` (tâches 1 et 3).
- Remplit `sendCommand(cmd)` : `fetch("/command", {method: "POST", credentials: "same-origin", body: JSON.stringify(cmd)})`. Une erreur 400 ou 409 s'affiche à côté du bouton.
- Produit `function connLabel(lastMsgAgeS, mode)`, qui renvoie :
  - `"En direct, mis à jour il y a N s"` si l'âge est inférieur à 15 ;
  - `"Reconnexion…"` s'il est inférieur à 60 ;
  - `"Hors ligne, données du HH:MM"` sinon, ou toujours en mode `final`.

Comportement, d'après la spec §2, §3 et §3.5 :
- En mode `live`, un `EventSource("/events")`. Chaque `snapshot` appelle `render(D)` ; chaque `ping` met à jour l'âge du dernier message ; `#conn` est rafraîchi chaque seconde.
- En mode `final` : pas d'`EventSource`, `#actions` est masqué, et `#conn` affiche « Hors ligne ».
- **Tuile `#actions` :**
  - l'état de session est l'un de « Claude travaille », « Claude attend ta réponse » ou « Aucune session active : relance /mantis-run » ;
  - si `D.stale`, on ajoute « aucune activité depuis 20 min » ;
  - les boutons dépendent de l'état : Mettre en pause ou Reprendre, Arrêter, Relancer l'étape ;
  - tous sont `disabled` quand `listening == "none"`, avec l'explication.
- **Commandes en attente :** chacune affiche « en attente, prise en compte à la fin du lot en cours » en gris, puis « appliquée » ou « refusée : raison » quand elle apparaît dans `D.commands.done`.
- **`#waiting-banner` :** visible quand `D.waiting.kind == "question"`. Il affiche la question et un bouton par option, qui envoie `{action: "answer", question, value}`.
- **`#activity` :** les 50 derniers événements, le plus récent en haut, avec un lien « voir tout » qui déplie le reste.
- **`#live-region` :** annonce le texte de chaque nouvel événement `kind "stage"`.
- **Animations :**
  - une carte qui change de colonne glisse vers sa nouvelle place (technique FLIP : mesurer avant et après `render`, puis animer `transform` en 220 ms) ;
  - une carte nouvelle apparaît en fondu ;
  - aucune animation sous `prefers-reduced-motion`.
- La fiche ouverte se met à jour sans perdre son défilement.

- [ ] **Step 1 : tests qui échouent.**
  - `test_conn_label` (node) : `connLabel(3, "live")` commence par `"En direct"`, `connLabel(30, "live") === "Reconnexion…"`, et `connLabel(90, "live")` comme `connLabel(0, "final")` commencent par `"Hors ligne"`.
  - `test_final_sans_eventsource` : dans `test_render`, le payload a `mode == "final"`, et le JS conditionne `new EventSource` à `D.mode === "live"`. Le test vérifie par regex la présence de `D.mode === "live"`.
  - `test_page_live_servie` : dans `test_dashboard`, `GET /` renvoie une page dont le snapshot inclus a `mode == "live"`.
- [ ] **Step 2 :** les tests échouent.
- [ ] **Step 3 :** implémenter.
- [ ] **Step 4 :** `python3 S/test_render.py && python3 S/test_dashboard.py` affichent `OK`.
- [ ] **Step 5 : vérification dans le navigateur.**
  1. Lancer `dashboard.py serve` sur un audit fictif Sharp avec review `running`, puis ouvrir l'URL.
  2. Dans un autre terminal, passer review à `done` dans `state.json`. La page doit changer en moins de 2 s et le journal afficher « Étape Review terminée ».
  3. Cliquer sur « Mettre en pause » : `dashboard.py pending` doit afficher la commande.
  4. `dashboard.py ack <id> applied` : la page doit afficher « appliquée ».
  5. Passer `finished: true` : les boutons se grisent.
- [ ] **Step 6 : commit** `feat(osho-mantis): dashboard en direct (SSE, actions, attente, journal)`.

### Task 8 : brancher les skills

**Files :**
- Modify : `plugins/osho-mantis/skills/mantis-triage/SKILL.md`
- Modify : `plugins/osho-mantis/skills/mantis-run/SKILL.md`
- Modify : `plugins/osho-mantis/.claude-plugin/plugin.json`, version `0.1.0` → `0.2.0` ; la description mentionne « live dashboard »
- Modify : `.claude-plugin/marketplace.json`, description d'osho-mantis alignée

**Interfaces :**
- Consomme la ligne de commande de `dashboard.py` (tâche 4). Les chemins passent par les variables existantes `R="${CLAUDE_PLUGIN_ROOT}/skills/mantis-run/scripts"`, que triage doit aussi définir.

Changements, d'après la spec §1.1, §3.3, §3.4 et §4 :

- **mantis-triage**
  - Étape 3 : après `mkdir "$AUDIT/workspace"`, lancer `python3 "$R/dashboard.py" serve "$AUDIT"`, puis `open` sur l'URL et l'afficher en secours dans le terminal.
  - Étape 6 : on remplace AskUserQuestion par un message texte qui reprend les 4 options (mêmes libellés, ordre, « (Recommandé) » et descriptions). En parallèle, on écrit `waiting.json` avec `{kind: "question", question: "volume", options: [{value, label, description}], since}` et on lance `Monitor`, dont la boucle se termine dès qu'une nouvelle commande apparaît : `until [ -n "$(python3 "$R/dashboard.py" pending "$AUDIT")" ]; do sleep 2; done`. Puis on termine le tour.
  - Une réponse de la page (`answer`) ou du terminal est acceptée par nom de niveau (casse ignorée) ou par numéro de 1 à 4 ; sinon la question est reposée. Une réponse tapée est d'abord enregistrée avec `dashboard.py command`. On termine par `ack`, puis on supprime `waiting.json`.
  - L'étape 2 (versionnement) ne change pas.
- **mantis-run**
  - §1 : après le contrôle hostile, `dashboard.py serve "$AUDIT"`, puis `open` si `reused` vaut false.
  - §3 :
    - avant une étape, mettre `"running"` au lieu de `"pending"` ;
    - écrire `current` à chaque lot et le supprimer après l'étape ;
    - reproduce inclut aussi les ids de `state.json["force_repro"]` qui ne sont pas écartés.
  - Nouveau « Point de contrôle », à exécuter avant chaque étape, après chaque retour de lot et entre deux findings de patch Sharp+ :
    - `dashboard.py pending`, puis traiter chaque commande dans l'ordre ;
    - `false_positive` et `prioritize_repro` passent par `dashboard.py apply` ;
    - `pause` : mettre `paused: true`, puis attendre ;
    - `stop` : remettre l'étape en cours à `pending`, mettre `stopped: true`, faire Finish 1, 2 et 4 sans `finished`, puis terminer ;
    - `resume`, `retry` et `answer` hors attente : `ack refused` avec une raison ;
    - chaque commande se termine par `ack`.
  - Nouveau « Attendre l'utilisateur » (pause, échec, question) :
    - écrire `waiting.json`, poser la question en texte simple, lancer Monitor (même boucle) et terminer le tour ;
    - au réveil, refaire le point de contrôle ;
    - à l'expiration de Monitor, relancer la surveillance si `server.json` existe et que son pid est vivant ; sinon supprimer `waiting.json`, dire « relance `/mantis-run` » et terminer.
  - La règle « Failure » devient : mettre l'étape à `failed`, écrire `waiting.json` avec `{kind: "failed", stage, reason}` (la raison en 2 lignes), puis passer par « Attendre l'utilisateur ».
  - Ajouter un paragraphe « Depuis le terminal » : une demande en langage naturel (pause, faux positif…) passe par `dashboard.py command`, puis par le point de contrôle.
  - §4 Finish : l'étape 4 devient `python3 "$R/render.py" "$AUDIT"`, sans `open`. Le rapport final indique le chemin de `dashboard.html`.

- [ ] **Step 1 :** écrire les modifications.
- [ ] **Step 2 : relecture de cohérence.** Chaque sous-commande `dashboard.py` citée dans les SKILL.md existe : `python3 S/dashboard.py --help` les liste toutes. Aucun `AskUserQuestion` ne subsiste à l'étape 6 de triage. `grep -n '"pending"' mantis-run/SKILL.md` ne montre plus la pose avant étape.
- [ ] **Step 3 :** `python3 S/test_snapshot.py && python3 S/test_commands.py && python3 S/test_dashboard.py && python3 S/test_render.py` affichent tous `OK`.
- [ ] **Step 4 : commit** `feat(osho-mantis): triage et run pilotés depuis le dashboard live (0.2.0)`.

### Task 9 : vérification de bout en bout (contrôleur, avant fusion)

Pas de code. Lancer un audit **Light** réel sur un petit repo de test, avec la page ouverte du début à la fin. Le repo est créé avec `osho-core:donnees-fictives` ou est un repo jouet local, jamais un repo client.

Points à cocher :
1. Le dashboard s'ouvre au triage, et la question de niveau répond depuis la page.
2. Pause puis reprise depuis la page ; pause depuis le terminal.
3. Faux positif depuis la fiche : la carte passe dans Écartés.
4. Échec simulé (renommer temporairement le dossier Mantis d'une étape) puis « Relancer ».
5. Fin d'audit : la page affiche « Audit terminé », et le `dashboard.html` final s'ouvre hors ligne avec le même design.
