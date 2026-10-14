# Escouade × Superpowers — note de cadrage

*14 octobre 2026 · Robin · base de travail, rien n'est décidé*

## 1. Ce qu'on veut

Faire tourner plus tard un agent qui **optimise la création de tâches avec Superpowers dans Escouade**, pour que :

1. le découpage Superpowers (plan, tâches, relectures) **colle à l'interface kanban** d'Escouade ;
2. les **sous-tâches** de l'agent (une tâche du plan, un correctif, un audit) soient visibles comme sous-tâches du ticket ;
3. les **critères d'acceptation** du ticket et ceux du plan soient les mêmes, suivis au même endroit.

Le travail se fait dans ce dépôt (OshO Skillz) : les hooks y sont déjà (`plugins/osho-core/hooks/` : `superpowers-offer.sh`, `crg.sh`), ainsi que `audit-loop` et `revue-artefact`.

## 2. Comment Escouade pilote un agent aujourd'hui

Constaté sur les tickets kata KAT-3 à KAT-7 (13-14 octobre 2026).

- **Un ticket = un worktree** `.claude/worktrees/kat-n` sur la branche `ticket/kat-n`, et un agent Claude Code lancé par Escouade (opus, effort medium, mode auto).
- **Un prompt ajouté** (`appendPrompt` dans `~/.escouade/state.json`) qui fixe :
  - les critères d'acceptation numérotés, à vérifier soi-même ;
  - un bloc ` ```escouade {"criteres": […], "avancement": […], "lancement": {…}} ``` ` à la fin de **chaque** réponse ;
  - les ports réservés (`ESCOUADE_PORT_BASE`, `ESCOUADE_PORT_END`), jamais écrits dans un fichier versionné.
- **Des boucles** : tant qu'un critère est `ok: false`, Escouade relance l'agent (« Boucle n/5. Critères non atteints : … »), au plus 5 fois.
- **La validation** du ticket vérifie que le worktree est toujours sur `ticket/kat-n`, puis tente `gh pr create` depuis `ticket/kat-n` vers `dev`.
- `extractCriteria: true`, `syncStates: true` dans `~/.escouade/settings.json`.

Côté projet, le `CLAUDE.md` de kata impose sa propre méthode : un plan par lot (`superpowers:writing-plans`), un sous-agent par tâche avec relecture (`subagent-driven-development`), une branche `feat/…` par lot, une seule CI locale complète, `audit-loop` en relecture finale, la fusion sur le oui explicite de Robin, puis la doc en dernier.

## 3. Difficultés et warnings relevés

### 3.1 Branche du worktree (le plus coûteux)

- **22 avertissements** dans `~/.escouade/app.log` : « Le worktree n'est plus sur la branche ticket/kat-n », sur KAT-4, KAT-5, KAT-6 et KAT-7.
- **Cause** : la méthode kata dit « une branche `feat/…` par lot ». L'agent fait `git checkout -b feat/…` **dans** le worktree, et Escouade ne reconnaît plus le ticket.
- **Divergence** : sur KAT-6, `ticket/kat-n` partait d'un commit local du ticket précédent (`12a1db2`, une copie de KAT-5) absent de `origin/dev`, avec le même contenu. Pour revenir sur la branche sans réécrire d'historique, il a fallu une fusion avec conflits partout. Le `git reset --hard` a été refusé par le mode auto (« Irreversible Local Destruction »).
- **PR en double** : comme la PR part de `feat/…`, la création de PR d'Escouade depuis `ticket/kat-n` échoue (« No commits between dev and ticket/kat-n »).
- Ce qu'il faudrait :
  - ne jamais changer de branche dans un worktree Escouade ;
  - pousser `ticket/kat-n:feat/<lot>` ;
  - partir d'une branche ticket recalée sur `origin/dev` ;
  - ou laisser Escouade créer la PR.

### 3.2 Critères et boucles

- **Le bloc ` ```escouade ` à chaque réponse** oblige l'agent à finir son tour. Pendant une longue attente (CI de 10 minutes, audit, sous-agent), il finit son tour « en attente », et Escouade compte une boucle. KAT-6 a utilisé les boucles 1 à 4, plus un retour de test, alors que le travail avançait normalement.
- **Un critère invérifiable depuis le worktree** : « page d'avancement à jour » est un artefact claude.ai publié depuis une autre session, et aucun outil de publication d'artefact n'est disponible dans une session lancée par Escouade. Le critère est resté `false` jusqu'à ce que Robin le déclare sans objet.
- **Des critères en conflit avec `CLAUDE.md`** :
  - « PR fusionnée dans dev après audit prêt » face à « on ne fusionne qu'avec le oui explicite de Robin » ;
  - « CI complète une fois, hash noté » face à « revérifie tous les critères », qui a fait relancer la CI sur un nouveau hash.
- **Le bloc `lancement`** : `ouvrir` doit montrer la fonctionnalité, mais les identifiants semés (client, mission) changent à chaque préparation de la base de test. Une adresse stable vers l'écran est donc impossible ; seul l'accueil reste fiable.
- `avancement` (3 à 8 éléments) et `criteres` ont été remplis à la main à chaque réponse. Ce sont les mêmes informations que le registre Superpowers (`.superpowers/sdd/<plan>/progress.md`), qui n'est pas versionné et que le skill efface en fin de plan.

### 3.3 Sous-tâches invisibles

- Superpowers découpe en tâches avec un registre, des fiches et des rapports dans `.superpowers/sdd/`. Escouade n'en voit rien : le kanban montre un seul ticket « en cours » pendant des heures.
- Les rappels « TaskCreate / TaskUpdate » du harnais sont ignorés : l'agent suit son registre. Personne ne voit les 7 tâches, les 6 tours de correctifs et les 2 tours d'audit de KAT-6.
- **Volume pour KAT-6** : 23 sous-agents (7 implémentations, 7 relectures opus, 5 re-relectures, 2 audits, 1 doc, plus des reprises). Robin : « c'est long ».

### 3.4 Hooks et questions en mode autonome

- **`superpowers-offer.sh`** pose une question (AskUserQuestion) au premier message, alors que la session est lancée par Escouade en autonomie. La réponse est évidente : `CLAUDE.md` impose déjà Superpowers.
- **Le hook `revue-artefact`** pousse à présenter le plan et le bilan en page d'artefact, ce qui est impossible dans une session Escouade. Il entre aussi en conflit avec « ne pas s'arrêter, poser une question seulement si une décision est nécessaire ».
- **AskUserQuestion avec une option « Je le donne »** : Robin l'a choisie sans montant, et il a fallu reposer la question (coût IA). Préférer une question ouverte, ou une valeur saisie dans « Other ».
- **Mode auto** :
  - la fusion a été refusée (« Merge Without Review ») malgré le critère du ticket ;
  - dans la foulée, une simple lecture de fichier a été refusée pour la même raison ;
  - il a donc fallu demander le oui à Robin. À prévoir : une règle de permission, ou le oui explicite dans le ticket.

### 3.5 Environnement

- **zsh ne découpe pas les variables** (`for c in "npm run x"; $c` puis `env $E cmd`). Cela a donné une première « CI » où rien n'a tourné, et un lancement qui a visé la base `kata` (le garde-fou de la base l'a refusé). Écrire les boucles dans un script `bash`.
- **Deux noms pour la même plage de ports** : Escouade donne `ESCOUADE_PORT_BASE`, la CI kata lit `PW_PORT_BASE`. De plus, Playwright ne démarre ses serveurs qu'avec `PW_PROJECT=e2e`.
- **Tests concurrents** : la CI complète et un audit qui lance « un fichier vitest » partagent la base `kata_test` (vidée à chaque lancement), d'où un risque de collision.
- Escouade lui-même :
  - 18 « update endpoint did not respond » ;
  - un `state.json` invalide (`null` au lieu d'une chaîne, ligne 156) ;
  - le mémo Claude `import-xirp-escouade` : écrire `state.json` pendant qu'Escouade tourne est écrasé.

## 4. Pistes à travailler

1. **Un skill ou un hook « mode Escouade »**. Il détecte la session lancée par Escouade (variable d'environnement, `appendPrompt`, chemin `.claude/worktrees/kat-n`), puis :
   - n'offre pas Superpowers et désactive les artefacts ;
   - bloque `git checkout`/`switch` hors de `ticket/kat-n` (hook PreToolUse) ;
   - pousse la PR depuis la branche du ticket.
2. **Le plan donne les sous-tâches** : chaque tâche du plan devient une sous-tâche Escouade (création, état, commit, relecture), via le serveur MCP d'Escouade (`mcpEnabled`, port 47821) ou `TaskCreate`/`TaskUpdate` si Escouade les lit.
3. **Les critères donnent le plan** : les critères du ticket sont recopiés dans le plan (section « Critères d'acceptation ») ; le registre Superpowers tient leur état ; le bloc ` ```escouade ` se génère depuis le registre au lieu d'être réécrit à la main.
4. **Des tours qui ne coûtent pas une boucle** : convenir avec Escouade d'un état « en attente d'un travail en fond » (CI, audit) qui ne relance pas l'agent, ou ne relancer qu'à la notification.
5. **Des critères vérifiables** : un modèle de ticket qui refuse les critères hors worktree (artefact, page externe) ou les marque « confirmés par Robin ».
6. **Moins de sièges de relecture** pour les petites tâches front (une relecture opus plus une re-relecture sonnet par tâche) ; Robin garde les relectures opus (mémo Claude `methode-lot-allegee`), donc chercher l'économie ailleurs : regrouper les petites tâches, une seule re-relecture.
7. **Les permissions d'un ticket** : si le ticket autorise la fusion, une règle de permission limitée à `gh pr merge <n> --merge` vers `dev` pour cette session.

## 5. Questions ouvertes

1. Escouade expose-t-il des sous-tâches (API ou MCP) ? Sinon, faut-il les ajouter côté Escouade (`~/dev/xirp-escouade`) ?
2. Qui crée la PR : Escouade depuis `ticket/kat-n`, ou l'agent ? Et qui fusionne ?
3. La branche `feat/…` de `CLAUDE.md` kata survit-elle à Escouade, ou devient-elle `ticket/kat-n` ?
4. Les boucles : faut-il garder 5 relances quand un lot dure plusieurs heures ?

## Sources

- `~/.escouade/app.log`, `~/.escouade/settings.json`, `~/.escouade/state.json` (agent `kat-6-v0-5-7-analyse-et-leviers`)
- kata : `CLAUDE.md` § 4, `docs/plans/2026-10-13-v05-7-bilan.md`, `docs/plans/2026-10-13-v05-6-bilan.md`
- Mémoires Claude du projet kata : `escouade-branche-ticket`, `methode-lot-allegee`, `import-xirp-escouade`
- Ce dépôt : `plugins/osho-core/hooks/superpowers-offer.sh`, `docs/decisions.md`
