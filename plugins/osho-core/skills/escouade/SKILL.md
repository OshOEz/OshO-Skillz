---
name: escouade
description: Méthode pour travailler avec Escouade (Kanban de tickets qui lance un agent Claude Code par ticket, dans un worktree sur la branche ticket/<clé>). Utiliser dès qu'une session tourne sur une branche ticket/<clé> ou commence par « Tu travailles en autonomie sur le ticket », quand l'utilisateur veut découper un travail en tickets Escouade, demande comment utiliser Escouade, veut fusionner, auditer ou clore un ticket, quand un ticket est renvoyé après un audit, ou pour laisser une demande dans « À toi ».
---

# escouade

Escouade fait foi pour le suivi et la fusion : un ticket s'approuve depuis le Kanban ; s'il y a une PR, c'est celle qu'ouvre Escouade, jamais une seconde à côté.

Contexte du dépôt (sort 1 hors d'un ticket) :

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/escouade/scripts/contexte.sh" [chemin] [base]
# ticket: ABC-4 / branche: ticket/abc-4 / base: dev / retard: 3
```

`base` vient d'`origin/HEAD` ; passe-la en argument si le projet en a une autre (par exemple `dev`).

## Découper : un ticket = un lot

- **Un ticket par lot livrable** (un bilan), pas par tâche, avec ses critères vérifiables (une commande, un test, un écran) dans `criteria`.
- Un lot qui dépend d'un autre se crée **tout de suite** avec `after` : il démarre quand ceux-là sont finis.
- `model` et `effort` par ticket quand le lot le demande.
- Lis la cible et l'action dans `get_board`, ne les suppose pas.
- Avant `create_ticket`, mets la branche cible **locale** à jour, car avec l'autopilote le ticket démarre aussitôt depuis elle : `git branch --show-current` affiche `<cible>` → `git pull --ff-only` ; sinon → `git fetch origin <cible>:<cible>`.
- Un ticket qui attend une décision de l'utilisateur : `ask_user` avec `tickets`, pour que l'autopilote le laisse en attente.
- Le découpage initial se fait depuis une session classique (hors ticket), avec superpowers:brainstorming puis writing-plans si c'est complexe.

## Dans un ticket (agent lancé par Escouade)

1. **Mémoire.** `search_memory` sur le sujet du ticket, pour reprendre les façons de faire et les pièges déjà notés.
2. **Rattraper la base.** `contexte.sh` donne un `retard` supérieur à 0 → `git fetch origin && git merge origin/<base>` sur la branche du ticket. Ne jamais `reset` la branche ni changer de branche dans le worktree : Escouade suit `ticket/<clé>` et c'est elle qu'il fusionne.
3. **Plan, puis tâches.** Lot complexe : superpowers (brainstorming, writing-plans, subagent-driven-development). `TaskCreate` par tâche **dès le plan approuvé, avant le premier sous-agent**, car elles s'affichent en haut de l'agent dans Escouade ; `TaskUpdate` et `report_progress` à chaque tâche.
4. **Sous-agents dans le worktree du ticket**, jamais dans un autre, car Escouade ne voit que `ticket/<clé>` ; une tâche commitée à la fois, `[<CLÉ>]` à la fin du message.
5. **Ne jamais finir un tour pour surveiller** ou attendre un sous-agent, car chaque fin de tour compte comme une boucle et un ticket qui épuise ses boucles est tenu pour fini. Une demande `ask_user` ne s'attend pas non plus : continue, sa réponse te réveillera.
6. **Deux canaux vers l'utilisateur.** La question qui te bloque → l'outil de question ; ce que tu attends sans être bloqué (un choix, un feu vert, un essai qu'il est seul à pouvoir faire) → `ask_user`, avec ta recommandation, jamais un secret.
7. **Décisions et méthode.** Une décision sur le produit → `propose_decision`. Une façon de travailler apprise → `write_memory`.
8. **Ports et secrets.** Utilise les ports réservés du prompt (`ESCOUADE_PORT_BASE`, `ESCOUADE_PORT_END`) en variables d'environnement, jamais dans un fichier versionné ; arrête tes serveurs par PID ou par tes propres ports, jamais par un motif (`pkill -f`), car tu tuerais ceux des autres tickets. Ne commite pas les fichiers qu'Escouade copie depuis le projet (`.env`…).
9. **Hors du lot.** Du travail qui reste et sort du lot → `split_ticket`.
10. **Fin.** Le bilan demandé par le prompt (bloc `escouade`, critères vérifiés par une commande). N'audite pas ton propre ticket et ne fusionne rien.
11. **Ticket renvoyé après un audit** (le commentaire liste des constats `F1`, `F2`…) : un commit par constat, avec `Refs F<n>` dans son message. Un constat que tu juges faux ne se corrige pas : conteste-le, avec la raison. Dans ton dernier message, mets d'abord le bilan (bloc `escouade`, lu où qu'il soit), puis ce bloc **en toutes dernières lignes**, en texte simple sans clôture de code, car l'auditeur ne reçoit que le début et la fin d'un long message :

   ```
   AUDIT:
   F1 corrigé 3f2a9c1
   F2 contesté : le cas vide est déjà refusé par la route
   ```

## Auditer et fusionner (session principale)

1. **Auditer** un ticket « À revoir » : `osho-core:audit-loop <CLÉ>` depuis la session principale. L'agent du ticket n'audite ni n'approuve jamais son propre ticket (Escouade le refuse de toute façon).
2. **Approuver** : `approve_ticket` répond dès le début de l'approbation (tests, commit, action du Kanban) ; `wait_ticket` jusqu'à ce que le ticket soit fini ou bloqué (240 s au plus par appel, repris avec `since`), puis lis son issue dans `get_ticket` (lien de la PR compris, blocage sur un conflit). Selon l'`action` de `get_board` :
   - `merge` → `git push origin <cible>`, depuis le dossier du projet (le `folder` de `list_projects`), car le worktree du ticket peut avoir été supprimé ; sinon la cible locale diverge d'`origin` et les tickets suivants partent d'une base fausse ;
   - `pr` → donne à l'utilisateur le lien de la PR ouverte par Escouade et arrête-toi : ne la fusionne jamais toi-même ;
   - `push`, `keep` → dis ce qu'Escouade a fait, rien de plus.
3. **Bloqué sur un conflit de fusion** (`get_ticket`) → `resolve_conflict`.

## Hors Escouade

Branche `feat/…`, PR, puis `osho-core:audit-loop` en mode PR.
