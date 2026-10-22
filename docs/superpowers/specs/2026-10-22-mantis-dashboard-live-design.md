# osho-mantis : dashboard live, design

Date : 2026-10-22 · Plugin : osho-mantis · Branche : `feat/mantis-dash`
Maquette de référence : [assets/2026-10-22-mantis-dashboard-maquette.html](./assets/2026-10-22-mantis-dashboard-maquette.html) (à ouvrir dans un navigateur)
Remplace le §1.1 « Dashboard en direct » de [2026-10-07-osho-mantis-0.2-design.md](./2026-10-07-osho-mantis-0.2-design.md), jamais implémenté.

## Intention

Aujourd'hui, `dashboard.html` n'est produit qu'à la fin de l'audit (`mantis-run` §4.4). Pendant un audit de 30 min à plusieurs heures, l'utilisateur n'a que le terminal.

On veut un **poste de pilotage** ouvert dans le navigateur du début à la fin :

- il suit **toutes les étapes**, triage compris, et chaque vulnérabilité **en temps réel** ;
- il permet d'**agir depuis la page** ;
- le **terminal reste un canal équivalent** : tout ce qu'on fait sur la page se fait aussi en tapant dans la session Claude, et la page peut ne servir qu'à regarder.

Le modèle est le companion visuel de Superpowers : un petit serveur local surveille des fichiers, pousse les changements au navigateur et enregistre les clics dans un fichier que Claude relit.

## Objectifs

1. Le dashboard s'ouvre dès le triage et se met à jour seul, en moins de 2 s après chaque écriture d'un fichier d'état.
2. L'utilisateur peut, depuis la page **ou** le terminal : mettre en pause, reprendre, arrêter, relancer une étape en échec, répondre aux questions de l'audit (versionnement, niveau), marquer un finding faux positif, prioriser la reproduction d'un finding.
3. La même page sert de rapport final : à la fin, `dashboard.html` est un fichier autonome (hors ligne, sans serveur) avec le même design.
4. Le design reprend Horizon OS (voir « Design ») et le pipeline existe en deux vues, **Réseau** et **Matrice**.

## Non-objectifs

- Pas de lancement de Claude depuis la page. Si aucune session n'écoute (voir §3.5), les boutons d'action sont **grisés**, avec l'explication « Aucune session active : relance `/mantis-run` ». Le serveur refuse aussi le POST dans ce cas (409). Les actions restent possibles depuis le terminal, qui lance alors la session.
- Pas de correction du code audité dans ce lot : c'est le **lot 2** (voir §9).
- Pas d'interruption d'un agent en plein travail : une action prend effet au prochain point de contrôle (voir §3.3).
- Pas de multi-audit (pas de liste d'audits) ni d'accès distant : `127.0.0.1` uniquement.
- Pas de dépendance nouvelle : Python 3 stdlib côté serveur, HTML/CSS/JS sans build côté page.
- Pas de modification des SKILL.md de Mantis amont.

## Anti-objectifs (échec même si « ça marche »)

- La page affiche « En direct » alors qu'elle ne reçoit plus rien.
- Du contenu de finding (issu d'un repo potentiellement hostile) est interprété comme HTML ou script.
- Une action cliquée est perdue en silence, ou appliquée deux fois.
- Le serveur reste en vie indéfiniment après l'audit, ou écoute hors de `127.0.0.1`.
- Le coût en tokens de l'audit augmente sensiblement : le suivi live doit être calculé par le serveur, pas écrit par Claude.

## 1. Architecture

```
mantis-run / mantis-triage (Claude)          dashboard.py serve (Python stdlib)            Navigateur
  écrit state.json, campaign.json ───────▶  scrute AUDIT/ toutes les 500 ms  ──SSE──▶  page live
  agents écrivent workspace/findings/*.json  calcule un snapshot (fonctions de         (Réseau/Matrice,
                                             render.py) + diff → activity.jsonl         kanban, fiche)
  lit commands.jsonl aux points de    ◀────  POST /command → commands.jsonl     ◀────  clics
  contrôle, écrit commands-done.jsonl
```

### 1.1 Fichiers (tous sous `<AUDIT>/`)

| Fichier | Écrit par | Rôle |
|---|---|---|
| `state.json` | mantis-run (existant) | étapes, tour, notes ; **ajouts** ci-dessous |
| `campaign.json`, `inventory.json`, `triage.md` | triage (existant) | infos de la bannière et de l'étape Triage |
| `workspace/findings/*.json` | agents Mantis (existant) | kanban et fiches, mis à jour en direct |
| `activity.jsonl` | **serveur** | journal horodaté déduit des diffs entre snapshots |
| `commands.jsonl` | **serveur** (clic) ou **mantis-run** (commande tapée au terminal) | demandes d'action, une par ligne, avec `id` unique |
| `commands-done.jsonl` | mantis-run | accusé de chaque commande traitée : `{id, result: applied|refused, reason?, at}` |
| `waiting.json` | mantis-triage ou mantis-run | présent seulement quand Claude attend l'utilisateur : `{kind: paused\|failed\|question, stage?, reason?, question?, options?: [{value, label, description}], since}` ; supprimé dès que l'attente est levée |
| `server.json` | serveur | `{pid, port, url, key, started_at}` ; supprimé à l'arrêt |

Ajouts à `state.json` (écrits par mantis-run, coût minime) :

- valeur d'étape `"running"` (en plus de `pending`, `done`, `failed`, `skipped`), posée avant chaque étape à la place du `"pending"` actuel ;
- `current: {stage, batch: "2/3", workers: 3, model}`, réécrit à chaque lot d'agents, supprimé entre les étapes ;
- `paused: true` pendant une pause (l'attente elle-même est décrite dans `waiting.json`, utilisable aussi par le triage avant que `state.json` existe) ;
- `stopped: true` si l'utilisateur a arrêté l'audit.

Durées d'étapes et horodatages : déduits par le serveur des transitions observées, puis enregistrés dans `activity.jsonl`. Claude n'écrit pas d'horodatage. Si le serveur n'a pas vu une transition (par exemple s'il était arrêté), la durée affichée est « inconnue », sans erreur.

État du triage, sans `state.json` : le serveur le déduit des fichiers. Triage en cours tant que `campaign.json` n'a pas de `recommended` ; en attente du niveau si `waiting.json` porte la question Volume ; terminé dès que `campaign.json` a `level`. Le triage n'écrit pas de `state.json`, et la règle « pas de `state.json` → l'initialiser » de mantis-run §2.2 reste inchangée.

Identifiant d'un finding dans les commandes : le **nom de son fichier sans `.json`** (unique par construction), et non le champ `id` (deux fichiers peuvent porter le même). Le snapshot expose ce nom pour chaque finding (`_src`). Le lien profond `#<id>` garde le `_file` actuel (nom déjà dédoublonné de `patches/`).

### 1.2 `dashboard.py` (nouveau, à côté de `render.py`)

- `python3 dashboard.py serve <AUDIT>` lance le serveur en arrière-plan sur `127.0.0.1`, sur un port libre. Il écrit `server.json`, affiche l'URL avec une clé de session (`?key=…`, 32 octets aléatoires), puis rend la main. S'il trouve un `server.json` dont le pid est vivant et répond, il réutilise ce serveur et affiche son URL.
- `python3 dashboard.py stop <AUDIT>` arrête le serveur et supprime `server.json`.
- `python3 dashboard.py command <AUDIT> <json>` ajoute une commande à `commands.jsonl` avec la même validation que le POST. C'est le chemin utilisé quand l'utilisateur agit depuis le terminal, pour que les deux canaux passent par la même file.
- Le serveur reprend les fonctions de `render.py` (`load_findings`, `bucket`, `stats`, `label`…) pour construire le snapshot. Ce code n'est **pas dupliqué**.
- Routes :
  - `GET /` : la page ;
  - `GET /events` : flux SSE ; un snapshot complet à la connexion, puis un snapshot à chaque changement et un `ping` toutes les 10 s ;
  - `POST /command` : ajoute une commande.
- Toutes les routes exigent la clé (paramètre au premier chargement, puis cookie `HttpOnly; SameSite=Strict`). Le POST exige aussi un en-tête `Origin` égal à l'origine du serveur.
- Arrêt automatique 30 min après `finished: true` ou `stopped: true`, ou après 4 h sans aucun changement de fichier ni client connecté.

### 1.3 `render.py`

Reste le générateur des fichiers finaux (`README.md`, `patches/`, `dashboard.html`). Son `dashboard.html` devient **la même page** que la page live, avec le snapshot final inclus (`<script type="application/json">`, comme aujourd'hui) et sans connexion au serveur : pas d'indicateur « En direct », boutons d'action masqués. La page et ses styles vivent dans un seul gabarit partagé par les deux modes, par exemple `dashboard.html.tmpl`.

## 2. Ce que la page affiche

Ordre de haut en bas, comme le layout B de la maquette.

1. **Barre du haut** (48 px) : logo « M », fil d'Ariane `Mantis / <repo> / <audit>`, indicateur de connexion et bascule clair / sombre.
   - Connexion : « En direct, mis à jour il y a N s » quand des messages arrivent ; « Reconnexion… » sans message depuis 15 s ; « Hors ligne, données du HH:MM » après 60 s ou en mode fichier final.
2. **Bannière** à diagonale bicolore :
   - titre : `Audit <niveau>, <étape en cours> en cours`, ou `terminé`, `en pause`, `arrêté` ;
   - sous-titre : heure de début, tour, temps écoulé ;
   - **4 stats** en gros chiffres mono : findings, critiques ou hautes, reproduits, patchs vérifiés. Une stat qui ne s'applique pas au niveau (reproduits en Light) affiche « n/a » avec une infobulle, comme `stats()` aujourd'hui.
3. **Pipeline**, avec à sa gauche deux icônes empilées verticalement (Réseau, Matrice) pour changer de vue. Le choix est mémorisé dans `localStorage`.
   - Étapes affichées : `Triage` puis les étapes du niveau, dans l'ordre de la table de mantis-run. Celles qui ne sont pas au niveau n'apparaissent pas ; celles qui sont `skipped` apparaissent barrées ou hachurées.
   - **Réseau** : un nœud rond par étape, avec un code de 3 lettres (TRI, HIS, IDX, ARC, THR, PLN, RSC, DDP, REV, CRT, REP, CHN, PAT, CAL, RFL), reliés par des fils sur fond de grille. L'étape active émet une pulsation et son fil entrant est parcouru par un flux. Les étapes parallèles montrent leurs workers en dérivation (W1…Wn). Pied de vue : T+ écoulé, `étape i / n`, workers actifs, modèle.
   - **Matrice** : une case par étape (code, nom, état, durée) ; la case active est encadrée de coins et balayée par une ligne. Bandeau : `Opération Mantis`, niveau, tour, T+. Les 3 derniers événements du journal sont intégrés en bas.
   - Overkill : le numéro du tour (1 à 3) est affiché, et le pipeline montre les étapes du tour en cours.
   - Un clic sur une étape ouvre un panneau qui montre son état, ses durées, ses notes (`state.json.notes` qui la concernent) et, si elle est `failed`, la raison et le bouton « Relancer ».
4. **Kanban des vulnérabilités**, en pleine largeur.
   - Deux vues, avec un bouton pour basculer (choix mémorisé dans `localStorage`) :
     - **Sévérité**, par défaut pendant l'audit : Critical, High, Medium, Low, comme le kanban actuel ;
     - **Avancement**, pour suivre les correctifs : Trouvées → Revues → Évaluées (critic) → Reproduites → Corrigées. Seules les colonnes des étapes présentes au niveau sont affichées : en Light, Trouvées → Revues → Corrigées. Le lot 2 y ajoutera un bouton « Corriger » par carte.
   - Les findings écartés sont dans une colonne « Écartés » repliée par défaut.
   - Carte : pastille de sévérité (couleur **et** texte), titre, `fichier:ligne` en mono, puces d'état (Confirmé, Reproduit, Patch vérifié). Une carte qui change de colonne glisse vers sa nouvelle place ; une carte nouvelle apparaît en fondu.
   - Le filtre texte et le lien profond `#<id>` existants sont conservés.
5. **Colonne de droite** (240 px) : tuile **Actions** (selon l'état : Mettre en pause / Reprendre, Arrêter, Relancer l'étape) et tuile **Activité** (journal en direct, plus récent en haut, 50 lignes avec « voir tout »).
6. **Fiche d'un finding** : s'ouvre **au centre, en superposition façon Notion « peek »**.
   - Contenu : barre (id, fichier, « Ouvrir en pleine page », fermer), pastille de sévérité, titre, frise des étapes déjà traversées par ce finding, propriétés (statut, emplacement, exploitabilité, reproduction, patch, score), puis les sections existantes du panneau actuel : problème, impact, preuve et reproduction, correctif (diff coloré), historique.
   - Boutons : « Marquer faux positif », « Prioriser la reproduction » (masqué si le niveau n'a pas de reproduce, ou si la reproduction est déjà faite), « Copier le diff ».
   - Fermeture par Échap, clic hors fiche ou ✕. Le focus est piégé dans la fiche et rendu à la carte à la fermeture.
   - « Ouvrir en pleine page » donne une vue `#<id>&full` qui occupe toute la largeur.
   - La fiche ouverte se met à jour en direct sans perdre le défilement.
7. **Question en attente** : quand mantis-triage ou mantis-run attend une réponse (niveau d'audit, relance après échec), un bandeau bleu apparaît sous la bannière avec la question et les options en boutons. La même question est posée dans le terminal.

## 3. Agir : la page et le terminal

### 3.1 Commandes

Format d'une ligne de `commands.jsonl` : `{id, at, source: "page"|"terminal", action, ...}`.

| action | Paramètres | Quand elle est acceptée | Effet appliqué par mantis-run |
|---|---|---|---|
| `pause` | – | audit en cours | au prochain point de contrôle : `paused: true`, puis attente (§3.4) |
| `resume` | – | `paused` | reprend là où il s'était arrêté |
| `stop` | – | toujours avant la fin | au prochain point de contrôle : étape en cours remise à `pending`, `stopped: true`, puis étapes de Finish 1, 2 et 4 (intégrité, shadow, rendu), sans `finished: true` ; `/mantis-run` relance plus tard à partir de là |
| `retry` | `stage` | cette étape est `failed` | remet l'étape à `pending` et reprend |
| `answer` | `question`, `value` | une question est en attente et `value` fait partie de ses options | comme si l'utilisateur avait répondu dans le terminal |
| `false_positive` | `finding` | le finding existe et n'est pas déjà écarté | écrit `status: FALSE_POSITIVE` et `user_override: {action, at}` dans le finding ; il sort des étapes suivantes |
| `prioritize_repro` | `finding` | le niveau a reproduce, cette étape n'est pas `done`, et le finding n'est pas écarté | ajoute l'id à `state.json.force_repro` ; le finding entre dans le périmètre de reproduce même s'il en serait exclu (par exemple MEDIUM en Sharp) |

- Le serveur **valide** chaque POST : action connue, paramètres de type attendu, finding existant, étape existante, au plus 1 Ko. Sinon, réponse 400 et rien n'est écrit. La page affiche l'erreur à côté du bouton.
- Après un POST accepté, la page affiche l'action « en attente » (en gris, avec « pris en compte à la fin du lot en cours ») jusqu'à son accusé dans `commands-done.jsonl`, puis « appliquée » ou « refusée : raison ».
- Une commande déjà accusée n'est jamais rejouée : mantis-run ne traite que les `id` absents de `commands-done.jsonl`.

### 3.2 Depuis le terminal

L'utilisateur peut écrire en langage naturel (« mets en pause », « marque f-014 en faux positif »). mantis-run passe alors par `dashboard.py command` : l'action suit la même file, apparaît sur la page et dans le journal. Les réponses aux questions tapées dans le terminal sont acceptées directement.

### 3.3 Points de contrôle de mantis-run

mantis-run lit `commands.jsonl` :

- avant chaque étape ;
- après chaque retour de lot d'agents parallèles ;
- dans Patch Sharp+, entre deux findings.

Pendant qu'un agent travaille, Claude est bloqué : la page le dit (« pris en compte à la fin du lot en cours »).

À chaque point de contrôle, toutes les commandes non accusées sont traitées dans l'ordre. Une commande devenue inapplicable (par exemple `retry` sur une étape qui n'est plus `failed`) est accusée `refused` avec sa raison.

### 3.4 Attente de l'utilisateur (pause, échec, question)

Aujourd'hui, un échec arrête mantis-run (« relance `/mantis-run` »). Désormais, dans ces trois cas, mantis-run :

1. écrit `waiting.json` (et `paused: true` dans `state.json` pour une pause) ;
2. pose la question dans le terminal en texte simple (pas d'AskUserQuestion, qui bloquerait la réponse depuis la page), avec les mêmes options que sur la page ;
3. lance le tool `Monitor` en surveillance de `commands.jsonl` (boucle qui se termine dès qu'une nouvelle commande pertinente apparaît), puis termine son tour.

La première réponse qui arrive gagne : un clic sur la page réveille Claude via Monitor, et une réponse tapée dans le terminal réveille Claude directement (il l'enregistre alors avec `dashboard.py command`). L'autre canal voit la réponse comme déjà traitée.

- **Ce qui réveille Claude :** toute nouvelle commande. Pendant une pause, `false_positive` et `prioritize_repro` sont appliquées tout de suite, puis Claude se remet en attente. `resume`, `retry`, `stop` et `answer` lèvent l'attente.
- **Limite de Monitor :** à l'expiration, Claude relance la surveillance tant que `server.json` existe et que son pid est vivant. Si le serveur est arrêté, Claude supprime `waiting.json`, dit dans le terminal de relancer `/mantis-run` et termine.
- **Question Volume (niveau) du triage :** elle passe aussi par ce mécanisme, avec du texte simple dans le terminal au lieu d'AskUserQuestion. La réponse tapée est acceptée si elle désigne un niveau : le nom (Light, Sharp, Savage, Overkill, sans tenir compte de la casse) ou son numéro de 1 à 4. Sinon, Claude repose la question. Libellés, ordre, « (Recommandé) » et descriptions sont ceux de mantis-triage étape 6.
- **Question de versionnement (repo public ou visibilité inconnue) :** elle **reste au terminal seul**, avec AskUserQuestion comme aujourd'hui. Elle arrive avant que le dossier d'audit et le serveur existent, et l'exclusion git doit précéder toute écriture dans le repo. Le dashboard s'ouvre juste après.
- Un échec affiche sa raison en 2 lignes, à la fois dans le terminal et dans le panneau de l'étape, avec « Relancer » et « Arrêter ».

### 3.5 Session à l'écoute

La page affiche dans la tuile Actions l'un de ces trois états, déduits par le serveur sans écriture supplémentaire de Claude :

- « Claude travaille » : une étape est `running`, ou le triage est en cours ;
- « Claude attend ta réponse » : `waiting.json` existe ;
- « Aucune session active : relance `/mantis-run` » : dans tous les autres cas, par exemple entre la fin du triage et le lancement de mantis-run, ou après un arrêt. Les boutons d'action sont alors grisés et le serveur refuse le POST (409).

C'est une heuristique : une session Claude fermée brutalement pendant une étape `running` affiche encore « Claude travaille ». Si aucun fichier n'a changé depuis 20 min alors qu'une étape est `running`, la page ajoute « aucune activité depuis 20 min ».

## 4. Cycle de vie

1. **mantis-triage**, étape 3 (juste après la création de `AUDIT`, donc après la question de versionnement) : `dashboard.py serve "$AUDIT"`, puis ouverture de l'URL dans le navigateur (`open`) et affichage de l'URL dans le terminal en secours. Le pipeline montre alors Triage en cours.
2. **mantis-run**, §1 (une fois `AUDIT` choisi et le contrôle « hostile » passé) : `dashboard.py serve "$AUDIT"`. Le serveur est réutilisé s'il tourne déjà ; sinon il est relancé et la page est rouverte.
3. Pendant l'audit : rien d'autre, puisque le serveur suit les fichiers tout seul.
4. **Finish** : `render.py` produit le `dashboard.html` final. La page live affiche « Audit terminé » ; le serveur s'arrête seul 30 min plus tard, et la page passe alors en « Hors ligne » en gardant ses données. Le terminal donne le chemin de `dashboard.html` pour une relecture ultérieure. L'ancien `open dashboard.html` de l'étape 4.4 est supprimé, puisque la page est déjà ouverte.

Le `dashboard.html` final inclut le journal d'activité et les durées lus dans `activity.jsonl` s'il existe ; les trous éventuels s'affichent « inconnue ». La frise d'un finding dans la fiche est déduite de ses champs (`reasoning`, `production_viability`, `repro_status`, `patch_status`…), pas du journal, et elle est donc toujours complète.

`server.json`, `activity.jsonl`, `commands.jsonl` et `commands-done.jsonl` restent dans le dossier d'audit comme trace. Ils suivent la règle de versionnement existante du dossier ; `server.json` est supprimé à l'arrêt.

## 5. Sécurité

- Le repo audité peut être hostile : tout texte issu d'un finding est inséré avec `textContent` (pas de `innerHTML`) ; le JSON inclus dans le fichier final reste échappé comme aujourd'hui (`safe_json`, test `XSS` existant).
- Le serveur écoute sur `127.0.0.1` uniquement, exige la clé de session sur toutes les routes, vérifie `Origin` sur le POST, et ne sert que la page et le flux : aucun fichier arbitraire, pas de route `/files`.
- Les écritures de mantis-run déclenchées par une commande (`false_positive`, `force_repro`) passent par la même validation que le serveur (id existant dans `workspace/findings/`, sans `/` ni `..`).
- Le contrôle « hostile » existant de mantis-run (liens symboliques dans `osho-mantis/`) s'exécute **avant** le lancement du serveur.

## 6. Design

Base : Horizon OS (`~/dev/OshO-dev/Coqpit/horizon/apps/web/src/theme.css`, spec `docs/superpowers/specs/2026-10-11-refonte-ovh-ui-design.md` dans ce repo-là). Les jetons sont recopiés en variables CSS dans le gabarit. On ne crée **pas** de dépendance vers ce repo.

- **Thème** : sombre par défaut, clair disponible (bascule dans la barre du haut, suit `prefers-color-scheme` au premier chargement). On garde les deux jeux de jetons d'Horizon : fond `#0b0d14` / `#eff1f5`, cartes `#12151f` / `#fff`, texte `#e7ebf6` / `#0b1a4a`, accent unique `#7ea6ff` / `#0050d7`, bordures `#242a3b` / `#e1e5ee`, sélection `#1e2847` / `#d5dbf1`, bannière `#18203d` + `#10162b` / `#d4daee` + `#e7eaf5`. États : succès `oklch(.72 .15 155)`, alerte `oklch(.80 .15 85)`, erreur `oklch(.65 .20 25)`. Sévérités : critique `oklch(.62 .22 20)`, haute `oklch(.70 .18 45)`, moyenne `oklch(.80 .15 85)`, basse `oklch(.72 .08 240)`.
- **Typo** : Source Sans 3 pour le texte, Geist Mono pour chiffres, codes d'étapes, chemins et journal ; chiffres tabulaires partout. Pas de téléchargement de police : pile `"Source Sans 3", system-ui` et `"Geist Mono", ui-monospace, Menlo`, puisque le fichier final doit marcher hors ligne.
- **Rayons** : 10 px pour tuiles, fiche et pipeline ; 6 px pour boutons, cartes du kanban et champs ; pastilles en `rounded-full`.
- **Ton du pipeline** : « salle de renseignement » sobre. Grille fine, codes en 3 lettres, mono en capitales espacées, un seul accent bleu, pas de néon ni de lueur.
- **Mouvement** : seul ce qui change d'état bouge (l'étape active, une carte qui change de colonne, la fiche qui s'ouvre avec un fondu et une montée de 8 px en 180 ms, easing `cubic-bezier(.16,1,.3,1)`). `prefers-reduced-motion` coupe toutes les animations.
- **Accessibilité** : contraste AA ; jamais la couleur seule (sévérité et état portent toujours un mot ou une icône) ; navigation au clavier sur les cartes, les étapes et la bascule de vue ; libellé accessible sur les boutons-icônes ; région `aria-live="polite"` pour annoncer les changements d'étape.
- **Largeur** : conçu pour 1280 px et plus. En dessous de 1024 px, la colonne de droite passe sous le kanban et le pipeline défile horizontalement.

## 7. Tests

- `test_render.py` : les tests existants passent toujours. Ils sont adaptés au nouveau gabarit, sans supprimer de cas (XSS, collisions d'id, thème clair, aucun finding, lien profond, filtre).
- Nouveau `test_dashboard.py`, en auto-test exécutable comme `test_render.py` (`python3 test_dashboard.py`) :
  - le snapshot se construit à partir d'un dossier d'audit fictif, à chaque phase (triage seul, en cours, `failed`, en pause, terminé, Overkill tour 2) ;
  - le diff entre deux snapshots produit les bons événements d'activité (étape démarrée et terminée avec sa durée, nouveau finding, finding qui change de colonne) ;
  - état déduit pour la tuile « session à l'écoute » (§3.5) dans les trois cas ;
- validation des commandes : chaque action valide passe, et chaque cas invalide est refusé (action inconnue, finding absent, id avec `..`, plus de 1 Ko, `retry` sur une étape non `failed`) ;
  - le serveur répond 403 sans clé et 403 sur un POST d'une autre `Origin` ; le flux SSE envoie un snapshot après modification de `state.json` ;
  - `serve` réutilise un serveur vivant ; `stop` supprime `server.json`.
- Vérification manuelle avant fusion : un audit Light sur un petit repo, avec la page ouverte de bout en bout. Au programme : pause et reprise depuis la page, pause depuis le terminal, faux positif depuis la fiche, échec simulé puis « Relancer ».

## 8. Laissé au constructeur

- Le découpage du JS dans le gabarit, les noms de fonctions, la forme exacte du snapshot.
- L'icône des deux boutons de vue (pas de SVG d'icône dessiné à la main si une bibliothèque est disponible ; sinon une forme géométrique simple).
- La formulation exacte des textes du journal, en français, sans tiret cadratin.

## 9. Lot 2 (spec séparée, après ce lot) : « Corriger » depuis le kanban d'avancement

Décidé avec l'utilisateur le 2026-10-22, à brainstormer dans sa propre spec. Une carte de la vue Avancement aura un bouton « Corriger ». Il demande à Claude de lancer des sous-agents qui corrigent le vrai code, et la carte se met à jour une fois le travail terminé. Ce lot remet en cause le principe actuel de repo en lecture seule. Piste proposée, non validée : un worktree sur une branche `mantis-fix/<audit>`, un commit par finding, une re-attaque Docker quand le niveau le permet, jamais sur la branche courante, jamais de push. Ce lot 1 prépare le terrain : la file de commandes et la vue Avancement.
