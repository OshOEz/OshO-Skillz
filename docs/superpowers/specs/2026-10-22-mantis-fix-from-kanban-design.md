# osho-mantis : « Corriger » depuis le kanban (lot 2), design

Date : 2026-10-22 · Plugin : osho-mantis (0.2.0 vers 0.3.0) · Branche : `feat/mantis-fix`
Base : [2026-10-22-mantis-dashboard-live-design.md](./2026-10-22-mantis-dashboard-live-design.md), lot 1, fusionné. Ce document remplace son §9.

## Intention

Le lot 1 montre l'audit en direct et des correctifs **proposés** (`patch_diff`), que l'utilisateur doit appliquer à la main. Le lot 2 fait passer de « trouvé » à « corrigé dans le code » en deux clics depuis la carte d'une vulnérabilité, sans quitter le dashboard.

Parcours voulu par l'utilisateur, avec ses mots :

1. Dans la vue **Avancement**, je clique **Corriger** sur une carte.
2. Ça crée un **sous-agent dans la conversation Claude**. La carte affiche un état de chargement.
3. Quand l'agent a fini, la carte affiche un bouton **Merger**.
4. Je clique **Merger** : le correctif rejoint la **branche de l'audit**, et la carte passe dans **Corrigées**.
5. Aucune vérification n'est demandée sur la carte. Si je veux regarder le travail, je vais voir l'agent dans la session Claude.

La **branche de l'audit** est une branche créée exprès, par exemple `mantis/audit-2026-10-22_17h28`, qui part de la branche sur laquelle l'audit a été lancé. Chaque correctif y arrive après un clic sur « Merger ». L'utilisateur fusionne lui-même cette branche dans son travail, quand il veut.

## Objectifs

1. Un clic **Corriger** lance un sous-agent de correction pour ce finding. Depuis le terminal, « corrige f-014 » fait la même chose.
2. Le correctif est un commit sur une branche à lui, à partir de l'état courant de la branche de l'audit.
3. Un clic **Merger** fusionne ce commit dans la branche de l'audit. La carte passe dans « Corrigées » en moins de 2 s.
4. Tout se fait sans toucher au répertoire de travail de l'utilisateur ni à sa branche courante.
5. Le bouton fonctionne pendant l'audit comme après la fin.

## Non-objectifs

- Pas de vérification automatique avant le merge : pas de test, pas de re-attaque Docker, pas de revue. Le correctif est jugé par l'utilisateur, s'il le souhaite, dans l'agent.
- Pas de push, pas de PR. La branche de l'audit reste locale.
- Pas de fusion de la branche de l'audit dans la branche de l'utilisateur. C'est son geste.
- Pas de correction groupée (« tout corriger ») dans ce lot.

## Anti-objectifs (échec même si « ça marche »)

- Un agent de correction modifie le répertoire de travail de l'utilisateur, sa branche courante ou une autre branche que la sienne.
- « Merger » laisse la branche de l'audit dans un état cassé : conflit à moitié résolu, marqueurs `<<<<<<<` commités.
- Une carte affiche « Corrigée » alors que rien n'a été fusionné.
- Un correctif fusionné disparaît en silence parce qu'un autre l'a écrasé.
- L'audit en cours se bloque ou ralentit visiblement parce qu'une correction tourne.

## 1. Modèle

### 1.1 Branche de l'audit

- **Nom :** `mantis/<nom du dossier d'audit>`, par exemple `mantis/audit-2026-10-22_17h28`.
- **Point de départ :** le commit `HEAD` du repo au début de l'audit. mantis-run §2 l'enregistre dans `state.json` sous `base_commit` (nouveau champ). Pour un audit créé avant le lot 2, sans `base_commit`, on prend le `HEAD` du repo au moment du premier clic.
- **Création :** paresseuse, au premier « Corriger » de l'audit. Si la branche existe déjà (reprise), on la réutilise.
- Elle est créée et modifiée **sans checkout** dans le répertoire de l'utilisateur.

### 1.2 Une correction

Une correction par finding (`<stem>` = nom du fichier du finding, comme `_src` au lot 1). L'état est stocké dans `<AUDIT>/fixes.json` : `{<stem>: {status, branch, worktree, commit, base, error, agent, at}}`.

| `status` | Sens | Carte (vue Avancement) |
|---|---|---|
| absent | rien demandé | bouton **Corriger** |
| `queued` | commande reçue, agent pas encore lancé | « En file… » |
| `running` | agent lancé | état de chargement, « Correction en cours » |
| `ready` | commit prêt sur la branche du correctif | bouton **Merger** |
| `failed` | l'agent n'a pas pu corriger, ou n'a rien commité | raison en 1 ligne, bouton **Corriger** à nouveau |
| `conflict` | le merge a échoué sur un conflit | « Conflit avec un autre correctif », bouton **Recorriger** |
| `merged` | fusionné dans la branche de l'audit | carte dans **Corrigées** |

- **Branche du correctif :** `mantis/fix/<audit>/<stem court>`, créée à partir de la tête courante de la branche de l'audit au moment du lancement.
- **Worktree :** chaque agent travaille dans un worktree à lui, hors du repo et hors du dossier d'audit (`mktemp -d`), sur la branche du correctif. Ce worktree est supprimé après le merge, ou après un échec.

### 1.3 Colonnes du kanban d'avancement

Au lot 1, « Corrigées » regroupait les findings qui avaient un correctif **proposé** (`patch_status` valant `MITIGATION_PROPOSED` ou `VERIFIED_SECURE`). Désormais, « Corrigées » veut dire **fusionné dans la branche de l'audit**. *(Choix de Claude.)*

- Nouvelle colonne **« Correctif proposé »** : `patch_status` est présent, mais la correction n'est pas `merged`.
- **« Corrigées »** : `fixes.json[stem].status == "merged"`.
- Ordre des colonnes en Light : Trouvées, Revues, Correctif proposé, Corrigées. En Sharp et au-dessus : Trouvées, Revues, Évaluées, Reproduites, Correctif proposé, Corrigées.
- Le bouton **Corriger** apparaît sur toute carte non écartée qui n'est pas `merged`, quelle que soit sa colonne.
- La vue Sévérité affiche aussi l'état de la correction, en petite puce, sans les boutons. *(Choix de Claude.)*

## 2. Déroulé

### 2.1 Corriger

1. **Page :** POST de la commande `fix` avec `{finding}`. La validation est la même qu'au lot 1, avec ces règles : finding non écarté, pas déjà `queued`, `running` ou `merged`, et une session Claude à l'écoute.
2. **mantis-run, au prochain point de contrôle** (lot 1, §3.3), ou tout de suite s'il est en attente :
   1. il crée la branche de l'audit si besoin ;
   2. il crée la branche et le worktree du correctif ;
   3. il passe le finding à `running` dans `fixes.json` ;
   4. il lance **un sous-agent en arrière-plan** (`run_in_background`), avec le prompt du §2.3 ;
   5. il accuse la commande, puis reprend l'audit là où il était.
3. **À la fin de l'agent** (notification de Claude Code), mantis-run vérifie que la branche du correctif a au moins un commit de plus que son point de départ et que le worktree est propre :
   - si oui : `ready`, avec le sha dans `commit` ;
   - sinon : `failed`, avec la raison.

   Le worktree est gardé jusqu'au merge.
4. **Corrections en parallèle :** au plus 3 agents de correction tournent en même temps. Au-delà, les demandes restent `queued` et sont lancées dès qu'une place se libère. *(Choix de Claude.)*

### 2.2 Merger

- La commande `merge_fix` avec `{finding}` est **appliquée directement par le serveur**, sans attendre Claude, parce que c'est une opération git déterministe et que l'utilisateur attend un effet immédiat. *(Choix de Claude.)* Elle est acceptée seulement si le finding est `ready`.
- **Opération :** fusionner la branche du correctif dans la branche de l'audit **sans checkout dans le répertoire de l'utilisateur**. Elle est faite par un merge en mémoire (`git merge-tree --write-tree`, puis `git commit-tree` et `git update-ref` avec l'ancienne valeur attendue), ou par un worktree jetable de la branche de l'audit. Le choix revient au constructeur.
  - Le commit de merge a pour message `Merge correctif Mantis : <titre du finding> [<stem>]`.
  - `update-ref` vérifie l'ancienne valeur, pour qu'un merge concurrent ne puisse jamais en écraser un autre.
- **Succès :** `merged`. Le worktree et la branche du correctif sont supprimés, la carte passe dans « Corrigées », et le journal affiche « Correctif fusionné : <titre> ».
- **Conflit :** rien n'est écrit dans la branche de l'audit, et le statut passe à `conflict`. **Recorriger** remet le finding en `queued` et relance un agent à partir de la tête **à jour** de la branche de l'audit, en lui donnant le diff déjà tenté comme point de départ.
- Le merge est accepté aussi quand aucune session Claude n'écoute, puisqu'il n'a pas besoin de Claude.

### 2.3 Prompt de l'agent de correction

```
You fix one security finding of a Mantis audit in a git worktree.
Worktree (your only writable location): <WORKTREE>, on branch <FIX_BRANCH>.
Finding: <AUDIT>/workspace/findings/<stem>.json (read it: title, description, code_paths, reasoning, patch_diff if any).
1. Fix the root cause with the smallest change. If patch_diff exists, start from it and adapt it to the current code.
2. Edit only files inside <WORKTREE>. Never touch <REPO>, other branches, or <AUDIT>.
3. Never build, install, run or test target code on the host (static work only).
4. Commit once on <FIX_BRANCH>: `fix(mantis): <title> [<stem>]`. Do not push, do not merge.
5. If you cannot fix it safely, commit nothing and say why.
Reply in 3 lines: commit sha or « aucun », files changed, any doubt.
```

- **Modèle :** sonnet. Opus si la sévérité est CRITICAL. *(Choix de Claude.)*
- Le sous-agent est nommé `Correctif <stem court>` pour que l'utilisateur le retrouve dans la session.

### 2.4 Après la fin de l'audit

Aujourd'hui, mantis-run se termine après Finish, et la page passe à « Aucune session active ». Pour que « Corriger » marche après l'audit, il faut une session Claude à l'écoute. *(Validé par l'utilisateur : §5.)*

- À la fin de Finish, mantis-run reste à l'écoute des corrections dans un mode « Corrections ». Il lance Monitor sur `pending` et traite les commandes `fix` comme au §2.1. La page affiche « Claude attend tes demandes de correction », avec un bouton **Terminer**.
- Le mode se termine quand l'utilisateur clique **Terminer** ou tape « terminé », ou quand aucun clic n'arrive pendant 30 min et qu'aucune correction n'est en cours.
- Plus tard, `/mantis-run <audit>` sur un audit terminé rouvre directement ce mode, sans relancer l'audit.


### 2.5 Cas limites *(choix de Claude)*

- **Arrêt, session fermée ou plantée :**
  - les agents de correction en cours ne sont pas tués : ils tournent en arrière-plan et finissent leur commit ;
  - les demandes `queued` restent en file pour la reprise ;
  - à la reprise (`/mantis-run`, §1), chaque entrée `running` sans agent vivant est réévaluée : `ready` si la branche du correctif a un commit au-delà de sa base et un worktree propre, sinon `failed` (« correction interrompue »).
- **Arbre de travail sale au début de l'audit** (`git_status_before` non vide) : la branche de l'audit part quand même de `HEAD`. Le bouton Corriger affiche alors un avertissement fixe : « L'audit portait aussi sur des modifications non commitées : le correctif part du dernier commit. » L'agent reçoit la même consigne, et il répond « aucun » si le code visé n'existe pas dans le commit.
- **Étapes suivantes de l'audit :** un finding `running`, `ready` ou `merged` sort du périmètre de critic, reproduce, patch et calibrate, comme un finding écarté. Il ne consomme plus de quota et ne peut plus être reclassé après coup.
- **Rapport final :** après chaque `merge_fix` réussi sur un audit `finished`, le serveur relance `render.py`, pour que `README.md` et `dashboard.html` montrent les corrections fusionnées. Le README gagne une section « Corrections fusionnées » avec la branche de l'audit et la commande pour la fusionner.
- **Hooks et filtres git :** le repo audité peut être hostile. Tous les `worktree add`, `commit` et merges se font avec `-c core.hooksPath=/dev/null` et sans filtres de checkout (`-c filter.<x>.smudge=` n'est pas fiable : on passe `GIT_CONFIG_NOSYSTEM=1` et un `-c core.attributesFile=/dev/null`, et on refuse de créer le worktree si `.gitattributes` déclare un `filter=`). Le hook pre-commit de l'utilisateur ne tourne donc pas sur ces commits. C'est voulu.

## 3. Commandes ajoutées

Format et file d'actions : ceux du lot 1. Toutes passent par `commands.validate()`.

| action | Paramètres | Acceptée si | Appliquée par |
|---|---|---|---|
| `fix` | `finding` | non écarté, `status` absent, `failed` ou `conflict`, session à l'écoute | mantis-run (point de contrôle ou mode Corrections) |
| `merge_fix` | `finding` | `status == "ready"` | **le serveur**, immédiatement |
| `end_fixes` | aucun | mode Corrections actif | mantis-run |

Depuis le terminal :
- « corrige f-014 » donne `fix` ;
- « merge f-014 » donne `merge_fix`, appliqué par `dashboard.py apply` ;
- « terminé » donne `end_fixes`.

## 4. Sécurité et robustesse

- Toutes les commandes git visent le repo de `campaign.json.repo` et des noms de branche construits par le code. Le `<stem>` est validé comme au lot 1 : pas de `/`, de `\` ni de `..`, et le fichier doit exister. Aucun nom de branche ne vient tel quel de la page.
- Les worktrees sont créés avec `mktemp -d`, avec le même garde-fou que le shadow du lot 1 avant toute suppression.
- Le serveur n'exécute que `merge_fix`. Toute autre opération git reste chez mantis-run.
- `fixes.json` est écrit avec l'écriture atomique `O_EXCL` du lot 1.
- Si l'utilisateur a supprimé ou déplacé la branche de l'audit à la main, `merge_fix` répond `failed` (« branche de l'audit introuvable ») et ne la recrée pas d'office.
- Le contrôle d'intégrité de Finish (lot 1, §4.1) compare toujours `git status` du répertoire de l'utilisateur. Il doit rester vide de changements, puisque les corrections n'y écrivent rien.

## 5. Décisions de l'utilisateur (2026-10-22)

1. **Après la fin de l'audit, Claude reste à l'écoute** dans le mode « Corrections » décrit au §2.4. Le mode a un bouton Terminer, s'arrête tout seul après 30 min sans clic, et `/mantis-run` sur un audit terminé le rouvre.
2. **La branche de l'audit est affichée** dans la bannière et dans le rapport final, par exemple « 3 correctifs sur `mantis/audit-…` », avec un bouton qui copie `git merge mantis/audit-…`.

## 6. Tests

- **Auto-tests :**
  - `fixes.json` et les colonnes « Correctif proposé » et « Corrigées » ;
  - validation des commandes `fix`, `merge_fix` et `end_fixes` ;
  - merge sans conflit, avec conflit (la branche de l'audit est inchangée), et en concurrence (`update-ref` refusé) ;
  - aucun changement dans le répertoire de travail ni sur la branche courante après un merge ;
  - stem hostile refusé.
- **Essai réel** sur le repo jouet `~/dev/mantis-toy` :
  - corriger deux findings qui touchent le même fichier (`app.py`), merger le premier, constater le conflit sur le second, puis recorriger et merger ;
  - vérifier `git log mantis/audit-…`, puis que `git status` du repo est inchangé.

## 7. Laissé au constructeur

- Merge en mémoire ou worktree jetable (§2.2).
- La forme exacte de l'état de chargement sur la carte (dans le style du lot 1).
- Le découpage du code : un module `fixes.py` est suggéré, à côté de `commands.py`.
